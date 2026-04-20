from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.common import LaborForecastRunStatus
from app.models.labor_forecasting import LaborForecastPoint, LaborForecastRun
from app.schemas.labor_forecasting import LaborForecastPointPayload, LaborForecastRunContract
from app.services.auto_scheduler import stable_payload_hash


def build_labor_forecast_contract(
    *,
    planning_window_start: datetime,
    planning_window_end: datetime,
    feature_snapshot_hash: str,
    points: Sequence[LaborForecastPointPayload | Mapping[str, object]] | None = None,
    forecast_model_version: str = "v1",
    forecast_metadata: Mapping[str, object] | None = None,
) -> LaborForecastRunContract:
    normalized_points = [
        point if isinstance(point, LaborForecastPointPayload) else LaborForecastPointPayload.model_validate(point)
        for point in (points or [])
    ]
    return LaborForecastRunContract(
        planning_window_start=planning_window_start,
        planning_window_end=planning_window_end,
        forecast_model_version=forecast_model_version,
        feature_snapshot_hash=feature_snapshot_hash,
        points=list(normalized_points),
        forecast_metadata=dict(forecast_metadata or {}),
    )


def build_labor_forecast_feature_snapshot_hash(
    payload: Mapping[str, object],
) -> str:
    return stable_payload_hash(payload)


async def create_labor_forecast_run(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None,
    contract: LaborForecastRunContract,
    status: LaborForecastRunStatus = LaborForecastRunStatus.queued,
    started_at: datetime | None = None,
) -> LaborForecastRun:
    forecast_run = LaborForecastRun(
        business_id=business_id,
        location_id=location_id,
        planning_window_start=contract.planning_window_start,
        planning_window_end=contract.planning_window_end,
        forecast_model_version=contract.forecast_model_version,
        feature_snapshot_hash=contract.feature_snapshot_hash,
        status=status,
        forecast_metadata=dict(contract.forecast_metadata or {}),
        started_at=started_at,
    )
    session.add(forecast_run)
    await session.flush()
    return forecast_run


async def record_labor_forecast_result(
    session: AsyncSession,
    forecast_run: LaborForecastRun,
    *,
    status: LaborForecastRunStatus | None = None,
    points: Sequence[LaborForecastPointPayload | Mapping[str, object]] | None = None,
    forecast_metadata: Mapping[str, object] | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> LaborForecastRun:
    if forecast_metadata:
        forecast_run.forecast_metadata = {
            **(forecast_run.forecast_metadata or {}),
            **dict(forecast_metadata),
        }
    if started_at is not None:
        forecast_run.started_at = started_at

    if points is not None:
        forecast_run.points[:] = []
        for raw_point in points:
            point = (
                raw_point
                if isinstance(raw_point, LaborForecastPointPayload)
                else LaborForecastPointPayload.model_validate(raw_point)
            )
            row = LaborForecastPoint(
                labor_forecast_run_id=forecast_run.id,
                location_id=point.location_id,
                role_id=point.role_id,
                window_start=point.window_start,
                window_end=point.window_end,
                predicted_headcount=Decimal(str(point.predicted_headcount)),
                predicted_labor_hours=(
                    Decimal(str(point.predicted_labor_hours))
                    if point.predicted_labor_hours is not None
                    else None
                ),
                confidence=Decimal(str(point.confidence)),
                forecast_payload=dict(point.forecast_payload or {}),
            )
            session.add(row)
            forecast_run.points.append(row)

    if status is not None:
        forecast_run.status = status
        if status == LaborForecastRunStatus.running and forecast_run.started_at is None:
            forecast_run.started_at = datetime.now(timezone.utc)
        if status in {
            LaborForecastRunStatus.completed,
            LaborForecastRunStatus.failed,
            LaborForecastRunStatus.cancelled,
        }:
            forecast_run.completed_at = completed_at or datetime.now(timezone.utc)

    await session.flush()
    return forecast_run


async def load_labor_forecast_run(
    session: AsyncSession,
    labor_forecast_run_id: UUID,
) -> LaborForecastRun | None:
    return await session.get(
        LaborForecastRun,
        labor_forecast_run_id,
        populate_existing=True,
        options=(selectinload(LaborForecastRun.points),),
    )


async def list_labor_forecast_runs(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None = None,
    status: LaborForecastRunStatus | str | None = None,
    limit: int = 25,
) -> list[LaborForecastRun]:
    stmt = (
        select(LaborForecastRun)
        .where(LaborForecastRun.business_id == business_id)
        .order_by(LaborForecastRun.created_at.desc(), LaborForecastRun.id.desc())
        .limit(max(1, min(limit, 100)))
        .options(selectinload(LaborForecastRun.points))
    )
    if location_id is not None:
        stmt = stmt.where(LaborForecastRun.location_id == location_id)
    if status is not None:
        normalized_status = (
            status if isinstance(status, LaborForecastRunStatus) else LaborForecastRunStatus(str(status))
        )
        stmt = stmt.where(LaborForecastRun.status == normalized_status)
    result = await session.execute(stmt)
    return list(result.scalars().all())
