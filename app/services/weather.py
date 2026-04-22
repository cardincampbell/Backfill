from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx

from app.config import settings
from app.schemas.weather import (
    LocationWeatherForecastPointRead,
    LocationWeatherForecastRead,
    LocationWeatherForecastSummaryRead,
    WeatherSeverityFlag,
)
from app.services import businesses, feature_snapshot_builder

_OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_OPEN_METEO_HOURLY_FIELDS = (
    "temperature_2m",
    "precipitation_probability",
    "precipitation",
    "wind_speed_10m",
    "weather_code",
)
_SUPPORTED_PROVIDERS = {"open_meteo"}
logger = logging.getLogger(__name__)

_WEATHER_CODE_LABELS: dict[int, str] = {
    0: "Clear",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Light freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Rain showers",
    82: "Heavy rain showers",
    85: "Light snow showers",
    86: "Snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Severe thunderstorm with hail",
}


@dataclass(frozen=True)
class ForecastWindow:
    range_start: datetime
    range_end: datetime
    request_start: datetime
    request_end: datetime


def _float_value(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _weather_label(code: int | None) -> str:
    if code is None:
        return "Unknown"
    return _WEATHER_CODE_LABELS.get(code, "Unmapped")


def _severity_flag(
    *,
    weather_code: int | None,
    precipitation_probability: int | None,
    precipitation_inches: float | None,
    wind_speed_mph: float | None,
) -> WeatherSeverityFlag:
    precip = precipitation_inches or 0.0
    wind = wind_speed_mph or 0.0
    probability = precipitation_probability or 0
    code = weather_code or -1

    if code in {95, 96, 99} or wind >= 30.0 or precip >= 0.25:
        return "high"
    if code in {
        45,
        48,
        51,
        53,
        55,
        56,
        57,
        61,
        63,
        65,
        66,
        67,
        71,
        73,
        75,
        77,
        80,
        81,
        82,
        85,
        86,
    }:
        return "monitor"
    if wind >= 20.0 or precip >= 0.05 or probability >= 40:
        return "monitor"
    return "none"


def _build_summary(points: list[LocationWeatherForecastPointRead]) -> LocationWeatherForecastSummaryRead:
    worst: WeatherSeverityFlag = "none"
    monitor_hours = 0
    high_hours = 0
    precipitation_hours = 0
    peak_precipitation = 0.0
    peak_wind = 0.0

    for point in points:
        if point.severity_flag == "high":
            worst = "high"
            high_hours += 1
        elif point.severity_flag == "monitor":
            if worst != "high":
                worst = "monitor"
            monitor_hours += 1
        precip = point.precipitation_inches or 0.0
        if precip > 0:
            precipitation_hours += 1
        peak_precipitation = max(peak_precipitation, precip)
        peak_wind = max(peak_wind, point.wind_speed_mph or 0.0)

    return LocationWeatherForecastSummaryRead(
        worst_severity_flag=worst,
        monitor_hour_count=monitor_hours,
        high_hour_count=high_hours,
        precipitation_hour_count=precipitation_hours,
        peak_precipitation_inches=round(peak_precipitation, 3),
        peak_wind_speed_mph=round(peak_wind, 1),
    )


def _resolve_forecast_window(
    *,
    timezone_name: str,
    starts_at: datetime | None,
    ends_at: datetime | None,
    hours: int,
    now: datetime | None,
) -> ForecastWindow:
    if hours < 1:
        raise ValueError("weather_hours_out_of_range")
    if hours > settings.weather_forecast_max_hours:
        raise ValueError("weather_hours_out_of_range")

    reference_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    range_start = starts_at.astimezone(timezone.utc) if starts_at is not None else reference_now.replace(
        minute=0,
        second=0,
        microsecond=0,
    )
    range_end = ends_at.astimezone(timezone.utc) if ends_at is not None else range_start + timedelta(hours=hours)
    if range_end <= range_start:
        raise ValueError("weather_range_invalid")
    if range_end - range_start > timedelta(hours=settings.weather_forecast_max_hours):
        raise ValueError("weather_hours_out_of_range")

    local_zone = ZoneInfo(timezone_name)
    request_start = range_start.astimezone(local_zone).replace(minute=0, second=0, microsecond=0)
    request_end = range_end.astimezone(local_zone)
    if request_end.minute or request_end.second or request_end.microsecond:
        request_end = (request_end + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

    return ForecastWindow(
        range_start=range_start,
        range_end=range_end,
        request_start=request_start,
        request_end=request_end,
    )


async def _fetch_open_meteo_hourly_forecast(
    *,
    latitude: float,
    longitude: float,
    timezone_name: str,
    window: ForecastWindow,
) -> dict[str, Any]:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(_OPEN_METEO_HOURLY_FIELDS),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": timezone_name,
        "start_hour": window.request_start.strftime("%Y-%m-%dT%H:%M"),
        "end_hour": window.request_end.strftime("%Y-%m-%dT%H:%M"),
    }
    async with httpx.AsyncClient(timeout=settings.weather_timeout_seconds) as client:
        response = await client.get(_OPEN_METEO_FORECAST_URL, params=params)
        response.raise_for_status()
        return response.json()


def _normalize_open_meteo_forecast(
    *,
    business_id: UUID,
    location_id: UUID,
    latitude: float,
    longitude: float,
    timezone_name: str,
    payload: dict[str, Any],
    window: ForecastWindow,
    fetched_at: datetime,
) -> LocationWeatherForecastRead:
    local_zone = ZoneInfo(timezone_name)
    hourly = payload.get("hourly") or {}
    raw_times = list(hourly.get("time") or [])
    temps = list(hourly.get("temperature_2m") or [])
    probabilities = list(hourly.get("precipitation_probability") or [])
    precipitations = list(hourly.get("precipitation") or [])
    winds = list(hourly.get("wind_speed_10m") or [])
    codes = list(hourly.get("weather_code") or [])

    points: list[LocationWeatherForecastPointRead] = []
    for index, raw_time in enumerate(raw_times):
        if not isinstance(raw_time, str):
            continue
        try:
            local_time = datetime.fromisoformat(raw_time).replace(tzinfo=local_zone)
        except ValueError:
            continue
        forecast_at = local_time.astimezone(timezone.utc)
        if forecast_at < window.range_start or forecast_at > window.range_end:
            continue

        probability = probabilities[index] if index < len(probabilities) else None
        precipitation = precipitations[index] if index < len(precipitations) else None
        wind = winds[index] if index < len(winds) else None
        code = codes[index] if index < len(codes) else None
        severity = _severity_flag(
            weather_code=code if isinstance(code, int) else int(code) if code is not None else None,
            precipitation_probability=int(probability) if probability is not None else None,
            precipitation_inches=float(precipitation) if precipitation is not None else None,
            wind_speed_mph=float(wind) if wind is not None else None,
        )
        points.append(
            LocationWeatherForecastPointRead(
                forecast_at=forecast_at,
                temperature_f=float(temps[index]) if index < len(temps) and temps[index] is not None else None,
                precipitation_probability=int(probability) if probability is not None else None,
                precipitation_inches=float(precipitation) if precipitation is not None else None,
                wind_speed_mph=float(wind) if wind is not None else None,
                weather_code=int(code) if code is not None else None,
                weather_label=_weather_label(int(code)) if code is not None else "Unknown",
                severity_flag=severity,
            )
        )

    return LocationWeatherForecastRead(
        business_id=business_id,
        location_id=location_id,
        provider="open_meteo",
        timezone=timezone_name,
        latitude=latitude,
        longitude=longitude,
        fetched_at=fetched_at,
        range_start=window.range_start,
        range_end=window.range_end,
        summary=_build_summary(points),
        points=points,
    )


async def get_location_forecast(
    session,
    *,
    business_id: UUID,
    location_id: UUID,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    hours: int = 72,
    now: datetime | None = None,
) -> LocationWeatherForecastRead:
    location = await businesses.get_location(session, business_id, location_id)
    if location is None:
        raise LookupError("location_not_found")

    latitude = _float_value(getattr(location, "latitude", None))
    longitude = _float_value(getattr(location, "longitude", None))
    if latitude is None or longitude is None:
        raise ValueError("location_coordinates_required")

    provider = settings.weather_provider or "open_meteo"
    if provider not in _SUPPORTED_PROVIDERS:
        raise RuntimeError("unsupported_weather_provider")

    window = _resolve_forecast_window(
        timezone_name=location.timezone,
        starts_at=starts_at,
        ends_at=ends_at,
        hours=hours,
        now=now,
    )
    fetched_at = datetime.now(timezone.utc)

    if provider == "open_meteo":
        try:
            payload = await _fetch_open_meteo_hourly_forecast(
                latitude=latitude,
                longitude=longitude,
                timezone_name=location.timezone,
                window=window,
            )
        except httpx.HTTPError as exc:
            raise RuntimeError("weather_provider_request_failed") from exc
        forecast = _normalize_open_meteo_forecast(
            business_id=business_id,
            location_id=location_id,
            latitude=latitude,
            longitude=longitude,
            timezone_name=location.timezone,
            payload=payload,
            window=window,
            fetched_at=fetched_at,
        )
        await _persist_weather_forecast_snapshot_best_effort(
            session,
            forecast,
            source_payload=payload,
        )
        return forecast

    raise RuntimeError("unsupported_weather_provider")


async def _persist_weather_forecast_snapshot_best_effort(
    session,
    forecast: LocationWeatherForecastRead,
    *,
    source_payload: dict[str, Any] | None = None,
) -> None:
    try:
        await feature_snapshot_builder.record_weather_forecast_snapshot(
            session,
            forecast,
            source_payload=source_payload,
        )
    except Exception:
        logger.warning(
            "Failed to persist weather forecast snapshot",
            extra={
                "business_id": str(forecast.business_id),
                "location_id": str(forecast.location_id),
                "provider": forecast.provider,
                "range_start": forecast.range_start.isoformat(),
                "range_end": forecast.range_end.isoformat(),
            },
            exc_info=True,
        )
