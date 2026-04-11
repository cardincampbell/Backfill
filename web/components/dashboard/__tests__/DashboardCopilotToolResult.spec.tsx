import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CopilotActionRun } from "@/lib/types/copilot";
import DashboardCopilotToolResult from "../DashboardCopilotToolResult";

function baseActionRun(
  resultPayload: CopilotActionRun["result_payload"],
  toolName: string,
): CopilotActionRun {
  return {
    id: "action-1",
    copilot_session_id: "session-1",
    tool_name: toolName,
    status: "executed",
    input_payload: {},
    validation_result: {
      ok: true,
      code: "ok",
      message: "ok",
    },
    result_payload: resultPayload,
    error_payload: {},
    started_at: "2026-04-10T12:00:00Z",
    finished_at: "2026-04-10T12:01:00Z",
  };
}

describe("DashboardCopilotToolResult", () => {
  it("renders open shift results with a shift deep link", () => {
    render(
      <DashboardCopilotToolResult
        actionRun={baseActionRun(
          {
            kind: "open_shifts",
            total_open_shifts: 2,
            location_count: 1,
            items: [
              {
                shift_id: "shift-1",
                location_id: "location-1",
                location_name: "Santa Monica",
                role_name: "RN",
                starts_at: "2026-04-10T17:00:00Z",
                ends_at: "2026-04-10T21:00:00Z",
                status: "open",
              },
            ],
          },
          "schedule.list_open_shifts",
        )}
        dark={false}
      />,
    );

    expect(screen.getByText("Open shifts")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open shift/i })).toHaveAttribute(
      "href",
      "/dashboard/shifts/shift-1",
    );
  });

  it("renders active campaign results with a shift deep link", () => {
    render(
      <DashboardCopilotToolResult
        actionRun={baseActionRun(
          {
            kind: "campaigns",
            total_active_campaigns: 1,
            running_count: 1,
            queued_count: 0,
            items: [
              {
                campaign_id: "campaign-1",
                shift_id: "shift-2",
                location_name: "Pasadena",
                role_name: "Caregiver",
                status: "running",
                phase_target: "phase_1",
                opened_at: "2026-04-10T16:00:00Z",
              },
            ],
          },
          "coverage.list_active_campaigns",
        )}
        dark={false}
      />,
    );

    expect(screen.getByText("Active campaigns")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open shift/i })).toHaveAttribute(
      "href",
      "/dashboard/shifts/shift-2",
    );
  });

  it("renders manager action results with a review deep link", () => {
    render(
      <DashboardCopilotToolResult
        actionRun={baseActionRun(
          {
            kind: "manager_actions",
            total_actions: 1,
            items: [
              {
                campaign_id: "campaign-2",
                shift_id: "shift-3",
                location_name: "Downtown",
                role_name: "Dispatcher",
                starts_at: "2026-04-10T20:00:00Z",
                status: "queued",
              },
            ],
          },
          "schedule.list_manager_actions",
        )}
        dark={false}
      />,
    );

    expect(screen.getByText("Manager actions")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Review shift/i })).toHaveAttribute(
      "href",
      "/dashboard/shifts/shift-3",
    );
  });
});
