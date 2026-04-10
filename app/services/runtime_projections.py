from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workforce import Employee
from app.schemas.coverage import CoverageCandidatePreview
from app.services import delivery

SCORE_SNAPSHOT_STALE_AFTER = timedelta(minutes=15)
_ENGINE_RUNTIME_SOURCE = "authoring_tables"
_SCORE_SNAPSHOT_SOURCE = "employee.response_profile"


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


def score_snapshot_state(
    employee: Employee,
    *,
    now: datetime,
) -> dict[str, object]:
    profile = employee.response_profile if isinstance(employee.response_profile, dict) else {}
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
