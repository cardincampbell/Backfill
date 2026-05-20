import { apiFetchApp, fetchAppJson, API_PREFIX } from "./backend-client";
import {
  getBusinessProfile,
  type CompliancePayrollProviderProfile,
  type ComplianceRuleSourceReference,
} from "./workspace";

export type ComplianceArtifactTypeCount = {
  artifact_type: string;
  count: number;
};

export type ComplianceRuleCatalogEntry = {
  catalog_kind: string;
  code: string;
  label: string;
  description?: string | null;
  jurisdiction_code?: string | null;
  source_document_title?: string | null;
  source_urls: string[];
  source_version?: string | null;
  source_hash?: string | null;
  effective_start_date?: string | null;
  effective_end_date?: string | null;
  payload_hash?: string | null;
  rule_families: string[];
  version_id?: string | null;
  version_no?: number | null;
  rule_payload: Record<string, unknown>;
};

export type LocationComplianceRuleCatalog = {
  location_id: string;
  jurisdiction_code: string;
  as_of: string;
  labor_rule_profiles: ComplianceRuleCatalogEntry[];
  work_permit_templates: ComplianceRuleCatalogEntry[];
};

export type ComplianceWeekShift = {
  shift_id: string;
  employee_id: string;
  employee_name?: string | null;
  role_id: string;
  role_name?: string | null;
  starts_at: string;
  ends_at: string;
  compliance_status: string;
  profile_code?: string | null;
  blocking_rule_codes: string[];
  warning_rule_codes: string[];
  premium_rule_codes: string[];
  premium_total_cents: number;
  unresolved_premium_rule_codes: string[];
  override_applied: boolean;
  override_artifact_id?: string | null;
  rule_source_references?: ComplianceRuleSourceReference[];
};

export type ComplianceWeekEmployee = {
  employee_id: string;
  employee_name?: string | null;
  assignment_count: number;
  shift_ids: string[];
  warning_rule_codes: string[];
  premium_rule_codes: string[];
  premium_total_cents: number;
  unresolved_premium_rule_codes: string[];
  override_applied_count: number;
};

export type ComplianceOverrideArtifactSummary = {
  artifact_id: string;
  shift_id: string;
  employee_id: string;
  employee_name?: string | null;
  rule_code: string;
  artifact_type: string;
  approved_at: string;
  expires_at?: string | null;
  note?: string | null;
};

export type LocationComplianceWeek = {
  location_id: string;
  week_start_date: string;
  week_end_date: string;
  shift_count: number;
  assigned_shift_count: number;
  employee_count: number;
  warning_assignment_count: number;
  blocked_assignment_count: number;
  unresolved_premium_assignment_count: number;
  premium_total_cents: number;
  override_applied_count: number;
  warning_rule_codes: string[];
  premium_rule_codes: string[];
  unresolved_premium_rule_codes: string[];
  artifact_type_counts: ComplianceArtifactTypeCount[];
  shifts: ComplianceWeekShift[];
  employees: ComplianceWeekEmployee[];
  override_artifacts: ComplianceOverrideArtifactSummary[];
};

export type CompliancePayrollAdjustment = {
  shift_id: string;
  employee_id: string;
  employee_name?: string | null;
  role_name?: string | null;
  starts_at: string;
  ends_at: string;
  compliance_status: string;
  profile_code?: string | null;
  premium_cents: number;
  premium_rule_codes: string[];
  unresolved_premium_rule_codes: string[];
  premium_payment_required: boolean;
  manual_review_required: boolean;
  override_applied: boolean;
  override_artifact_id?: string | null;
  override_artifact_type?: string | null;
  override_artifact_note?: string | null;
  payroll_row_kind?: string;
  payroll_status?: string;
  employee_number?: string | null;
  external_ref?: string | null;
  employee_identifier?: string | null;
  employee_identifier_type?: string | null;
  earning_code?: string | null;
  earning_label?: string | null;
  source_rule_code?: string | null;
  source_reason_codes?: string[];
  rule_source_references?: ComplianceRuleSourceReference[];
};

export type LocationCompliancePayrollExport = {
  location_id: string;
  week_start_date: string;
  week_end_date: string;
  provider_profile: CompliancePayrollProviderProfile;
  row_count: number;
  premium_payment_row_count: number;
  ready_adjustment_row_count?: number;
  manual_review_row_count: number;
  missing_employee_identifier_row_count?: number;
  artifact_record_row_count: number;
  total_premium_cents: number;
  rows: CompliancePayrollAdjustment[];
};

export type ComplianceTrendWeek = {
  week_start_date: string;
  week_end_date: string;
  shift_count: number;
  assigned_shift_count: number;
  warning_assignment_count: number;
  blocked_assignment_count: number;
  unresolved_premium_assignment_count: number;
  premium_total_cents: number;
  override_applied_count: number;
};

export type ComplianceTrendRuleCount = {
  rule_code: string;
  count: number;
};

export type CompliancePolicySettingsSnapshot = {
  minimum_rest_hours?: number | null;
  written_consent_allowed?: boolean | null;
  first_meal_waiver_allowed?: boolean | null;
  second_meal_waiver_allowed?: boolean | null;
  require_structured_break_plans: boolean;
  block_unresolved_premiums: boolean;
  max_daily_minutes?: number | null;
  max_weekly_minutes?: number | null;
  max_consecutive_work_days?: number | null;
  required_rest_days_per_workweek?: number | null;
  school_day_weekdays?: string[] | null;
  school_dates?: string[] | null;
  non_school_dates?: string[] | null;
};

export type CompliancePolicyVersion = {
  id: string;
  business_id: string;
  location_id?: string | null;
  policy_scope: "business" | "location";
  policy_hash: string;
  settings: CompliancePolicySettingsSnapshot;
  effective_at: string;
  superseded_at?: string | null;
  created_by_user_id?: string | null;
  replaces_version_id?: string | null;
  clears_parent: boolean;
  is_effective: boolean;
  is_scheduled: boolean;
};

export type LocationComplianceTrend = {
  location_id: string;
  start_week_date: string;
  end_week_date: string;
  week_count: number;
  total_shift_count: number;
  total_assigned_shift_count: number;
  total_warning_assignment_count: number;
  total_blocked_assignment_count: number;
  total_unresolved_premium_assignment_count: number;
  total_override_applied_count: number;
  total_premium_cents: number;
  top_warning_rule_codes: ComplianceTrendRuleCount[];
  top_premium_rule_codes: ComplianceTrendRuleCount[];
  top_unresolved_premium_rule_codes: ComplianceTrendRuleCount[];
  weeks: ComplianceTrendWeek[];
};

export type LocationCompliancePolicySimulation = {
  location_id: string;
  end_week_start_date: string;
  week_count: number;
  baseline_location_compliance_policy_hash: string;
  baseline_location_compliance_settings: CompliancePolicySettingsSnapshot;
  proposed_location_compliance_settings: CompliancePolicySettingsSnapshot;
  baseline: LocationComplianceTrend;
  simulated: LocationComplianceTrend;
  delta: {
    warning_assignment_count_delta: number;
    blocked_assignment_count_delta: number;
    unresolved_premium_assignment_count_delta: number;
    override_applied_count_delta: number;
    premium_total_cents_delta: number;
  };
  week_deltas: Array<{
    week_start_date: string;
    week_end_date: string;
    warning_assignment_count_delta: number;
    blocked_assignment_count_delta: number;
    unresolved_premium_assignment_count_delta: number;
    override_applied_count_delta: number;
    premium_total_cents_delta: number;
  }>;
};

export type LocationComplianceWeekReplay = {
  location_id: string;
  week_start_date: string;
  week_end_date: string;
  replay_policy_version_id: string;
  replay_policy_scope: string;
  replay_policy_hash: string;
  replay_policy_effective_at: string;
  baseline: LocationComplianceWeek;
  replayed: LocationComplianceWeek;
  delta: {
    warning_assignment_count_delta: number;
    blocked_assignment_count_delta: number;
    unresolved_premium_assignment_count_delta: number;
    override_applied_count_delta: number;
    premium_total_cents_delta: number;
  };
};

export type CompliancePolicyActivation = {
  policy_version_id: string;
  policy_scope: string;
  policy_hash: string;
  effective_at: string;
  location_id?: string | null;
  location_name?: string | null;
};

export type LocationComplianceScheduledPolicyDrift = {
  location_id: string;
  start_week_date: string;
  end_week_date: string;
  week_count: number;
  activating_policy_versions: CompliancePolicyActivation[];
  frozen_current: LocationComplianceTrend;
  scheduled: LocationComplianceTrend;
  delta: {
    warning_assignment_count_delta: number;
    blocked_assignment_count_delta: number;
    unresolved_premium_assignment_count_delta: number;
    override_applied_count_delta: number;
    premium_total_cents_delta: number;
  };
  week_deltas: Array<{
    week_start_date: string;
    week_end_date: string;
    warning_assignment_count_delta: number;
    blocked_assignment_count_delta: number;
    unresolved_premium_assignment_count_delta: number;
    override_applied_count_delta: number;
    premium_total_cents_delta: number;
  }>;
};

export type BusinessComplianceLocationTrend = {
  location_id: string;
  location_name: string;
  total_shift_count: number;
  total_assigned_shift_count: number;
  total_warning_assignment_count: number;
  total_blocked_assignment_count: number;
  total_unresolved_premium_assignment_count: number;
  total_override_applied_count: number;
  total_premium_cents: number;
};

export type BusinessComplianceTrend = {
  business_id: string;
  end_week_start_date: string;
  week_count: number;
  location_count: number;
  total_shift_count: number;
  total_assigned_shift_count: number;
  total_warning_assignment_count: number;
  total_blocked_assignment_count: number;
  total_unresolved_premium_assignment_count: number;
  total_override_applied_count: number;
  total_premium_cents: number;
  top_warning_rule_codes: ComplianceTrendRuleCount[];
  top_premium_rule_codes: ComplianceTrendRuleCount[];
  top_unresolved_premium_rule_codes: ComplianceTrendRuleCount[];
  weeks: ComplianceTrendWeek[];
  locations: BusinessComplianceLocationTrend[];
};

export type BusinessCompliancePolicySimulation = {
  business_id: string;
  end_week_start_date: string;
  week_count: number;
  location_count: number;
  baseline_business_compliance_policy_hash: string;
  baseline_business_compliance_settings: CompliancePolicySettingsSnapshot;
  proposed_business_compliance_settings: CompliancePolicySettingsSnapshot;
  baseline: BusinessComplianceTrend;
  simulated: BusinessComplianceTrend;
  delta: {
    warning_assignment_count_delta: number;
    blocked_assignment_count_delta: number;
    unresolved_premium_assignment_count_delta: number;
    override_applied_count_delta: number;
    premium_total_cents_delta: number;
  };
  week_deltas: Array<{
    week_start_date: string;
    week_end_date: string;
    warning_assignment_count_delta: number;
    blocked_assignment_count_delta: number;
    unresolved_premium_assignment_count_delta: number;
    override_applied_count_delta: number;
    premium_total_cents_delta: number;
  }>;
  location_deltas: Array<{
    location_id: string;
    location_name: string;
    warning_assignment_count_delta: number;
    blocked_assignment_count_delta: number;
    unresolved_premium_assignment_count_delta: number;
    override_applied_count_delta: number;
    premium_total_cents_delta: number;
  }>;
};

export type BusinessComplianceScheduledPolicyDrift = {
  business_id: string;
  start_week_date: string;
  end_week_date: string;
  week_count: number;
  location_count: number;
  activating_policy_versions: CompliancePolicyActivation[];
  frozen_current: BusinessComplianceTrend;
  scheduled: BusinessComplianceTrend;
  delta: {
    warning_assignment_count_delta: number;
    blocked_assignment_count_delta: number;
    unresolved_premium_assignment_count_delta: number;
    override_applied_count_delta: number;
    premium_total_cents_delta: number;
  };
  week_deltas: Array<{
    week_start_date: string;
    week_end_date: string;
    warning_assignment_count_delta: number;
    blocked_assignment_count_delta: number;
    unresolved_premium_assignment_count_delta: number;
    override_applied_count_delta: number;
    premium_total_cents_delta: number;
  }>;
  location_deltas: Array<{
    location_id: string;
    location_name: string;
    warning_assignment_count_delta: number;
    blocked_assignment_count_delta: number;
    unresolved_premium_assignment_count_delta: number;
    override_applied_count_delta: number;
    premium_total_cents_delta: number;
  }>;
};

export type ApplyLocationCompliancePolicyResult =
  | {
    ok: true;
  }
  | {
    ok: false;
    reason: "stale_preview";
    current_compliance_policy_hash: string;
    current_compliance_settings: LocationCompliancePolicySimulation["baseline_location_compliance_settings"];
  }
  | {
    ok: false;
    reason: "request_failed";
    message: string;
  };

export type ApplyBusinessCompliancePolicyResult =
  | {
    ok: true;
  }
  | {
    ok: false;
    reason: "stale_preview";
    current_compliance_policy_hash: string;
    current_compliance_settings: CompliancePolicySettingsSnapshot;
  }
  | {
    ok: false;
    reason: "request_failed";
    message: string;
  };

export type RestoreCompliancePolicyVersionResult =
  | {
    ok: true;
    version: CompliancePolicyVersion;
  }
  | {
    ok: false;
    reason: "stale_preview";
    current_compliance_policy_hash: string;
    current_compliance_settings: CompliancePolicySettingsSnapshot;
  }
  | {
    ok: false;
    reason: "request_failed";
    message: string;
  };

export async function getLocationComplianceWeek(
  businessId: string,
  locationId: string,
  weekStartDate: string,
): Promise<LocationComplianceWeek | null> {
  return fetchAppJson<LocationComplianceWeek>(
    `/businesses/${businessId}/locations/${locationId}/finance/compliance-weeks/${weekStartDate}`,
  );
}

export async function getLocationCompliancePayrollExport(
  businessId: string,
  locationId: string,
  weekStartDate: string,
): Promise<LocationCompliancePayrollExport | null> {
  return fetchAppJson<LocationCompliancePayrollExport>(
    `/businesses/${businessId}/locations/${locationId}/finance/compliance-weeks/${weekStartDate}/payroll-export`,
  );
}

export async function getLocationComplianceRuleCatalog(
  businessId: string,
  locationId: string,
): Promise<LocationComplianceRuleCatalog | null> {
  return fetchAppJson<LocationComplianceRuleCatalog>(
    `/businesses/${businessId}/locations/${locationId}/finance/compliance-rule-catalog`,
  );
}

export async function getLocationComplianceTrend(
  businessId: string,
  locationId: string,
  endWeekStartDate: string,
  weekCount = 6,
): Promise<LocationComplianceTrend | null> {
  return fetchAppJson<LocationComplianceTrend>(
    `/businesses/${businessId}/locations/${locationId}/finance/compliance-trends/${endWeekStartDate}?week_count=${weekCount}`,
  );
}

export async function getLocationComplianceScheduledPolicyDrift(
  businessId: string,
  locationId: string,
  startWeekDate: string,
  weekCount = 6,
): Promise<LocationComplianceScheduledPolicyDrift | null> {
  return fetchAppJson<LocationComplianceScheduledPolicyDrift>(
    `/businesses/${businessId}/locations/${locationId}/finance/scheduled-policy-drift/${startWeekDate}?week_count=${weekCount}`,
  );
}

export async function simulateLocationCompliancePolicy(
  businessId: string,
  locationId: string,
  endWeekStartDate: string,
  payload: {
    week_count?: number;
    compliance: Record<string, unknown>;
  },
): Promise<LocationCompliancePolicySimulation | null> {
  try {
    const response = await apiFetchApp(
      `/businesses/${businessId}/locations/${locationId}/finance/compliance-trends/${endWeekStartDate}/simulate-policy`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    );
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as LocationCompliancePolicySimulation;
  } catch (error) {
    if (typeof window !== "undefined") {
      console.error("Backfill compliance policy simulation failed", error);
    }
    return null;
  }
}

export async function getLocationCompliancePolicyVersions(
  businessId: string,
  locationId: string,
  limit = 10,
): Promise<CompliancePolicyVersion[]> {
  try {
    const response = await apiFetchApp(
      `/businesses/${businessId}/locations/${locationId}/settings/compliance-policy-versions?limit=${limit}`,
    );
    if (!response.ok) {
      return [];
    }
    return (await response.json()) as CompliancePolicyVersion[];
  } catch (error) {
    if (typeof window !== "undefined") {
      console.error("Backfill location compliance policy versions failed", error);
    }
    return [];
  }
}

export async function replayLocationCompliancePolicyVersion(
  businessId: string,
  locationId: string,
  weekStartDate: string,
  policyVersionId: string,
): Promise<LocationComplianceWeekReplay | null> {
  try {
    const response = await apiFetchApp(
      `/businesses/${businessId}/locations/${locationId}/finance/compliance-weeks/${weekStartDate}/replay-policy/${policyVersionId}`,
    );
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as LocationComplianceWeekReplay;
  } catch (error) {
    if (typeof window !== "undefined") {
      console.error("Backfill location compliance replay failed", error);
    }
    return null;
  }
}

export async function simulateBusinessCompliancePolicy(
  businessId: string,
  endWeekStartDate: string,
  payload: {
    week_count?: number;
    compliance: Record<string, unknown>;
  },
): Promise<BusinessCompliancePolicySimulation | null> {
  try {
    const response = await apiFetchApp(
      `/businesses/${businessId}/finance/compliance-trends/${endWeekStartDate}/simulate-policy`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    );
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as BusinessCompliancePolicySimulation;
  } catch (error) {
    if (typeof window !== "undefined") {
      console.error("Backfill business compliance policy simulation failed", error);
    }
    return null;
  }
}

export async function getBusinessComplianceScheduledPolicyDrift(
  businessId: string,
  startWeekDate: string,
  weekCount = 6,
): Promise<BusinessComplianceScheduledPolicyDrift | null> {
  return fetchAppJson<BusinessComplianceScheduledPolicyDrift>(
    `/businesses/${businessId}/finance/scheduled-policy-drift/${startWeekDate}?week_count=${weekCount}`,
  );
}

export async function getBusinessCompliancePolicyVersions(
  businessId: string,
  limit = 10,
): Promise<CompliancePolicyVersion[]> {
  try {
    const response = await apiFetchApp(
      `/businesses/${businessId}/compliance-policy-versions?limit=${limit}`,
    );
    if (!response.ok) {
      return [];
    }
    return (await response.json()) as CompliancePolicyVersion[];
  } catch (error) {
    if (typeof window !== "undefined") {
      console.error("Backfill business compliance policy versions failed", error);
    }
    return [];
  }
}

export async function applySimulatedLocationCompliancePolicy(
  businessId: string,
  locationId: string,
  payload: {
    expected_compliance_policy_hash: string;
    compliance: Record<string, unknown>;
    effective_at?: string;
  },
): Promise<ApplyLocationCompliancePolicyResult> {
  try {
    const response = await apiFetchApp(
      `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/settings`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          expected_compliance_policy_hash: payload.expected_compliance_policy_hash,
          compliance: payload.compliance,
          compliance_effective_at: payload.effective_at ?? null,
        }),
      },
    );
    if (response.ok) {
      return { ok: true };
    }
    const errorPayload = await response.json().catch(() => null) as {
      detail?: {
        code?: string;
        current_compliance_policy_hash?: string;
        current_compliance_settings?: ApplyLocationCompliancePolicyResult extends infer _T ? Record<string, unknown> : never;
      } | string;
    } | null;
    if (
      response.status === 409
      && errorPayload
      && typeof errorPayload.detail === "object"
      && errorPayload.detail?.code === "location_compliance_policy_preview_stale"
    ) {
      return {
        ok: false,
        reason: "stale_preview",
        current_compliance_policy_hash: String(errorPayload.detail.current_compliance_policy_hash || ""),
        current_compliance_settings: (
          errorPayload.detail.current_compliance_settings as LocationCompliancePolicySimulation["baseline_location_compliance_settings"]
        ) ?? {
          require_structured_break_plans: false,
          block_unresolved_premiums: false,
        },
      };
    }
    return {
      ok: false,
      reason: "request_failed",
      message: typeof errorPayload?.detail === "string"
        ? errorPayload.detail
        : `Request failed with status ${response.status}`,
    };
  } catch (error) {
    return {
      ok: false,
      reason: "request_failed",
      message: error instanceof Error ? error.message : "Request failed",
    };
  }
}

export async function restoreLocationCompliancePolicyVersion(
  businessId: string,
  locationId: string,
  versionId: string,
  payload: {
    expected_current_policy_hash?: string;
    effective_at?: string;
  },
): Promise<RestoreCompliancePolicyVersionResult> {
  try {
    const response = await apiFetchApp(
      `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/settings/compliance-policy-versions/${versionId}/restore`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          expected_current_policy_hash: payload.expected_current_policy_hash,
          effective_at: payload.effective_at ?? null,
        }),
      },
    );
    if (response.ok) {
      return {
        ok: true,
        version: (await response.json()) as CompliancePolicyVersion,
      };
    }
    const errorPayload = await response.json().catch(() => null) as {
      detail?: {
        code?: string;
        current_compliance_policy_hash?: string;
        current_compliance_settings?: Record<string, unknown>;
      } | string;
    } | null;
    if (
      response.status === 409
      && errorPayload
      && typeof errorPayload.detail === "object"
      && errorPayload.detail?.code === "location_compliance_policy_preview_stale"
    ) {
      return {
        ok: false,
        reason: "stale_preview",
        current_compliance_policy_hash: String(errorPayload.detail.current_compliance_policy_hash || ""),
        current_compliance_settings: (
          errorPayload.detail.current_compliance_settings as CompliancePolicySettingsSnapshot
        ) ?? {
          require_structured_break_plans: false,
          block_unresolved_premiums: false,
        },
      };
    }
    return {
      ok: false,
      reason: "request_failed",
      message: typeof errorPayload?.detail === "string"
        ? errorPayload.detail
        : `Request failed with status ${response.status}`,
    };
  } catch (error) {
    return {
      ok: false,
      reason: "request_failed",
      message: error instanceof Error ? error.message : "Request failed",
    };
  }
}

export async function applySimulatedBusinessCompliancePolicy(
  businessId: string,
  payload: {
    expected_compliance_policy_hash: string;
    compliance: Record<string, unknown>;
    effective_at?: string;
  },
): Promise<ApplyBusinessCompliancePolicyResult> {
  try {
    const businessProfile = await getBusinessProfile(businessId);
    const response = await apiFetchApp(
      `${API_PREFIX}/businesses/${businessId}`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          display_name: businessProfile.display_name,
          vertical: businessProfile.vertical,
          primary_email: businessProfile.primary_email,
          timezone: businessProfile.timezone,
          expected_compliance_policy_hash: payload.expected_compliance_policy_hash,
          compliance_effective_at: payload.effective_at ?? null,
          compliance: payload.compliance,
        }),
      },
    );
    if (response.ok) {
      return { ok: true };
    }
    const errorPayload = await response.json().catch(() => null) as {
      detail?: {
        code?: string;
        current_compliance_policy_hash?: string;
        current_compliance_settings?: Record<string, unknown>;
      } | string;
    } | null;
    if (
      response.status === 409
      && errorPayload
      && typeof errorPayload.detail === "object"
      && errorPayload.detail?.code === "business_compliance_policy_preview_stale"
    ) {
      return {
        ok: false,
        reason: "stale_preview",
        current_compliance_policy_hash: String(errorPayload.detail.current_compliance_policy_hash || ""),
        current_compliance_settings: (
          errorPayload.detail.current_compliance_settings as CompliancePolicySettingsSnapshot
        ) ?? {
          require_structured_break_plans: false,
          block_unresolved_premiums: false,
        },
      };
    }
    return {
      ok: false,
      reason: "request_failed",
      message: typeof errorPayload?.detail === "string"
        ? errorPayload.detail
        : `Request failed with status ${response.status}`,
    };
  } catch (error) {
    return {
      ok: false,
      reason: "request_failed",
      message: error instanceof Error ? error.message : "Request failed",
    };
  }
}

export async function restoreBusinessCompliancePolicyVersion(
  businessId: string,
  versionId: string,
  payload: {
    expected_current_policy_hash?: string;
    effective_at?: string;
  },
): Promise<RestoreCompliancePolicyVersionResult> {
  try {
    const response = await apiFetchApp(
      `${API_PREFIX}/businesses/${businessId}/compliance-policy-versions/${versionId}/restore`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          expected_current_policy_hash: payload.expected_current_policy_hash,
          effective_at: payload.effective_at ?? null,
        }),
      },
    );
    if (response.ok) {
      return {
        ok: true,
        version: (await response.json()) as CompliancePolicyVersion,
      };
    }
    const errorPayload = await response.json().catch(() => null) as {
      detail?: {
        code?: string;
        current_compliance_policy_hash?: string;
        current_compliance_settings?: Record<string, unknown>;
      } | string;
    } | null;
    if (
      response.status === 409
      && errorPayload
      && typeof errorPayload.detail === "object"
      && errorPayload.detail?.code === "business_compliance_policy_preview_stale"
    ) {
      return {
        ok: false,
        reason: "stale_preview",
        current_compliance_policy_hash: String(errorPayload.detail.current_compliance_policy_hash || ""),
        current_compliance_settings: (
          errorPayload.detail.current_compliance_settings as CompliancePolicySettingsSnapshot
        ) ?? {
          require_structured_break_plans: false,
          block_unresolved_premiums: false,
        },
      };
    }
    return {
      ok: false,
      reason: "request_failed",
      message: typeof errorPayload?.detail === "string"
        ? errorPayload.detail
        : `Request failed with status ${response.status}`,
    };
  } catch (error) {
    return {
      ok: false,
      reason: "request_failed",
      message: error instanceof Error ? error.message : "Request failed",
    };
  }
}
