"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  CircleDollarSign,
  RefreshCw,
  Sparkles,
} from "lucide-react";

import { listPlatformEvents } from "@/lib/api/events";
import type { PlatformEvent } from "@/lib/types/events";

type Feedback = {
  tone: "error";
  message: string;
} | null;

function formatRelativeTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Just now";
  }
  const deltaMs = date.getTime() - Date.now();
  const deltaMinutes = Math.round(deltaMs / 60000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (Math.abs(deltaMinutes) < 60) {
    return formatter.format(deltaMinutes, "minute");
  }
  const deltaHours = Math.round(deltaMinutes / 60);
  if (Math.abs(deltaHours) < 24) {
    return formatter.format(deltaHours, "hour");
  }
  const deltaDays = Math.round(deltaHours / 24);
  return formatter.format(deltaDays, "day");
}

function eventTone(
  eventType: string,
): "success" | "warning" | "info" {
  if (
    eventType.endsWith(".accepted") ||
    eventType.endsWith(".charged") ||
    eventType.endsWith(".created") ||
    eventType.endsWith(".executed")
  ) {
    return "success";
  }
  if (
    eventType.endsWith(".failed") ||
    eventType.endsWith(".declined") ||
    eventType.endsWith(".cancelled")
  ) {
    return "warning";
  }
  return "info";
}

function eventIcon(eventType: string) {
  if (eventType.startsWith("copilot.")) {
    return Sparkles;
  }
  if (eventType.startsWith("finance.") || eventType.startsWith("billing.")) {
    return CircleDollarSign;
  }
  if (
    eventType.endsWith(".accepted") ||
    eventType.endsWith(".charged") ||
    eventType.endsWith(".executed") ||
    eventType.endsWith(".created")
  ) {
    return CheckCircle2;
  }
  if (
    eventType.endsWith(".failed") ||
    eventType.endsWith(".declined") ||
    eventType.endsWith(".cancelled")
  ) {
    return AlertCircle;
  }
  return Activity;
}

function eventTitle(event: PlatformEvent): string {
  switch (event.event_type) {
    case "coverage.campaign.created":
      return "Campaign created";
    case "coverage.phase_1.executed":
      return "Phase 1 executed";
    case "coverage.phase_2.executed":
      return "Phase 2 executed";
    case "coverage.dispatch.executed":
      return "Dispatch executed";
    case "coverage.offer.accepted":
      return "Offer accepted";
    case "coverage.offer.declined":
      return "Offer declined";
    case "finance.cost.recorded":
      return "Cost recorded";
    case "billing.fill.charged":
      return "Fill charged";
    case "billing.fill.capped":
      return "Fill capped";
    case "billing.fill.voided":
      return "Fill voided";
    case "copilot.session.created":
      return "Copilot session started";
    case "copilot.action.executed":
      return "Copilot action executed";
    case "copilot.action.failed":
      return "Copilot action failed";
    default:
      return event.event_type.replace(/\./g, " ");
  }
}

function eventDescription(event: PlatformEvent): string {
  const payload = event.payload ?? {};
  switch (event.event_type) {
    case "coverage.campaign.created":
      return `Campaign ${String(payload.campaign_id ?? event.entity_id ?? "").slice(0, 8)} opened for shift ${String(payload.shift_id ?? "").slice(0, 8)}.`;
    case "coverage.phase_1.executed":
    case "coverage.phase_2.executed":
      return `${payload.candidate_count ?? 0} candidates reviewed and ${payload.offer_count ?? 0} offers sent.`;
    case "coverage.dispatch.executed":
      return `${payload.phase_executed ?? "Dispatch"} sent ${payload.offer_count ?? 0} offers from ${payload.candidate_count ?? 0} candidates.`;
    case "coverage.offer.accepted":
      return `Shift ${String(payload.shift_id ?? "").slice(0, 8)} now has an accepted offer.`;
    case "coverage.offer.declined":
      return `An offer was declined for shift ${String(payload.shift_id ?? "").slice(0, 8)}.`;
    case "finance.cost.recorded":
      return `A runtime cost entry was recorded for trace ${String(event.trace_id).slice(0, 8)}.`;
    case "billing.fill.charged":
      return "A successful fill charge was written to the billing ledger.";
    case "billing.fill.capped":
      return "A fill was capped under current billing rules.";
    case "billing.fill.voided":
      return "A previously recorded fill charge was voided.";
    case "copilot.session.created":
      return `Session ${String(event.entity_id ?? "").slice(0, 8)} started from ${String(event.event_metadata?.channel ?? "dashboard")}.`;
    case "copilot.action.executed":
      return `Tool ${String((payload.action_run as { tool_name?: unknown } | undefined)?.tool_name ?? "copilot")} executed successfully.`;
    case "copilot.action.failed":
      return `Tool ${String((payload.action_run as { tool_name?: unknown } | undefined)?.tool_name ?? "copilot")} failed validation or execution.`;
    default:
      if (typeof event.error_message === "string" && event.error_message) {
        return event.error_message;
      }
      return `Trace ${String(event.trace_id).slice(0, 8)} · ${event.entity_type.replace(/_/g, " ")}`;
  }
}

function visibleEvent(event: PlatformEvent): boolean {
  return !["copilot.message.recorded", "copilot.intent.resolved"].includes(
    event.event_type,
  );
}

export default function DashboardActivityFeedPanel({
  dark,
  businessId,
  locationId,
  locationName,
}: {
  dark: boolean;
  businessId?: string | null;
  locationId?: string | null;
  locationName?: string | null;
}) {
  const [events, setEvents] = useState<PlatformEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);

  const loadEvents = useCallback(async () => {
    if (!businessId) {
      setEvents([]);
      setFeedback({
        tone: "error",
        message: "Event feed needs a business context before it can load.",
      });
      return;
    }
    try {
      setLoading(true);
      setFeedback(null);
      const nextEvents = await listPlatformEvents(businessId, {
        locationId: locationId ?? null,
        limit: 20,
      });
      setEvents(nextEvents.filter(visibleEvent));
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Could not load activity.";
      setFeedback({
        tone: "error",
        message:
          message === "business_access_denied"
            ? "You need manager access to view the activity feed."
            : message,
      });
    } finally {
      setLoading(false);
    }
  }, [businessId, locationId]);

  useEffect(() => {
    void loadEvents();
  }, [loadEvents]);

  const headerDescription = useMemo(() => {
    if (locationName) {
      return `Recent platform events for ${locationName}`;
    }
    return "Recent platform events across your current business";
  }, [locationName]);

  const emptyCopy = locationName
    ? `No platform events yet for ${locationName}.`
    : "No platform events yet for this business.";

  return (
    <div className="flex h-full flex-col">
      <div
        className={`flex items-center justify-between border-b px-3 py-3 ${
          dark ? "border-white/[0.06]" : "border-[#F0F0F5]"
        }`}
      >
        <div>
          <h3
            className={`text-[13px] ${dark ? "text-white" : "text-[#0A2540]"}`}
            style={{ fontWeight: 560 }}
          >
            Activity Feed
          </h3>
          <p
            className={`mt-1 text-[11px] ${
              dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"
            }`}
            style={{ fontWeight: 420 }}
          >
            {headerDescription}
          </p>
        </div>
        <button
          className={`rounded-lg p-1.5 transition-colors ${
            dark ? "hover:bg-white/[0.06]" : "hover:bg-[#F7F8FA]"
          }`}
          disabled={loading}
          onClick={() => {
            void loadEvents();
          }}
          type="button"
        >
          <RefreshCw
            size={14}
            className={`${dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"} ${
              loading ? "animate-spin" : ""
            }`}
          />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3">
        {feedback ? (
          <div
            className={`rounded-xl border px-3 py-2 text-[11px] ${
              dark
                ? "border-[#E5484D]/30 bg-[#E5484D]/10 text-[#F8B4B4]"
                : "border-[#E5484D]/20 bg-[#FFF2F2] text-[#A33A3A]"
            }`}
            style={{ fontWeight: 500 }}
          >
            {feedback.message}
          </div>
        ) : null}

        {!feedback && loading && events.length === 0 ? (
          <div
            className={`rounded-xl px-3 py-2 text-[11px] ${
              dark ? "bg-white/[0.05] text-[#C1CED8]" : "bg-[#F0F0F5] text-[#5E6D7A]"
            }`}
            style={{ fontWeight: 420 }}
          >
            Loading activity…
          </div>
        ) : null}

        {!feedback && !loading && events.length === 0 ? (
          <div
            className={`rounded-xl px-3 py-2 text-[11px] ${
              dark ? "bg-white/[0.05] text-[#C1CED8]" : "bg-[#F0F0F5] text-[#5E6D7A]"
            }`}
            style={{ fontWeight: 420 }}
          >
            {emptyCopy}
          </div>
        ) : null}

        <div className="space-y-2">
          {events.map((event) => {
            const Icon = eventIcon(event.event_type);
            const tone = eventTone(event.event_type);
            const iconClass =
              tone === "success"
                ? "text-[#00B893]"
                : tone === "warning"
                  ? "text-[#E5484D]"
                  : "text-[#635BFF]";
            return (
              <motion.div
                key={event.id}
                animate={{ opacity: 1, y: 0 }}
                className={`rounded-xl border px-3 py-2.5 ${
                  dark
                    ? "border-white/[0.06] bg-white/[0.03]"
                    : "border-[#E5E7EB] bg-white"
                }`}
                initial={{ opacity: 0, y: 6 }}
                transition={{ duration: 0.2 }}
              >
                <div className="flex items-start gap-3">
                  <div
                    className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
                      dark ? "bg-white/[0.05]" : "bg-[#F7F8FA]"
                    }`}
                  >
                    <Icon size={14} className={iconClass} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p
                        className={`text-[12px] ${
                          dark ? "text-white" : "text-[#0A2540]"
                        }`}
                        style={{ fontWeight: 560 }}
                      >
                        {eventTitle(event)}
                      </p>
                      <span
                        className={`shrink-0 text-[10px] ${
                          dark ? "text-[#8898AA]" : "text-[#8898AA]"
                        }`}
                        style={{ fontWeight: 500 }}
                      >
                        {formatRelativeTime(event.occurred_at)}
                      </span>
                    </div>
                    <p
                      className={`mt-1 text-[11px] ${
                        dark ? "text-[#C1CED8]" : "text-[#5E6D7A]"
                      }`}
                      style={{ fontWeight: 420 }}
                    >
                      {eventDescription(event)}
                    </p>
                    <div className="mt-2 flex items-center gap-2 text-[10px]">
                      {event.location_id ? (
                        <span
                          className={`rounded-full px-2 py-0.5 ${
                            dark
                              ? "bg-white/[0.06] text-[#C1CED8]"
                              : "bg-[#F0F0F5] text-[#5E6D7A]"
                          }`}
                          style={{ fontWeight: 500 }}
                        >
                          Location scoped
                        </span>
                      ) : null}
                      {typeof event.event_metadata?.channel === "string" ? (
                        <span
                          className={`rounded-full px-2 py-0.5 ${
                            dark
                              ? "bg-white/[0.06] text-[#C1CED8]"
                              : "bg-[#F0F0F5] text-[#5E6D7A]"
                          }`}
                          style={{ fontWeight: 500 }}
                        >
                          {String(event.event_metadata.channel)}
                        </span>
                      ) : null}
                    </div>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
