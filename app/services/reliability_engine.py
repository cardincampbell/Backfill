from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.common import EmployeeStatus
from app.models.reliability import ReliabilityEvent, ReliabilitySnapshot
from app.models.workforce import Employee
from app.schemas.auto_scheduler import (
    ReliabilityComponentPayload,
    ReliabilityEmployeeSnapshotPayload,
    ReliabilitySnapshotPayload,
)
from app.services.auto_scheduler import stable_payload_hash

DEFAULT_RELIABILITY_BASELINE = 0.7
DEFAULT_PRIOR_WEIGHT = 5.0
DEFAULT_SNAPSHOT_VERSION = "v1"
DEFAULT_RESPONSE_WINDOW_SECONDS = 3600.0
OVERALL_COMPONENT_WEIGHTS = {
    "attendance": 0.30,
    "punctuality": 0.15,
    "commitment": 0.20,
    "response_behavior": 0.15,
    "coverage_reliability": 0.20,
}


def build_employee_reliability_snapshot(
    *,
    employee_id: UUID,
    business_id: UUID,
    events: Sequence[ReliabilityEvent | Mapping[str, Any]],
    snapshot_at: datetime,
    baseline_score: float = DEFAULT_RELIABILITY_BASELINE,
    prior_weight: float = DEFAULT_PRIOR_WEIGHT,
) -> ReliabilityEmployeeSnapshotPayload:
    baseline = _clamp_score(baseline_score)
    event_type_counts: Counter[str] = Counter()
    observed_event_count = 0
    component_metrics: dict[str, dict[str, Any]] = {
        key: {
            "score_total": 0.0,
            "sample_size": 0,
            "event_counts": Counter(),
            "response_time_seconds": [],
            "late_minutes": [],
        }
        for key in OVERALL_COMPONENT_WEIGHTS
    }

    for raw_event in events:
        event_type = str(_event_value(raw_event, "event_type") or "").strip()
        if not event_type:
            continue
        event_payload = _event_payload(raw_event)
        event_type_counts[event_type] += 1
        contributed = False

        if event_type == "worked_shift":
            contributed = True
            _record_component_score(component_metrics, "attendance", 1.0, event_type)
            _record_component_score(
                component_metrics,
                "punctuality",
                _late_arrival_score(event_payload.get("late_minutes")),
                event_type,
                late_minutes=event_payload.get("late_minutes"),
            )
        elif event_type == "late_arrival":
            contributed = True
            _record_component_score(
                component_metrics,
                "punctuality",
                _late_arrival_score(event_payload.get("late_minutes")),
                event_type,
                late_minutes=event_payload.get("late_minutes"),
            )
        elif event_type == "missed_shift":
            contributed = True
            _record_component_score(component_metrics, "attendance", 0.0, event_type)
        elif event_type == "early_departure":
            contributed = True
            _record_component_score(component_metrics, "attendance", 0.35, event_type)
        elif event_type == "accepted_offer":
            contributed = True
            _record_component_score(component_metrics, "commitment", 0.8, event_type)
            _record_component_score(component_metrics, "coverage_reliability", 0.8, event_type)
        elif event_type == "declined_offer":
            contributed = True
            _record_component_score(component_metrics, "response_behavior", 1.0, event_type)
        elif event_type == "accepted_then_cancelled":
            contributed = True
            _record_component_score(component_metrics, "commitment", 0.0, event_type)
            _record_component_score(component_metrics, "coverage_reliability", 0.0, event_type)
        elif event_type == "accepted_and_worked":
            contributed = True
            _record_component_score(component_metrics, "attendance", 1.0, event_type)
            _record_component_score(component_metrics, "commitment", 1.0, event_type)
            _record_component_score(component_metrics, "coverage_reliability", 1.0, event_type)
        elif event_type == "responded_to_callout":
            contributed = True
            _record_component_score(component_metrics, "response_behavior", 1.0, event_type)
            _record_component_score(component_metrics, "coverage_reliability", 0.9, event_type)
        elif event_type == "no_response_to_offer":
            contributed = True
            _record_component_score(component_metrics, "response_behavior", 0.0, event_type)
            _record_component_score(component_metrics, "coverage_reliability", 0.0, event_type)
        elif event_type == "standby_acceptance":
            contributed = True
            _record_component_score(component_metrics, "response_behavior", 1.0, event_type)
            _record_component_score(component_metrics, "coverage_reliability", 1.0, event_type)
        elif event_type == "standby_promotion_success":
            contributed = True
            _record_component_score(component_metrics, "coverage_reliability", 1.0, event_type)
            _record_component_score(component_metrics, "commitment", 1.0, event_type)
        elif event_type == "callout_submitted":
            contributed = True
            _record_component_score(component_metrics, "attendance", 0.4, event_type)
            _record_component_score(component_metrics, "commitment", 0.4, event_type)
        elif event_type == "manager_removed":
            contributed = True
            _record_component_score(component_metrics, "commitment", 0.25, event_type)
        elif event_type == "reassignment_requested":
            contributed = True
            _record_component_score(component_metrics, "commitment", 0.4, event_type)
        elif event_type == "response_time_recorded":
            contributed = True
            response_time_seconds = _as_float(event_payload.get("response_time_seconds"))
            _record_component_score(
                component_metrics,
                "response_behavior",
                _response_time_score(response_time_seconds),
                event_type,
                response_time_seconds=response_time_seconds,
            )

        if contributed:
            observed_event_count += 1

    components = {
        "attendance": _build_component_payload(
            component_metrics["attendance"],
            baseline=baseline,
            prior_weight=prior_weight,
        ),
        "punctuality": _build_component_payload(
            component_metrics["punctuality"],
            baseline=baseline,
            prior_weight=prior_weight,
        ),
        "commitment": _build_component_payload(
            component_metrics["commitment"],
            baseline=baseline,
            prior_weight=prior_weight,
        ),
        "response_behavior": _build_component_payload(
            component_metrics["response_behavior"],
            baseline=baseline,
            prior_weight=prior_weight,
        ),
        "coverage_reliability": _build_component_payload(
            component_metrics["coverage_reliability"],
            baseline=baseline,
            prior_weight=prior_weight,
        ),
    }
    overall_score = sum(
        OVERALL_COMPONENT_WEIGHTS[name] * components[name].score
        for name in OVERALL_COMPONENT_WEIGHTS
    )
    overall_confidence = _confidence_for_sample_size(
        sample_size=observed_event_count,
        prior_weight=prior_weight,
    )

    return ReliabilityEmployeeSnapshotPayload(
        employee_id=employee_id,
        overall_score=round(_clamp_score(overall_score), 4),
        confidence=round(overall_confidence, 4),
        sample_size=observed_event_count,
        attendance=components["attendance"],
        punctuality=components["punctuality"],
        commitment=components["commitment"],
        response_behavior=components["response_behavior"],
        coverage_reliability=components["coverage_reliability"],
        metadata={
            "baseline_score": round(baseline, 4),
            "prior_weight": prior_weight,
            "event_type_counts": dict(event_type_counts),
            "snapshot_at": snapshot_at.isoformat(),
        },
    )


def build_reliability_snapshot_payload(
    *,
    employee_snapshots: Sequence[ReliabilityEmployeeSnapshotPayload],
    generated_at: datetime,
    snapshot_version: str = DEFAULT_SNAPSHOT_VERSION,
    metadata: Mapping[str, Any] | None = None,
) -> ReliabilitySnapshotPayload:
    ordered_snapshots = sorted(employee_snapshots, key=lambda snapshot: str(snapshot.employee_id))
    base_payload = {
        "generated_at": generated_at.isoformat(),
        "snapshot_version": snapshot_version,
        "employees": [snapshot.model_dump(mode="json") for snapshot in ordered_snapshots],
        "metadata": dict(metadata or {}),
    }
    snapshot_hash = stable_payload_hash(base_payload)
    return ReliabilitySnapshotPayload(
        generated_at=generated_at,
        snapshot_hash=snapshot_hash,
        snapshot_version=snapshot_version,
        employees=list(ordered_snapshots),
        metadata=dict(metadata or {}),
    )


async def record_reliability_event(
    session: AsyncSession,
    *,
    business_id: UUID,
    employee_id: UUID,
    event_type: str,
    occurred_at: datetime,
    source: str,
    shift_id: UUID | None = None,
    location_id: UUID | None = None,
    role_id: UUID | None = None,
    event_payload: Mapping[str, Any] | None = None,
) -> ReliabilityEvent:
    event = ReliabilityEvent(
        business_id=business_id,
        employee_id=employee_id,
        shift_id=shift_id,
        location_id=location_id,
        role_id=role_id,
        event_type=event_type,
        occurred_at=occurred_at,
        source=source,
        event_payload=dict(event_payload or {}),
    )
    session.add(event)
    await session.flush()
    return event


async def refresh_employee_reliability_snapshot(
    session: AsyncSession,
    employee_id: UUID,
    *,
    snapshot_at: datetime | None = None,
) -> ReliabilitySnapshot | None:
    employee = await session.get(Employee, employee_id)
    if employee is None:
        return None

    effective_snapshot_at = snapshot_at or datetime.now(timezone.utc)
    baseline = await _business_baseline_score(
        session,
        business_id=employee.business_id,
        exclude_employee_id=employee.id,
    )
    events = await _load_employee_reliability_events(
        session,
        employee_id=employee.id,
        snapshot_at=effective_snapshot_at,
    )
    employee_snapshot = build_employee_reliability_snapshot(
        employee_id=employee.id,
        business_id=employee.business_id,
        events=events,
        snapshot_at=effective_snapshot_at,
        baseline_score=baseline,
    )
    payload = employee_snapshot.model_dump(mode="json")
    snapshot = ReliabilitySnapshot(
        employee_id=employee.id,
        business_id=employee.business_id,
        snapshot_at=effective_snapshot_at,
        sample_size=employee_snapshot.sample_size,
        confidence=employee_snapshot.confidence,
        attendance_score=employee_snapshot.attendance.score,
        punctuality_score=employee_snapshot.punctuality.score,
        commitment_score=employee_snapshot.commitment.score,
        response_behavior_score=employee_snapshot.response_behavior.score,
        coverage_reliability_score=employee_snapshot.coverage_reliability.score,
        overall_reliability_score=employee_snapshot.overall_score,
        snapshot_version=DEFAULT_SNAPSHOT_VERSION,
        payload_hash=stable_payload_hash(payload),
        snapshot_payload=payload,
    )
    session.add(snapshot)

    employee.reliability_score = round(employee_snapshot.overall_score, 3)
    avg_response_time_seconds = employee_snapshot.response_behavior.metrics.get("avg_response_time_seconds")
    employee.avg_response_time_seconds = (
        int(avg_response_time_seconds)
        if isinstance(avg_response_time_seconds, (int, float)) and avg_response_time_seconds >= 0
        else None
    )
    employee.response_profile = {
        "reliability_snapshot_version": DEFAULT_SNAPSHOT_VERSION,
        "snapshot_at": effective_snapshot_at.isoformat(),
        "sample_size": employee_snapshot.sample_size,
        "confidence": round(employee_snapshot.confidence, 4),
        "attendance_score": employee_snapshot.attendance.score,
        "punctuality_score": employee_snapshot.punctuality.score,
        "commitment_score": employee_snapshot.commitment.score,
        "response_behavior_score": employee_snapshot.response_behavior.score,
        "coverage_reliability_score": employee_snapshot.coverage_reliability.score,
        "overall_reliability_score": employee_snapshot.overall_score,
    }
    await session.flush()
    return snapshot


async def refresh_business_reliability_snapshots(
    session: AsyncSession,
    *,
    business_id: UUID,
    employee_ids: Sequence[UUID] | None = None,
    snapshot_at: datetime | None = None,
) -> list[ReliabilitySnapshot]:
    employees = await _load_business_employees(
        session,
        business_id=business_id,
        employee_ids=employee_ids,
    )
    snapshots: list[ReliabilitySnapshot] = []
    for employee in employees:
        snapshot = await refresh_employee_reliability_snapshot(
            session,
            employee.id,
            snapshot_at=snapshot_at,
        )
        if snapshot is not None:
            snapshots.append(snapshot)
    return snapshots


async def build_pinned_reliability_snapshot_payload(
    session: AsyncSession,
    *,
    business_id: UUID,
    employee_ids: Sequence[UUID],
    generated_at: datetime | None = None,
) -> ReliabilitySnapshotPayload:
    effective_generated_at = generated_at or datetime.now(timezone.utc)
    snapshots = await refresh_business_reliability_snapshots(
        session,
        business_id=business_id,
        employee_ids=employee_ids,
        snapshot_at=effective_generated_at,
    )
    employee_snapshots = [
        ReliabilityEmployeeSnapshotPayload.model_validate(snapshot.snapshot_payload)
        for snapshot in snapshots
    ]
    return build_reliability_snapshot_payload(
        employee_snapshots=employee_snapshots,
        generated_at=effective_generated_at,
        metadata={
            "business_id": str(business_id),
            "employee_count": len(employee_snapshots),
        },
    )


async def _load_business_employees(
    session: AsyncSession,
    *,
    business_id: UUID,
    employee_ids: Sequence[UUID] | None,
) -> list[Employee]:
    stmt = select(Employee).where(
        Employee.business_id == business_id,
        Employee.status == EmployeeStatus.active,
    )
    if employee_ids:
        stmt = stmt.where(Employee.id.in_(list(employee_ids)))
    result = await session.execute(stmt.order_by(Employee.created_at.asc()))
    return list(result.scalars().all())


async def _load_employee_reliability_events(
    session: AsyncSession,
    *,
    employee_id: UUID,
    snapshot_at: datetime,
) -> list[ReliabilityEvent]:
    result = await session.execute(
        select(ReliabilityEvent)
        .where(
            ReliabilityEvent.employee_id == employee_id,
            ReliabilityEvent.occurred_at <= snapshot_at,
        )
        .order_by(ReliabilityEvent.occurred_at.asc(), ReliabilityEvent.id.asc())
    )
    return list(result.scalars().all())


async def _business_baseline_score(
    session: AsyncSession,
    *,
    business_id: UUID,
    exclude_employee_id: UUID | None = None,
) -> float:
    stmt = select(func.avg(Employee.reliability_score)).where(
        Employee.business_id == business_id,
        Employee.status == EmployeeStatus.active,
    )
    if exclude_employee_id is not None:
        stmt = stmt.where(Employee.id != exclude_employee_id)
    avg_score = await session.scalar(stmt)
    if avg_score is None:
        return DEFAULT_RELIABILITY_BASELINE
    return _clamp_score(float(avg_score))


def _record_component_score(
    component_metrics: dict[str, dict[str, Any]],
    component_name: str,
    score: float,
    event_type: str,
    *,
    response_time_seconds: float | None = None,
    late_minutes: float | None = None,
) -> None:
    component = component_metrics[component_name]
    component["score_total"] += _clamp_score(score)
    component["sample_size"] += 1
    component["event_counts"][event_type] += 1
    if response_time_seconds is not None:
        component["response_time_seconds"].append(response_time_seconds)
    if late_minutes is not None:
        component["late_minutes"].append(late_minutes)


def _build_component_payload(
    component_metric: Mapping[str, Any],
    *,
    baseline: float,
    prior_weight: float,
) -> ReliabilityComponentPayload:
    sample_size = int(component_metric.get("sample_size") or 0)
    raw_average = (
        float(component_metric.get("score_total") or 0.0) / sample_size
        if sample_size > 0
        else baseline
    )
    score = _shrink_score(
        raw_average=raw_average,
        sample_size=sample_size,
        baseline=baseline,
        prior_weight=prior_weight,
    )
    response_times = [
        int(value)
        for value in component_metric.get("response_time_seconds", [])
        if isinstance(value, (int, float))
    ]
    late_minutes = [
        float(value)
        for value in component_metric.get("late_minutes", [])
        if isinstance(value, (int, float, Decimal))
    ]
    metrics = {
        "baseline_score": round(baseline, 4),
        "prior_weight": prior_weight,
        "raw_average": round(raw_average, 4),
        "event_counts": dict(component_metric.get("event_counts", {})),
    }
    if response_times:
        metrics["avg_response_time_seconds"] = int(sum(response_times) / len(response_times))
    if late_minutes:
        metrics["avg_late_minutes"] = round(sum(late_minutes) / len(late_minutes), 2)
    return ReliabilityComponentPayload(
        score=round(score, 4),
        confidence=round(_confidence_for_sample_size(sample_size=sample_size, prior_weight=prior_weight), 4),
        sample_size=sample_size,
        metrics=metrics,
    )


def _response_time_score(response_time_seconds: float | None) -> float:
    if response_time_seconds is None:
        return DEFAULT_RELIABILITY_BASELINE
    bounded = max(0.0, min(float(response_time_seconds), DEFAULT_RESPONSE_WINDOW_SECONDS))
    return _clamp_score(1.0 - (bounded / DEFAULT_RESPONSE_WINDOW_SECONDS))


def _late_arrival_score(late_minutes: object) -> float:
    late = _as_float(late_minutes)
    if late is None or late <= 0:
        return 1.0
    if late <= 5:
        return 0.85
    if late <= 15:
        return 0.6
    if late <= 30:
        return 0.3
    return 0.1


def _shrink_score(
    *,
    raw_average: float,
    sample_size: int,
    baseline: float,
    prior_weight: float,
) -> float:
    numerator = (raw_average * sample_size) + (baseline * prior_weight)
    denominator = sample_size + prior_weight
    if denominator <= 0:
        return baseline
    return _clamp_score(numerator / denominator)


def _confidence_for_sample_size(*, sample_size: int, prior_weight: float) -> float:
    if sample_size <= 0:
        return 0.0
    return max(0.0, min(sample_size / (sample_size + prior_weight), 1.0))


def _event_value(raw_event: ReliabilityEvent | Mapping[str, Any], key: str) -> Any:
    if isinstance(raw_event, Mapping):
        return raw_event.get(key)
    return getattr(raw_event, key, None)


def _event_payload(raw_event: ReliabilityEvent | Mapping[str, Any]) -> Mapping[str, Any]:
    payload = _event_value(raw_event, "event_payload")
    return payload if isinstance(payload, Mapping) else {}


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    return None


def _clamp_score(value: float) -> float:
    return max(0.0, min(float(value), 1.0))
