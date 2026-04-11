from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.common import AssignmentStatus, CoverageAttemptStatus, CoverageCaseStatus, EmployeeStatus
from app.models.coverage import CoverageCase, CoverageContactAttempt
from app.models.scheduling import Shift, ShiftAssignment
from app.models.workforce import Employee
from app.schemas.coverage import CoverageCandidatePreview
from app.services import delivery

SCORE_SNAPSHOT_STALE_AFTER = timedelta(minutes=15)
CONTACT_COOLDOWN_HARD = timedelta(minutes=15)
CONTACT_COOLDOWN_SOFT = timedelta(hours=2)
RECENT_BURDEN_WINDOW = timedelta(days=7)
OVERTIME_LOOKBACK_WINDOW = timedelta(days=7)
_ENGINE_RUNTIME_SOURCE = "authoring_tables"
_SCORE_SNAPSHOT_SOURCE = "employee.response_profile"
_PROJECTION_BLOCK_MIN_EMPLOYEE_COUNT = 5
_PROJECTION_BLOCK_STALE_RATIO = 0.5


def _normalize_datetime(value: object | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _score_snapshot_state_from_profile(
    profile: dict[str, object] | None,
    *,
    now: datetime,
) -> dict[str, object]:
    updated_at = _normalize_datetime(profile.get("updated_at"))
    if updated_at is None:
        return {
            "source": _SCORE_SNAPSHOT_SOURCE,
            "status": "missing",
            "updated_at": None,
            "age_seconds": None,
            "freshness_target_seconds": int(SCORE_SNAPSHOT_STALE_AFTER.total_seconds()),
        }

    age_seconds = max(0, int((now - updated_at).total_seconds()))
    status = "fresh" if age_seconds <= int(SCORE_SNAPSHOT_STALE_AFTER.total_seconds()) else "stale"
    return {
        "source": _SCORE_SNAPSHOT_SOURCE,
        "status": status,
        "updated_at": updated_at.isoformat(),
        "age_seconds": age_seconds,
        "freshness_target_seconds": int(SCORE_SNAPSHOT_STALE_AFTER.total_seconds()),
    }


def score_snapshot_state(
    employee: Employee,
    *,
    now: datetime,
) -> dict[str, object]:
    profile = employee.response_profile if isinstance(employee.response_profile, dict) else {}
    return _score_snapshot_state_from_profile(profile, now=now)


async def refresh_employee_score_snapshots(
    session: AsyncSession,
    employees: Iterable[Employee],
    *,
    now: datetime | None = None,
) -> dict[UUID, dict[str, object]]:
    reference_time = now or datetime.now(timezone.utc)
    employees_list = list(employees)
    states = {
        employee.id: score_snapshot_state(employee, now=reference_time)
        for employee in employees_list
    }

    for employee in employees_list:
        current_state = states.get(employee.id, {})
        if current_state.get("status") not in {"missing", "stale"}:
            continue

        refreshed_employee = await delivery.refresh_employee_reliability(
            session,
            employee.id,
            now=reference_time,
        )
        refreshed_state = score_snapshot_state(
            refreshed_employee or employee,
            now=reference_time,
        )
        refreshed_state["status"] = "refreshed"
        refreshed_state["refreshed_at"] = reference_time.isoformat()
        states[employee.id] = refreshed_state

    return states


async def monitor_runtime_projection_freshness(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    business_limit: int = 25,
) -> dict[str, object]:
    reference_time = now or datetime.now(timezone.utc)
    active_business_result = await session.execute(
        select(Shift.business_id)
        .join(CoverageCase, CoverageCase.shift_id == Shift.id)
        .where(CoverageCase.status.in_([CoverageCaseStatus.queued, CoverageCaseStatus.running]))
        .distinct()
        .limit(max(1, business_limit))
    )
    business_ids: list[object] = []
    for row in active_business_result.all():
        business_id = row[0] if isinstance(row, tuple) else row
        if business_id is not None:
            business_ids.append(business_id)
    if not business_ids:
        return {
            "status": "ready",
            "checked_at": reference_time.isoformat(),
            "freshness_target_seconds": int(SCORE_SNAPSHOT_STALE_AFTER.total_seconds()),
            "monitored_business_count": 0,
            "candidate_employee_count": 0,
            "fresh_employee_count": 0,
            "stale_employee_count": 0,
            "missing_employee_count": 0,
            "blocked_business_count": 0,
            "blocked_business_ids": [],
        }

    employee_result = await session.execute(
        select(Employee.business_id, Employee.response_profile)
        .where(
            Employee.business_id.in_(business_ids),
            Employee.status == EmployeeStatus.active,
        )
    )

    fresh_employee_count = 0
    stale_employee_count = 0
    missing_employee_count = 0
    business_counts: dict[str, dict[str, int]] = {
        str(business_id): {"candidate_employee_count": 0, "stale_or_missing_count": 0}
        for business_id in business_ids
    }

    for business_id, response_profile in employee_result.all():
        if business_id is None:
            continue
        state = _score_snapshot_state_from_profile(
            response_profile if isinstance(response_profile, dict) else {},
            now=reference_time,
        )
        business_bucket = business_counts.setdefault(
            str(business_id),
            {"candidate_employee_count": 0, "stale_or_missing_count": 0},
        )
        business_bucket["candidate_employee_count"] += 1

        if state["status"] == "fresh":
            fresh_employee_count += 1
        elif state["status"] == "stale":
            stale_employee_count += 1
            business_bucket["stale_or_missing_count"] += 1
        else:
            missing_employee_count += 1
            business_bucket["stale_or_missing_count"] += 1

    blocked_business_ids = [
        business_id
        for business_id, counts in business_counts.items()
        if counts["candidate_employee_count"] >= _PROJECTION_BLOCK_MIN_EMPLOYEE_COUNT
        and counts["stale_or_missing_count"] / counts["candidate_employee_count"] >= _PROJECTION_BLOCK_STALE_RATIO
    ]

    status = "blocked" if blocked_business_ids else "ready"
    result: dict[str, object] = {
        "status": status,
        "checked_at": reference_time.isoformat(),
        "freshness_target_seconds": int(SCORE_SNAPSHOT_STALE_AFTER.total_seconds()),
        "monitored_business_count": len(business_counts),
        "candidate_employee_count": fresh_employee_count + stale_employee_count + missing_employee_count,
        "fresh_employee_count": fresh_employee_count,
        "stale_employee_count": stale_employee_count,
        "missing_employee_count": missing_employee_count,
        "blocked_business_count": len(blocked_business_ids),
        "blocked_business_ids": blocked_business_ids,
    }
    if blocked_business_ids:
        result["blocked_reason"] = "runtime_projections_too_stale"
    return result


def build_runtime_projection_metadata(
    candidates: Iterable[CoverageCandidatePreview],
) -> dict[str, object]:
    counts = {
        "fresh": 0,
        "stale": 0,
        "missing": 0,
        "refreshed": 0,
        "unknown": 0,
    }

    for candidate in candidates:
        scoring_factors = candidate.scoring_factors if isinstance(candidate.scoring_factors, dict) else {}
        snapshot = scoring_factors.get("score_snapshot")
        if not isinstance(snapshot, dict):
            counts["unknown"] += 1
            continue
        status = str(snapshot.get("status") or "unknown").strip().lower()
        if status not in counts:
            status = "unknown"
        counts[status] += 1

    return {
        "eligibility": {
            "source": _ENGINE_RUNTIME_SOURCE,
            "mode": "live_authoring_fallback",
            "freshness_target_seconds": 60,
        },
        "availability": {
            "source": _ENGINE_RUNTIME_SOURCE,
            "mode": "live_authoring_fallback",
            "freshness_target_seconds": 60,
        },
        "score_snapshots": {
            "source": _SCORE_SNAPSHOT_SOURCE,
            "mode": "runtime_refresh_on_campaign_open",
            "freshness_target_seconds": int(SCORE_SNAPSHOT_STALE_AFTER.total_seconds()),
            "candidate_count": sum(counts.values()),
            **counts,
        },
    }


def _shift_duration_hours(shift: Shift) -> float:
    return max(0.0, (shift.ends_at - shift.starts_at).total_seconds() / 3600)


def _contact_cooldown_snapshot(
    *,
    last_contact_at: datetime | None,
    now: datetime,
) -> dict[str, object]:
    if last_contact_at is None:
        return {
            "status": "clear",
            "multiplier": 1.0,
            "last_contact_at": None,
            "age_seconds": None,
        }

    age_seconds = max(0, int((now - last_contact_at).total_seconds()))
    if age_seconds < int(CONTACT_COOLDOWN_HARD.total_seconds()):
        return {
            "status": "hard_cooldown",
            "multiplier": 0.0,
            "last_contact_at": last_contact_at.isoformat(),
            "age_seconds": age_seconds,
        }
    if age_seconds < int(CONTACT_COOLDOWN_SOFT.total_seconds()):
        return {
            "status": "soft_cooldown",
            "multiplier": 0.65,
            "last_contact_at": last_contact_at.isoformat(),
            "age_seconds": age_seconds,
        }
    return {
        "status": "clear",
        "multiplier": 1.0,
        "last_contact_at": last_contact_at.isoformat(),
        "age_seconds": age_seconds,
    }


def _recent_burden_snapshot(
    *,
    recent_attempt_count: int,
    recent_accept_count: int,
    recent_assignment_hours: float,
) -> dict[str, object]:
    attempt_penalty = min(max(recent_attempt_count, 0), 6) * 0.03
    accept_penalty = min(max(recent_accept_count, 0), 3) * 0.04
    hour_penalty = min(max(recent_assignment_hours, 0.0) / 24.0, 1.0) * 0.12
    multiplier = max(0.7, round(1.0 - attempt_penalty - accept_penalty - hour_penalty, 3))
    return {
        "multiplier": multiplier,
        "recent_attempt_count": recent_attempt_count,
        "recent_accept_count": recent_accept_count,
        "recent_assignment_hours": round(recent_assignment_hours, 2),
    }


def _overtime_risk_snapshot(
    *,
    projected_hours: float,
) -> dict[str, object]:
    if projected_hours >= 40.0:
        multiplier = 0.4
        status = "high"
    elif projected_hours >= 32.0:
        multiplier = 0.7
        status = "elevated"
    elif projected_hours >= 24.0:
        multiplier = 0.85
        status = "watch"
    else:
        multiplier = 1.0
        status = "clear"
    return {
        "status": status,
        "multiplier": multiplier,
        "projected_hours": round(projected_hours, 2),
    }


async def build_outreach_guardrail_snapshots(
    session: AsyncSession,
    employees: Iterable[Employee],
    *,
    shift: Shift,
    now: datetime | None = None,
) -> dict[UUID, dict[str, object]]:
    reference_time = now or datetime.now(timezone.utc)
    employees_list = list(employees)
    employee_ids = [employee.id for employee in employees_list]
    if not employee_ids:
        return {}

    attempts_by_employee: dict[UUID, list[tuple[datetime | None, CoverageAttemptStatus | str | None]]] = {
        employee_id: []
        for employee_id in employee_ids
    }
    recent_attempts_result = await session.execute(
        select(
            CoverageContactAttempt.employee_id,
            CoverageContactAttempt.requested_at,
            CoverageContactAttempt.status,
        ).where(
            CoverageContactAttempt.employee_id.in_(employee_ids),
            CoverageContactAttempt.requested_at >= reference_time - RECENT_BURDEN_WINDOW,
        )
    )
    for employee_id, requested_at, status in recent_attempts_result.all():
        if employee_id is None:
            continue
        attempts_by_employee.setdefault(employee_id, []).append((requested_at, status))

    assignment_hours_by_employee: dict[UUID, float] = {
        employee_id: 0.0
        for employee_id in employee_ids
    }
    assignment_window_start = shift.ends_at - OVERTIME_LOOKBACK_WINDOW
    assignment_rows = await session.execute(
        select(
            ShiftAssignment.employee_id,
            Shift.starts_at,
            Shift.ends_at,
        )
        .join(Shift, ShiftAssignment.shift_id == Shift.id)
        .where(
            ShiftAssignment.employee_id.in_(employee_ids),
            ShiftAssignment.status.in_(
                [
                    AssignmentStatus.assigned,
                    AssignmentStatus.accepted,
                    AssignmentStatus.completed,
                ]
            ),
            Shift.ends_at > assignment_window_start,
            Shift.starts_at < shift.ends_at,
        )
    )
    for employee_id, starts_at, ends_at in assignment_rows.all():
        if employee_id is None or starts_at is None or ends_at is None:
            continue
        assignment_hours_by_employee[employee_id] = assignment_hours_by_employee.get(employee_id, 0.0) + max(
            0.0,
            (ends_at - starts_at).total_seconds() / 3600,
        )

    current_shift_hours = _shift_duration_hours(shift)
    snapshots: dict[UUID, dict[str, object]] = {}
    for employee in employees_list:
        attempts = attempts_by_employee.get(employee.id, [])
        last_contact_at = max(
            (requested_at for requested_at, _status in attempts if requested_at is not None),
            default=None,
        )
        recent_attempt_count = len(attempts)
        recent_accept_count = sum(
            1
            for _requested_at, status in attempts
            if str(status.value if hasattr(status, "value") else status) == CoverageAttemptStatus.accepted.value
        )
        recent_assignment_hours = assignment_hours_by_employee.get(employee.id, 0.0)

        cooldown = _contact_cooldown_snapshot(last_contact_at=last_contact_at, now=reference_time)
        burden = _recent_burden_snapshot(
            recent_attempt_count=recent_attempt_count,
            recent_accept_count=recent_accept_count,
            recent_assignment_hours=recent_assignment_hours,
        )
        overtime = _overtime_risk_snapshot(
            projected_hours=recent_assignment_hours + current_shift_hours,
        )
        overall = round(
            float(cooldown["multiplier"]) * float(burden["multiplier"]) * float(overtime["multiplier"]),
            3,
        )

        snapshots[employee.id] = {
            "contact_cooldown": cooldown,
            "recent_burden": burden,
            "overtime_risk": overtime,
            "overall_multiplier": overall,
            "hard_excluded": float(cooldown["multiplier"]) == 0.0,
        }

    return snapshots
