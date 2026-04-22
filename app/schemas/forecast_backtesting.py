from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


class ForecastBucketBacktestRead(BaseSchema):
    labor_forecast_point_id: UUID
    location_id: Optional[UUID] = None
    role_id: Optional[UUID] = None
    bucket_start: datetime
    bucket_end: datetime
    predicted_headcount: float
    predicted_labor_hours: Optional[float] = None
    confidence: float
    actual_headcount: float
    actual_labor_hours: float
    headcount_error: float
    labor_hours_error: float
    actuals_completeness_status: Literal["pending", "finalized"]
    actuals_finalized_at: Optional[datetime] = None
    actuals_finalization_policy_version: str
    pending_reasons: list[str] = Field(default_factory=list)
    forecast_payload: dict = Field(default_factory=dict)
    actuals_payload: dict = Field(default_factory=dict)


class ForecastCalibrationBandRead(BaseSchema):
    label: str
    bucket_count: int
    mean_confidence: float
    within_half_headcount_rate: Optional[float] = None
    within_one_headcount_rate: Optional[float] = None
    headcount_mae: Optional[float] = None


class ForecastBacktestSummaryRead(BaseSchema):
    finalized_bucket_count: int
    pending_bucket_count: int
    finalized_bucket_rate: float
    headcount_mae: Optional[float] = None
    headcount_bias: Optional[float] = None
    labor_hours_mae: Optional[float] = None
    labor_hours_bias: Optional[float] = None
    mean_confidence: Optional[float] = None
    confidence_calibration: list[ForecastCalibrationBandRead] = Field(default_factory=list)


class ForecastBacktestRead(BaseSchema):
    labor_forecast_run_id: UUID
    business_id: UUID
    location_id: Optional[UUID] = None
    planning_window_start: datetime
    planning_window_end: datetime
    as_of: datetime
    actuals_finalization_policy_version: str
    summary: ForecastBacktestSummaryRead
    buckets: list[ForecastBucketBacktestRead] = Field(default_factory=list)
