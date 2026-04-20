from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.common import LaborForecastRunStatus
from app.models.labor_forecasting import LaborForecastRun
from app.schemas.labor_forecasting import LaborForecastPointPayload
from app.services import labor_forecasting


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


def test_build_labor_forecast_contract_normalizes_points():
    planning_window_start = datetime(2026, 4, 27, 0, 0, tzinfo=timezone.utc)
    planning_window_end = datetime(2026, 5, 4, 0, 0, tzinfo=timezone.utc)
    location_id = uuid4()
    role_id = uuid4()

    contract = labor_forecasting.build_labor_forecast_contract(
        planning_window_start=planning_window_start,
        planning_window_end=planning_window_end,
        feature_snapshot_hash="sha256:features",
        points=[
            {
                "location_id": location_id,
                "role_id": role_id,
                "window_start": datetime(2026, 4, 28, 16, 0, tzinfo=timezone.utc),
                "window_end": datetime(2026, 4, 28, 22, 0, tzinfo=timezone.utc),
                "predicted_headcount": 2,
                "predicted_labor_hours": 12,
                "confidence": 0.8,
                "forecast_payload": {"source": "pattern"},
            }
        ],
        forecast_metadata={"source_type": "historical_pattern"},
    )

    assert contract.planning_window_start == planning_window_start
    assert contract.planning_window_end == planning_window_end
    assert contract.feature_snapshot_hash == "sha256:features"
    assert contract.forecast_metadata["source_type"] == "historical_pattern"
    assert len(contract.points) == 1
    assert isinstance(contract.points[0], LaborForecastPointPayload)
    assert contract.points[0].location_id == location_id
    assert contract.points[0].role_id == role_id


def test_build_labor_forecast_feature_snapshot_hash_is_stable():
    business_id = str(uuid4())
    hash_one = labor_forecasting.build_labor_forecast_feature_snapshot_hash(
        {
            "business_id": business_id,
            "features": [
                {"key": "weather", "value": "sunny"},
                {"key": "weekday", "value": 2},
            ],
        }
    )
    hash_two = labor_forecasting.build_labor_forecast_feature_snapshot_hash(
        {
            "features": [
                {"value": "sunny", "key": "weather"},
                {"value": 2, "key": "weekday"},
            ],
            "business_id": business_id,
        }
    )

    assert hash_one.startswith("sha256:")
    assert hash_two.startswith("sha256:")
    assert hash_one == hash_two


@pytest.mark.asyncio
async def test_create_labor_forecast_run_persists_header():
    session = _FakeSession()
    business_id = uuid4()
    location_id = uuid4()
    contract = labor_forecasting.build_labor_forecast_contract(
        planning_window_start=datetime(2026, 4, 27, 0, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 5, 4, 0, 0, tzinfo=timezone.utc),
        feature_snapshot_hash="sha256:features",
        forecast_metadata={"source_type": "historical_pattern"},
    )

    forecast_run = await labor_forecasting.create_labor_forecast_run(
        session,
        business_id=business_id,
        location_id=location_id,
        contract=contract,
        status=LaborForecastRunStatus.queued,
    )

    assert forecast_run.business_id == business_id
    assert forecast_run.location_id == location_id
    assert forecast_run.status == LaborForecastRunStatus.queued
    assert forecast_run.forecast_metadata["source_type"] == "historical_pattern"
    assert session.added[-1] is forecast_run
    assert session.flush_count == 1


@pytest.mark.asyncio
async def test_record_labor_forecast_result_replaces_points_and_completes_run():
    session = _FakeSession()
    forecast_run = LaborForecastRun(
        id=uuid4(),
        business_id=uuid4(),
        location_id=uuid4(),
        planning_window_start=datetime(2026, 4, 27, 0, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 5, 4, 0, 0, tzinfo=timezone.utc),
        forecast_model_version="v1",
        feature_snapshot_hash="sha256:features",
        status=LaborForecastRunStatus.queued,
        forecast_metadata={"source_type": "historical_pattern"},
    )
    forecast_run.points = []

    updated_run = await labor_forecasting.record_labor_forecast_result(
        session,
        forecast_run,
        status=LaborForecastRunStatus.completed,
        points=[
            {
                "location_id": forecast_run.location_id,
                "role_id": uuid4(),
                "window_start": datetime(2026, 4, 28, 16, 0, tzinfo=timezone.utc),
                "window_end": datetime(2026, 4, 28, 22, 0, tzinfo=timezone.utc),
                "predicted_headcount": 2,
                "predicted_labor_hours": 12,
                "confidence": 0.82,
                "forecast_payload": {"source": "historical_pattern"},
            }
        ],
        forecast_metadata={"source_count": 4},
    )

    assert updated_run is forecast_run
    assert updated_run.status == LaborForecastRunStatus.completed
    assert updated_run.completed_at is not None
    assert updated_run.forecast_metadata["source_count"] == 4
    assert len(updated_run.points) == 1
    assert float(updated_run.points[0].predicted_headcount) == 2.0
    assert float(updated_run.points[0].predicted_labor_hours) == 12.0
    assert float(updated_run.points[0].confidence) == 0.82
    assert session.flush_count == 1


@pytest.mark.asyncio
async def test_load_and_list_labor_forecast_runs_return_rows():
    session = _FakeSession()
    forecast_run = LaborForecastRun(
        id=uuid4(),
        business_id=uuid4(),
        location_id=uuid4(),
        planning_window_start=datetime(2026, 4, 27, 0, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 5, 4, 0, 0, tzinfo=timezone.utc),
        forecast_model_version="v1",
        feature_snapshot_hash="sha256:features",
        status=LaborForecastRunStatus.running,
        forecast_metadata={},
    )
    forecast_run.points = []
    session.get_result = forecast_run
    session.execute_rows = [forecast_run]

    loaded = await labor_forecasting.load_labor_forecast_run(session, forecast_run.id)
    listed = await labor_forecasting.list_labor_forecast_runs(
        session,
        business_id=forecast_run.business_id,
        location_id=forecast_run.location_id,
        status=LaborForecastRunStatus.running,
    )

    assert loaded is forecast_run
    assert listed == [forecast_run]
