from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


class LaborForecastPointPayload(BaseSchema):
    location_id: Optional[UUID] = None
    role_id: Optional[UUID] = None
    window_start: datetime
    window_end: datetime
    predicted_headcount: float = Field(ge=0.0)
    predicted_labor_hours: Optional[float] = Field(default=None, ge=0.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    forecast_payload: dict = Field(default_factory=dict)


class LaborForecastRunContract(BaseSchema):
    planning_window_start: datetime
    planning_window_end: datetime
    forecast_model_version: str = "v1"
    feature_snapshot_hash: str
    points: list[LaborForecastPointPayload] = Field(default_factory=list)
    forecast_metadata: dict = Field(default_factory=dict)


class LaborForecastRunRead(BaseSchema):
    id: UUID
    business_id: UUID
    location_id: Optional[UUID] = None
    planning_window_start: datetime
    planning_window_end: datetime
    forecast_model_version: str
    feature_snapshot_hash: str
    status: str
    forecast_metadata: dict
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class LaborForecastPointRead(BaseSchema):
    id: UUID
    labor_forecast_run_id: UUID
    location_id: Optional[UUID] = None
    role_id: Optional[UUID] = None
    window_start: datetime
    window_end: datetime
    predicted_headcount: float
    predicted_labor_hours: Optional[float] = None
    confidence: float
    forecast_payload: dict
    created_at: datetime
    updated_at: datetime


class LaborForecastRunDetailRead(LaborForecastRunRead):
    points: list[LaborForecastPointRead] = Field(default_factory=list)
