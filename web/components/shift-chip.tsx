"use client";

import { useRouter } from "next/navigation";
import { useState, useRef, useEffect } from "react";
import { amendAssignment, deleteShift, cancelOffer, closeOpenShift, reopenOpenShift } from "@/lib/shifts-api";
import type { Worker, ConfirmationStatus, AttendanceStatus, ShiftAction } from "@/lib/types";

type ShiftChipProps = {
  shiftId: number;
  workerName: string | null;
  workerId: number | null;
  startTime: string;
  endTime: string;
  workers: Worker[];
  canDelete?: boolean;
  coverageStatus?: "active" | "backfilled" | "awaiting_manager_approval" | "closed" | "none" | null;
  filledViaBackfill?: boolean;
  confirmationStatus?: ConfirmationStatus | null;
  attendanceStatus?: AttendanceStatus | null;
  availableActions?: ShiftAction[];
  selectable?: boolean;
  selected?: boolean;
  onSelect?: (shiftId: number) => void;
};

function formatTime(time: string): string {
  const [h, m] = time.split(":");
  const hour = parseInt(h, 10);
  const suffix = hour >= 12 ? "p" : "a";
  const display = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
  return m === "00" ? `${display}${suffix}` : `${display}:${m}${suffix}`;
}

const ACTION_LABELS: Record<string, string> = {
  start_coverage: "Start coverage",
  cancel_offer: "Cancel offer",
  close_shift: "Close shift",
  reopen_shift: "Reopen",
  reopen_and_offer: "Reopen & offer",
};

export function ShiftChip({
  shiftId,
  workerName,
  workerId,
  startTime,
  endTime,
  workers,
  canDelete = false,
  coverageStatus = null,
  filledViaBackfill = false,
  confirmationStatus = null,
  attendanceStatus = null,
  availableActions = [],
  selectable = false,
  selected = false,
  onSelect,
}: ShiftChipProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const isClosed = coverageStatus === "closed";
  const isOpenShift = !workerId && !isClosed;
  const isBackfilled = filledViaBackfill || coverageStatus === "backfilled";
  const isCoverageActive = coverageStatus === "active";
  const isPendingApproval = coverageStatus === "awaiting_manager_approval";

  const hasShiftActions = availableActions.length > 0;

  const chipClass = isClosed
    ? "shift-chip shift-chip-closed"
    : isPendingApproval
      ? "shift-chip shift-chip-approval"
      : isCoverageActive
        ? "shift-chip shift-chip-coverage"
        : isOpenShift
          ? "shift-chip shift-chip-open"
          : isBackfilled
            ? "shift-chip shift-chip-backfilled"
            : "shift-chip";

  // Close popover on outside click
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  async function handleAssign(selectedWorkerId: number) {
    setSaving(true);
    try {
      const result = await amendAssignment(shiftId, selectedWorkerId);
      if (result) router.refresh();
    } finally {
      setSaving(false);
      setOpen(false);
    }
  }

  async function handleDelete() {
    setSaving(true);
    try {
      const result = await deleteShift(shiftId);
      if (result) router.refresh();
    } finally {
      setSaving(false);
      setOpen(false);
    }
  }

  async function handleShiftAction(action: string) {
    setBusy(action);
    let ok = false;

    if (action === "cancel_offer") ok = await cancelOffer(shiftId);
    else if (action === "close_shift") ok = await closeOpenShift(shiftId);
    else if (action === "reopen_shift") ok = await reopenOpenShift(shiftId, false);
    else if (action === "reopen_and_offer") ok = await reopenOpenShift(shiftId, true);
    else if (action === "start_coverage") {
      // start_coverage uses the coverage/start endpoint
      try {
        const res = await fetch(`/api/shifts/${shiftId}/coverage/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        });
        ok = res.ok;
      } catch { /* noop */ }
    }

    if (ok) {
      router.refresh();
      setOpen(false);
    }
    setBusy(null);
  }

  function handleChipClick() {
    if (selectable && onSelect) {
      onSelect(shiftId);
      return;
    }
    setOpen(!open);
  }

  return (
    <div style={{ position: "relative" }} ref={popoverRef}>
      <div
        className={`${chipClass}${selected ? " shift-chip-selected" : ""}`}
        style={{ cursor: "pointer" }}
        onClick={handleChipClick}
      >
        <span>
          {isClosed ? "Closed" : (workerName ?? "Open")}
          {isBackfilled && <span className="shift-badge shift-badge-backfill" title="Filled via Backfill">BF</span>}
          {isCoverageActive && <span className="shift-badge shift-badge-coverage" title="Coverage in progress">COV</span>}
          {isPendingApproval && <span className="shift-badge shift-badge-approval" title="Awaiting manager approval">PEND</span>}
        </span>
        <span className="shift-time">
          {formatTime(startTime)}{"\u2013"}{formatTime(endTime)}
          {confirmationStatus === "confirmed" && <span className="shift-indicator shift-indicator-ok" title="Confirmed">{"\u2713"}</span>}
          {confirmationStatus === "pending" && <span className="shift-indicator shift-indicator-pending" title="Awaiting confirmation">{"\u25CB"}</span>}
          {confirmationStatus === "declined" && <span className="shift-indicator shift-indicator-alert" title="Declined">{"\u2717"}</span>}
          {confirmationStatus === "escalated" && <span className="shift-indicator shift-indicator-alert" title="Escalated">{"\u26A0"}</span>}
          {attendanceStatus === "checked_in" && <span className="shift-indicator shift-indicator-ok" title="Checked in">{"\u2713"}</span>}
          {attendanceStatus === "late" && <span className="shift-indicator shift-indicator-warn" title="Running late">{"\u29D7"}</span>}
          {attendanceStatus === "escalated" && <span className="shift-indicator shift-indicator-alert" title="No-show escalated">{"\u26A0"}</span>}
        </span>
      </div>

      {open && (
        <div className="chip-popover">
          {/* Shift lifecycle actions */}
          {hasShiftActions && (
            <>
              <div className="chip-popover-header">
                {busy ? "Working\u2026" : "Actions"}
              </div>
              <div className="chip-popover-actions">
                {availableActions.map((action) => (
                  <button
                    key={action}
                    className={action.startsWith("reopen") || action === "start_coverage" ? "button button-small" : "button-secondary button-small"}
                    disabled={busy !== null || saving}
                    onClick={() => handleShiftAction(action)}
                    style={{ width: "100%" }}
                  >
                    {busy === action ? "\u2026" : (ACTION_LABELS[action] ?? action.replace(/_/g, " "))}
                  </button>
                ))}
              </div>
            </>
          )}

          {/* Assignment section */}
          {!isClosed && (
            <>
              <div className="chip-popover-header">
                {saving ? "Saving\u2026" : "Assign to"}
              </div>
              <div className="chip-popover-list">
                {workers.length === 0 ? (
                  <div className="chip-popover-empty">No workers available</div>
                ) : (
                  workers.map((w) => (
                    <button
                      key={w.id}
                      className={`chip-popover-option${w.id === workerId ? " chip-popover-option-current" : ""}`}
                      disabled={saving || busy !== null || w.id === workerId}
                      onClick={() => handleAssign(w.id)}
                    >
                      <span className="chip-popover-name">{w.name}</span>
                      {w.roles?.length > 0 && (
                        <span className="chip-popover-roles">{w.roles.join(", ")}</span>
                      )}
                    </button>
                  ))
                )}
              </div>
            </>
          )}

          <div className="chip-popover-footer">
            {canDelete && !isClosed && (
              <button
                className="chip-popover-delete"
                disabled={saving || busy !== null}
                onClick={handleDelete}
              >
                Delete
              </button>
            )}
            <button
              className="chip-popover-cancel"
              onClick={() => setOpen(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
