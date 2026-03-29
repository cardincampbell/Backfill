"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ScheduleExceptionQueueResponse, ScheduleExceptionQueueItem } from "@/lib/types";
import { executeExceptionAction, cancelOffer, closeOpenShift } from "@/lib/shifts-api";

type ExceptionsFeedProps = {
  data: ScheduleExceptionQueueResponse;
};

function severityPillClass(item: ScheduleExceptionQueueItem): string {
  if (item.severity === "critical") return "pill pill-failed";
  if (item.severity === "warning" || item.action_required) return "pill pill-warning";
  if (item.code?.startsWith("open_shift")) return "pill pill-open";
  return "pill";
}

function exceptionLabel(item: ScheduleExceptionQueueItem): string {
  if (item.code === "coverage_fill_approval_required") return "Fill approval";
  if (item.code === "coverage_agency_approval_required") return "Agency approval";
  if (item.code === "coverage_active") return "Coverage active";
  if (item.code === "late_arrival_needs_review") return "Late";
  if (item.code === "missed_check_in_needs_review") return "Missed check-in";
  if (item.code === "missed_check_in_escalated") return "No-show";
  if (item.code?.startsWith("open_shift")) return "Open shift";
  if (item.severity === "critical") return "Critical";
  if (item.severity === "warning") return "Warning";
  return "Info";
}

function ExceptionCard({ item, locationId }: { item: ScheduleExceptionQueueItem; locationId: number }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [resolved, setResolved] = useState(false);

  const hasActions = item.action_required && item.available_actions && item.available_actions.length > 0;

  async function handleAction(actionName: string) {
    if (!item.shift_id || !item.code) return;
    setBusy(actionName);
    let ok = false;

    if (actionName === "cancel_offer") {
      ok = await cancelOffer(item.shift_id);
    } else if (actionName === "close_shift") {
      ok = await closeOpenShift(item.shift_id);
    } else {
      const result = await executeExceptionAction(locationId, {
        exception_code: item.code,
        shift_id: item.shift_id,
        action: actionName,
        cascade_id: item.cascade_id ?? undefined,
      });
      ok = result !== null;
    }

    if (ok) {
      setResolved(true);
      router.refresh();
    }
    setBusy(null);
  }

  function actionLabel(action: string): string {
    const labels: Record<string, string> = {
      approve_fill: "Approve",
      decline_fill: "Decline",
      approve_agency: "Approve agency",
      wait_for_worker: "Wait",
      start_coverage: "Start coverage",
      cancel_offer: "Cancel offer",
      close_shift: "Close shift",
    };
    return labels[action] ?? action.replace(/_/g, " ");
  }

  function actionStyle(action: string): string {
    if (action.startsWith("approve")) return "button button-small";
    if (action === "close_shift" || action === "cancel_offer") return "button-secondary button-small";
    return "button-secondary button-small";
  }

  const cardClass = [
    "exception-card",
    item.action_required && !resolved ? "exception-card-action" : "",
    resolved ? "exception-card-resolved" : "",
  ].filter(Boolean).join(" ");

  return (
    <div className={cardClass}>
      <div className="exception-card-body">
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className={severityPillClass(item)}>{exceptionLabel(item)}</span>
          <span className="exception-card-message">{item.message}</span>
        </div>
        {(item.role || item.date || item.worker_name) && (
          <div className="exception-card-meta">
            {[item.role, item.date, item.worker_name].filter(Boolean).join(" \u00B7 ")}
          </div>
        )}
      </div>

      {hasActions && !resolved && (
        <div className="exception-card-actions">
          {item.available_actions!.map((action) => (
            <button
              key={action}
              className={actionStyle(action)}
              disabled={busy !== null}
              onClick={() => handleAction(action)}
            >
              {busy === action ? "\u2026" : actionLabel(action)}
            </button>
          ))}
        </div>
      )}

      {resolved && (
        <span style={{ fontSize: "0.78rem", color: "var(--muted)" }}>Resolved</span>
      )}
    </div>
  );
}

export function ExceptionsFeed({ data }: ExceptionsFeedProps) {
  if (data.exceptions.length === 0) {
    return (
      <div className="empty">
        <strong>No exceptions</strong>
        <div>Schedule exceptions and alerts will appear here when detected.</div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="summary-bar">
        <div className="summary-bar-item">
          <strong>{data.summary.total}</strong>
          <span>Total</span>
        </div>
        {data.summary.action_required > 0 && (
          <div className="summary-bar-item">
            <strong style={{ color: "var(--accent)" }}>{data.summary.action_required}</strong>
            <span>Action needed</span>
          </div>
        )}
        {data.summary.critical > 0 && (
          <div className="summary-bar-item">
            <strong style={{ color: "var(--accent)" }}>{data.summary.critical}</strong>
            <span>Critical</span>
          </div>
        )}
      </div>

      <div className="exception-feed">
        {data.exceptions.map((item, i) => (
          <ExceptionCard key={item.id ?? i} item={item} locationId={data.location_id} />
        ))}
      </div>
    </div>
  );
}
