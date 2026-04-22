from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.common import BucketAlignmentMode, DemandFeatureSnapshotStatus, DstHandlingMode
from app.models.demand_features import (
    DemandFeatureSnapshot,
    DemandFeatureSnapshotPoint,
    WeatherForecastSnapshot,
)
from app.schemas.feature_snapshots import (
    DemandFeatureSnapshotContract,
    DemandFeatureSnapshotPointPayload,
)
from app.schemas.weather import LocationWeatherForecastRead
from app.services.payload_utils import stable_payload_hash, stable_payload_json


def _json_safe_mapping(payload: Mapping[str, object] | None) -> dict[str, object]:
    return json.loads(stable_payload_json(dict(payload or {})))


def _decimal_value(value: float | int | str | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


def build_demand_feature_snapshot_contract(
    *,
    planning_window_start: datetime,
    planning_window_end: datetime,
    timezone_name: str,
    bucket_minutes: int,
    points: Sequence[DemandFeatureSnapshotPointPayload | Mapping[str, object]] | None = None,
    bucket_alignment_mode: BucketAlignmentMode | str = BucketAlignmentMode.local_operating_time,
    dst_handling_mode: DstHandlingMode | str = DstHandlingMode.skip_missing_repeat_distinct,
    feature_schema_version: str = "v1",
    snapshot_status: DemandFeatureSnapshotStatus | str = DemandFeatureSnapshotStatus.completed,
    source_summary: Mapping[str, object] | None = None,
    operating_hours_version: str | None = None,
) -> DemandFeatureSnapshotContract:
    normalized_points = [
        point
        if isinstance(point, DemandFeatureSnapshotPointPayload)
        else DemandFeatureSnapshotPointPayload.model_validate(point)
        for point in (points or [])
    ]
    return DemandFeatureSnapshotContract(
        planning_window_start=planning_window_start,
        planning_window_end=planning_window_end,
        timezone_name=timezone_name,
        bucket_minutes=bucket_minutes,
        bucket_alignment_mode=bucket_alignment_mode,
        dst_handling_mode=dst_handling_mode,
        feature_schema_version=feature_schema_version,
        snapshot_status=snapshot_status,
        operating_hours_version=operating_hours_version,
        source_summary=dict(source_summary or {}),
        points=list(normalized_points),
    )


def build_demand_feature_snapshot_hash(
    contract: DemandFeatureSnapshotContract,
) -> str:
    ordered_points = sorted(
        (
            {
                "location_id": str(point.location_id) if point.location_id is not None else None,
                "role_id": str(point.role_id) if point.role_id is not None else None,
                "bucket_start": point.bucket_start.isoformat(),
                "bucket_end": point.bucket_end.isoformat(),
                "feature_vector_version": point.feature_vector_version,
                "feature_payload": _json_safe_mapping(point.feature_payload),
            }
            for point in contract.points
        ),
        key=lambda point: (
            point["location_id"] or "",
            point["role_id"] or "",
            point["bucket_start"],
            point["bucket_end"],
            point["feature_vector_version"],
        ),
    )
    return stable_payload_hash(
        {
            "planning_window_start": contract.planning_window_start.isoformat(),
            "planning_window_end": contract.planning_window_end.isoformat(),
            "timezone_name": contract.timezone_name,
            "bucket_minutes": contract.bucket_minutes,
            "bucket_alignment_mode": _enum_value(contract.bucket_alignment_mode),
            "dst_handling_mode": _enum_value(contract.dst_handling_mode),
            "feature_schema_version": contract.feature_schema_version,
            "operating_hours_version": contract.operating_hours_version,
            "source_summary": _json_safe_mapping(contract.source_summary),
            "points": ordered_points,
        }
    )


async def create_demand_feature_snapshot(
    session,
    *,
    business_id: UUID,
    location_id: UUID | None,
    contract: DemandFeatureSnapshotContract,
) -> DemandFeatureSnapshot:
    snapshot = DemandFeatureSnapshot(
        business_id=business_id,
        location_id=location_id,
        planning_window_start=contract.planning_window_start,
        planning_window_end=contract.planning_window_end,
        timezone_name=contract.timezone_name,
        bucket_minutes=contract.bucket_minutes,
        bucket_alignment_mode=contract.bucket_alignment_mode,
        dst_handling_mode=contract.dst_handling_mode,
        snapshot_hash=build_demand_feature_snapshot_hash(contract),
        feature_schema_version=contract.feature_schema_version,
        snapshot_status=contract.snapshot_status,
        operating_hours_version=contract.operating_hours_version,
        source_summary=_json_safe_mapping(contract.source_summary),
    )
    session.add(snapshot)

    for point in contract.points:
        row = DemandFeatureSnapshotPoint(
            demand_feature_snapshot=snapshot,
            location_id=point.location_id,
            role_id=point.role_id,
            bucket_start=point.bucket_start,
            bucket_end=point.bucket_end,
            feature_payload=_json_safe_mapping(point.feature_payload),
            feature_vector_version=point.feature_vector_version,
        )
        session.add(row)

    await session.flush()
    return snapshot


async def load_demand_feature_snapshot(
    session,
    demand_feature_snapshot_id: UUID,
) -> DemandFeatureSnapshot | None:
    return await session.get(
        DemandFeatureSnapshot,
        demand_feature_snapshot_id,
        populate_existing=True,
        options=(selectinload(DemandFeatureSnapshot.points),),
    )


async def record_weather_forecast_snapshot(
    session,
    forecast: LocationWeatherForecastRead,
    *,
    forecast_generated_at: datetime | None = None,
    source_payload: Mapping[str, object] | None = None,
) -> list[WeatherForecastSnapshot]:
    generated_at = forecast_generated_at or forecast.fetched_at
    ingested_at = datetime.now(timezone.utc)
    rows: list[WeatherForecastSnapshot] = []

    for point in forecast.points:
        row = WeatherForecastSnapshot(
            business_id=forecast.business_id,
            location_id=forecast.location_id,
            provider=forecast.provider,
            forecast_generated_at=generated_at,
            forecast_valid_at=point.forecast_at,
            bucket_start=point.forecast_at,
            bucket_end=point.forecast_at + timedelta(hours=1),
            temperature_f=_decimal_value(point.temperature_f),
            precipitation_probability=point.precipitation_probability,
            precipitation_inches=_decimal_value(point.precipitation_inches),
            wind_speed_mph=_decimal_value(point.wind_speed_mph),
            weather_code=point.weather_code,
            severity_flag=point.severity_flag,
            source_payload=_json_safe_mapping(
                {
                    "summary": forecast.summary.model_dump(mode="json"),
                    "timezone": forecast.timezone,
                    "range_start": forecast.range_start,
                    "range_end": forecast.range_end,
                    "fetched_at": forecast.fetched_at,
                    "point": point.model_dump(mode="json"),
                    "provider_payload": dict(source_payload or {}),
                }
            ),
            ingested_at=ingested_at,
        )
        session.add(row)
        rows.append(row)

    await session.flush()
    return rows


async def list_weather_forecast_snapshots(
    session,
    *,
    business_id: UUID,
    location_id: UUID | None = None,
    bucket_start: datetime | None = None,
    bucket_end: datetime | None = None,
    limit: int = 5000,
) -> list[WeatherForecastSnapshot]:
    stmt = (
        select(WeatherForecastSnapshot)
        .where(WeatherForecastSnapshot.business_id == business_id)
        .order_by(
            WeatherForecastSnapshot.bucket_start.asc(),
            WeatherForecastSnapshot.forecast_generated_at.desc(),
            WeatherForecastSnapshot.id.desc(),
        )
        .limit(max(1, min(limit, 5000)))
    )
    if location_id is not None:
        stmt = stmt.where(WeatherForecastSnapshot.location_id == location_id)
    if bucket_start is not None:
        stmt = stmt.where(WeatherForecastSnapshot.bucket_start >= bucket_start)
    if bucket_end is not None:
        stmt = stmt.where(WeatherForecastSnapshot.bucket_start < bucket_end)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def build_weather_snapshot_bucket_lookup(
    rows: Sequence[WeatherForecastSnapshot],
) -> dict[tuple[str | None, datetime, datetime], dict[str, object]]:
    latest_rows: dict[tuple[str | None, datetime, datetime], WeatherForecastSnapshot] = {}
    for row in rows:
        key = (
            str(row.location_id) if row.location_id is not None else None,
            row.bucket_start,
            row.bucket_end,
        )
        existing = latest_rows.get(key)
        if existing is None or row.forecast_generated_at > existing.forecast_generated_at:
            latest_rows[key] = row

    return {
        key: {
            "weather_provider": row.provider,
            "weather_forecast_generated_at": row.forecast_generated_at.isoformat(),
            "weather_forecast_valid_at": row.forecast_valid_at.isoformat(),
            "weather_temperature_f": float(row.temperature_f) if row.temperature_f is not None else None,
            "weather_precipitation_probability": row.precipitation_probability,
            "weather_precipitation_inches": (
                float(row.precipitation_inches) if row.precipitation_inches is not None else None
            ),
            "weather_wind_speed_mph": float(row.wind_speed_mph) if row.wind_speed_mph is not None else None,
            "weather_code": row.weather_code,
            "weather_severity_flag": row.severity_flag,
        }
        for key, row in latest_rows.items()
    }
