from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from app.models.business import Business, Location
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.compliance import ComplianceOverrideArtifact, CompliancePolicyVersion
from app.models.finance import BillingLedgerEntry, CostLedgerEntry
from app.models.scheduling import Shift, ShiftAssignment
from app.models.workforce import Employee
from app.services import billing_ledger, compliance_source_references, cost_ledger, workforce
from app.services import settings as settings_service
from app.services import shift_assignments
from app.services.schedule_weeks import schedule_week_window

MICROS_PER_CENT = 10_000
_MISSING_PAYROLL_IDENTIFIER_REASON_CODES = {
    "missing_employee_identifier",
    "missing_employee_number",
    "missing_quickbooks_employee_reference",
}


@dataclass(frozen=True)
class CampaignCostBreakdownRow:
    provider: str
    product: str
    total_cost_micros: int
    total_cost_cents_rounded: int


@dataclass(frozen=True)
class CampaignEconomicsSnapshot:
    coverage_case_id: UUID
    total_cost_micros: int
    total_cost_cents_rounded: int
    total_billed_cents: int
    total_billed_micros: int
    gross_margin_micros: int
    gross_margin_cents_rounded: int
    billed_entry_count: int
    cost_entry_count: int


@dataclass(frozen=True)
class LocationBillingCapSnapshot:
    location_id: UUID
    billing_cycle_start: Any
    billed_cents: int
    remaining_cents: int
    monthly_cap_cents: int
    fill_price_cents: int
    next_fill_charge_cents: int
    is_capped: bool


@dataclass(frozen=True)
class ComplianceArtifactTypeCountRow:
    artifact_type: str
    count: int


@dataclass(frozen=True)
class ComplianceWeekShiftRow:
    shift_id: UUID
    employee_id: UUID
    employee_name: str | None
    role_id: UUID
    role_name: str | None
    starts_at: Any
    ends_at: Any
    compliance_status: str
    profile_code: str | None
    blocking_rule_codes: list[str]
    warning_rule_codes: list[str]
    premium_rule_codes: list[str]
    premium_total_cents: int
    unresolved_premium_rule_codes: list[str]
    override_applied: bool
    override_artifact_id: UUID | None
    premium_components: list[dict[str, object]] = field(default_factory=list)
    rule_source_references: list[dict[str, object]] = field(default_factory=list)
    policy_version_id: UUID | None = None
    policy_hash: str | None = None
    policy_effective_at: Any = None
    policy_scope: str | None = None


@dataclass(frozen=True)
class ComplianceWeekEmployeeRow:
    employee_id: UUID
    employee_name: str | None
    assignment_count: int
    shift_ids: list[UUID]
    warning_rule_codes: list[str]
    premium_rule_codes: list[str]
    premium_total_cents: int
    unresolved_premium_rule_codes: list[str]
    override_applied_count: int


@dataclass(frozen=True)
class ComplianceOverrideArtifactSummaryRow:
    artifact_id: UUID
    shift_id: UUID
    employee_id: UUID
    employee_name: str | None
    rule_code: str
    artifact_type: str
    approved_at: Any
    expires_at: Any
    note: str | None


@dataclass(frozen=True)
class LocationComplianceWeekSnapshot:
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
    warning_rule_codes: list[str]
    premium_rule_codes: list[str]
    unresolved_premium_rule_codes: list[str]
    artifact_type_counts: list[ComplianceArtifactTypeCountRow]
    shifts: list[ComplianceWeekShiftRow]
    employees: list[ComplianceWeekEmployeeRow]
    override_artifacts: list[ComplianceOverrideArtifactSummaryRow]


@dataclass(frozen=True)
class LocationComplianceWeekReplay:
    location_id: UUID
    week_start_date: date
    week_end_date: date
    replay_policy_version_id: UUID
    replay_policy_scope: str
    replay_policy_hash: str
    replay_policy_effective_at: datetime
    baseline: LocationComplianceWeekSnapshot
    replayed: LocationComplianceWeekSnapshot
    delta: ComplianceTrendDeltaSummary


@dataclass(frozen=True)
class CompliancePayrollAdjustmentRow:
    shift_id: UUID
    employee_id: UUID
    employee_name: str | None
    role_name: str | None
    starts_at: Any
    ends_at: Any
    compliance_status: str
    profile_code: str | None
    premium_cents: int
    premium_rule_codes: list[str]
    unresolved_premium_rule_codes: list[str]
    premium_payment_required: bool
    manual_review_required: bool
    override_applied: bool
    override_artifact_id: UUID | None
    override_artifact_type: str | None
    override_artifact_note: str | None
    payroll_row_kind: str = "premium_payment"
    payroll_status: str = "ready"
    employee_number: str | None = None
    external_ref: str | None = None
    employee_identifier: str | None = None
    employee_identifier_type: str | None = None
    earning_code: str | None = None
    earning_label: str | None = None
    source_rule_code: str | None = None
    source_reason_codes: list[str] = field(default_factory=list)
    rule_source_references: list[dict[str, object]] = field(default_factory=list)
    premium_rate_basis: str | None = None
    premium_rate_hourly_cents: int | None = None


@dataclass(frozen=True)
class LocationCompliancePayrollExport:
    location_id: UUID
    week_start_date: date
    week_end_date: date
    provider_profile: str
    row_count: int
    premium_payment_row_count: int
    ready_adjustment_row_count: int
    manual_review_row_count: int
    missing_employee_identifier_row_count: int
    artifact_record_row_count: int
    total_premium_cents: int
    rows: list[CompliancePayrollAdjustmentRow]


@dataclass(frozen=True)
class ComplianceTrendWeekRow:
    week_start_date: date
    week_end_date: date
    shift_count: int
    assigned_shift_count: int
    warning_assignment_count: int
    blocked_assignment_count: int
    unresolved_premium_assignment_count: int
    premium_total_cents: int
    override_applied_count: int


@dataclass(frozen=True)
class ComplianceTrendRuleCountRow:
    rule_code: str
    count: int


@dataclass(frozen=True)
class LocationComplianceTrendSnapshot:
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
    top_warning_rule_codes: list[ComplianceTrendRuleCountRow]
    top_premium_rule_codes: list[ComplianceTrendRuleCountRow]
    top_unresolved_premium_rule_codes: list[ComplianceTrendRuleCountRow]
    weeks: list[ComplianceTrendWeekRow]


@dataclass(frozen=True)
class ComplianceTrendDeltaRow:
    week_start_date: date
    week_end_date: date
    warning_assignment_count_delta: int
    blocked_assignment_count_delta: int
    unresolved_premium_assignment_count_delta: int
    override_applied_count_delta: int
    premium_total_cents_delta: int


@dataclass(frozen=True)
class ComplianceTrendDeltaSummary:
    warning_assignment_count_delta: int
    blocked_assignment_count_delta: int
    unresolved_premium_assignment_count_delta: int
    override_applied_count_delta: int
    premium_total_cents_delta: int


@dataclass(frozen=True)
class LocationCompliancePolicySimulation:
    location_id: UUID
    end_week_start_date: date
    week_count: int
    baseline_location_compliance_policy_hash: str
    baseline_location_compliance_settings: dict[str, object]
    proposed_location_compliance_settings: dict[str, object]
    baseline: LocationComplianceTrendSnapshot
    simulated: LocationComplianceTrendSnapshot
    delta: ComplianceTrendDeltaSummary
    week_deltas: list[ComplianceTrendDeltaRow]


@dataclass(frozen=True)
class CompliancePolicyActivationRow:
    policy_version_id: UUID
    policy_scope: str
    policy_hash: str
    effective_at: datetime
    location_id: UUID | None = None
    location_name: str | None = None


@dataclass(frozen=True)
class LocationComplianceScheduledPolicyDrift:
    location_id: UUID
    start_week_date: date
    end_week_date: date
    week_count: int
    activating_policy_versions: list[CompliancePolicyActivationRow]
    frozen_current: LocationComplianceTrendSnapshot
    scheduled: LocationComplianceTrendSnapshot
    delta: ComplianceTrendDeltaSummary
    week_deltas: list[ComplianceTrendDeltaRow]


@dataclass(frozen=True)
class BusinessComplianceLocationTrendRow:
    location_id: UUID
    location_name: str
    total_shift_count: int
    total_assigned_shift_count: int
    total_warning_assignment_count: int
    total_blocked_assignment_count: int
    total_unresolved_premium_assignment_count: int
    total_override_applied_count: int
    total_premium_cents: int


@dataclass(frozen=True)
class BusinessComplianceTrendSnapshot:
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
    top_warning_rule_codes: list[ComplianceTrendRuleCountRow]
    top_premium_rule_codes: list[ComplianceTrendRuleCountRow]
    top_unresolved_premium_rule_codes: list[ComplianceTrendRuleCountRow]
    weeks: list[ComplianceTrendWeekRow]
    locations: list[BusinessComplianceLocationTrendRow]


@dataclass(frozen=True)
class BusinessComplianceLocationDeltaRow:
    location_id: UUID
    location_name: str
    warning_assignment_count_delta: int
    blocked_assignment_count_delta: int
    unresolved_premium_assignment_count_delta: int
    override_applied_count_delta: int
    premium_total_cents_delta: int


@dataclass(frozen=True)
class BusinessCompliancePolicySimulation:
    business_id: UUID
    end_week_start_date: date
    week_count: int
    location_count: int
    baseline_business_compliance_policy_hash: str
    baseline_business_compliance_settings: dict[str, object]
    proposed_business_compliance_settings: dict[str, object]
    baseline: BusinessComplianceTrendSnapshot
    simulated: BusinessComplianceTrendSnapshot
    delta: ComplianceTrendDeltaSummary
    week_deltas: list[ComplianceTrendDeltaRow]
    location_deltas: list[BusinessComplianceLocationDeltaRow]


@dataclass(frozen=True)
class BusinessComplianceScheduledPolicyDrift:
    business_id: UUID
    start_week_date: date
    end_week_date: date
    week_count: int
    location_count: int
    activating_policy_versions: list[CompliancePolicyActivationRow]
    frozen_current: BusinessComplianceTrendSnapshot
    scheduled: BusinessComplianceTrendSnapshot
    delta: ComplianceTrendDeltaSummary
    week_deltas: list[ComplianceTrendDeltaRow]
    location_deltas: list[BusinessComplianceLocationDeltaRow]


def micros_to_cents_rounded(micros: int) -> int:
    return int(
        (Decimal(micros) / Decimal(MICROS_PER_CENT)).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def cents_to_micros(cents: int) -> int:
    return int(cents * MICROS_PER_CENT)


def _assignment_employee_name(assignment: ShiftAssignment | None) -> str | None:
    if assignment is None:
        return None
    metadata = assignment.assignment_metadata if isinstance(assignment.assignment_metadata, dict) else {}
    raw_name = metadata.get("employee_name")
    if isinstance(raw_name, str) and raw_name.strip():
        return raw_name.strip()
    employee = getattr(assignment, "employee", None)
    full_name = getattr(employee, "full_name", None)
    if isinstance(full_name, str) and full_name.strip():
        return full_name.strip()
    return None


def _normalized_rule_codes(value: object) -> list[str]:
    normalized = {
        str(rule_code or "").strip()
        for rule_code in value or []
        if str(rule_code or "").strip()
    }
    return sorted(normalized)


def _assignment_compliance_metadata(assignment: ShiftAssignment | None) -> dict[str, object]:
    if assignment is None:
        return {}
    metadata = assignment.assignment_metadata if isinstance(assignment.assignment_metadata, dict) else {}
    raw = metadata.get("compliance_evaluation")
    return dict(raw) if isinstance(raw, dict) else {}


def _merged_compliance_settings_payload(
    settings_payload: Mapping[str, object] | None,
    compliance_override: Mapping[str, object] | None,
) -> dict[str, object]:
    merged_settings = dict(settings_payload or {})
    if compliance_override is None:
        return merged_settings
    if (
        "compliance" in compliance_override
        or "compliance_policy_hash" in compliance_override
        or "compliance_policy_scope" in compliance_override
        or "compliance_policy_effective_at" in compliance_override
        or "compliance_policy_version_id" in compliance_override
        or "compliance_policy_clears_parent" in compliance_override
    ):
        for key, value in compliance_override.items():
            if value is None:
                merged_settings.pop(key, None)
            else:
                merged_settings[key] = value
        return merged_settings
    current_compliance = (
        dict(merged_settings.get("compliance"))
        if isinstance(merged_settings.get("compliance"), Mapping)
        else {}
    )
    for key, value in compliance_override.items():
        if value is None:
            current_compliance.pop(key, None)
        else:
            current_compliance[key] = value
    if current_compliance:
        merged_settings["compliance"] = current_compliance
    else:
        merged_settings.pop("compliance", None)
    return merged_settings


def _location_display_name(location: Location) -> str:
    display_name = getattr(location, "location_display_name", None)
    if isinstance(display_name, str) and display_name.strip():
        return display_name.strip()
    fallback = getattr(location, "display_name", None) or getattr(location, "name", None)
    return str(fallback or location.id)


async def _active_business_locations(
    session: AsyncSession,
    *,
    business_id: UUID,
) -> list[Location]:
    result = await session.execute(
        select(Location)
        .where(Location.business_id == business_id)
        .where(Location.is_active.is_(True))
        .order_by(Location.display_name.asc(), Location.name.asc(), Location.id.asc())
    )
    return list(result.scalars().all())


async def _scheduled_policy_versions_for_window(
    session: AsyncSession,
    *,
    business_id: UUID,
    window_end_at: datetime,
    reference_time: datetime,
    location_id: UUID | None = None,
) -> list[CompliancePolicyActivationRow]:
    stmt = (
        select(CompliancePolicyVersion)
        .options(selectinload(CompliancePolicyVersion.location))
        .where(CompliancePolicyVersion.business_id == business_id)
        .where(CompliancePolicyVersion.effective_at > reference_time)
        .where(CompliancePolicyVersion.effective_at <= window_end_at)
        .order_by(
            CompliancePolicyVersion.effective_at.asc(),
            CompliancePolicyVersion.created_at.asc(),
        )
    )
    if location_id is not None:
        stmt = stmt.where(
            (CompliancePolicyVersion.location_id.is_(None))
            | (CompliancePolicyVersion.location_id == location_id)
        )
    result = await session.execute(stmt)
    rows: list[CompliancePolicyActivationRow] = []
    for version in result.scalars().all():
        normalized_scope = (
            "location" if str(version.policy_scope).strip().lower() == "location" else "business"
        )
        rows.append(
            CompliancePolicyActivationRow(
                policy_version_id=version.id,
                policy_scope=normalized_scope,
                policy_hash=version.policy_hash,
                effective_at=version.effective_at,
                location_id=version.location_id,
                location_name=(
                    _location_display_name(version.location)
                    if version.location is not None
                    else None
                ),
            )
        )
    return rows


def _evaluation_metadata_payload(
    evaluation: Mapping[str, object] | None,
    *,
    override_artifact: ComplianceOverrideArtifact | None,
) -> dict[str, object]:
    payload = dict(evaluation or {})
    premium_total_cents = int(payload.get("premium_total_cents") or 0)
    premium_components = [
        dict(component)
        for component in payload.get("premium_components") or []
        if isinstance(component, Mapping)
    ]
    return {
        "status": str(payload.get("status") or "unresolved"),
        "blocking_rule_codes": list(payload.get("blocking_rule_codes") or []),
        "warning_rule_codes": list(payload.get("warning_rule_codes") or []),
        "premium_rule_codes": list(payload.get("premium_rule_codes") or []),
        "premium_total_cents": max(0, premium_total_cents),
        "premium_components": premium_components,
        "unresolved_premium_rule_codes": list(payload.get("unresolved_premium_rule_codes") or []),
        "override_applied": bool(payload.get("override_applied")),
        "override_artifact_id": (
            str(override_artifact.id)
            if override_artifact is not None
            else payload.get("override_artifact_id")
        ),
        "profile_code": payload.get("profile_code"),
        "profile_version_id": payload.get("profile_version_id"),
        "profile_payload_hash": payload.get("profile_payload_hash"),
        "policy_version_id": payload.get("policy_version_id"),
        "policy_hash": payload.get("policy_hash"),
        "policy_effective_at": payload.get("policy_effective_at"),
        "policy_scope": payload.get("policy_scope"),
        "rule_source_references": compliance_source_references.rule_source_references_from_evaluation(
            payload
        ),
    }


async def _load_compliance_policy_version_for_location(
    session: AsyncSession,
    *,
    location: Location,
    policy_version_id: UUID,
) -> CompliancePolicyVersion:
    version = await session.get(CompliancePolicyVersion, policy_version_id)
    if version is None or version.business_id != location.business_id:
        raise LookupError("compliance_policy_version_not_found")
    normalized_scope = (
        "location" if str(version.policy_scope).strip().lower() == "location" else "business"
    )
    if normalized_scope == "location" and version.location_id != location.id:
        raise LookupError("compliance_policy_version_not_found")
    if normalized_scope == "business" and version.location_id is not None:
        raise LookupError("compliance_policy_version_not_found")
    return version


async def _resolved_assignment_compliance_metadata(
    session: AsyncSession,
    *,
    shift: Shift,
    assignment: ShiftAssignment,
    business_settings_override: Mapping[str, object] | None = None,
    location_settings_override: Mapping[str, object] | None = None,
    force_recompute: bool = False,
) -> dict[str, object]:
    metadata = _assignment_compliance_metadata(assignment)
    if (
        metadata
        and not force_recompute
        and business_settings_override is None
        and location_settings_override is None
    ):
        return metadata
    if assignment.employee_id is None:
        return {}
    employee = assignment.employee
    if employee is None:
        employee = await session.get(Employee, assignment.employee_id)
    if employee is None:
        return {}
    if (
        business_settings_override is None
        and location_settings_override is None
        and not force_recompute
    ):
        from app.services import scheduling as scheduling_service

        _base_evaluation, evaluation, override_artifact = await scheduling_service._resolve_assignment_compliance(
            session,
            shift=shift,
            employee=employee,
            reference_time=shift.starts_at,
        )
        return scheduling_service._compliance_metadata_for_assignment(
            evaluation,
            override_artifact=override_artifact,
        )
    location = shift.location
    if location is None:
        location = await session.get(Location, shift.location_id)
    if location is None:
        return {}
    business = getattr(location, "business", None)
    if business is None:
        business = await session.get(Business, location.business_id)
    from app.services import compliance_engine, compliance_overrides, labor_rules

    resolved_business_settings, resolved_location_settings = (
        await settings_service.resolved_compliance_settings_inputs(
            session,
            business=business,
            location=location,
            as_of=shift.starts_at,
        )
        if business is not None
        else ({}, {})
    )
    business_settings = _merged_compliance_settings_payload(
        resolved_business_settings,
        business_settings_override,
    )
    location_settings = _merged_compliance_settings_payload(
        resolved_location_settings,
        location_settings_override,
    )
    profile = await labor_rules.runtime_resolved_profile(
        session,
        location=location,
        business=business,
        as_of=shift.starts_at,
    )
    if profile is None:
        work_permit_context = workforce.resolve_employee_work_permit_context(
            employee,
            shift_starts_at=shift.starts_at,
            timezone_name=shift.timezone,
        )
        unresolved = compliance_engine.evaluate_shift_assignment_compliance(
            None,
            candidate_shift=shift,
            counted_intervals=(),
            reference_time=shift.starts_at,
            employee_base_hourly_rate_cents=employee.base_hourly_rate_cents,
            employee_premium_hourly_rate_cents=employee.compliance_regular_rate_cents,
            employee_date_of_birth=employee.date_of_birth,
            employee_minor_school_status=employee.minor_school_status,
            employee_work_permit_number=work_permit_context.get("permit_number"),
            employee_work_permit_effective_start_on=work_permit_context.get("effective_start_on"),
            employee_work_permit_expires_on=work_permit_context.get("expires_on"),
            employee_work_permit_max_daily_minutes=work_permit_context.get("max_daily_minutes"),
            employee_work_permit_max_weekly_minutes=work_permit_context.get("max_weekly_minutes"),
            employee_work_permit_earliest_start_local_time=work_permit_context.get("earliest_start_local_time"),
            employee_work_permit_latest_end_local_time=work_permit_context.get("latest_end_local_time"),
            employee_work_permit_rule_profile=work_permit_context.get("rule_profile"),
            business_settings=business_settings,
            location_settings=location_settings,
        )
        return _evaluation_metadata_payload(unresolved, override_artifact=None)

    snapshots = await labor_rules.build_hours_snapshots(
        session,
        employees=[employee],
        shift=shift,
        profile=profile,
        compliance_settings=settings_service.merged_compliance_settings_from_inputs(
            business_settings=business_settings,
            location_settings=location_settings,
        ),
        now=shift.starts_at,
    )
    snapshot = snapshots.get(employee.id)
    counted_intervals = snapshot.counted_intervals if snapshot is not None else ()
    overtime_projection = labor_rules.evaluate_overtime_projection(
        profile,
        candidate_shift=shift,
        counted_intervals=counted_intervals,
        reference_time=shift.starts_at,
    )
    work_permit_context = workforce.resolve_employee_work_permit_context(
        employee,
        shift_starts_at=shift.starts_at,
        timezone_name=shift.timezone,
    )
    base_evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=counted_intervals,
        reference_time=shift.starts_at,
        overtime_projection=overtime_projection,
        employee_base_hourly_rate_cents=employee.base_hourly_rate_cents,
        employee_premium_hourly_rate_cents=employee.compliance_regular_rate_cents,
        employee_date_of_birth=employee.date_of_birth,
        employee_minor_school_status=employee.minor_school_status,
        employee_work_permit_number=work_permit_context.get("permit_number"),
        employee_work_permit_effective_start_on=work_permit_context.get("effective_start_on"),
        employee_work_permit_expires_on=work_permit_context.get("expires_on"),
        employee_work_permit_max_daily_minutes=work_permit_context.get("max_daily_minutes"),
        employee_work_permit_max_weekly_minutes=work_permit_context.get("max_weekly_minutes"),
        employee_work_permit_earliest_start_local_time=work_permit_context.get("earliest_start_local_time"),
        employee_work_permit_latest_end_local_time=work_permit_context.get("latest_end_local_time"),
        employee_work_permit_rule_profile=work_permit_context.get("rule_profile"),
        business_settings=business_settings,
        location_settings=location_settings,
    )
    artifacts_by_employee = await compliance_overrides.active_artifacts_for_shift_employees(
        session,
        shift_id=shift.id,
        employee_ids=[employee.id],
        reference_time=shift.starts_at,
    )
    override_artifact = compliance_overrides.matching_override_artifact(
        base_evaluation,
        artifacts_by_employee.get(employee.id, []),
        reference_time=shift.starts_at,
    )
    resolved = compliance_overrides.apply_override_artifact(base_evaluation, override_artifact)
    return _evaluation_metadata_payload(resolved, override_artifact=override_artifact)


def _uuid_or_none(value: object) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


async def total_billed_for_campaign(session: AsyncSession, coverage_case_id: UUID) -> int:
    return await billing_ledger.billed_cents_for_campaign(session, coverage_case_id)


async def location_compliance_week_snapshot(
    session: AsyncSession,
    *,
    location,
    week_start_date: date,
    business_settings_override: Mapping[str, object] | None = None,
    location_settings_override: Mapping[str, object] | None = None,
    force_recompute: bool = False,
) -> LocationComplianceWeekSnapshot:
    window = schedule_week_window(location.timezone, week_start_date)
    result = await session.execute(
        select(Shift)
        .options(
            selectinload(Shift.role),
            selectinload(Shift.assignments).selectinload(ShiftAssignment.employee),
        )
        .where(Shift.location_id == location.id)
        .where(Shift.ends_at >= window.starts_at)
        .where(Shift.starts_at <= window.ends_at)
        .order_by(Shift.starts_at.asc())
    )
    shifts = list(result.scalars().all())

    shift_rows: list[ComplianceWeekShiftRow] = []
    employee_rows: dict[UUID, dict[str, object]] = {}
    premium_rule_codes: set[str] = set()
    warning_rule_codes: set[str] = set()
    unresolved_premium_rule_codes: set[str] = set()
    override_artifact_ids: list[UUID] = []
    warning_assignment_count = 0
    blocked_assignment_count = 0
    unresolved_premium_assignment_count = 0
    premium_total_cents = 0

    for shift in shifts:
        current_assignment = shift_assignments.current_assignment(shift.assignments or [])
        if current_assignment is None or current_assignment.employee_id is None:
            continue
        compliance = await _resolved_assignment_compliance_metadata(
            session,
            shift=shift,
            assignment=current_assignment,
            business_settings_override=business_settings_override,
            location_settings_override=location_settings_override,
            force_recompute=force_recompute,
        )
        status = str(compliance.get("status") or "unresolved").strip().lower() or "unresolved"
        blocking_codes = _normalized_rule_codes(compliance.get("blocking_rule_codes"))
        warning_codes = _normalized_rule_codes(compliance.get("warning_rule_codes"))
        premium_codes = _normalized_rule_codes(compliance.get("premium_rule_codes"))
        unresolved_codes = _normalized_rule_codes(compliance.get("unresolved_premium_rule_codes"))
        override_applied = bool(compliance.get("override_applied"))
        override_artifact_id = _uuid_or_none(compliance.get("override_artifact_id"))
        premium_total = int(compliance.get("premium_total_cents") or 0)

        if status == "warning":
            warning_assignment_count += 1
        elif status == "block":
            blocked_assignment_count += 1
        if unresolved_codes:
            unresolved_premium_assignment_count += 1
        if override_applied and override_artifact_id is not None:
            override_artifact_ids.append(override_artifact_id)

        premium_total_cents += max(0, premium_total)
        premium_rule_codes.update(premium_codes)
        warning_rule_codes.update(warning_codes)
        unresolved_premium_rule_codes.update(unresolved_codes)

        employee_name = _assignment_employee_name(current_assignment)
        shift_rows.append(
            ComplianceWeekShiftRow(
                shift_id=shift.id,
                employee_id=current_assignment.employee_id,
                employee_name=employee_name,
                role_id=shift.role_id,
                role_name=shift.role.name if shift.role is not None else None,
                starts_at=shift.starts_at,
                ends_at=shift.ends_at,
                compliance_status=status,
                profile_code=str(compliance.get("profile_code") or "").strip() or None,
                blocking_rule_codes=blocking_codes,
                warning_rule_codes=warning_codes,
                premium_rule_codes=premium_codes,
                premium_total_cents=max(0, premium_total),
                unresolved_premium_rule_codes=unresolved_codes,
                override_applied=override_applied,
                override_artifact_id=override_artifact_id,
                premium_components=[
                    dict(component)
                    for component in compliance.get("premium_components") or []
                    if isinstance(component, Mapping)
                ],
                rule_source_references=compliance_source_references.rule_source_references_from_evaluation(
                    compliance
                ),
                policy_version_id=_uuid_or_none(compliance.get("policy_version_id")),
                policy_hash=(
                    str(compliance.get("policy_hash") or "").strip() or None
                ),
                policy_effective_at=(
                    datetime.fromisoformat(str(compliance["policy_effective_at"]).replace("Z", "+00:00"))
                    if compliance.get("policy_effective_at") is not None
                    else None
                ),
                policy_scope=(
                    str(compliance.get("policy_scope") or "").strip() or None
                ),
            )
        )

        employee_bucket = employee_rows.setdefault(
            current_assignment.employee_id,
            {
                "employee_id": current_assignment.employee_id,
                "employee_name": employee_name,
                "assignment_count": 0,
                "shift_ids": [],
                "warning_rule_codes": set(),
                "premium_rule_codes": set(),
                "premium_total_cents": 0,
                "unresolved_premium_rule_codes": set(),
                "override_applied_count": 0,
            },
        )
        employee_bucket["assignment_count"] += 1
        employee_bucket["shift_ids"].append(shift.id)
        employee_bucket["warning_rule_codes"].update(warning_codes)
        employee_bucket["premium_rule_codes"].update(premium_codes)
        employee_bucket["premium_total_cents"] += max(0, premium_total)
        employee_bucket["unresolved_premium_rule_codes"].update(unresolved_codes)
        if override_applied:
            employee_bucket["override_applied_count"] += 1

    artifact_lookup: dict[UUID, ComplianceOverrideArtifact] = {}
    if override_artifact_ids:
        artifact_result = await session.execute(
            select(ComplianceOverrideArtifact)
            .options(selectinload(ComplianceOverrideArtifact.employee))
            .where(ComplianceOverrideArtifact.id.in_(sorted(set(override_artifact_ids))))
        )
        artifact_lookup = {
            artifact.id: artifact
            for artifact in artifact_result.scalars().all()
        }

    override_artifacts: list[ComplianceOverrideArtifactSummaryRow] = []
    artifact_type_counts = Counter[str]()
    for artifact_id in sorted(set(override_artifact_ids), key=str):
        artifact = artifact_lookup.get(artifact_id)
        if artifact is None:
            continue
        artifact_type = artifact.artifact_type.value if hasattr(artifact.artifact_type, "value") else str(artifact.artifact_type)
        artifact_type_counts[artifact_type] += 1
        employee_name = getattr(artifact.employee, "full_name", None)
        override_artifacts.append(
            ComplianceOverrideArtifactSummaryRow(
                artifact_id=artifact.id,
                shift_id=artifact.shift_id,
                employee_id=artifact.employee_id,
                employee_name=employee_name.strip() if isinstance(employee_name, str) and employee_name.strip() else None,
                rule_code=artifact.rule_code,
                artifact_type=artifact_type,
                approved_at=artifact.approved_at,
                expires_at=artifact.expires_at,
                note=artifact.note,
            )
        )

    employee_summary_rows = [
        ComplianceWeekEmployeeRow(
            employee_id=employee_id,
            employee_name=bucket["employee_name"],
            assignment_count=int(bucket["assignment_count"]),
            shift_ids=sorted(bucket["shift_ids"], key=str),
            warning_rule_codes=sorted(bucket["warning_rule_codes"]),
            premium_rule_codes=sorted(bucket["premium_rule_codes"]),
            premium_total_cents=int(bucket["premium_total_cents"]),
            unresolved_premium_rule_codes=sorted(bucket["unresolved_premium_rule_codes"]),
            override_applied_count=int(bucket["override_applied_count"]),
        )
        for employee_id, bucket in sorted(
            employee_rows.items(),
            key=lambda item: (
                -(int(item[1]["premium_total_cents"])),
                str(item[1]["employee_name"] or ""),
                str(item[0]),
            ),
        )
    ]

    return LocationComplianceWeekSnapshot(
        location_id=location.id,
        week_start_date=window.week_start,
        week_end_date=window.week_end,
        shift_count=len(shifts),
        assigned_shift_count=len(shift_rows),
        employee_count=len(employee_summary_rows),
        warning_assignment_count=warning_assignment_count,
        blocked_assignment_count=blocked_assignment_count,
        unresolved_premium_assignment_count=unresolved_premium_assignment_count,
        premium_total_cents=premium_total_cents,
        override_applied_count=len({artifact_id for artifact_id in override_artifact_ids}),
        warning_rule_codes=sorted(warning_rule_codes),
        premium_rule_codes=sorted(premium_rule_codes),
        unresolved_premium_rule_codes=sorted(unresolved_premium_rule_codes),
        artifact_type_counts=[
            ComplianceArtifactTypeCountRow(artifact_type=artifact_type, count=count)
            for artifact_type, count in sorted(artifact_type_counts.items())
        ],
        shifts=shift_rows,
        employees=employee_summary_rows,
        override_artifacts=override_artifacts,
    )


async def location_compliance_week_policy_replay(
    session: AsyncSession,
    *,
    location: Location,
    week_start_date: date,
    policy_version_id: UUID,
) -> LocationComplianceWeekReplay:
    version = await _load_compliance_policy_version_for_location(
        session,
        location=location,
        policy_version_id=policy_version_id,
    )
    replay_scope = (
        "location" if str(version.policy_scope).strip().lower() == "location" else "business"
    )
    override_payload = settings_service.compliance_policy_version_settings_payload(version)
    baseline = await location_compliance_week_snapshot(
        session,
        location=location,
        week_start_date=week_start_date,
    )
    replay_kwargs: dict[str, object] = {
        "location": location,
        "week_start_date": week_start_date,
        "force_recompute": True,
    }
    if replay_scope == "business":
        replay_kwargs["business_settings_override"] = override_payload
    else:
        replay_kwargs["location_settings_override"] = override_payload
    replayed = await location_compliance_week_snapshot(
        session,
        **replay_kwargs,
    )
    return LocationComplianceWeekReplay(
        location_id=location.id,
        week_start_date=replayed.week_start_date,
        week_end_date=replayed.week_end_date,
        replay_policy_version_id=version.id,
        replay_policy_scope=replay_scope,
        replay_policy_hash=version.policy_hash,
        replay_policy_effective_at=version.effective_at,
        baseline=baseline,
        replayed=replayed,
        delta=ComplianceTrendDeltaSummary(
            warning_assignment_count_delta=(
                replayed.warning_assignment_count - baseline.warning_assignment_count
            ),
            blocked_assignment_count_delta=(
                replayed.blocked_assignment_count - baseline.blocked_assignment_count
            ),
            unresolved_premium_assignment_count_delta=(
                replayed.unresolved_premium_assignment_count
                - baseline.unresolved_premium_assignment_count
            ),
            override_applied_count_delta=(
                replayed.override_applied_count - baseline.override_applied_count
            ),
            premium_total_cents_delta=(
                replayed.premium_total_cents - baseline.premium_total_cents
            ),
        ),
    )


async def location_compliance_payroll_export(
    session: AsyncSession,
    *,
    location,
    week_start_date: date,
) -> LocationCompliancePayrollExport:
    snapshot = await location_compliance_week_snapshot(
        session,
        location=location,
        week_start_date=week_start_date,
    )
    business = await session.get(Business, location.business_id)
    payroll_settings = _compliance_payroll_export_settings(
        business.settings if business is not None and isinstance(business.settings, Mapping) else None
    )
    artifact_lookup = {
        artifact.artifact_id: artifact
        for artifact in snapshot.override_artifacts
    }
    rows: list[CompliancePayrollAdjustmentRow] = []
    premium_payment_row_count = 0
    ready_adjustment_row_count = 0
    manual_review_row_count = 0
    missing_employee_identifier_row_count = 0
    artifact_record_row_count = 0

    for shift in snapshot.shifts:
        if (
            shift.premium_total_cents <= 0
            and not shift.unresolved_premium_rule_codes
            and not shift.override_applied
        ):
            continue
        employee = await session.get(Employee, shift.employee_id)
        artifact = artifact_lookup.get(shift.override_artifact_id) if shift.override_artifact_id is not None else None
        shift_rows = _build_compliance_payroll_rows_for_shift(
            shift=shift,
            employee=employee,
            artifact=artifact,
            payroll_settings=payroll_settings,
        )
        for row in shift_rows:
            if row.payroll_row_kind == "premium_payment":
                premium_payment_row_count += 1
                ready_adjustment_row_count += 1
            elif row.payroll_row_kind == "manual_review":
                manual_review_row_count += 1
                if any(
                    reason_code in _MISSING_PAYROLL_IDENTIFIER_REASON_CODES
                    for reason_code in row.source_reason_codes
                ):
                    missing_employee_identifier_row_count += 1
            elif row.payroll_row_kind == "artifact_record":
                artifact_record_row_count += 1
        rows.extend(shift_rows)

    rows.sort(
        key=lambda row: (
            0 if row.payroll_row_kind == "premium_payment" else 1 if row.payroll_row_kind == "manual_review" else 2,
            -row.premium_cents,
            -len(row.unresolved_premium_rule_codes),
            str(row.employee_name or ""),
            str(row.shift_id),
        )
    )
    return LocationCompliancePayrollExport(
        location_id=snapshot.location_id,
        week_start_date=snapshot.week_start_date,
        week_end_date=snapshot.week_end_date,
        provider_profile=_payroll_provider_profile(payroll_settings),
        row_count=len(rows),
        premium_payment_row_count=premium_payment_row_count,
        ready_adjustment_row_count=ready_adjustment_row_count,
        manual_review_row_count=manual_review_row_count,
        missing_employee_identifier_row_count=missing_employee_identifier_row_count,
        artifact_record_row_count=artifact_record_row_count,
        total_premium_cents=sum(max(0, row.premium_cents) for row in rows),
        rows=rows,
    )


def _compliance_payroll_export_settings(
    business_settings: Mapping[str, object] | None,
) -> dict[str, object]:
    raw = (
        business_settings.get("compliance_payroll_export")
        if isinstance(business_settings, Mapping)
        else None
    )
    return settings_service.read_compliance_payroll_export_settings(raw).model_dump()


def _payroll_provider_profile(
    payroll_settings: Mapping[str, object],
) -> str:
    return (
        str(payroll_settings.get("provider_profile") or "generic_csv_v1").strip()
        or "generic_csv_v1"
    )


def _employee_identifier_for_payroll(
    employee: Employee | None,
    *,
    employee_id: UUID,
    payroll_settings: Mapping[str, object],
) -> tuple[str | None, str | None]:
    for field_name in payroll_settings.get("employee_identifier_priority") or ():
        if field_name == "employee_number":
            value = str(getattr(employee, "employee_number", "") or "").strip()
            if value:
                return value, "employee_number"
        elif field_name == "external_ref":
            value = str(getattr(employee, "external_ref", "") or "").strip()
            if value:
                return value, "external_ref"
    if bool(payroll_settings.get("allow_internal_employee_id_fallback")):
        return str(employee_id), "employee_id"
    return None, None


def _employee_identifier_candidates(
    employee: Employee | None,
) -> tuple[str | None, str | None]:
    employee_number = (
        str(getattr(employee, "employee_number", "") or "").strip()
        if employee is not None
        else ""
    )
    external_ref = (
        str(getattr(employee, "external_ref", "") or "").strip()
        if employee is not None
        else ""
    )
    return (
        employee_number or None,
        external_ref or None,
    )


def _provider_identifier_readiness(
    *,
    provider_profile: str,
    employee_identifier: str | None,
    employee_number: str | None,
    external_ref: str | None,
) -> tuple[bool, list[str]]:
    if provider_profile == "gusto_csv_v1":
        return (
            employee_number is not None,
            [] if employee_number is not None else ["missing_employee_number"],
        )
    if provider_profile == "quickbooks_csv_v1":
        ready = employee_number is not None or external_ref is not None
        return (
            ready,
            [] if ready else ["missing_quickbooks_employee_reference"],
        )
    if provider_profile == "adp_csv_v1":
        return (
            employee_number is not None,
            [] if employee_number is not None else ["missing_employee_number"],
        )
    return (
        employee_identifier is not None,
        [] if employee_identifier is not None else ["missing_employee_identifier"],
    )


def _payroll_earning_code(
    rule_code: str | None,
    *,
    payroll_settings: Mapping[str, object],
) -> tuple[str, str]:
    normalized_rule_code = str(rule_code or "").strip()
    overrides = payroll_settings.get("earning_codes") if isinstance(payroll_settings.get("earning_codes"), Mapping) else {}
    row = overrides.get(normalized_rule_code) if isinstance(overrides, Mapping) else None
    if isinstance(row, Mapping):
        code = str(row.get("code") or "").strip()
        label = str(row.get("label") or "").strip()
        if code:
            return code, label or _humanize_rule_code(normalized_rule_code)
    default_code = str(payroll_settings.get("default_earning_code") or "COMPLIANCE").strip() or "COMPLIANCE"
    default_label = (
        str(payroll_settings.get("default_earning_label") or "Compliance Premium").strip()
        or "Compliance Premium"
    )
    return default_code, default_label


def _build_compliance_payroll_rows_for_shift(
    *,
    shift: ComplianceWeekShiftRow,
    employee: Employee | None,
    artifact: ComplianceOverrideArtifactSummaryRow | None,
    payroll_settings: Mapping[str, object],
) -> list[CompliancePayrollAdjustmentRow]:
    rows: list[CompliancePayrollAdjustmentRow] = []
    employee_number, external_ref = _employee_identifier_candidates(employee)
    employee_identifier, employee_identifier_type = _employee_identifier_for_payroll(
        employee,
        employee_id=shift.employee_id,
        payroll_settings=payroll_settings,
    )
    provider_profile = _payroll_provider_profile(payroll_settings)
    provider_identifier_ready, provider_missing_reason_codes = _provider_identifier_readiness(
        provider_profile=provider_profile,
        employee_identifier=employee_identifier,
        employee_number=employee_number,
        external_ref=external_ref,
    )
    unresolved_rule_codes_emitted: set[str] = set()

    for component in _normalized_payroll_premium_components(shift):
        rule_code = str(component.get("rule_code") or "").strip() or None
        reason_codes = [
            str(reason_code).strip()
            for reason_code in component.get("reason_codes") or []
            if str(reason_code).strip()
        ]
        premium_cents = max(0, int(component.get("premium_cents") or 0))
        premium_type = str(component.get("premium_type") or "").strip().lower()
        is_ready_payment = (
            premium_type == "fixed_cents"
            and premium_cents > 0
            and provider_identifier_ready
        )
        row_kind = "premium_payment" if is_ready_payment else "manual_review"
        row_status = "ready" if is_ready_payment else "manual_review"
        for missing_reason_code in provider_missing_reason_codes:
            if missing_reason_code not in reason_codes:
                reason_codes.append(missing_reason_code)
        if premium_type == "wage_dependent_unresolved" and rule_code:
            unresolved_rule_codes_emitted.add(rule_code)
        earning_code = None
        earning_label = None
        if premium_type == "fixed_cents" and premium_cents > 0:
            earning_code, earning_label = _payroll_earning_code(
                rule_code,
                payroll_settings=payroll_settings,
            )
        rows.append(
            CompliancePayrollAdjustmentRow(
                shift_id=shift.shift_id,
                employee_id=shift.employee_id,
                employee_name=shift.employee_name,
                role_name=shift.role_name,
                starts_at=shift.starts_at,
                ends_at=shift.ends_at,
                compliance_status=shift.compliance_status,
                profile_code=shift.profile_code,
                premium_cents=premium_cents,
                premium_rate_basis=str(component.get("premium_rate_basis") or "").strip() or None,
                premium_rate_hourly_cents=(
                    max(0, int(component.get("premium_rate_hourly_cents") or 0))
                    if component.get("premium_rate_hourly_cents") is not None
                    else None
                ),
                premium_rule_codes=[rule_code] if rule_code else [],
                unresolved_premium_rule_codes=(
                    [rule_code] if premium_type == "wage_dependent_unresolved" and rule_code else []
                ),
                premium_payment_required=premium_cents > 0,
                manual_review_required=row_kind == "manual_review",
                override_applied=shift.override_applied,
                override_artifact_id=shift.override_artifact_id,
                override_artifact_type=artifact.artifact_type if artifact is not None else None,
                override_artifact_note=artifact.note if artifact is not None else None,
                payroll_row_kind=row_kind,
                payroll_status=row_status,
                employee_number=employee_number,
                external_ref=external_ref,
                employee_identifier=employee_identifier,
                employee_identifier_type=employee_identifier_type,
                earning_code=earning_code,
                earning_label=earning_label,
                source_rule_code=rule_code,
                source_reason_codes=reason_codes,
                rule_source_references=_payroll_row_rule_source_references(
                    shift,
                    rule_codes=[rule_code] if rule_code else [],
                ),
            )
        )

    for rule_code in shift.unresolved_premium_rule_codes:
        if rule_code in unresolved_rule_codes_emitted:
            continue
        reason_codes = ["wage_dependent_premium_unresolved"]
        for missing_reason_code in provider_missing_reason_codes:
            if missing_reason_code not in reason_codes:
                reason_codes.append(missing_reason_code)
        rows.append(
            CompliancePayrollAdjustmentRow(
                shift_id=shift.shift_id,
                employee_id=shift.employee_id,
                employee_name=shift.employee_name,
                role_name=shift.role_name,
                starts_at=shift.starts_at,
                ends_at=shift.ends_at,
                compliance_status=shift.compliance_status,
                profile_code=shift.profile_code,
                premium_cents=0,
                premium_rate_basis="wage_basis_missing",
                premium_rate_hourly_cents=None,
                premium_rule_codes=[],
                unresolved_premium_rule_codes=[rule_code],
                premium_payment_required=False,
                manual_review_required=True,
                override_applied=shift.override_applied,
                override_artifact_id=shift.override_artifact_id,
                override_artifact_type=artifact.artifact_type if artifact is not None else None,
                override_artifact_note=artifact.note if artifact is not None else None,
                payroll_row_kind="manual_review",
                payroll_status="manual_review",
                employee_number=employee_number,
                external_ref=external_ref,
                employee_identifier=employee_identifier,
                employee_identifier_type=employee_identifier_type,
                earning_code=None,
                earning_label=None,
                source_rule_code=rule_code,
                source_reason_codes=reason_codes,
                rule_source_references=_payroll_row_rule_source_references(
                    shift,
                    rule_codes=[rule_code],
                ),
            )
        )

    if shift.override_applied and not rows:
        rows.append(
            CompliancePayrollAdjustmentRow(
                shift_id=shift.shift_id,
                employee_id=shift.employee_id,
                employee_name=shift.employee_name,
                role_name=shift.role_name,
                starts_at=shift.starts_at,
                ends_at=shift.ends_at,
                compliance_status=shift.compliance_status,
                profile_code=shift.profile_code,
                premium_cents=0,
                premium_rate_basis=None,
                premium_rate_hourly_cents=None,
                premium_rule_codes=[],
                unresolved_premium_rule_codes=[],
                premium_payment_required=False,
                manual_review_required=False,
                override_applied=True,
                override_artifact_id=shift.override_artifact_id,
                override_artifact_type=artifact.artifact_type if artifact is not None else None,
                override_artifact_note=artifact.note if artifact is not None else None,
                payroll_row_kind="artifact_record",
                payroll_status="info_only",
                employee_number=employee_number,
                external_ref=external_ref,
                employee_identifier=employee_identifier,
                employee_identifier_type=employee_identifier_type,
                earning_code=None,
                earning_label=None,
                source_rule_code=artifact.rule_code if artifact is not None else None,
                source_reason_codes=["override_artifact_applied"],
                rule_source_references=_payroll_row_rule_source_references(
                    shift,
                    rule_codes=[artifact.rule_code] if artifact is not None and artifact.rule_code else [],
                ),
            )
        )
    return rows


def _normalized_payroll_premium_components(
    shift: ComplianceWeekShiftRow,
) -> list[dict[str, object]]:
    components = [
        dict(component)
        for component in shift.premium_components or []
        if isinstance(component, Mapping) and bool(component.get("premium_type"))
    ]
    if components:
        return components
    if shift.premium_total_cents > 0:
        fallback_rule_code = shift.premium_rule_codes[0] if shift.premium_rule_codes else "compliance_premium"
        return [
            {
                "rule_code": fallback_rule_code,
                "premium_type": "fixed_cents",
                "premium_cents": shift.premium_total_cents,
                "reason_codes": [],
            }
        ]
    return []


def _payroll_row_rule_source_references(
    shift: ComplianceWeekShiftRow,
    *,
    rule_codes: list[str],
) -> list[dict[str, object]]:
    existing = compliance_source_references.filter_rule_source_references(
        shift.rule_source_references,
        rule_codes=rule_codes,
    )
    if existing:
        return existing
    return compliance_source_references.build_rule_source_references(
        rule_codes=rule_codes,
        profile_code=shift.profile_code,
    )


def _humanize_rule_code(value: str | None) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return "Compliance Premium"
    return " ".join(
        part.capitalize()
        for part in normalized.split("_")
        if part
    )


def _top_rule_counts(counter: Counter[str], *, limit: int = 5) -> list[ComplianceTrendRuleCountRow]:
    return [
        ComplianceTrendRuleCountRow(rule_code=rule_code, count=count)
        for rule_code, count in sorted(
            counter.items(),
            key=lambda item: (-item[1], item[0]),
        )[:limit]
    ]


async def location_compliance_trend_snapshot(
    session: AsyncSession,
    *,
    location,
    end_week_start_date: date,
    week_count: int = 6,
    business_settings_override: Mapping[str, object] | None = None,
    location_settings_override: Mapping[str, object] | None = None,
    force_recompute: bool = False,
) -> LocationComplianceTrendSnapshot:
    normalized_week_count = max(1, min(int(week_count or 1), 12))
    start_week_date = end_week_start_date - timedelta(days=7 * (normalized_week_count - 1))
    week_dates = [
        start_week_date + timedelta(days=7 * index)
        for index in range(normalized_week_count)
    ]

    warning_rule_counter: Counter[str] = Counter()
    premium_rule_counter: Counter[str] = Counter()
    unresolved_rule_counter: Counter[str] = Counter()
    total_shift_count = 0
    total_assigned_shift_count = 0
    total_warning_assignment_count = 0
    total_blocked_assignment_count = 0
    total_unresolved_premium_assignment_count = 0
    total_override_applied_count = 0
    total_premium_cents = 0
    weeks: list[ComplianceTrendWeekRow] = []

    for week_start_date in week_dates:
        snapshot_kwargs: dict[str, object] = {
            "location": location,
            "week_start_date": week_start_date,
        }
        if business_settings_override is not None:
            snapshot_kwargs["business_settings_override"] = business_settings_override
        if location_settings_override is not None:
            snapshot_kwargs["location_settings_override"] = location_settings_override
        if force_recompute:
            snapshot_kwargs["force_recompute"] = True
        snapshot = await location_compliance_week_snapshot(
            session,
            **snapshot_kwargs,
        )
        total_shift_count += snapshot.shift_count
        total_assigned_shift_count += snapshot.assigned_shift_count
        total_warning_assignment_count += snapshot.warning_assignment_count
        total_blocked_assignment_count += snapshot.blocked_assignment_count
        total_unresolved_premium_assignment_count += snapshot.unresolved_premium_assignment_count
        total_override_applied_count += snapshot.override_applied_count
        total_premium_cents += snapshot.premium_total_cents
        warning_rule_counter.update(snapshot.warning_rule_codes)
        premium_rule_counter.update(snapshot.premium_rule_codes)
        unresolved_rule_counter.update(snapshot.unresolved_premium_rule_codes)
        weeks.append(
            ComplianceTrendWeekRow(
                week_start_date=snapshot.week_start_date,
                week_end_date=snapshot.week_end_date,
                shift_count=snapshot.shift_count,
                assigned_shift_count=snapshot.assigned_shift_count,
                warning_assignment_count=snapshot.warning_assignment_count,
                blocked_assignment_count=snapshot.blocked_assignment_count,
                unresolved_premium_assignment_count=snapshot.unresolved_premium_assignment_count,
                premium_total_cents=snapshot.premium_total_cents,
                override_applied_count=snapshot.override_applied_count,
            )
        )

    return LocationComplianceTrendSnapshot(
        location_id=location.id,
        start_week_date=start_week_date,
        end_week_date=end_week_start_date,
        week_count=normalized_week_count,
        total_shift_count=total_shift_count,
        total_assigned_shift_count=total_assigned_shift_count,
        total_warning_assignment_count=total_warning_assignment_count,
        total_blocked_assignment_count=total_blocked_assignment_count,
        total_unresolved_premium_assignment_count=total_unresolved_premium_assignment_count,
        total_override_applied_count=total_override_applied_count,
        total_premium_cents=total_premium_cents,
        top_warning_rule_codes=_top_rule_counts(warning_rule_counter),
        top_premium_rule_codes=_top_rule_counts(premium_rule_counter),
        top_unresolved_premium_rule_codes=_top_rule_counts(unresolved_rule_counter),
        weeks=weeks,
    )


async def location_compliance_policy_simulation(
    session: AsyncSession,
    *,
    location,
    end_week_start_date: date,
    week_count: int = 6,
    proposed_location_compliance_settings: Mapping[str, object] | None = None,
) -> LocationCompliancePolicySimulation:
    business = getattr(location, "business", None)
    session_get = getattr(session, "get", None)
    business_id = getattr(location, "business_id", None)
    if business is None and business_id is not None and callable(session_get):
        business = await session_get(Business, business_id)
    if business is not None:
        current_location_context = await settings_service.resolve_location_compliance_policy_context(
            session,
            business=business,
            location=location,
            as_of=datetime.now(timezone.utc),
        )
        baseline_location_settings = current_location_context.settings.model_dump()
        baseline_location_hash = current_location_context.policy_hash
    else:
        baseline_location_settings = settings_service.read_compliance_settings(
            getattr(location, "settings", {}).get("compliance")
            if isinstance(getattr(location, "settings", None), dict)
            else {},
        ).model_dump()
        baseline_location_hash = settings_service.compliance_policy_hash(
            baseline_location_settings
        )
    baseline = await location_compliance_trend_snapshot(
        session,
        location=location,
        end_week_start_date=end_week_start_date,
        week_count=week_count,
    )
    simulated = await location_compliance_trend_snapshot(
        session,
        location=location,
        end_week_start_date=end_week_start_date,
        week_count=week_count,
        location_settings_override=proposed_location_compliance_settings,
        force_recompute=True,
    )
    baseline_weeks = {
        week.week_start_date: week
        for week in baseline.weeks
    }
    week_deltas: list[ComplianceTrendDeltaRow] = []
    for simulated_week in simulated.weeks:
        baseline_week = baseline_weeks.get(simulated_week.week_start_date)
        if baseline_week is None:
            continue
        week_deltas.append(
            ComplianceTrendDeltaRow(
                week_start_date=simulated_week.week_start_date,
                week_end_date=simulated_week.week_end_date,
                warning_assignment_count_delta=(
                    simulated_week.warning_assignment_count - baseline_week.warning_assignment_count
                ),
                blocked_assignment_count_delta=(
                    simulated_week.blocked_assignment_count - baseline_week.blocked_assignment_count
                ),
                unresolved_premium_assignment_count_delta=(
                    simulated_week.unresolved_premium_assignment_count - baseline_week.unresolved_premium_assignment_count
                ),
                override_applied_count_delta=(
                    simulated_week.override_applied_count - baseline_week.override_applied_count
                ),
                premium_total_cents_delta=(
                    simulated_week.premium_total_cents - baseline_week.premium_total_cents
                ),
            )
        )
    return LocationCompliancePolicySimulation(
        location_id=location.id,
        end_week_start_date=end_week_start_date,
        week_count=simulated.week_count,
        baseline_location_compliance_policy_hash=baseline_location_hash,
        baseline_location_compliance_settings=baseline_location_settings,
        proposed_location_compliance_settings=dict(proposed_location_compliance_settings or {}),
        baseline=baseline,
        simulated=simulated,
        delta=ComplianceTrendDeltaSummary(
            warning_assignment_count_delta=(
                simulated.total_warning_assignment_count - baseline.total_warning_assignment_count
            ),
            blocked_assignment_count_delta=(
                simulated.total_blocked_assignment_count - baseline.total_blocked_assignment_count
            ),
            unresolved_premium_assignment_count_delta=(
                simulated.total_unresolved_premium_assignment_count - baseline.total_unresolved_premium_assignment_count
            ),
            override_applied_count_delta=(
                simulated.total_override_applied_count - baseline.total_override_applied_count
            ),
            premium_total_cents_delta=(
                simulated.total_premium_cents - baseline.total_premium_cents
            ),
        ),
        week_deltas=week_deltas,
    )


async def location_compliance_scheduled_policy_drift(
    session: AsyncSession,
    *,
    location: Location,
    start_week_date: date,
    week_count: int = 6,
) -> LocationComplianceScheduledPolicyDrift:
    normalized_week_count = max(1, min(int(week_count or 1), 12))
    end_week_start_date = start_week_date + timedelta(days=7 * (normalized_week_count - 1))
    first_week_window = schedule_week_window(location.timezone, start_week_date)
    reference_time = min(datetime.now(timezone.utc), first_week_window.starts_at)
    business = getattr(location, "business", None)
    session_get = getattr(session, "get", None)
    business_id = getattr(location, "business_id", None)
    if business is None and business_id is not None and callable(session_get):
        business = await session_get(Business, business_id)

    frozen_business_settings = (
        await settings_service.effective_business_settings_payload(
            session,
            business=business,
            as_of=reference_time,
        )
        if business is not None
        else {}
    )
    frozen_location_settings = (
        await settings_service.effective_location_settings_payload(
            session,
            business=business,
            location=location,
            as_of=reference_time,
        )
        if business is not None
        else dict(location.settings or {})
    )
    frozen_current = await location_compliance_trend_snapshot(
        session,
        location=location,
        end_week_start_date=end_week_start_date,
        week_count=normalized_week_count,
        business_settings_override=frozen_business_settings,
        location_settings_override=frozen_location_settings,
        force_recompute=True,
    )
    scheduled = await location_compliance_trend_snapshot(
        session,
        location=location,
        end_week_start_date=end_week_start_date,
        week_count=normalized_week_count,
    )
    frozen_weeks = {week.week_start_date: week for week in frozen_current.weeks}
    week_deltas: list[ComplianceTrendDeltaRow] = []
    for scheduled_week in scheduled.weeks:
        frozen_week = frozen_weeks.get(scheduled_week.week_start_date)
        if frozen_week is None:
            continue
        week_deltas.append(
            ComplianceTrendDeltaRow(
                week_start_date=scheduled_week.week_start_date,
                week_end_date=scheduled_week.week_end_date,
                warning_assignment_count_delta=(
                    scheduled_week.warning_assignment_count - frozen_week.warning_assignment_count
                ),
                blocked_assignment_count_delta=(
                    scheduled_week.blocked_assignment_count - frozen_week.blocked_assignment_count
                ),
                unresolved_premium_assignment_count_delta=(
                    scheduled_week.unresolved_premium_assignment_count
                    - frozen_week.unresolved_premium_assignment_count
                ),
                override_applied_count_delta=(
                    scheduled_week.override_applied_count - frozen_week.override_applied_count
                ),
                premium_total_cents_delta=(
                    scheduled_week.premium_total_cents - frozen_week.premium_total_cents
                ),
            )
        )

    last_week_window = schedule_week_window(location.timezone, end_week_start_date)
    activating_policy_versions = (
        await _scheduled_policy_versions_for_window(
            session,
            business_id=location.business_id,
            location_id=location.id,
            window_end_at=last_week_window.ends_at,
            reference_time=reference_time,
        )
    )

    return LocationComplianceScheduledPolicyDrift(
        location_id=location.id,
        start_week_date=start_week_date,
        end_week_date=end_week_start_date,
        week_count=normalized_week_count,
        activating_policy_versions=activating_policy_versions,
        frozen_current=frozen_current,
        scheduled=scheduled,
        delta=ComplianceTrendDeltaSummary(
            warning_assignment_count_delta=(
                scheduled.total_warning_assignment_count - frozen_current.total_warning_assignment_count
            ),
            blocked_assignment_count_delta=(
                scheduled.total_blocked_assignment_count - frozen_current.total_blocked_assignment_count
            ),
            unresolved_premium_assignment_count_delta=(
                scheduled.total_unresolved_premium_assignment_count
                - frozen_current.total_unresolved_premium_assignment_count
            ),
            override_applied_count_delta=(
                scheduled.total_override_applied_count - frozen_current.total_override_applied_count
            ),
            premium_total_cents_delta=(
                scheduled.total_premium_cents - frozen_current.total_premium_cents
            ),
        ),
        week_deltas=week_deltas,
    )


async def business_compliance_trend_snapshot(
    session: AsyncSession,
    *,
    business: Business,
    end_week_start_date: date,
    week_count: int = 6,
    business_settings_override: Mapping[str, object] | None = None,
    location_settings_overrides_by_id: Mapping[UUID, Mapping[str, object]] | None = None,
    force_recompute: bool = False,
) -> BusinessComplianceTrendSnapshot:
    locations = await _active_business_locations(session, business_id=business.id)
    normalized_week_count = max(1, min(int(week_count or 1), 12))
    start_week_date = end_week_start_date - timedelta(days=7 * (normalized_week_count - 1))
    week_dates = [
        start_week_date + timedelta(days=7 * index)
        for index in range(normalized_week_count)
    ]

    location_buckets: dict[UUID, dict[str, object]] = {
        location.id: {
            "location_id": location.id,
            "location_name": _location_display_name(location),
            "total_shift_count": 0,
            "total_assigned_shift_count": 0,
            "total_warning_assignment_count": 0,
            "total_blocked_assignment_count": 0,
            "total_unresolved_premium_assignment_count": 0,
            "total_override_applied_count": 0,
            "total_premium_cents": 0,
        }
        for location in locations
    }

    warning_rule_counter: Counter[str] = Counter()
    premium_rule_counter: Counter[str] = Counter()
    unresolved_rule_counter: Counter[str] = Counter()
    total_shift_count = 0
    total_assigned_shift_count = 0
    total_warning_assignment_count = 0
    total_blocked_assignment_count = 0
    total_unresolved_premium_assignment_count = 0
    total_override_applied_count = 0
    total_premium_cents = 0
    weeks: list[ComplianceTrendWeekRow] = []

    for week_start_date in week_dates:
        week_shift_count = 0
        week_assigned_shift_count = 0
        week_warning_assignment_count = 0
        week_blocked_assignment_count = 0
        week_unresolved_premium_assignment_count = 0
        week_override_applied_count = 0
        week_premium_total_cents = 0
        for location in locations:
            snapshot_kwargs: dict[str, object] = {
                "location": location,
                "week_start_date": week_start_date,
            }
            if business_settings_override is not None:
                snapshot_kwargs["business_settings_override"] = business_settings_override
            if (
                location_settings_overrides_by_id is not None
                and location.id in location_settings_overrides_by_id
            ):
                snapshot_kwargs["location_settings_override"] = location_settings_overrides_by_id[location.id]
            if force_recompute:
                snapshot_kwargs["force_recompute"] = True
            snapshot = await location_compliance_week_snapshot(
                session,
                **snapshot_kwargs,
            )
            week_shift_count += snapshot.shift_count
            week_assigned_shift_count += snapshot.assigned_shift_count
            week_warning_assignment_count += snapshot.warning_assignment_count
            week_blocked_assignment_count += snapshot.blocked_assignment_count
            week_unresolved_premium_assignment_count += snapshot.unresolved_premium_assignment_count
            week_override_applied_count += snapshot.override_applied_count
            week_premium_total_cents += snapshot.premium_total_cents

            total_shift_count += snapshot.shift_count
            total_assigned_shift_count += snapshot.assigned_shift_count
            total_warning_assignment_count += snapshot.warning_assignment_count
            total_blocked_assignment_count += snapshot.blocked_assignment_count
            total_unresolved_premium_assignment_count += snapshot.unresolved_premium_assignment_count
            total_override_applied_count += snapshot.override_applied_count
            total_premium_cents += snapshot.premium_total_cents
            warning_rule_counter.update(snapshot.warning_rule_codes)
            premium_rule_counter.update(snapshot.premium_rule_codes)
            unresolved_rule_counter.update(snapshot.unresolved_premium_rule_codes)

            bucket = location_buckets[location.id]
            bucket["total_shift_count"] = int(bucket["total_shift_count"]) + snapshot.shift_count
            bucket["total_assigned_shift_count"] = int(bucket["total_assigned_shift_count"]) + snapshot.assigned_shift_count
            bucket["total_warning_assignment_count"] = int(bucket["total_warning_assignment_count"]) + snapshot.warning_assignment_count
            bucket["total_blocked_assignment_count"] = int(bucket["total_blocked_assignment_count"]) + snapshot.blocked_assignment_count
            bucket["total_unresolved_premium_assignment_count"] = (
                int(bucket["total_unresolved_premium_assignment_count"]) + snapshot.unresolved_premium_assignment_count
            )
            bucket["total_override_applied_count"] = int(bucket["total_override_applied_count"]) + snapshot.override_applied_count
            bucket["total_premium_cents"] = int(bucket["total_premium_cents"]) + snapshot.premium_total_cents

        weeks.append(
            ComplianceTrendWeekRow(
                week_start_date=week_start_date,
                week_end_date=week_start_date + timedelta(days=6),
                shift_count=week_shift_count,
                assigned_shift_count=week_assigned_shift_count,
                warning_assignment_count=week_warning_assignment_count,
                blocked_assignment_count=week_blocked_assignment_count,
                unresolved_premium_assignment_count=week_unresolved_premium_assignment_count,
                premium_total_cents=week_premium_total_cents,
                override_applied_count=week_override_applied_count,
            )
        )

    location_rows = [
        BusinessComplianceLocationTrendRow(
            location_id=location_id,
            location_name=str(bucket["location_name"]),
            total_shift_count=int(bucket["total_shift_count"]),
            total_assigned_shift_count=int(bucket["total_assigned_shift_count"]),
            total_warning_assignment_count=int(bucket["total_warning_assignment_count"]),
            total_blocked_assignment_count=int(bucket["total_blocked_assignment_count"]),
            total_unresolved_premium_assignment_count=int(bucket["total_unresolved_premium_assignment_count"]),
            total_override_applied_count=int(bucket["total_override_applied_count"]),
            total_premium_cents=int(bucket["total_premium_cents"]),
        )
        for location_id, bucket in sorted(
            location_buckets.items(),
            key=lambda item: (
                -int(item[1]["total_premium_cents"]),
                -int(item[1]["total_blocked_assignment_count"]),
                str(item[1]["location_name"]),
                str(item[0]),
            ),
        )
    ]

    return BusinessComplianceTrendSnapshot(
        business_id=business.id,
        end_week_start_date=end_week_start_date,
        week_count=normalized_week_count,
        location_count=len(locations),
        total_shift_count=total_shift_count,
        total_assigned_shift_count=total_assigned_shift_count,
        total_warning_assignment_count=total_warning_assignment_count,
        total_blocked_assignment_count=total_blocked_assignment_count,
        total_unresolved_premium_assignment_count=total_unresolved_premium_assignment_count,
        total_override_applied_count=total_override_applied_count,
        total_premium_cents=total_premium_cents,
        top_warning_rule_codes=_top_rule_counts(warning_rule_counter),
        top_premium_rule_codes=_top_rule_counts(premium_rule_counter),
        top_unresolved_premium_rule_codes=_top_rule_counts(unresolved_rule_counter),
        weeks=weeks,
        locations=location_rows,
    )


async def business_compliance_policy_simulation(
    session: AsyncSession,
    *,
    business: Business,
    end_week_start_date: date,
    week_count: int = 6,
    proposed_business_compliance_settings: Mapping[str, object] | None = None,
) -> BusinessCompliancePolicySimulation:
    current_business_context = await settings_service.resolve_business_compliance_policy_context(
        session,
        business=business,
        as_of=datetime.now(timezone.utc),
    )
    baseline = await business_compliance_trend_snapshot(
        session,
        business=business,
        end_week_start_date=end_week_start_date,
        week_count=week_count,
    )
    simulated = await business_compliance_trend_snapshot(
        session,
        business=business,
        end_week_start_date=end_week_start_date,
        week_count=week_count,
        business_settings_override=proposed_business_compliance_settings,
        force_recompute=True,
    )
    baseline_weeks = {
        week.week_start_date: week
        for week in baseline.weeks
    }
    baseline_locations = {
        row.location_id: row
        for row in baseline.locations
    }
    week_deltas: list[ComplianceTrendDeltaRow] = []
    for simulated_week in simulated.weeks:
        baseline_week = baseline_weeks.get(simulated_week.week_start_date)
        if baseline_week is None:
            continue
        week_deltas.append(
            ComplianceTrendDeltaRow(
                week_start_date=simulated_week.week_start_date,
                week_end_date=simulated_week.week_end_date,
                warning_assignment_count_delta=(
                    simulated_week.warning_assignment_count - baseline_week.warning_assignment_count
                ),
                blocked_assignment_count_delta=(
                    simulated_week.blocked_assignment_count - baseline_week.blocked_assignment_count
                ),
                unresolved_premium_assignment_count_delta=(
                    simulated_week.unresolved_premium_assignment_count - baseline_week.unresolved_premium_assignment_count
                ),
                override_applied_count_delta=(
                    simulated_week.override_applied_count - baseline_week.override_applied_count
                ),
                premium_total_cents_delta=(
                    simulated_week.premium_total_cents - baseline_week.premium_total_cents
                ),
            )
        )

    location_deltas: list[BusinessComplianceLocationDeltaRow] = []
    for simulated_location in simulated.locations:
        baseline_location = baseline_locations.get(simulated_location.location_id)
        if baseline_location is None:
            continue
        location_deltas.append(
            BusinessComplianceLocationDeltaRow(
                location_id=simulated_location.location_id,
                location_name=simulated_location.location_name,
                warning_assignment_count_delta=(
                    simulated_location.total_warning_assignment_count
                    - baseline_location.total_warning_assignment_count
                ),
                blocked_assignment_count_delta=(
                    simulated_location.total_blocked_assignment_count
                    - baseline_location.total_blocked_assignment_count
                ),
                unresolved_premium_assignment_count_delta=(
                    simulated_location.total_unresolved_premium_assignment_count
                    - baseline_location.total_unresolved_premium_assignment_count
                ),
                override_applied_count_delta=(
                    simulated_location.total_override_applied_count
                    - baseline_location.total_override_applied_count
                ),
                premium_total_cents_delta=(
                    simulated_location.total_premium_cents
                    - baseline_location.total_premium_cents
                ),
            )
        )

    location_deltas.sort(
        key=lambda row: (
            -abs(row.premium_total_cents_delta),
            -abs(row.blocked_assignment_count_delta),
            row.location_name,
            str(row.location_id),
        )
    )

    return BusinessCompliancePolicySimulation(
        business_id=business.id,
        end_week_start_date=end_week_start_date,
        week_count=simulated.week_count,
        location_count=simulated.location_count,
        baseline_business_compliance_policy_hash=(
            current_business_context.policy_hash
            if current_business_context is not None
            else settings_service.compliance_policy_hash(
                settings_service.read_compliance_settings(
                    business.settings.get("compliance")
                    if isinstance(business.settings, dict)
                    else {}
                ).model_dump()
            )
        ),
        baseline_business_compliance_settings=(
            current_business_context.settings.model_dump()
            if current_business_context is not None
            else settings_service.read_compliance_settings(
                business.settings.get("compliance")
                if isinstance(business.settings, dict)
                else {}
            ).model_dump()
        ),
        proposed_business_compliance_settings=dict(proposed_business_compliance_settings or {}),
        baseline=baseline,
        simulated=simulated,
        delta=ComplianceTrendDeltaSummary(
            warning_assignment_count_delta=(
                simulated.total_warning_assignment_count - baseline.total_warning_assignment_count
            ),
            blocked_assignment_count_delta=(
                simulated.total_blocked_assignment_count - baseline.total_blocked_assignment_count
            ),
            unresolved_premium_assignment_count_delta=(
                simulated.total_unresolved_premium_assignment_count
                - baseline.total_unresolved_premium_assignment_count
            ),
            override_applied_count_delta=(
                simulated.total_override_applied_count - baseline.total_override_applied_count
            ),
            premium_total_cents_delta=(
                simulated.total_premium_cents - baseline.total_premium_cents
            ),
        ),
        week_deltas=week_deltas,
        location_deltas=location_deltas,
    )


async def business_compliance_scheduled_policy_drift(
    session: AsyncSession,
    *,
    business: Business,
    start_week_date: date,
    week_count: int = 6,
) -> BusinessComplianceScheduledPolicyDrift:
    normalized_week_count = max(1, min(int(week_count or 1), 12))
    end_week_start_date = start_week_date + timedelta(days=7 * (normalized_week_count - 1))
    first_week_window = schedule_week_window(business.timezone, start_week_date)
    reference_time = min(datetime.now(timezone.utc), first_week_window.starts_at)
    locations = await _active_business_locations(session, business_id=business.id)
    frozen_business_settings = await settings_service.effective_business_settings_payload(
        session,
        business=business,
        as_of=reference_time,
    )
    frozen_location_settings_by_id: dict[UUID, Mapping[str, object]] = {}
    for location in locations:
        frozen_location_settings_by_id[location.id] = await settings_service.effective_location_settings_payload(
            session,
            business=business,
            location=location,
            as_of=reference_time,
        )

    frozen_current = await business_compliance_trend_snapshot(
        session,
        business=business,
        end_week_start_date=end_week_start_date,
        week_count=normalized_week_count,
        business_settings_override=frozen_business_settings,
        location_settings_overrides_by_id=frozen_location_settings_by_id,
        force_recompute=True,
    )
    scheduled = await business_compliance_trend_snapshot(
        session,
        business=business,
        end_week_start_date=end_week_start_date,
        week_count=normalized_week_count,
    )

    frozen_weeks = {week.week_start_date: week for week in frozen_current.weeks}
    week_deltas: list[ComplianceTrendDeltaRow] = []
    for scheduled_week in scheduled.weeks:
        frozen_week = frozen_weeks.get(scheduled_week.week_start_date)
        if frozen_week is None:
            continue
        week_deltas.append(
            ComplianceTrendDeltaRow(
                week_start_date=scheduled_week.week_start_date,
                week_end_date=scheduled_week.week_end_date,
                warning_assignment_count_delta=(
                    scheduled_week.warning_assignment_count - frozen_week.warning_assignment_count
                ),
                blocked_assignment_count_delta=(
                    scheduled_week.blocked_assignment_count - frozen_week.blocked_assignment_count
                ),
                unresolved_premium_assignment_count_delta=(
                    scheduled_week.unresolved_premium_assignment_count
                    - frozen_week.unresolved_premium_assignment_count
                ),
                override_applied_count_delta=(
                    scheduled_week.override_applied_count - frozen_week.override_applied_count
                ),
                premium_total_cents_delta=(
                    scheduled_week.premium_total_cents - frozen_week.premium_total_cents
                ),
            )
        )

    frozen_locations = {row.location_id: row for row in frozen_current.locations}
    location_deltas: list[BusinessComplianceLocationDeltaRow] = []
    for scheduled_location in scheduled.locations:
        frozen_location = frozen_locations.get(scheduled_location.location_id)
        if frozen_location is None:
            continue
        location_deltas.append(
            BusinessComplianceLocationDeltaRow(
                location_id=scheduled_location.location_id,
                location_name=scheduled_location.location_name,
                warning_assignment_count_delta=(
                    scheduled_location.total_warning_assignment_count
                    - frozen_location.total_warning_assignment_count
                ),
                blocked_assignment_count_delta=(
                    scheduled_location.total_blocked_assignment_count
                    - frozen_location.total_blocked_assignment_count
                ),
                unresolved_premium_assignment_count_delta=(
                    scheduled_location.total_unresolved_premium_assignment_count
                    - frozen_location.total_unresolved_premium_assignment_count
                ),
                override_applied_count_delta=(
                    scheduled_location.total_override_applied_count
                    - frozen_location.total_override_applied_count
                ),
                premium_total_cents_delta=(
                    scheduled_location.total_premium_cents
                    - frozen_location.total_premium_cents
                ),
            )
        )
    location_deltas.sort(
        key=lambda row: (
            -abs(row.premium_total_cents_delta),
            -abs(row.blocked_assignment_count_delta),
            row.location_name,
            str(row.location_id),
        )
    )

    latest_window_end_at = schedule_week_window(business.timezone, end_week_start_date).ends_at
    activating_policy_versions = await _scheduled_policy_versions_for_window(
        session,
        business_id=business.id,
        window_end_at=latest_window_end_at,
        reference_time=reference_time,
    )

    return BusinessComplianceScheduledPolicyDrift(
        business_id=business.id,
        start_week_date=start_week_date,
        end_week_date=end_week_start_date,
        week_count=normalized_week_count,
        location_count=scheduled.location_count,
        activating_policy_versions=activating_policy_versions,
        frozen_current=frozen_current,
        scheduled=scheduled,
        delta=ComplianceTrendDeltaSummary(
            warning_assignment_count_delta=(
                scheduled.total_warning_assignment_count - frozen_current.total_warning_assignment_count
            ),
            blocked_assignment_count_delta=(
                scheduled.total_blocked_assignment_count - frozen_current.total_blocked_assignment_count
            ),
            unresolved_premium_assignment_count_delta=(
                scheduled.total_unresolved_premium_assignment_count
                - frozen_current.total_unresolved_premium_assignment_count
            ),
            override_applied_count_delta=(
                scheduled.total_override_applied_count - frozen_current.total_override_applied_count
            ),
            premium_total_cents_delta=(
                scheduled.total_premium_cents - frozen_current.total_premium_cents
            ),
        ),
        week_deltas=week_deltas,
        location_deltas=location_deltas,
    )


async def _count_cost_entries(session: AsyncSession, coverage_case_id: UUID) -> int:
    total = await session.scalar(
        select(func.count()).select_from(CostLedgerEntry).where(
            CostLedgerEntry.coverage_case_id == coverage_case_id
        )
    )
    return int(total or 0)


async def _count_billing_entries(session: AsyncSession, coverage_case_id: UUID) -> int:
    total = await session.scalar(
        select(func.count()).select_from(BillingLedgerEntry).where(
            BillingLedgerEntry.coverage_case_id == coverage_case_id
        )
    )
    return int(total or 0)


async def campaign_cost_breakdown(
    session: AsyncSession,
    coverage_case_id: UUID,
) -> list[CampaignCostBreakdownRow]:
    result = await session.execute(
        select(
            CostLedgerEntry.provider,
            CostLedgerEntry.product,
            func.coalesce(func.sum(CostLedgerEntry.total_cost_micros), 0),
        )
        .where(CostLedgerEntry.coverage_case_id == coverage_case_id)
        .group_by(CostLedgerEntry.provider, CostLedgerEntry.product)
        .order_by(CostLedgerEntry.provider.asc(), CostLedgerEntry.product.asc())
    )
    rows = result.all()
    breakdown: list[CampaignCostBreakdownRow] = []
    for provider, product, total_cost_micros in rows:
        normalized_total = int(total_cost_micros or 0)
        breakdown.append(
            CampaignCostBreakdownRow(
                provider=provider,
                product=product,
                total_cost_micros=normalized_total,
                total_cost_cents_rounded=micros_to_cents_rounded(normalized_total),
            )
        )
    return breakdown


async def campaign_economics_snapshot(
    session: AsyncSession,
    coverage_case_id: UUID,
) -> CampaignEconomicsSnapshot:
    total_cost_micros = await cost_ledger.total_cost_for_campaign(session, coverage_case_id)
    total_billed_cents = await total_billed_for_campaign(session, coverage_case_id)
    total_billed_micros = cents_to_micros(total_billed_cents)
    gross_margin_micros = total_billed_micros - total_cost_micros
    cost_entry_count = await _count_cost_entries(session, coverage_case_id)
    billed_entry_count = await _count_billing_entries(session, coverage_case_id)
    return CampaignEconomicsSnapshot(
        coverage_case_id=coverage_case_id,
        total_cost_micros=total_cost_micros,
        total_cost_cents_rounded=micros_to_cents_rounded(total_cost_micros),
        total_billed_cents=total_billed_cents,
        total_billed_micros=total_billed_micros,
        gross_margin_micros=gross_margin_micros,
        gross_margin_cents_rounded=micros_to_cents_rounded(gross_margin_micros),
        billed_entry_count=billed_entry_count,
        cost_entry_count=cost_entry_count,
    )


async def location_billing_cap_snapshot(
    session: AsyncSession,
    *,
    location_id: UUID,
    occurred_at,
    timezone_name: str,
    fill_price_cents: int | None = None,
    monthly_cap_cents: int | None = None,
) -> LocationBillingCapSnapshot:
    decision = await billing_ledger.evaluate_fill_charge(
        session,
        location_id=location_id,
        occurred_at=occurred_at,
        timezone_name=timezone_name,
        fill_price_cents=fill_price_cents,
        monthly_cap_cents=monthly_cap_cents,
    )
    remaining_cents = max(0, decision.monthly_cap_cents - decision.billed_cents_before)
    return LocationBillingCapSnapshot(
        location_id=location_id,
        billing_cycle_start=decision.billing_cycle_start,
        billed_cents=decision.billed_cents_before,
        remaining_cents=remaining_cents,
        monthly_cap_cents=decision.monthly_cap_cents,
        fill_price_cents=decision.fill_price_cents,
        next_fill_charge_cents=decision.amount_cents,
        is_capped=decision.amount_cents == 0,
    )


async def list_cost_entries(
    session: AsyncSession,
    *,
    coverage_case_id: UUID,
    limit: int = 50,
) -> list[CostLedgerEntry]:
    result = await session.execute(
        select(CostLedgerEntry)
        .where(CostLedgerEntry.coverage_case_id == coverage_case_id)
        .order_by(CostLedgerEntry.occurred_at.desc(), CostLedgerEntry.created_at.desc())
        .limit(max(1, min(limit, 250)))
    )
    return list(result.scalars().all())


async def list_billing_entries(
    session: AsyncSession,
    *,
    coverage_case_id: UUID,
    limit: int = 50,
) -> list[BillingLedgerEntry]:
    result = await session.execute(
        select(BillingLedgerEntry)
        .where(BillingLedgerEntry.coverage_case_id == coverage_case_id)
        .order_by(BillingLedgerEntry.occurred_at.desc(), BillingLedgerEntry.created_at.desc())
        .limit(max(1, min(limit, 250)))
    )
    return list(result.scalars().all())
