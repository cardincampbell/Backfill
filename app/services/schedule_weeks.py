from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Mapping
from zoneinfo import ZoneInfo

WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass
class ScheduleWeekWindow:
    week_start: date
    week_end: date
    starts_at: datetime
    ends_at: datetime


def normalized_week_start_day(value: str | None) -> str:
    normalized = (value or "monday").strip().lower()
    return normalized if normalized in WEEKDAY_INDEX else "monday"


def effective_week_start_day(
    *,
    business_settings: Mapping[str, object] | None,
    location_settings: Mapping[str, object] | None,
) -> str:
    location_override = location_settings.get("week_start_day") if location_settings else None
    if isinstance(location_override, str):
        return normalized_week_start_day(location_override)

    business_default = business_settings.get("week_start_day") if business_settings else None
    if isinstance(business_default, str):
        return normalized_week_start_day(business_default)

    return "monday"


def week_anchor_for(
    timezone_name: str,
    week_start_day: str | None,
    value: date | None = None,
) -> date:
    current = value or datetime.now(ZoneInfo(timezone_name)).date()
    start_index = WEEKDAY_INDEX[normalized_week_start_day(week_start_day)]
    return current - timedelta(days=(current.weekday() - start_index) % 7)


def schedule_week_window(
    timezone_name: str,
    week_start_day: str | date | None,
    week_start: date | None = None,
) -> ScheduleWeekWindow:
    local_zone = ZoneInfo(timezone_name)
    if isinstance(week_start_day, date):
        week_start = week_start_day
        week_start_day = "monday"
    anchor = week_anchor_for(timezone_name, week_start_day, week_start)
    week_end = anchor + timedelta(days=6)
    starts_at = datetime.combine(anchor, datetime.min.time(), tzinfo=local_zone).astimezone(timezone.utc)
    ends_at = datetime.combine(week_end, datetime.max.time(), tzinfo=local_zone).astimezone(timezone.utc)
    return ScheduleWeekWindow(
        week_start=anchor,
        week_end=week_end,
        starts_at=starts_at,
        ends_at=ends_at,
    )
