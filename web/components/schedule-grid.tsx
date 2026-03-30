"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ScheduleShift, ScheduleException, ScheduleSummary, ScheduleLifecycleState, Worker } from "@/lib/types";
import { batchShiftActions, bulkAssignShifts, bulkEditShifts } from "@/lib/shifts-api";
import type { BulkEditFields } from "@/lib/shifts-api";
import { EmptyState } from "./empty-state";
import { ShiftChip } from "./shift-chip";
import { AddShiftForm } from "./add-shift-form";

type ScheduleGridProps = {
  shifts: ScheduleShift[];
  exceptions: ScheduleException[];
  summary: ScheduleSummary;
  lifecycleState: ScheduleLifecycleState;
  weekStartDate: string;
  scheduleId?: number;
  workers?: Worker[];
};

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const BATCH_ACTION_LABELS: Record<string, string> = {
  start_coverage: "Start coverage",
  cancel_offer: "Cancel offer",
  close_shift: "Close shifts",
  reopen_shift: "Reopen",
  reopen_and_offer: "Reopen & offer",
};

function dateForDay(weekStart: string, dayIndex: number): string {
  const d = new Date(weekStart + "T00:00:00");
  d.setDate(d.getDate() + dayIndex);
  return d.toISOString().slice(0, 10);
}

function exceptionPillClass(ex: ScheduleException): string {
  if (ex.severity === "critical") return "pill pill-failed";
  if (ex.severity === "warning" || ex.action_required) return "pill pill-warning";
  if (ex.code?.startsWith("open_shift")) return "pill pill-open";
  if (ex.type === "open_shift") return "pill pill-open";
  return "pill";
}

function exceptionLabel(ex: ScheduleException): string {
  if (ex.code === "open_shift_closed") return "Closed";
  if (ex.code === "coverage_fill_approval_required") return "Fill approval";
  if (ex.code === "coverage_agency_approval_required") return "Agency approval";
  if (ex.code === "coverage_active") return "Coverage active";
  if (ex.code === "late_arrival_needs_review") return "Late";
  if (ex.code === "missed_check_in_needs_review") return "Missed check-in";
  if (ex.code === "missed_check_in_escalated") return "No-show";
  if (ex.code?.startsWith("open_shift")) return "Open";
  if (ex.type === "open_shift") return "Open";
  return ex.severity === "critical" ? "Critical" : "Warning";
}

function lifecyclePillClass(state: ScheduleLifecycleState): string {
  const map: Record<string, string> = {
    draft: "pill pill-draft",
    published: "pill pill-published",
    amended: "pill pill-amended",
    recalled: "pill pill-recalled",
    archived: "pill",
  };
  return map[state] ?? "pill";
}

function normalizeRole(value: string): string {
  return value.trim().toLowerCase();
}

function workerSupportsRole(worker: Worker, role: string): boolean {
  return (worker.roles ?? []).some((item) => normalizeRole(item) === normalizeRole(role));
}

function workerInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() ?? "").join("") || "?";
}

export function ScheduleGrid({
  shifts,
  exceptions,
  summary,
  lifecycleState,
  weekStartDate,
  scheduleId,
  workers = [],
}: ScheduleGridProps) {
  const router = useRouter();
  const [selectedShifts, setSelectedShifts] = useState<Set<number>>(new Set());
  const [selectMode, setSelectMode] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchFeedback, setBatchFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [assignWorkerId, setAssignWorkerId] = useState<number | "">("");
  const [showEditPanel, setShowEditPanel] = useState(false);

  const roles = [...new Set(shifts.map((s) => s.role))].sort();
  const dates = DAY_LABELS.map((_, i) => dateForDay(weekStartDate, i));
  const isReadOnly = lifecycleState === "archived";
  const roleSections = roles.map((role) => {
    const roleShifts = shifts.filter((shift) => shift.role === role);
    const openShifts = roleShifts.filter((shift) => !shift.assignment?.worker_id);
    const rosterWorkers = workers.filter((worker) => workerSupportsRole(worker, role));
    const assignedWorkers = Array.from(
      new Map(
        roleShifts
          .filter((shift) => shift.assignment?.worker_id && shift.assignment?.worker_name)
          .map((shift) => [
            Number(shift.assignment?.worker_id),
            {
              id: Number(shift.assignment?.worker_id),
              name: shift.assignment?.worker_name ?? "Assigned worker",
            },
          ]),
      ).values(),
    );
    const workerRows = [
      ...rosterWorkers.map((worker) => ({ id: worker.id, name: worker.name })),
      ...assignedWorkers.filter((worker) => !rosterWorkers.some((item) => item.id === worker.id)),
    ].sort((left, right) => left.name.localeCompare(right.name));

    return {
      role,
      openShifts,
      workerRows,
      scheduledCount: roleShifts.length,
      openCount: openShifts.length,
      filledCount: roleShifts.filter((shift) => Boolean(shift.assignment?.worker_id)).length,
    };
  });

  // Compute which batch actions are available for the selected shifts
  const selectedShiftObjects = shifts.filter((s) => selectedShifts.has(s.id));
  const commonActions = selectedShiftObjects.length > 0
    ? (selectedShiftObjects[0].available_actions ?? []).filter((action) =>
        selectedShiftObjects.every((s) => (s.available_actions ?? []).includes(action))
      )
    : [];

  function toggleSelect(shiftId: number) {
    setSelectedShifts((prev) => {
      const next = new Set(prev);
      if (next.has(shiftId)) next.delete(shiftId);
      else next.add(shiftId);
      return next;
    });
  }

  function exitSelectMode() {
    setSelectMode(false);
    setSelectedShifts(new Set());
    setBatchFeedback(null);
    setAssignWorkerId("");
    setShowEditPanel(false);
  }

  async function handleBatchAction(action: string) {
    if (!scheduleId || selectedShifts.size === 0) return;
    setBatchBusy(true);
    setBatchFeedback(null);
    const result = await batchShiftActions(scheduleId, [...selectedShifts], action);
    if (result) {
      setBatchFeedback({
        type: result.error_count > 0 ? "error" : "success",
        message: `${result.success_count} of ${result.processed_count} shifts updated.${result.error_count > 0 ? ` ${result.error_count} failed.` : ""}`,
      });
      setSelectedShifts(new Set());
      router.refresh();
    } else {
      setBatchFeedback({ type: "error", message: "Batch action failed." });
    }
    setBatchBusy(false);
  }

  async function handleBulkAssign(workerId: number | null) {
    if (!scheduleId || selectedShifts.size === 0) return;
    setBatchBusy(true);
    setBatchFeedback(null);
    const assignments = [...selectedShifts].map((shiftId) => ({
      shift_id: shiftId,
      worker_id: workerId,
    }));
    const result = await bulkAssignShifts(scheduleId, assignments);
    if (result) {
      setBatchFeedback({
        type: result.error_count > 0 ? "error" : "success",
        message: workerId
          ? `Assigned ${result.success_count} of ${result.processed_count} shifts.${result.error_count > 0 ? ` ${result.error_count} failed.` : ""}`
          : `Cleared ${result.success_count} of ${result.processed_count} assignments.${result.error_count > 0 ? ` ${result.error_count} failed.` : ""}`,
      });
      setSelectedShifts(new Set());
      setAssignWorkerId("");
      router.refresh();
    } else {
      setBatchFeedback({ type: "error", message: "Bulk assignment failed." });
    }
    setBatchBusy(false);
  }

  async function handleBulkEdit(fields: BulkEditFields) {
    if (!scheduleId || selectedShifts.size === 0) return;
    setBatchBusy(true);
    setBatchFeedback(null);
    const result = await bulkEditShifts(scheduleId, [...selectedShifts], fields);
    if (result) {
      setBatchFeedback({
        type: result.error_count > 0 ? "error" : "success",
        message: `Edited ${result.success_count} of ${result.processed_count} shifts.${result.error_count > 0 ? ` ${result.error_count} failed.` : ""}`,
      });
      setSelectedShifts(new Set());
      setShowEditPanel(false);
      router.refresh();
    } else {
      setBatchFeedback({ type: "error", message: "Bulk edit failed." });
    }
    setBatchBusy(false);
  }

  if (shifts.length === 0) {
    return (
      <div>
        <EmptyState
          title="No shifts this week"
          body="Import a schedule, copy last week, or create shifts manually to populate the grid."
        />
        {scheduleId && !isReadOnly && (
          <div style={{ marginTop: 16 }}>
            <AddShiftForm
              scheduleId={scheduleId}
              weekStartDate={weekStartDate}
              workers={workers}
              roles={[]}
            />
          </div>
        )}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Summary */}
      <div className="summary-bar">
        <div className="summary-bar-item">
          <strong>{summary.filled_shifts}</strong>
          <span>Filled</span>
        </div>
        <div className="summary-bar-item">
          <strong>{summary.open_shifts}</strong>
          <span>Open</span>
        </div>
        <div className="summary-bar-item">
          <strong>{summary.at_risk_shifts}</strong>
          <span>At risk</span>
        </div>
        {(summary.action_required_count ?? 0) > 0 && (
          <div className="summary-bar-item">
            <strong style={{ color: "var(--accent)" }}>{summary.action_required_count}</strong>
            <span>Action needed</span>
          </div>
        )}
        {(summary.attendance_issues ?? 0) > 0 && (
          <div className="summary-bar-item">
            <strong>{summary.attendance_issues}</strong>
            <span>Attendance</span>
          </div>
        )}
        {summary.warning_count > 0 && !(summary.action_required_count) && (
          <div className="summary-bar-item">
            <strong>{summary.warning_count}</strong>
            <span>Warnings</span>
          </div>
        )}
        <div className="summary-bar-item">
          <span className={lifecyclePillClass(lifecycleState)}>
            {lifecycleState}
          </span>
        </div>
      </div>

      {/* Batch action toolbar */}
      {scheduleId && !isReadOnly && (
        <div className="batch-toolbar">
          {selectMode ? (
            <>
              <span style={{ fontSize: "0.82rem", color: "var(--muted)" }}>
                {selectedShifts.size} selected
              </span>
              <div className="batch-toolbar-divider" />
              {commonActions.map((action) => (
                <button
                  key={action}
                  className="button-secondary button-small"
                  disabled={batchBusy || selectedShifts.size === 0}
                  onClick={() => handleBatchAction(action)}
                >
                  {batchBusy ? "\u2026" : (BATCH_ACTION_LABELS[action] ?? action.replace(/_/g, " "))}
                </button>
              ))}
              {selectedShifts.size > 0 && (
                <>
                  <div className="batch-toolbar-divider" />
                  <select
                    className="settings-select"
                    style={{ margin: 0, maxWidth: 180, padding: "6px 28px 6px 10px", fontSize: "0.78rem" }}
                    value={assignWorkerId}
                    onChange={(e) => setAssignWorkerId(e.target.value ? Number(e.target.value) : "")}
                  >
                    <option value="">Assign to\u2026</option>
                    {workers.map((w) => (
                      <option key={w.id} value={w.id}>{w.name}</option>
                    ))}
                  </select>
                  {assignWorkerId !== "" && (
                    <button
                      className="button button-small"
                      disabled={batchBusy}
                      onClick={() => handleBulkAssign(Number(assignWorkerId))}
                    >
                      {batchBusy ? "\u2026" : "Assign"}
                    </button>
                  )}
                  <button
                    className="button-secondary button-small"
                    disabled={batchBusy}
                    onClick={() => handleBulkAssign(null)}
                  >
                    Clear assignment
                  </button>
                </>
              )}
              {selectedShifts.size > 0 && (
                <>
                  <div className="batch-toolbar-divider" />
                  <button
                    className="button-secondary button-small"
                    onClick={() => setShowEditPanel(!showEditPanel)}
                  >
                    {showEditPanel ? "Hide edit" : "Edit details"}
                  </button>
                </>
              )}
              <div className="batch-toolbar-divider" />
              <button className="button-secondary button-small" onClick={exitSelectMode}>
                Done
              </button>
            </>
          ) : (
            <button className="button-secondary button-small" onClick={() => setSelectMode(true)}>
              Select shifts
            </button>
          )}
          {batchFeedback && (
            <span style={{
              fontSize: "0.78rem",
              padding: "4px 10px",
              borderRadius: "var(--radius-sm)",
              background: batchFeedback.type === "success" ? "rgba(39, 174, 96, 0.04)" : "rgba(191, 91, 57, 0.04)",
              color: batchFeedback.type === "success" ? "#1a7a42" : "var(--accent)",
            }}>
              {batchFeedback.message}
            </span>
          )}
        </div>
      )}

      {/* Bulk edit panel */}
      {showEditPanel && selectedShifts.size > 0 && (
        <BulkEditPanel
          roles={roles}
          busy={batchBusy}
          onApply={handleBulkEdit}
          onCancel={() => setShowEditPanel(false)}
        />
      )}

      {/* Grid */}
      <div className="schedule-board">
        {roleSections.map((section) => (
          <section key={section.role} className="schedule-roster-group">
            <div className="schedule-roster-group-head">
              <div>
                <h4>{section.role}</h4>
                <p>
                  {section.filledCount} covered · {section.openCount} open · {section.workerRows.length} people in the lane
                </p>
              </div>
              <span className="schedule-roster-group-pill">{section.scheduledCount} shifts</span>
            </div>

            <div className="schedule-roster-grid">
              <div className="schedule-roster-head schedule-roster-head-label">Team</div>
              {DAY_LABELS.map((day, i) => (
                <div key={`${section.role}-${day}`} className="schedule-roster-head">
                  {day}
                  <span>{dates[i].slice(5)}</span>
                </div>
              ))}

              <div className="schedule-roster-person schedule-roster-person-open">
                <div className="schedule-roster-avatar schedule-roster-avatar-open">+</div>
                <div className="schedule-roster-person-text">
                  <strong>Open shifts</strong>
                  <span>
                    {section.openCount > 0
                      ? `${section.openCount} shifts still need coverage`
                      : "No open shifts in this role lane"}
                  </span>
                </div>
              </div>
              {dates.map((date) => {
                const dayShifts = section.openShifts.filter((shift) => shift.date === date);
                return (
                  <div
                    key={`${section.role}-open-${date}`}
                    className={`schedule-roster-cell${dayShifts.length === 0 ? " schedule-roster-cell-empty" : ""}`}
                  >
                    {dayShifts.map((shift) => (
                      <ShiftChip
                        key={shift.id}
                        shiftId={shift.id}
                        workerName={shift.assignment?.worker_name ?? null}
                        workerId={shift.assignment?.worker_id ?? null}
                        startTime={shift.start_time}
                        endTime={shift.end_time}
                        workers={workers}
                        canDelete={!isReadOnly}
                        coverageStatus={shift.coverage?.status ?? null}
                        filledViaBackfill={shift.assignment?.filled_via_backfill ?? false}
                        confirmationStatus={shift.confirmation?.status ?? null}
                        attendanceStatus={shift.attendance?.status ?? null}
                        availableActions={shift.available_actions}
                        selectable={selectMode}
                        selected={selectedShifts.has(shift.id)}
                        onSelect={toggleSelect}
                      />
                    ))}
                  </div>
                );
              })}

              {section.workerRows.map((worker) => (
                <div key={`${section.role}-${worker.id}`} className="schedule-roster-row">
                  <div className="schedule-roster-person">
                    <div className="schedule-roster-avatar">{workerInitials(worker.name)}</div>
                    <div className="schedule-roster-person-text">
                      <strong>{worker.name}</strong>
                      <span>{section.role}</span>
                    </div>
                  </div>
                  {dates.map((date) => {
                    const dayShifts = shifts.filter(
                      (shift) =>
                        shift.role === section.role &&
                        shift.date === date &&
                        shift.assignment?.worker_id === worker.id,
                    );
                    return (
                      <div
                        key={`${section.role}-${worker.id}-${date}`}
                        className={`schedule-roster-cell${dayShifts.length === 0 ? " schedule-roster-cell-empty" : ""}`}
                      >
                        {dayShifts.map((shift) => (
                          <ShiftChip
                            key={shift.id}
                            shiftId={shift.id}
                            workerName={shift.assignment?.worker_name ?? null}
                            workerId={shift.assignment?.worker_id ?? null}
                            startTime={shift.start_time}
                            endTime={shift.end_time}
                            workers={workers}
                            canDelete={!isReadOnly}
                            coverageStatus={shift.coverage?.status ?? null}
                            filledViaBackfill={shift.assignment?.filled_via_backfill ?? false}
                            confirmationStatus={shift.confirmation?.status ?? null}
                            attendanceStatus={shift.attendance?.status ?? null}
                            availableActions={shift.available_actions}
                            selectable={selectMode}
                            selected={selectedShifts.has(shift.id)}
                            onSelect={toggleSelect}
                          />
                        ))}
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>

      {/* Add shift */}
      {scheduleId && !isReadOnly && (
        <AddShiftForm
          scheduleId={scheduleId}
          weekStartDate={weekStartDate}
          workers={workers}
          roles={roles}
        />
      )}

      {/* Exceptions */}
      {exceptions.length > 0 && (
        <div>
          <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Exceptions ({exceptions.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {exceptions.map((ex, i) => (
              <div
                key={i}
                className="sched-exception"
                style={ex.action_required ? { borderLeftColor: "var(--accent)" } : undefined}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span className={exceptionPillClass(ex)}>
                    {exceptionLabel(ex)}
                  </span>
                  <span style={{ fontSize: "0.85rem" }}>{ex.message}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Bulk edit panel ───────────────────────────────────────────────────────

function BulkEditPanel({
  roles,
  busy,
  onApply,
  onCancel,
}: {
  roles: string[];
  busy: boolean;
  onApply: (fields: BulkEditFields) => void;
  onCancel: () => void;
}) {
  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const fields: BulkEditFields = {};

    const role = String(form.get("role") ?? "").trim();
    const startTime = String(form.get("start_time") ?? "").trim();
    const endTime = String(form.get("end_time") ?? "").trim();
    const notes = String(form.get("notes") ?? "").trim();

    if (role) fields.role = role;
    if (startTime) fields.start_time = startTime;
    if (endTime) fields.end_time = endTime;
    if (notes) fields.notes = notes;

    if (Object.keys(fields).length === 0) return;
    onApply(fields);
  }

  return (
    <div style={{
      padding: 20,
      borderRadius: "var(--radius-lg)",
      background: "var(--panel)",
      border: "1px solid var(--line)",
      boxShadow: "var(--shadow)",
    }}>
      <div style={{ fontSize: "0.82rem", fontWeight: 600, marginBottom: 12, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
        Edit selected shifts
      </div>
      <form onSubmit={handleSubmit}>
        <div className="form-grid">
          <label className="field">
            <span>Role</span>
            <input name="role" list="edit-role-list" placeholder="Leave blank to keep" />
            <datalist id="edit-role-list">
              {roles.map((r) => (
                <option key={r} value={r} />
              ))}
            </datalist>
          </label>
          <label className="field">
            <span>Notes</span>
            <input name="notes" placeholder="Leave blank to keep" />
          </label>
          <label className="field">
            <span>Start time</span>
            <input name="start_time" type="time" />
          </label>
          <label className="field">
            <span>End time</span>
            <input name="end_time" type="time" />
          </label>
        </div>
        <div className="cta-row" style={{ marginTop: 16 }}>
          <button className="button button-small" type="submit" disabled={busy}>
            {busy ? "Applying\u2026" : "Apply changes"}
          </button>
          <button className="button-secondary button-small" type="button" onClick={onCancel}>
            Cancel
          </button>
        </div>
        <div style={{ fontSize: "0.75rem", color: "var(--muted)", marginTop: 8 }}>
          Only fill the fields you want to change. Blank fields are left unchanged.
        </div>
      </form>
    </div>
  );
}
