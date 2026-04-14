import { describe, expect, it } from "vitest";

import {
  shouldRefreshActivityFeedForRealtimeEvent,
  shouldRefreshSchedulerForRealtimeEvent,
  type RealtimePlatformEvent,
} from "./realtime-events";

function buildEvent(
  eventType: string,
  overrides: Partial<RealtimePlatformEvent> = {},
): RealtimePlatformEvent {
  return {
    platform_event_id: "event-1",
    business_id: "business-1",
    location_id: "location-1",
    event_type: eventType,
    entity_type: "shift",
    entity_id: "shift-1",
    trace_id: "trace-1",
    occurred_at: "2026-04-13T16:00:00Z",
    source: "platform_event",
    ...overrides,
  };
}

describe("realtime event filters", () => {
  it("refreshes the scheduler for schedule events", () => {
    expect(
      shouldRefreshSchedulerForRealtimeEvent(
        buildEvent("schedule.shift.assigned"),
      ),
    ).toBe(true);
  });

  it("refreshes the scheduler for coverage events", () => {
    expect(
      shouldRefreshSchedulerForRealtimeEvent(
        buildEvent("coverage.outreach_attempt.accepted"),
      ),
    ).toBe(true);
  });

  it("ignores non-scheduler domains for the scheduler surface", () => {
    expect(
      shouldRefreshSchedulerForRealtimeEvent(
        buildEvent("billing.fill.charged"),
      ),
    ).toBe(false);
  });

  it("ignores hidden copilot housekeeping events for the feed", () => {
    expect(
      shouldRefreshActivityFeedForRealtimeEvent(
        buildEvent("copilot.message.recorded"),
      ),
    ).toBe(false);
    expect(
      shouldRefreshActivityFeedForRealtimeEvent(
        buildEvent("copilot.intent.resolved"),
      ),
    ).toBe(false);
  });

  it("refreshes the feed for visible platform events", () => {
    expect(
      shouldRefreshActivityFeedForRealtimeEvent(
        buildEvent("coverage.campaign.created"),
      ),
    ).toBe(true);
  });
});
