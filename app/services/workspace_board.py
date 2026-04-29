from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.business import Business, Location, LocationRole, Role
from app.models.common import AssignmentStatus, CoverageCaseStatus, MembershipRole, OfferStatus, ShiftLifecycleStatus
from app.models.coverage import CoverageCase, CoverageOffer
from app.models.events import PlatformEvent
from app.models.scheduling import Shift, ShiftAssignment
from app.models.workforce import Employee, EmployeeRole
from app.schemas.workspace_board import (
    WorkspaceBoardActionSummaryRead,
    WorkspaceBoardPublishSummaryRead,
    WorkspaceBoardRoleRead,
    WorkspaceBoardShiftAssignmentRead,
    WorkspaceBoardShiftRead,
    WorkspaceBoardWorkerRead,
    WorkspaceLocationBoardRead,
)
from app.services import platform_events
from app.services.schedule_weeks import effective_week_start_day, schedule_week_window
from app.services import shift_assignments as shift_assignment_service


READ_ROLES = {
    MembershipRole.owner,
    MembershipRole.admin,
    MembershipRole.manager,
    MembershipRole.viewer,
}
_PUBLISHED_AMENDMENT_METADATA_KEY = "published_amendment"
_SHIFT_HISTORICAL_ARTIFACTS_KEY = "historical_artifacts"


def board_window(timezone_name: str, week_start_day: str | date | None, week_start: date | None = None):
    return schedule_week_window(timezone_name, week_start_day, week_start)

def _to_float(value: Decimal | float | int | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def _best_assignment(shift: Shift) -> ShiftAssignment | None:
    return shift_assignment_service.current_assignment(shift.assignments or [])


def _assignment_employee_name(assignment: ShiftAssignment | None) -> str | None:
    if assignment is None:
        return None
    if assignment.employee is not None and assignment.employee.full_name:
        return assignment.employee.full_name
    metadata = assignment.assignment_metadata or {}
    if isinstance(metadata, dict):
        raw_name = metadata.get("employee_name")
        if isinstance(raw_name, str):
            name = raw_name.strip()
            if name:
                return name
    return None


def _assignment_compliance_metadata(assignment: ShiftAssignment | None) -> dict:
    metadata = _assignment_metadata(assignment)
    raw = metadata.get("compliance_evaluation")
    return dict(raw) if isinstance(raw, dict) else {}


def _assignment_read(assignment: ShiftAssignment | None) -> WorkspaceBoardShiftAssignmentRead | None:
    if assignment is None:
        return None
    compliance_metadata = _assignment_compliance_metadata(assignment)
    return WorkspaceBoardShiftAssignmentRead(
        assignment_id=assignment.id,
        employee_id=assignment.employee_id,
        employee_name=_assignment_employee_name(assignment),
        status=assignment.status.value if hasattr(assignment.status, "value") else str(assignment.status),
        assigned_via=assignment.assigned_via,
        accepted_at=assignment.accepted_at,
        compliance_status=(
            str(compliance_metadata.get("status")).strip()
            if str(compliance_metadata.get("status") or "").strip()
            else None
        ),
        compliance_profile_code=(
            str(compliance_metadata.get("profile_code")).strip()
            if str(compliance_metadata.get("profile_code") or "").strip()
            else None
        ),
        compliance_blocking_rule_codes=[
            str(rule_code).strip()
            for rule_code in (compliance_metadata.get("blocking_rule_codes") or [])
            if str(rule_code).strip()
        ],
        compliance_warning_rule_codes=[
            str(rule_code).strip()
            for rule_code in (compliance_metadata.get("warning_rule_codes") or [])
            if str(rule_code).strip()
        ],
        compliance_premium_rule_codes=[
            str(rule_code).strip()
            for rule_code in (compliance_metadata.get("premium_rule_codes") or [])
            if str(rule_code).strip()
        ],
        compliance_premium_total_cents=max(0, int(compliance_metadata.get("premium_total_cents") or 0)),
        compliance_unresolved_premium_rule_codes=[
            str(rule_code).strip()
            for rule_code in (compliance_metadata.get("unresolved_premium_rule_codes") or [])
            if str(rule_code).strip()
        ],
        compliance_override_applied=bool(compliance_metadata.get("override_applied")),
        compliance_override_artifact_id=(
            str(compliance_metadata.get("override_artifact_id")).strip()
            if str(compliance_metadata.get("override_artifact_id") or "").strip()
            else None
        ),
    )


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


def _shift_lifecycle_status_value(shift: Shift) -> str:
    lifecycle_status = shift.lifecycle_status
    return lifecycle_status.value if hasattr(lifecycle_status, "value") else str(lifecycle_status)


def _shift_display_employee_id(shift: Shift) -> UUID | None:
    current = _best_assignment(shift)
    if current is not None and current.employee_id is not None:
        return current.employee_id
    latest = shift_assignment_service.latest_assignment(shift.assignments or [])
    return latest.employee_id if latest is not None else None


def _shift_metadata_value(shift: Shift, key: str) -> object | None:
    shift_metadata = shift.shift_metadata if isinstance(shift.shift_metadata, dict) else {}
    return shift_metadata.get(key)


def _shift_amendment_metadata(shift: Shift) -> dict:
    shift_metadata = shift.shift_metadata if isinstance(shift.shift_metadata, dict) else {}
    raw = shift_metadata.get(_PUBLISHED_AMENDMENT_METADATA_KEY)
    return dict(raw) if isinstance(raw, dict) else {}


def _inferred_live_schedule_break_reason_code(shift: Shift) -> str | None:
    if _shift_lifecycle_status_value(shift) not in {
        ShiftLifecycleStatus.scheduled.value,
        ShiftLifecycleStatus.in_progress.value,
    }:
        return None
    current_assignment = _best_assignment(shift)
    if current_assignment is not None:
        return None
    latest_assignment = shift_assignment_service.latest_assignment(shift.assignments or [])
    status_value = _assignment_status_value(latest_assignment)
    if status_value == AssignmentStatus.no_show.value:
        return "no_show"
    if status_value == AssignmentStatus.cancelled.value and shift.seats_filled < shift.seats_requested:
        return "callout"
    return None


def _shift_amended_from_published(shift: Shift) -> bool:
    metadata = _shift_amendment_metadata(shift)
    if metadata.get("amended_from_published") is not None:
        return bool(metadata.get("amended_from_published"))
    return _inferred_live_schedule_break_reason_code(shift) is not None


def _shift_amendment_reason_code(shift: Shift) -> str | None:
    raw_reason = _shift_amendment_metadata(shift).get("reason_code")
    if isinstance(raw_reason, str) and raw_reason:
        return raw_reason
    return _inferred_live_schedule_break_reason_code(shift)


def _shift_schedule_break(shift: Shift) -> bool:
    metadata = _shift_amendment_metadata(shift)
    if metadata.get("schedule_break") is not None:
        return bool(metadata.get("schedule_break"))
    return _inferred_live_schedule_break_reason_code(shift) is not None


def _shift_amended_employee_ids(shift: Shift) -> list[UUID]:
    raw_value = _shift_amendment_metadata(shift).get("amended_employee_ids")
    employee_ids: list[UUID] = []
    if isinstance(raw_value, list):
        for raw_id in raw_value:
            try:
                employee_ids.append(raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id)))
            except (TypeError, ValueError):
                continue
    if employee_ids:
        return employee_ids
    if _inferred_live_schedule_break_reason_code(shift) is None:
        return []
    latest_assignment = shift_assignment_service.latest_assignment(shift.assignments or [])
    if latest_assignment is None or latest_assignment.employee_id is None:
        return []
    return [latest_assignment.employee_id]


def _shift_historical_artifacts(shift: Shift) -> list[dict]:
    raw_value = _shift_amendment_metadata(shift).get(_SHIFT_HISTORICAL_ARTIFACTS_KEY)
    if not isinstance(raw_value, list):
        return []
    return [dict(entry) for entry in raw_value if isinstance(entry, dict)]


def _assignment_metadata(assignment: ShiftAssignment | None) -> dict:
    if assignment is None:
        return {}
    raw_metadata = assignment.assignment_metadata
    return dict(raw_metadata) if isinstance(raw_metadata, dict) else {}


def _assignment_amendment_reason_code(assignment: ShiftAssignment | None) -> str | None:
    raw_reason = _assignment_metadata(assignment).get("published_amendment_reason_code")
    if isinstance(raw_reason, str) and raw_reason:
        return raw_reason
    return None


def _assignment_amendment_action(assignment: ShiftAssignment | None) -> str | None:
    raw_action = _assignment_metadata(assignment).get("published_amendment_action")
    if isinstance(raw_action, str) and raw_action:
        return raw_action
    return None


def _assignment_status_value(assignment: ShiftAssignment | None) -> str | None:
    if assignment is None:
        return None
    status = assignment.status
    return status.value if hasattr(status, "value") else str(status)


def _derived_cancelled_history_reason_code(shift: Shift) -> str | None:
    if _shift_lifecycle_status_value(shift) != ShiftLifecycleStatus.cancelled.value:
        return None
    if _shift_amendment_reason_code(shift) == "cancelled":
        return "cancelled"
    if any(
        _assignment_amendment_reason_code(assignment) in {"cancelled", "callout", "no_show"}
        or _assignment_amendment_action(assignment) in {"cancel_shift", "unassign_shift"}
        for assignment in shift.assignments or []
    ):
        return "cancelled"
    if _shift_metadata_value(shift, "consistency_repair_reason") == "cancelled_shift_owned_assignment_cleanup":
        return "cancelled"
    return None


def _effective_shift_amendment_reason_code(shift: Shift) -> str | None:
    raw_reason = _shift_amendment_reason_code(shift)
    if raw_reason is not None:
        return raw_reason
    return _derived_cancelled_history_reason_code(shift)


def _recovered_shift_historical_artifacts(shift: Shift) -> list[dict]:
    artifacts = _shift_historical_artifacts(shift)
    if artifacts:
        return artifacts
    if _shift_lifecycle_status_value(shift) not in {
        ShiftLifecycleStatus.scheduled.value,
        ShiftLifecycleStatus.in_progress.value,
    }:
        return []
    if _shift_schedule_break(shift):
        return []
    current_assignment = _best_assignment(shift)
    if current_assignment is None:
        return []
    assignments = sorted(
        list(shift.assignments or []),
        key=lambda item: (item.sequence_no or 0, item.created_at or datetime.min),
    )
    for assignment in reversed(assignments):
        if current_assignment is not None and assignment.id == current_assignment.id:
            continue
        reason_code = _assignment_amendment_reason_code(assignment)
        if reason_code not in {"callout", "no_show"}:
            continue
        status = _assignment_status_value(assignment)
        if status not in {AssignmentStatus.cancelled.value, AssignmentStatus.no_show.value}:
            continue
        return [
            {
                "artifact_id": f"recovered-{assignment.id}",
                "employee_id": str(assignment.employee_id) if assignment.employee_id is not None else None,
                "employee_name": _assignment_employee_name(assignment),
                "reason_code": reason_code,
                "starts_at": shift.starts_at.isoformat(),
                "ends_at": shift.ends_at.isoformat(),
                "role_id": str(shift.role_id),
                "role_code": shift.role.code if shift.role is not None else None,
                "role_name": shift.role.name if shift.role is not None else None,
            }
        ]
    return []


def _shift_historical_artifact_employee_ids(shift: Shift) -> list[UUID]:
    employee_ids: list[UUID] = []
    for artifact in _recovered_shift_historical_artifacts(shift):
        raw_employee_id = artifact.get("employee_id")
        if raw_employee_id is None:
            continue
        try:
            employee_ids.append(raw_employee_id if isinstance(raw_employee_id, UUID) else UUID(str(raw_employee_id)))
        except (TypeError, ValueError):
            continue
    return employee_ids


def _latest_timestamp(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if current is None:
        return candidate
    if candidate is None:
        return current
    return max(current, candidate)


def _shift_historical_display(shift: Shift) -> bool:
    return (
        _shift_lifecycle_status_value(shift) == ShiftLifecycleStatus.cancelled.value
        and _effective_shift_amendment_reason_code(shift) == "cancelled"
    )


def _historical_artifact_shift_reads(shift: Shift) -> list[WorkspaceBoardShiftRead]:
    shift_reads: list[WorkspaceBoardShiftRead] = []
    for index, artifact in enumerate(_recovered_shift_historical_artifacts(shift)):
        raw_starts_at = artifact.get("starts_at")
        raw_ends_at = artifact.get("ends_at")
        raw_reason_code = artifact.get("reason_code")
        if not isinstance(raw_starts_at, str) or not isinstance(raw_ends_at, str):
            continue
        if not isinstance(raw_reason_code, str) or not raw_reason_code:
            continue
        try:
            starts_at = datetime.fromisoformat(raw_starts_at)
            ends_at = datetime.fromisoformat(raw_ends_at)
        except ValueError:
            continue
        raw_employee_id = artifact.get("employee_id")
        employee_id: UUID | None = None
        if raw_employee_id is not None:
            try:
                employee_id = raw_employee_id if isinstance(raw_employee_id, UUID) else UUID(str(raw_employee_id))
            except (TypeError, ValueError):
                employee_id = None
        employee_name = artifact.get("employee_name") if isinstance(artifact.get("employee_name"), str) else None
        role_id = shift.role_id
        raw_role_id = artifact.get("role_id")
        if raw_role_id is not None:
            try:
                role_id = raw_role_id if isinstance(raw_role_id, UUID) else UUID(str(raw_role_id))
            except (TypeError, ValueError):
                role_id = shift.role_id
        role_code = artifact.get("role_code") if isinstance(artifact.get("role_code"), str) else shift.role.code
        role_name = artifact.get("role_name") if isinstance(artifact.get("role_name"), str) else shift.role.name
        artifact_token = artifact.get("artifact_id") if isinstance(artifact.get("artifact_id"), str) else str(index)
        artifact_shift_id = uuid5(shift.id, f"historical:{artifact_token}")
        artifact_assignment_id = uuid5(artifact_shift_id, "last-assignment")
        shift_reads.append(
            WorkspaceBoardShiftRead(
                shift_id=artifact_shift_id,
                role_id=role_id,
                role_code=role_code,
                role_name=role_name,
                starts_at=starts_at,
                ends_at=ends_at,
                lifecycle_status=ShiftLifecycleStatus.cancelled.value,
                staffing_status=(
                    shift.staffing_status.value
                    if hasattr(shift.staffing_status, "value")
                    else str(shift.staffing_status)
                ),
                status=shift.status.value,
                seats_requested=shift.seats_requested,
                seats_filled=0,
                requires_manager_approval=shift.requires_manager_approval,
                premium_cents=shift.premium_cents,
                notes=shift.notes,
                current_assignment=None,
                last_assignment=WorkspaceBoardShiftAssignmentRead(
                    assignment_id=artifact_assignment_id,
                    employee_id=employee_id,
                    employee_name=employee_name,
                    status="no_show" if raw_reason_code == "no_show" else "cancelled",
                    assigned_via="published_amendment",
                    accepted_at=None,
                ),
                coverage_case_id=None,
                coverage_case_status=None,
                pending_offer_count=0,
                delivered_offer_count=0,
                standby_depth=0,
                manager_action_required=False,
                amended_from_published=False,
                amendment_reason_code=raw_reason_code,
                schedule_break=False,
                historical_display=True,
            )
        )
    return shift_reads


async def _build_publish_summary(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
    week_start: date,
    week_end: date,
    workers: list[WorkspaceBoardWorkerRead],
    shifts: list[Shift],
) -> WorkspaceBoardPublishSummaryRead:
    publish_event_rows = await session.execute(
        select(PlatformEvent)
        .where(
            PlatformEvent.business_id == business_id,
            PlatformEvent.location_id == location_id,
            PlatformEvent.event_type == platform_events.PlatformEventType.SCHEDULE_WEEK_PUBLISHED,
        )
        .order_by(PlatformEvent.occurred_at.desc())
        .limit(50)
    )
    publish_events = list(publish_event_rows.scalars().all())
    published_event = next(
        (
            entry
            for entry in publish_events
            if isinstance(entry.payload, dict)
            and entry.payload.get("week_start_date") == week_start.isoformat()
            and entry.payload.get("week_end_date") == week_end.isoformat()
        ),
        None,
    )
    if published_event is None:
        return WorkspaceBoardPublishSummaryRead()

    published_at = published_event.occurred_at
    published_shift_ids: set[UUID] = set()
    amended_shift_ids: set[UUID] = set()
    published_employee_ids: set[UUID] = set()
    amended_employee_ids: set[UUID] = set()
    amended_at: datetime | None = None

    amended_event_rows = await session.execute(
        select(PlatformEvent)
        .where(
            PlatformEvent.business_id == business_id,
            PlatformEvent.location_id == location_id,
            PlatformEvent.event_type == platform_events.PlatformEventType.SCHEDULE_WEEK_AMENDED,
            PlatformEvent.occurred_at > published_at,
        )
        .order_by(PlatformEvent.occurred_at.desc())
        .limit(100)
    )
    amended_events = list(amended_event_rows.scalars().all())
    matching_amended_events = [
        entry
        for entry in amended_events
        if isinstance(entry.payload, dict)
        and entry.payload.get("week_start_date") == week_start.isoformat()
        and entry.payload.get("week_end_date") == week_end.isoformat()
    ]
    if matching_amended_events:
        amended_at = matching_amended_events[0].occurred_at

    for shift in shifts:
        employee_id = _shift_display_employee_id(shift)
        if _shift_amended_from_published(shift):
            amended_shift_ids.add(shift.id)
            for amended_employee_id in _shift_amended_employee_ids(shift):
                amended_employee_ids.add(amended_employee_id)
            if employee_id is not None:
                amended_employee_ids.add(employee_id)
            amended_at = _latest_timestamp(amended_at, shift.updated_at or shift.created_at)
            continue

        lifecycle_status = _shift_lifecycle_status_value(shift)
        if lifecycle_status in {
            ShiftLifecycleStatus.scheduled.value,
            ShiftLifecycleStatus.in_progress.value,
        }:
            published_shift_ids.add(shift.id)
            if employee_id is not None:
                published_employee_ids.add(employee_id)
            for historical_employee_id in _shift_historical_artifact_employee_ids(shift):
                published_employee_ids.add(historical_employee_id)
            continue

        if _shift_historical_display(shift):
            if employee_id is not None:
                published_employee_ids.add(employee_id)
            continue

        if lifecycle_status == ShiftLifecycleStatus.draft.value:
            amended_shift_ids.add(shift.id)
            if employee_id is not None:
                amended_employee_ids.add(employee_id)
            amended_at = _latest_timestamp(amended_at, shift.updated_at or shift.created_at)

    state = "amended" if amended_at is not None or amended_shift_ids or amended_employee_ids else "published"
    return WorkspaceBoardPublishSummaryRead(
        state=state,
        published_at=published_at,
        amended_at=amended_at,
        published_shift_ids=sorted(published_shift_ids, key=str),
        amended_shift_ids=sorted(amended_shift_ids, key=str),
        published_employee_ids=sorted(published_employee_ids, key=str),
        amended_employee_ids=sorted(amended_employee_ids, key=str),
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
    location_settings = location.settings if isinstance(location.settings, dict) else {}
    business_settings = business.settings if isinstance(business.settings, dict) else {}
    window = schedule_week_window(
        location.timezone,
        effective_week_start_day(
            business_settings=business_settings,
            location_settings=location_settings,
        ),
        week_start,
    )

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
            selectinload(Employee.employee_locations),
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
        employee_location = next(
            (
                item
                for item in (employee.employee_locations or [])
                if item.location_id == location_id
            ),
            None,
        )
        primary_location_id = employee.primary_location_id
        can_cover_here = employee_location is not None
        can_blast_here = bool(employee_location.can_blast) if employee_location is not None else False
        workers.append(
            WorkspaceBoardWorkerRead(
                employee_id=employee.id,
                full_name=employee.full_name,
                preferred_name=employee.preferred_name,
                phone_e164=employee.phone_e164,
                email=employee.email,
                primary_location_id=primary_location_id,
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
        last_assignment = shift_assignment_service.latest_assignment(shift.assignments or [])
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
                lifecycle_status=(
                    shift.lifecycle_status.value
                    if hasattr(shift.lifecycle_status, "value")
                    else str(shift.lifecycle_status)
                ),
                staffing_status=(
                    shift.staffing_status.value
                    if hasattr(shift.staffing_status, "value")
                    else str(shift.staffing_status)
                ),
                status=shift.status.value,
                seats_requested=shift.seats_requested,
                seats_filled=shift.seats_filled,
                requires_manager_approval=shift.requires_manager_approval,
                premium_cents=shift.premium_cents,
                notes=shift.notes,
                current_assignment=_assignment_read(current_assignment),
                last_assignment=_assignment_read(last_assignment),
                coverage_case_id=latest_case.id if latest_case is not None else None,
                coverage_case_status=latest_case.status.value if latest_case is not None else None,
                pending_offer_count=pending_offer_count,
                delivered_offer_count=delivered_offer_count,
                standby_depth=standby_depth,
                manager_action_required=manager_action_required,
                amended_from_published=_shift_amended_from_published(shift),
                amendment_reason_code=_effective_shift_amendment_reason_code(shift),
                schedule_break=_shift_schedule_break(shift),
                historical_display=_shift_historical_display(shift),
            )
        )
        shift_reads.extend(_historical_artifact_shift_reads(shift))

    shift_reads.sort(key=lambda item: (item.starts_at, item.role_name, str(item.shift_id)))

    publish_summary = await _build_publish_summary(
        session,
        business_id=business_id,
        location_id=location_id,
        week_start=window.week_start,
        week_end=window.week_end,
        workers=workers,
        shifts=shifts,
    )
    business_name = business.display_name
    location_role_setup_required = not bool(location_roles)
    location_employee_setup_required = not any(worker.can_cover_here for worker in workers)
    return WorkspaceLocationBoardRead(
        business_id=business.id,
        business_name=business_name,
        business_slug=business.slug,
        location_id=location.id,
        location_name=location.display_name,
        location_slug=location.slug,
        address_line_1=location.address_line_1,
        locality=location.locality,
        region=location.region,
        postal_code=location.postal_code,
        country_code=location.country_code,
        timezone=location.timezone,
        week_start_date=window.week_start,
        week_end_date=window.week_end,
        location_role_setup_required=location_role_setup_required,
        location_employee_setup_required=location_employee_setup_required,
        location_setup_required=(
            location_role_setup_required or location_employee_setup_required
        ),
        roles=roles,
        available_roles=available_roles,
        workers=workers,
        shifts=shift_reads,
        publish_summary=publish_summary,
        action_summary=WorkspaceBoardActionSummaryRead(
            total=approval_required + active_coverage,
            approval_required=approval_required,
            active_coverage=active_coverage,
            open_shifts=open_shifts,
        ),
    )
