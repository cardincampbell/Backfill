from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.business import Business, Location, LocationRole, Role
from app.models.common import (
    AssignmentStatus,
    CoverageAttemptStatus,
    CoverageCaseStatus,
    CoverageRunStatus,
    EmployeeStatus,
    OfferStatus,
    OutboxChannel,
    OutboxStatus,
    ShiftLifecycleStatus,
    ShiftStaffingStatus,
)
from app.models.coverage import CoverageCase, CoverageContactAttempt, CoverageOffer, OutboxEvent
from app.models.scheduling import Shift, ShiftAssignment
from app.models.workforce import Employee, EmployeeLocation, EmployeeRole
from app.schemas.scheduling import (
    ScheduleWeekPublishRead,
    ScheduleWeekPublishWrite,
    ShiftAssignmentMutationResponse,
    ShiftAssignmentRead,
    ShiftAssignmentWrite,
    ShiftCreate,
    ShiftUpdate,
)
from app.services import delivery, shift_assignments, worker_runtime
from app.services.schedule_weeks import effective_week_start_day, schedule_week_window

_ACTIVE_CASE_STATUSES = {CoverageCaseStatus.queued, CoverageCaseStatus.running}
_ACTIVE_OFFER_STATUSES = {OfferStatus.pending, OfferStatus.delivered}
_ACTIVE_RUN_STATUSES = {CoverageRunStatus.queued, CoverageRunStatus.running}
_USABLE_LOCATION_ACCESS_LEVELS = {"approved", "trusted"}
class ShiftAssignmentConflictError(Exception):
    def __init__(self, current_assignment: ShiftAssignment | None):
        super().__init__("stale_assignment_conflict")
        self.current_assignment = current_assignment


class ScheduleWeekPublishConflictError(Exception):
    def __init__(
        self,
        *,
        week_start_date: date,
        publishable_shift_ids: list[UUID],
        draft_shift_count: int,
        already_scheduled_shift_count: int,
    ):
        super().__init__("stale_publish_conflict")
        self.week_start_date = week_start_date
        self.publishable_shift_ids = publishable_shift_ids
        self.draft_shift_count = draft_shift_count
        self.already_scheduled_shift_count = already_scheduled_shift_count


@dataclass
class ShiftAssignmentMutationResult:
    shift: Shift
    action: str
    source: str
    previous_assignment: ShiftAssignment | None
    current_assignment: ShiftAssignment | None
    cancelled_cases: list[CoverageCase]
    cancelled_offers: list[CoverageOffer]
    no_op: bool = False


@dataclass
class ScheduleWeekPublishResult:
    business_id: UUID
    location_id: UUID
    week_start_date: date
    week_end_date: date
    published_shifts: list[Shift]
    already_scheduled_shifts: list[Shift]
    notification_enqueued_assignment_count: int
    notification_enqueued_employee_count: int


def _assignment_employee_name(assignment: ShiftAssignment | None) -> str | None:
    if assignment is None:
        return None
    metadata = getattr(assignment, "assignment_metadata", None) or {}
    if isinstance(metadata, dict):
        raw_name = metadata.get("employee_name")
        if isinstance(raw_name, str):
            name = raw_name.strip()
            if name:
                return name
    employee = getattr(assignment, "__dict__", {}).get("employee")
    if employee is not None:
        raw_name = getattr(employee, "full_name", None)
        if isinstance(raw_name, str):
            name = raw_name.strip()
            if name:
                return name
    raw_name = getattr(assignment, "employee_name", None)
    if isinstance(raw_name, str):
        name = raw_name.strip()
        if name:
            return name
    return None


def _assignment_read(assignment: ShiftAssignment | None) -> ShiftAssignmentRead | None:
    if assignment is None:
        return None
    return ShiftAssignmentRead(
        assignment_id=assignment.id,
        employee_id=assignment.employee_id,
        employee_name=_assignment_employee_name(assignment),
        status=assignment.status.value if hasattr(assignment.status, "value") else str(assignment.status),
        assigned_via=assignment.assigned_via,
        accepted_at=assignment.accepted_at,
    )


def build_shift_assignment_response(
    result: ShiftAssignmentMutationResult,
) -> ShiftAssignmentMutationResponse:
    return ShiftAssignmentMutationResponse(
        shift_id=result.shift.id,
        lifecycle_status=(
            result.shift.lifecycle_status.value
            if hasattr(result.shift.lifecycle_status, "value")
            else str(result.shift.lifecycle_status)
        ),
        staffing_status=(
            result.shift.staffing_status.value
            if hasattr(result.shift.staffing_status, "value")
            else str(result.shift.staffing_status)
        ),
        status=result.shift.status.value if hasattr(result.shift.status, "value") else str(result.shift.status),
        current_assignment=_assignment_read(result.current_assignment),
    )


def build_schedule_week_publish_response(
    result: ScheduleWeekPublishResult,
) -> ScheduleWeekPublishRead:
    return ScheduleWeekPublishRead(
        business_id=result.business_id,
        location_id=result.location_id,
        week_start_date=result.week_start_date,
        week_end_date=result.week_end_date,
        publish_mode="draft_only_net_new",
        published_shift_count=len(result.published_shifts),
        already_scheduled_shift_count=len(result.already_scheduled_shifts),
        notification_enqueued_assignment_count=result.notification_enqueued_assignment_count,
        notification_enqueued_employee_count=result.notification_enqueued_employee_count,
        published_shift_ids=[shift.id for shift in result.published_shifts],
        already_scheduled_shift_ids=[shift.id for shift in result.already_scheduled_shifts],
    )


def _normalized_notify_channels(channels: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw_channel in channels:
        channel = str(raw_channel).strip().lower()
        if channel not in {"sms", "email"} or channel in seen:
            continue
        seen.add(channel)
        normalized.append(channel)
    return normalized


def _format_shift_notification_line(shift: Shift) -> str:
    timezone_name = shift.timezone or "UTC"
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = timezone.utc
    starts_local = shift.starts_at.astimezone(tz)
    ends_local = shift.ends_at.astimezone(tz)
    role_name = getattr(getattr(shift, "role", None), "name", None) or "Shift"
    date_label = starts_local.strftime("%a %b %d").replace(" 0", " ")
    start_label = starts_local.strftime("%I:%M%p").lstrip("0")
    end_label = ends_local.strftime("%I:%M%p").lstrip("0")
    return f"{date_label} {start_label}-{end_label} · {role_name}"


def _schedule_publish_notification_payload(
    *,
    business_id: UUID,
    location_id: UUID,
    location_name: str,
    week_start_date: date,
    week_end_date: date,
    employee: Employee,
    shifts: list[Shift],
    note: str | None,
) -> dict:
    week_label = f"{week_start_date.strftime('%b %d').replace(' 0', ' ')} – {week_end_date.strftime('%b %d, %Y').replace(' 0', ' ')}"
    shift_lines = [_format_shift_notification_line(shift) for shift in shifts]
    subject = f"Your Backfill schedule for {week_label} is live"
    intro = f"Your schedule for {location_name} for the week of {week_label} is now live."
    text_body = "\n".join(
        [
            f"Hi {employee.full_name},",
            "",
            intro,
            "",
            *[f"- {line}" for line in shift_lines],
            *(["", note] if note else []),
        ]
    )
    html_lines = "".join(f"<li>{line}</li>" for line in shift_lines)
    html_body = (
        f"<p>Hi {employee.full_name},</p>"
        f"<p>{intro}</p>"
        f"<ul>{html_lines}</ul>"
        + (f"<p>{note}</p>" if note else "")
    )
    return {
        "business_id": str(business_id),
        "location_id": str(location_id),
        "employee_id": str(employee.id),
        "employee_name": employee.full_name,
        "phone_e164": employee.phone_e164,
        "email": employee.email,
        "location_name": location_name,
        "week_start_date": week_start_date.isoformat(),
        "week_end_date": week_end_date.isoformat(),
        "shift_ids": [str(shift.id) for shift in shifts],
        "shift_count": len(shifts),
        "text_body": text_body,
        "html_body": html_body,
        "subject": subject,
    }


async def _enqueue_schedule_publish_notifications(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
    location_name: str,
    week_start_date: date,
    week_end_date: date,
    shifts: list[Shift],
    notify_channels: list[str],
    note: str | None,
) -> tuple[int, int]:
    normalized_channels = _normalized_notify_channels(notify_channels)
    if not normalized_channels:
        return 0, 0

    shifts_by_employee: dict[UUID, list[Shift]] = {}
    employees_by_id: dict[UUID, Employee] = {}
    enqueued_assignment_count = 0

    for shift in shifts:
        current_assignment = shift_assignments.current_assignment(shift.assignments or [])
        employee = current_assignment.employee if current_assignment is not None else None
        if current_assignment is None or employee is None:
            continue
        available_channels = [
            channel
            for channel in normalized_channels
            if (channel == "sms" and employee.phone_e164) or (channel == "email" and employee.email)
        ]
        if not available_channels:
            continue
        shifts_by_employee.setdefault(employee.id, []).append(shift)
        employees_by_id[employee.id] = employee
        enqueued_assignment_count += 1

    for employee_id, employee_shifts in shifts_by_employee.items():
        employee = employees_by_id[employee_id]
        payload = _schedule_publish_notification_payload(
            business_id=business_id,
            location_id=location_id,
            location_name=location_name,
            week_start_date=week_start_date,
            week_end_date=week_end_date,
            employee=employee,
            shifts=employee_shifts,
            note=note,
        )
        for channel in normalized_channels:
            if channel == "sms" and not employee.phone_e164:
                continue
            if channel == "email" and not employee.email:
                continue
            session.add(
                OutboxEvent(
                    aggregate_type="schedule_publish",
                    aggregate_id=employee.id,
                    topic=delivery.SCHEDULE_PUBLISH_NOTIFICATION_TOPIC,
                    channel=OutboxChannel(channel),
                    payload=payload,
                    result_payload={},
                )
            )

    return enqueued_assignment_count, len(shifts_by_employee)


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
    if payload.ends_at <= payload.starts_at:
        raise ValueError("shift_end_must_be_after_start")

    enabled_role = await session.scalar(
        select(LocationRole).where(
            LocationRole.location_id == payload.location_id,
            LocationRole.role_id == payload.role_id,
            LocationRole.is_active.is_(True),
        )
    )
    if enabled_role is None:
        raise ValueError("location_role_not_enabled")

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
    shift = await session.get(
        Shift,
        shift_id,
        options=(
            selectinload(Shift.assignments),
            selectinload(Shift.coverage_cases),
        ),
    )
    if shift is None or shift.business_id != business_id:
        raise LookupError("shift_not_found")

    changed = False

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
            raise ValueError("location_role_not_enabled")
        shift.role_id = payload.role_id
        changed = True

    if payload.timezone is not None and payload.timezone != shift.timezone:
        shift.timezone = payload.timezone
        changed = True
    if payload.starts_at is not None and payload.starts_at != shift.starts_at:
        shift.starts_at = payload.starts_at
        changed = True
    if payload.ends_at is not None and payload.ends_at != shift.ends_at:
        shift.ends_at = payload.ends_at
        changed = True
    if payload.starts_at is not None or payload.ends_at is not None:
        if shift.ends_at <= shift.starts_at:
            raise ValueError("shift_end_must_be_after_start")
    if payload.seats_requested is not None and payload.seats_requested != shift.seats_requested:
        if payload.seats_requested < max(1, shift.seats_filled):
            raise ValueError("seats_requested_below_current_fill")
        shift.seats_requested = payload.seats_requested
        changed = True
    if (
        payload.requires_manager_approval is not None
        and payload.requires_manager_approval != shift.requires_manager_approval
    ):
        shift.requires_manager_approval = payload.requires_manager_approval
        changed = True
    if payload.premium_cents is not None and payload.premium_cents != shift.premium_cents:
        shift.premium_cents = payload.premium_cents
        changed = True
    if payload.notes is not None and payload.notes != shift.notes:
        shift.notes = payload.notes
        changed = True
    if payload.shift_metadata is not None and payload.shift_metadata != shift.shift_metadata:
        shift.shift_metadata = payload.shift_metadata
        changed = True

    _recompute_shift_ownership_state(shift)
    if changed and shift.lifecycle_status == ShiftLifecycleStatus.scheduled:
        shift.lifecycle_status = ShiftLifecycleStatus.draft

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

    if shift.lifecycle_status != ShiftLifecycleStatus.draft:
        raise ValueError("scheduled_shift_delete_requires_republish")

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


async def publish_schedule_week(
    session: AsyncSession,
    business_id: UUID,
    location_id: UUID,
    week_start_date: date,
    payload: ScheduleWeekPublishWrite,
) -> ScheduleWeekPublishResult:
    business = await session.get(Business, business_id)
    location = await session.get(Location, location_id)
    if business is None or location is None or location.business_id != business_id:
        raise LookupError("business_or_location_not_found")

    business_settings = business.settings if isinstance(business.settings, dict) else {}
    location_settings = location.settings if isinstance(location.settings, dict) else {}
    window = schedule_week_window(
        location.timezone,
        effective_week_start_day(
            business_settings=business_settings,
            location_settings=location_settings,
        ),
        week_start_date,
    )

    result = await session.execute(
        select(Shift)
        .options(
            selectinload(Shift.location),
            selectinload(Shift.role),
            selectinload(Shift.assignments).selectinload(ShiftAssignment.employee),
        )
        .where(
            Shift.business_id == business_id,
            Shift.location_id == location_id,
            Shift.ends_at >= window.starts_at,
            Shift.starts_at <= window.ends_at,
        )
        .order_by(Shift.starts_at.asc(), Shift.created_at.asc())
    )
    shifts = list(result.scalars().all())
    draft_shifts = [
        shift for shift in shifts if shift.lifecycle_status == ShiftLifecycleStatus.draft
    ]
    already_scheduled_shifts = [
        shift for shift in shifts if shift.lifecycle_status == ShiftLifecycleStatus.scheduled
    ]
    current_publishable_shift_ids = [shift.id for shift in draft_shifts]

    if payload.expected_shift_ids is not None:
        expected_shift_ids = sorted(str(shift_id) for shift_id in payload.expected_shift_ids)
        actual_shift_ids = sorted(str(shift_id) for shift_id in current_publishable_shift_ids)
        if expected_shift_ids != actual_shift_ids:
            raise ScheduleWeekPublishConflictError(
                week_start_date=window.week_start,
                publishable_shift_ids=current_publishable_shift_ids,
                draft_shift_count=len(draft_shifts),
                already_scheduled_shift_count=len(already_scheduled_shifts),
            )

    for shift in draft_shifts:
        shift.lifecycle_status = ShiftLifecycleStatus.scheduled

    notification_enqueued_assignment_count, notification_enqueued_employee_count = (
        await _enqueue_schedule_publish_notifications(
            session,
            business_id=business_id,
            location_id=location_id,
            location_name=getattr(location, "display_name", None) or location.name,
            week_start_date=window.week_start,
            week_end_date=window.week_end,
            shifts=draft_shifts,
            notify_channels=payload.notify_channels,
            note=payload.note,
        )
    )

    await session.flush()
    return ScheduleWeekPublishResult(
        business_id=business_id,
        location_id=location_id,
        week_start_date=window.week_start,
        week_end_date=window.week_end,
        published_shifts=draft_shifts,
        already_scheduled_shifts=already_scheduled_shifts,
        notification_enqueued_assignment_count=notification_enqueued_assignment_count,
        notification_enqueued_employee_count=notification_enqueued_employee_count,
    )


async def set_shift_assignment(
    session: AsyncSession,
    business_id: UUID,
    shift_id: UUID,
    payload: ShiftAssignmentWrite,
    *,
    assigned_by_user_id: UUID | None = None,
) -> ShiftAssignmentMutationResult:
    shift = await _load_shift_for_assignment(session, business_id, shift_id)
    current = shift_assignments.current_assignment(shift.assignments or [])

    if int(shift.seats_requested or 1) != 1:
        raise ValueError("single_seat_only_v1")

    expected_assignment_id = payload.expected_assignment_id
    current_assignment_id = current.id if current is not None else None
    if expected_assignment_id != current_assignment_id:
        raise ShiftAssignmentConflictError(current)

    if payload.employee_id is None:
        if current is None:
            return ShiftAssignmentMutationResult(
                shift=shift,
                action="noop",
                source=payload.source,
                previous_assignment=None,
                current_assignment=None,
                cancelled_cases=[],
                cancelled_offers=[],
                no_op=True,
            )

        cancelled_cases, cancelled_offers = await _cancel_active_automation(
            session,
            shift,
            reason="manual_assignment_override",
        )
        now = datetime.now(timezone.utc)
        current.status = AssignmentStatus.cancelled
        current.cancelled_at = now
        current.assignment_metadata = {
            **(current.assignment_metadata or {}),
            "manual_unassigned_at": now.isoformat(),
            "manual_unassigned_note": payload.note,
            "manual_unassigned_source": payload.source,
        }
        _recompute_shift_ownership_state(shift)
        if shift.lifecycle_status == ShiftLifecycleStatus.scheduled:
            shift.lifecycle_status = ShiftLifecycleStatus.draft
        await session.flush()
        return ShiftAssignmentMutationResult(
            shift=shift,
            action="unassigned",
            source=payload.source,
            previous_assignment=current,
            current_assignment=None,
            cancelled_cases=cancelled_cases,
            cancelled_offers=cancelled_offers,
        )

    employee = await _load_employee_for_assignment(session, business_id, payload.employee_id)
    _validate_employee_eligibility(employee, shift)

    if current is not None and current.employee_id == employee.id:
        return ShiftAssignmentMutationResult(
            shift=shift,
            action="noop",
            source=payload.source,
            previous_assignment=current,
            current_assignment=current,
            cancelled_cases=[],
            cancelled_offers=[],
            no_op=True,
        )

    cancelled_cases, cancelled_offers = await _cancel_active_automation(
        session,
        shift,
        reason="manual_assignment_override",
    )
    now = datetime.now(timezone.utc)
    next_sequence_no = _next_assignment_sequence_no(shift)
    previous_assignment = current
    if current is not None:
        current.status = AssignmentStatus.replaced
        current.assignment_metadata = {
            **(current.assignment_metadata or {}),
            "replaced_at": now.isoformat(),
            "replaced_via": payload.source,
            "replacement_note": payload.note,
        }

    assignment = ShiftAssignment(
        shift_id=shift.id,
        employee_id=employee.id,
        assigned_by_user_id=assigned_by_user_id,
        replaced_assignment_id=current.id if current is not None else None,
        assigned_via=payload.source,
        status=AssignmentStatus.assigned,
        sequence_no=next_sequence_no,
        assignment_metadata={
            "note": payload.note,
            "source": payload.source,
            "employee_name": employee.full_name,
        },
    )
    assignment.employee = employee
    session.add(assignment)
    shift.assignments.append(assignment)
    _recompute_shift_ownership_state(shift)
    if shift.lifecycle_status == ShiftLifecycleStatus.scheduled:
        shift.lifecycle_status = ShiftLifecycleStatus.draft
    await session.flush()
    return ShiftAssignmentMutationResult(
        shift=shift,
        action="assigned" if current is None else "reassigned",
        source=payload.source,
        previous_assignment=previous_assignment,
        current_assignment=assignment,
        cancelled_cases=cancelled_cases,
        cancelled_offers=cancelled_offers,
    )


async def _load_shift_for_assignment(
    session: AsyncSession,
    business_id: UUID,
    shift_id: UUID,
) -> Shift:
    shift = await session.get(
        Shift,
        shift_id,
        options=(
            selectinload(Shift.location),
            selectinload(Shift.role),
            selectinload(Shift.assignments).selectinload(ShiftAssignment.employee),
            selectinload(Shift.coverage_cases)
            .selectinload(CoverageCase.offers)
            .selectinload(CoverageOffer.attempts)
            .selectinload(CoverageContactAttempt.outbox_event),
            selectinload(Shift.coverage_cases).selectinload(CoverageCase.runs),
        ),
    )
    if shift is None or shift.business_id != business_id:
        raise LookupError("shift_not_found")
    return shift


async def _load_employee_for_assignment(
    session: AsyncSession,
    business_id: UUID,
    employee_id: UUID,
) -> Employee:
    employee = await session.get(
        Employee,
        employee_id,
        options=(
            selectinload(Employee.employee_roles).selectinload(EmployeeRole.role),
            selectinload(Employee.employee_locations).selectinload(EmployeeLocation.location),
        ),
    )
    if employee is None or employee.business_id != business_id:
        raise LookupError("employee_not_found")
    return employee


def _validate_employee_eligibility(employee: Employee, shift: Shift) -> None:
    if employee.status != EmployeeStatus.active:
        raise ValueError("employee_not_active")
    if shift.role_id not in {assignment.role_id for assignment in (employee.employee_roles or [])}:
        raise ValueError("employee_missing_shift_role")
    employee_location = next(
        (
            record
            for record in (employee.employee_locations or [])
            if record.location_id == shift.location_id
        ),
        None,
    )
    if employee_location is None:
        raise ValueError("employee_missing_location_eligibility")
    if employee_location.access_level not in _USABLE_LOCATION_ACCESS_LEVELS:
        raise ValueError("employee_location_not_usable")


def _next_assignment_sequence_no(shift: Shift) -> int:
    existing = [int(assignment.sequence_no or 0) for assignment in (shift.assignments or [])]
    return (max(existing) if existing else 0) + 1


def _recompute_shift_ownership_state(shift: Shift) -> None:
    current = shift_assignments.current_assignment(shift.assignments or [])
    shift.seats_filled = 1 if current is not None else 0
    if current is not None:
        shift.staffing_status = ShiftStaffingStatus.covered
        return
    has_active_automation = any(
        coverage_case.status in _ACTIVE_CASE_STATUSES
        for coverage_case in (shift.coverage_cases or [])
    )
    shift.staffing_status = (
        ShiftStaffingStatus.filling if has_active_automation else ShiftStaffingStatus.open
    )


async def _cancel_active_automation(
    session: AsyncSession,
    shift: Shift,
    *,
    reason: str,
) -> tuple[list[CoverageCase], list[CoverageOffer]]:
    now = datetime.now(timezone.utc)
    cancelled_cases: list[CoverageCase] = []
    cancelled_offers: list[CoverageOffer] = []

    for coverage_case in shift.coverage_cases or []:
        if coverage_case.status not in _ACTIVE_CASE_STATUSES:
            continue
        case_cancelled_offer_ids: list[str] = []
        for offer in coverage_case.offers or []:
            if offer.status not in _ACTIVE_OFFER_STATUSES:
                continue
            offer.status = OfferStatus.cancelled
            offer.offer_metadata = {
                **(offer.offer_metadata or {}),
                "manual_override_reason": reason,
                "manual_override_cancelled_at": now.isoformat(),
            }
            latest_attempt = _latest_attempt(offer)
            if latest_attempt is not None:
                await delivery.mark_offer_attempt_outcome(
                    session,
                    offer,
                    status=CoverageAttemptStatus.cancelled,
                    occurred_at=now,
                    response_payload={"manual_override_reason": reason},
                )
                if latest_attempt.outbox_event is not None and latest_attempt.outbox_event.status in {
                    OutboxStatus.pending,
                    OutboxStatus.processing,
                }:
                    worker_runtime.mark_outbox_event_cancelled(
                        latest_attempt.outbox_event,
                        now=now,
                        error_message=reason,
                        result_payload={"manual_override_reason": reason},
                    )
            cancelled_offers.append(offer)
            case_cancelled_offer_ids.append(str(offer.id))

        if case_cancelled_offer_ids:
            await _cancel_offer_outbox_events(
                session,
                [UUID(offer_id) for offer_id in case_cancelled_offer_ids],
                now=now,
                reason=reason,
            )

        for run in coverage_case.runs or []:
            if run.status not in _ACTIVE_RUN_STATUSES:
                continue
            run.status = CoverageRunStatus.cancelled
            run.finished_at = now
            run.run_metadata = {
                **(run.run_metadata or {}),
                "cancel_reason": reason,
                "cancelled_at": now.isoformat(),
            }

        coverage_case.status = CoverageCaseStatus.cancelled
        coverage_case.closed_at = now
        coverage_case.case_metadata = {
            **(coverage_case.case_metadata or {}),
            "manual_override_reason": reason,
            "manual_override_cancelled_at": now.isoformat(),
            "manual_override_cancelled_offer_ids": case_cancelled_offer_ids,
        }
        cancelled_cases.append(coverage_case)

    return cancelled_cases, cancelled_offers


async def _cancel_offer_outbox_events(
    session: AsyncSession,
    offer_ids: list[UUID],
    *,
    now: datetime,
    reason: str,
) -> None:
    if not offer_ids:
        return
    result = await session.execute(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_type == "coverage_offer",
            OutboxEvent.aggregate_id.in_(offer_ids),
            OutboxEvent.topic == "coverage.offer.created",
            OutboxEvent.status.in_([OutboxStatus.pending, OutboxStatus.processing]),
        )
    )
    for event in result.scalars().all():
        worker_runtime.mark_outbox_event_cancelled(
            event,
            now=now,
            error_message=reason,
            result_payload={"manual_override_reason": reason},
        )


def _latest_attempt(offer: CoverageOffer) -> CoverageContactAttempt | None:
    attempts = list(getattr(offer, "attempts", []) or [])
    if not attempts:
        return None
    return max(
        attempts,
        key=lambda attempt: (
            int(getattr(attempt, "attempt_no", 0) or 0),
            getattr(attempt, "requested_at", None) or datetime.min.replace(tzinfo=timezone.utc),
        ),
    )
