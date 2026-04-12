from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from app.schemas.common import BaseSchema

WeatherSeverityFlag = Literal["none", "monitor", "high"]


class LocationWeatherForecastPointRead(BaseSchema):
    forecast_at: datetime
    temperature_f: float | None = None
    precipitation_probability: int | None = None
    precipitation_inches: float | None = None
    wind_speed_mph: float | None = None
    weather_code: int | None = None
    weather_label: str
    severity_flag: WeatherSeverityFlag


class LocationWeatherForecastSummaryRead(BaseSchema):
    worst_severity_flag: WeatherSeverityFlag
    monitor_hour_count: int
    high_hour_count: int
    precipitation_hour_count: int
    peak_precipitation_inches: float
    peak_wind_speed_mph: float


class LocationWeatherForecastRead(BaseSchema):
    business_id: UUID
    location_id: UUID
    provider: str
    timezone: str
    latitude: float
    longitude: float
    fetched_at: datetime
    range_start: datetime
    range_end: datetime
    summary: LocationWeatherForecastSummaryRead
    points: list[LocationWeatherForecastPointRead]
