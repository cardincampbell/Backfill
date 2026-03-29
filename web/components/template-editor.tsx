"use client";

import { useState } from "react";
import type { ScheduleTemplate, TemplateSlot, TemplatePreviewResponse, StaffingPlan } from "@/lib/types";
import {
  getTemplate,
  createTemplateSlot,
  editTemplateSlot,
  duplicateTemplateSlot,
  deleteTemplateSlot,
  previewTemplate,
  bulkDuplicateTemplateSlots,
  bulkDeleteTemplateSlots,
  getStaffingPlan,
  autoAssignTemplate,
  applySuggestions,
  clearTemplateAssignments,
} from "@/lib/shifts-api";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DEFAULT_ROLES = ["Server", "Bartender", "Host", "Cook", "Cashier", "Manager"];

function formatTime(t: string): string {
  return t.slice(0, 5);
}

function formatDate(date: string): string {
  const d = new Date(date + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatHours(h: number): string {
  return h % 1 === 0 ? `${h}h` : `${h.toFixed(1)}h`;
}

function futureMondays(count: number): string[] {
  const today = new Date();
  const day = today.getDay();
  const diff = day === 0 ? 1 : 8 - day;
  const result: string[] = [];
  for (let i = 0; i < count; i++) {
    const d = new Date(today);
    d.setDate(today.getDate() + diff + i * 7);
    result.push(d.toISOString().slice(0, 10));
  }
  return result;
}

// ── Add slot form ─────────────────────────────────────────────────────────

function AddSlotForm({
  templateId,
  dayOfWeek,
  existingRoles,
  onAdded,
}: {
  templateId: number;
  dayOfWeek: number;
  existingRoles: string[];
  onAdded: (slot: TemplateSlot) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [role, setRole] = useState("");
  const [startTime, setStartTime] = useState("09:00");
  const [endTime, setEndTime] = useState("17:00");

  async function handleAdd() {
    const r = role.trim();
    if (!r) return;
    setBusy(true);
    const result = await createTemplateSlot(templateId, {
      role: r,
      day_of_week: dayOfWeek,
      start_time: startTime,
      end_time: endTime,
    });
    if (result) {
      onAdded(result);
      setRole("");
    }
    setBusy(false);
  }

  return (
    <div style={{ display: "flex", gap: 6, alignItems: "end", flexWrap: "wrap" }}>
      <label className="field" style={{ flex: "1 1 100px", minWidth: 0 }}>
        <span style={{ fontSize: "0.72rem" }}>Role</span>
        <input
          list={`roles-${dayOfWeek}`}
          value={role}
          onChange={(e) => setRole(e.target.value)}
          placeholder="Role"
          style={{ fontSize: "0.82rem" }}
        />
        <datalist id={`roles-${dayOfWeek}`}>
          {existingRoles.map((r) => (
            <option key={r} value={r} />
          ))}
        </datalist>
      </label>
      <label className="field" style={{ flex: "0 0 90px" }}>
        <span style={{ fontSize: "0.72rem" }}>Start</span>
        <input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} style={{ fontSize: "0.82rem" }} />
      </label>
      <label className="field" style={{ flex: "0 0 90px" }}>
        <span style={{ fontSize: "0.72rem" }}>End</span>
        <input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} style={{ fontSize: "0.82rem" }} />
      </label>
      <button
        className="button button-small"
        disabled={busy || !role.trim()}
        onClick={handleAdd}
        style={{ marginBottom: 1 }}
      >
        {busy ? "Adding\u2026" : "Add"}
      </button>
    </div>
  );
}

// ── Slot row ──────────────────────────────────────────────────────────────

function SlotRow({
  slot,
  selected,
  onToggleSelect,
  onUpdated,
  onDuplicated,
  onDeleted,
}: {
  slot: TemplateSlot;
  selected: boolean;
  onToggleSelect: (id: number) => void;
  onUpdated: (slot: TemplateSlot) => void;
  onDuplicated: (slot: TemplateSlot) => void;
  onDeleted: (id: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [editRole, setEditRole] = useState(slot.role);
  const [editStart, setEditStart] = useState(slot.start_time.slice(0, 5));
  const [editEnd, setEditEnd] = useState(slot.end_time.slice(0, 5));
  const [editNotes, setEditNotes] = useState(slot.notes ?? "");

  const hasWarnings = slot.warnings && slot.warnings.length > 0;
  const isOverlap = slot.warnings?.some((w) => w.code === "template_overlap");

  async function handleSave() {
    if (!slot.id) return;
    setBusy(true);
    const result = await editTemplateSlot(slot.id, {
      role: editRole.trim() || undefined,
      start_time: editStart || undefined,
      end_time: editEnd || undefined,
      notes: editNotes.trim() || undefined,
    });
    if (result) {
      onUpdated(result);
      setEditing(false);
    }
    setBusy(false);
  }

  async function handleDuplicate() {
    if (!slot.id) return;
    setBusy(true);
    const result = await duplicateTemplateSlot(slot.id);
    if (result) onDuplicated(result);
    setBusy(false);
  }

  async function handleDelete() {
    if (!slot.id) return;
    setBusy(true);
    const ok = await deleteTemplateSlot(slot.id);
    if (ok) onDeleted(slot.id);
    setBusy(false);
  }

  if (editing) {
    return (
      <div style={{ display: "flex", gap: 6, alignItems: "end", flexWrap: "wrap", padding: "6px 0" }}>
        <label className="field" style={{ flex: "1 1 80px", minWidth: 0 }}>
          <span style={{ fontSize: "0.72rem" }}>Role</span>
          <input value={editRole} onChange={(e) => setEditRole(e.target.value)} style={{ fontSize: "0.82rem" }} />
        </label>
        <label className="field" style={{ flex: "0 0 90px" }}>
          <span style={{ fontSize: "0.72rem" }}>Start</span>
          <input type="time" value={editStart} onChange={(e) => setEditStart(e.target.value)} style={{ fontSize: "0.82rem" }} />
        </label>
        <label className="field" style={{ flex: "0 0 90px" }}>
          <span style={{ fontSize: "0.72rem" }}>End</span>
          <input type="time" value={editEnd} onChange={(e) => setEditEnd(e.target.value)} style={{ fontSize: "0.82rem" }} />
        </label>
        <label className="field" style={{ flex: "1 1 100px", minWidth: 0 }}>
          <span style={{ fontSize: "0.72rem" }}>Notes</span>
          <input value={editNotes} onChange={(e) => setEditNotes(e.target.value)} placeholder="Optional" style={{ fontSize: "0.82rem" }} />
        </label>
        <div style={{ display: "flex", gap: 4, marginBottom: 1 }}>
          <button className="button button-small" disabled={busy} onClick={handleSave}>
            {busy ? "Saving\u2026" : "Save"}
          </button>
          <button className="button-secondary button-small" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: 8,
      padding: "5px 0",
      borderBottom: "1px solid rgba(0,0,0,0.04)",
      fontSize: "0.82rem",
      background: isOverlap ? "rgba(191, 91, 57, 0.03)" : undefined,
    }}>
      {slot.id && (
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onToggleSelect(slot.id!)}
          style={{ accentColor: "var(--brand)" }}
        />
      )}
      <span style={{ fontWeight: 500, minWidth: 70 }}>{slot.role}</span>
      <span style={{ color: "var(--muted)", fontVariantNumeric: "tabular-nums" }}>
        {formatTime(slot.start_time)}{"\u2013"}{formatTime(slot.end_time)}
      </span>
      {slot.worker_name && (
        <span style={{ color: "var(--muted)", fontSize: "0.78rem" }}>{slot.worker_name}</span>
      )}
      {hasWarnings && (
        <span
          style={{ fontSize: "0.72rem", color: "var(--accent)", fontWeight: 500 }}
          title={slot.warnings!.map((w) => w.message).join("; ")}
        >
          {isOverlap ? "Overlap" : `${slot.warnings!.length} warning${slot.warnings!.length !== 1 ? "s" : ""}`}
        </span>
      )}
      {slot.notes && (
        <span style={{ color: "var(--muted)", fontSize: "0.75rem", fontStyle: "italic" }}>{slot.notes}</span>
      )}
      <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
        <button className="button-secondary button-small" disabled={busy} onClick={() => setEditing(true)} style={{ fontSize: "0.72rem", padding: "2px 8px" }}>
          Edit
        </button>
        <button className="button-secondary button-small" disabled={busy} onClick={handleDuplicate} style={{ fontSize: "0.72rem", padding: "2px 8px" }}>
          Duplicate
        </button>
        <button className="button-secondary button-small" disabled={busy} onClick={handleDelete} style={{ fontSize: "0.72rem", padding: "2px 8px", color: "var(--accent)" }}>
          Remove
        </button>
      </div>
    </div>
  );
}

// ── Template summaries ────────────────────────────────────────────────────

function TemplateSummaries({ template }: { template: ScheduleTemplate }) {
  const { daily_summary, role_summary, worker_summary } = template;
  if (!daily_summary && !role_summary && !worker_summary) return null;

  return (
    <div style={{ display: "flex", gap: 20, flexWrap: "wrap", fontSize: "0.78rem" }}>
      {daily_summary && daily_summary.length > 0 && (
        <div style={{ minWidth: 120 }}>
          <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
            By day
          </div>
          {daily_summary.map((d) => (
            <div key={d.day_of_week} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <span>{DAY_LABELS[d.day_of_week]}</span>
              <span style={{ color: "var(--muted)" }}>{d.slot_count} slots · {formatHours(d.total_hours)}</span>
            </div>
          ))}
        </div>
      )}
      {role_summary && role_summary.length > 0 && (
        <div style={{ minWidth: 140 }}>
          <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
            By role
          </div>
          {role_summary.map((r) => (
            <div key={r.role} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <span>{r.role}</span>
              <span style={{ color: "var(--muted)" }}>{r.slot_count} slots · {formatHours(r.total_hours)}</span>
            </div>
          ))}
        </div>
      )}
      {worker_summary && worker_summary.length > 0 && (
        <div style={{ minWidth: 160 }}>
          <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
            By worker
          </div>
          {worker_summary.map((w) => (
            <div key={w.worker_id} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <span>{w.worker_name}</span>
              <span style={{ color: "var(--muted)" }}>{w.slot_count} slots · {formatHours(w.total_hours)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Staffing plan panel ───────────────────────────────────────────────────

const STRATEGY_OPTIONS: { value: import("@/lib/types").AssignmentStrategy; label: string; desc: string }[] = [
  { value: "priority_first", label: "Priority first", desc: "Assign top-ranked workers first" },
  { value: "balance_hours", label: "Balance hours", desc: "Spread hours evenly across workers" },
  { value: "minimize_overtime", label: "Minimize overtime", desc: "Avoid exceeding max weekly hours" },
];

function StaffingPlanPanel({
  templateId,
  onTemplateChanged,
}: {
  templateId: number;
  onTemplateChanged: (t: ScheduleTemplate) => void;
}) {
  const [plan, setPlan] = useState<StaffingPlan | null>(null);
  const [strategy, setStrategy] = useState<import("@/lib/types").AssignmentStrategy>("balance_hours");
  const [busy, setBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  async function loadPlan(s?: import("@/lib/types").AssignmentStrategy) {
    setBusy(true);
    const result = await getStaffingPlan(templateId, s ?? strategy);
    setPlan(result);
    setBusy(false);
  }

  async function handleStrategyChange(s: import("@/lib/types").AssignmentStrategy) {
    setStrategy(s);
    await loadPlan(s);
  }

  async function handleAutoAssign() {
    setActionBusy(true);
    setFeedback(null);
    const result = await autoAssignTemplate(templateId, strategy);
    if (result) {
      setFeedback({
        type: "success",
        message: `Auto-assigned ${result.assigned_count} slot${result.assigned_count !== 1 ? "s" : ""}${result.skipped_count > 0 ? `, ${result.skipped_count} skipped` : ""}.`,
      });
      onTemplateChanged(result.template);
      const updated = await getStaffingPlan(templateId, strategy);
      setPlan(updated);
    } else {
      setFeedback({ type: "error", message: "Auto-assign failed." });
    }
    setActionBusy(false);
  }

  async function handleApplySuggestions() {
    setActionBusy(true);
    setFeedback(null);
    const result = await applySuggestions(templateId);
    if (result) {
      setFeedback({
        type: "success",
        message: `Applied ${result.applied_count} suggestion${result.applied_count !== 1 ? "s" : ""}${result.skipped_count > 0 ? `, ${result.skipped_count} skipped` : ""}.`,
      });
      onTemplateChanged(result.template);
      const updated = await getStaffingPlan(templateId, strategy);
      setPlan(updated);
    } else {
      setFeedback({ type: "error", message: "Failed to apply suggestions." });
    }
    setActionBusy(false);
  }

  async function handleClearAssignments() {
    setActionBusy(true);
    setFeedback(null);
    const result = await clearTemplateAssignments(templateId);
    if (result) {
      setFeedback({ type: "success", message: "All assignments cleared." });
      onTemplateChanged(result);
      const updated = await getStaffingPlan(templateId, strategy);
      setPlan(updated);
    } else {
      setFeedback({ type: "error", message: "Failed to clear assignments." });
    }
    setActionBusy(false);
  }

  if (!plan) {
    return (
      <div>
        <div style={{ fontSize: "0.78rem", fontWeight: 600, marginBottom: 8 }}>Staffing plan</div>
        <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 8 }}>
          <span style={{ fontSize: "0.72rem", color: "var(--muted)" }}>Strategy:</span>
          {STRATEGY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              className={strategy === opt.value ? "button button-small" : "button-secondary button-small"}
              onClick={() => setStrategy(opt.value)}
              title={opt.desc}
              style={{ fontSize: "0.72rem", padding: "2px 8px" }}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <button className="button-secondary button-small" onClick={() => loadPlan()} disabled={busy}>
          {busy ? "Loading\u2026" : "Load staffing plan"}
        </button>
      </div>
    );
  }

  const reviewCount = plan.review_required_count ?? 0;
  const recommendedCount = plan.recommended_assignment_count ?? 0;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div style={{ fontSize: "0.78rem", fontWeight: 600 }}>Staffing plan</div>
        {plan.ready_to_generate != null && (
          <span style={{
            fontSize: "0.68rem",
            fontWeight: 600,
            padding: "1px 6px",
            borderRadius: 999,
            background: plan.ready_to_generate ? "rgba(39, 174, 96, 0.08)" : "rgba(191, 91, 57, 0.08)",
            color: plan.ready_to_generate ? "#1a7a42" : "var(--accent)",
          }}>
            {plan.ready_to_publish ? "Ready to publish" : plan.ready_to_generate ? "Ready to generate" : "Needs review"}
          </span>
        )}
      </div>

      {/* Strategy picker */}
      <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 12 }}>
        <span style={{ fontSize: "0.72rem", color: "var(--muted)" }}>Strategy:</span>
        {STRATEGY_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            className={strategy === opt.value ? "button button-small" : "button-secondary button-small"}
            onClick={() => handleStrategyChange(opt.value)}
            disabled={busy}
            title={opt.desc}
            style={{ fontSize: "0.72rem", padding: "2px 8px" }}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Summary stats */}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: "0.78rem", marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: "0.72rem", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Eligible</div>
          <div style={{ fontWeight: 600 }}>{plan.eligible_worker_count}</div>
        </div>
        <div>
          <div style={{ fontSize: "0.72rem", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Auto-assignable</div>
          <div style={{ fontWeight: 600 }}>{plan.auto_assignable_shift_count}</div>
        </div>
        {recommendedCount > 0 && (
          <div>
            <div style={{ fontSize: "0.72rem", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Recommended</div>
            <div style={{ fontWeight: 600 }}>{recommendedCount}</div>
          </div>
        )}
        <div>
          <div style={{ fontSize: "0.72rem", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Gaps</div>
          <div style={{ fontWeight: 600, color: plan.staffing_gap_count > 0 ? "var(--accent)" : undefined }}>
            {plan.staffing_gap_count}
          </div>
        </div>
        {reviewCount > 0 && (
          <div>
            <div style={{ fontSize: "0.72rem", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Needs review</div>
            <div style={{ fontWeight: 600, color: "var(--accent)" }}>{reviewCount}</div>
          </div>
        )}
        <div>
          <div style={{ fontSize: "0.72rem", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>OT risk</div>
          <div style={{ fontWeight: 600, color: plan.overtime_risk_count > 0 ? "var(--accent)" : undefined }}>
            {plan.overtime_risk_count}
          </div>
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
        {plan.auto_assignable_shift_count > 0 && (
          <button className="button button-small" onClick={handleAutoAssign} disabled={actionBusy}>
            {actionBusy ? "Working\u2026" : `Auto-assign ${plan.auto_assignable_shift_count}`}
          </button>
        )}
        {recommendedCount > 0 && (
          <button className="button-secondary button-small" onClick={handleApplySuggestions} disabled={actionBusy}>
            Apply {recommendedCount} suggestions
          </button>
        )}
        <button
          className="button-secondary button-small"
          onClick={handleClearAssignments}
          disabled={actionBusy}
          style={{ color: "var(--accent)" }}
        >
          Clear all assignments
        </button>
      </div>

      {feedback && (
        <div style={{
          fontSize: "0.82rem",
          marginBottom: 12,
          padding: "6px 10px",
          borderRadius: "var(--radius-sm)",
          background: feedback.type === "success" ? "rgba(39, 174, 96, 0.04)" : "rgba(191, 91, 57, 0.04)",
          color: feedback.type === "success" ? "#1a7a42" : "var(--accent)",
        }}>
          {feedback.message}
        </div>
      )}

      {/* Worker capacities */}
      {plan.worker_capacities.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
            Worker capacity
          </div>
          <div style={{ fontSize: "0.78rem" }}>
            {plan.worker_capacities.map((w) => (
              <div key={w.worker_id} style={{
                display: "flex",
                justifyContent: "space-between",
                gap: 12,
                padding: "3px 0",
                borderBottom: "1px solid rgba(0,0,0,0.04)",
                color: w.overtime_risk ? "var(--accent)" : undefined,
              }}>
                <span>{w.worker_name}</span>
                <span style={{ color: w.at_capacity ? "var(--accent)" : "var(--muted)", fontVariantNumeric: "tabular-nums" }}>
                  {formatHours(w.template_hours)}
                  {w.max_hours_per_week != null ? ` / ${formatHours(w.max_hours_per_week)}` : ""}
                  {w.overtime_risk ? " (overtime risk)" : ""}
                  {w.at_capacity && !w.overtime_risk ? " (at capacity)" : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Slot suggestions with richer metadata */}
      {plan.slot_suggestions.length > 0 && (
        <div>
          <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
            Suggestions
          </div>
          <div style={{ fontSize: "0.78rem" }}>
            {plan.slot_suggestions.filter((s) => s.suggested_workers.length > 0 || s.needs_review).slice(0, 25).map((s) => (
              <div key={s.slot_id} style={{
                padding: "4px 0",
                borderBottom: "1px solid rgba(0,0,0,0.04)",
                background: s.needs_review ? "rgba(191, 91, 57, 0.02)" : undefined,
              }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span style={{ fontWeight: 500 }}>{s.role}</span>
                  <span style={{ color: "var(--muted)" }}>
                    {DAY_LABELS[s.day_of_week]} {formatTime(s.start_time)}{"\u2013"}{formatTime(s.end_time)}
                  </span>
                  {s.recommended_worker_name && (
                    <span style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--brand, #0071e3)" }}>
                      {"\u2192"} {s.recommended_worker_name}
                    </span>
                  )}
                  {s.needs_review && (
                    <span style={{ fontSize: "0.68rem", padding: "0 4px", borderRadius: 999, background: "rgba(191, 91, 57, 0.08)", color: "var(--accent)" }}>
                      Review
                    </span>
                  )}
                </div>
                <div style={{ display: "flex", gap: 6, marginTop: 2, flexWrap: "wrap" }}>
                  {s.suggested_workers.slice(0, 3).map((w) => (
                    <span key={w.worker_id} style={{
                      fontSize: "0.72rem",
                      padding: "1px 6px",
                      borderRadius: 999,
                      background: "rgba(0, 113, 227, 0.06)",
                      color: "var(--brand, #0071e3)",
                    }}>
                      {w.rank != null ? `#${w.rank} ` : ""}{w.worker_name}
                      {w.confidence != null ? ` (${Math.round(w.confidence * 100)}%)` : ""}
                      {w.reason ? ` \u2014 ${w.reason}` : ""}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ marginTop: 8 }}>
        <button className="button-secondary button-small" onClick={() => loadPlan()} disabled={busy} style={{ fontSize: "0.72rem" }}>
          {busy ? "Refreshing\u2026" : "Refresh plan"}
        </button>
      </div>
    </div>
  );
}

// ── Preview panel ─────────────────────────────────────────────────────────

function PreviewPanel({ templateId }: { templateId: number }) {
  const [preview, setPreview] = useState<TemplatePreviewResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [dayFilter, setDayFilter] = useState<Set<number>>(new Set());
  const weeks = futureMondays(4);

  function toggleDayFilter(day: number) {
    setDayFilter((prev) => {
      const next = new Set(prev);
      if (next.has(day)) next.delete(day);
      else next.add(day);
      return next;
    });
  }

  async function handlePreview(week: string) {
    setBusy(true);
    const filter = dayFilter.size > 0 ? [...dayFilter].sort() : undefined;
    const result = await previewTemplate(templateId, week, filter);
    setPreview(result);
    setBusy(false);
  }

  return (
    <div>
      <div style={{ fontSize: "0.78rem", fontWeight: 600, marginBottom: 8 }}>Preview for a target week</div>

      {/* Day filter toggles */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
        <span style={{ fontSize: "0.72rem", color: "var(--muted)", alignSelf: "center" }}>Filter days:</span>
        {DAY_LABELS.map((day, i) => (
          <button
            key={day}
            className={dayFilter.has(i) ? "button button-small" : "button-secondary button-small"}
            onClick={() => toggleDayFilter(i)}
            style={{ fontSize: "0.72rem", padding: "2px 8px" }}
          >
            {day}
          </button>
        ))}
        {dayFilter.size > 0 && (
          <button
            className="button-secondary button-small"
            onClick={() => setDayFilter(new Set())}
            style={{ fontSize: "0.72rem", padding: "2px 8px" }}
          >
            Clear
          </button>
        )}
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
        {weeks.map((w) => (
          <button
            key={w}
            className="button-secondary button-small"
            disabled={busy}
            onClick={() => handlePreview(w)}
            style={{ fontVariantNumeric: "tabular-nums" }}
          >
            {formatDate(w)}
          </button>
        ))}
      </div>
      {preview && (
        <div style={{ fontSize: "0.82rem" }}>
          <div style={{ marginBottom: 8, display: "flex", gap: 12, flexWrap: "wrap" }}>
            <span><strong>{preview.summary.total_shifts}</strong> shifts</span>
            <span><strong>{preview.summary.assigned_shifts}</strong> assigned</span>
            <span><strong>{preview.summary.open_shifts}</strong> open</span>
            {preview.existing_schedule_id && (
              <span style={{ color: "var(--accent)" }}>
                Existing schedule with {preview.existing_shift_count ?? 0} shifts {preview.replace_required ? "(replace required)" : ""}
              </span>
            )}
          </div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            {DAY_LABELS.map((day, i) => {
              const dayShifts = preview.shifts.filter((s) => {
                const d = new Date(s.date + "T00:00:00");
                return d.getDay() === (i + 1) % 7;
              });
              if (dayFilter.size > 0 && !dayFilter.has(i)) return null;
              return (
                <div key={day} style={{ minWidth: 90 }}>
                  <div style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
                    {day}
                  </div>
                  {dayShifts.length === 0 ? (
                    <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>{"\u2014"}</div>
                  ) : (
                    dayShifts.map((s, j) => (
                      <div key={j} style={{ fontSize: "0.78rem", marginBottom: 2 }}>
                        <span style={{ fontWeight: 500 }}>{s.role}</span>
                        <span style={{ color: "var(--muted)", marginLeft: 4 }}>
                          {formatTime(s.start_time)}{"\u2013"}{formatTime(s.end_time)}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main editor ───────────────────────────────────────────────────────────

type TemplateEditorProps = {
  template: ScheduleTemplate;
  onClose: () => void;
  onTemplateChanged: (t: ScheduleTemplate) => void;
};

export function TemplateEditor({ template: initialTemplate, onClose, onTemplateChanged }: TemplateEditorProps) {
  const [template, setTemplate] = useState(initialTemplate);
  const [showPreview, setShowPreview] = useState(false);
  const [showSummaries, setShowSummaries] = useState(false);
  const [showStaffing, setShowStaffing] = useState(false);
  const [selectedSlots, setSelectedSlots] = useState<Set<number>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  const existingRoles = [...new Set(template.slots.map((s) => s.role))].sort();
  const allRoles = [...new Set([...existingRoles, ...DEFAULT_ROLES])].sort();
  const validation = template.validation_summary;
  const warnings = template.template_warnings;

  function updateTemplate(t: ScheduleTemplate) {
    setTemplate(t);
    onTemplateChanged(t);
    // Clear selection of slots that no longer exist
    const validIds = new Set(t.slots.filter((s) => s.id).map((s) => s.id!));
    setSelectedSlots((prev) => {
      const next = new Set([...prev].filter((id) => validIds.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }

  function refreshTemplateData() {
    getTemplate(template.id).then((t) => {
      if (t) updateTemplate(t);
    });
  }

  function handleSlotChange() {
    refreshTemplateData();
  }

  function toggleSlotSelect(id: number) {
    setSelectedSlots((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // ── Bulk actions ──

  async function handleBulkDuplicate() {
    if (selectedSlots.size === 0) return;
    setBulkBusy(true);
    const result = await bulkDuplicateTemplateSlots(template.id, [...selectedSlots]);
    if (result?.template) {
      updateTemplate(result.template);
      setSelectedSlots(new Set());
    }
    setBulkBusy(false);
  }

  async function handleBulkDelete() {
    if (selectedSlots.size === 0) return;
    setBulkBusy(true);
    const result = await bulkDeleteTemplateSlots(template.id, [...selectedSlots]);
    if (result?.template) {
      updateTemplate(result.template);
      setSelectedSlots(new Set());
    }
    setBulkBusy(false);
  }

  function selectAllDay(dayIndex: number) {
    const dayIds = template.slots.filter((s) => s.day_of_week === dayIndex && s.id).map((s) => s.id!);
    setSelectedSlots((prev) => {
      const allSelected = dayIds.every((id) => prev.has(id));
      const next = new Set(prev);
      if (allSelected) {
        dayIds.forEach((id) => next.delete(id));
      } else {
        dayIds.forEach((id) => next.add(id));
      }
      return next;
    });
  }

  return (
    <div className="settings-card" style={{ border: "2px solid var(--brand, #0071e3)" }}>
      <div className="settings-card-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>Editing: {template.name}</span>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {validation && (
            <span style={{
              fontSize: "0.72rem",
              fontWeight: 500,
              color: validation.ready ? "#1a7a42" : "var(--accent)",
            }}>
              {validation.ready
                ? "Ready"
                : `${validation.warning_count} warning${validation.warning_count !== 1 ? "s" : ""}`}
              {validation.overlap_count ? ` · ${validation.overlap_count} overlap${validation.overlap_count !== 1 ? "s" : ""}` : ""}
            </span>
          )}
          <button className="button-secondary button-small" onClick={() => { setShowSummaries(!showSummaries); }}>
            {showSummaries ? "Hide stats" : "Stats"}
          </button>
          <button className="button-secondary button-small" onClick={() => setShowStaffing(!showStaffing)}>
            {showStaffing ? "Hide staffing" : "Staffing"}
          </button>
          <button className="button-secondary button-small" onClick={() => setShowPreview(!showPreview)}>
            {showPreview ? "Hide preview" : "Preview"}
          </button>
          <button className="button-secondary button-small" onClick={onClose}>
            Done
          </button>
        </div>
      </div>

      <div className="settings-card-body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {/* Validation + template-level warnings */}
        {validation && !validation.ready && (
          <div style={{
            fontSize: "0.78rem",
            padding: "8px 12px",
            borderRadius: "var(--radius-sm)",
            background: "rgba(191, 91, 57, 0.04)",
            color: "var(--accent)",
          }}>
            {validation.invalid_assignments > 0 && (
              <div>{validation.invalid_assignments} invalid assignment{validation.invalid_assignments !== 1 ? "s" : ""}</div>
            )}
            {validation.unassigned_shifts > 0 && (
              <div>{validation.unassigned_shifts} unassigned shift{validation.unassigned_shifts !== 1 ? "s" : ""}</div>
            )}
            {validation.overlap_count != null && validation.overlap_count > 0 && (
              <div>{validation.overlap_count} time overlap{validation.overlap_count !== 1 ? "s" : ""} detected</div>
            )}
          </div>
        )}

        {warnings && warnings.length > 0 && (
          <div style={{
            fontSize: "0.78rem",
            padding: "8px 12px",
            borderRadius: "var(--radius-sm)",
            background: "rgba(191, 91, 57, 0.04)",
            color: "var(--accent)",
            display: "flex",
            flexDirection: "column",
            gap: 2,
          }}>
            {warnings.map((w, i) => (
              <div key={i}>{w.message}</div>
            ))}
          </div>
        )}

        {/* Summaries */}
        {showSummaries && <TemplateSummaries template={template} />}

        {/* Staffing plan */}
        {showStaffing && (
          <div style={{ borderTop: "1px solid rgba(0,0,0,0.06)", paddingTop: 16 }}>
            <StaffingPlanPanel
              templateId={template.id}
              onTemplateChanged={(t) => updateTemplate(t)}
            />
          </div>
        )}

        {/* Bulk selection toolbar */}
        {selectedSlots.size > 0 && (
          <div style={{
            display: "flex",
            gap: 8,
            alignItems: "center",
            padding: "8px 12px",
            borderRadius: "var(--radius-sm)",
            background: "rgba(0, 113, 227, 0.04)",
            fontSize: "0.78rem",
          }}>
            <strong>{selectedSlots.size} selected</strong>
            <button
              className="button-secondary button-small"
              disabled={bulkBusy}
              onClick={handleBulkDuplicate}
              style={{ fontSize: "0.72rem", padding: "2px 8px" }}
            >
              {bulkBusy ? "Working\u2026" : "Duplicate selected"}
            </button>
            <button
              className="button-secondary button-small"
              disabled={bulkBusy}
              onClick={handleBulkDelete}
              style={{ fontSize: "0.72rem", padding: "2px 8px", color: "var(--accent)" }}
            >
              Delete selected
            </button>
            <button
              className="button-secondary button-small"
              onClick={() => setSelectedSlots(new Set())}
              style={{ fontSize: "0.72rem", padding: "2px 8px" }}
            >
              Clear
            </button>
          </div>
        )}

        {/* Day columns */}
        {DAY_LABELS.map((day, dayIndex) => {
          const daySlots = template.slots.filter((s) => s.day_of_week === dayIndex);
          const daySummary = template.daily_summary?.find((d) => d.day_of_week === dayIndex);
          const daySlotIds = daySlots.filter((s) => s.id).map((s) => s.id!);
          const allDaySelected = daySlotIds.length > 0 && daySlotIds.every((id) => selectedSlots.has(id));

          return (
            <div key={day}>
              <div style={{
                fontSize: "0.72rem",
                fontWeight: 600,
                color: "var(--muted)",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
                marginBottom: 6,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}>
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  {daySlotIds.length > 0 && (
                    <input
                      type="checkbox"
                      checked={allDaySelected}
                      onChange={() => selectAllDay(dayIndex)}
                      style={{ accentColor: "var(--brand)" }}
                    />
                  )}
                  {day}
                </span>
                <span>
                  {daySlots.length} slot{daySlots.length !== 1 ? "s" : ""}
                  {daySummary ? ` · ${formatHours(daySummary.total_hours)}` : ""}
                </span>
              </div>

              {daySlots.map((slot) => (
                <SlotRow
                  key={slot.id ?? `${slot.day_of_week}-${slot.start_time}-${slot.role}`}
                  slot={slot}
                  selected={slot.id ? selectedSlots.has(slot.id) : false}
                  onToggleSelect={toggleSlotSelect}
                  onUpdated={handleSlotChange}
                  onDuplicated={handleSlotChange}
                  onDeleted={handleSlotChange}
                />
              ))}

              <div style={{ marginTop: 6 }}>
                <AddSlotForm
                  templateId={template.id}
                  dayOfWeek={dayIndex}
                  existingRoles={allRoles}
                  onAdded={handleSlotChange}
                />
              </div>
            </div>
          );
        })}

        {/* Preview */}
        {showPreview && (
          <div style={{ borderTop: "1px solid rgba(0,0,0,0.06)", paddingTop: 16 }}>
            <PreviewPanel templateId={template.id} />
          </div>
        )}
      </div>
    </div>
  );
}
