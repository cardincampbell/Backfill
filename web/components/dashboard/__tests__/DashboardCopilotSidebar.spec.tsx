import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/copilot", () => ({
  cancelCopilotSocketTurn: vi.fn(),
  connectCopilotSessionSocket: vi.fn(() => ({
    readyState: 3,
    addEventListener: vi.fn(),
    close: vi.fn(),
  })),
  createCopilotMessage: vi.fn(),
  createCopilotSession: vi.fn(),
  sendCopilotSocketMessage: vi.fn(),
}));

import {
  createCopilotMessage,
  createCopilotSession,
} from "@/lib/api/copilot";
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

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps session creation lazy until the user explicitly opens Copilot", async () => {
    createCopilotSessionMock.mockResolvedValue(buildSessionDetail());

    const { rerender } = render(
      <DashboardCopilotSidebar
        autoStartSignal={0}
        businessId="business-1"
        dark={false}
        locationId="location-1"
        locationName="Santa Monica"
      />,
    );

    expect(createCopilotSessionMock).not.toHaveBeenCalled();

    rerender(
      <DashboardCopilotSidebar
        autoStartSignal={1}
        businessId="business-1"
        dark={false}
        locationId="location-1"
        locationName="Santa Monica"
      />,
    );

    await waitFor(() => {
      expect(createCopilotSessionMock).toHaveBeenCalledTimes(1);
    });
  });

  it("deduplicates in-flight explicit session starts", async () => {
    const pending = deferredPromise<CopilotSessionDetail>();
    createCopilotSessionMock.mockReturnValue(pending.promise);

    const { rerender } = render(
      <DashboardCopilotSidebar
        autoStartSignal={1}
        businessId="business-1"
        dark={false}
        locationId="location-1"
        locationName="Santa Monica"
      />,
    );

    rerender(
      <DashboardCopilotSidebar
        autoStartSignal={2}
        businessId="business-1"
        dark={false}
        locationId="location-1"
        locationName="Santa Monica"
      />,
    );

    expect(createCopilotSessionMock).toHaveBeenCalledTimes(1);

    await waitFor(() => {
      expect(screen.getByText("Loading Copilot…")).toBeInTheDocument();
    });

    pending.resolve(buildSessionDetail());

    await waitFor(() => {
      expect(screen.queryByText("Loading Copilot…")).not.toBeInTheDocument();
    });
  });

  it("renders a single copilot conversation surface without nested tabs", async () => {
    const user = userEvent.setup();
    createCopilotSessionMock.mockResolvedValue(buildSessionDetail());
    createCopilotMessageMock.mockResolvedValue(buildTurn());

    render(
      <DashboardCopilotSidebar
        autoStartSignal={1}
        businessId="business-1"
        dark={false}
        locationId="location-1"
        locationName="Santa Monica"
      />,
    );

    expect(screen.queryByRole("button", { name: /Feed/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start Copilot" })).not.toBeInTheDocument();

    const input = await screen.findByPlaceholderText(/Ask Copilot/i);
    await user.type(input, "Show me open shifts");
    fireEvent.keyDown(input, { key: "Enter", code: "Enter" });

    await waitFor(() => {
      expect(createCopilotMessageMock).toHaveBeenCalledTimes(1);
    });
  });
});
