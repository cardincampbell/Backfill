import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import CompliancePolicySettingsEditor from "./CompliancePolicySettingsEditor";

const mockSimulateLocationCompliancePolicy = vi.fn();
const mockApplySimulatedLocationCompliancePolicy = vi.fn();
const mockSimulateBusinessCompliancePolicy = vi.fn();
const mockApplySimulatedBusinessCompliancePolicy = vi.fn();
const mockGetLocationCompliancePolicyVersions = vi.fn();
const mockGetBusinessCompliancePolicyVersions = vi.fn();
const mockRestoreLocationCompliancePolicyVersion = vi.fn();
const mockRestoreBusinessCompliancePolicyVersion = vi.fn();
const mockReplayLocationCompliancePolicyVersion = vi.fn();

vi.mock("@/lib/api/finance", () => ({
  getLocationCompliancePolicyVersions: (...args: unknown[]) =>
    mockGetLocationCompliancePolicyVersions(...args),
  getBusinessCompliancePolicyVersions: (...args: unknown[]) =>
    mockGetBusinessCompliancePolicyVersions(...args),
  simulateLocationCompliancePolicy: (...args: unknown[]) =>
    mockSimulateLocationCompliancePolicy(...args),
  applySimulatedLocationCompliancePolicy: (...args: unknown[]) =>
    mockApplySimulatedLocationCompliancePolicy(...args),
  simulateBusinessCompliancePolicy: (...args: unknown[]) =>
    mockSimulateBusinessCompliancePolicy(...args),
  applySimulatedBusinessCompliancePolicy: (...args: unknown[]) =>
    mockApplySimulatedBusinessCompliancePolicy(...args),
  restoreLocationCompliancePolicyVersion: (...args: unknown[]) =>
    mockRestoreLocationCompliancePolicyVersion(...args),
  restoreBusinessCompliancePolicyVersion: (...args: unknown[]) =>
    mockRestoreBusinessCompliancePolicyVersion(...args),
  replayLocationCompliancePolicyVersion: (...args: unknown[]) =>
    mockReplayLocationCompliancePolicyVersion(...args),
}));

function currentWeekStartDate(weekStartDay: string) {
  const dayIndex = {
    sunday: 0,
    monday: 1,
    tuesday: 2,
    wednesday: 3,
    thursday: 4,
    friday: 5,
    saturday: 6,
  }[weekStartDay] ?? 1;
  const now = new Date();
  const localDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const offset = (localDate.getDay() - dayIndex + 7) % 7;
  localDate.setDate(localDate.getDate() - offset);
  const year = localDate.getFullYear();
  const month = String(localDate.getMonth() + 1).padStart(2, "0");
  const day = String(localDate.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function futureDateTimeLocalValue() {
  const future = new Date(Date.now() + 72 * 60 * 60 * 1000);
  const year = future.getFullYear();
  const month = String(future.getMonth() + 1).padStart(2, "0");
  const day = String(future.getDate()).padStart(2, "0");
  const hour = String(future.getHours()).padStart(2, "0");
  const minute = String(future.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hour}:${minute}`;
}

describe("CompliancePolicySettingsEditor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSimulateLocationCompliancePolicy.mockResolvedValue({
      location_id: "loc_123",
      end_week_start_date: currentWeekStartDate("monday"),
      week_count: 6,
      baseline_location_compliance_policy_hash: "location_hash_1234567890",
      baseline_location_compliance_settings: {
        require_structured_break_plans: false,
        block_unresolved_premiums: false,
      },
      proposed_location_compliance_settings: {
        minimum_rest_hours: 12,
        require_structured_break_plans: true,
        block_unresolved_premiums: false,
      },
      baseline: {
        location_id: "loc_123",
        start_week_date: "2026-03-16",
        end_week_date: "2026-04-20",
        week_count: 6,
        total_shift_count: 24,
        total_assigned_shift_count: 22,
        total_warning_assignment_count: 5,
        total_blocked_assignment_count: 2,
        total_unresolved_premium_assignment_count: 1,
        total_override_applied_count: 3,
        total_premium_cents: 3200,
        top_warning_rule_codes: [],
        top_premium_rule_codes: [],
        top_unresolved_premium_rule_codes: [],
        weeks: [],
      },
      simulated: {
        location_id: "loc_123",
        start_week_date: "2026-03-16",
        end_week_date: "2026-04-20",
        week_count: 6,
        total_shift_count: 24,
        total_assigned_shift_count: 22,
        total_warning_assignment_count: 6,
        total_blocked_assignment_count: 3,
        total_unresolved_premium_assignment_count: 2,
        total_override_applied_count: 2,
        total_premium_cents: 4100,
        top_warning_rule_codes: [],
        top_premium_rule_codes: [],
        top_unresolved_premium_rule_codes: [],
        weeks: [],
      },
      delta: {
        warning_assignment_count_delta: 1,
        blocked_assignment_count_delta: 1,
        unresolved_premium_assignment_count_delta: 1,
        override_applied_count_delta: -1,
        premium_total_cents_delta: 900,
      },
      week_deltas: [],
    });
    mockApplySimulatedLocationCompliancePolicy.mockResolvedValue({ ok: true });
    mockGetLocationCompliancePolicyVersions.mockResolvedValue([
      {
        id: "ver_loc_old",
        business_id: "biz_123",
        location_id: "loc_123",
        policy_scope: "location",
        policy_hash: "hash_loc_old_123456",
        settings: {
          minimum_rest_hours: 11,
          require_structured_break_plans: false,
          block_unresolved_premiums: false,
        },
        effective_at: "2026-04-01T12:00:00Z",
        superseded_at: "2026-04-20T12:00:00Z",
        created_by_user_id: null,
        replaces_version_id: null,
        clears_parent: false,
        is_effective: false,
        is_scheduled: false,
      },
      {
        id: "ver_loc_current",
        business_id: "biz_123",
        location_id: "loc_123",
        policy_scope: "location",
        policy_hash: "hash_loc_current_123456",
        settings: {
          require_structured_break_plans: false,
          block_unresolved_premiums: false,
        },
        effective_at: "2026-04-20T12:00:00Z",
        superseded_at: null,
        created_by_user_id: null,
        replaces_version_id: "ver_loc_old",
        clears_parent: false,
        is_effective: true,
        is_scheduled: false,
      },
    ]);
    mockRestoreLocationCompliancePolicyVersion.mockResolvedValue({
      ok: true,
      version: {
        id: "ver_loc_restored",
        business_id: "biz_123",
        location_id: "loc_123",
        policy_scope: "location",
        policy_hash: "hash_loc_restored_123456",
        settings: {
          minimum_rest_hours: 11,
          written_consent_allowed: null,
          first_meal_waiver_allowed: null,
          second_meal_waiver_allowed: null,
          require_structured_break_plans: false,
          block_unresolved_premiums: false,
          max_consecutive_work_days: null,
          required_rest_days_per_workweek: null,
          max_daily_minutes: null,
          max_weekly_minutes: null,
        },
        effective_at: "2026-04-24T12:00:00Z",
        superseded_at: null,
        created_by_user_id: null,
        replaces_version_id: "ver_loc_old",
        clears_parent: false,
        is_effective: true,
        is_scheduled: false,
      },
    });
    mockReplayLocationCompliancePolicyVersion.mockResolvedValue({
      location_id: "loc_123",
      week_start_date: currentWeekStartDate("monday"),
      week_end_date: currentWeekStartDate("monday"),
      replay_policy_version_id: "ver_loc_old",
      replay_policy_scope: "location",
      replay_policy_hash: "hash_loc_old_123456",
      replay_policy_effective_at: "2026-04-01T12:00:00Z",
      baseline: {
        location_id: "loc_123",
        week_start_date: currentWeekStartDate("monday"),
        week_end_date: currentWeekStartDate("monday"),
        shift_count: 3,
        assigned_shift_count: 3,
        employee_count: 2,
        warning_assignment_count: 1,
        blocked_assignment_count: 0,
        unresolved_premium_assignment_count: 0,
        premium_total_cents: 1200,
        override_applied_count: 0,
        warning_rule_codes: [],
        premium_rule_codes: [],
        unresolved_premium_rule_codes: [],
        artifact_type_counts: [],
        shifts: [],
        employees: [],
        override_artifacts: [],
      },
      replayed: {
        location_id: "loc_123",
        week_start_date: currentWeekStartDate("monday"),
        week_end_date: currentWeekStartDate("monday"),
        shift_count: 3,
        assigned_shift_count: 3,
        employee_count: 2,
        warning_assignment_count: 2,
        blocked_assignment_count: 1,
        unresolved_premium_assignment_count: 1,
        premium_total_cents: 1800,
        override_applied_count: 0,
        warning_rule_codes: [],
        premium_rule_codes: [],
        unresolved_premium_rule_codes: [],
        artifact_type_counts: [],
        shifts: [],
        employees: [],
        override_artifacts: [],
      },
      delta: {
        warning_assignment_count_delta: 1,
        blocked_assignment_count_delta: 1,
        unresolved_premium_assignment_count_delta: 1,
        override_applied_count_delta: 0,
        premium_total_cents_delta: 600,
      },
    });
    mockSimulateBusinessCompliancePolicy.mockResolvedValue({
      business_id: "biz_123",
      end_week_start_date: currentWeekStartDate("monday"),
      week_count: 6,
      location_count: 2,
      baseline_business_compliance_policy_hash: "business_hash_1234567890",
      baseline_business_compliance_settings: {
        require_structured_break_plans: false,
        block_unresolved_premiums: false,
      },
      proposed_business_compliance_settings: {
        max_daily_minutes: 480,
        block_unresolved_premiums: true,
        require_structured_break_plans: false,
      },
      baseline: {
        business_id: "biz_123",
        end_week_start_date: "2026-04-20",
        week_count: 6,
        location_count: 2,
        total_shift_count: 44,
        total_assigned_shift_count: 40,
        total_warning_assignment_count: 7,
        total_blocked_assignment_count: 2,
        total_unresolved_premium_assignment_count: 3,
        total_override_applied_count: 4,
        total_premium_cents: 5200,
        top_warning_rule_codes: [],
        top_premium_rule_codes: [],
        top_unresolved_premium_rule_codes: [],
        weeks: [],
        locations: [],
      },
      simulated: {
        business_id: "biz_123",
        end_week_start_date: "2026-04-20",
        week_count: 6,
        location_count: 2,
        total_shift_count: 44,
        total_assigned_shift_count: 40,
        total_warning_assignment_count: 8,
        total_blocked_assignment_count: 4,
        total_unresolved_premium_assignment_count: 1,
        total_override_applied_count: 3,
        total_premium_cents: 4700,
        top_warning_rule_codes: [],
        top_premium_rule_codes: [],
        top_unresolved_premium_rule_codes: [],
        weeks: [],
        locations: [],
      },
      delta: {
        warning_assignment_count_delta: 1,
        blocked_assignment_count_delta: 2,
        unresolved_premium_assignment_count_delta: -2,
        override_applied_count_delta: -1,
        premium_total_cents_delta: -500,
      },
      week_deltas: [],
      location_deltas: [
        {
          location_id: "loc_123",
          location_name: "Downtown",
          warning_assignment_count_delta: 1,
          blocked_assignment_count_delta: 1,
          unresolved_premium_assignment_count_delta: -1,
          override_applied_count_delta: -1,
          premium_total_cents_delta: -200,
        },
      ],
    });
    mockApplySimulatedBusinessCompliancePolicy.mockResolvedValue({ ok: true });
    mockGetBusinessCompliancePolicyVersions.mockResolvedValue([
      {
        id: "ver_biz_current",
        business_id: "biz_123",
        location_id: null,
        policy_scope: "business",
        policy_hash: "hash_biz_current_123456",
        settings: {
          require_structured_break_plans: false,
          block_unresolved_premiums: false,
        },
        effective_at: "2026-04-20T12:00:00Z",
        superseded_at: null,
        created_by_user_id: null,
        replaces_version_id: null,
        clears_parent: false,
        is_effective: true,
        is_scheduled: false,
      },
    ]);
    mockRestoreBusinessCompliancePolicyVersion.mockResolvedValue({
      ok: true,
      version: {
        id: "ver_biz_restored",
        business_id: "biz_123",
        location_id: null,
        policy_scope: "business",
        policy_hash: "hash_biz_restored_123456",
        settings: {
          require_structured_break_plans: false,
          block_unresolved_premiums: false,
        },
        effective_at: "2026-04-24T12:00:00Z",
        superseded_at: null,
        created_by_user_id: null,
        replaces_version_id: null,
        clears_parent: false,
        is_effective: true,
        is_scheduled: false,
      },
    });
  });

  it("previews and applies a location policy", async () => {
    const onApplied = vi.fn();
    const weekStartDate = currentWeekStartDate("monday");

    render(
      <CompliancePolicySettingsEditor
        businessId="biz_123"
        currentPolicy={{
          require_structured_break_plans: false,
          block_unresolved_premiums: false,
        }}
        dark={false}
        description="Location compliance preview"
        locationId="loc_123"
        onApplied={onApplied}
        scope="location"
        title="Location Compliance Policy"
        weekStartDay="monday"
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("e.g. 12"), {
      target: { value: "12" },
    });
    fireEvent.click(screen.getByLabelText(/require structured break plans/i));
    fireEvent.click(screen.getByRole("button", { name: /run preview/i }));

    await waitFor(() =>
      expect(mockSimulateLocationCompliancePolicy).toHaveBeenCalledWith(
        "biz_123",
        "loc_123",
        weekStartDate,
        {
          week_count: 6,
          compliance: {
            minimum_rest_hours: 12,
            max_daily_minutes: null,
            max_weekly_minutes: null,
            max_consecutive_work_days: null,
            required_rest_days_per_workweek: null,
            require_structured_break_plans: true,
            block_unresolved_premiums: false,
            written_consent_allowed: null,
            first_meal_waiver_allowed: null,
            second_meal_waiver_allowed: null,
            school_day_weekdays: [],
            school_dates: [],
            non_school_dates: [],
          },
        },
      ),
    );

    await screen.findByText(/preview hash/i);
    fireEvent.click(screen.getByRole("button", { name: /apply to location policy/i }));

    await waitFor(() =>
      expect(mockApplySimulatedLocationCompliancePolicy).toHaveBeenCalledWith(
        "biz_123",
        "loc_123",
        {
          expected_compliance_policy_hash: "location_hash_1234567890",
          compliance: {
            minimum_rest_hours: 12,
            require_structured_break_plans: true,
            block_unresolved_premiums: false,
          },
          effective_at: undefined,
        },
      ),
    );
    expect(onApplied).toHaveBeenCalledWith({
      minimum_rest_hours: 12,
      written_consent_allowed: null,
      first_meal_waiver_allowed: null,
      second_meal_waiver_allowed: null,
      require_structured_break_plans: true,
      block_unresolved_premiums: false,
      max_consecutive_work_days: null,
      required_rest_days_per_workweek: null,
      max_daily_minutes: null,
      max_weekly_minutes: null,
      school_day_weekdays: [],
      school_dates: [],
      non_school_dates: [],
    });
  });

  it("loads version history and restores a location policy version", async () => {
    const onApplied = vi.fn();

    render(
      <CompliancePolicySettingsEditor
        businessId="biz_123"
        currentPolicy={{
          require_structured_break_plans: false,
          block_unresolved_premiums: false,
        }}
        dark={false}
        description="Location compliance preview"
        locationId="loc_123"
        onApplied={onApplied}
        scope="location"
        title="Location Compliance Policy"
        weekStartDay="monday"
      />,
    );

    await waitFor(() =>
      expect(mockGetLocationCompliancePolicyVersions).toHaveBeenCalledWith(
        "biz_123",
        "loc_123",
        6,
      ),
    );

    const restoreButtons = await screen.findAllByRole("button", { name: /restore now/i });
    fireEvent.click(restoreButtons[0]);

    await waitFor(() =>
      expect(mockRestoreLocationCompliancePolicyVersion).toHaveBeenCalledWith(
        "biz_123",
        "loc_123",
        "ver_loc_old",
        {
          expected_current_policy_hash: "hash_loc_current_123456",
          effective_at: undefined,
        },
      ),
    );
    expect(onApplied).toHaveBeenCalledWith({
      minimum_rest_hours: 11,
      written_consent_allowed: null,
      first_meal_waiver_allowed: null,
      second_meal_waiver_allowed: null,
      require_structured_break_plans: false,
      block_unresolved_premiums: false,
      max_consecutive_work_days: null,
      required_rest_days_per_workweek: null,
      max_daily_minutes: null,
      max_weekly_minutes: null,
    });
  });

  it("schedules a future location policy activation without mutating current policy state", async () => {
    const onApplied = vi.fn();
    const futureLocalValue = futureDateTimeLocalValue();
    const expectedIso = new Date(futureLocalValue).toISOString();

    render(
      <CompliancePolicySettingsEditor
        businessId="biz_123"
        currentPolicy={{
          require_structured_break_plans: false,
          block_unresolved_premiums: false,
        }}
        dark={false}
        description="Location compliance preview"
        locationId="loc_123"
        onApplied={onApplied}
        scope="location"
        title="Location Compliance Policy"
        weekStartDay="monday"
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("e.g. 12"), {
      target: { value: "12" },
    });
    fireEvent.change(screen.getByLabelText(/activation time/i), {
      target: { value: futureLocalValue },
    });
    fireEvent.click(screen.getByRole("button", { name: /run preview/i }));
    await screen.findByText(/preview hash/i);
    fireEvent.click(screen.getByRole("button", { name: /apply to location policy/i }));

    await waitFor(() =>
      expect(mockApplySimulatedLocationCompliancePolicy).toHaveBeenCalledWith(
        "biz_123",
        "loc_123",
        expect.objectContaining({
          expected_compliance_policy_hash: "location_hash_1234567890",
          effective_at: expectedIso,
        }),
      ),
    );
    expect(onApplied).not.toHaveBeenCalled();
    await screen.findByText(/location compliance policy scheduled/i);
  });

  it("replays a historical location policy version for the selected week", async () => {
    const weekStartDate = currentWeekStartDate("monday");

    render(
      <CompliancePolicySettingsEditor
        businessId="biz_123"
        currentPolicy={{
          require_structured_break_plans: false,
          block_unresolved_premiums: false,
        }}
        dark={false}
        description="Location compliance preview"
        locationId="loc_123"
        onApplied={vi.fn()}
        scope="location"
        title="Location Compliance Policy"
        weekStartDay="monday"
      />,
    );

    const replayButtons = await screen.findAllByRole("button", { name: /replay week/i });
    fireEvent.click(replayButtons[0]);

    await waitFor(() =>
      expect(mockReplayLocationCompliancePolicyVersion).toHaveBeenCalledWith(
        "biz_123",
        "loc_123",
        weekStartDate,
        "ver_loc_old",
      ),
    );
    await screen.findByText(new RegExp(`Week Replay for ${weekStartDate}`));
    await screen.findByText("+$6.00");
  });

  it("previews and applies a business default policy", async () => {
    const onApplied = vi.fn();
    const weekStartDate = currentWeekStartDate("monday");

    render(
      <CompliancePolicySettingsEditor
        businessId="biz_123"
        currentPolicy={{
          require_structured_break_plans: false,
          block_unresolved_premiums: false,
        }}
        dark={false}
        description="Business compliance preview"
        onApplied={onApplied}
        scope="business"
        title="Business Compliance Policy"
        weekStartDay="monday"
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("e.g. 480"), {
      target: { value: "480" },
    });
    fireEvent.click(screen.getByLabelText(/block unresolved premiums/i));
    fireEvent.click(screen.getByRole("button", { name: /run preview/i }));

    await waitFor(() =>
      expect(mockSimulateBusinessCompliancePolicy).toHaveBeenCalledWith(
        "biz_123",
        weekStartDate,
        {
          week_count: 6,
          compliance: {
            minimum_rest_hours: null,
            max_daily_minutes: 480,
            max_weekly_minutes: null,
            max_consecutive_work_days: null,
            required_rest_days_per_workweek: null,
            require_structured_break_plans: false,
            block_unresolved_premiums: true,
            written_consent_allowed: null,
            first_meal_waiver_allowed: null,
            second_meal_waiver_allowed: null,
            school_day_weekdays: [],
            school_dates: [],
            non_school_dates: [],
          },
        },
      ),
    );

    await screen.findByText("Location Impact");
    fireEvent.click(screen.getByRole("button", { name: /apply as business default/i }));

    await waitFor(() =>
      expect(mockApplySimulatedBusinessCompliancePolicy).toHaveBeenCalledWith(
        "biz_123",
        {
          expected_compliance_policy_hash: "business_hash_1234567890",
          compliance: {
            max_daily_minutes: 480,
            block_unresolved_premiums: true,
            require_structured_break_plans: false,
          },
          effective_at: undefined,
        },
      ),
    );
    expect(onApplied).toHaveBeenCalledWith({
      minimum_rest_hours: null,
      written_consent_allowed: null,
      first_meal_waiver_allowed: null,
      second_meal_waiver_allowed: null,
      require_structured_break_plans: false,
      block_unresolved_premiums: true,
      max_consecutive_work_days: null,
      required_rest_days_per_workweek: null,
      max_daily_minutes: 480,
      max_weekly_minutes: null,
      school_day_weekdays: [],
      school_dates: [],
      non_school_dates: [],
    });
  });
});
