from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Location, LocationRole, Role
from app.models.common import CoverageCaseStatus, ShiftStatus
from app.models.coverage import CoverageCase
from app.models.scheduling import Shift
from app.models.scheduling import ShiftAssignment
from app.schemas.scheduling import ShiftCreate, ShiftUpdate
from app.services import businesses


async def list_shifts(
    session: AsyncSession,
    business_id: UUID,
    *,
    location_id: UUID | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
) -> list[Shift]:
    stmt = select(Shift).where(Shift.business_id == business_id)
    if location_id is not None:
        stmt = stmt.where(Shift.location_id == location_id)
    if starts_at is not None:
        stmt = stmt.where(Shift.ends_at >= starts_at)
    if ends_at is not None:
        stmt = stmt.where(Shift.starts_at <= ends_at)
    result = await session.execute(stmt.order_by(Shift.starts_at.asc()))
    return list(result.scalars().all())


async def create_shift(session: AsyncSession, business_id: UUID, payload: ShiftCreate) -> Shift:
    location = await session.get(Location, payload.location_id)
    role = await session.get(Role, payload.role_id)
    if location is None or role is None or location.business_id != business_id or role.business_id != business_id:
        raise LookupError("location_or_role_not_found")

    enabled_role = await session.scalar(
        select(LocationRole).where(
            LocationRole.location_id == payload.location_id,
            LocationRole.role_id == payload.role_id,
            LocationRole.is_active.is_(True),
        )
    )
    if enabled_role is None:
        enabled_role = await businesses.ensure_location_role(
            session,
            business_id=business_id,
            location_id=payload.location_id,
            role_id=payload.role_id,
            source="shift_usage",
        )

    shift = Shift(
        business_id=business_id,
        location_id=payload.location_id,
        role_id=payload.role_id,
        source_system=payload.source_system,
        source_shift_id=payload.source_shift_id,
        timezone=payload.timezone,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        seats_requested=payload.seats_requested,
        requires_manager_approval=payload.requires_manager_approval,
        premium_cents=payload.premium_cents,
        notes=payload.notes,
        shift_metadata=payload.shift_metadata,
    )
    session.add(shift)
    await session.flush()
    await session.refresh(shift)
    return shift


async def update_shift(
    session: AsyncSession,
    business_id: UUID,
    shift_id: UUID,
    payload: ShiftUpdate,
) -> Shift:
    shift = await session.get(Shift, shift_id)
    if shift is None or shift.business_id != business_id:
        raise LookupError("shift_not_found")

    if payload.role_id is not None and payload.role_id != shift.role_id:
        role = await session.get(Role, payload.role_id)
        if role is None or role.business_id != business_id:
            raise LookupError("role_not_found")
        enabled_role = await session.scalar(
            select(LocationRole).where(
                LocationRole.location_id == shift.location_id,
                LocationRole.role_id == payload.role_id,
                LocationRole.is_active.is_(True),
            )
        )
        if enabled_role is None:
            enabled_role = await businesses.ensure_location_role(
                session,
                business_id=business_id,
                location_id=shift.location_id,
                role_id=payload.role_id,
                source="shift_usage",
            )
        shift.role_id = payload.role_id

    if payload.timezone is not None:
        shift.timezone = payload.timezone
    if payload.starts_at is not None:
        shift.starts_at = payload.starts_at
    if payload.ends_at is not None:
        shift.ends_at = payload.ends_at
    if payload.starts_at is not None or payload.ends_at is not None:
        if shift.ends_at <= shift.starts_at:
          raise ValueError("shift_end_must_be_after_start")
    if payload.seats_requested is not None:
        if payload.seats_requested < max(1, shift.seats_filled):
            raise ValueError("seats_requested_below_current_fill")
        shift.seats_requested = payload.seats_requested
    if payload.requires_manager_approval is not None:
        shift.requires_manager_approval = payload.requires_manager_approval
    if payload.premium_cents is not None:
        shift.premium_cents = payload.premium_cents
    if payload.notes is not None:
        shift.notes = payload.notes
    if payload.shift_metadata is not None:
        shift.shift_metadata = payload.shift_metadata

    if shift.seats_filled >= shift.seats_requested and shift.seats_requested > 0:
        shift.status = ShiftStatus.covered
    elif shift.seats_filled > 0:
        shift.status = ShiftStatus.filling
    else:
        shift.status = ShiftStatus.open

    await session.flush()
    await session.refresh(shift)
    return shift


async def delete_shift(
    session: AsyncSession,
    business_id: UUID,
    shift_id: UUID,
) -> Shift:
    shift = await session.get(Shift, shift_id)
    if shift is None or shift.business_id != business_id:
        raise LookupError("shift_not_found")

    assignment_count = await session.scalar(
        select(func.count(ShiftAssignment.id)).where(ShiftAssignment.shift_id == shift_id)
    )
    if int(assignment_count or 0) > 0:
        raise ValueError("shift_has_assignments")

    active_case_count = await session.scalar(
        select(func.count(CoverageCase.id)).where(
            CoverageCase.shift_id == shift_id,
            CoverageCase.status.in_([
                CoverageCaseStatus.queued,
                CoverageCaseStatus.running,
                CoverageCaseStatus.filled,
            ]),
        )
    )
    if int(active_case_count or 0) > 0:
        raise ValueError("shift_has_coverage_history")

    await session.delete(shift)
    await session.flush()
    return shift
