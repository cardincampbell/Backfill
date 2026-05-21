from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema
from app.schemas.compliance import ComplianceRuleSourceReferenceRead
from app.schemas.settings import CompliancePolicySettingsRead, CompliancePolicySettingsUpdate


class CampaignCostBreakdownRead(BaseSchema):
    provider: str
    product: str
    total_cost_micros: int
    total_cost_cents_rounded: int


class CampaignEconomicsRead(BaseSchema):
    coverage_case_id: UUID
    total_cost_micros: int
    total_cost_cents_rounded: int
    total_billed_cents: int
    total_billed_micros: int
    gross_margin_micros: int
    gross_margin_cents_rounded: int
    billed_entry_count: int
    cost_entry_count: int
    cost_breakdown: list[CampaignCostBreakdownRead]


class LocationBillingCapRead(BaseSchema):
    location_id: UUID
    billing_cycle_start: datetime
    billed_cents: int
    remaining_cents: int
    monthly_cap_cents: int
    fill_price_cents: int
    next_fill_charge_cents: int
    is_capped: bool


class CostLedgerEntryRead(BaseSchema):
    id: UUID
    business_id: UUID | None = None
    location_id: UUID | None = None
    coverage_case_id: UUID | None = None
    shift_id: UUID | None = None
    employee_id: UUID | None = None
    provider: str
    product: str
    reference_type: str
    reference_id: str | None = None
    idempotency_key: str | None = None
    quantity: Decimal
    unit_cost_micros: int
    total_cost_micros: int
    cost_metadata: dict[str, Any]
    error_message: str | None = None
    occurred_at: datetime


class BillingLedgerEntryRead(BaseSchema):
    id: UUID
    business_id: UUID | None = None
    location_id: UUID | None = None
    coverage_case_id: UUID | None = None
    shift_id: UUID | None = None
    employee_id: UUID | None = None
    billing_event_type: str
    billing_cycle_start: datetime
    amount_cents: int
    cap_applied: bool
    idempotency_key: str | None = None
    billing_metadata: dict[str, Any]
    error_message: str | None = None
    occurred_at: datetime


class ComplianceArtifactTypeCountRead(BaseSchema):
    artifact_type: str
    count: int


class ComplianceRuleCatalogEntryRead(BaseSchema):
    catalog_kind: str
    code: str
    label: str
    description: str | None = None
    jurisdiction_code: str | None = None
    source_document_title: str | None = None
    source_urls: list[str] = Field(default_factory=list)
    source_version: str | None = None
    source_hash: str | None = None
    effective_start_date: date | None = None
    effective_end_date: date | None = None
    payload_hash: str | None = None
    rule_families: list[str] = Field(default_factory=list)
    version_id: UUID | None = None
    version_no: int | None = None
    rule_payload: dict[str, Any] = Field(default_factory=dict)


class LocationComplianceRuleCatalogRead(BaseSchema):
    location_id: UUID
    jurisdiction_code: str
    as_of: datetime
    labor_rule_profiles: list[ComplianceRuleCatalogEntryRead] = Field(default_factory=list)
    work_permit_templates: list[ComplianceRuleCatalogEntryRead] = Field(default_factory=list)


class ComplianceWeekShiftRead(BaseSchema):
    shift_id: UUID
    employee_id: UUID
    employee_name: str | None = None
    role_id: UUID
    role_name: str | None = None
    starts_at: datetime
    ends_at: datetime
    compliance_status: str
    profile_code: str | None = None
    blocking_rule_codes: list[str] = Field(default_factory=list)
    warning_rule_codes: list[str] = Field(default_factory=list)
    premium_rule_codes: list[str] = Field(default_factory=list)
    premium_total_cents: int = 0
    unresolved_premium_rule_codes: list[str] = Field(default_factory=list)
    override_applied: bool = False
    override_artifact_id: UUID | None = None
    rule_source_references: list[ComplianceRuleSourceReferenceRead] = Field(default_factory=list)
    policy_version_id: UUID | None = None
    policy_hash: str | None = None
    policy_effective_at: datetime | None = None
    policy_scope: str | None = None


class ComplianceWeekEmployeeRead(BaseSchema):
    employee_id: UUID
    employee_name: str | None = None
    assignment_count: int
    shift_ids: list[UUID] = Field(default_factory=list)
    warning_rule_codes: list[str] = Field(default_factory=list)
    premium_rule_codes: list[str] = Field(default_factory=list)
    premium_total_cents: int = 0
    unresolved_premium_rule_codes: list[str] = Field(default_factory=list)
    override_applied_count: int = 0


class ComplianceOverrideArtifactSummaryRead(BaseSchema):
    artifact_id: UUID
    shift_id: UUID
    employee_id: UUID
    employee_name: str | None = None
    rule_code: str
    artifact_type: str
    approved_at: datetime
    expires_at: datetime | None = None
    note: str | None = None


class LocationComplianceWeekRead(BaseSchema):
    location_id: UUID
    week_start_date: date
    week_end_date: date
    shift_count: int
    assigned_shift_count: int
    employee_count: int
    warning_assignment_count: int
    blocked_assignment_count: int
    unresolved_premium_assignment_count: int
    premium_total_cents: int
    override_applied_count: int
    warning_rule_codes: list[str] = Field(default_factory=list)
    premium_rule_codes: list[str] = Field(default_factory=list)
    unresolved_premium_rule_codes: list[str] = Field(default_factory=list)
    artifact_type_counts: list[ComplianceArtifactTypeCountRead] = Field(default_factory=list)
    shifts: list[ComplianceWeekShiftRead] = Field(default_factory=list)
    employees: list[ComplianceWeekEmployeeRead] = Field(default_factory=list)
    override_artifacts: list[ComplianceOverrideArtifactSummaryRead] = Field(default_factory=list)


class CompliancePayrollAdjustmentRead(BaseSchema):
    shift_id: UUID
    employee_id: UUID
    employee_name: str | None = None
    role_name: str | None = None
    starts_at: datetime
    ends_at: datetime
    compliance_status: str
    profile_code: str | None = None
    premium_cents: int = 0
    premium_rate_basis: str | None = None
    premium_rate_hourly_cents: int | None = Field(default=None, ge=0)
    premium_rule_codes: list[str] = Field(default_factory=list)
    unresolved_premium_rule_codes: list[str] = Field(default_factory=list)
    premium_payment_required: bool = False
    manual_review_required: bool = False
    override_applied: bool = False
    override_artifact_id: UUID | None = None
    override_artifact_type: str | None = None
    override_artifact_note: str | None = None
    payroll_row_kind: str = "premium_payment"
    payroll_status: str = "ready"
    employee_number: str | None = None
    external_ref: str | None = None
    employee_identifier: str | None = None
    employee_identifier_type: str | None = None
    earning_code: str | None = None
    earning_label: str | None = None
    source_rule_code: str | None = None
    source_reason_codes: list[str] = Field(default_factory=list)
    rule_source_references: list[ComplianceRuleSourceReferenceRead] = Field(default_factory=list)


class LocationCompliancePayrollExportRead(BaseSchema):
    location_id: UUID
    week_start_date: date
    week_end_date: date
    provider_profile: str = "generic_csv_v1"
    row_count: int
    premium_payment_row_count: int
    ready_adjustment_row_count: int = 0
    manual_review_row_count: int
    missing_employee_identifier_row_count: int = 0
    artifact_record_row_count: int
    total_premium_cents: int
    rows: list[CompliancePayrollAdjustmentRead] = Field(default_factory=list)


class ComplianceTrendWeekRead(BaseSchema):
    week_start_date: date
    week_end_date: date
    shift_count: int
    assigned_shift_count: int
    warning_assignment_count: int
    blocked_assignment_count: int
    unresolved_premium_assignment_count: int
    premium_total_cents: int
    override_applied_count: int


class ComplianceTrendRuleCountRead(BaseSchema):
    rule_code: str
    count: int


class LocationComplianceTrendRead(BaseSchema):
    location_id: UUID
    start_week_date: date
    end_week_date: date
    week_count: int
    total_shift_count: int
    total_assigned_shift_count: int
    total_warning_assignment_count: int
    total_blocked_assignment_count: int
    total_unresolved_premium_assignment_count: int
    total_override_applied_count: int
    total_premium_cents: int
    top_warning_rule_codes: list[ComplianceTrendRuleCountRead] = Field(default_factory=list)
    top_premium_rule_codes: list[ComplianceTrendRuleCountRead] = Field(default_factory=list)
    top_unresolved_premium_rule_codes: list[ComplianceTrendRuleCountRead] = Field(default_factory=list)
    weeks: list[ComplianceTrendWeekRead] = Field(default_factory=list)


class LocationCompliancePolicySimulationRequest(BaseSchema):
    week_count: int = Field(default=6, ge=1, le=12)
    compliance: CompliancePolicySettingsUpdate = Field(default_factory=CompliancePolicySettingsUpdate)


class ComplianceTrendDeltaRead(BaseSchema):
    warning_assignment_count_delta: int
    blocked_assignment_count_delta: int
    unresolved_premium_assignment_count_delta: int
    override_applied_count_delta: int
    premium_total_cents_delta: int


class ComplianceTrendWeekDeltaRead(BaseSchema):
    week_start_date: date
    week_end_date: date
    warning_assignment_count_delta: int
    blocked_assignment_count_delta: int
    unresolved_premium_assignment_count_delta: int
    override_applied_count_delta: int
    premium_total_cents_delta: int


class LocationCompliancePolicySimulationRead(BaseSchema):
    location_id: UUID
    end_week_start_date: date
    week_count: int
    baseline_location_compliance_policy_hash: str
    baseline_location_compliance_settings: CompliancePolicySettingsRead = Field(
        default_factory=CompliancePolicySettingsRead
    )
    proposed_location_compliance_settings: CompliancePolicySettingsRead = Field(
        default_factory=CompliancePolicySettingsRead
    )
    baseline: LocationComplianceTrendRead
    simulated: LocationComplianceTrendRead
    delta: ComplianceTrendDeltaRead
    week_deltas: list[ComplianceTrendWeekDeltaRead] = Field(default_factory=list)


class LocationComplianceWeekReplayRead(BaseSchema):
    location_id: UUID
    week_start_date: date
    week_end_date: date
    replay_policy_version_id: UUID
    replay_policy_scope: str
    replay_policy_hash: str
    replay_policy_effective_at: datetime
    baseline: LocationComplianceWeekRead
    replayed: LocationComplianceWeekRead
    delta: ComplianceTrendDeltaRead


class CompliancePolicyActivationRead(BaseSchema):
    policy_version_id: UUID
    policy_scope: str
    policy_hash: str
    effective_at: datetime
    location_id: UUID | None = None
    location_name: str | None = None


class LocationComplianceScheduledPolicyDriftRead(BaseSchema):
    location_id: UUID
    start_week_date: date
    end_week_date: date
    week_count: int
    activating_policy_versions: list[CompliancePolicyActivationRead] = Field(default_factory=list)
    frozen_current: LocationComplianceTrendRead
    scheduled: LocationComplianceTrendRead
    delta: ComplianceTrendDeltaRead
    week_deltas: list[ComplianceTrendWeekDeltaRead] = Field(default_factory=list)


class BusinessComplianceLocationTrendRead(BaseSchema):
    location_id: UUID
    location_name: str
    total_shift_count: int
    total_assigned_shift_count: int
    total_warning_assignment_count: int
    total_blocked_assignment_count: int
    total_unresolved_premium_assignment_count: int
    total_override_applied_count: int
    total_premium_cents: int


class BusinessComplianceTrendRead(BaseSchema):
    business_id: UUID
    end_week_start_date: date
    week_count: int
    location_count: int
    total_shift_count: int
    total_assigned_shift_count: int
    total_warning_assignment_count: int
    total_blocked_assignment_count: int
    total_unresolved_premium_assignment_count: int
    total_override_applied_count: int
    total_premium_cents: int
    top_warning_rule_codes: list[ComplianceTrendRuleCountRead] = Field(default_factory=list)
    top_premium_rule_codes: list[ComplianceTrendRuleCountRead] = Field(default_factory=list)
    top_unresolved_premium_rule_codes: list[ComplianceTrendRuleCountRead] = Field(default_factory=list)
    weeks: list[ComplianceTrendWeekRead] = Field(default_factory=list)
    locations: list[BusinessComplianceLocationTrendRead] = Field(default_factory=list)


class BusinessCompliancePolicySimulationRequest(BaseSchema):
    week_count: int = Field(default=6, ge=1, le=12)
    compliance: CompliancePolicySettingsUpdate = Field(default_factory=CompliancePolicySettingsUpdate)


class BusinessComplianceLocationDeltaRead(BaseSchema):
    location_id: UUID
    location_name: str
    warning_assignment_count_delta: int
    blocked_assignment_count_delta: int
    unresolved_premium_assignment_count_delta: int
    override_applied_count_delta: int
    premium_total_cents_delta: int


class BusinessCompliancePolicySimulationRead(BaseSchema):
    business_id: UUID
    end_week_start_date: date
    week_count: int
    location_count: int
    baseline_business_compliance_policy_hash: str
    baseline_business_compliance_settings: CompliancePolicySettingsRead = Field(
        default_factory=CompliancePolicySettingsRead
    )
    proposed_business_compliance_settings: CompliancePolicySettingsRead = Field(
        default_factory=CompliancePolicySettingsRead
    )
    baseline: BusinessComplianceTrendRead
    simulated: BusinessComplianceTrendRead
    delta: ComplianceTrendDeltaRead
    week_deltas: list[ComplianceTrendWeekDeltaRead] = Field(default_factory=list)
    location_deltas: list[BusinessComplianceLocationDeltaRead] = Field(default_factory=list)


class BusinessComplianceScheduledPolicyDriftRead(BaseSchema):
    business_id: UUID
    start_week_date: date
    end_week_date: date
    week_count: int
    location_count: int
    activating_policy_versions: list[CompliancePolicyActivationRead] = Field(default_factory=list)
    frozen_current: BusinessComplianceTrendRead
    scheduled: BusinessComplianceTrendRead
    delta: ComplianceTrendDeltaRead
    week_deltas: list[ComplianceTrendWeekDeltaRead] = Field(default_factory=list)
    location_deltas: list[BusinessComplianceLocationDeltaRead] = Field(default_factory=list)
