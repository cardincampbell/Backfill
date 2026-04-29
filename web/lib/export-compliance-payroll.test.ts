import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  buildCompliancePayrollCsv,
  exportCompliancePayrollCsv,
} from "./export-compliance-payroll";

const report = {
  location_id: "loc_123",
  week_start_date: "2026-04-06",
  week_end_date: "2026-04-12",
  row_count: 1,
  premium_payment_row_count: 1,
  ready_adjustment_row_count: 1,
  manual_review_row_count: 1,
  missing_employee_identifier_row_count: 0,
  artifact_record_row_count: 0,
  total_premium_cents: 2250,
  rows: [
    {
      shift_id: "shift_1",
      employee_id: "emp_1",
      employee_name: "Taylor Server",
      role_name: "Server",
      starts_at: "2026-04-07T16:00:00Z",
      ends_at: "2026-04-07T23:00:00Z",
      compliance_status: "warning",
      profile_code: "ca_restaurant_v1",
      premium_cents: 2250,
      premium_rule_codes: ["meal_break_first_window"],
      unresolved_premium_rule_codes: ["split_shift_premium"],
      premium_payment_required: true,
      manual_review_required: true,
      override_applied: true,
      override_artifact_id: "artifact_1",
      override_artifact_type: "meal_waiver",
      override_artifact_note: "Signed waiver on file",
      payroll_row_kind: "premium_payment",
      payroll_status: "ready",
      employee_identifier: "EMP-42",
      employee_identifier_type: "employee_number",
      earning_code: "MEALPREM",
      earning_label: "Meal Break Premium",
      source_rule_code: "meal_break_first_window",
      source_reason_codes: ["first_meal_break_missing"],
    },
  ],
};

describe("buildCompliancePayrollCsv", () => {
  it("renders header and payroll consequence rows", () => {
    const csv = buildCompliancePayrollCsv(report, {
      locationName: "Downtown",
      weekLabel: "Apr 6 – 12",
    });

    expect(csv).toContain('"Employee Identifier"');
    expect(csv).toContain('"Premium Cents"');
    expect(csv).toContain('"Taylor Server"');
    expect(csv).toContain('"EMP-42"');
    expect(csv).toContain('"MEALPREM"');
    expect(csv).toContain('"2250"');
    expect(csv).toContain('"meal_break_first_window"');
    expect(csv).toContain('"split_shift_premium"');
    expect(csv).toContain('"meal_waiver"');
  });
});

describe("exportCompliancePayrollCsv", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("creates a downloadable csv blob", () => {
    const createObjectURL = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:test");
    const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const click = vi.fn();
    const anchor = { click, href: "", download: "" } as unknown as HTMLAnchorElement;
    vi.spyOn(document, "createElement").mockReturnValue(anchor);

    exportCompliancePayrollCsv(report, {
      locationName: "Downtown",
      weekLabel: "Apr 6 – 12",
    });

    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect(anchor.download).toContain("compliance-payroll.csv");
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:test");
  });
});
