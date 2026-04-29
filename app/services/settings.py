from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Business, Location
from app.models.compliance import CompliancePolicyVersion
from app.schemas.settings import (
    BusinessShiftDefaultsRead,
    BusinessShiftDefaultsUpdate,
    CompliancePayrollExportSettingsRead,
    CompliancePayrollExportSettingsUpdate,
    CompliancePolicyVersionRead,
    CompliancePolicySettingsRead,
    LocationSettingsRead,
    LocationSettingsUpdate,
    LocationShiftDefaultsRead,
    LocationShiftDefaultsUpdate,
    ShiftPresetRead,
)
from app.services import businesses, labor_rule_resolution
from app.services import shift_defaults as shift_defaults_service


DEFAULT_LOCATION_SETTINGS = {
    "coverage_requires_manager_approval": False,
    "late_arrival_policy": "wait",
    "missed_check_in_policy": "manager_action",
    "agency_supply_approved": False,
    "writeback_enabled": False,
    "scheduling_platform": "backfill_native",
    "integration_status": None,
    "backfill_shifts_enabled": False,
    "backfill_shifts_launch_state": "off",
    "backfill_shifts_beta_eligible": False,
    "week_start_day": None,
}

_EMPTY_COMPLIANCE_POLICY = CompliancePolicySettingsRead()
_WEEKDAY_ORDER = {
    "sunday": 0,
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
}
_DEFAULT_COMPLIANCE_PAYROLL_IDENTIFIER_PRIORITY = ("employee_number", "external_ref")
_DEFAULT_COMPLIANCE_PAYROLL_EARNING_CODES = {
    "meal_break_first_window": ("MEALPREM", "Meal Break Premium"),
    "meal_break_second_window": ("MEALPREM", "Meal Break Premium"),
    "paid_rest_break_quota": ("RESTPREM", "Rest Break Premium"),
    "split_shift_premium": ("SPLITPREM", "Split Shift Premium"),
    "spread_of_hours_premium": ("SPREADPREM", "Spread of Hours Premium"),
    "minimum_rest_window": ("RESTGAPPREM", "Reduced Rest Window Premium"),
    "clopening_restricted": ("RESTGAPPREM", "Reduced Rest Window Premium"),
    "overtime_projection": ("OVERTIME", "Projected Overtime"),
}


class CompliancePolicyPreviewStaleError(Exception):
    def __init__(
        self,
        *,
        current_compliance_policy_hash: str,
        current_compliance_settings: CompliancePolicySettingsRead,
    ) -> None:
        super().__init__("location_compliance_policy_preview_stale")
        self.current_compliance_policy_hash = current_compliance_policy_hash
        self.current_compliance_settings = current_compliance_settings


@dataclass(frozen=True)
class ResolvedCompliancePolicyContext:
    policy_scope: Literal["business", "location"]
    settings: CompliancePolicySettingsRead
    policy_hash: str
    version_id: UUID | None = None
    effective_at: datetime | None = None
    clears_parent: bool = False
    source: Literal["versioned", "legacy", "none"] = "none"

    @property
    def is_explicit(self) -> bool:
        return self.source != "none"


def _normalized_school_day_weekdays(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    weekdays = {
        str(item or "").strip().lower()
        for item in value
        if str(item or "").strip().lower() in _WEEKDAY_ORDER
    }
    return sorted(weekdays, key=lambda item: _WEEKDAY_ORDER[item])


def _normalized_policy_dates(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized_dates: set[str] = set()
    for item in value:
        raw = str(item or "").strip()
        if not raw:
            continue
        try:
            normalized_dates.add(date.fromisoformat(raw).isoformat())
        except ValueError:
            continue
    return sorted(normalized_dates)


def _read_compliance_settings(payload: object) -> CompliancePolicySettingsRead:
    raw = dict(payload) if isinstance(payload, dict) else {}
    return CompliancePolicySettingsRead(
        minimum_rest_hours=(
            float(raw["minimum_rest_hours"])
            if raw.get("minimum_rest_hours") is not None
            else None
        ),
        written_consent_allowed=(
            bool(raw["written_consent_allowed"])
            if raw.get("written_consent_allowed") is not None
            else None
        ),
        first_meal_waiver_allowed=(
            bool(raw["first_meal_waiver_allowed"])
            if raw.get("first_meal_waiver_allowed") is not None
            else None
        ),
        second_meal_waiver_allowed=(
            bool(raw["second_meal_waiver_allowed"])
            if raw.get("second_meal_waiver_allowed") is not None
            else None
        ),
        require_structured_break_plans=bool(raw.get("require_structured_break_plans")),
        block_unresolved_premiums=bool(raw.get("block_unresolved_premiums")),
        max_daily_minutes=(
            int(raw["max_daily_minutes"])
            if raw.get("max_daily_minutes") is not None
            else None
        ),
        max_weekly_minutes=(
            int(raw["max_weekly_minutes"])
            if raw.get("max_weekly_minutes") is not None
            else None
        ),
        school_day_weekdays=_normalized_school_day_weekdays(
            raw.get("school_day_weekdays")
        ),
        school_dates=_normalized_policy_dates(raw.get("school_dates")),
        non_school_dates=_normalized_policy_dates(raw.get("non_school_dates")),
    )


def _humanize_rule_code(rule_code: str) -> str:
    return str(rule_code or "").replace("_", " ").strip().title() or "Compliance Premium"


def _read_compliance_payroll_export_settings(
    payload: object,
) -> CompliancePayrollExportSettingsRead:
    raw = dict(payload) if isinstance(payload, dict) else {}
    priority: list[str] = []
    for value in raw.get("employee_identifier_priority") or _DEFAULT_COMPLIANCE_PAYROLL_IDENTIFIER_PRIORITY:
        normalized = str(value or "").strip()
        if normalized in {"employee_number", "external_ref"} and normalized not in priority:
            priority.append(normalized)
    if not priority:
        priority = list(_DEFAULT_COMPLIANCE_PAYROLL_IDENTIFIER_PRIORITY)

    earning_codes: dict[str, object] = {}
    merged_defaults = {
        rule_code: {"code": code, "label": label}
        for rule_code, (code, label) in _DEFAULT_COMPLIANCE_PAYROLL_EARNING_CODES.items()
    }
    raw_earning_codes = raw.get("earning_codes")
    if isinstance(raw_earning_codes, dict):
        for rule_code, raw_value in raw_earning_codes.items():
            normalized_rule_code = str(rule_code or "").strip()
            if not normalized_rule_code:
                continue
            code = ""
            label = ""
            if isinstance(raw_value, dict):
                code = str(raw_value.get("code") or "").strip()
                label = str(raw_value.get("label") or "").strip()
            else:
                code = str(raw_value or "").strip()
            if not code:
                continue
            merged_defaults[normalized_rule_code] = {
                "code": code,
                "label": label or _humanize_rule_code(normalized_rule_code),
            }
    for rule_code, config in merged_defaults.items():
        if isinstance(config, dict):
            earning_codes[rule_code] = config

    return CompliancePayrollExportSettingsRead(
        employee_identifier_priority=priority,
        allow_internal_employee_id_fallback=bool(
            raw.get("allow_internal_employee_id_fallback")
        ),
        default_earning_code=(
            str(raw.get("default_earning_code") or "COMPLIANCE").strip()
            or "COMPLIANCE"
        ),
        default_earning_label=(
            str(raw.get("default_earning_label") or "Compliance Premium").strip()
            or "Compliance Premium"
        ),
        earning_codes=earning_codes,
    )


def read_compliance_settings(payload: object) -> CompliancePolicySettingsRead:
    return _read_compliance_settings(payload)


def read_compliance_payroll_export_settings(
    payload: object,
) -> CompliancePayrollExportSettingsRead:
    return _read_compliance_payroll_export_settings(payload)


def compliance_policy_hash(payload: object) -> str:
    normalized = _read_compliance_settings(payload).model_dump(mode="json")
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def has_nonempty_compliance_policy(payload: object) -> bool:
    return _read_compliance_settings(payload).model_dump() != _EMPTY_COMPLIANCE_POLICY.model_dump()


def merge_compliance_payroll_export_update(
    current_payload: object,
    update: CompliancePayrollExportSettingsUpdate,
) -> dict[str, object]:
    current_settings = _read_compliance_payroll_export_settings(current_payload).model_dump()
    updates = update.model_dump(exclude_unset=True)

    if "employee_identifier_priority" in updates and updates["employee_identifier_priority"] is not None:
        current_settings["employee_identifier_priority"] = list(
            updates["employee_identifier_priority"]
        )
    if "allow_internal_employee_id_fallback" in updates:
        current_settings["allow_internal_employee_id_fallback"] = bool(
            updates["allow_internal_employee_id_fallback"]
        )
    if "default_earning_code" in updates and updates["default_earning_code"] is not None:
        current_settings["default_earning_code"] = str(
            updates["default_earning_code"]
        ).strip()
    if "default_earning_label" in updates and updates["default_earning_label"] is not None:
        current_settings["default_earning_label"] = str(
            updates["default_earning_label"]
        ).strip()
    if "earning_codes" in updates and updates["earning_codes"] is not None:
        next_earning_codes = dict(current_settings.get("earning_codes") or {})
        for rule_code, raw_value in updates["earning_codes"].items():
            normalized_rule_code = str(rule_code or "").strip()
            if not normalized_rule_code:
                continue
            if raw_value is None:
                next_earning_codes.pop(normalized_rule_code, None)
                continue
            value = (
                raw_value.model_dump(exclude_unset=True)
                if hasattr(raw_value, "model_dump")
                else dict(raw_value)
                if isinstance(raw_value, dict)
                else {}
            )
            code = str(value.get("code") or "").strip()
            label = str(value.get("label") or "").strip()
            if not code:
                next_earning_codes.pop(normalized_rule_code, None)
                continue
            next_earning_codes[normalized_rule_code] = {
                "code": code,
                "label": label or _humanize_rule_code(normalized_rule_code),
            }
        current_settings["earning_codes"] = next_earning_codes

    return _read_compliance_payroll_export_settings(current_settings).model_dump()


def _optional_uuid(value: object) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


def _parse_datetime_value(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _coerce_policy_version(value: object) -> CompliancePolicyVersion | None:
    return value if isinstance(value, CompliancePolicyVersion) else None


def _shift_preset_reads(presets: list[dict[str, object]]) -> list[ShiftPresetRead]:
    return [
        ShiftPresetRead(
            key=str(item["key"]),
            label=str(item["label"]),
            start_hour=int(item["start_hour"]),
            end_hour=int(item["end_hour"]),
        )
        for item in presets
    ]


def _read_location_settings_payload(
    *,
    location: Location,
    payload: dict[str, object],
) -> LocationSettingsRead:
    return LocationSettingsRead(
        location_id=location.id,
        coverage_requires_manager_approval=bool(payload["coverage_requires_manager_approval"]),
        late_arrival_policy=str(payload["late_arrival_policy"]),
        missed_check_in_policy=str(payload["missed_check_in_policy"]),
        agency_supply_approved=bool(payload["agency_supply_approved"]),
        writeback_enabled=bool(payload["writeback_enabled"]),
        timezone=location.timezone,
        scheduling_platform=(
            str(payload["scheduling_platform"])
            if payload.get("scheduling_platform") is not None
            else None
        ),
        integration_status=(
            str(payload["integration_status"])
            if payload.get("integration_status") is not None
            else None
        ),
        backfill_shifts_enabled=bool(payload["backfill_shifts_enabled"]),
        backfill_shifts_launch_state=str(payload["backfill_shifts_launch_state"]),
        backfill_shifts_beta_eligible=bool(payload["backfill_shifts_beta_eligible"]),
        week_start_day=(
            str(payload["week_start_day"])
            if payload.get("week_start_day") is not None
            else None
        ),
        compliance=_read_compliance_settings(payload.get("compliance")),
        compliance_policy_version_id=_optional_uuid(payload.get("compliance_policy_version_id")),
        compliance_policy_hash=(
            str(payload["compliance_policy_hash"])
            if payload.get("compliance_policy_hash") is not None
            else None
        ),
        compliance_policy_effective_at=_parse_datetime_value(
            payload.get("compliance_policy_effective_at")
        ),
        compliance_policy_scope=(
            str(payload["compliance_policy_scope"])
            if payload.get("compliance_policy_scope") in {"business", "location"}
            else None
        ),
        compliance_policy_clears_parent=bool(payload.get("compliance_policy_clears_parent")),
    )


def _read_location_settings(location: Location) -> LocationSettingsRead:
    payload = {**DEFAULT_LOCATION_SETTINGS, **(location.settings or {})}
    return _read_location_settings_payload(location=location, payload=payload)


def _context_to_settings_payload(
    base_settings: dict[str, object],
    *,
    context: ResolvedCompliancePolicyContext | None,
) -> dict[str, object]:
    next_settings = dict(base_settings)
    next_settings.pop("compliance_policy_version_id", None)
    next_settings.pop("compliance_policy_hash", None)
    next_settings.pop("compliance_policy_effective_at", None)
    next_settings.pop("compliance_policy_scope", None)
    next_settings.pop("compliance_policy_clears_parent", None)
    if context is None or not context.is_explicit:
        next_settings.pop("compliance", None)
        return next_settings

    if has_nonempty_compliance_policy(context.settings.model_dump()):
        next_settings["compliance"] = context.settings.model_dump()
    else:
        next_settings.pop("compliance", None)
    next_settings["compliance_policy_hash"] = context.policy_hash
    next_settings["compliance_policy_scope"] = context.policy_scope
    next_settings["compliance_policy_clears_parent"] = context.clears_parent
    if context.version_id is not None:
        next_settings["compliance_policy_version_id"] = str(context.version_id)
    else:
        next_settings.pop("compliance_policy_version_id", None)
    if context.effective_at is not None:
        next_settings["compliance_policy_effective_at"] = context.effective_at.isoformat()
    else:
        next_settings.pop("compliance_policy_effective_at", None)
    return next_settings


def apply_compliance_policy_context_to_settings(
    base_settings: dict[str, object],
    *,
    context: ResolvedCompliancePolicyContext | None,
) -> dict[str, object]:
    return _context_to_settings_payload(base_settings, context=context)


def _effective_location_policy_context(
    *,
    business_context: ResolvedCompliancePolicyContext | None,
    location_context: ResolvedCompliancePolicyContext | None,
) -> ResolvedCompliancePolicyContext | None:
    if location_context is not None and location_context.is_explicit:
        return location_context
    return business_context


async def _effective_policy_version(
    session: AsyncSession,
    *,
    business_id: UUID,
    policy_scope: Literal["business", "location"],
    as_of: datetime,
    location_id: UUID | None = None,
) -> CompliancePolicyVersion | None:
    stmt = (
        select(CompliancePolicyVersion)
        .where(CompliancePolicyVersion.business_id == business_id)
        .where(CompliancePolicyVersion.policy_scope == policy_scope)
        .where(CompliancePolicyVersion.effective_at <= as_of)
        .where(
            CompliancePolicyVersion.superseded_at.is_(None)
            | (CompliancePolicyVersion.superseded_at > as_of)
        )
        .order_by(
            CompliancePolicyVersion.effective_at.desc(),
            CompliancePolicyVersion.created_at.desc(),
        )
        .limit(1)
    )
    if policy_scope == "location":
        stmt = stmt.where(CompliancePolicyVersion.location_id == location_id)
    else:
        stmt = stmt.where(CompliancePolicyVersion.location_id.is_(None))
    return _coerce_policy_version(await session.scalar(stmt))


def _context_from_version(
    version: CompliancePolicyVersion,
) -> ResolvedCompliancePolicyContext:
    settings = _read_compliance_settings(version.settings_payload)
    return ResolvedCompliancePolicyContext(
        policy_scope=(
            "location" if str(version.policy_scope).strip().lower() == "location" else "business"
        ),
        settings=settings,
        policy_hash=version.policy_hash,
        version_id=version.id,
        effective_at=version.effective_at,
        clears_parent=not has_nonempty_compliance_policy(settings.model_dump()),
        source="versioned",
    )


def _legacy_context(
    *,
    policy_scope: Literal["business", "location"],
    payload: object,
) -> ResolvedCompliancePolicyContext | None:
    if not has_nonempty_compliance_policy(payload):
        return None
    settings = _read_compliance_settings(payload)
    return ResolvedCompliancePolicyContext(
        policy_scope=policy_scope,
        settings=settings,
        policy_hash=compliance_policy_hash(settings.model_dump()),
        version_id=None,
        effective_at=None,
        clears_parent=False,
        source="legacy",
    )


def _stored_context(
    *,
    policy_scope: Literal["business", "location"],
    settings_payload: object,
) -> ResolvedCompliancePolicyContext | None:
    raw_settings = dict(settings_payload) if isinstance(settings_payload, dict) else {}
    compliance_payload = raw_settings.get("compliance")
    stored_hash = (
        str(raw_settings.get("compliance_policy_hash")).strip()
        if raw_settings.get("compliance_policy_hash") is not None
        else ""
    )
    stored_version_id = _optional_uuid(raw_settings.get("compliance_policy_version_id"))
    stored_effective_at = _parse_datetime_value(raw_settings.get("compliance_policy_effective_at"))
    stored_scope = str(raw_settings.get("compliance_policy_scope") or "").strip().lower()
    clears_parent = bool(raw_settings.get("compliance_policy_clears_parent"))
    settings = _read_compliance_settings(compliance_payload)
    has_policy_payload = has_nonempty_compliance_policy(settings.model_dump())
    has_policy_metadata = any(
        (
            stored_hash,
            stored_version_id is not None,
            stored_effective_at is not None,
            stored_scope in {"business", "location"},
            clears_parent,
        )
    )
    if not has_policy_metadata and not has_policy_payload:
        return None
    return ResolvedCompliancePolicyContext(
        policy_scope=(
            stored_scope
            if stored_scope in {"business", "location"}
            else policy_scope
        ),
        settings=settings,
        policy_hash=stored_hash or compliance_policy_hash(settings.model_dump()),
        version_id=stored_version_id,
        effective_at=stored_effective_at,
        clears_parent=clears_parent or not has_policy_payload,
        source="versioned" if has_policy_metadata else "legacy",
    )


async def resolve_business_compliance_policy_context(
    session: AsyncSession,
    *,
    business: Business,
    as_of: datetime,
) -> ResolvedCompliancePolicyContext | None:
    version = await _effective_policy_version(
        session,
        business_id=business.id,
        policy_scope="business",
        as_of=as_of,
    )
    if version is not None:
        return _context_from_version(version)
    return _stored_context(
        policy_scope="business",
        settings_payload=business.settings,
    )


async def resolve_location_compliance_policy_context(
    session: AsyncSession,
    *,
    business: Business,
    location: Location,
    as_of: datetime,
) -> ResolvedCompliancePolicyContext | None:
    version = await _effective_policy_version(
        session,
        business_id=business.id,
        location_id=location.id,
        policy_scope="location",
        as_of=as_of,
    )
    if version is not None:
        return _context_from_version(version)
    return _stored_context(
        policy_scope="location",
        settings_payload=location.settings,
    )


async def resolved_compliance_settings_inputs(
    session: AsyncSession,
    *,
    business: Business | None,
    location: Location | None,
    as_of: datetime,
) -> tuple[dict[str, object], dict[str, object]]:
    business_settings = (
        dict(business.settings)
        if business is not None and isinstance(business.settings, dict)
        else {}
    )
    location_settings = (
        dict(location.settings)
        if location is not None and isinstance(location.settings, dict)
        else {}
    )
    if business is not None:
        business_context = await resolve_business_compliance_policy_context(
            session,
            business=business,
            as_of=as_of,
        )
        business_settings = _context_to_settings_payload(
            business_settings,
            context=business_context,
        )
    if business is not None and location is not None:
        location_context = await resolve_location_compliance_policy_context(
            session,
            business=business,
            location=location,
            as_of=as_of,
        )
        location_settings = _context_to_settings_payload(
            location_settings,
            context=location_context,
        )
    elif location is not None:
        location_settings = _context_to_settings_payload(
            location_settings,
            context=_legacy_context(
                policy_scope="location",
                payload=location.settings.get("compliance")
                if isinstance(location.settings, dict)
                else {},
            ),
        )
    return business_settings, location_settings


async def effective_business_settings_payload(
    session: AsyncSession,
    *,
    business: Business,
    as_of: datetime,
) -> dict[str, object]:
    context = await resolve_business_compliance_policy_context(
        session,
        business=business,
        as_of=as_of,
    )
    return apply_compliance_policy_context_to_settings(
        dict(business.settings or {}),
        context=context,
    )


async def effective_location_settings_payload(
    session: AsyncSession,
    *,
    business: Business,
    location: Location,
    as_of: datetime,
) -> dict[str, object]:
    business_context = await resolve_business_compliance_policy_context(
        session,
        business=business,
        as_of=as_of,
    )
    location_context = await resolve_location_compliance_policy_context(
        session,
        business=business,
        location=location,
        as_of=as_of,
    )
    return apply_compliance_policy_context_to_settings(
        dict(location.settings or {}),
        context=_effective_location_policy_context(
            business_context=business_context,
            location_context=location_context,
        ),
    )


def merge_compliance_policy_update(
    current_payload: object,
    update_payload: object,
) -> dict[str, object]:
    current_settings = _read_compliance_settings(current_payload).model_dump()
    raw_update = (
        update_payload.model_dump(exclude_unset=True)
        if hasattr(update_payload, "model_dump")
        else dict(update_payload)
        if isinstance(update_payload, dict)
        else {}
    )
    for key, value in raw_update.items():
        current_settings[key] = value
    return _read_compliance_settings(current_settings).model_dump()


async def create_compliance_policy_version(
    session: AsyncSession,
    *,
    business: Business,
    policy_scope: Literal["business", "location"],
    settings_payload: object,
    effective_at: datetime,
    location: Location | None = None,
    created_by_user_id: UUID | None = None,
    note: str | None = None,
) -> CompliancePolicyVersion:
    normalized_settings = _read_compliance_settings(settings_payload).model_dump()
    policy_hash = compliance_policy_hash(normalized_settings)
    previous_version = _coerce_policy_version(await session.scalar(
        select(CompliancePolicyVersion)
        .where(CompliancePolicyVersion.business_id == business.id)
        .where(CompliancePolicyVersion.policy_scope == policy_scope)
        .where(
            CompliancePolicyVersion.location_id == location.id
            if policy_scope == "location" and location is not None
            else CompliancePolicyVersion.location_id.is_(None)
        )
        .where(CompliancePolicyVersion.effective_at < effective_at)
        .order_by(CompliancePolicyVersion.effective_at.desc(), CompliancePolicyVersion.created_at.desc())
        .limit(1)
    ))
    next_version = _coerce_policy_version(await session.scalar(
        select(CompliancePolicyVersion)
        .where(CompliancePolicyVersion.business_id == business.id)
        .where(CompliancePolicyVersion.policy_scope == policy_scope)
        .where(
            CompliancePolicyVersion.location_id == location.id
            if policy_scope == "location" and location is not None
            else CompliancePolicyVersion.location_id.is_(None)
        )
        .where(CompliancePolicyVersion.effective_at > effective_at)
        .order_by(CompliancePolicyVersion.effective_at.asc(), CompliancePolicyVersion.created_at.asc())
        .limit(1)
    ))
    version = CompliancePolicyVersion(
        business_id=business.id,
        location_id=location.id if location is not None else None,
        created_by_user_id=created_by_user_id,
        replaces_version_id=previous_version.id if previous_version is not None else None,
        policy_scope=policy_scope,
        policy_hash=policy_hash,
        settings_payload=normalized_settings,
        effective_at=effective_at,
        superseded_at=next_version.effective_at if next_version is not None else None,
        note=note,
    )
    session.add(version)
    if previous_version is not None and (
        previous_version.superseded_at is None or previous_version.superseded_at > effective_at
    ):
        previous_version.superseded_at = effective_at
    await session.flush()
    return version


async def list_compliance_policy_versions(
    session: AsyncSession,
    *,
    business_id: UUID,
    policy_scope: Literal["business", "location"],
    location_id: UUID | None = None,
    limit: int = 20,
    as_of: datetime | None = None,
) -> list[CompliancePolicyVersionRead]:
    reference_time = as_of or datetime.now(timezone.utc)
    stmt = (
        select(CompliancePolicyVersion)
        .where(CompliancePolicyVersion.business_id == business_id)
        .where(CompliancePolicyVersion.policy_scope == policy_scope)
        .order_by(CompliancePolicyVersion.effective_at.desc(), CompliancePolicyVersion.created_at.desc())
        .limit(limit)
    )
    if policy_scope == "location":
        stmt = stmt.where(CompliancePolicyVersion.location_id == location_id)
    else:
        stmt = stmt.where(CompliancePolicyVersion.location_id.is_(None))
    result = await session.execute(stmt)
    versions = list(result.scalars().all())
    return [
        compliance_policy_version_read(version, as_of=reference_time)
        for version in versions
    ]


def compliance_policy_version_read(
    version: CompliancePolicyVersion,
    *,
    as_of: datetime | None = None,
) -> CompliancePolicyVersionRead:
    reference_time = as_of or datetime.now(timezone.utc)
    return CompliancePolicyVersionRead(
        id=version.id,
        business_id=version.business_id,
        location_id=version.location_id,
        policy_scope=(
            "location" if str(version.policy_scope).strip().lower() == "location" else "business"
        ),
        policy_hash=version.policy_hash,
        settings=_read_compliance_settings(version.settings_payload),
        effective_at=version.effective_at,
        superseded_at=version.superseded_at,
        created_by_user_id=version.created_by_user_id,
        replaces_version_id=version.replaces_version_id,
        clears_parent=not has_nonempty_compliance_policy(version.settings_payload),
        is_effective=(
            version.effective_at <= reference_time
            and (version.superseded_at is None or version.superseded_at > reference_time)
        ),
        is_scheduled=version.effective_at > reference_time,
    )


def compliance_policy_version_settings_payload(
    version: CompliancePolicyVersion,
) -> dict[str, object]:
    return apply_compliance_policy_context_to_settings(
        {},
        context=_context_from_version(version),
    )


async def restore_compliance_policy_version(
    session: AsyncSession,
    *,
    business: Business,
    policy_scope: Literal["business", "location"],
    version_id: UUID,
    location: Location | None = None,
    actor_user_id: UUID | None = None,
    expected_current_policy_hash: str | None = None,
    effective_at: datetime | None = None,
    note: str | None = None,
) -> CompliancePolicyVersion:
    version = await session.get(CompliancePolicyVersion, version_id)
    if version is None or version.business_id != business.id:
        raise LookupError("compliance_policy_version_not_found")
    normalized_scope = (
        "location" if str(version.policy_scope).strip().lower() == "location" else "business"
    )
    if normalized_scope != policy_scope:
        raise LookupError("compliance_policy_version_not_found")
    if policy_scope == "location":
        if location is None or version.location_id != location.id:
            raise LookupError("compliance_policy_version_not_found")
    elif version.location_id is not None:
        raise LookupError("compliance_policy_version_not_found")

    reference_time = datetime.now(timezone.utc)
    current_context = (
        await resolve_location_compliance_policy_context(
            session,
            business=business,
            location=location,
            as_of=reference_time,
        )
        if policy_scope == "location" and location is not None
        else await resolve_business_compliance_policy_context(
            session,
            business=business,
            as_of=reference_time,
        )
    )
    if expected_current_policy_hash is not None:
        current_hash = (
            current_context.policy_hash
            if current_context is not None
            else compliance_policy_hash({})
        )
        if current_hash != expected_current_policy_hash:
            raise CompliancePolicyPreviewStaleError(
                current_compliance_policy_hash=current_hash,
                current_compliance_settings=(
                    current_context.settings
                    if current_context is not None
                    else _EMPTY_COMPLIANCE_POLICY
                ),
            )

    return await create_compliance_policy_version(
        session,
        business=business,
        policy_scope=policy_scope,
        settings_payload=version.settings_payload,
        effective_at=effective_at or reference_time,
        location=location,
        created_by_user_id=actor_user_id,
        note=note or f"restored_from:{version.id}",
    )


async def get_location_settings(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
) -> LocationSettingsRead:
    location = await businesses.get_location(session, business_id, location_id)
    if location is None:
        raise LookupError("location_not_found")
    business = await businesses.get_business(session, business_id)
    reference_time = datetime.now(timezone.utc)
    business_context = (
        await resolve_business_compliance_policy_context(
            session,
            business=business,
            as_of=reference_time,
        )
        if business is not None
        else None
    )
    location_context = (
        await resolve_location_compliance_policy_context(
            session,
            business=business,
            location=location,
            as_of=reference_time,
        )
        if business is not None
        else _legacy_context(
            policy_scope="location",
            payload=location.settings.get("compliance")
            if isinstance(location.settings, dict)
            else {},
        )
    )
    payload = {
        **DEFAULT_LOCATION_SETTINGS,
        **dict(location.settings or {}),
    }
    payload = _context_to_settings_payload(
        payload,
        context=_effective_location_policy_context(
            business_context=business_context,
            location_context=location_context,
        ),
    )
    return _read_location_settings_payload(location=location, payload=payload)


async def _get_first_business_location(
    session: AsyncSession,
    business_id: UUID,
) -> Location | None:
    return await session.scalar(
        select(Location)
        .where(Location.business_id == business_id, Location.is_active.is_(True))
        .order_by(Location.created_at.asc())
        .limit(1)
    )


async def get_business_shift_defaults(
    session: AsyncSession,
    *,
    business_id: UUID,
) -> BusinessShiftDefaultsRead:
    business = await businesses.get_business(session, business_id)
    if business is None:
        raise LookupError("business_not_found")

    first_location = await _get_first_business_location(session, business_id)
    presets, is_persisted, derived_from_location_id = (
        shift_defaults_service.read_business_shift_presets(
            business,
            fallback_location=first_location,
        )
    )
    return BusinessShiftDefaultsRead(
        business_id=business.id,
        presets=_shift_preset_reads(presets),
        derived_from_location_id=derived_from_location_id,
        is_persisted=is_persisted,
    )


async def update_business_shift_defaults(
    session: AsyncSession,
    *,
    business_id: UUID,
    payload: BusinessShiftDefaultsUpdate,
) -> BusinessShiftDefaultsRead:
    business = await businesses.get_business(session, business_id)
    if business is None:
        raise LookupError("business_not_found")

    normalized = shift_defaults_service.normalize_shift_presets(
        [item.model_dump() for item in payload.presets]
    )
    if normalized is None:
        raise ValueError("invalid_shift_defaults")

    next_settings = dict(business.settings or {})
    next_settings["shift_defaults"] = normalized
    next_settings["shift_defaults_source"] = "manual"
    business.settings = next_settings
    await session.flush()
    return BusinessShiftDefaultsRead(
        business_id=business.id,
        presets=_shift_preset_reads(normalized),
        derived_from_location_id=_optional_uuid(
            next_settings.get("shift_defaults_seeded_from_location_id"),
        ),
        is_persisted=True,
    )


async def get_location_shift_defaults(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
) -> LocationShiftDefaultsRead:
    business = await businesses.get_business(session, business_id)
    if business is None:
        raise LookupError("business_not_found")
    location = await businesses.get_location(session, business_id, location_id)
    if location is None:
        raise LookupError("location_not_found")

    first_location = await _get_first_business_location(session, business_id)
    business_presets, _, _ = shift_defaults_service.read_business_shift_presets(
        business,
        fallback_location=first_location,
    )
    override_presets = shift_defaults_service.read_location_shift_override(location)
    effective_presets = override_presets or business_presets
    return LocationShiftDefaultsRead(
        business_id=business.id,
        location_id=location.id,
        has_overrides=override_presets is not None,
        presets=_shift_preset_reads(effective_presets),
        business_presets=_shift_preset_reads(business_presets),
        override_presets=(
            _shift_preset_reads(override_presets) if override_presets is not None else None
        ),
    )


async def update_location_shift_defaults(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
    payload: LocationShiftDefaultsUpdate,
) -> LocationShiftDefaultsRead:
    business = await businesses.get_business(session, business_id)
    if business is None:
        raise LookupError("business_not_found")
    location = await businesses.get_location(session, business_id, location_id)
    if location is None:
        raise LookupError("location_not_found")

    next_settings = dict(location.settings or {})
    if payload.presets is None:
        next_settings.pop("shift_defaults_override", None)
    else:
        normalized = shift_defaults_service.normalize_shift_presets(
            [item.model_dump() for item in payload.presets]
        )
        if normalized is None:
            raise ValueError("invalid_shift_defaults")
        next_settings["shift_defaults_override"] = normalized
    location.settings = next_settings
    await session.flush()
    return await get_location_shift_defaults(
        session,
        business_id=business_id,
        location_id=location_id,
    )


async def update_location_settings(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
    payload: LocationSettingsUpdate,
    actor_user_id: UUID | None = None,
) -> LocationSettingsRead:
    business = await businesses.get_business(session, business_id)
    if business is None:
        raise LookupError("business_not_found")
    location = await businesses.get_location(session, business_id, location_id)
    if location is None:
        raise LookupError("location_not_found")

    next_settings = dict(location.settings or {})
    updates = payload.model_dump(exclude_unset=True)
    updates.pop("expected_compliance_policy_hash", None)
    updates.pop("compliance_effective_at", None)
    timezone_changed = False

    if "timezone" in updates:
        next_timezone = updates.pop("timezone") or location.timezone
        timezone_changed = next_timezone != location.timezone
        location.timezone = next_timezone

    if "compliance" in updates:
        updates.pop("compliance")
        reference_time = datetime.now(timezone.utc)
        current_context = await resolve_location_compliance_policy_context(
            session,
            business=business,
            location=location,
            as_of=reference_time,
        )
        expected_hash = payload.expected_compliance_policy_hash
        if expected_hash is not None:
            current_hash = (
                current_context.policy_hash
                if current_context is not None
                else compliance_policy_hash({})
            )
            if current_hash != expected_hash:
                raise CompliancePolicyPreviewStaleError(
                    current_compliance_policy_hash=current_hash,
                    current_compliance_settings=(
                        current_context.settings
                        if current_context is not None
                        else _EMPTY_COMPLIANCE_POLICY
                    ),
                )
        next_compliance = (
            _EMPTY_COMPLIANCE_POLICY.model_dump()
            if payload.compliance is None
            else merge_compliance_policy_update(
                current_context.settings.model_dump()
                if current_context is not None
                else {},
                payload.compliance,
            )
        )
        effective_at = payload.compliance_effective_at or reference_time
        current_settings_payload = (
            current_context.settings.model_dump()
            if current_context is not None
            else _EMPTY_COMPLIANCE_POLICY.model_dump()
        )
        effective_context = current_context
        if (
            next_compliance != current_settings_payload
            or payload.compliance_effective_at is not None
        ):
            created_version = await create_compliance_policy_version(
                session,
                business=business,
                location=location,
                policy_scope="location",
                settings_payload=next_compliance,
                effective_at=effective_at,
                created_by_user_id=actor_user_id,
            )
            if effective_at <= reference_time:
                effective_context = _context_from_version(created_version)
        next_settings = _context_to_settings_payload(
            next_settings,
            context=effective_context,
        )

    next_settings.update(updates)
    location.settings = next_settings
    await session.flush()
    if timezone_changed:
        await labor_rule_resolution.sync_location_labor_rule_resolution(
            session,
            business=business,
            location=location,
        )
    return await get_location_settings(
        session,
        business_id=business_id,
        location_id=location_id,
    )
