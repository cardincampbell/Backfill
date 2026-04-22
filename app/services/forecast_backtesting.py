from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from statistics import mean
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.demand_features import AttendanceHistoryFact, PosSalesFact
from app.models.labor_forecasting import LaborForecastRun
from app.schemas.forecast_backtesting import (
    ForecastBacktestRead,
    ForecastBacktestSummaryRead,
    ForecastBucketBacktestRead,
    ForecastCalibrationBandRead,
)
from app.services import labor_forecasting

ACTUALS_FINALIZATION_POLICY_VERSION = "bucket_plus_48h_v1"
DEFAULT_FINALIZATION_DELAY = timedelta(hours=48)
_CONFIDENCE_BANDS: tuple[tuple[str, float, float], ...] = (
    ("low", 0.0, 0.34),
    ("medium", 0.34, 0.67),
    ("high", 0.67, 1.01),
)


async def build_forecast_backtest(
    session: AsyncSession,
    *,
    labor_forecast_run_id: UUID,
    as_of: datetime | None = None,
) -> ForecastBacktestRead | None:
    forecast_run = await labor_forecasting.load_labor_forecast_run(session, labor_forecast_run_id)
    if forecast_run is None:
        return None

    effective_as_of = as_of or datetime.now(timezone.utc)
    attendance_rows = await _list_attendance_facts_for_window(
        session,
        business_id=forecast_run.business_id,
        location_id=forecast_run.location_id,
        window_start=forecast_run.planning_window_start,
        window_end=forecast_run.planning_window_end,
    )
    pos_rows = await _list_pos_sales_facts_for_window(
        session,
        business_id=forecast_run.business_id,
        location_id=forecast_run.location_id,
        window_start=forecast_run.planning_window_start,
        window_end=forecast_run.planning_window_end,
    )

    buckets: list[ForecastBucketBacktestRead] = []
    finalized_buckets: list[ForecastBucketBacktestRead] = []
    for point in sorted(
        forecast_run.points or [],
        key=lambda row: (row.window_start, str(row.location_id or ""), str(row.role_id or "")),
    ):
        actual_labor_hours = _actual_labor_hours_for_bucket(
            attendance_rows,
            location_id=point.location_id,
            role_id=point.role_id,
            bucket_start=point.window_start,
            bucket_end=point.window_end,
        )
        bucket_duration_hours = max((point.window_end - point.window_start).total_seconds() / 3600.0, 0.0)
        actual_headcount = round(actual_labor_hours / bucket_duration_hours, 4) if bucket_duration_hours > 0 else 0.0
        finalization = evaluate_actuals_finalization(
            bucket_end=point.window_end,
            as_of=effective_as_of,
            finalization_delay=DEFAULT_FINALIZATION_DELAY,
            attendance_rows=attendance_rows,
            pos_rows=pos_rows,
        )
        bucket = ForecastBucketBacktestRead(
            labor_forecast_point_id=point.id,
            location_id=point.location_id,
            role_id=point.role_id,
            bucket_start=point.window_start,
            bucket_end=point.window_end,
            predicted_headcount=round(float(point.predicted_headcount), 4),
            predicted_labor_hours=(
                round(float(point.predicted_labor_hours), 4)
                if point.predicted_labor_hours is not None
                else None
            ),
            confidence=round(float(point.confidence), 4),
            actual_headcount=actual_headcount,
            actual_labor_hours=round(actual_labor_hours, 4),
            headcount_error=round(actual_headcount - float(point.predicted_headcount), 4),
            labor_hours_error=round(
                actual_labor_hours - float(point.predicted_labor_hours or 0.0),
                4,
            ),
            actuals_completeness_status=finalization["actuals_completeness_status"],
            actuals_finalized_at=finalization["actuals_finalized_at"],
            actuals_finalization_policy_version=finalization["actuals_finalization_policy_version"],
            pending_reasons=list(finalization["pending_reasons"]),
            forecast_payload=dict(point.forecast_payload or {}),
            actuals_payload={
                "attendance_fact_count": int(
                    _attendance_fact_count_for_bucket(
                        attendance_rows,
                        location_id=point.location_id,
                        role_id=point.role_id,
                        bucket_start=point.window_start,
                        bucket_end=point.window_end,
                    )
                ),
                "pos_fact_count": int(_pos_fact_count_for_bucket(pos_rows, point.window_start, point.window_end)),
            },
        )
        buckets.append(bucket)
        if bucket.actuals_completeness_status == "finalized":
            finalized_buckets.append(bucket)

    summary = _build_summary(
        finalized_buckets=finalized_buckets,
        pending_bucket_count=len(buckets) - len(finalized_buckets),
        total_bucket_count=len(buckets),
    )
    return ForecastBacktestRead(
        labor_forecast_run_id=forecast_run.id,
        business_id=forecast_run.business_id,
        location_id=forecast_run.location_id,
        planning_window_start=forecast_run.planning_window_start,
        planning_window_end=forecast_run.planning_window_end,
        as_of=effective_as_of,
        actuals_finalization_policy_version=ACTUALS_FINALIZATION_POLICY_VERSION,
        summary=summary,
        buckets=buckets,
    )


def evaluate_actuals_finalization(
    *,
    bucket_end: datetime,
    as_of: datetime,
    finalization_delay: timedelta = DEFAULT_FINALIZATION_DELAY,
    attendance_rows: Sequence[AttendanceHistoryFact] = (),
    pos_rows: Sequence[PosSalesFact] = (),
) -> dict[str, object]:
    finalizable_at = bucket_end + finalization_delay
    pending_reasons: list[str] = []
    if as_of < finalizable_at:
        pending_reasons.append("finalization_delay_window_open")

    latest_attendance_ingested_at = max(
        (row.ingested_at for row in attendance_rows if row.ingested_at is not None),
        default=None,
    )
    latest_pos_ingested_at = max(
        (row.ingested_at for row in pos_rows if row.ingested_at is not None),
        default=None,
    )

    status = "finalized" if not pending_reasons else "pending"
    return {
        "actuals_completeness_status": status,
        "actuals_finalized_at": finalizable_at if status == "finalized" else None,
        "actuals_finalization_policy_version": ACTUALS_FINALIZATION_POLICY_VERSION,
        "pending_reasons": pending_reasons,
        "latest_attendance_ingested_at": latest_attendance_ingested_at,
        "latest_pos_ingested_at": latest_pos_ingested_at,
    }


async def _list_attendance_facts_for_window(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None,
    window_start: datetime,
    window_end: datetime,
) -> list[AttendanceHistoryFact]:
    stmt = (
        select(AttendanceHistoryFact)
        .where(
            AttendanceHistoryFact.business_id == business_id,
            AttendanceHistoryFact.starts_at < window_end,
            AttendanceHistoryFact.ends_at > window_start,
        )
        .order_by(AttendanceHistoryFact.starts_at.asc(), AttendanceHistoryFact.id.asc())
    )
    if location_id is not None:
        stmt = stmt.where(AttendanceHistoryFact.location_id == location_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _list_pos_sales_facts_for_window(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None,
    window_start: datetime,
    window_end: datetime,
) -> list[PosSalesFact]:
    stmt = (
        select(PosSalesFact)
        .where(
            PosSalesFact.business_id == business_id,
            PosSalesFact.bucket_start < window_end,
            PosSalesFact.bucket_end > window_start,
        )
        .order_by(PosSalesFact.bucket_start.asc(), PosSalesFact.id.asc())
    )
    if location_id is not None:
        stmt = stmt.where(PosSalesFact.location_id == location_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _actual_labor_hours_for_bucket(
    rows: Sequence[AttendanceHistoryFact],
    *,
    location_id: UUID | None,
    role_id: UUID | None,
    bucket_start: datetime,
    bucket_end: datetime,
) -> float:
    actual_labor_hours = 0.0
    for row in rows:
        if location_id is not None and row.location_id != location_id:
            continue
        if role_id is not None and row.role_id != role_id:
            continue
        overlap_hours = _overlap_hours(
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            bucket_start=bucket_start,
            bucket_end=bucket_end,
        )
        if overlap_hours <= 0:
            continue
        worked_ratio = _worked_hours_ratio(row)
        actual_labor_hours += overlap_hours * worked_ratio
    return actual_labor_hours


def _attendance_fact_count_for_bucket(
    rows: Sequence[AttendanceHistoryFact],
    location_id: UUID | None,
    role_id: UUID | None,
    bucket_start: datetime,
    bucket_end: datetime,
) -> int:
    return sum(
        1
        for row in rows
        if (location_id is None or row.location_id == location_id)
        and (role_id is None or row.role_id == role_id)
        and _overlap_hours(
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            bucket_start=bucket_start,
            bucket_end=bucket_end,
        )
        > 0
    )


def _pos_fact_count_for_bucket(
    rows: Sequence[PosSalesFact],
    bucket_start: datetime,
    bucket_end: datetime,
) -> int:
    return sum(
        1
        for row in rows
        if row.bucket_start < bucket_end and row.bucket_end > bucket_start
    )


def _worked_hours_ratio(row: AttendanceHistoryFact) -> float:
    scheduled_hours = float(row.scheduled_hours or 0.0)
    worked_hours = float(row.worked_hours or 0.0)
    if scheduled_hours <= 0:
        return 0.0
    return max(min(worked_hours / scheduled_hours, 1.5), 0.0)


def _overlap_hours(
    *,
    starts_at: datetime,
    ends_at: datetime,
    bucket_start: datetime,
    bucket_end: datetime,
) -> float:
    overlap_start = max(starts_at, bucket_start)
    overlap_end = min(ends_at, bucket_end)
    if overlap_end <= overlap_start:
        return 0.0
    return (overlap_end - overlap_start).total_seconds() / 3600.0


def _build_summary(
    *,
    finalized_buckets: Sequence[ForecastBucketBacktestRead],
    pending_bucket_count: int,
    total_bucket_count: int,
) -> ForecastBacktestSummaryRead:
    finalized_count = len(finalized_buckets)
    headcount_errors = [bucket.headcount_error for bucket in finalized_buckets]
    labor_hours_errors = [bucket.labor_hours_error for bucket in finalized_buckets]
    confidences = [bucket.confidence for bucket in finalized_buckets]
    calibration = _confidence_calibration(finalized_buckets)

    return ForecastBacktestSummaryRead(
        finalized_bucket_count=finalized_count,
        pending_bucket_count=pending_bucket_count,
        finalized_bucket_rate=round(finalized_count / total_bucket_count, 4) if total_bucket_count > 0 else 1.0,
        headcount_mae=round(mean(abs(error) for error in headcount_errors), 4) if headcount_errors else None,
        headcount_bias=round(mean(headcount_errors), 4) if headcount_errors else None,
        labor_hours_mae=round(mean(abs(error) for error in labor_hours_errors), 4) if labor_hours_errors else None,
        labor_hours_bias=round(mean(labor_hours_errors), 4) if labor_hours_errors else None,
        mean_confidence=round(mean(confidences), 4) if confidences else None,
        confidence_calibration=calibration,
    )


def _confidence_calibration(
    finalized_buckets: Sequence[ForecastBucketBacktestRead],
) -> list[ForecastCalibrationBandRead]:
    grouped: dict[str, list[ForecastBucketBacktestRead]] = defaultdict(list)
    for bucket in finalized_buckets:
        grouped[_confidence_band_label(bucket.confidence)].append(bucket)

    rows: list[ForecastCalibrationBandRead] = []
    for label, _lower, _upper in _CONFIDENCE_BANDS:
        buckets = grouped.get(label, [])
        if not buckets:
            rows.append(
                ForecastCalibrationBandRead(
                    label=label,
                    bucket_count=0,
                    mean_confidence=0.0,
                )
            )
            continue
        errors = [abs(bucket.headcount_error) for bucket in buckets]
        rows.append(
            ForecastCalibrationBandRead(
                label=label,
                bucket_count=len(buckets),
                mean_confidence=round(mean(bucket.confidence for bucket in buckets), 4),
                within_half_headcount_rate=round(
                    sum(1 for error in errors if error <= 0.5) / len(errors),
                    4,
                ),
                within_one_headcount_rate=round(
                    sum(1 for error in errors if error <= 1.0) / len(errors),
                    4,
                ),
                headcount_mae=round(mean(errors), 4),
            )
        )
    return rows


def _confidence_band_label(confidence: float) -> str:
    for label, lower, upper in _CONFIDENCE_BANDS:
        if lower <= confidence < upper:
            return label
    return _CONFIDENCE_BANDS[-1][0]
