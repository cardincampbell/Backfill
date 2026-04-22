from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.common import AssignmentStatus, CoverageCaseStatus
from app.models.coverage import CoverageCase
from app.models.demand_features import AttendanceHistoryFact, CalloutHistoryFact
from app.models.scheduling import Shift, ShiftAssignment
from app.schemas.forecast_history import AttendanceHistoryFactPayload, CalloutHistoryFactPayload
from app.services.payload_utils import stable_payload_hash, stable_payload_json

_FOUR_DECIMAL_PLACES = Decimal("0.0001")


def _json_safe_mapping(payload: Mapping[str, object] | None) -> dict[str, object]:
    return json.loads(stable_payload_json(dict(payload or {})))


def _decimal_hours(value: float) -> Decimal:
    return Decimal(str(value)).quantize(_FOUR_DECIMAL_PLACES, rounding=ROUND_HALF_UP)


def _duration_hours(starts_at: datetime, ends_at: datetime) -> Decimal:
    return _decimal_hours(max((ends_at - starts_at).total_seconds(), 0.0) / 3600.0)


def _int_metadata_value(payload: Mapping[str, object] | None, key: str) -> int | None:
    value = (payload or {}).get(key)
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _assignment_attendance_status(assignment: ShiftAssignment) -> str:
    if assignment.status == AssignmentStatus.no_show:
        return "no_show"
    if assignment.status == AssignmentStatus.completed or (
        assignment.checked_in_at is not None and assignment.checked_out_at is not None
    ):
        return "completed"
    if assignment.checked_in_at is not None:
        return "in_progress"
    return assignment.status.value


def build_attendance_history_fact_payload_from_assignment(
    *,
    shift: Shift,
    assignment: ShiftAssignment,
    source_system: str = "backfill_native",
    source_payload: Mapping[str, object] | None = None,
) -> AttendanceHistoryFactPayload:
    scheduled_hours = _duration_hours(shift.starts_at, shift.ends_at)
    worked_hours = (
        _duration_hours(assignment.checked_in_at, assignment.checked_out_at)
        if assignment.checked_in_at is not None and assignment.checked_out_at is not None
        else Decimal("0")
    )
    return AttendanceHistoryFactPayload(
        business_id=shift.business_id,
        location_id=shift.location_id,
        role_id=shift.role_id,
        shift_id=shift.id,
        employee_id=assignment.employee_id,
        source_system=source_system,
        source_assignment_id=str(assignment.id),
        starts_at=shift.starts_at,
        ends_at=shift.ends_at,
        scheduled_hours=scheduled_hours,
        worked_hours=worked_hours,
        attendance_status=_assignment_attendance_status(assignment),
        late_minutes=_int_metadata_value(assignment.assignment_metadata, "late_minutes"),
        left_early_minutes=_int_metadata_value(assignment.assignment_metadata, "left_early_minutes"),
        source_payload={
            "assignment_status": assignment.status.value,
            "assigned_via": assignment.assigned_via,
            "accepted_at": assignment.accepted_at.isoformat() if assignment.accepted_at is not None else None,
            "checked_in_at": assignment.checked_in_at.isoformat() if assignment.checked_in_at is not None else None,
            "checked_out_at": assignment.checked_out_at.isoformat() if assignment.checked_out_at is not None else None,
            "assignment_metadata": dict(assignment.assignment_metadata or {}),
            **dict(source_payload or {}),
        },
    )


def build_callout_history_fact_payload_from_case(
    *,
    coverage_case: CoverageCase,
    shift: Shift,
    source_system: str = "backfill_native",
    source_payload: Mapping[str, object] | None = None,
) -> CalloutHistoryFactPayload:
    occurred_at = coverage_case.opened_at or coverage_case.created_at or datetime.now(timezone.utc)
    notice_minutes = None
    if shift.starts_at > occurred_at:
        notice_minutes = int((shift.starts_at - occurred_at).total_seconds() // 60)
    filled = coverage_case.status == CoverageCaseStatus.filled
    fill_latency_minutes = None
    if filled and coverage_case.closed_at is not None and coverage_case.closed_at >= occurred_at:
        fill_latency_minutes = int((coverage_case.closed_at - occurred_at).total_seconds() // 60)
    return CalloutHistoryFactPayload(
        business_id=shift.business_id,
        location_id=coverage_case.location_id,
        role_id=coverage_case.role_id,
        shift_id=coverage_case.shift_id,
        source_system=source_system,
        source_case_id=str(coverage_case.id),
        occurred_at=occurred_at,
        shift_starts_at=shift.starts_at,
        shift_ends_at=shift.ends_at,
        notice_minutes=notice_minutes,
        reason_code=coverage_case.reason_code,
        filled=filled,
        fill_latency_minutes=fill_latency_minutes,
        source_payload={
            "status": coverage_case.status.value,
            "phase_target": coverage_case.phase_target,
            "triggered_by": coverage_case.triggered_by,
            "opened_at": coverage_case.opened_at.isoformat() if coverage_case.opened_at is not None else None,
            "closed_at": coverage_case.closed_at.isoformat() if coverage_case.closed_at is not None else None,
            "case_metadata": dict(coverage_case.case_metadata or {}),
            **dict(source_payload or {}),
        },
    )


def build_attendance_history_fact_dedupe_key(
    payload: AttendanceHistoryFactPayload | Mapping[str, object],
) -> str:
    normalized = (
        payload if isinstance(payload, AttendanceHistoryFactPayload) else AttendanceHistoryFactPayload.model_validate(payload)
    )
    identity_ref = (
        normalized.source_assignment_id
        or normalized.source_payload.get("source_record_id")
        or normalized.source_payload.get("external_id")
    )
    return stable_payload_hash(
        {
            "source_system": normalized.source_system,
            "identity_ref": identity_ref,
            "shift_id": str(normalized.shift_id) if normalized.shift_id is not None else None,
            "employee_id": str(normalized.employee_id) if normalized.employee_id is not None else None,
            "starts_at": normalized.starts_at.isoformat(),
            "ends_at": normalized.ends_at.isoformat(),
        }
    )


def build_callout_history_fact_dedupe_key(
    payload: CalloutHistoryFactPayload | Mapping[str, object],
) -> str:
    normalized = payload if isinstance(payload, CalloutHistoryFactPayload) else CalloutHistoryFactPayload.model_validate(payload)
    identity_ref = (
        normalized.source_case_id
        or normalized.source_payload.get("source_record_id")
        or normalized.source_payload.get("external_id")
    )
    return stable_payload_hash(
        {
            "source_system": normalized.source_system,
            "identity_ref": identity_ref,
            "shift_id": str(normalized.shift_id) if normalized.shift_id is not None else None,
            "occurred_at": normalized.occurred_at.isoformat(),
        }
    )


def _apply_attendance_history_fact_payload(
    row: AttendanceHistoryFact,
    payload: AttendanceHistoryFactPayload,
    *,
    dedupe_key: str,
    ingested_at: datetime,
) -> AttendanceHistoryFact:
    row.business_id = payload.business_id
    row.location_id = payload.location_id
    row.role_id = payload.role_id
    row.shift_id = payload.shift_id
    row.employee_id = payload.employee_id
    row.source_system = payload.source_system
    row.source_assignment_id = payload.source_assignment_id
    row.starts_at = payload.starts_at
    row.ends_at = payload.ends_at
    row.scheduled_hours = payload.scheduled_hours
    row.worked_hours = payload.worked_hours
    row.attendance_status = payload.attendance_status
    row.late_minutes = payload.late_minutes
    row.left_early_minutes = payload.left_early_minutes
    row.source_payload = _json_safe_mapping(payload.source_payload)
    row.ingested_at = ingested_at
    row.dedupe_key = dedupe_key
    return row


def _apply_callout_history_fact_payload(
    row: CalloutHistoryFact,
    payload: CalloutHistoryFactPayload,
    *,
    dedupe_key: str,
    ingested_at: datetime,
) -> CalloutHistoryFact:
    row.business_id = payload.business_id
    row.location_id = payload.location_id
    row.role_id = payload.role_id
    row.shift_id = payload.shift_id
    row.source_system = payload.source_system
    row.source_case_id = payload.source_case_id
    row.occurred_at = payload.occurred_at
    row.shift_starts_at = payload.shift_starts_at
    row.shift_ends_at = payload.shift_ends_at
    row.notice_minutes = payload.notice_minutes
    row.reason_code = payload.reason_code
    row.filled = bool(payload.filled)
    row.fill_latency_minutes = payload.fill_latency_minutes
    row.source_payload = _json_safe_mapping(payload.source_payload)
    row.ingested_at = ingested_at
    row.dedupe_key = dedupe_key
    return row


async def upsert_attendance_history_fact(
    session: AsyncSession,
    payload: AttendanceHistoryFactPayload | Mapping[str, object],
) -> AttendanceHistoryFact:
    rows = await upsert_attendance_history_facts(session, [payload])
    return rows[0]


async def upsert_attendance_history_facts(
    session: AsyncSession,
    payloads: Sequence[AttendanceHistoryFactPayload | Mapping[str, object]],
) -> list[AttendanceHistoryFact]:
    ingested_at = datetime.now(timezone.utc)
    normalized_payloads = [
        payload
        if isinstance(payload, AttendanceHistoryFactPayload)
        else AttendanceHistoryFactPayload.model_validate(payload)
        for payload in payloads
    ]
    dedupe_index: dict[tuple[str, str], AttendanceHistoryFact] = {}
    persisted: dict[tuple[str, str], AttendanceHistoryFact] = {}

    for payload in normalized_payloads:
        dedupe_key = payload.dedupe_key or build_attendance_history_fact_dedupe_key(payload)
        cache_key = (payload.source_system, dedupe_key)
        row = dedupe_index.get(cache_key)

        if row is None:
            result = await session.execute(
                select(AttendanceHistoryFact).where(
                    AttendanceHistoryFact.source_system == payload.source_system,
                    AttendanceHistoryFact.dedupe_key == dedupe_key,
                )
            )
            row = next(iter(result.scalars().all()), None)

        if row is None:
            row = AttendanceHistoryFact(
                business_id=payload.business_id,
                location_id=payload.location_id,
                role_id=payload.role_id,
                shift_id=payload.shift_id,
                employee_id=payload.employee_id,
                source_system=payload.source_system,
                source_assignment_id=payload.source_assignment_id,
                starts_at=payload.starts_at,
                ends_at=payload.ends_at,
                scheduled_hours=payload.scheduled_hours,
                worked_hours=payload.worked_hours,
                attendance_status=payload.attendance_status,
                late_minutes=payload.late_minutes,
                left_early_minutes=payload.left_early_minutes,
                source_payload={},
                ingested_at=ingested_at,
                dedupe_key=dedupe_key,
            )
            session.add(row)

        dedupe_index[cache_key] = _apply_attendance_history_fact_payload(
            row,
            payload,
            dedupe_key=dedupe_key,
            ingested_at=ingested_at,
        )
        persisted[cache_key] = row

    await session.flush()
    return list(persisted.values())


async def upsert_callout_history_fact(
    session: AsyncSession,
    payload: CalloutHistoryFactPayload | Mapping[str, object],
) -> CalloutHistoryFact:
    rows = await upsert_callout_history_facts(session, [payload])
    return rows[0]


async def sync_attendance_history_fact_for_assignment(
    session: AsyncSession,
    *,
    shift: Shift,
    assignment: ShiftAssignment,
    source_system: str = "backfill_native",
    source_payload: Mapping[str, object] | None = None,
) -> AttendanceHistoryFact:
    payload = build_attendance_history_fact_payload_from_assignment(
        shift=shift,
        assignment=assignment,
        source_system=source_system,
        source_payload=source_payload,
    )
    return await upsert_attendance_history_fact(session, payload)


async def sync_callout_history_fact_for_case(
    session: AsyncSession,
    *,
    coverage_case: CoverageCase,
    shift: Shift,
    source_system: str = "backfill_native",
    source_payload: Mapping[str, object] | None = None,
) -> CalloutHistoryFact:
    payload = build_callout_history_fact_payload_from_case(
        coverage_case=coverage_case,
        shift=shift,
        source_system=source_system,
        source_payload=source_payload,
    )
    return await upsert_callout_history_fact(session, payload)


async def upsert_callout_history_facts(
    session: AsyncSession,
    payloads: Sequence[CalloutHistoryFactPayload | Mapping[str, object]],
) -> list[CalloutHistoryFact]:
    ingested_at = datetime.now(timezone.utc)
    normalized_payloads = [
        payload if isinstance(payload, CalloutHistoryFactPayload) else CalloutHistoryFactPayload.model_validate(payload)
        for payload in payloads
    ]
    dedupe_index: dict[tuple[str, str], CalloutHistoryFact] = {}
    persisted: dict[tuple[str, str], CalloutHistoryFact] = {}

    for payload in normalized_payloads:
        dedupe_key = payload.dedupe_key or build_callout_history_fact_dedupe_key(payload)
        cache_key = (payload.source_system, dedupe_key)
        row = dedupe_index.get(cache_key)

        if row is None:
            result = await session.execute(
                select(CalloutHistoryFact).where(
                    CalloutHistoryFact.source_system == payload.source_system,
                    CalloutHistoryFact.dedupe_key == dedupe_key,
                )
            )
            row = next(iter(result.scalars().all()), None)

        if row is None:
            row = CalloutHistoryFact(
                business_id=payload.business_id,
                location_id=payload.location_id,
                role_id=payload.role_id,
                shift_id=payload.shift_id,
                source_system=payload.source_system,
                source_case_id=payload.source_case_id,
                occurred_at=payload.occurred_at,
                shift_starts_at=payload.shift_starts_at,
                shift_ends_at=payload.shift_ends_at,
                notice_minutes=payload.notice_minutes,
                reason_code=payload.reason_code,
                filled=payload.filled,
                fill_latency_minutes=payload.fill_latency_minutes,
                source_payload={},
                ingested_at=ingested_at,
                dedupe_key=dedupe_key,
            )
            session.add(row)

        dedupe_index[cache_key] = _apply_callout_history_fact_payload(
            row,
            payload,
            dedupe_key=dedupe_key,
            ingested_at=ingested_at,
        )
        persisted[cache_key] = row

    await session.flush()
    return list(persisted.values())


async def list_attendance_history_facts(
    session: AsyncSession,
    *,
    business_id,
    location_id=None,
    role_id=None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    limit: int = 500,
) -> list[AttendanceHistoryFact]:
    stmt = (
        select(AttendanceHistoryFact)
        .where(AttendanceHistoryFact.business_id == business_id)
        .order_by(AttendanceHistoryFact.starts_at.asc(), AttendanceHistoryFact.id.asc())
        .limit(max(1, min(limit, 5000)))
    )
    if location_id is not None:
        stmt = stmt.where(AttendanceHistoryFact.location_id == location_id)
    if role_id is not None:
        stmt = stmt.where(AttendanceHistoryFact.role_id == role_id)
    if starts_at is not None:
        stmt = stmt.where(AttendanceHistoryFact.starts_at >= starts_at)
    if ends_at is not None:
        stmt = stmt.where(AttendanceHistoryFact.starts_at < ends_at)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_callout_history_facts(
    session: AsyncSession,
    *,
    business_id,
    location_id=None,
    role_id=None,
    occurred_at_start: datetime | None = None,
    occurred_at_end: datetime | None = None,
    limit: int = 500,
) -> list[CalloutHistoryFact]:
    stmt = (
        select(CalloutHistoryFact)
        .where(CalloutHistoryFact.business_id == business_id)
        .order_by(CalloutHistoryFact.occurred_at.asc(), CalloutHistoryFact.id.asc())
        .limit(max(1, min(limit, 5000)))
    )
    if location_id is not None:
        stmt = stmt.where(CalloutHistoryFact.location_id == location_id)
    if role_id is not None:
        stmt = stmt.where(CalloutHistoryFact.role_id == role_id)
    if occurred_at_start is not None:
        stmt = stmt.where(CalloutHistoryFact.occurred_at >= occurred_at_start)
    if occurred_at_end is not None:
        stmt = stmt.where(CalloutHistoryFact.occurred_at < occurred_at_end)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _iter_local_bucket_signatures(
    *,
    starts_at: datetime,
    ends_at: datetime,
    timezone_name: str,
    bucket_minutes: int,
) -> list[tuple[int, int, int]]:
    local_zone = ZoneInfo(timezone_name)
    local_start = starts_at.astimezone(local_zone)
    local_end = ends_at.astimezone(local_zone)
    if local_end <= local_start:
        return []

    bucket_cursor = local_start.replace(
        minute=(local_start.minute // bucket_minutes) * bucket_minutes,
        second=0,
        microsecond=0,
    )
    signatures: list[tuple[int, int, int]] = []
    seen: set[tuple[int, int, int]] = set()

    while bucket_cursor < local_end:
        next_bucket = bucket_cursor + timedelta(minutes=bucket_minutes)
        overlap_start = max(local_start, bucket_cursor)
        overlap_end = min(local_end, next_bucket)
        if overlap_end > overlap_start:
            signature = (bucket_cursor.weekday(), bucket_cursor.hour, bucket_minutes)
            if signature not in seen:
                seen.add(signature)
                signatures.append(signature)
        bucket_cursor = next_bucket

    return signatures


def summarize_attendance_by_local_bucket(
    rows: Sequence[AttendanceHistoryFact],
    *,
    timezone_name: str,
    bucket_minutes: int,
    lookback_days: int,
) -> dict[tuple[str | None, str | None, int, int, int], dict[str, object]]:
    aggregates: dict[tuple[str | None, str | None, int, int, int], dict[str, float]] = {}

    for row in rows:
        signatures = _iter_local_bucket_signatures(
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            timezone_name=timezone_name,
            bucket_minutes=bucket_minutes,
        )
        for weekday, hour, duration_minutes in signatures:
            key = (
                str(row.location_id) if row.location_id is not None else None,
                str(row.role_id) if row.role_id is not None else None,
                weekday,
                hour,
                duration_minutes,
            )
            bucket = aggregates.setdefault(
                key,
                {
                    "sample_count": 0.0,
                    "completed_count": 0.0,
                    "no_show_count": 0.0,
                    "late_minutes_total": 0.0,
                    "late_minutes_samples": 0.0,
                    "left_early_minutes_total": 0.0,
                    "left_early_minutes_samples": 0.0,
                    "worked_hours_ratio_total": 0.0,
                    "worked_hours_ratio_samples": 0.0,
                },
            )
            bucket["sample_count"] += 1.0
            if row.attendance_status == "completed":
                bucket["completed_count"] += 1.0
            if row.attendance_status == "no_show":
                bucket["no_show_count"] += 1.0
            if row.late_minutes is not None:
                bucket["late_minutes_total"] += float(row.late_minutes)
                bucket["late_minutes_samples"] += 1.0
            if row.left_early_minutes is not None:
                bucket["left_early_minutes_total"] += float(row.left_early_minutes)
                bucket["left_early_minutes_samples"] += 1.0
            if row.scheduled_hours > 0:
                ratio = float(row.worked_hours / row.scheduled_hours)
                bucket["worked_hours_ratio_total"] += ratio
                bucket["worked_hours_ratio_samples"] += 1.0

    summaries: dict[tuple[str | None, str | None, int, int, int], dict[str, object]] = {}
    for key, bucket in aggregates.items():
        sample_count = max(bucket["sample_count"], 1.0)
        late_samples = max(bucket["late_minutes_samples"], 1.0)
        left_early_samples = max(bucket["left_early_minutes_samples"], 1.0)
        worked_ratio_samples = max(bucket["worked_hours_ratio_samples"], 1.0)
        summaries[key] = {
            f"attendance_sample_count_{lookback_days}d": int(bucket["sample_count"]),
            f"attendance_completed_rate_{lookback_days}d": round(bucket["completed_count"] / sample_count, 4),
            f"attendance_no_show_rate_{lookback_days}d": round(bucket["no_show_count"] / sample_count, 4),
            f"attendance_late_minutes_mean_{lookback_days}d": (
                round(bucket["late_minutes_total"] / late_samples, 2) if bucket["late_minutes_samples"] > 0 else None
            ),
            f"attendance_left_early_minutes_mean_{lookback_days}d": (
                round(bucket["left_early_minutes_total"] / left_early_samples, 2)
                if bucket["left_early_minutes_samples"] > 0
                else None
            ),
            f"attendance_worked_hours_ratio_mean_{lookback_days}d": (
                round(bucket["worked_hours_ratio_total"] / worked_ratio_samples, 4)
                if bucket["worked_hours_ratio_samples"] > 0
                else None
            ),
        }
    return summaries


def summarize_callout_history_by_local_bucket(
    rows: Sequence[CalloutHistoryFact],
    *,
    timezone_name: str,
    bucket_minutes: int,
    lookback_days: int,
) -> dict[tuple[str | None, str | None, int, int, int], dict[str, object]]:
    aggregates: dict[tuple[str | None, str | None, int, int, int], dict[str, float]] = {}

    for row in rows:
        window_start = row.shift_starts_at or row.occurred_at
        window_end = row.shift_ends_at or (window_start + timedelta(minutes=bucket_minutes))
        if window_end <= window_start:
            window_end = window_start + timedelta(minutes=bucket_minutes)
        signatures = _iter_local_bucket_signatures(
            starts_at=window_start,
            ends_at=window_end,
            timezone_name=timezone_name,
            bucket_minutes=bucket_minutes,
        )
        for weekday, hour, duration_minutes in signatures:
            key = (
                str(row.location_id) if row.location_id is not None else None,
                str(row.role_id) if row.role_id is not None else None,
                weekday,
                hour,
                duration_minutes,
            )
            bucket = aggregates.setdefault(
                key,
                {
                    "sample_count": 0.0,
                    "filled_count": 0.0,
                    "notice_minutes_total": 0.0,
                    "notice_minutes_samples": 0.0,
                    "fill_latency_minutes_total": 0.0,
                    "fill_latency_minutes_samples": 0.0,
                },
            )
            bucket["sample_count"] += 1.0
            if row.filled:
                bucket["filled_count"] += 1.0
            if row.notice_minutes is not None:
                bucket["notice_minutes_total"] += float(row.notice_minutes)
                bucket["notice_minutes_samples"] += 1.0
            if row.fill_latency_minutes is not None:
                bucket["fill_latency_minutes_total"] += float(row.fill_latency_minutes)
                bucket["fill_latency_minutes_samples"] += 1.0

    summaries: dict[tuple[str | None, str | None, int, int, int], dict[str, object]] = {}
    for key, bucket in aggregates.items():
        sample_count = max(bucket["sample_count"], 1.0)
        notice_samples = max(bucket["notice_minutes_samples"], 1.0)
        fill_latency_samples = max(bucket["fill_latency_minutes_samples"], 1.0)
        summaries[key] = {
            f"callout_sample_count_{lookback_days}d": int(bucket["sample_count"]),
            f"callout_filled_rate_{lookback_days}d": round(bucket["filled_count"] / sample_count, 4),
            f"callout_notice_minutes_mean_{lookback_days}d": (
                round(bucket["notice_minutes_total"] / notice_samples, 2)
                if bucket["notice_minutes_samples"] > 0
                else None
            ),
            f"callout_fill_latency_minutes_mean_{lookback_days}d": (
                round(bucket["fill_latency_minutes_total"] / fill_latency_samples, 2)
                if bucket["fill_latency_minutes_samples"] > 0
                else None
            ),
        }
    return summaries
