import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import CompliancePayrollExportSettingsEditor, {
  readCompliancePayrollExportSettingsSnapshot,
} from "./CompliancePayrollExportSettingsEditor";

const mockUpdateBusinessProfile = vi.fn();

vi.mock("@/lib/api/workspace", () => ({
  updateBusinessProfile: (...args: unknown[]) => mockUpdateBusinessProfile(...args),
}));

describe("CompliancePayrollExportSettingsEditor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUpdateBusinessProfile.mockResolvedValue({
      id: "biz_123",
      name: "backfill",
      display_name: "Backfill",
      slug: "backfill",
      timezone: "America/Los_Angeles",
      status: "active",
      settings: {
        compliance_payroll_export: {
          provider_profile: "gusto_csv_v1",
          employee_identifier_priority: ["external_ref", "employee_number"],
          allow_internal_employee_id_fallback: true,
          default_earning_code: "COMPPREM",
          default_earning_label: "Compliance Premium",
          earning_codes: {
            meal_break_first_window: { code: "MEALPREM" },
          },
        },
      },
      place_metadata: {},
      created_at: "2026-04-27T00:00:00Z",
      updated_at: "2026-04-27T00:00:00Z",
    });
  });

  it("falls back to the generic provider profile when persisted data is invalid", () => {
    expect(
      readCompliancePayrollExportSettingsSnapshot({
        provider_profile: "unknown_csv_v999",
      }).provider_profile,
    ).toBe("generic_csv_v1");
  });

  it("saves business payroll export settings through the business profile update route", async () => {
    const onApplied = vi.fn();
    render(
      <CompliancePayrollExportSettingsEditor
        businessDisplayName="Backfill"
        businessId="biz_123"
        businessTimezone="America/Los_Angeles"
        currentSettings={{
          provider_profile: "generic_csv_v1",
          employee_identifier_priority: ["employee_number", "external_ref"],
          allow_internal_employee_id_fallback: false,
          default_earning_code: "COMPLIANCE",
          default_earning_label: "Compliance Premium",
          earning_codes: {},
        }}
        dark={false}
        onApplied={onApplied}
      />,
    );

    fireEvent.change(screen.getByLabelText(/preferred identifier/i), {
      target: { value: "external_ref" },
    });
    fireEvent.change(screen.getByLabelText(/payroll export format/i), {
      target: { value: "gusto_csv_v1" },
    });
    fireEvent.click(
      screen.getByLabelText(/fall back to backfill’s internal employee id/i),
    );
    fireEvent.change(screen.getByLabelText(/default earning code/i), {
      target: { value: "COMPPREM" },
    });
    fireEvent.change(screen.getByLabelText(/first meal premium code/i), {
      target: { value: "MEALPREM" },
    });

    fireEvent.click(
      screen.getByRole("button", { name: /save export settings/i }),
    );

    await waitFor(() => expect(mockUpdateBusinessProfile).toHaveBeenCalledOnce());
    expect(mockUpdateBusinessProfile).toHaveBeenCalledWith("biz_123", {
      display_name: "Backfill",
      timezone: "America/Los_Angeles",
      compliance_payroll_export: {
        provider_profile: "gusto_csv_v1",
        employee_identifier_priority: ["external_ref", "employee_number"],
        allow_internal_employee_id_fallback: true,
        default_earning_code: "COMPPREM",
        default_earning_label: "Compliance Premium",
        earning_codes: {
          meal_break_first_window: {
            code: "MEALPREM",
            label: "First meal premium",
          },
          meal_break_second_window: null,
          paid_rest_break_quota: null,
          split_shift_premium: null,
          spread_of_hours_premium: null,
        },
      },
    });
    await waitFor(() =>
      expect(onApplied).toHaveBeenCalledWith(
        expect.objectContaining({
          provider_profile: "gusto_csv_v1",
          employee_identifier_priority: ["external_ref", "employee_number"],
          allow_internal_employee_id_fallback: true,
          default_earning_code: "COMPPREM",
        }),
      ),
    );
  });
});
