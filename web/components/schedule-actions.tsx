"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { publishSchedule, copyLastWeek, recallSchedule, archiveSchedule, offerOpenShifts } from "@/lib/shifts-api";
import type { ScheduleLifecycleState } from "@/lib/types";

type ScheduleActionsProps = {
  scheduleId: number;
  locationId: number;
  lifecycleState: ScheduleLifecycleState;
  weekStartDate: string;
  basePath?: string;
};

function nextMonday(weekStart: string): string {
  const d = new Date(weekStart + "T00:00:00");
  d.setDate(d.getDate() + 7);
  return d.toISOString().slice(0, 10);
}

export function ScheduleActions({
  scheduleId,
  locationId,
  lifecycleState,
  weekStartDate,
  basePath,
}: ScheduleActionsProps) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const locationBasePath = basePath ?? `/dashboard/locations/${locationId}`;

  const disabled = busy !== null;

  async function handlePublish() {
    setBusy("publish");
    setFeedback(null);
    try {
      const result = await publishSchedule(scheduleId);
      if (result) {
        const ds = result.delivery_summary;
        let msg = `Published! ${ds.sms_sent} SMS sent`;
        if (ds.sms_failed) msg += `, ${ds.sms_failed} failed`;
        if (ds.not_enrolled) msg += `, ${ds.not_enrolled} not enrolled`;
        msg += ".";
        setFeedback({ type: "success", message: msg });
        router.refresh();
      } else {
        setFeedback({ type: "error", message: "Publish failed. Please try again." });
      }
    } finally {
      setBusy(null);
    }
  }

  async function handleCopyLastWeek() {
    setBusy("copy");
    setFeedback(null);
    const target = nextMonday(weekStartDate);
    try {
      const result = await copyLastWeek(locationId, scheduleId, target);
      if (result) {
        setFeedback({
          type: "success",
          message: `Copied ${result.copied_shift_count} shifts to week of ${result.week_start_date}. ${result.open_shift_count} open.`,
        });
        router.push(
          `${locationBasePath}?tab=schedule&week_start=${result.week_start_date}`
        );
        router.refresh();
      } else {
        setFeedback({ type: "error", message: "Copy failed. A schedule may already exist for next week." });
      }
    } finally {
      setBusy(null);
    }
  }

  async function handleRecall() {
    setBusy("recall");
    setFeedback(null);
    try {
      const result = await recallSchedule(scheduleId);
      if (result) {
        setFeedback({ type: "success", message: "Schedule recalled. It is no longer visible to employees." });
        router.refresh();
      } else {
        setFeedback({ type: "error", message: "Recall failed. Only published or amended schedules can be recalled." });
      }
    } finally {
      setBusy(null);
    }
  }

  async function handleArchive() {
    setBusy("archive");
    setFeedback(null);
    try {
      const result = await archiveSchedule(scheduleId);
      if (result) {
        setFeedback({ type: "success", message: "Schedule archived." });
        router.refresh();
      } else {
        setFeedback({ type: "error", message: "Archive failed." });
      }
    } finally {
      setBusy(null);
    }
  }

  async function handleOfferOpenShifts() {
    setBusy("offer");
    setFeedback(null);
    try {
      const result = await offerOpenShifts(scheduleId);
      if (result) {
        setFeedback({
          type: "success",
          message: result.offered_count > 0
            ? `Started offers for ${result.offered_count} open shift(s).`
            : "No open shifts to offer.",
        });
        router.refresh();
      } else {
        setFeedback({ type: "error", message: "Failed to offer open shifts." });
      }
    } finally {
      setBusy(null);
    }
  }

  const canPublish = lifecycleState === "draft" || lifecycleState === "amended";
  const canOffer = lifecycleState === "published" || lifecycleState === "amended";
  const canRecall = lifecycleState === "published" || lifecycleState === "amended";
  const canArchive = lifecycleState !== "archived";

  return (
    <div>
      <div className="cta-row">
        {canPublish && (
          <button className="button button-small" disabled={disabled} onClick={handlePublish}>
            {busy === "publish" ? "Publishing\u2026" : "Publish"}
          </button>
        )}
        {canRecall && (
          <button className="button-secondary button-small" disabled={disabled} onClick={handleRecall}>
            {busy === "recall" ? "Recalling\u2026" : "Recall"}
          </button>
        )}
        {canOffer && (
          <button className="button-secondary button-small" disabled={disabled} onClick={handleOfferOpenShifts}>
            {busy === "offer" ? "Offering\u2026" : "Offer open shifts"}
          </button>
        )}
        <button className="button-secondary button-small" disabled={disabled} onClick={handleCopyLastWeek}>
          {busy === "copy" ? "Copying\u2026" : "Copy to next week"}
        </button>
        {canArchive && (
          <button className="button-secondary button-small" disabled={disabled} onClick={handleArchive}>
            {busy === "archive" ? "Archiving\u2026" : "Archive"}
          </button>
        )}
      </div>
      {feedback && (
        <div style={{
          fontSize: "0.82rem",
          marginTop: 10,
          padding: "8px 12px",
          borderRadius: "var(--radius-sm)",
          background: feedback.type === "success" ? "rgba(39, 174, 96, 0.04)" : "rgba(191, 91, 57, 0.04)",
          color: feedback.type === "success" ? "#1a7a42" : "var(--accent)",
        }}>
          {feedback.message}
        </div>
      )}
    </div>
  );
}
