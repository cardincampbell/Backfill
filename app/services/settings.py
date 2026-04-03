from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Location
from app.schemas.settings import LocationSettingsRead, LocationSettingsUpdate
from app.services import businesses


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
}


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


async def update_location_settings(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
    payload: LocationSettingsUpdate,
) -> LocationSettingsRead:
    location = await businesses.get_location(session, business_id, location_id)
    if location is None:
        raise LookupError("location_not_found")

    next_settings = dict(location.settings or {})
    updates = payload.model_dump(exclude_unset=True)

    if "timezone" in updates:
        location.timezone = updates.pop("timezone") or location.timezone

    next_settings.update(updates)
    location.settings = next_settings
    await session.flush()
    return _read_location_settings(location)
