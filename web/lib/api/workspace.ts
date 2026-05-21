import type { PlaceSuggestion } from "@/lib/api/places";
import { buildLocationPayloadFromPlace } from "@/lib/place-location";
import { apiFetchApp, fetchAppJson, API_PREFIX } from "./backend-client";

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export type WorkspaceUser = {
  id: string;
  full_name?: string | null;
  email?: string | null;
  primary_phone_e164?: string | null;
};

export type WorkspaceLocation = {
  membership_id: string;
  membership_role: string;
  membership_scope: string;
  business_id: string;
  business_name: string;
  business_display_name: string;
  business_slug: string;
  location_id: string;
  location_name: string;
  location_display_name: string;
  location_slug: string;
  address_line_1?: string | null;
  locality?: string | null;
  region?: string | null;
  postal_code?: string | null;
  country_code: string;
  timezone: string;
  google_place_id?: string | null;
};

export type WorkspaceBusiness = {
  business_id: string;
  business_name: string;
  business_display_name: string;
  business_slug: string;
  membership_role: string;
  location_count: number;
  locations: WorkspaceLocation[];
};

export type BusinessCreatePayload = {
  name: string;
  display_name?: string;
  timezone?: string;
  primary_email?: string | null;
};

export type BusinessProfile = {
  id: string;
  name: string;
  display_name: string;
  slug: string;
  vertical?: string | null;
  primary_phone_e164?: string | null;
  primary_email?: string | null;
  timezone: string;
  status: string;
  settings: Record<string, unknown>;
  place_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type BusinessProfileUpdatePayload = {
  display_name: string;
  vertical?: string | null;
  primary_email?: string | null;
  timezone: string;
  expected_compliance_policy_hash?: string | null;
  company_address?: string | null;
  week_start_day?: string | null;
  same_day_second_shift_allowed?: boolean | null;
  same_location_overlap_minutes?: number | null;
  cross_location_shift_coverage_allowed?: boolean | null;
  cross_location_min_gap_minutes?: number | null;
  cross_location_max_radius_miles?: number | null;
  reliability_coaching_style?: "supportive" | "direct" | "firm" | null;
  compliance?: CompliancePolicySettingsUpdate | null;
  compliance_payroll_export?: CompliancePayrollExportSettingsUpdate | null;
};

export type ShiftDefaultKey = string;

export type ShiftDefault = {
  key: ShiftDefaultKey;
  label: string;
  start_hour: number;
  end_hour: number;
};

export type BusinessShiftDefaults = {
  business_id: string;
  presets: ShiftDefault[];
  derived_from_location_id?: string | null;
  is_persisted: boolean;
};

export type LocationShiftDefaults = {
  business_id: string;
  location_id: string;
  has_overrides: boolean;
  presets: ShiftDefault[];
  business_presets: ShiftDefault[];
  override_presets?: ShiftDefault[] | null;
};

export type Workspace = {
  user: WorkspaceUser;
  onboarding_required: boolean;
  businesses: WorkspaceBusiness[];
  locations: WorkspaceLocation[];
};

export type ManagerAccessEntry = {
  id: string;
  location_id: string;
  entry_kind: "membership" | "invite";
  manager_name?: string | null;
  manager_email?: string | null;
  phone_e164?: string | null;
  role: string;
  invite_status: string;
  invite_channel: string;
  accepted_at?: string | null;
  revoked_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ManagerAccessInvitePayload = {
  email: string;
  manager_name?: string;
  role?: string;
};

export type LocationSettings = {
  location_id: string;
  coverage_requires_manager_approval: boolean;
  late_arrival_policy: "wait" | "manager_action" | "start_coverage";
  missed_check_in_policy: "manager_action" | "start_coverage";
  agency_supply_approved: boolean;
  writeback_enabled: boolean;
  timezone?: string | null;
  scheduling_platform?: string | null;
  integration_status?: string | null;
  backfill_shifts_enabled: boolean;
  backfill_shifts_launch_state: string;
  backfill_shifts_beta_eligible: boolean;
  week_start_day?: string | null;
  compliance: CompliancePolicySettings;
};

export type CompliancePolicySettings = {
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

export type CompliancePolicySettingsUpdate = Partial<CompliancePolicySettings>;

export type CompliancePayrollIdentifierField =
  | "employee_number"
  | "external_ref";

export type CompliancePayrollProviderProfile =
  | "generic_csv_v1"
  | "gusto_csv_v1"
  | "quickbooks_csv_v1"
  | "adp_csv_v1";

export type CompliancePayrollExportRuleCodeConfig = {
  code: string;
  label?: string | null;
};

export type CompliancePayrollExportSettings = {
  provider_profile: CompliancePayrollProviderProfile;
  employee_identifier_priority: CompliancePayrollIdentifierField[];
  allow_internal_employee_id_fallback: boolean;
  default_earning_code: string;
  default_earning_label: string;
  earning_codes: Record<string, CompliancePayrollExportRuleCodeConfig>;
};

export type CompliancePayrollExportRuleCodeConfigUpdate = {
  code?: string | null;
  label?: string | null;
};

export type CompliancePayrollExportSettingsUpdate = {
  provider_profile?: CompliancePayrollProviderProfile | null;
  employee_identifier_priority?: CompliancePayrollIdentifierField[] | null;
  allow_internal_employee_id_fallback?: boolean | null;
  default_earning_code?: string | null;
  default_earning_label?: string | null;
  earning_codes?: Record<
    string,
    CompliancePayrollExportRuleCodeConfigUpdate | null
  > | null;
};

export type LocationSettingsUpdate = Partial<
  Omit<LocationSettings, "location_id" | "compliance">
> & {
  compliance?: CompliancePolicySettingsUpdate | null;
};

export type WorkspaceBoard = {
  business_id: string;
  business_name: string;
  business_slug: string;
  location_id: string;
  location_name: string;
  location_slug: string;
  address_line_1?: string | null;
  locality?: string | null;
  region?: string | null;
  postal_code?: string | null;
  country_code: string;
  timezone: string;
  week_start_date: string;
  week_end_date: string;
  location_role_setup_required: boolean;
  location_employee_setup_required: boolean;
  location_setup_required: boolean;
  roles: Array<{
    role_id: string;
    role_code: string;
    role_name: string;
    min_headcount?: number | null;
    max_headcount?: number | null;
  }>;
  available_roles: Array<{
    role_id: string;
    role_code: string;
    role_name: string;
    min_headcount?: number | null;
    max_headcount?: number | null;
  }>;
  workers: Array<{
    employee_id: string;
    full_name: string;
    preferred_name?: string | null;
    phone_e164?: string | null;
    email?: string | null;
    primary_location_id?: string | null;
    avg_response_time_seconds?: number | null;
    role_ids: string[];
    role_names: string[];
    reliability_score: number;
    can_cover_here: boolean;
    can_blast_here: boolean;
  }>;
  publish_summary: {
    state: "draft" | "published" | "amended";
    published_at?: string | null;
    amended_at?: string | null;
    published_shift_ids: string[];
    amended_shift_ids: string[];
    published_employee_ids: string[];
    amended_employee_ids: string[];
  };
  shifts: Array<{
    shift_id: string;
    role_id: string;
    role_code: string;
    role_name: string;
    starts_at: string;
    ends_at: string;
    lifecycle_status: string;
    staffing_status: string;
    status: string;
    seats_requested: number;
    seats_filled: number;
    requires_manager_approval: boolean;
    premium_cents: number;
    notes?: string | null;
    current_assignment?: {
      assignment_id: string;
      employee_id?: string | null;
      employee_name?: string | null;
      status: string;
      assigned_via: string;
      accepted_at?: string | null;
      compliance_status?: string | null;
      compliance_profile_code?: string | null;
      compliance_blocking_rule_codes: string[];
      compliance_warning_rule_codes: string[];
      compliance_premium_rule_codes: string[];
      compliance_premium_total_cents: number;
      compliance_unresolved_premium_rule_codes: string[];
      compliance_override_applied: boolean;
      compliance_override_artifact_id?: string | null;
    } | null;
    last_assignment?: {
      assignment_id: string;
      employee_id?: string | null;
      employee_name?: string | null;
      status: string;
      assigned_via: string;
      accepted_at?: string | null;
      compliance_status?: string | null;
      compliance_profile_code?: string | null;
      compliance_blocking_rule_codes: string[];
      compliance_warning_rule_codes: string[];
      compliance_premium_rule_codes: string[];
      compliance_premium_total_cents: number;
      compliance_unresolved_premium_rule_codes: string[];
      compliance_override_applied: boolean;
      compliance_override_artifact_id?: string | null;
    } | null;
    campaign_id?: string | null;
    campaign_status?: string | null;
    coverage_case_id?: string | null;
    coverage_case_status?: string | null;
    pending_offer_count: number;
    delivered_offer_count: number;
    standby_depth: number;
    manager_action_required: boolean;
    amended_from_published: boolean;
    amendment_reason_code?: string | null;
    schedule_break: boolean;
    historical_display: boolean;
  }>;
  action_summary: {
    total: number;
    approval_required: number;
    active_coverage: number;
    open_shifts: number;
  };
};

export type ShiftCreatePayload = {
  location_id: string;
  role_id: string;
  timezone: string;
  starts_at: string;
  ends_at: string;
  seats_requested?: number;
  requires_manager_approval?: boolean;
  premium_cents?: number;
  notes?: string | null;
  source_system?: string;
  source_shift_id?: string | null;
  shift_metadata?: Record<string, unknown>;
};

export type ShiftUpdatePayload = Partial<
  Omit<ShiftCreatePayload, "location_id" | "source_system" | "source_shift_id">
> & {
  role_id?: string;
  shift_metadata?: Record<string, unknown>;
};

export type ShiftRecord = {
  id: string;
  business_id: string;
  location_id: string;
  role_id: string;
  source_system: string;
  source_shift_id?: string | null;
  timezone: string;
  starts_at: string;
  ends_at: string;
  lifecycle_status: string;
  staffing_status: string;
  status: string;
  seats_requested: number;
  seats_filled: number;
  requires_manager_approval: boolean;
  premium_cents: number;
  notes?: string | null;
  shift_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ShiftAssignmentMutationPayload = {
  employee_id: string | null;
  source: "scheduler_ui" | "copilot";
  note?: string;
  expected_assignment_id?: string | null;
};

export type ShiftAssignmentMutationResponse = {
  shift_id: string;
  lifecycle_status: string;
  staffing_status: string;
  status: string;
  current_assignment?: WorkspaceBoard["shifts"][number]["current_assignment"] | null;
};

export type ScheduleWeekPublishPayload = {
  source: "scheduler_ui" | "copilot";
  notify_channels: Array<"sms" | "email">;
  expected_shift_ids?: string[] | null;
  note?: string;
};

export type ComplianceRuleSourceReference = {
  rule_code: string;
  source_kind: string;
  source_code?: string | null;
  source_label?: string | null;
  jurisdiction_code?: string | null;
  source_document_title?: string | null;
  source_urls: string[];
  source_version?: string | null;
  source_hash?: string | null;
  version_id?: string | null;
  payload_hash?: string | null;
  effective_at?: string | null;
};

export type ScheduleWeekPublishResponse = {
  business_id: string;
  location_id: string;
  week_start_date: string;
  week_end_date: string;
  publish_mode: "draft_only_net_new";
  published_shift_count: number;
  already_scheduled_shift_count: number;
  notification_enqueued_assignment_count: number;
  notification_enqueued_employee_count: number;
  published_shift_ids: string[];
  already_scheduled_shift_ids: string[];
  compliance_summary?: {
    selected_assignment_count: number;
    clear_assignment_count: number;
    warning_assignment_count: number;
    blocked_assignment_count: number;
    override_applied_count: number;
    override_eligible_warning_count: number;
    premium_total_cents: number;
    unresolved_premium_rule_count: number;
    unresolved_premium_rule_codes: string[];
    warning_rule_codes: string[];
    override_eligible_artifact_types: string[];
    warning_shift_ids: string[];
    blocked_shift_ids: string[];
    override_eligible_shift_ids: string[];
  };
  compliance_review_items?: Array<{
    assignment_id?: string | null;
    shift_id: string;
    employee_id: string;
    status: string;
    blocking_rule_codes: string[];
    warning_rule_codes: string[];
    premium_total_cents: number;
    unresolved_premium_rule_codes: string[];
    override_applied: boolean;
    override_artifact_id?: string | null;
    override_eligible_artifact_types: string[];
    policy_version_id?: string | null;
    policy_hash?: string | null;
    policy_effective_at?: string | null;
    policy_scope?: string | null;
    issues: Array<{
      rule_code: string;
      status: string;
      reason_codes: string[];
      premium_required: boolean;
      premium_type?: string | null;
      premium_cents: number;
      premium_rate_basis?: string | null;
      premium_rate_hourly_cents?: number | null;
      unresolved_premium: boolean;
      would_block: boolean;
      artifact_type_allowed?: "written_consent" | "meal_waiver" | null;
      override_applied: boolean;
      override_artifact_id?: string | null;
      rule_source_references: ComplianceRuleSourceReference[];
    }>;
  }>;
};

export type ComplianceReviewSummary = NonNullable<
  ScheduleWeekPublishResponse["compliance_summary"]
>;

export type ComplianceReviewItem = NonNullable<
  ScheduleWeekPublishResponse["compliance_review_items"]
>[number];

export type ScheduleWeekFuturePolicyReview = {
  policy_version_id?: string | null;
  policy_hash?: string | null;
  policy_effective_at: string;
  policy_scope: string;
  summary: ComplianceReviewSummary;
  review_items: ComplianceReviewItem[];
};

export type ScheduleWeekFuturePolicyReviewResponse = {
  week_start_date: string;
  week_end_date: string;
  summary: ComplianceReviewSummary;
  policy_reviews: ScheduleWeekFuturePolicyReview[];
};

export type ShiftComplianceDecisionHistoryItem = {
  id: string;
  occurred_at: string;
  actor_type: string;
  actor_user_id?: string | null;
  actor_membership_id?: string | null;
  trace_id: string;
  shift_id: string;
  employee_id: string;
  assignment_id?: string | null;
  coverage_case_id?: string | null;
  decision_source: string;
  decision_outcome: string;
  engine_version: string;
  profile_code?: string | null;
  profile_version_id?: string | null;
  profile_payload_hash?: string | null;
  blocking_rule_codes: string[];
  warning_rule_codes: string[];
  premium_rule_codes: string[];
  premium_total_cents: number;
  premium_components: Array<Record<string, unknown>>;
  unresolved_premium_rule_codes: string[];
  override_applied: boolean;
  override_artifact_id?: string | null;
  rule_source_references: ComplianceRuleSourceReference[];
  evaluation: Record<string, unknown>;
};

export type PublishedShiftAmendmentPayload = {
  action: "cancel_shift" | "unassign_shift" | "reassign_shift";
  reason_code: "cancelled" | "callout" | "no_show" | "reassignment" | "amendment";
  target_employee_id?: string | null;
  source: "scheduler_ui" | "copilot" | "retell_voice" | "sms_automation";
  note?: string;
};

export type PublishedShiftAmendmentResponse = {
  shift_id: string;
  action: PublishedShiftAmendmentPayload["action"];
  reason_code: PublishedShiftAmendmentPayload["reason_code"];
  amended_from_published: boolean;
  schedule_break: boolean;
  lifecycle_status: string;
  staffing_status: string;
  status: string;
  week_publish_state: "amended";
  current_assignment?: WorkspaceBoard["shifts"][number]["current_assignment"] | null;
};

export type PredictiveScheduleRun = {
  id: string;
  business_id: string;
  location_id?: string | null;
  planning_window_start: string;
  planning_window_end: string;
  run_type: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | string;
  optimizer_engine: string;
  objective_version: string;
  constraints_version: string;
  policy_version: string;
  input_snapshot_version: string;
  input_snapshot_hash: string;
  run_metadata: Record<string, unknown>;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
  inputs?: {
    shift_payload: Record<string, unknown>;
    employee_payload: Record<string, unknown>;
    availability_payload: Record<string, unknown>;
    policy_payload: Record<string, unknown>;
    labor_payload: Record<string, unknown>;
    reliability_payload: Record<string, unknown>;
    reliability_snapshot_generated_at?: string | null;
    reliability_snapshot_hash?: string | null;
    reliability_snapshot_version?: string | null;
    source_metadata: Record<string, unknown>;
  } | null;
  proposed_shifts: Array<{
    id: string;
    schedule_run_id: string;
    applied_shift_id?: string | null;
    source_run_id?: string | null;
    source_point_id?: string | null;
    location_id?: string | null;
    role_id?: string | null;
    demand_key: string;
    optimizer_shift_id: string;
    source_type: string;
    generation_version: string;
    timezone: string;
    starts_at: string;
    ends_at: string;
    headcount: number;
    premium_cents: number;
    requires_manager_approval: boolean;
    generation_payload: Record<string, unknown>;
    created_at: string;
    updated_at: string;
  }>;
  assignments: Array<{
    id: string;
    shift_id?: string | null;
    proposed_shift_id?: string | null;
    employee_id?: string | null;
    decision_score: number;
    decision_rank: number;
    assignment_payload: Record<string, unknown>;
    created_at: string;
    updated_at: string;
  }>;
  rejections: Array<{
    id: string;
    shift_id?: string | null;
    employee_id?: string | null;
    candidate_rank: number;
    rejection_reason_codes: unknown[];
    score_payload: Record<string, unknown>;
    constraint_failure_payload: Record<string, unknown>;
    created_at: string;
    updated_at: string;
  }>;
  explanation?: {
    summary_payload: Record<string, unknown>;
    fairness_payload: Record<string, unknown>;
    overtime_payload: Record<string, unknown>;
    coverage_payload: Record<string, unknown>;
    unassigned_shift_payload: Record<string, unknown>;
  } | null;
  metrics?: {
    shift_count: number;
    assigned_shift_count: number;
    unassigned_shift_count: number;
    candidate_considered_count: number;
    overtime_assignment_count: number;
    fairness_spread_metrics: Record<string, unknown>;
    solver_runtime_ms: number;
    objective_value?: number | null;
  } | null;
  compliance_summary?: {
    selected_assignment_count: number;
    clear_assignment_count: number;
    warning_assignment_count: number;
    blocked_assignment_count: number;
    override_applied_count: number;
    override_eligible_warning_count: number;
    premium_total_cents: number;
    unresolved_premium_rule_count: number;
    unresolved_premium_rule_codes: string[];
    warning_rule_codes: string[];
    override_eligible_artifact_types: string[];
    warning_shift_ids: string[];
    blocked_shift_ids: string[];
    override_eligible_shift_ids: string[];
  } | null;
  compliance_review_items?: Array<{
    assignment_id: string;
    shift_id?: string | null;
    proposed_shift_id?: string | null;
    optimizer_shift_id?: string | null;
    employee_id: string;
    status: string;
    blocking_rule_codes: string[];
    warning_rule_codes: string[];
    premium_total_cents: number;
    unresolved_premium_rule_codes: string[];
    override_applied: boolean;
    override_artifact_id?: string | null;
    override_eligible_artifact_types: string[];
    issues: Array<{
      rule_code: string;
      status: string;
      reason_codes: string[];
      premium_required: boolean;
      premium_type?: string | null;
      premium_cents: number;
      premium_rate_basis?: string | null;
      premium_rate_hourly_cents?: number | null;
      unresolved_premium: boolean;
      would_block: boolean;
      artifact_type_allowed?: "written_consent" | "meal_waiver" | null;
      override_applied: boolean;
      override_artifact_id?: string | null;
      rule_source_references: ComplianceRuleSourceReference[];
    }>;
  }> | null;
  applies: Array<{
    id: string;
    schedule_run_id: string;
    business_id: string;
    location_id?: string | null;
    planning_window_start: string;
    planning_window_end: string;
    status: string;
    target_snapshot_hash: string;
    current_snapshot_hash: string;
    stale_reason?: string | null;
    apply_metadata: Record<string, unknown>;
    applied_at?: string | null;
    created_at: string;
    updated_at: string;
  }>;
  replay_run_ids: string[];
};

export type PredictiveScheduleApplyResult = {
  id: string;
  schedule_run_id: string;
  business_id: string;
  location_id?: string | null;
  planning_window_start: string;
  planning_window_end: string;
  status: "queued" | "applied" | "stale_rejected" | "failed" | "no_op" | string;
  target_snapshot_hash: string;
  current_snapshot_hash: string;
  stale_reason?: string | null;
  apply_metadata: Record<string, unknown>;
  applied_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type ShiftComplianceOverrideCreatePayload = {
  employee_id: string;
  artifact_type: "written_consent" | "meal_waiver";
  rule_code?: string | null;
  expires_at?: string | null;
  note?: string | null;
  artifact_payload?: Record<string, unknown>;
};

export type ShiftComplianceOverrideRecord = {
  id: string;
  business_id: string;
  location_id: string;
  shift_id: string;
  employee_id: string;
  assignment_id?: string | null;
  labor_rule_profile_version_id?: string | null;
  approved_by_user_id?: string | null;
  rule_code: string;
  artifact_type: string;
  status: string;
  engine_version: string;
  profile_payload_hash?: string | null;
  approved_at: string;
  expires_at?: string | null;
  revoked_at?: string | null;
  note?: string | null;
  reason_codes: string[];
  artifact_payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export class ShiftAssignmentConflictError extends Error {
  currentAssignment?: ShiftAssignmentMutationResponse["current_assignment"];

  constructor(
    message: string,
    currentAssignment?: ShiftAssignmentMutationResponse["current_assignment"],
  ) {
    super(message);
    this.name = "ShiftAssignmentConflictError";
    this.currentAssignment = currentAssignment;
  }
}

export class ShiftAssignmentComplianceError extends Error {
  summary?: ComplianceReviewSummary;
  reviewItems?: ComplianceReviewItem[];

  constructor(
    message: string,
    summary?: ShiftAssignmentComplianceError["summary"],
    reviewItems?: ShiftAssignmentComplianceError["reviewItems"],
  ) {
    super(message);
    this.name = "ShiftAssignmentComplianceError";
    this.summary = summary;
    this.reviewItems = reviewItems;
  }
}

export class ScheduleWeekPublishConflictError extends Error {
  current?: {
    week_start_date: string;
    publishable_shift_ids: string[];
    draft_shift_count: number;
    already_scheduled_shift_count: number;
  };

  constructor(
    message: string,
    current?: ScheduleWeekPublishConflictError["current"],
  ) {
    super(message);
    this.name = "ScheduleWeekPublishConflictError";
    this.current = current;
  }
}

export class PublishedShiftAmendmentComplianceError extends Error {
  summary?: ComplianceReviewSummary;
  reviewItems?: ComplianceReviewItem[];

  constructor(
    message: string,
    summary?: PublishedShiftAmendmentComplianceError["summary"],
    reviewItems?: PublishedShiftAmendmentComplianceError["reviewItems"],
  ) {
    super(message);
    this.name = "PublishedShiftAmendmentComplianceError";
    this.summary = summary;
    this.reviewItems = reviewItems;
  }
}

export class ScheduleWeekPublishComplianceError extends Error {
  summary?: ScheduleWeekPublishResponse["compliance_summary"];
  reviewItems?: ScheduleWeekPublishResponse["compliance_review_items"];

  constructor(
    message: string,
    summary?: ScheduleWeekPublishComplianceError["summary"],
    reviewItems?: ScheduleWeekPublishComplianceError["reviewItems"],
  ) {
    super(message);
    this.name = "ScheduleWeekPublishComplianceError";
    this.summary = summary;
    this.reviewItems = reviewItems;
  }
}

export class ScheduleWeekPublishFuturePolicyConflictError extends Error {
  summary?: ComplianceReviewSummary;
  policyReviews?: ScheduleWeekFuturePolicyReview[];

  constructor(
    message: string,
    summary?: ScheduleWeekPublishFuturePolicyConflictError["summary"],
    policyReviews?: ScheduleWeekPublishFuturePolicyConflictError["policyReviews"],
  ) {
    super(message);
    this.name = "ScheduleWeekPublishFuturePolicyConflictError";
    this.summary = summary;
    this.policyReviews = policyReviews;
  }
}

export type CoverageCampaign = {
  id: string;
  shift_id: string;
  location_id: string;
  role_id: string;
  status: string;
  phase_target: string;
  reason_code?: string | null;
  priority: number;
  requires_manager_approval: boolean;
  triggered_by?: string | null;
  campaign_metadata: Record<string, unknown>;
  case_metadata: Record<string, unknown>;
  opened_at?: string | null;
  closed_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type CoverageCampaignExecutionDecision = {
  campaign_id: string;
  coverage_case_id: string;
  shift_id: string;
  recommended_phase?: string | null;
  recommendation_reason: string;
  phase_1_candidate_count: number;
  phase_2_candidate_count: number;
  phase_1_plan: {
    phase: string;
    operating_mode: string;
    strategy: string;
    time_to_shift_minutes: number;
    dispatch_limit: number;
    offer_ttl_minutes: number;
    premium_cents: number;
    phase_2_eligible: boolean;
    phase_2_reason?: string | null;
  };
  phase_2_plan: {
    phase: string;
    operating_mode: string;
    strategy: string;
    time_to_shift_minutes: number;
    dispatch_limit: number;
    offer_ttl_minutes: number;
    premium_cents: number;
    phase_2_eligible: boolean;
    phase_2_reason?: string | null;
  };
};

export type CoverageCampaignDispatchResult = {
  decision: CoverageCampaignExecutionDecision;
  phase_executed?: string | null;
  campaign: CoverageCampaign;
  coverage_case: CoverageCampaign;
  candidate_count: number;
  offers: Array<{
    id: string;
    status: string;
    employee_id: string;
    channel: string;
    expires_at?: string | null;
  }>;
};

export type CoverageCase = CoverageCampaign;
export type CoverageExecutionDecision = CoverageCampaignExecutionDecision;
export type CoverageDispatchResult = CoverageCampaignDispatchResult;

export type EmployeeEnrollmentPayload = {
  location_id: string;
  role_ids: string[];
  full_name: string;
  preferred_name?: string | null;
  phone_e164?: string | null;
  email?: string | null;
  employment_type?: string | null;
  notes?: string | null;
  employee_metadata?: Record<string, unknown>;
};

export async function getWorkspace(): Promise<Workspace | null> {
  return fetchAppJson<Workspace>(`${API_PREFIX}/workspace`);
}

export async function createBusiness(payload: BusinessCreatePayload) {
  const response = await apiFetchApp(`${API_PREFIX}/businesses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as {
    id: string;
    name: string;
    display_name: string;
    slug: string;
    timezone: string;
  };
}

export async function getBusinessProfile(businessId: string) {
  const response = await apiFetchApp(`${API_PREFIX}/businesses/${businessId}`);
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as BusinessProfile;
}

export async function updateBusinessProfile(
  businessId: string,
  payload: BusinessProfileUpdatePayload,
) {
  const response = await apiFetchApp(`${API_PREFIX}/businesses/${businessId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as BusinessProfile;
}

export async function getBusinessShiftDefaults(businessId: string) {
  return fetchAppJson<BusinessShiftDefaults>(
    `${API_PREFIX}/businesses/${businessId}/shift-defaults`,
  );
}

export async function updateBusinessShiftDefaults(
  businessId: string,
  presets: ShiftDefault[],
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/shift-defaults`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ presets }),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as BusinessShiftDefaults;
}

export async function deriveBusinessRoles(businessId: string) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/roles/derive`,
    {
      method: "POST",
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as {
    business_id: string;
    vertical?: string | null;
    settings: Record<string, unknown>;
    roles: Array<{
      id: string;
      business_id: string;
      code: string;
      name: string;
      category?: string | null;
      description?: string | null;
      min_notice_minutes: number;
      default_shift_length_minutes?: number | null;
      coverage_priority: number;
      metadata_json: Record<string, unknown>;
      created_at: string;
      updated_at: string;
    }>;
  };
}

export async function createLocationFromPlace(
  businessId: string,
  place: PlaceSuggestion,
  options?: {
    timezone?: string;
    settings?: Record<string, unknown>;
  },
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/locations`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildLocationPayloadFromPlace(place, options)),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as {
    id: string;
    business_id: string;
    name: string;
    display_name: string;
    slug: string;
  };
}

export async function deleteLocation(businessId: string, locationId: string) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/locations/${locationId}`,
    {
      method: "DELETE",
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as { deleted: boolean; location_id: string };
}

export async function inviteLocationManager(
  businessId: string,
  locationId: string,
  payload: ManagerAccessInvitePayload,
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/manager-access`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as {
    location_id: string;
    created: boolean;
    delivery_id?: string | null;
    access: ManagerAccessEntry;
  };
}

export async function listLocationManagers(
  businessId: string,
  locationId: string,
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/manager-access`,
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as ManagerAccessEntry[];
}

export async function revokeLocationManager(
  businessId: string,
  locationId: string,
  membershipId: string,
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/manager-access/${membershipId}`,
    {
      method: "DELETE",
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as {
    revoked: boolean;
    location_id: string;
    access_kind: string;
    access_id: string;
  };
}

export async function revokeLocationManagerInvite(
  businessId: string,
  locationId: string,
  inviteId: string,
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/manager-invites/${inviteId}`,
    {
      method: "DELETE",
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as {
    revoked: boolean;
    location_id: string;
    access_kind: string;
    access_id: string;
  };
}

export async function getLocationSettings(
  businessId: string,
  locationId: string,
) {
  return fetchAppJson<LocationSettings>(
    `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/settings`,
  );
}

export async function updateLocationSettings(
  businessId: string,
  locationId: string,
  payload: LocationSettingsUpdate,
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/settings`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as LocationSettings;
}

export async function getLocationShiftDefaults(
  businessId: string,
  locationId: string,
) {
  return fetchAppJson<LocationShiftDefaults>(
    `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/shift-defaults`,
  );
}

export async function updateLocationShiftDefaults(
  businessId: string,
  locationId: string,
  presets: ShiftDefault[] | null,
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/shift-defaults`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ presets }),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as LocationShiftDefaults;
}

export async function attachRoleToLocation(
  businessId: string,
  locationId: string,
  roleId: string,
  payload?: {
    min_headcount?: number | null;
    max_headcount?: number | null;
    premium_rules?: Record<string, unknown>;
    coverage_settings?: Record<string, unknown>;
  },
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/roles/${roleId}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload ?? {}),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as {
    id: string;
    location_id: string;
    role_id: string;
    is_active: boolean;
    min_headcount?: number | null;
    max_headcount?: number | null;
    premium_rules: Record<string, unknown>;
    coverage_settings: Record<string, unknown>;
    created_at: string;
    updated_at: string;
  };
}

export async function getLocationBoard(
  businessId: string,
  locationId: string,
  weekStart?: string,
): Promise<WorkspaceBoard | null> {
  const qs = weekStart ? `?week_start=${encodeURIComponent(weekStart)}` : "";
  const response = await apiFetchApp(
    `${API_PREFIX}/workspace/businesses/${businessId}/locations/${locationId}/board${qs}`,
    {
      cache: "no-store",
      next: { revalidate: 0 },
    },
  );
  if (!response.ok) {
    return null;
  }
  const board = (await response.json()) as WorkspaceBoard;
  if (!board) {
    return null;
  }
  return {
    ...board,
    shifts: board.shifts.map((shift) => ({
      ...shift,
      campaign_id: shift.campaign_id ?? shift.coverage_case_id ?? null,
      campaign_status: shift.campaign_status ?? shift.coverage_case_status ?? null,
    })),
  } satisfies WorkspaceBoard;
}

export async function createShift(
  businessId: string,
  payload: ShiftCreatePayload,
) {
  const response = await apiFetchApp(`${API_PREFIX}/businesses/${businessId}/shifts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as ShiftRecord;
}

export async function updateShift(
  businessId: string,
  shiftId: string,
  payload: ShiftUpdatePayload,
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/shifts/${shiftId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as ShiftRecord;
}

export async function deleteShift(businessId: string, shiftId: string) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/shifts/${shiftId}`,
    {
      method: "DELETE",
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as { deleted: boolean; shift_id: string };
}

export async function assignShift(
  businessId: string,
  shiftId: string,
  payload: ShiftAssignmentMutationPayload,
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/shifts/${shiftId}/assignment`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (response.status === 409) {
    const body = (await response.json().catch(() => null)) as {
      detail?: {
        code?: string;
        current_assignment?: ShiftAssignmentMutationResponse["current_assignment"];
      } | string;
    } | null;
    const detail = body?.detail;
    if (detail && typeof detail === "object") {
      throw new ShiftAssignmentConflictError(
        detail.code ?? "stale_assignment_conflict",
        detail.current_assignment,
      );
    }
    throw new ShiftAssignmentConflictError("stale_assignment_conflict");
  }
  if (response.status === 422) {
    const body = (await response.json().catch(() => null)) as {
      detail?: {
        code?: string;
        summary?: ComplianceReviewSummary;
        review_items?: ComplianceReviewItem[];
      } | string;
    } | null;
    const detail = body?.detail;
    if (detail && typeof detail === "object" && detail.code === "assignment_compliance_blocked") {
      throw new ShiftAssignmentComplianceError(
        detail.code,
        detail.summary,
        detail.review_items,
      );
    }
  }
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as ShiftAssignmentMutationResponse;
}

export async function amendPublishedShift(
  businessId: string,
  shiftId: string,
  payload: PublishedShiftAmendmentPayload,
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/shifts/${shiftId}/published-amendment`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (response.status === 422) {
    const body = (await response.json().catch(() => null)) as {
      detail?: {
        code?: string;
        summary?: ComplianceReviewSummary;
        review_items?: ComplianceReviewItem[];
      } | string;
    } | null;
    const detail = body?.detail;
    if (
      detail
      && typeof detail === "object"
      && detail.code === "published_amendment_compliance_blocked"
    ) {
      throw new PublishedShiftAmendmentComplianceError(
        detail.code,
        detail.summary,
        detail.review_items,
      );
    }
  }
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as PublishedShiftAmendmentResponse;
}

export async function publishScheduleWeek(
  businessId: string,
  locationId: string,
  weekStartDate: string,
  payload: ScheduleWeekPublishPayload,
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/schedule-weeks/${weekStartDate}/publish`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (response.status === 409 || response.status === 422) {
    const body = (await response.json().catch(() => null)) as {
      detail?: {
        code?: string;
        current?: ScheduleWeekPublishConflictError["current"];
        summary?: ScheduleWeekPublishResponse["compliance_summary"];
        review_items?: ScheduleWeekPublishResponse["compliance_review_items"];
        policy_reviews?: ScheduleWeekFuturePolicyReview[];
      } | string;
    } | null;
    const detail = body?.detail;
    if (detail && typeof detail === "object") {
      if (detail.code === "publish_compliance_blocked") {
        throw new ScheduleWeekPublishComplianceError(
          detail.code,
          detail.summary,
          detail.review_items,
        );
      }
      if (detail.code === "publish_future_policy_conflict") {
        throw new ScheduleWeekPublishFuturePolicyConflictError(
          detail.code,
          detail.summary,
          detail.policy_reviews,
        );
      }
      throw new ScheduleWeekPublishConflictError(
        detail.code ?? "stale_publish_conflict",
        detail.current,
      );
    }
    if (response.status === 422) {
      throw new ScheduleWeekPublishComplianceError("publish_compliance_blocked");
    }
    throw new ScheduleWeekPublishConflictError("stale_publish_conflict");
  }
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as ScheduleWeekPublishResponse;
}

export async function getScheduleWeekFuturePolicyReview(
  businessId: string,
  locationId: string,
  weekStartDate: string,
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/schedule-weeks/${weekStartDate}/future-policy-review`,
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as ScheduleWeekFuturePolicyReviewResponse;
}

export async function ensurePredictiveSchedule(
  businessId: string,
  locationId: string,
  weekStartDate: string,
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/schedule-weeks/${weekStartDate}/predictive-schedule`,
    {
      method: "POST",
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as PredictiveScheduleRun;
}

export async function applyPredictiveSchedule(
  businessId: string,
  locationId: string,
  weekStartDate: string,
  scheduleRunId: string,
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/locations/${locationId}/schedule-weeks/${weekStartDate}/predictive-schedule/${scheduleRunId}/apply`,
    {
      method: "POST",
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as PredictiveScheduleApplyResult;
}

export async function createShiftComplianceOverride(
  businessId: string,
  shiftId: string,
  payload: ShiftComplianceOverrideCreatePayload,
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/shifts/${shiftId}/compliance-overrides`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as ShiftComplianceOverrideRecord;
}

export async function listShiftComplianceDecisions(
  businessId: string,
  shiftId: string,
  options?: { limit?: number },
) {
  const search = new URLSearchParams();
  if (typeof options?.limit === "number") {
    search.set("limit", String(options.limit));
  }
  const suffix = search.size > 0 ? `?${search.toString()}` : "";
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/shifts/${shiftId}/compliance-decisions${suffix}`,
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as ShiftComplianceDecisionHistoryItem[];
}

function normalizeCoverageCampaign(
  payload: CoverageCampaign | (CoverageCampaign & { campaign_metadata?: Record<string, unknown> }),
): CoverageCampaign {
  return {
    ...payload,
    campaign_metadata: payload.campaign_metadata ?? payload.case_metadata ?? {},
    case_metadata: payload.case_metadata ?? payload.campaign_metadata ?? {},
  };
}

function normalizeCoverageDecision(
  payload: CoverageCampaignExecutionDecision,
): CoverageCampaignExecutionDecision {
  return {
    ...payload,
    campaign_id: payload.campaign_id ?? payload.coverage_case_id,
    coverage_case_id: payload.coverage_case_id ?? payload.campaign_id,
  };
}

function normalizeCoverageDispatchResult(
  payload: CoverageCampaignDispatchResult,
): CoverageCampaignDispatchResult {
  const campaign = normalizeCoverageCampaign(payload.campaign ?? payload.coverage_case);
  return {
    ...payload,
    decision: normalizeCoverageDecision(payload.decision),
    campaign,
    coverage_case: campaign,
  };
}

export async function createCoverageCampaign(
  businessId: string,
  payload: {
    shift_id: string;
    phase_target?: string;
    reason_code?: string;
    priority?: number;
    requires_manager_approval?: boolean;
    triggered_by?: string;
    campaign_metadata?: Record<string, unknown>;
    case_metadata?: Record<string, unknown>;
  },
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/coverage-campaigns`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return normalizeCoverageCampaign((await response.json()) as CoverageCampaign);
}

export async function getCoverageCampaignPlan(
  businessId: string,
  campaignId: string,
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/coverage-campaigns/${campaignId}/plan`,
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return normalizeCoverageDecision(
    (await response.json()) as CoverageCampaignExecutionDecision,
  );
}

export async function executeCoverageCampaign(
  businessId: string,
  campaignId: string,
  payload?: {
    phase_override?: string;
    channel?: string;
    dispatch_limit?: number;
    offer_ttl_minutes?: number;
    run_metadata?: Record<string, unknown>;
  },
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/coverage-campaigns/${campaignId}/execute`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload ?? {}),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return normalizeCoverageDispatchResult(
    (await response.json()) as CoverageCampaignDispatchResult,
  );
}

export const createCoverageCase = createCoverageCampaign;
export const getCoveragePlan = getCoverageCampaignPlan;
export const executeCoverageCase = executeCoverageCampaign;

export async function enrollEmployeeAtLocation(
  businessId: string,
  payload: EmployeeEnrollmentPayload,
) {
  const response = await apiFetchApp(
    `${API_PREFIX}/businesses/${businessId}/employees/enroll`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as {
    employee: {
      id: string;
      full_name: string;
      preferred_name?: string | null;
      email?: string | null;
      phone_e164?: string | null;
    };
    roles: Array<{
      id: string;
      role_id: string;
      is_primary: boolean;
    }>;
  };
}
