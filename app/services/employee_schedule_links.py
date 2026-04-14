from __future__ import annotations

import hashlib
import hmac
from datetime import date, datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import quote, urlencode
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.business import Location
from app.models.common import ShiftLifecycleStatus
from app.models.scheduling import Shift, ShiftAssignment
from app.models.workforce import Employee, EmployeeLocation, EmployeeScheduleAccessLink
from app.schemas.employee_schedule import (
    PublicEmployeeScheduleLocationRead,
    PublicEmployeeScheduleRead,
    PublicEmployeeScheduleShiftRead,
)
from app.services import shift_assignments
from app.services.schedule_weeks import effective_week_start_day, schedule_week_window

_TOKEN_PREFIX = "bfv2sched"
_PUBLISHABLE_LIFECYCLE_STATUSES = {
    ShiftLifecycleStatus.scheduled,
    ShiftLifecycleStatus.in_progress,
    ShiftLifecycleStatus.completed,
    ShiftLifecycleStatus.cancelled,
}
_VISIBLE_LOCATION_ACCESS_LEVELS = {"approved", "trusted"}
_LAST_ACCESSED_TOUCH_WINDOW = timedelta(minutes=15)


def _sign_token_payload(payload: str) -> str:
    return hmac.new(
        settings.public_link_signing_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def build_employee_schedule_token(link: EmployeeScheduleAccessLink) -> str:
    payload = f"{link.id}.{int(link.token_version or 1)}"
    return f"{_TOKEN_PREFIX}_{payload}.{_sign_token_payload(payload)}"


def parse_employee_schedule_token(raw_token: str) -> tuple[UUID, int] | None:
    token = str(raw_token or "").strip()
    if not token.startswith(f"{_TOKEN_PREFIX}_"):
        return None
    encoded = token[len(_TOKEN_PREFIX) + 1 :]
    try:
        link_id_text, version_text, signature = encoded.split(".", 2)
        link_id = UUID(link_id_text)
        version = int(version_text)
    except (TypeError, ValueError):
        return None
    expected = _sign_token_payload(f"{link_id}.{version}")
    if not hmac.compare_digest(signature, expected):
        return None
    return link_id, version


def build_employee_schedule_link(
    token: str,
    *,
    week_start_date: date | None = None,
    location_id: UUID | None = None,
) -> str:
    params: dict[str, str] = {}
    if week_start_date is not None:
        params["week_start"] = week_start_date.isoformat()
    if location_id is not None:
        params["location_id"] = str(location_id)
    query = f"?{urlencode(params)}" if params else ""
    return f"{settings.web_base_url}/schedule/{quote(token)}{query}"


async def get_or_create_schedule_access_link(
    session: AsyncSession,
    *,
    business_id: UUID,
    employee: Employee,
) -> tuple[EmployeeScheduleAccessLink, bool]:
    link = await session.scalar(
        select(EmployeeScheduleAccessLink).where(
            EmployeeScheduleAccessLink.business_id == business_id,
            EmployeeScheduleAccessLink.employee_id == employee.id,
        )
    )
    now = datetime.now(timezone.utc)
    if link is None:
        link = EmployeeScheduleAccessLink(
            business_id=business_id,
            employee_id=employee.id,
            token_version=1,
            rotated_at=now,
            revoked_at=None,
            last_accessed_at=None,
            link_metadata={},
        )
        session.add(link)
        await session.flush()
        return link, True

    created = False
    if link.revoked_at is not None:
        link.token_version = int(link.token_version or 1) + 1
        link.rotated_at = now
        link.revoked_at = None
        await session.flush()
    return link, created


async def rotate_schedule_access_link(
    session: AsyncSession,
    *,
    link: EmployeeScheduleAccessLink,
) -> EmployeeScheduleAccessLink:
    now = datetime.now(timezone.utc)
    link.token_version = int(link.token_version or 1) + 1
    link.rotated_at = now
    link.revoked_at = None
    await session.flush()
    return link


def _visible_employee_locations(employee_locations: Iterable[EmployeeLocation] | None) -> list[EmployeeLocation]:
    visible_locations: list[EmployeeLocation] = []
    for employee_location in employee_locations or []:
        if employee_location.access_level not in _VISIBLE_LOCATION_ACCESS_LEVELS:
            continue
        if employee_location.location is None:
            continue
        visible_locations.append(employee_location)
    visible_locations.sort(
        key=lambda item: (
            item.location.location_display_name.lower(),
            item.created_at or datetime.min.replace(tzinfo=timezone.utc),
        )
    )
    return visible_locations


def _selected_location_for(
    *,
    employee: Employee,
    explicit_location_id: UUID | None,
) -> Location | None:
    visible_locations = _visible_employee_locations(employee.employee_locations)
    if explicit_location_id is None:
        return None
    for employee_location in visible_locations:
        if employee_location.location_id == explicit_location_id:
            return employee_location.location
    raise LookupError("location_not_found")


async def resolve_schedule_access_link(
    session: AsyncSession,
    raw_token: str,
) -> tuple[EmployeeScheduleAccessLink | None, bool]:
    parsed = parse_employee_schedule_token(raw_token)
    if parsed is None:
        return None, False
    link_id, token_version = parsed
    link = await session.get(
        EmployeeScheduleAccessLink,
        link_id,
        options=[
            selectinload(EmployeeScheduleAccessLink.employee)
            .selectinload(Employee.employee_locations)
            .selectinload(EmployeeLocation.location),
            selectinload(EmployeeScheduleAccessLink.business),
        ],
    )
    if link is None or link.revoked_at is not None:
        return None, False
    if int(link.token_version or 1) != token_version:
        return None, False

    now = datetime.now(timezone.utc)
    touched = False
    if link.last_accessed_at is None or link.last_accessed_at <= now - _LAST_ACCESSED_TOUCH_WINDOW:
        link.last_accessed_at = now
        touched = True
    return link, touched


async def get_employee_schedule_read(
    session: AsyncSession,
    *,
    raw_token: str,
    week_start: date | None = None,
    location_id: UUID | None = None,
) -> tuple[PublicEmployeeScheduleRead | None, bool]:
    link, touched = await resolve_schedule_access_link(session, raw_token)
    if link is None or link.employee is None or link.business is None:
        return None, touched

    employee = link.employee
    business = link.business
    selected_location = _selected_location_for(employee=employee, explicit_location_id=location_id)
    business_settings = business.settings if isinstance(business.settings, dict) else {}
    location_settings = (
        selected_location.settings
        if selected_location is not None and isinstance(selected_location.settings, dict)
        else {}
    )
    timezone_name = (
        selected_location.timezone
        if selected_location is not None
        else (business.timezone or "America/Los_Angeles")
    )
    week_start_day = effective_week_start_day(
        business_settings=business_settings,
        location_settings=location_settings,
    )
    window = schedule_week_window(timezone_name, week_start_day, week_start)

    shifts_result = await session.execute(
        select(Shift)
        .options(
            selectinload(Shift.location),
            selectinload(Shift.role),
            selectinload(Shift.assignments).selectinload(ShiftAssignment.employee),
        )
        .where(
            Shift.business_id == business.id,
            Shift.lifecycle_status.in_(_PUBLISHABLE_LIFECYCLE_STATUSES),
            Shift.ends_at >= window.starts_at,
            Shift.starts_at <= window.ends_at,
        )
        .order_by(Shift.starts_at.asc())
    )
    shifts = list(shifts_result.scalars().all())

    filtered_shifts: list[PublicEmployeeScheduleShiftRead] = []
    for shift in shifts:
        if selected_location is not None and shift.location_id != selected_location.id:
            continue
        current_assignment = shift_assignments.current_assignment(shift.assignments or [])
        if current_assignment is None or current_assignment.employee_id != employee.id:
            continue
        location = shift.location
        role = shift.role
        filtered_shifts.append(
            PublicEmployeeScheduleShiftRead(
                shift_id=shift.id,
                location_id=shift.location_id,
                location_name=location.location_display_name if location is not None else "Location",
                role_id=shift.role_id,
                role_name=role.name if role is not None else "Shift",
                starts_at=shift.starts_at,
                ends_at=shift.ends_at,
                timezone=shift.timezone,
                lifecycle_status=shift.lifecycle_status.value,
                staffing_status=shift.staffing_status.value,
                notes=shift.notes,
            )
        )

    available_locations = [
        PublicEmployeeScheduleLocationRead(
            location_id=employee_location.location_id,
            location_name=employee_location.location.location_display_name,
            location_timezone=employee_location.location.timezone,
        )
        for employee_location in _visible_employee_locations(employee.employee_locations)
    ]
    selected_location_name = selected_location.location_display_name if selected_location is not None else None

    return (
        PublicEmployeeScheduleRead(
            business_id=business.id,
            business_name=business.display_name,
            employee_id=employee.id,
            employee_name=employee.full_name,
            timezone=timezone_name,
            week_start_day=week_start_day,
            week_start_date=window.week_start,
            week_end_date=window.week_end,
            selected_location_id=selected_location.id if selected_location is not None else None,
            selected_location_name=selected_location_name,
            available_locations=available_locations,
            shifts=filtered_shifts,
        ),
        touched,
    )
