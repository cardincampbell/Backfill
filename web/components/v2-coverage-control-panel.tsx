"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  createV2CoverageCase,
  executeV2CoverageCase,
  getV2CoveragePlan,
  type V2WorkspaceBoard,
} from "@/lib/api/v2-workspace";

type ShiftRow = V2WorkspaceBoard["shifts"][number];

type V2CoverageControlPanelProps = {
  businessId: string;
  shifts: ShiftRow[];
  title: string;
  description: string;
  emptyTitle: string;
  emptyBody: string;
};

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

function canRunCoverage(shift: ShiftRow): boolean {
  if (shift.seats_filled >= shift.seats_requested) return false;
  return shift.status !== "covered";
}

function shouldReuseCoverageCase(shift: ShiftRow): boolean {
  if (!shift.coverage_case_id) return false;
  return !["filled", "cancelled", "exhausted"].includes(
    shift.coverage_case_status ?? "",
  );
}

export function V2CoverageControlPanel({
  businessId,
  shifts,
  title,
  description,
  emptyTitle,
  emptyBody,
}: V2CoverageControlPanelProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [busyShiftId, setBusyShiftId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{
    tone: "success" | "error";
    message: string;
  } | null>(null);

  function handleRunCoverage(shift: ShiftRow) {
    if (!canRunCoverage(shift) || busyShiftId || isPending) return;
    setBusyShiftId(shift.shift_id);
    setFeedback(null);

    startTransition(async () => {
      try {
        const coverageCaseId =
          shouldReuseCoverageCase(shift)
            ? shift.coverage_case_id!
            : (
                await createV2CoverageCase(businessId, {
                shift_id: shift.shift_id,
                phase_target: "phase_1",
                priority: 100,
                requires_manager_approval: shift.requires_manager_approval,
                triggered_by: "manager_workspace",
                case_metadata: { source: "workspace_v2" },
              })
              ).id;

        const decision = await getV2CoveragePlan(businessId, coverageCaseId);
        const result = await executeV2CoverageCase(businessId, coverageCaseId, {
          phase_override: decision.recommended_phase ?? undefined,
          channel: "sms",
          run_metadata: { source: "workspace_v2" },
        });

        setFeedback({
          tone: "success",
          message:
            result.phase_executed
              ? `${shift.role_name}: ${result.phase_executed.replace("_", " ")} dispatched to ${result.candidate_count} candidates with ${result.offers.length} offers.`
              : `${shift.role_name}: no dispatch was needed.`,
        });
        router.refresh();
      } catch (error) {
        setFeedback({
          tone: "error",
          message:
            error instanceof Error
              ? error.message
              : "Could not run coverage for this shift.",
        });
      } finally {
        setBusyShiftId(null);
      }
    });
  }

  return (
    <section className="settings-card v2-manager-panel">
      <div className="settings-card-header">{title}</div>
      <div className="settings-card-body">
        <div className="v2-manager-panel-head">
          <div>
            <strong>{title}</strong>
            <p>{description}</p>
          </div>
        </div>

        {feedback ? (
          <div className="account-locations-feedback" data-tone={feedback.tone} role="status">
            {feedback.message}
          </div>
        ) : null}

        <div className="v2-manager-list">
          {shifts.length ? (
            shifts.map((shift) => {
              const buttonLabel = shift.coverage_case_id ? "Advance coverage" : "Start coverage";
              const disabled = !canRunCoverage(shift) || busyShiftId === shift.shift_id || isPending;
              return (
                <article key={shift.shift_id} className="account-location-card">
                  <div className="account-location-card-main">
                    <div className="account-location-card-copy">
                      <strong>{shift.role_name}</strong>
                      <span>{formatShiftMeta(shift)}</span>
                    </div>
                    <div className="account-location-card-meta">
                      <span>
                        {shift.status}
                        {shift.coverage_case_status ? ` · ${shift.coverage_case_status}` : ""}
                        {shift.pending_offer_count > 0 ? ` · ${shift.pending_offer_count} pending` : ""}
                        {shift.delivered_offer_count > 0 ? ` · ${shift.delivered_offer_count} delivered` : ""}
                      </span>
                    </div>
                  </div>
                  <div className="account-location-card-actions">
                    <button
                      className="button button-small"
                      disabled={disabled}
                      onClick={() => handleRunCoverage(shift)}
                      type="button"
                    >
                      {busyShiftId === shift.shift_id ? "Running…" : buttonLabel}
                    </button>
                  </div>
                </article>
              );
            })
          ) : (
            <div className="empty">
              <div className="empty-mark">+</div>
              <div className="empty-title">{emptyTitle}</div>
              <div className="empty-copy">{emptyBody}</div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
