from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import forecast_engine


def test_build_baseline_labor_forecast_points_blends_historical_signals():
    snapshot = SimpleNamespace(
        timezone_name="America/Los_Angeles",
        points=[
            SimpleNamespace(
                id=uuid4(),
                location_id=uuid4(),
                role_id=uuid4(),
                bucket_start=datetime(2026, 4, 22, 16, 0, tzinfo=timezone.utc),
                bucket_end=datetime(2026, 4, 22, 17, 0, tzinfo=timezone.utc),
                feature_payload={
                    "timezone_name": "America/Los_Angeles",
                    "attendance_sample_count_56d": 16,
                    "attendance_no_show_rate_56d": 0.125,
                    "pos_sales_sample_count_28d": 8,
                    "pos_order_count_mean_28d": 18,
                    "pos_gross_sales_cents_mean_28d": 45_000,
                    "callout_sample_count_56d": 4,
                    "weather_severity_flag": "monitor",
                    "fixed_headcount": 0,
                    "generated_headcount": 0,
                },
            )
        ],
    )

    points = forecast_engine.build_baseline_labor_forecast_points(snapshot)

    assert len(points) == 1
    point = points[0]
    assert point.predicted_headcount == pytest.approx(1.9635, rel=1e-4)
    assert point.predicted_labor_hours == pytest.approx(1.9635, rel=1e-4)
    assert point.confidence == pytest.approx(0.95, rel=1e-4)
    assert point.forecast_payload["attendance_baseline_headcount_56d"] == pytest.approx(2.0, rel=1e-4)
    assert point.forecast_payload["sales_signal_headcount_28d"] == pytest.approx(1.0, rel=1e-4)
    assert point.forecast_payload["risk_uplift_factor"] == pytest.approx(0.1, rel=1e-4)
    assert point.forecast_payload["weather_headcount_factor"] == pytest.approx(1.05, rel=1e-4)


def test_build_generated_demand_from_forecast_run_materializes_remaining_headcount():
    location_id = uuid4()
    role_id = uuid4()
    first_point_id = uuid4()
    second_point_id = uuid4()
    forecast_run = SimpleNamespace(
        id=uuid4(),
        forecast_model_version=forecast_engine.BASELINE_FORECAST_MODEL_VERSION,
        points=[
            SimpleNamespace(
                id=first_point_id,
                location_id=location_id,
                role_id=role_id,
                window_start=datetime(2026, 4, 22, 16, 0, tzinfo=timezone.utc),
                window_end=datetime(2026, 4, 22, 17, 0, tzinfo=timezone.utc),
                predicted_headcount=1.8,
                confidence=0.82,
                forecast_payload={
                    "existing_fixed_headcount": 1,
                    "existing_generated_headcount": 0,
                },
            ),
            SimpleNamespace(
                id=second_point_id,
                location_id=location_id,
                role_id=role_id,
                window_start=datetime(2026, 4, 22, 17, 0, tzinfo=timezone.utc),
                window_end=datetime(2026, 4, 22, 18, 0, tzinfo=timezone.utc),
                predicted_headcount=1.7,
                confidence=0.78,
                forecast_payload={
                    "existing_fixed_headcount": 1,
                    "existing_generated_headcount": 0,
                },
            ),
        ],
    )

    generated_demand = forecast_engine.build_generated_demand_from_forecast_run(
        forecast_run,
        timezone_name="America/Los_Angeles",
    )

    assert len(generated_demand.proposed_shifts) == 1
    proposed_shift = generated_demand.proposed_shifts[0]
    assert proposed_shift.source_type == "forecast"
    assert proposed_shift.source_run_id == forecast_run.id
    assert proposed_shift.source_point_id == first_point_id
    assert proposed_shift.headcount == 1
    assert proposed_shift.starts_at == datetime(2026, 4, 22, 16, 0, tzinfo=timezone.utc)
    assert proposed_shift.ends_at == datetime(2026, 4, 22, 18, 0, tzinfo=timezone.utc)
    assert proposed_shift.generation_payload["forecast_bucket_count"] == 2
    assert proposed_shift.generation_payload["forecast_point_ids"] == [
        str(first_point_id),
        str(second_point_id),
    ]
    assert generated_demand.metadata["generated_shift_count"] == 1
