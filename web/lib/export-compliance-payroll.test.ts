import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  buildCompliancePayrollCsv,
  exportCompliancePayrollCsv,
} from "./export-compliance-payroll";

const report = {
  location_id: "loc_123",
  week_start_date: "2026-04-06",
  week_end_date: "2026-04-12",
  provider_profile: "generic_csv_v1" as const,
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
      premium_rate_basis: "employee_compliance_regular_rate",
      premium_rate_hourly_cents: 2250,
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
      employee_number: "EMP-42",
      external_ref: "toast-42",
      earning_code: "MEALPREM",
      earning_label: "Meal Break Premium",
      source_rule_code: "meal_break_first_window",
      source_reason_codes: ["first_meal_break_missing"],
      rule_source_references: [
        {
          rule_code: "meal_break_first_window",
          source_kind: "labor_rule_profile",
          source_code: "ca_restaurant_v1",
          source_label: "California restaurant baseline",
          jurisdiction_code: "US-CA",
          source_document_title: null,
          source_urls: ["https://example.com/ca-rule-pack"],
          source_version: "ca_rule_pack_v3",
          source_hash: "sha256:ca-pack",
          version_id: "profile_version_1",
          payload_hash: null,
          effective_at: null,
        },
      ],
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
    expect(csv).toContain('"Premium Basis"');
    expect(csv).toContain('"Premium Rate USD/Hour"');
    expect(csv).toContain('"Taylor Server"');
    expect(csv).toContain('"EMP-42"');
    expect(csv).toContain('"MEALPREM"');
    expect(csv).toContain('"2250"');
    expect(csv).toContain('"saved_compliance_premium_rate"');
    expect(csv).toContain('"22.50"');
    expect(csv).toContain('"meal_break_first_window"');
    expect(csv).toContain('"split_shift_premium"');
    expect(csv).toContain('"meal_waiver"');
    expect(csv).toContain('"Labor Rule Profile · California restaurant baseline"');
  });

  it("renders provider-specific gusto headers and employee number rows", () => {
    const csv = buildCompliancePayrollCsv(
      {
        ...report,
        provider_profile: "gusto_csv_v1",
      },
      {
        locationName: "Downtown",
        weekLabel: "Apr 6 – 12",
      },
    );

    expect(csv).toContain('"Employee Number"');
    expect(csv).toContain('"Amount USD"');
    expect(csv).toContain('"Premium Basis"');
    expect(csv).not.toContain('"Employee Identifier Type"');
    expect(csv).toContain('"EMP-42"');
    expect(csv).toContain('"22.50"');
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

  it("uses the provider-specific filename suffix", () => {
    const createObjectURL = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:test");
    const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const click = vi.fn();
    const anchor = { click, href: "", download: "" } as unknown as HTMLAnchorElement;
    vi.spyOn(document, "createElement").mockReturnValue(anchor);

    exportCompliancePayrollCsv(
      {
        ...report,
        provider_profile: "gusto_csv_v1",
      },
      {
        locationName: "Downtown",
        weekLabel: "Apr 6 – 12",
      },
    );

    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(anchor.download).toContain("gusto.csv");
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:test");
  });
});
