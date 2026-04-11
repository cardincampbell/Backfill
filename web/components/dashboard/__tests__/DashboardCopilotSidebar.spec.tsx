import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/copilot", () => ({
  createCopilotMessage: vi.fn(),
  createCopilotSession: vi.fn(),
}));

vi.mock("@/lib/api/events", () => ({
  listPlatformEvents: vi.fn(),
}));

import {
  createCopilotMessage,
  createCopilotSession,
} from "@/lib/api/copilot";
import { listPlatformEvents } from "@/lib/api/events";
import type { CopilotSessionDetail, CopilotTurn } from "@/lib/types/copilot";
import DashboardCopilotSidebar from "../DashboardCopilotSidebar";

function buildSessionDetail(): CopilotSessionDetail {
  return {
    session: {
      id: "session-1",
      business_id: "business-1",
      location_id: "location-1",
      operator_user_id: "user-1",
      channel_last_seen: "dashboard",
      state: "active",
      context_profile: {},
      working_memory: {},
      created_at: "2026-04-10T12:00:00Z",
    },
    tools: [],
    messages: [],
    action_runs: [],
  };
}

function buildTurn(): CopilotTurn {
  return {
    session: buildSessionDetail().session,
    resolved_intent: {
      family: "schedule",
      tool_name: "schedule.list_open_shifts",
      reasoning: "Test",
      confidence: 0.9,
    },
    inbound_message: {
      id: "message-in-1",
      copilot_session_id: "session-1",
      direction: "inbound",
      normalized_channel: "dashboard",
      raw_text: "Show me open shifts",
      normalized_text: "show me open shifts",
      message_metadata: {},
      created_at: "2026-04-10T12:01:00Z",
    },
    outbound_message: {
      id: "message-out-1",
      copilot_session_id: "session-1",
      direction: "outbound",
      normalized_channel: "dashboard",
      raw_text: "Here are the open shifts.",
      normalized_text: "Here are the open shifts.",
      message_metadata: {},
      created_at: "2026-04-10T12:01:01Z",
    },
    action_run: {
      id: "action-1",
      copilot_session_id: "session-1",
      tool_name: "schedule.list_open_shifts",
      status: "executed",
      input_payload: {},
      validation_result: { ok: true, code: "ok", message: "ok" },
      result_payload: { kind: "open_shifts", total_open_shifts: 0, items: [] },
      error_payload: {},
      started_at: "2026-04-10T12:01:00Z",
      finished_at: "2026-04-10T12:01:01Z",
    },
    tools: [],
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

describe("DashboardCopilotSidebar", () => {
  const createCopilotSessionMock = vi.mocked(createCopilotSession);
  const createCopilotMessageMock = vi.mocked(createCopilotMessage);
  const listPlatformEventsMock = vi.mocked(listPlatformEvents);

  beforeEach(() => {
    vi.clearAllMocks();
    listPlatformEventsMock.mockResolvedValue([]);
  });

  it("keeps session creation lazy until the user explicitly starts Copilot", async () => {
    const user = userEvent.setup();
    createCopilotSessionMock.mockResolvedValue(buildSessionDetail());

    render(
      <DashboardCopilotSidebar
        businessId="business-1"
        dark={false}
        locationId="location-1"
        locationName="Santa Monica"
      />,
    );

    expect(createCopilotSessionMock).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Start Copilot" }));

    await waitFor(() => {
      expect(createCopilotSessionMock).toHaveBeenCalledTimes(1);
    });
  });

  it("deduplicates in-flight explicit session starts", async () => {
    const pending = deferredPromise<CopilotSessionDetail>();
    createCopilotSessionMock.mockReturnValue(pending.promise);

    render(
      <DashboardCopilotSidebar
        businessId="business-1"
        dark={false}
        locationId="location-1"
        locationName="Santa Monica"
      />,
    );

    const startButton = screen.getByRole("button", { name: "Start Copilot" });
    fireEvent.click(startButton);
    fireEvent.click(startButton);

    expect(createCopilotSessionMock).toHaveBeenCalledTimes(1);

    await waitFor(() => {
      expect(screen.getByText("Loading Copilot…")).toBeInTheDocument();
    });

    pending.resolve(buildSessionDetail());

    await waitFor(() => {
      expect(startButton).not.toBeInTheDocument();
    });
  });

  it("waits to load the feed until the feed tab is active", async () => {
    const user = userEvent.setup();
    createCopilotSessionMock.mockResolvedValue(buildSessionDetail());
    createCopilotMessageMock.mockResolvedValue(buildTurn());

    render(
      <DashboardCopilotSidebar
        businessId="business-1"
        dark={false}
        locationId="location-1"
        locationName="Santa Monica"
      />,
    );

    expect(listPlatformEventsMock).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /Feed/i }));

    await waitFor(() => {
      expect(listPlatformEventsMock).toHaveBeenCalledTimes(1);
    });
  });
});
