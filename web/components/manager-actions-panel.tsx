"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import type { ManagerAction, ManagerActionsResponse } from "@/lib/types";
import { approveFill, declineFill, approveAgency, waitForWorker, startCoverageForShift } from "@/lib/shifts-api";

type ManagerActionsPanelProps = {
  data: ManagerActionsResponse;
};

function formatTime(time: string): string {
  const [h, m] = time.split(":");
  const hour = parseInt(h, 10);
  const suffix = hour >= 12 ? "pm" : "am";
  const display = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
  return m === "00" ? `${display}${suffix}` : `${display}:${m}${suffix}`;
}

function formatDate(date: string): string {
  const d = new Date(date + "T00:00:00");
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function actionTypeConfig(type: string): { label: string; className: string } {
  const map: Record<string, { label: string; className: string }> = {
    approve_fill: { label: "Fill approval", className: "mgr-action-type mgr-action-type-fill" },
    approve_agency: { label: "Agency approval", className: "mgr-action-type mgr-action-type-agency" },
    review_late_arrival: { label: "Late arrival", className: "mgr-action-type mgr-action-type-attendance" },
    review_missed_check_in: { label: "Missed check-in", className: "mgr-action-type mgr-action-type-attendance" },
  };
  return map[type] ?? { label: type, className: "mgr-action-type" };
}

function ActionCard({ action }: { action: ManagerAction }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  const isFill = action.action_type === "approve_fill";
  const isAgency = action.action_type === "approve_agency";
  const isAttendance = action.action_type === "review_late_arrival" || action.action_type === "review_missed_check_in";
  const config = actionTypeConfig(action.action_type);

  async function handleAction(actionName: string) {
    setBusy(actionName);
    let ok = false;

    if (actionName === "approve" && isFill) ok = await approveFill(action.cascade_id);
    else if (actionName === "decline" && isFill) ok = await declineFill(action.cascade_id);
    else if (actionName === "approve" && isAgency) ok = await approveAgency(action.cascade_id);
    else if (actionName === "wait_for_worker") ok = await waitForWorker(action.shift_id);
    else if (actionName === "start_coverage") ok = await startCoverageForShift(action.shift_id);

    if (ok) {
      setResult(actionName);
      router.refresh();
    }
    setBusy(null);
  }

  const disabled = busy !== null || result !== null;

  function resultLabel(): string {
    if (result === "approve") return "Approved";
    if (result === "decline") return "Declined";
    if (result === "wait_for_worker") return "Waiting";
    if (result === "start_coverage") return "Coverage started";
    return "Done";
  }

  return (
    <div className={`mgr-action-card${result ? " mgr-action-card-resolved" : ""}`}>
      <div className="mgr-action-header">
        <span className={config.className}>{config.label}</span>
        <span className="mgr-action-time">{timeAgo(action.requested_at)}</span>
      </div>

      <div className="mgr-action-body">
        <div className="mgr-action-title">{action.role}</div>
        <div className="mgr-action-meta">
          {formatDate(action.date)} at {formatTime(action.start_time)}
        </div>
        {isFill && action.worker_name && (
          <div className="mgr-action-worker">
            {action.worker_name} wants to cover this shift
          </div>
        )}
        {action.action_type === "review_late_arrival" && action.worker_name && (
          <div className="mgr-action-worker">
            {action.worker_name} reported running late
            {action.late_eta_minutes ? ` (ETA ~${action.late_eta_minutes}min)` : ""}
          </div>
        )}
        {action.action_type === "review_missed_check_in" && action.worker_name && (
          <div className="mgr-action-worker">
            {action.worker_name} missed their check-in
          </div>
        )}
      </div>

      {result ? (
        <div className={`mgr-action-result ${result === "decline" || result === "start_coverage" ? "mgr-action-result-declined" : "mgr-action-result-approved"}`}>
          {resultLabel()}
        </div>
      ) : (
        <div className="mgr-action-buttons">
          {/* Fill / Agency approval actions */}
          {(isFill || isAgency) && (
            <>
              <button className="button button-small" disabled={disabled} onClick={() => handleAction("approve")}>
                {busy === "approve" ? "Approving\u2026" : "Approve"}
              </button>
              {isFill && (
                <button className="button-secondary button-small" disabled={disabled} onClick={() => handleAction("decline")}>
                  {busy === "decline" ? "Declining\u2026" : "Decline"}
                </button>
              )}
            </>
          )}

          {/* Attendance review actions */}
          {isAttendance && action.available_actions.includes("wait_for_worker") && (
            <button className="button-secondary button-small" disabled={disabled} onClick={() => handleAction("wait_for_worker")}>
              {busy === "wait_for_worker" ? "Waiting\u2026" : "Wait for worker"}
            </button>
          )}
          {isAttendance && action.available_actions.includes("start_coverage") && (
            <button className="button button-small" disabled={disabled} onClick={() => handleAction("start_coverage")}>
              {busy === "start_coverage" ? "Starting\u2026" : "Start coverage"}
            </button>
          )}

          <Link className="button-secondary button-small" href={`/dashboard/shifts/${action.shift_id}`}>
            View
          </Link>
        </div>
      )}
    </div>
  );
}

export function ManagerActionsPanel({ data }: ManagerActionsPanelProps) {
  if (data.actions.length === 0) {
    return (
      <div className="empty">
        <strong>No pending actions</strong>
        <div>When workers claim shifts, report late, or miss check-ins, manager actions will appear here.</div>
      </div>
    );
  }

  return (
    <div className="mgr-actions-panel">
      <div className="summary-bar">
        <div className="summary-bar-item">
          <strong>{data.summary.total}</strong>
          <span>Pending</span>
        </div>
        {data.summary.approve_fill > 0 && (
          <div className="summary-bar-item">
            <strong>{data.summary.approve_fill}</strong>
            <span>Fill approvals</span>
          </div>
        )}
        {data.summary.approve_agency > 0 && (
          <div className="summary-bar-item">
            <strong>{data.summary.approve_agency}</strong>
            <span>Agency approvals</span>
          </div>
        )}
        {(data.summary.attendance_reviews ?? 0) > 0 && (
          <div className="summary-bar-item">
            <strong>{data.summary.attendance_reviews}</strong>
            <span>Attendance</span>
          </div>
        )}
      </div>

      <div className="mgr-action-list">
        {data.actions.map((action) => (
          <ActionCard key={`${action.cascade_id}-${action.action_type}`} action={action} />
        ))}
      </div>
    </div>
  );
}
