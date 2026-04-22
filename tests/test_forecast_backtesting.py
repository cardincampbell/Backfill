from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import forecast_backtesting


@pytest.mark.asyncio
async def test_build_forecast_backtest_computes_finalized_bucket_metrics(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    forecast_point_id = uuid4()
    forecast_run_id = uuid4()
    forecast_run = SimpleNamespace(
        id=forecast_run_id,
        business_id=business_id,
        location_id=location_id,
        planning_window_start=datetime(2026, 4, 20, 16, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 20, 17, 0, tzinfo=timezone.utc),
        points=[
            SimpleNamespace(
                id=forecast_point_id,
                location_id=location_id,
                role_id=role_id,
                window_start=datetime(2026, 4, 20, 16, 0, tzinfo=timezone.utc),
                window_end=datetime(2026, 4, 20, 17, 0, tzinfo=timezone.utc),
                predicted_headcount=1.25,
                predicted_labor_hours=1.25,
                confidence=0.82,
                forecast_payload={"engine_type": "baseline_bucketed"},
            )
        ],
    )
    attendance_row = SimpleNamespace(
        location_id=location_id,
        role_id=role_id,
        starts_at=datetime(2026, 4, 20, 16, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 20, 17, 0, tzinfo=timezone.utc),
        scheduled_hours=1.0,
        worked_hours=1.0,
        ingested_at=datetime(2026, 4, 20, 18, 0, tzinfo=timezone.utc),
    )
    pos_row = SimpleNamespace(
        bucket_start=datetime(2026, 4, 20, 16, 0, tzinfo=timezone.utc),
        bucket_end=datetime(2026, 4, 20, 17, 0, tzinfo=timezone.utc),
        ingested_at=datetime(2026, 4, 20, 18, 0, tzinfo=timezone.utc),
    )

    async def fake_load(_session, labor_forecast_run_id):
        assert labor_forecast_run_id == forecast_run_id
        return forecast_run

    async def fake_attendance(*_args, **_kwargs):
        return [attendance_row]

    async def fake_pos(*_args, **_kwargs):
        return [pos_row]

    monkeypatch.setattr(
        "app.services.forecast_backtesting.labor_forecasting.load_labor_forecast_run",
        fake_load,
    )
    monkeypatch.setattr(
        "app.services.forecast_backtesting._list_attendance_facts_for_window",
        fake_attendance,
    )
    monkeypatch.setattr(
        "app.services.forecast_backtesting._list_pos_sales_facts_for_window",
        fake_pos,
    )

    result = await forecast_backtesting.build_forecast_backtest(
        SimpleNamespace(),
        labor_forecast_run_id=forecast_run_id,
        as_of=datetime(2026, 4, 22, 18, 0, tzinfo=timezone.utc),
    )

    assert result is not None
    assert result.summary.finalized_bucket_count == 1
    assert result.summary.pending_bucket_count == 0
    assert result.summary.headcount_mae == pytest.approx(0.25, rel=1e-4)
    assert result.summary.labor_hours_mae == pytest.approx(0.25, rel=1e-4)
    assert result.summary.confidence_calibration[2].label == "high"
    assert result.summary.confidence_calibration[2].bucket_count == 1

    bucket = result.buckets[0]
    assert bucket.labor_forecast_point_id == forecast_point_id
    assert bucket.actual_headcount == pytest.approx(1.0, rel=1e-4)
    assert bucket.actual_labor_hours == pytest.approx(1.0, rel=1e-4)
    assert bucket.headcount_error == pytest.approx(-0.25, rel=1e-4)
    assert bucket.actuals_completeness_status == "finalized"
    assert bucket.actuals_finalization_policy_version == forecast_backtesting.ACTUALS_FINALIZATION_POLICY_VERSION


def test_evaluate_actuals_finalization_marks_recent_buckets_pending():
    bucket_end = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)

    result = forecast_backtesting.evaluate_actuals_finalization(
        bucket_end=bucket_end,
        as_of=bucket_end + timedelta(hours=12),
    )

    assert result["actuals_completeness_status"] == "pending"
    assert result["actuals_finalized_at"] is None
    assert result["pending_reasons"] == ["finalization_delay_window_open"]
