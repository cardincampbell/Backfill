import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/events", () => ({
  listPlatformEvents: vi.fn(),
}));

import { listPlatformEvents } from "@/lib/api/events";
import type { PlatformEvent } from "@/lib/types/events";
import DashboardActivityFeedPanel from "../DashboardActivityFeedPanel";

function buildEvent(overrides: Partial<PlatformEvent> = {}): PlatformEvent {
  return {
    id: "event-1",
    business_id: "business-1",
    location_id: "location-1",
    schema_version: 1,
    event_type: "coverage.campaign.created",
    compatibility_event_name: null,
    entity_type: "coverage_campaign",
    entity_id: "campaign-1",
    actor_type: "system",
    actor_user_id: null,
    actor_membership_id: null,
    trace_id: "trace-1",
    ip_address: null,
    user_agent: null,
    payload: {
      campaign_id: "campaign-1",
      shift_id: "shift-1",
    },
    event_metadata: {
      channel: "dashboard",
    },
    error_message: null,
    occurred_at: "2026-04-10T12:00:00Z",
    ...overrides,
  };
}

function deferredPromise<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, resolve, reject };
}

describe("DashboardActivityFeedPanel", () => {
  const listPlatformEventsMock = vi.mocked(listPlatformEvents);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading and empty states", async () => {
    const pending = deferredPromise<PlatformEvent[]>();
    listPlatformEventsMock.mockReturnValue(pending.promise);

    render(
      <DashboardActivityFeedPanel
        active
        businessId="business-1"
        dark={false}
        locationId="location-1"
        locationName="Santa Monica"
      />,
    );

    expect(screen.getByLabelText("Loading activity")).toBeInTheDocument();

    pending.resolve([]);

    await waitFor(() => {
      expect(screen.getByText("Nothing new yet")).toBeInTheDocument();
    });
  });

  it("shows an error state with retry support", async () => {
    const user = userEvent.setup();
    listPlatformEventsMock.mockRejectedValue(new Error("network_error"));

    render(
      <DashboardActivityFeedPanel
        active
        businessId="business-1"
        dark={false}
        locationId="location-1"
        locationName="Santa Monica"
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Feed unavailable")).toBeInTheDocument();
    });

    listPlatformEventsMock.mockResolvedValue([buildEvent()]);

    await user.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => {
      expect(screen.getByText("Campaign created")).toBeInTheDocument();
    });
  });

  it("refreshes only while active", async () => {
    vi.useFakeTimers();
    listPlatformEventsMock.mockResolvedValue([buildEvent()]);

    const { rerender } = render(
      <DashboardActivityFeedPanel
        active
        businessId="business-1"
        dark={false}
        locationId="location-1"
        locationName="Santa Monica"
      />,
    );

    await act(async () => {
      await Promise.resolve();
    });
    const initialCallCount = listPlatformEventsMock.mock.calls.length;
    expect(initialCallCount).toBeGreaterThan(0);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(listPlatformEventsMock).toHaveBeenCalledTimes(initialCallCount + 1);

    rerender(
      <DashboardActivityFeedPanel
        active={false}
        businessId="business-1"
        dark={false}
        locationId="location-1"
        locationName="Santa Monica"
      />,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(listPlatformEventsMock).toHaveBeenCalledTimes(initialCallCount + 1);

    vi.useRealTimers();
  });

  it("preserves the last good feed state when a background refresh fails", async () => {
    listPlatformEventsMock
      .mockResolvedValueOnce([buildEvent()])
      .mockResolvedValueOnce([buildEvent()])
      .mockRejectedValueOnce(new Error("network_error"));

    const user = userEvent.setup();

    render(
      <DashboardActivityFeedPanel
        active
        businessId="business-1"
        dark={false}
        locationHref="/location/business/santa-monica"
        locationId="location-1"
        locationName="Santa Monica"
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Campaign created")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Refresh feed" }));

    await waitFor(() => {
      expect(screen.getByText("Feed refresh delayed")).toBeInTheDocument();
    });
    expect(screen.getByText("Campaign created")).toBeInTheDocument();
  });

  it("only shows an open-location deep link when a real location view href is available", async () => {
    listPlatformEventsMock.mockResolvedValue([buildEvent({ payload: {} })]);

    const { rerender } = render(
      <DashboardActivityFeedPanel
        active
        businessId="business-1"
        dark={false}
        locationId="location-1"
        locationName="Santa Monica"
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Campaign created")).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("link", { name: "Open location" }),
    ).not.toBeInTheDocument();

    rerender(
      <DashboardActivityFeedPanel
        active
        businessId="business-1"
        dark={false}
        locationHref="/location/business/santa-monica"
        locationId="location-1"
        locationName="Santa Monica"
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Open location" })).toHaveAttribute(
        "href",
        "/location/business/santa-monica",
      );
    });
  });
});
