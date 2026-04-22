from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.common import DemandFeatureSnapshotStatus
from app.models.demand_features import DemandFeatureSnapshot, WeatherForecastSnapshot
from app.schemas.weather import (
    LocationWeatherForecastPointRead,
    LocationWeatherForecastRead,
    LocationWeatherForecastSummaryRead,
)
from app.services import feature_snapshot_builder


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalarResult(self._rows)


class _FakeSession:
    def __init__(self):
        self.added: list[object] = []
        self.flush_count = 0
        self.get_result = None
        self.execute_rows: list[object] = []

    def add(self, instance):
        now = datetime.now(timezone.utc)
        if getattr(instance, "id", None) is None:
            instance.id = uuid4()
        if hasattr(instance, "created_at") and getattr(instance, "created_at", None) is None:
            instance.created_at = now
        if hasattr(instance, "updated_at") and getattr(instance, "updated_at", None) is None:
            instance.updated_at = now
        self.added.append(instance)

    async def flush(self):
        self.flush_count += 1

    async def get(self, model, object_id, **_kwargs):
        if self.get_result is not None and getattr(self.get_result, "id", None) == object_id:
            return self.get_result
        return None

    async def execute(self, _stmt):
        return _FakeExecuteResult(self.execute_rows)


def _weather_forecast() -> LocationWeatherForecastRead:
    business_id = uuid4()
    location_id = uuid4()
    return LocationWeatherForecastRead(
        business_id=business_id,
        location_id=location_id,
        provider="open_meteo",
        timezone="America/Los_Angeles",
        latitude=33.8121,
        longitude=-117.919,
        fetched_at=datetime(2026, 4, 21, 15, 0, tzinfo=timezone.utc),
        range_start=datetime(2026, 4, 22, 14, 0, tzinfo=timezone.utc),
        range_end=datetime(2026, 4, 22, 16, 0, tzinfo=timezone.utc),
        summary=LocationWeatherForecastSummaryRead(
            worst_severity_flag="monitor",
            monitor_hour_count=2,
            high_hour_count=0,
            precipitation_hour_count=1,
            peak_precipitation_inches=0.07,
            peak_wind_speed_mph=12.5,
        ),
        points=[
            LocationWeatherForecastPointRead(
                forecast_at=datetime(2026, 4, 22, 14, 0, tzinfo=timezone.utc),
                temperature_f=67.5,
                precipitation_probability=25,
                precipitation_inches=0.0,
                wind_speed_mph=9.3,
                weather_code=1,
                weather_label="Mainly clear",
                severity_flag="none",
            ),
            LocationWeatherForecastPointRead(
                forecast_at=datetime(2026, 4, 22, 15, 0, tzinfo=timezone.utc),
                temperature_f=64.1,
                precipitation_probability=55,
                precipitation_inches=0.07,
                wind_speed_mph=12.5,
                weather_code=61,
                weather_label="Light rain",
                severity_flag="monitor",
            ),
        ],
    )


def test_build_demand_feature_snapshot_hash_is_stable_across_point_order():
    location_id = uuid4()
    role_id = uuid4()
    contract_one = feature_snapshot_builder.build_demand_feature_snapshot_contract(
        planning_window_start=datetime(2026, 4, 27, 0, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 5, 4, 0, 0, tzinfo=timezone.utc),
        timezone_name="America/Los_Angeles",
        bucket_minutes=60,
        points=[
            {
                "location_id": location_id,
                "role_id": role_id,
                "bucket_start": datetime(2026, 4, 28, 16, 0, tzinfo=timezone.utc),
                "bucket_end": datetime(2026, 4, 28, 17, 0, tzinfo=timezone.utc),
                "feature_payload": {"weather": {"severity": "monitor"}, "dow": 2},
            },
            {
                "location_id": location_id,
                "role_id": role_id,
                "bucket_start": datetime(2026, 4, 28, 17, 0, tzinfo=timezone.utc),
                "bucket_end": datetime(2026, 4, 28, 18, 0, tzinfo=timezone.utc),
                "feature_payload": {"dow": 2, "weather": {"severity": "none"}},
            },
        ],
        source_summary={"sources": ["weather", "schedule_history"]},
    )
    contract_two = feature_snapshot_builder.build_demand_feature_snapshot_contract(
        planning_window_start=contract_one.planning_window_start,
        planning_window_end=contract_one.planning_window_end,
        timezone_name=contract_one.timezone_name,
        bucket_minutes=contract_one.bucket_minutes,
        points=list(reversed(contract_one.points)),
        source_summary={"sources": ["weather", "schedule_history"]},
    )

    hash_one = feature_snapshot_builder.build_demand_feature_snapshot_hash(contract_one)
    hash_two = feature_snapshot_builder.build_demand_feature_snapshot_hash(contract_two)

    assert hash_one.startswith("sha256:")
    assert hash_one == hash_two


@pytest.mark.asyncio
async def test_create_demand_feature_snapshot_persists_header_and_points():
    session = _FakeSession()
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    contract = feature_snapshot_builder.build_demand_feature_snapshot_contract(
        planning_window_start=datetime(2026, 4, 27, 0, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 5, 4, 0, 0, tzinfo=timezone.utc),
        timezone_name="America/Los_Angeles",
        bucket_minutes=60,
        operating_hours_version="hours_v3",
        source_summary={"weather_revision_count": 24},
        points=[
            {
                "location_id": location_id,
                "role_id": role_id,
                "bucket_start": datetime(2026, 4, 28, 16, 0, tzinfo=timezone.utc),
                "bucket_end": datetime(2026, 4, 28, 17, 0, tzinfo=timezone.utc),
                "feature_payload": {
                    "day_of_week": 2,
                    "weather": {"severity_flag": "monitor"},
                    "historical_scheduled_seats": 3,
                },
                "feature_vector_version": "v1",
            }
        ],
    )

    snapshot = await feature_snapshot_builder.create_demand_feature_snapshot(
        session,
        business_id=business_id,
        location_id=location_id,
        contract=contract,
    )

    assert snapshot.business_id == business_id
    assert snapshot.location_id == location_id
    assert snapshot.snapshot_status == DemandFeatureSnapshotStatus.completed
    assert snapshot.operating_hours_version == "hours_v3"
    assert snapshot.snapshot_hash.startswith("sha256:")
    assert len(snapshot.points) == 1
    assert snapshot.points[0].role_id == role_id
    assert snapshot.points[0].feature_payload["historical_scheduled_seats"] == 3
    assert session.flush_count == 1


@pytest.mark.asyncio
async def test_load_demand_feature_snapshot_returns_row():
    session = _FakeSession()
    snapshot = DemandFeatureSnapshot(
        id=uuid4(),
        business_id=uuid4(),
        location_id=uuid4(),
        planning_window_start=datetime(2026, 4, 27, 0, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 5, 4, 0, 0, tzinfo=timezone.utc),
        timezone_name="America/Los_Angeles",
        bucket_minutes=60,
        snapshot_hash="sha256:test",
        feature_schema_version="v1",
        snapshot_status=DemandFeatureSnapshotStatus.completed,
        source_summary={},
    )
    snapshot.points = []
    session.get_result = snapshot

    loaded = await feature_snapshot_builder.load_demand_feature_snapshot(session, snapshot.id)

    assert loaded is snapshot


@pytest.mark.asyncio
async def test_record_weather_forecast_snapshot_persists_rows():
    session = _FakeSession()
    forecast = _weather_forecast()

    rows = await feature_snapshot_builder.record_weather_forecast_snapshot(
        session,
        forecast,
        source_payload={"provider_revision": "r1"},
    )

    assert len(rows) == 2
    assert rows[0].business_id == forecast.business_id
    assert rows[0].location_id == forecast.location_id
    assert rows[0].forecast_generated_at == forecast.fetched_at
    assert rows[0].bucket_end > rows[0].bucket_start
    assert float(rows[1].precipitation_inches) == pytest.approx(0.07)
    assert rows[1].source_payload["provider_payload"]["provider_revision"] == "r1"
    assert rows[1].source_payload["point"]["severity_flag"] == "monitor"


def test_build_weather_snapshot_bucket_lookup_prefers_latest_revision():
    location_id = uuid4()
    older = WeatherForecastSnapshot(
        id=uuid4(),
        business_id=uuid4(),
        location_id=location_id,
        provider="open_meteo",
        forecast_generated_at=datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc),
        forecast_valid_at=datetime(2026, 4, 22, 14, 0, tzinfo=timezone.utc),
        bucket_start=datetime(2026, 4, 22, 14, 0, tzinfo=timezone.utc),
        bucket_end=datetime(2026, 4, 22, 15, 0, tzinfo=timezone.utc),
        temperature_f=67.0,
        precipitation_probability=10,
        precipitation_inches=0,
        wind_speed_mph=8.0,
        weather_code=1,
        severity_flag="none",
        source_payload={},
        ingested_at=datetime(2026, 4, 21, 10, 5, tzinfo=timezone.utc),
    )
    newer = WeatherForecastSnapshot(
        id=uuid4(),
        business_id=older.business_id,
        location_id=location_id,
        provider="open_meteo",
        forecast_generated_at=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        forecast_valid_at=older.forecast_valid_at,
        bucket_start=older.bucket_start,
        bucket_end=older.bucket_end,
        temperature_f=64.0,
        precipitation_probability=70,
        precipitation_inches=0.12,
        wind_speed_mph=15.0,
        weather_code=61,
        severity_flag="monitor",
        source_payload={},
        ingested_at=datetime(2026, 4, 21, 12, 5, tzinfo=timezone.utc),
    )

    lookup = feature_snapshot_builder.build_weather_snapshot_bucket_lookup([older, newer])

    key = (str(location_id), older.bucket_start, older.bucket_end)
    assert lookup[key]["weather_severity_flag"] == "monitor"
    assert lookup[key]["weather_precipitation_probability"] == 70
    assert lookup[key]["weather_forecast_generated_at"] == newer.forecast_generated_at.isoformat()
