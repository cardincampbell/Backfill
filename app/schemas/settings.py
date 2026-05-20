from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema

ShiftPresetKey = str
CompliancePayrollIdentifierField = Literal["employee_number", "external_ref"]
CompliancePayrollProviderProfile = Literal[
    "generic_csv_v1",
    "gusto_csv_v1",
    "quickbooks_csv_v1",
    "adp_csv_v1",
]
SchoolDayWeekday = Literal[
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
]


class ShiftPresetRead(BaseSchema):
    key: ShiftPresetKey
    label: str
    start_hour: int
    end_hour: int


class ShiftPresetUpdate(BaseSchema):
    key: ShiftPresetKey
    label: str
    start_hour: int
    end_hour: int


class BusinessShiftDefaultsRead(BaseSchema):
    business_id: UUID
    presets: list[ShiftPresetRead]
    derived_from_location_id: Optional[UUID] = None
    is_persisted: bool = True


class BusinessShiftDefaultsUpdate(BaseSchema):
    presets: list[ShiftPresetUpdate]


class LocationShiftDefaultsRead(BaseSchema):
    business_id: UUID
    location_id: UUID
    has_overrides: bool
    presets: list[ShiftPresetRead]
    business_presets: list[ShiftPresetRead]
    override_presets: Optional[list[ShiftPresetRead]] = None


class LocationShiftDefaultsUpdate(BaseSchema):
    presets: Optional[list[ShiftPresetUpdate]] = None


class CompliancePolicySettingsRead(BaseSchema):
    minimum_rest_hours: float | None = None
    written_consent_allowed: bool | None = None
    first_meal_waiver_allowed: bool | None = None
    second_meal_waiver_allowed: bool | None = None
    require_structured_break_plans: bool = False
    block_unresolved_premiums: bool = False
    max_daily_minutes: int | None = None
    max_weekly_minutes: int | None = None
    max_consecutive_work_days: int | None = None
    required_rest_days_per_workweek: int | None = None
    school_day_weekdays: list[SchoolDayWeekday] = Field(default_factory=list)
    school_dates: list[str] = Field(default_factory=list)
    non_school_dates: list[str] = Field(default_factory=list)


class CompliancePolicySettingsUpdate(BaseSchema):
    minimum_rest_hours: float | None = Field(default=None, ge=0)
    written_consent_allowed: bool | None = None
    first_meal_waiver_allowed: bool | None = None
    second_meal_waiver_allowed: bool | None = None
    require_structured_break_plans: bool | None = None
    block_unresolved_premiums: bool | None = None
    max_daily_minutes: int | None = Field(default=None, ge=0)
    max_weekly_minutes: int | None = Field(default=None, ge=0)
    max_consecutive_work_days: int | None = Field(default=None, ge=0)
    required_rest_days_per_workweek: int | None = Field(default=None, ge=0, le=7)
    school_day_weekdays: list[SchoolDayWeekday] | None = None
    school_dates: list[str] | None = None
    non_school_dates: list[str] | None = None


class CompliancePayrollExportRuleCodeConfigRead(BaseSchema):
    code: str
    label: str | None = None


class CompliancePayrollExportRuleCodeConfigUpdate(BaseSchema):
    code: str | None = None
    label: str | None = None


class CompliancePayrollExportSettingsRead(BaseSchema):
    provider_profile: CompliancePayrollProviderProfile = "generic_csv_v1"
    employee_identifier_priority: list[CompliancePayrollIdentifierField] = Field(
        default_factory=lambda: ["employee_number", "external_ref"]
    )
    allow_internal_employee_id_fallback: bool = False
    default_earning_code: str = "COMPLIANCE"
    default_earning_label: str = "Compliance Premium"
    earning_codes: dict[str, CompliancePayrollExportRuleCodeConfigRead] = Field(
        default_factory=dict
    )


class CompliancePayrollExportSettingsUpdate(BaseSchema):
    provider_profile: CompliancePayrollProviderProfile | None = None
    employee_identifier_priority: list[CompliancePayrollIdentifierField] | None = None
    allow_internal_employee_id_fallback: bool | None = None
    default_earning_code: str | None = None
    default_earning_label: str | None = None
    earning_codes: (
        dict[str, CompliancePayrollExportRuleCodeConfigUpdate | None] | None
    ) = None


class CompliancePolicyVersionRead(BaseSchema):
    id: UUID
    business_id: UUID
    location_id: UUID | None = None
    policy_scope: Literal["business", "location"]
    policy_hash: str
    settings: CompliancePolicySettingsRead = Field(
        default_factory=CompliancePolicySettingsRead
    )
    effective_at: datetime
    superseded_at: datetime | None = None
    created_by_user_id: UUID | None = None
    replaces_version_id: UUID | None = None
    clears_parent: bool = False
    is_effective: bool = False
    is_scheduled: bool = False


class CompliancePolicyVersionRestoreWrite(BaseSchema):
    expected_current_policy_hash: str | None = None
    effective_at: datetime | None = None
    note: str | None = None


class LocationSettingsRead(BaseSchema):
    location_id: UUID
    coverage_requires_manager_approval: bool = False
    late_arrival_policy: Literal["wait", "manager_action", "start_coverage"] = "wait"
    missed_check_in_policy: Literal["manager_action", "start_coverage"] = "manager_action"
    agency_supply_approved: bool = False
    writeback_enabled: bool = False
    timezone: Optional[str] = None
    scheduling_platform: Optional[str] = "backfill_native"
    integration_status: Optional[str] = None
    backfill_shifts_enabled: bool = False
    backfill_shifts_launch_state: str = "off"
    backfill_shifts_beta_eligible: bool = False
    week_start_day: Literal[
        "sunday",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
    ] | None = None
    compliance: CompliancePolicySettingsRead = Field(default_factory=CompliancePolicySettingsRead)
    compliance_policy_version_id: UUID | None = None
    compliance_policy_hash: str | None = None
    compliance_policy_effective_at: datetime | None = None
    compliance_policy_scope: Literal["business", "location"] | None = None
    compliance_policy_clears_parent: bool = False


class LocationSettingsUpdate(BaseSchema):
    expected_compliance_policy_hash: str | None = None
    compliance_effective_at: datetime | None = None
    coverage_requires_manager_approval: bool | None = None
    late_arrival_policy: Literal["wait", "manager_action", "start_coverage"] | None = None
    missed_check_in_policy: Literal["manager_action", "start_coverage"] | None = None
    agency_supply_approved: bool | None = None
    writeback_enabled: bool | None = None
    timezone: str | None = None
    scheduling_platform: str | None = None
    integration_status: str | None = None
    backfill_shifts_enabled: bool | None = None
    backfill_shifts_launch_state: str | None = None
    backfill_shifts_beta_eligible: bool | None = None
    week_start_day: Literal[
        "sunday",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
    ] | None = None
    compliance: CompliancePolicySettingsUpdate | None = None
