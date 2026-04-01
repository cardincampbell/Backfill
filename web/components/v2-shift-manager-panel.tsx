"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";

import {
  createV2Shift,
  deleteV2Shift,
  updateV2Shift,
  type V2WorkspaceBoard,
} from "@/lib/api/v2-workspace";

type ShiftRow = V2WorkspaceBoard["shifts"][number];
type RoleRow = V2WorkspaceBoard["roles"][number];

type V2ShiftManagerPanelProps = {
  businessId: string;
  locationId: string;
  timezone: string;
  weekStartDate: string;
  roles: RoleRow[];
  shifts: ShiftRow[];
};

type ShiftDraft = {
  role_id: string;
  starts_at: string;
  ends_at: string;
  seats_requested: number;
  requires_manager_approval: boolean;
  premium_cents: number;
  notes: string;
};

function toInputValue(value: string): string {
  const date = new Date(value);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function toIso(value: string): string {
  return new Date(value).toISOString();
}

function defaultDraft(roleId: string, weekStartDate: string): ShiftDraft {
  return {
    role_id: roleId,
    starts_at: `${weekStartDate}T09:00`,
    ends_at: `${weekStartDate}T17:00`,
    seats_requested: 1,
    requires_manager_approval: false,
    premium_cents: 0,
    notes: "",
  };
}

function buildDraftFromShift(shift: ShiftRow): ShiftDraft {
  return {
    role_id: shift.role_id,
    starts_at: toInputValue(shift.starts_at),
    ends_at: toInputValue(shift.ends_at),
    seats_requested: shift.seats_requested,
    requires_manager_approval: shift.requires_manager_approval,
    premium_cents: shift.premium_cents,
    notes: shift.notes ?? "",
  };
}

function formatShiftMeta(shift: ShiftRow): string {
  const start = new Date(shift.starts_at);
  const end = new Date(shift.ends_at);
  return `${start.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  })} · ${start.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  })} - ${end.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  })}`;
}

export function V2ShiftManagerPanel({
  businessId,
  locationId,
  timezone,
  weekStartDate,
  roles,
  shifts,
}: V2ShiftManagerPanelProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [showCreate, setShowCreate] = useState(false);
  const [editingShiftId, setEditingShiftId] = useState<string | null>(null);
  const [busyShiftId, setBusyShiftId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{
    tone: "success" | "error";
    message: string;
  } | null>(null);
  const initialRoleId = roles[0]?.role_id ?? "";
  const [createDraft, setCreateDraft] = useState<ShiftDraft>(
    defaultDraft(initialRoleId, weekStartDate),
  );
  const [editDraft, setEditDraft] = useState<ShiftDraft | null>(null);

  const sortedShifts = useMemo(
    () =>
      [...shifts].sort(
        (left, right) =>
          new Date(left.starts_at).getTime() - new Date(right.starts_at).getTime(),
      ),
    [shifts],
  );

  function resetCreateDraft() {
    setCreateDraft(defaultDraft(roles[0]?.role_id ?? "", weekStartDate));
  }

  function openEdit(shift: ShiftRow) {
    setFeedback(null);
    setEditingShiftId(shift.shift_id);
    setEditDraft(buildDraftFromShift(shift));
  }

  function closeEdit() {
    setEditingShiftId(null);
    setEditDraft(null);
  }

  function updateDraft(
    draft: ShiftDraft,
    field: keyof ShiftDraft,
    value: string | number | boolean,
  ): ShiftDraft {
    return {
      ...draft,
      [field]: value,
    };
  }

  function validateDraft(draft: ShiftDraft): string | null {
    if (!draft.role_id) return "Select a role first.";
    if (!draft.starts_at || !draft.ends_at) return "Set both start and end times.";
    if (new Date(draft.ends_at).getTime() <= new Date(draft.starts_at).getTime()) {
      return "Shift end must be after shift start.";
    }
    if (draft.seats_requested < 1) return "Shifts need at least one requested seat.";
    if (draft.premium_cents < 0) return "Premium cannot be negative.";
    return null;
  }

  function handleCreate() {
    const error = validateDraft(createDraft);
    if (error) {
      setFeedback({ tone: "error", message: error });
      return;
    }
    setFeedback(null);
    setBusyShiftId("create");
    startTransition(async () => {
      try {
        await createV2Shift(businessId, {
          location_id: locationId,
          role_id: createDraft.role_id,
          timezone,
          starts_at: toIso(createDraft.starts_at),
          ends_at: toIso(createDraft.ends_at),
          seats_requested: createDraft.seats_requested,
          requires_manager_approval: createDraft.requires_manager_approval,
          premium_cents: createDraft.premium_cents,
          notes: createDraft.notes.trim() || null,
        });
        setFeedback({ tone: "success", message: "Shift created." });
        resetCreateDraft();
        setShowCreate(false);
        router.refresh();
      } catch (error) {
        setFeedback({
          tone: "error",
          message: error instanceof Error ? error.message : "Could not create the shift.",
        });
      } finally {
        setBusyShiftId(null);
      }
    });
  }

  function handleSave(shiftId: string) {
    if (!editDraft) return;
    const error = validateDraft(editDraft);
    if (error) {
      setFeedback({ tone: "error", message: error });
      return;
    }
    setFeedback(null);
    setBusyShiftId(shiftId);
    startTransition(async () => {
      try {
        await updateV2Shift(businessId, shiftId, {
          role_id: editDraft.role_id,
          timezone,
          starts_at: toIso(editDraft.starts_at),
          ends_at: toIso(editDraft.ends_at),
          seats_requested: editDraft.seats_requested,
          requires_manager_approval: editDraft.requires_manager_approval,
          premium_cents: editDraft.premium_cents,
          notes: editDraft.notes.trim() || null,
        });
        setFeedback({ tone: "success", message: "Shift updated." });
        closeEdit();
        router.refresh();
      } catch (error) {
        setFeedback({
          tone: "error",
          message: error instanceof Error ? error.message : "Could not update the shift.",
        });
      } finally {
        setBusyShiftId(null);
      }
    });
  }

  function handleDelete(shift: ShiftRow) {
    if (busyShiftId || isPending) return;
    const confirmed = window.confirm(
      `Delete the ${shift.role_name} shift on ${formatShiftMeta(shift)}?`,
    );
    if (!confirmed) return;
    setFeedback(null);
    setBusyShiftId(shift.shift_id);
    startTransition(async () => {
      try {
        await deleteV2Shift(businessId, shift.shift_id);
        setFeedback({ tone: "success", message: "Shift deleted." });
        closeEdit();
        router.refresh();
      } catch (error) {
        setFeedback({
          tone: "error",
          message: error instanceof Error ? error.message : "Could not delete the shift.",
        });
      } finally {
        setBusyShiftId(null);
      }
    });
  }

  return (
    <section className="settings-card v2-manager-panel">
      <div className="settings-card-header">Shift manager</div>
      <div className="settings-card-body">
        <div className="v2-manager-panel-head">
          <div>
            <strong>Manage the weekly schedule</strong>
            <p>Create shifts, tune approvals, and clean up open demand without leaving the board.</p>
          </div>
          <button
            className={showCreate ? "button-secondary button-small" : "button button-small"}
            onClick={() => {
              setFeedback(null);
              if (showCreate) {
                setShowCreate(false);
                resetCreateDraft();
                return;
              }
              setShowCreate(true);
              closeEdit();
            }}
            type="button"
          >
            {showCreate ? "Close" : "New shift"}
          </button>
        </div>

        {showCreate ? (
          <div className="v2-manager-form-grid">
            <label className="field">
              <span>Role</span>
              <select
                value={createDraft.role_id}
                onChange={(event) =>
                  setCreateDraft((current) =>
                    updateDraft(current, "role_id", event.target.value),
                  )
                }
              >
                {roles.map((role) => (
                  <option key={role.role_id} value={role.role_id}>
                    {role.role_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Start</span>
              <input
                type="datetime-local"
                value={createDraft.starts_at}
                onChange={(event) =>
                  setCreateDraft((current) =>
                    updateDraft(current, "starts_at", event.target.value),
                  )
                }
              />
            </label>
            <label className="field">
              <span>End</span>
              <input
                type="datetime-local"
                value={createDraft.ends_at}
                onChange={(event) =>
                  setCreateDraft((current) =>
                    updateDraft(current, "ends_at", event.target.value),
                  )
                }
              />
            </label>
            <label className="field">
              <span>Seats</span>
              <input
                min={1}
                type="number"
                value={createDraft.seats_requested}
                onChange={(event) =>
                  setCreateDraft((current) =>
                    updateDraft(
                      current,
                      "seats_requested",
                      Number.parseInt(event.target.value || "1", 10),
                    ),
                  )
                }
              />
            </label>
            <label className="field">
              <span>Premium cents</span>
              <input
                min={0}
                type="number"
                value={createDraft.premium_cents}
                onChange={(event) =>
                  setCreateDraft((current) =>
                    updateDraft(
                      current,
                      "premium_cents",
                      Number.parseInt(event.target.value || "0", 10),
                    ),
                  )
                }
              />
            </label>
            <label className="field v2-manager-checkbox">
              <span>Manager approval</span>
              <input
                checked={createDraft.requires_manager_approval}
                type="checkbox"
                onChange={(event) =>
                  setCreateDraft((current) =>
                    updateDraft(
                      current,
                      "requires_manager_approval",
                      event.target.checked,
                    ),
                  )
                }
              />
            </label>
            <label className="field v2-manager-form-span">
              <span>Notes</span>
              <textarea
                rows={3}
                value={createDraft.notes}
                onChange={(event) =>
                  setCreateDraft((current) =>
                    updateDraft(current, "notes", event.target.value),
                  )
                }
                placeholder="Optional context for the manager or coverage engine."
              />
            </label>
            <div className="v2-manager-panel-actions">
              <span className="muted">Stored in {timezone}</span>
              <button
                className="button button-small"
                disabled={busyShiftId === "create" || isPending}
                onClick={handleCreate}
                type="button"
              >
                {busyShiftId === "create" ? "Creating…" : "Create shift"}
              </button>
            </div>
          </div>
        ) : null}

        {feedback ? (
          <div className="account-locations-feedback" data-tone={feedback.tone} role="status">
            {feedback.message}
          </div>
        ) : null}

        <div className="v2-manager-list">
          {sortedShifts.length ? (
            sortedShifts.map((shift) => {
              const isEditing = editingShiftId === shift.shift_id && editDraft;
              return (
                <article key={shift.shift_id} className="account-location-card">
                  <div className="account-location-card-main">
                    <div className="account-location-card-copy">
                      <strong>{shift.role_name}</strong>
                      <span>{formatShiftMeta(shift)}</span>
                    </div>
                    <div className="account-location-card-meta">
                      <span>
                        {shift.status} · {shift.seats_filled}/{shift.seats_requested} filled
                        {shift.pending_offer_count > 0 ? ` · ${shift.pending_offer_count} pending` : ""}
                      </span>
                    </div>
                  </div>
                  <div className="account-location-card-actions">
                    <button
                      className="button-secondary button-small"
                      disabled={busyShiftId === shift.shift_id || isPending}
                      onClick={() => (isEditing ? closeEdit() : openEdit(shift))}
                      type="button"
                    >
                      {isEditing ? "Close" : "Edit"}
                    </button>
                    <button
                      className="button-secondary button-small account-location-delete"
                      disabled={busyShiftId === shift.shift_id || isPending}
                      onClick={() => handleDelete(shift)}
                      type="button"
                    >
                      {busyShiftId === shift.shift_id ? "Working…" : "Delete"}
                    </button>
                  </div>

                  {isEditing && editDraft ? (
                    <div className="v2-manager-form-grid">
                      <label className="field">
                        <span>Role</span>
                        <select
                          value={editDraft.role_id}
                          onChange={(event) =>
                            setEditDraft((current) =>
                              current
                                ? updateDraft(current, "role_id", event.target.value)
                                : current,
                            )
                          }
                        >
                          {roles.map((role) => (
                            <option key={role.role_id} value={role.role_id}>
                              {role.role_name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="field">
                        <span>Start</span>
                        <input
                          type="datetime-local"
                          value={editDraft.starts_at}
                          onChange={(event) =>
                            setEditDraft((current) =>
                              current
                                ? updateDraft(current, "starts_at", event.target.value)
                                : current,
                            )
                          }
                        />
                      </label>
                      <label className="field">
                        <span>End</span>
                        <input
                          type="datetime-local"
                          value={editDraft.ends_at}
                          onChange={(event) =>
                            setEditDraft((current) =>
                              current
                                ? updateDraft(current, "ends_at", event.target.value)
                                : current,
                            )
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Seats</span>
                        <input
                          min={1}
                          type="number"
                          value={editDraft.seats_requested}
                          onChange={(event) =>
                            setEditDraft((current) =>
                              current
                                ? updateDraft(
                                    current,
                                    "seats_requested",
                                    Number.parseInt(event.target.value || "1", 10),
                                  )
                                : current,
                            )
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Premium cents</span>
                        <input
                          min={0}
                          type="number"
                          value={editDraft.premium_cents}
                          onChange={(event) =>
                            setEditDraft((current) =>
                              current
                                ? updateDraft(
                                    current,
                                    "premium_cents",
                                    Number.parseInt(event.target.value || "0", 10),
                                  )
                                : current,
                            )
                          }
                        />
                      </label>
                      <label className="field v2-manager-checkbox">
                        <span>Manager approval</span>
                        <input
                          checked={editDraft.requires_manager_approval}
                          type="checkbox"
                          onChange={(event) =>
                            setEditDraft((current) =>
                              current
                                ? updateDraft(
                                    current,
                                    "requires_manager_approval",
                                    event.target.checked,
                                  )
                                : current,
                            )
                          }
                        />
                      </label>
                      <label className="field v2-manager-form-span">
                        <span>Notes</span>
                        <textarea
                          rows={3}
                          value={editDraft.notes}
                          onChange={(event) =>
                            setEditDraft((current) =>
                              current
                                ? updateDraft(current, "notes", event.target.value)
                                : current,
                            )
                          }
                        />
                      </label>
                      <div className="v2-manager-panel-actions">
                        <span className="muted">
                          Coverage history or assignments can block deletion.
                        </span>
                        <button
                          className="button button-small"
                          disabled={busyShiftId === shift.shift_id || isPending}
                          onClick={() => handleSave(shift.shift_id)}
                          type="button"
                        >
                          {busyShiftId === shift.shift_id ? "Saving…" : "Save changes"}
                        </button>
                      </div>
                    </div>
                  ) : null}
                </article>
              );
            })
          ) : (
            <div className="empty">
              <div className="empty-mark">+</div>
              <div className="empty-title">No shifts yet</div>
              <div className="empty-copy">
                Create your first shift here and it will appear immediately on the board above.
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
