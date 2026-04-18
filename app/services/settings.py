from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Location
from app.schemas.settings import (
    BusinessShiftDefaultsRead,
    BusinessShiftDefaultsUpdate,
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


def _optional_uuid(value: object) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


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


def _read_location_settings(location: Location) -> LocationSettingsRead:
    payload = {**DEFAULT_LOCATION_SETTINGS, **(location.settings or {})}
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
    return _read_location_settings(location)


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
) -> LocationSettingsRead:
    business = await businesses.get_business(session, business_id)
    if business is None:
        raise LookupError("business_not_found")
    location = await businesses.get_location(session, business_id, location_id)
    if location is None:
        raise LookupError("location_not_found")

    next_settings = dict(location.settings or {})
    updates = payload.model_dump(exclude_unset=True)
    timezone_changed = False

    if "timezone" in updates:
        next_timezone = updates.pop("timezone") or location.timezone
        timezone_changed = next_timezone != location.timezone
        location.timezone = next_timezone

    next_settings.update(updates)
    location.settings = next_settings
    await session.flush()
    if timezone_changed:
        await labor_rule_resolution.sync_location_labor_rule_resolution(
            session,
            business=business,
            location=location,
        )
    return _read_location_settings(location)
