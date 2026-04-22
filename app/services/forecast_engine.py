from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from math import ceil
from statistics import mean

from app.schemas.auto_scheduler import GeneratedDemandPayload, ProposedShiftPayload
from app.schemas.labor_forecasting import LaborForecastPointPayload

BASELINE_FORECAST_MODEL_VERSION = "baseline_bucketed_v1"
FORECAST_SHAPING_POLICY_VERSION = "forecast_shape_v1"
FORECAST_MATERIALIZATION_RULE_VERSION = "ceil_remaining_headcount_v1"
_ATTENDANCE_LOOKBACK_DAYS = 56
_CALLOUT_LOOKBACK_DAYS = 56
_POS_ORDER_COUNT_PER_HEADCOUNT = 18.0
_POS_GROSS_SALES_CENTS_PER_HEADCOUNT = 45_000.0
_FORECAST_HEADCOUNT_THRESHOLD = 0.5


def build_baseline_labor_forecast_points(
    snapshot,
    *,
    forecast_model_version: str = BASELINE_FORECAST_MODEL_VERSION,
) -> list[LaborForecastPointPayload]:
    points: list[LaborForecastPointPayload] = []
    snapshot_points = sorted(
        getattr(snapshot, "points", []) or [],
        key=lambda item: (
            item.window_start if hasattr(item, "window_start") else item.bucket_start,
            str(item.location_id or ""),
            str(item.role_id or ""),
        ),
    )

    for snapshot_point in snapshot_points:
        feature_payload = dict(getattr(snapshot_point, "feature_payload", {}) or {})
        predicted_headcount, signal_payload = _predicted_headcount_for_bucket(feature_payload)
        duration_hours = max(
            (
                (
                    getattr(snapshot_point, "bucket_end", None)
                    or getattr(snapshot_point, "window_end", None)
                )
                - (
                    getattr(snapshot_point, "bucket_start", None)
                    or getattr(snapshot_point, "window_start", None)
                )
            ).total_seconds()
            / 3600,
            0.0,
        )
        confidence = _forecast_confidence(feature_payload)
        points.append(
            LaborForecastPointPayload(
                location_id=getattr(snapshot_point, "location_id", None),
                role_id=getattr(snapshot_point, "role_id", None),
                window_start=getattr(snapshot_point, "bucket_start", None)
                or getattr(snapshot_point, "window_start", None),
                window_end=getattr(snapshot_point, "bucket_end", None)
                or getattr(snapshot_point, "window_end", None),
                predicted_headcount=round(predicted_headcount, 4),
                predicted_labor_hours=round(predicted_headcount * duration_hours, 4),
                confidence=confidence,
                forecast_payload={
                    "engine_type": "baseline_bucketed",
                    "engine_version": forecast_model_version,
                    "timezone_name": str(
                        feature_payload.get("timezone_name") or getattr(snapshot, "timezone_name", "UTC")
                    ),
                    "existing_fixed_headcount": int(feature_payload.get("fixed_headcount") or 0),
                    "existing_generated_headcount": int(feature_payload.get("generated_headcount") or 0),
                    **signal_payload,
                },
            )
        )
    return points


def build_generated_demand_from_forecast_run(
    forecast_run,
    *,
    timezone_name: str,
    shaping_policy_version: str = FORECAST_SHAPING_POLICY_VERSION,
    materialization_rule_version: str = FORECAST_MATERIALIZATION_RULE_VERSION,
    materialization_threshold: float = _FORECAST_HEADCOUNT_THRESHOLD,
) -> GeneratedDemandPayload:
    proposed_shifts: list[ProposedShiftPayload] = []
    rows = sorted(
        getattr(forecast_run, "points", []) or [],
        key=lambda item: (
            item.window_start,
            str(item.location_id or ""),
            str(item.role_id or ""),
            str(item.id or ""),
        ),
    )

    current_group: dict[str, object] | None = None
    for point in rows:
        forecast_payload = dict(getattr(point, "forecast_payload", {}) or {})
        remaining_headcount = max(
            float(point.predicted_headcount)
            - float(forecast_payload.get("existing_fixed_headcount") or 0)
            - float(forecast_payload.get("existing_generated_headcount") or 0),
            0.0,
        )
        materialized_headcount = ceil(remaining_headcount) if remaining_headcount >= materialization_threshold else 0

        if (
            materialized_headcount <= 0
            or point.location_id is None
            or point.role_id is None
        ):
            if current_group is not None:
                proposed_shifts.append(
                    _proposed_shift_from_group(
                        current_group,
                        forecast_run=forecast_run,
                        timezone_name=timezone_name,
                        shaping_policy_version=shaping_policy_version,
                        materialization_rule_version=materialization_rule_version,
                    )
                )
                current_group = None
            continue

        group_key = (
            point.location_id,
            point.role_id,
            materialized_headcount,
            point.window_start,
        )
        if (
            current_group is None
            or current_group["location_id"] != point.location_id
            or current_group["role_id"] != point.role_id
            or current_group["headcount"] != materialized_headcount
            or current_group["window_end"] != point.window_start
        ):
            if current_group is not None:
                proposed_shifts.append(
                    _proposed_shift_from_group(
                        current_group,
                        forecast_run=forecast_run,
                        timezone_name=timezone_name,
                        shaping_policy_version=shaping_policy_version,
                        materialization_rule_version=materialization_rule_version,
                    )
                )
            current_group = {
                "group_key": group_key,
                "location_id": point.location_id,
                "role_id": point.role_id,
                "window_start": point.window_start,
                "window_end": point.window_end,
                "headcount": materialized_headcount,
                "raw_predicted_headcounts": [float(point.predicted_headcount)],
                "remaining_headcounts": [remaining_headcount],
                "confidences": [float(point.confidence)],
                "point_ids": [str(point.id)],
            }
        else:
            current_group["window_end"] = point.window_end
            current_group["raw_predicted_headcounts"].append(float(point.predicted_headcount))
            current_group["remaining_headcounts"].append(remaining_headcount)
            current_group["confidences"].append(float(point.confidence))
            current_group["point_ids"].append(str(point.id))

    if current_group is not None:
        proposed_shifts.append(
            _proposed_shift_from_group(
                current_group,
                forecast_run=forecast_run,
                timezone_name=timezone_name,
                shaping_policy_version=shaping_policy_version,
                materialization_rule_version=materialization_rule_version,
            )
        )

    return GeneratedDemandPayload(
        proposed_shifts=proposed_shifts,
        metadata={
            "source": "baseline_forecast_engine",
            "labor_forecast_run_id": str(forecast_run.id),
            "labor_forecast_point_count": len(rows),
            "generated_shift_count": len(proposed_shifts),
            "forecast_shaping_policy_version": shaping_policy_version,
            "forecast_materialization_rule_version": materialization_rule_version,
        },
    )


def _predicted_headcount_for_bucket(feature_payload: Mapping[str, object]) -> tuple[float, dict[str, object]]:
    attendance_samples = float(feature_payload.get(f"attendance_sample_count_{_ATTENDANCE_LOOKBACK_DAYS}d") or 0)
    attendance_baseline = attendance_samples / max(_ATTENDANCE_LOOKBACK_DAYS / 7.0, 1.0)

    sales_signal = _sales_signal_headcount(feature_payload)
    blended_baseline = attendance_baseline
    if sales_signal is not None:
        blended_baseline = (
            (attendance_baseline * 0.7) + (sales_signal * 0.3)
            if attendance_baseline > 0
            else sales_signal * 0.6
        )

    no_show_rate = float(feature_payload.get(f"attendance_no_show_rate_{_ATTENDANCE_LOOKBACK_DAYS}d") or 0.0)
    callout_samples = float(feature_payload.get(f"callout_sample_count_{_CALLOUT_LOOKBACK_DAYS}d") or 0)
    callout_pressure = callout_samples / max(_CALLOUT_LOOKBACK_DAYS / 7.0, 1.0)
    risk_uplift = min((callout_pressure * 0.15) + (no_show_rate * 0.2), 0.35)
    weather_factor = _weather_headcount_factor(feature_payload.get("weather_severity_flag"))
    predicted_headcount = max(blended_baseline * (1.0 + risk_uplift) * weather_factor, 0.0)

    return predicted_headcount, {
        "attendance_baseline_headcount_56d": round(attendance_baseline, 4),
        "sales_signal_headcount_28d": round(sales_signal, 4) if sales_signal is not None else None,
        "blended_baseline_headcount": round(blended_baseline, 4),
        "callout_pressure_56d": round(callout_pressure, 4),
        "attendance_no_show_rate_56d": round(no_show_rate, 4),
        "risk_uplift_factor": round(risk_uplift, 4),
        "weather_headcount_factor": round(weather_factor, 4),
    }


def _sales_signal_headcount(feature_payload: Mapping[str, object]) -> float | None:
    sales_samples = int(feature_payload.get("pos_sales_sample_count_28d") or 0)
    if sales_samples <= 0:
        return None

    signals: list[float] = []
    order_count = feature_payload.get("pos_order_count_mean_28d")
    if order_count is not None:
        signals.append(max(float(order_count) / _POS_ORDER_COUNT_PER_HEADCOUNT, 0.0))
    gross_sales_cents = feature_payload.get("pos_gross_sales_cents_mean_28d")
    if gross_sales_cents is not None:
        signals.append(max(float(gross_sales_cents) / _POS_GROSS_SALES_CENTS_PER_HEADCOUNT, 0.0))
    if not signals:
        return None
    return mean(signals)


def _forecast_confidence(feature_payload: Mapping[str, object]) -> float:
    attendance_samples = float(feature_payload.get(f"attendance_sample_count_{_ATTENDANCE_LOOKBACK_DAYS}d") or 0)
    sales_samples = float(feature_payload.get("pos_sales_sample_count_28d") or 0)
    callout_samples = float(feature_payload.get(f"callout_sample_count_{_CALLOUT_LOOKBACK_DAYS}d") or 0)
    weather_flag = str(feature_payload.get("weather_severity_flag") or "none").strip().lower()

    confidence = 0.15
    confidence += min(attendance_samples / 16.0, 1.0) * 0.5
    confidence += 0.15 if sales_samples > 0 else 0.0
    confidence += 0.1 if callout_samples > 0 else 0.0
    confidence += 0.05 if weather_flag not in {"", "none", "unknown"} else 0.0
    return round(min(max(confidence, 0.05), 0.95), 4)


def _weather_headcount_factor(severity_flag: object) -> float:
    normalized = str(severity_flag or "none").strip().lower()
    return {
        "none": 1.0,
        "monitor": 1.05,
        "warning": 1.12,
        "severe": 1.2,
    }.get(normalized, 1.0)


def _proposed_shift_from_group(
    group: Mapping[str, object],
    *,
    forecast_run,
    timezone_name: str,
    shaping_policy_version: str,
    materialization_rule_version: str,
) -> ProposedShiftPayload:
    point_ids = list(group["point_ids"])
    starts_at = group["window_start"]
    ends_at = group["window_end"]
    location_id = group["location_id"]
    role_id = group["role_id"]
    headcount = int(group["headcount"])
    demand_key = (
        f"forecast:{location_id}:{role_id}:{starts_at.isoformat()}:{ends_at.isoformat()}:{headcount}"
    )
    return ProposedShiftPayload(
        demand_key=demand_key,
        source_type="forecast",
        generation_version=shaping_policy_version,
        source_run_id=forecast_run.id,
        source_point_id=point_ids[0],
        location_id=location_id,
        role_id=role_id,
        timezone=timezone_name,
        starts_at=starts_at,
        ends_at=ends_at,
        headcount=headcount,
        premium_cents=0,
        requires_manager_approval=False,
        generation_payload={
            "forecast_point_ids": point_ids,
            "forecast_bucket_count": len(point_ids),
            "forecast_model_version": getattr(forecast_run, "forecast_model_version", BASELINE_FORECAST_MODEL_VERSION),
            "forecast_confidence_mean": round(mean(group["confidences"]), 4),
            "raw_predicted_headcount_mean": round(mean(group["raw_predicted_headcounts"]), 4),
            "raw_predicted_headcount_max": round(max(group["raw_predicted_headcounts"]), 4),
            "remaining_predicted_headcount_mean": round(mean(group["remaining_headcounts"]), 4),
            "remaining_predicted_headcount_max": round(max(group["remaining_headcounts"]), 4),
            "shaping_policy_version": shaping_policy_version,
            "materialization_rule_version": materialization_rule_version,
        },
    )
