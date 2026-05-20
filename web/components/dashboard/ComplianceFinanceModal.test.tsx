import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ComplianceFinanceModal } from "./ComplianceFinanceModal";

const mockGetLocationComplianceWeek = vi.fn();
const mockGetLocationComplianceTrend = vi.fn();
const mockGetLocationComplianceRuleCatalog = vi.fn();
const mockGetLocationComplianceScheduledPolicyDrift = vi.fn();
const mockGetBusinessComplianceScheduledPolicyDrift = vi.fn();
const mockGetLocationCompliancePayrollExport = vi.fn();
const mockSimulateLocationCompliancePolicy = vi.fn();
const mockApplySimulatedLocationCompliancePolicy = vi.fn();
const mockSimulateBusinessCompliancePolicy = vi.fn();
const mockApplySimulatedBusinessCompliancePolicy = vi.fn();
const mockExportCompliancePayrollCsv = vi.fn();

vi.mock("@/lib/api/finance", () => ({
  getLocationComplianceWeek: (...args: unknown[]) => mockGetLocationComplianceWeek(...args),
  getLocationComplianceTrend: (...args: unknown[]) => mockGetLocationComplianceTrend(...args),
  getLocationComplianceRuleCatalog: (...args: unknown[]) =>
    mockGetLocationComplianceRuleCatalog(...args),
  getLocationComplianceScheduledPolicyDrift: (...args: unknown[]) =>
    mockGetLocationComplianceScheduledPolicyDrift(...args),
  getBusinessComplianceScheduledPolicyDrift: (...args: unknown[]) =>
    mockGetBusinessComplianceScheduledPolicyDrift(...args),
  getLocationCompliancePayrollExport: (...args: unknown[]) =>
    mockGetLocationCompliancePayrollExport(...args),
  simulateLocationCompliancePolicy: (...args: unknown[]) =>
    mockSimulateLocationCompliancePolicy(...args),
  applySimulatedLocationCompliancePolicy: (...args: unknown[]) =>
    mockApplySimulatedLocationCompliancePolicy(...args),
  simulateBusinessCompliancePolicy: (...args: unknown[]) =>
    mockSimulateBusinessCompliancePolicy(...args),
  applySimulatedBusinessCompliancePolicy: (...args: unknown[]) =>
    mockApplySimulatedBusinessCompliancePolicy(...args),
}));

vi.mock("@/lib/export-compliance-payroll", () => ({
  exportCompliancePayrollCsv: (...args: unknown[]) => mockExportCompliancePayrollCsv(...args),
  describeCompliancePayrollProviderProfile: (profile: string | undefined) => {
    switch (profile) {
      case "gusto_csv_v1":
        return "Gusto-aligned CSV";
      case "quickbooks_csv_v1":
        return "QuickBooks-aligned CSV";
      case "adp_csv_v1":
        return "ADP-aligned CSV";
      default:
        return "Backfill generic CSV";
    }
  },
}));

const defaultReport = {
  location_id: "loc_123",
  week_start_date: "2026-04-06",
  week_end_date: "2026-04-12",
  shift_count: 3,
  assigned_shift_count: 2,
  employee_count: 1,
  warning_assignment_count: 1,
  blocked_assignment_count: 1,
  unresolved_premium_assignment_count: 1,
  premium_total_cents: 1845,
  override_applied_count: 1,
  warning_rule_codes: ["meal_break_missing"],
  premium_rule_codes: ["meal_break_premium"],
  unresolved_premium_rule_codes: ["split_shift_premium"],
  artifact_type_counts: [{ artifact_type: "meal_waiver", count: 1 }],
  shifts: [
    {
      shift_id: "shift_1",
      employee_id: "emp_1",
      employee_name: "Taylor Server",
      role_id: "role_1",
      role_name: "Server",
      starts_at: "2026-04-07T16:00:00Z",
      ends_at: "2026-04-07T23:00:00Z",
      compliance_status: "warning",
      profile_code: "ca_restaurant_v1",
      blocking_rule_codes: [],
      warning_rule_codes: ["meal_break_missing"],
      premium_rule_codes: ["meal_break_premium"],
      premium_total_cents: 1845,
      unresolved_premium_rule_codes: ["split_shift_premium"],
      override_applied: true,
      override_artifact_id: "artifact_1",
    },
  ],
  employees: [
    {
      employee_id: "emp_1",
      employee_name: "Taylor Server",
      assignment_count: 2,
      shift_ids: ["shift_1"],
      warning_rule_codes: ["meal_break_missing"],
      premium_rule_codes: ["meal_break_premium"],
      premium_total_cents: 1845,
      unresolved_premium_rule_codes: ["split_shift_premium"],
      override_applied_count: 1,
    },
  ],
  override_artifacts: [
    {
      artifact_id: "artifact_1",
      shift_id: "shift_1",
      employee_id: "emp_1",
      employee_name: "Taylor Server",
      rule_code: "meal_break_missing",
      artifact_type: "meal_waiver",
      approved_at: "2026-04-07T15:00:00Z",
      expires_at: null,
      note: "Signed waiver on file",
    },
  ],
};

const defaultProps = {
  businessId: "biz_123",
  locationId: "loc_123",
  locationName: "Downtown",
  weekLabel: "Apr 6 – 12",
  weekStartDateKey: "2026-04-06",
  onClose: vi.fn(),
  onOpenExport: vi.fn(),
};

const defaultTrendReport = {
  location_id: "loc_123",
  start_week_date: "2026-03-02",
  end_week_date: "2026-04-06",
  week_count: 6,
  total_shift_count: 28,
  total_assigned_shift_count: 24,
  total_warning_assignment_count: 6,
  total_blocked_assignment_count: 3,
  total_unresolved_premium_assignment_count: 2,
  total_override_applied_count: 4,
  total_premium_cents: 6450,
  top_warning_rule_codes: [{ rule_code: "meal_break_missing", count: 4 }],
  top_premium_rule_codes: [{ rule_code: "meal_break_premium", count: 3 }],
  top_unresolved_premium_rule_codes: [{ rule_code: "split_shift_premium", count: 2 }],
  weeks: [
    {
      week_start_date: "2026-03-02",
      week_end_date: "2026-03-08",
      shift_count: 4,
      assigned_shift_count: 3,
      warning_assignment_count: 1,
      blocked_assignment_count: 0,
      unresolved_premium_assignment_count: 0,
      premium_total_cents: 400,
      override_applied_count: 0,
    },
    {
      week_start_date: "2026-04-06",
      week_end_date: "2026-04-12",
      shift_count: 5,
      assigned_shift_count: 4,
      warning_assignment_count: 2,
      blocked_assignment_count: 1,
      unresolved_premium_assignment_count: 1,
      premium_total_cents: 1845,
      override_applied_count: 1,
    },
  ],
};

const defaultRuleCatalog = {
  location_id: "loc_123",
  jurisdiction_code: "US-CA",
  as_of: "2026-04-28T18:00:00Z",
  labor_rule_profiles: [
    {
      catalog_kind: "labor_rule_profile",
      code: "ca_restaurant_v1",
      label: "California restaurant baseline",
      description: null,
      jurisdiction_code: "US-CA",
      source_document_title: null,
      source_urls: ["https://example.com/ca-rule-pack"],
      source_version: "ca_rule_pack_v3",
      source_hash: "sha256:ca-pack",
      effective_start_date: null,
      effective_end_date: null,
      payload_hash: "sha256:labor-payload",
      rule_families: ["meal_break", "rest_break", "rest_window"],
      version_id: "profile_version_1",
      version_no: 3,
      rule_payload: { code: "ca_restaurant_v1" },
    },
  ],
  work_permit_templates: [
    {
      catalog_kind: "work_permit_template",
      code: "ca_16_17_school_required_v1",
      label: "California ages 16-17 while school required",
      description: "4 hours on schooldays, 8 hours on non-schooldays.",
      jurisdiction_code: "US-CA",
      source_document_title: "California Department of Industrial Relations minors summary charts",
      source_urls: ["https://www.dir.ca.gov/dlse/MinorsSummaryCharts.pdf"],
      source_version: "dir_minors_summary_charts_v1",
      source_hash: null,
      effective_start_date: null,
      effective_end_date: null,
      payload_hash: "sha256:permit-payload",
      rule_families: ["minor_labor", "work_permit"],
      version_id: null,
      version_no: null,
      rule_payload: { template_code: "ca_16_17_school_required_v1" },
    },
  ],
};

const defaultLocationDrift = {
  location_id: "loc_123",
  start_week_date: "2026-04-06",
  end_week_date: "2026-05-11",
  week_count: 6,
  activating_policy_versions: [
    {
      policy_version_id: "policy_loc_1",
      policy_scope: "location",
      policy_hash: "location_future_hash",
      effective_at: "2026-04-15T16:00:00Z",
      location_id: "loc_123",
      location_name: "Downtown",
    },
  ],
  frozen_current: defaultTrendReport,
  scheduled: {
    ...defaultTrendReport,
    total_warning_assignment_count: 8,
    total_blocked_assignment_count: 5,
    total_unresolved_premium_assignment_count: 3,
    total_override_applied_count: 5,
    total_premium_cents: 8150,
  },
  delta: {
    warning_assignment_count_delta: 2,
    blocked_assignment_count_delta: 2,
    unresolved_premium_assignment_count_delta: 1,
    override_applied_count_delta: 1,
    premium_total_cents_delta: 1700,
  },
  week_deltas: [
    {
      week_start_date: "2026-04-06",
      week_end_date: "2026-04-12",
      warning_assignment_count_delta: 1,
      blocked_assignment_count_delta: 1,
      unresolved_premium_assignment_count_delta: 1,
      override_applied_count_delta: 0,
      premium_total_cents_delta: 700,
    },
  ],
};

const defaultBusinessDrift = {
  business_id: "biz_123",
  start_week_date: "2026-04-06",
  end_week_date: "2026-05-11",
  week_count: 6,
  location_count: 2,
  activating_policy_versions: [
    {
      policy_version_id: "policy_business_1",
      policy_scope: "business",
      policy_hash: "business_future_hash",
      effective_at: "2026-04-14T16:00:00Z",
      location_id: null,
      location_name: null,
    },
  ],
  frozen_current: {
    business_id: "biz_123",
    end_week_start_date: "2026-04-06",
    week_count: 6,
    location_count: 2,
    total_shift_count: 28,
    total_assigned_shift_count: 24,
    total_warning_assignment_count: 6,
    total_blocked_assignment_count: 3,
    total_unresolved_premium_assignment_count: 2,
    total_override_applied_count: 4,
    total_premium_cents: 6450,
    top_warning_rule_codes: [],
    top_premium_rule_codes: [],
    top_unresolved_premium_rule_codes: [],
    weeks: defaultTrendReport.weeks,
    locations: [],
  },
  scheduled: {
    business_id: "biz_123",
    end_week_start_date: "2026-04-06",
    week_count: 6,
    location_count: 2,
    total_shift_count: 28,
    total_assigned_shift_count: 24,
    total_warning_assignment_count: 8,
    total_blocked_assignment_count: 5,
    total_unresolved_premium_assignment_count: 3,
    total_override_applied_count: 3,
    total_premium_cents: 8150,
    top_warning_rule_codes: [],
    top_premium_rule_codes: [],
    top_unresolved_premium_rule_codes: [],
    weeks: defaultTrendReport.weeks,
    locations: [],
  },
  delta: {
    warning_assignment_count_delta: 2,
    blocked_assignment_count_delta: 2,
    unresolved_premium_assignment_count_delta: 1,
    override_applied_count_delta: -1,
    premium_total_cents_delta: 1700,
  },
  week_deltas: [
    {
      week_start_date: "2026-04-06",
      week_end_date: "2026-04-12",
      warning_assignment_count_delta: 1,
      blocked_assignment_count_delta: 1,
      unresolved_premium_assignment_count_delta: 1,
      override_applied_count_delta: 0,
      premium_total_cents_delta: 700,
    },
  ],
  location_deltas: [
    {
      location_id: "loc_123",
      location_name: "Downtown",
      warning_assignment_count_delta: 2,
      blocked_assignment_count_delta: 2,
      unresolved_premium_assignment_count_delta: 1,
      override_applied_count_delta: -1,
      premium_total_cents_delta: 1700,
    },
  ],
};

function renderModal(overrides = {}) {
  return render(<ComplianceFinanceModal {...defaultProps} {...overrides} />);
}

describe("ComplianceFinanceModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetLocationComplianceWeek.mockResolvedValue(defaultReport);
    mockGetLocationComplianceTrend.mockResolvedValue(defaultTrendReport);
    mockGetLocationComplianceRuleCatalog.mockResolvedValue(defaultRuleCatalog);
    mockGetLocationComplianceScheduledPolicyDrift.mockResolvedValue(defaultLocationDrift);
    mockGetBusinessComplianceScheduledPolicyDrift.mockResolvedValue(defaultBusinessDrift);
    mockGetLocationCompliancePayrollExport.mockResolvedValue({
      location_id: "loc_123",
      week_start_date: "2026-04-06",
      week_end_date: "2026-04-12",
      provider_profile: "gusto_csv_v1",
      row_count: 1,
      premium_payment_row_count: 1,
      manual_review_row_count: 1,
      artifact_record_row_count: 0,
      total_premium_cents: 1845,
      rows: [],
    });
    mockSimulateLocationCompliancePolicy.mockResolvedValue({
      location_id: "loc_123",
      end_week_start_date: "2026-04-06",
      week_count: 6,
      baseline_location_compliance_policy_hash: "preview_hash_1234567890",
      baseline_location_compliance_settings: {
        require_structured_break_plans: false,
        block_unresolved_premiums: false,
      },
      proposed_location_compliance_settings: {
        minimum_rest_hours: 12,
        require_structured_break_plans: true,
        block_unresolved_premiums: false,
      },
      baseline: defaultTrendReport,
      simulated: defaultTrendReport,
      delta: {
        warning_assignment_count_delta: 2,
        blocked_assignment_count_delta: 1,
        unresolved_premium_assignment_count_delta: 1,
        override_applied_count_delta: -1,
        premium_total_cents_delta: 700,
      },
      week_deltas: [
        {
          week_start_date: "2026-04-06",
          week_end_date: "2026-04-12",
          warning_assignment_count_delta: 1,
          blocked_assignment_count_delta: 1,
          unresolved_premium_assignment_count_delta: 1,
          override_applied_count_delta: 0,
          premium_total_cents_delta: 700,
        },
      ],
    });
    mockApplySimulatedLocationCompliancePolicy.mockResolvedValue({ ok: true });
    mockSimulateBusinessCompliancePolicy.mockResolvedValue({
      business_id: "biz_123",
      end_week_start_date: "2026-04-06",
      week_count: 6,
      location_count: 2,
      baseline_business_compliance_policy_hash: "business_preview_hash_1234567890",
      baseline_business_compliance_settings: {
        minimum_rest_hours: 10,
        require_structured_break_plans: false,
        block_unresolved_premiums: false,
      },
      proposed_business_compliance_settings: {
        minimum_rest_hours: 12,
        require_structured_break_plans: true,
        block_unresolved_premiums: false,
      },
      baseline: {
        business_id: "biz_123",
        end_week_start_date: "2026-04-06",
        week_count: 6,
        location_count: 2,
        total_shift_count: 28,
        total_assigned_shift_count: 24,
        total_warning_assignment_count: 6,
        total_blocked_assignment_count: 3,
        total_unresolved_premium_assignment_count: 2,
        total_override_applied_count: 4,
        total_premium_cents: 6450,
        top_warning_rule_codes: [],
        top_premium_rule_codes: [],
        top_unresolved_premium_rule_codes: [],
        weeks: defaultTrendReport.weeks,
        locations: [],
      },
      simulated: {
        business_id: "biz_123",
        end_week_start_date: "2026-04-06",
        week_count: 6,
        location_count: 2,
        total_shift_count: 28,
        total_assigned_shift_count: 24,
        total_warning_assignment_count: 8,
        total_blocked_assignment_count: 5,
        total_unresolved_premium_assignment_count: 3,
        total_override_applied_count: 3,
        total_premium_cents: 8150,
        top_warning_rule_codes: [],
        top_premium_rule_codes: [],
        top_unresolved_premium_rule_codes: [],
        weeks: defaultTrendReport.weeks,
        locations: [],
      },
      delta: {
        warning_assignment_count_delta: 2,
        blocked_assignment_count_delta: 2,
        unresolved_premium_assignment_count_delta: 1,
        override_applied_count_delta: -1,
        premium_total_cents_delta: 1700,
      },
      week_deltas: [
        {
          week_start_date: "2026-04-06",
          week_end_date: "2026-04-12",
          warning_assignment_count_delta: 1,
          blocked_assignment_count_delta: 1,
          unresolved_premium_assignment_count_delta: 1,
          override_applied_count_delta: 0,
          premium_total_cents_delta: 700,
        },
      ],
      location_deltas: [
        {
          location_id: "loc_123",
          location_name: "Downtown",
          warning_assignment_count_delta: 2,
          blocked_assignment_count_delta: 2,
          unresolved_premium_assignment_count_delta: 1,
          override_applied_count_delta: -1,
          premium_total_cents_delta: 1700,
        },
      ],
    });
    mockApplySimulatedBusinessCompliancePolicy.mockResolvedValue({ ok: true });
  });

  it("loads and renders the weekly compliance finance summary", async () => {
    renderModal();

    expect(screen.getByText("Compliance Finance Review")).toBeInTheDocument();
    await screen.findByText("Employee Exposure");
    expect(screen.getAllByText("$18.45").length).toBeGreaterThan(0);
    expect(screen.getByText("Taylor Server")).toBeInTheDocument();
    expect(screen.getByText(/Signed waiver on file/)).toBeInTheDocument();
    expect(screen.getByText("Trend Window")).toBeInTheDocument();
    expect(screen.getByText("Rule Sources")).toBeInTheDocument();
    expect(screen.getByText("California restaurant baseline")).toBeInTheDocument();
    expect(screen.getByText("Permit Template Catalog")).toBeInTheDocument();
    expect(screen.getByText("Scheduled Policy Drift")).toBeInTheDocument();
    expect(screen.getByText("Activating Policies")).toBeInTheDocument();
    expect(screen.getByText("Policy Simulation")).toBeInTheDocument();
    expect(screen.getByText("Warning Hotspots")).toBeInTheDocument();
    expect(mockGetLocationComplianceWeek).toHaveBeenCalledWith(
      "biz_123",
      "loc_123",
      "2026-04-06",
    );
    expect(mockGetLocationComplianceTrend).toHaveBeenCalledWith(
      "biz_123",
      "loc_123",
      "2026-04-06",
      6,
    );
    expect(mockGetLocationComplianceRuleCatalog).toHaveBeenCalledWith(
      "biz_123",
      "loc_123",
    );
    expect(mockGetLocationComplianceScheduledPolicyDrift).toHaveBeenCalledWith(
      "biz_123",
      "loc_123",
      "2026-04-06",
      6,
    );
    expect(mockGetBusinessComplianceScheduledPolicyDrift).toHaveBeenCalledWith(
      "biz_123",
      "2026-04-06",
      6,
    );
  });

  it("shows an unavailable state when the report is missing", async () => {
    mockGetLocationComplianceWeek.mockResolvedValue(null);
    renderModal();

    await screen.findByText("Compliance finance report unavailable");
  });

  it("opens export from the footer action", async () => {
    const onOpenExport = vi.fn();
    renderModal({ onOpenExport });

    await screen.findByText("Open Export");
    fireEvent.click(screen.getByRole("button", { name: /open export/i }));
    expect(onOpenExport).toHaveBeenCalledOnce();
  });

  it("exports payroll csv from the footer action", async () => {
    renderModal();

    await screen.findByText("Export Gusto CSV");
    fireEvent.click(screen.getByRole("button", { name: /export gusto csv/i }));

    await waitFor(() =>
      expect(mockGetLocationCompliancePayrollExport).toHaveBeenCalledWith(
        "biz_123",
        "loc_123",
        "2026-04-06",
      ),
    );
    await waitFor(() => expect(mockExportCompliancePayrollCsv).toHaveBeenCalledOnce());
  });

  it("runs a compliance policy simulation from the modal", async () => {
    renderModal();

    await screen.findByText("Run Preview");
    fireEvent.change(screen.getByPlaceholderText("e.g. 12"), { target: { value: "12" } });
    fireEvent.change(screen.getByLabelText(/rest days \/ week/i), { target: { value: "1" } });
    fireEvent.click(screen.getByLabelText(/require structured break plans/i));
    fireEvent.click(screen.getByRole("button", { name: /run preview/i }));

    await waitFor(() =>
      expect(mockSimulateLocationCompliancePolicy).toHaveBeenCalledWith(
        "biz_123",
        "loc_123",
        "2026-04-06",
        {
          week_count: 6,
          compliance: {
            minimum_rest_hours: 12,
            required_rest_days_per_workweek: 1,
            require_structured_break_plans: true,
          },
        },
      ),
    );
    await waitFor(() => expect(screen.getAllByText("+$7.00").length).toBeGreaterThan(0));
    expect(screen.getByText("Simulated Policy")).toBeInTheDocument();
  });

  it("applies a reviewed simulation to location settings and reloads reports", async () => {
    renderModal();

    await screen.findByText("Run Preview");
    fireEvent.change(screen.getByPlaceholderText("e.g. 12"), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: /run preview/i }));
    await screen.findByText("Apply To Location Settings");

    fireEvent.click(screen.getByRole("button", { name: /apply to location settings/i }));

    await waitFor(() =>
      expect(mockApplySimulatedLocationCompliancePolicy).toHaveBeenCalledWith(
        "biz_123",
        "loc_123",
        {
          expected_compliance_policy_hash: "preview_hash_1234567890",
          compliance: {
            minimum_rest_hours: 12,
            require_structured_break_plans: true,
            block_unresolved_premiums: false,
          },
        },
      ),
    );
    await screen.findByText(/Applied to location settings/i);
    expect(mockGetLocationComplianceWeek).toHaveBeenCalledTimes(2);
    expect(mockGetLocationComplianceTrend).toHaveBeenCalledTimes(2);
  });

  it("shows a stale preview warning when the persisted policy changed", async () => {
    mockApplySimulatedLocationCompliancePolicy.mockResolvedValue({
      ok: false,
      reason: "stale_preview",
      current_compliance_policy_hash: "new_hash_9876543210",
      current_compliance_settings: {
        minimum_rest_hours: 10,
        written_consent_allowed: false,
        require_structured_break_plans: false,
        block_unresolved_premiums: true,
      },
    });
    renderModal();

    await screen.findByText("Run Preview");
    fireEvent.change(screen.getByPlaceholderText("e.g. 12"), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: /run preview/i }));
    await screen.findByText("Apply To Location Settings");
    fireEvent.click(screen.getByRole("button", { name: /apply to location settings/i }));

    await screen.findByText(/Preview is stale/i);
    expect(screen.getByText(/current persisted policy hash/i)).toBeInTheDocument();
    expect(screen.getByText(/written consent allowed: false/i)).toBeInTheDocument();
  });

  it("runs and applies a business default simulation from the modal", async () => {
    renderModal();

    await screen.findByText("Run Preview");
    fireEvent.click(screen.getByRole("button", { name: /business default/i }));
    fireEvent.change(screen.getByPlaceholderText("e.g. 12"), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: /run preview/i }));

    await waitFor(() =>
      expect(mockSimulateBusinessCompliancePolicy).toHaveBeenCalledWith(
        "biz_123",
        "2026-04-06",
        {
          week_count: 6,
          compliance: {
            minimum_rest_hours: 12,
          },
        },
      ),
    );
    expect((await screen.findAllByText("Location Impact")).length).toBeGreaterThan(0);
    expect(screen.getByText("Apply As Business Default")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /apply as business default/i }));

    await waitFor(() =>
      expect(mockApplySimulatedBusinessCompliancePolicy).toHaveBeenCalledWith(
        "biz_123",
        {
          expected_compliance_policy_hash: "business_preview_hash_1234567890",
          compliance: {
            minimum_rest_hours: 12,
            require_structured_break_plans: true,
            block_unresolved_premiums: false,
          },
        },
      ),
    );
    await screen.findByText(/Applied as the business default/i);
  });
});
