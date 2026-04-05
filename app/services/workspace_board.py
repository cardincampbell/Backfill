from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.business import Business, Location, LocationRole, Role
from app.models.common import AssignmentStatus, CoverageCaseStatus, MembershipRole, OfferStatus
from app.models.coverage import CoverageCase, CoverageOffer
from app.models.scheduling import Shift, ShiftAssignment
from app.models.workforce import Employee, EmployeeRole
from app.schemas.workspace_board import (
    WorkspaceBoardActionSummaryRead,
    WorkspaceBoardRoleRead,
    WorkspaceBoardShiftAssignmentRead,
    WorkspaceBoardShiftRead,
    WorkspaceBoardWorkerRead,
    WorkspaceLocationBoardRead,
)


READ_ROLES = {
    MembershipRole.owner,
    MembershipRole.admin,
    MembershipRole.manager,
    MembershipRole.viewer,
}


@dataclass
class LocationBoardWindow:
    week_start: date
    week_end: date
    starts_at: datetime
    ends_at: datetime


def monday_for(timezone_name: str, value: date | None = None) -> date:
    current = value or datetime.now(ZoneInfo(timezone_name)).date()
    return current - timedelta(days=current.weekday())


def board_window(timezone_name: str, week_start: date | None = None) -> LocationBoardWindow:
    local_zone = ZoneInfo(timezone_name)
    monday = monday_for(timezone_name, week_start)
    week_end = monday + timedelta(days=6)
    starts_at = datetime.combine(monday, datetime.min.time(), tzinfo=local_zone).astimezone(timezone.utc)
    ends_at = datetime.combine(week_end, datetime.max.time(), tzinfo=local_zone).astimezone(timezone.utc)
    return LocationBoardWindow(
        week_start=monday,
        week_end=week_end,
        starts_at=starts_at,
        ends_at=ends_at,
    )


def _to_float(value: Decimal | float | int | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def _best_assignment(shift: Shift) -> ShiftAssignment | None:
    active = [
        assignment
        for assignment in (shift.assignments or [])
        if assignment.status not in {
            AssignmentStatus.cancelled,
            AssignmentStatus.declined,
            AssignmentStatus.replaced,
        }
    ]
    if not active:
        return None
    return max(active, key=lambda item: (item.sequence_no, item.created_at))


def _latest_case(shift: Shift) -> CoverageCase | None:
    cases = list(shift.coverage_cases or [])
    if not cases:
        return None
    return max(cases, key=lambda item: item.created_at)


def _offer_counts(case: CoverageCase | None) -> tuple[int, int]:
    if case is None:
        return 0, 0
    pending = 0
    delivered = 0
    for offer in case.offers or []:
        if offer.status == OfferStatus.pending:
            pending += 1
        elif offer.status == OfferStatus.delivered:
            delivered += 1
    return pending, delivered


def _standby_depth(case: CoverageCase | None) -> int:
    if case is None:
        return 0
    raw_queue = (case.case_metadata or {}).get("standby_queue")
    if not isinstance(raw_queue, list):
        return 0
    return sum(1 for item in raw_queue if isinstance(item, dict))


def _manager_action_required(shift: Shift, case: CoverageCase | None) -> bool:
    if case is None:
        return False
    return bool(
        case.requires_manager_approval
        and case.status in {CoverageCaseStatus.queued, CoverageCaseStatus.running}
        and shift.seats_filled < shift.seats_requested
    )


async def get_location_board(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
    week_start: date | None = None,
) -> WorkspaceLocationBoardRead:
    business = await session.get(Business, business_id)
    location = await session.get(Location, location_id)
    if business is None or location is None or location.business_id != business_id:
        raise LookupError("business_or_location_not_found")
    window = board_window(location.timezone, week_start)

    role_rows = await session.execute(
        select(LocationRole)
        .options(selectinload(LocationRole.role))
        .where(
            LocationRole.location_id == location_id,
            LocationRole.is_active.is_(True),
        )
        .order_by(LocationRole.created_at.asc())
    )
    location_roles = list(role_rows.scalars().all())
    enabled_role_ids = {item.role_id for item in location_roles}
    roles = [
        WorkspaceBoardRoleRead(
            role_id=item.role.id,
            role_code=item.role.code,
            role_name=item.role.name,
            min_headcount=item.min_headcount,
            max_headcount=item.max_headcount,
        )
        for item in location_roles
        if item.role is not None
    ]
    business_role_rows = await session.execute(
        select(Role)
        .where(Role.business_id == business_id)
        .order_by(Role.name.asc(), Role.created_at.asc())
    )
    business_roles = list(business_role_rows.scalars().all())
    available_roles = [
        WorkspaceBoardRoleRead(
            role_id=role.id,
            role_code=role.code,
            role_name=role.name,
        )
        for role in business_roles
    ]

    employee_rows = await session.execute(
        select(Employee)
        .options(
            selectinload(Employee.employee_roles).selectinload(EmployeeRole.role),
            selectinload(Employee.clearances),
        )
        .where(Employee.business_id == business_id)
        .order_by(Employee.created_at.asc())
    )
    employees = list(employee_rows.scalars().all())

    shift_rows = await session.execute(
        select(Shift)
        .options(
            selectinload(Shift.role),
            selectinload(Shift.assignments).selectinload(ShiftAssignment.employee),
            selectinload(Shift.coverage_cases).selectinload(CoverageCase.offers),
        )
        .where(
            Shift.business_id == business_id,
            Shift.location_id == location_id,
            Shift.ends_at >= window.starts_at,
            Shift.starts_at <= window.ends_at,
        )
        .order_by(Shift.starts_at.asc())
    )
    shifts = list(shift_rows.scalars().all())

    workers: list[WorkspaceBoardWorkerRead] = []
    for employee in employees:
        role_ids = [
            assignment.role_id
            for assignment in employee.employee_roles or []
            if assignment.role_id in enabled_role_ids
        ]
        if not role_ids:
            continue
        role_names = sorted(
            {
                assignment.role.name
                for assignment in employee.employee_roles or []
                if assignment.role is not None and assignment.role_id in enabled_role_ids
            }
        )
        clearance = next(
            (item for item in (employee.clearances or []) if item.location_id == location_id),
            None,
        )
        can_cover_here = employee.home_location_id == location_id or clearance is not None
        can_blast_here = bool(clearance.can_blast) if clearance is not None else employee.home_location_id == location_id
        workers.append(
            WorkspaceBoardWorkerRead(
                employee_id=employee.id,
                full_name=employee.full_name,
                preferred_name=employee.preferred_name,
                phone_e164=employee.phone_e164,
                email=employee.email,
                home_location_id=employee.home_location_id,
                reliability_score=_to_float(employee.reliability_score),
                avg_response_time_seconds=employee.avg_response_time_seconds,
                role_ids=role_ids,
                role_names=role_names,
                can_cover_here=can_cover_here,
                can_blast_here=can_blast_here,
            )
        )
    workers.sort(key=lambda item: item.full_name.lower())

    shift_reads: list[WorkspaceBoardShiftRead] = []
    approval_required = 0
    active_coverage = 0
    open_shifts = 0

    for shift in shifts:
        current_assignment = _best_assignment(shift)
        latest_case = _latest_case(shift)
        pending_offer_count, delivered_offer_count = _offer_counts(latest_case)
        standby_depth = _standby_depth(latest_case)
        manager_action_required = _manager_action_required(shift, latest_case)

        if manager_action_required:
            approval_required += 1
        if latest_case is not None and latest_case.status in {
            CoverageCaseStatus.queued,
            CoverageCaseStatus.running,
        }:
            active_coverage += 1
        if shift.seats_filled < shift.seats_requested:
            open_shifts += 1

        shift_reads.append(
            WorkspaceBoardShiftRead(
                shift_id=shift.id,
                role_id=shift.role_id,
                role_code=shift.role.code if shift.role is not None else "role",
                role_name=shift.role.name if shift.role is not None else "Role",
                starts_at=shift.starts_at,
                ends_at=shift.ends_at,
                status=shift.status.value,
                seats_requested=shift.seats_requested,
                seats_filled=shift.seats_filled,
                requires_manager_approval=shift.requires_manager_approval,
                premium_cents=shift.premium_cents,
                notes=shift.notes,
                current_assignment=(
                    WorkspaceBoardShiftAssignmentRead(
                        assignment_id=current_assignment.id,
                        employee_id=current_assignment.employee_id,
                        employee_name=current_assignment.employee.full_name
                        if current_assignment.employee is not None
                        else None,
                        status=current_assignment.status.value,
                        assigned_via=current_assignment.assigned_via,
                        accepted_at=current_assignment.accepted_at,
                    )
                    if current_assignment is not None
                    else None
                ),
                coverage_case_id=latest_case.id if latest_case is not None else None,
                coverage_case_status=latest_case.status.value if latest_case is not None else None,
                pending_offer_count=pending_offer_count,
                delivered_offer_count=delivered_offer_count,
                standby_depth=standby_depth,
                manager_action_required=manager_action_required,
            )
        )

    business_name = business.brand_name or business.legal_name
    return WorkspaceLocationBoardRead(
        business_id=business.id,
        business_name=business_name,
        business_slug=business.slug,
        location_id=location.id,
        location_name=location.name,
        location_slug=location.slug,
        address_line_1=location.address_line_1,
        locality=location.locality,
        region=location.region,
        postal_code=location.postal_code,
        country_code=location.country_code,
        timezone=location.timezone,
        week_start_date=window.week_start,
        week_end_date=window.week_end,
        location_role_setup_required=not bool(location_roles),
        roles=roles,
        available_roles=available_roles,
        workers=workers,
        shifts=shift_reads,
        action_summary=WorkspaceBoardActionSummaryRead(
            total=approval_required + active_coverage,
            approval_required=approval_required,
            active_coverage=active_coverage,
            open_shifts=open_shifts,
        ),
    )
