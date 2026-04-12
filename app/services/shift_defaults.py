from __future__ import annotations

from collections import Counter
from math import ceil, floor
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Business, Location

SHIFT_PRESET_ORDER = ("morning", "afternoon", "evening", "night")
SHIFT_PRESET_LABELS = {
    "morning": "Morning",
    "afternoon": "Afternoon",
    "evening": "Evening",
    "night": "Night",
}
FALLBACK_SHIFT_PRESETS = [
    {"key": "morning", "label": "Morning", "start_hour": 7, "end_hour": 15},
    {"key": "afternoon", "label": "Afternoon", "start_hour": 11, "end_hour": 19},
    {"key": "evening", "label": "Evening", "start_hour": 15, "end_hour": 23},
    {"key": "night", "label": "Night", "start_hour": 23, "end_hour": 7},
]


def _normalize_hour(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        hour = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        hour = int(value.strip())
    else:
        return None
    if 0 <= hour <= 23:
        return hour
    return None


def _normalize_label(key: str, value: object) -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return SHIFT_PRESET_LABELS.get(key, key.replace("_", " ").strip().title() or "Shift")


def normalize_shift_presets(raw: object) -> list[dict[str, object]] | None:
    if not isinstance(raw, list):
        return None

    normalized: list[dict[str, object]] = []
    seen_keys: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            return None
        key = item.get("key")
        if not isinstance(key, str):
            return None
        key = key.strip()
        if not key or key in seen_keys:
            return None
        start_hour = _normalize_hour(item.get("start_hour"))
        end_hour = _normalize_hour(item.get("end_hour"))
        if start_hour is None or end_hour is None:
            return None
        seen_keys.add(key)
        normalized.append({
            "key": key,
            "label": _normalize_label(key, item.get("label")),
            "start_hour": start_hour,
            "end_hour": end_hour,
        })

    if not normalized:
        return None

    return normalized


def _parse_google_time(info: object) -> tuple[int, int] | None:
    if not isinstance(info, dict):
        return None

    raw_time = info.get("time")
    if isinstance(raw_time, str):
        digits = raw_time.strip()
        if len(digits) == 4 and digits.isdigit():
            hour = int(digits[:2])
            minute = int(digits[2:])
            if 0 <= hour <= 24 and 0 <= minute <= 59:
                if hour == 24 and minute != 0:
                    return None
                return hour % 24, minute

    raw_hour = info.get("hour")
    raw_minute = info.get("minute")
    if isinstance(raw_hour, int) and isinstance(raw_minute, int):
        hour = raw_hour
        minute = raw_minute
        if 0 <= hour <= 24 and 0 <= minute <= 59:
            if hour == 24 and minute != 0:
                return None
            return hour % 24, minute

    return None


def _parse_open_spans(regular_opening_hours: object) -> list[tuple[int, int]]:
    if not isinstance(regular_opening_hours, dict):
        return []

    periods = regular_opening_hours.get("periods")
    if not isinstance(periods, list):
        return []

    day_spans: dict[int, tuple[int, int]] = {}
    generic_spans: list[tuple[int, int]] = []

    for period in periods:
        if not isinstance(period, dict):
            continue
        open_info = period.get("open")
        close_info = period.get("close")
        start = _parse_google_time(open_info)
        end = _parse_google_time(close_info)
        if start is None or end is None:
            continue

        open_day = open_info.get("day") if isinstance(open_info, dict) else None
        close_day = close_info.get("day") if isinstance(close_info, dict) else None
        start_minutes = start[0] * 60 + start[1]
        end_minutes = end[0] * 60 + end[1]

        if isinstance(open_day, int) and 0 <= open_day <= 6:
            if isinstance(close_day, int) and 0 <= close_day <= 6:
                day_delta = close_day - open_day
                if day_delta < 0:
                    day_delta += 7
            else:
                day_delta = 0 if end_minutes > start_minutes else 1
            end_offset = (day_delta * 24 * 60) + end_minutes
            if end_offset <= start_minutes:
                end_offset += 24 * 60
            current = day_spans.get(open_day)
            if current is None:
                day_spans[open_day] = (start_minutes, end_offset)
            else:
                day_spans[open_day] = (
                    min(current[0], start_minutes),
                    max(current[1], end_offset),
                )
            continue

        if end_minutes <= start_minutes:
            end_minutes += 24 * 60
        generic_spans.append((start_minutes, end_minutes))

    if day_spans:
        return list(day_spans.values())
    return generic_spans


def _round_span_to_hours(start_minutes: int, end_minutes: int) -> tuple[int, int] | None:
    start_hour = floor(start_minutes / 60)
    end_hour = ceil(end_minutes / 60)
    if end_hour <= start_hour:
        end_hour += 24
    duration = end_hour - start_hour
    if duration < 4:
        return None
    return start_hour, end_hour


def _representative_span(location: Location | None) -> tuple[int, int] | None:
    if location is None:
        return None

    spans = _parse_open_spans(
        (location.google_place_metadata or {}).get("regular_opening_hours"),
    )
    if not spans:
        return None

    rounded_spans = [span for raw in spans if (span := _round_span_to_hours(*raw)) is not None]
    if not rounded_spans:
        return None

    counts = Counter(rounded_spans)
    return max(
        counts.keys(),
        key=lambda item: (counts[item], item[1] - item[0], -item[0]),
    )


def derive_shift_presets_from_location(location: Location | None) -> list[dict[str, object]]:
    span = _representative_span(location)
    if span is None:
        return [dict(item) for item in FALLBACK_SHIFT_PRESETS]

    start_hour, end_hour = span
    boundaries = [
        start_hour,
        start_hour + ((end_hour - start_hour) // 4),
        start_hour + ((end_hour - start_hour) // 2),
        start_hour + (((end_hour - start_hour) * 3) // 4),
        end_hour,
    ]

    presets: list[dict[str, object]] = []
    for index, key in enumerate(SHIFT_PRESET_ORDER):
        presets.append(
            {
                "key": key,
                "label": SHIFT_PRESET_LABELS[key],
                "start_hour": boundaries[index] % 24,
                "end_hour": boundaries[index + 1] % 24,
            }
        )
    return presets


def read_business_shift_presets(
    business: Business,
    *,
    fallback_location: Location | None = None,
) -> tuple[list[dict[str, object]], bool, UUID | None]:
    settings = dict(business.settings or {})
    presets = normalize_shift_presets(settings.get("shift_defaults"))
    derived_from_location_id = settings.get("shift_defaults_seeded_from_location_id")
    if isinstance(derived_from_location_id, str):
        try:
            derived_from_location_id = UUID(derived_from_location_id)
        except ValueError:
            derived_from_location_id = None
    elif not isinstance(derived_from_location_id, UUID):
        derived_from_location_id = None

    if presets is not None:
        return presets, True, derived_from_location_id

    return (
        derive_shift_presets_from_location(fallback_location),
        False,
        fallback_location.id if fallback_location is not None else None,
    )


def read_location_shift_override(location: Location) -> list[dict[str, object]] | None:
    settings = dict(location.settings or {})
    return normalize_shift_presets(settings.get("shift_defaults_override"))


async def seed_business_shift_defaults_from_location(
    session: AsyncSession,
    *,
    business: Business,
    location: Location,
) -> bool:
    _, persisted, _ = read_business_shift_presets(business)
    if persisted:
        return False

    next_settings = dict(business.settings or {})
    next_settings["shift_defaults"] = derive_shift_presets_from_location(location)
    next_settings["shift_defaults_source"] = "location_seed"
    next_settings["shift_defaults_seeded_from_location_id"] = str(location.id)
    business.settings = next_settings
    await session.flush()
    return True
