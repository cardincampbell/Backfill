from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from statistics import mean
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.auto_scheduler import ReplayRun, ScheduleRun
from app.models.common import AssignmentStatus, ScheduleRunStatus
from app.models.scheduling import Shift, ShiftAssignment
from app.services.auto_scheduler import stable_payload_hash

_ACTIVE_ASSIGNMENT_STATUSES = {
    AssignmentStatus.assigned.value,
    AssignmentStatus.accepted.value,
    AssignmentStatus.completed.value,
    AssignmentStatus.no_show.value,
}
_EXCLUDED_ASSIGNMENT_STATUSES = {
    AssignmentStatus.cancelled.value,
    AssignmentStatus.replaced.value,
    AssignmentStatus.declined.value,
}


def build_shift_duration_hours_map(shift_payload: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> dict[str, float]:
    shifts = _extract_payload_rows(shift_payload, list_key="shifts")
    duration_by_shift_id: dict[str, float] = {}
    for row in shifts:
        shift_id = str(row.get("shift_id") or row.get("id") or "").strip()
        if not shift_id:
            continue
        starts_at = _parse_datetime(row.get("starts_at"))
        ends_at = _parse_datetime(row.get("ends_at"))
        if starts_at is None or ends_at is None or ends_at <= starts_at:
            duration_by_shift_id[shift_id] = 0.0
            continue
        duration_by_shift_id[shift_id] = round((ends_at - starts_at).total_seconds() / 3600.0, 4)
    return duration_by_shift_id


def calculate_replay_metrics(
    *,
    proposed_assignments: Sequence[Mapping[str, Any]],
    actual_assignments: Sequence[Mapping[str, Any]],
    shift_duration_hours_by_shift_id: Mapping[str, float],
) -> dict[str, Any]:
    shift_ids = set(shift_duration_hours_by_shift_id.keys())
    if not shift_ids:
        shift_ids = {
            str(row.get("shift_id") or "")
            for row in proposed_assignments
            if row.get("shift_id")
        } | {
            str(row.get("shift_id") or "")
            for row in actual_assignments
            if row.get("shift_id")
        }

    proposed_by_shift = _selected_assignment_by_shift(proposed_assignments)
    actual_by_shift = _selected_assignment_by_shift(actual_assignments)
    shift_count = len(shift_ids)
    matched_assignment_count = sum(
        1
        for shift_id in shift_ids
        if _employee_id_for_row(proposed_by_shift.get(shift_id))
        and _employee_id_for_row(proposed_by_shift.get(shift_id)) == _employee_id_for_row(actual_by_shift.get(shift_id))
    )
    assignment_match_rate = (
        round(matched_assignment_count / shift_count, 4)
        if shift_count > 0
        else 1.0
    )

    proposed_hours = _hours_by_employee(
        assignments=proposed_assignments,
        shift_duration_hours_by_shift_id=shift_duration_hours_by_shift_id,
    )
    actual_hours = _hours_by_employee(
        assignments=actual_assignments,
        shift_duration_hours_by_shift_id=shift_duration_hours_by_shift_id,
    )
    proposed_outcomes = _proposed_assignment_outcomes(
        proposed_by_shift=proposed_by_shift,
        actual_by_shift=actual_by_shift,
        shift_ids=shift_ids,
    )
    override_count = sum(
        1
        for shift_id in shift_ids
        if _employee_id_for_row(proposed_by_shift.get(shift_id)) != _employee_id_for_row(actual_by_shift.get(shift_id))
    )
    uncovered_shift_count = sum(
        1 for shift_id in shift_ids if _employee_id_for_row(proposed_by_shift.get(shift_id)) is None
    )
    projected_ot_hours = round(
        sum(_projected_ot_hours(row) for row in proposed_assignments),
        4,
    )

    return {
        "assignment_match_rate": assignment_match_rate,
        "matched_assignment_count": matched_assignment_count,
        "shift_count": shift_count,
        "attendance_outcomes_on_proposed_assignments": proposed_outcomes,
        "overtime_exposure": {
            "projected_ot_hours": projected_ot_hours,
        },
        "fairness_spread": {
            "proposed": _fairness_spread_metrics(proposed_hours),
            "actual": _fairness_spread_metrics(actual_hours),
        },
        "uncovered_shift_count": uncovered_shift_count,
        "operator_override_delta": {
            "override_count": override_count,
            "override_rate": round(override_count / shift_count, 4) if shift_count > 0 else 0.0,
        },
    }


def build_actual_schedule_snapshot_hash(actual_schedule_payload: Mapping[str, Any]) -> str:
    return stable_payload_hash(
        {
            "shift_count": actual_schedule_payload.get("shift_count"),
            "shifts": _extract_payload_rows(actual_schedule_payload, list_key="shifts"),
            "assignments": _extract_payload_rows(actual_schedule_payload, list_key="assignments"),
        }
    )


async def load_actual_schedule_payload(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None,
    planning_window_start: datetime,
    planning_window_end: datetime,
) -> dict[str, Any]:
    shift_stmt = select(Shift).where(
        Shift.business_id == business_id,
        Shift.starts_at >= planning_window_start,
        Shift.starts_at < planning_window_end,
    )
    if location_id is not None:
        shift_stmt = shift_stmt.where(Shift.location_id == location_id)
    shift_result = await session.execute(shift_stmt.order_by(Shift.starts_at.asc(), Shift.id.asc()))
    shifts = list(shift_result.scalars().all())
    shift_ids = [shift.id for shift in shifts]

    assignments: list[ShiftAssignment] = []
    if shift_ids:
        assignment_result = await session.execute(
            select(ShiftAssignment)
            .where(ShiftAssignment.shift_id.in_(shift_ids))
            .order_by(ShiftAssignment.created_at.asc(), ShiftAssignment.id.asc())
        )
        assignments = list(assignment_result.scalars().all())

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "shift_count": len(shifts),
        "shifts": [
            {
                "shift_id": str(shift.id),
                "location_id": str(shift.location_id),
                "role_id": str(shift.role_id),
                "starts_at": shift.starts_at.isoformat(),
                "ends_at": shift.ends_at.isoformat(),
                "lifecycle_status": str(shift.lifecycle_status.value),
                "staffing_status": str(shift.staffing_status.value),
            }
            for shift in shifts
        ],
        "assignments": [
            {
                "assignment_id": str(assignment.id),
                "shift_id": str(assignment.shift_id),
                "employee_id": str(assignment.employee_id) if assignment.employee_id else None,
                "status": str(assignment.status.value),
                "assigned_via": assignment.assigned_via,
                "replaced_assignment_id": (
                    str(assignment.replaced_assignment_id)
                    if assignment.replaced_assignment_id
                    else None
                ),
            }
            for assignment in assignments
        ],
    }


async def create_replay_run(
    session: AsyncSession,
    *,
    schedule_run_id: UUID,
    replay_metadata: Mapping[str, Any] | None = None,
) -> ReplayRun:
    schedule_run = await _load_schedule_run(session, schedule_run_id)
    if schedule_run.status != ScheduleRunStatus.completed:
        raise ValueError("replay_requires_completed_schedule_run")
    if schedule_run.inputs is None:
        raise ValueError("replay_requires_schedule_run_inputs")

    proposed_assignments = [
        {
            "shift_id": str(assignment.shift_id) if assignment.shift_id else None,
            "employee_id": str(assignment.employee_id) if assignment.employee_id else None,
            "decision_rank": assignment.decision_rank,
            "decision_score": float(assignment.decision_score),
            "assignment_payload": dict(assignment.assignment_payload or {}),
        }
        for assignment in schedule_run.assignments
    ]
    actual_assignment_payload = await load_actual_schedule_payload(
        session,
        business_id=schedule_run.business_id,
        location_id=schedule_run.location_id,
        planning_window_start=schedule_run.planning_window_start,
        planning_window_end=schedule_run.planning_window_end,
    )
    shift_duration_hours = build_shift_duration_hours_map(schedule_run.inputs.shift_payload)
    metrics_payload = calculate_replay_metrics(
        proposed_assignments=proposed_assignments,
        actual_assignments=_extract_payload_rows(actual_assignment_payload, list_key="assignments"),
        shift_duration_hours_by_shift_id=shift_duration_hours,
    )
    actual_outcome_payload = {
        "actual_assignment_status_counts": _status_counts(
            _extract_payload_rows(actual_assignment_payload, list_key="assignments")
        ),
    }
    now = datetime.now(timezone.utc)
    replay_run = ReplayRun(
        schedule_run_id=schedule_run.id,
        business_id=schedule_run.business_id,
        location_id=schedule_run.location_id,
        planning_window_start=schedule_run.planning_window_start,
        planning_window_end=schedule_run.planning_window_end,
        status=ScheduleRunStatus.completed,
        comparison_version="v1",
        target_snapshot_hash=schedule_run.input_snapshot_hash,
        actual_snapshot_hash=build_actual_schedule_snapshot_hash(actual_assignment_payload),
        actual_assignment_payload=actual_assignment_payload,
        actual_outcome_payload=actual_outcome_payload,
        metrics_payload=metrics_payload,
        replay_metadata=dict(replay_metadata or {}),
        started_at=now,
        completed_at=now,
    )
    session.add(replay_run)
    await session.flush()
    return replay_run


async def _load_schedule_run(session: AsyncSession, schedule_run_id: UUID) -> ScheduleRun:
    result = await session.execute(
        select(ScheduleRun)
        .where(ScheduleRun.id == schedule_run_id)
        .options(
            selectinload(ScheduleRun.inputs),
            selectinload(ScheduleRun.assignments),
        )
    )
    schedule_run = result.scalar_one_or_none()
    if schedule_run is None:
        raise ValueError("schedule_run_not_found")
    return schedule_run


def _extract_payload_rows(
    payload: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    list_key: str,
) -> list[dict[str, Any]]:
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        raw_rows = payload.get(list_key)
        if isinstance(raw_rows, Sequence) and not isinstance(raw_rows, (str, bytes, bytearray)):
            return [dict(row) for row in raw_rows if isinstance(row, Mapping)]
    return []


def _selected_assignment_by_shift(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    selected: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        shift_id = str(row.get("shift_id") or "").strip()
        if not shift_id:
            continue
        status = str(row.get("status") or "").strip().lower()
        if status in _EXCLUDED_ASSIGNMENT_STATUSES:
            continue
        existing = selected.get(shift_id)
        if existing is None or _assignment_sort_key(row) < _assignment_sort_key(existing):
            selected[shift_id] = row
    return selected


def _assignment_sort_key(row: Mapping[str, Any]) -> tuple[int, str]:
    status = str(row.get("status") or "").strip().lower()
    if status in _ACTIVE_ASSIGNMENT_STATUSES:
        priority = 0
    elif status:
        priority = 1
    else:
        priority = 2
    return (priority, str(row.get("assignment_id") or ""))


def _employee_id_for_row(row: Mapping[str, Any] | None) -> str | None:
    if not isinstance(row, Mapping):
        return None
    value = row.get("employee_id")
    if value in (None, ""):
        return None
    return str(value)


def _hours_by_employee(
    *,
    assignments: Sequence[Mapping[str, Any]],
    shift_duration_hours_by_shift_id: Mapping[str, float],
) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in assignments:
        employee_id = _employee_id_for_row(row)
        if employee_id is None:
            continue
        status = str(row.get("status") or "").strip().lower()
        if status in _EXCLUDED_ASSIGNMENT_STATUSES:
            continue
        shift_id = str(row.get("shift_id") or "").strip()
        totals[employee_id] = round(
            totals.get(employee_id, 0.0) + float(shift_duration_hours_by_shift_id.get(shift_id, 0.0)),
            4,
        )
    return totals


def _fairness_spread_metrics(hours_by_employee: Mapping[str, float]) -> dict[str, Any]:
    if not hours_by_employee:
        return {
            "employee_count": 0,
            "min_hours": 0.0,
            "max_hours": 0.0,
            "avg_hours": 0.0,
            "spread_hours": 0.0,
        }
    hours = list(hours_by_employee.values())
    min_hours = min(hours)
    max_hours = max(hours)
    return {
        "employee_count": len(hours),
        "min_hours": round(min_hours, 4),
        "max_hours": round(max_hours, 4),
        "avg_hours": round(mean(hours), 4),
        "spread_hours": round(max_hours - min_hours, 4),
    }


def _proposed_assignment_outcomes(
    *,
    proposed_by_shift: Mapping[str, Mapping[str, Any]],
    actual_by_shift: Mapping[str, Mapping[str, Any]],
    shift_ids: set[str],
) -> dict[str, int]:
    outcomes: dict[str, int] = {}
    for shift_id in shift_ids:
        proposed_row = proposed_by_shift.get(shift_id)
        actual_row = actual_by_shift.get(shift_id)
        proposed_employee_id = _employee_id_for_row(proposed_row)
        actual_employee_id = _employee_id_for_row(actual_row)
        if proposed_employee_id is None:
            outcomes["unfilled"] = outcomes.get("unfilled", 0) + 1
            continue
        if actual_row is None:
            outcomes["unmatched"] = outcomes.get("unmatched", 0) + 1
            continue
        if proposed_employee_id != actual_employee_id:
            outcomes["reassigned_elsewhere"] = outcomes.get("reassigned_elsewhere", 0) + 1
            continue
        status = str(actual_row.get("status") or "unknown").strip().lower()
        outcomes[status] = outcomes.get(status, 0) + 1
    return dict(sorted(outcomes.items()))


def _projected_ot_hours(row: Mapping[str, Any]) -> float:
    assignment_payload = row.get("assignment_payload")
    if not isinstance(assignment_payload, Mapping):
        return 0.0
    labor_projection = assignment_payload.get("labor_projection")
    if isinstance(labor_projection, Mapping):
        value = labor_projection.get("projected_ot_hours")
        if isinstance(value, (int, float)):
            return float(value)
    value = assignment_payload.get("projected_ot_hours")
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _status_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "unknown").strip().lower()
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None
