from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
from typing import Any

from app.services import ai_policy, ai_prompts
from app.services.ai_runtime import run_structured


@dataclass
class OpenShiftCreationExtraction:
    fields: dict[str, Any]
    runtime: dict[str, Any]


@dataclass
class ShiftEditExtraction:
    fields: dict[str, Any]
    runtime: dict[str, Any]


async def extract_open_shift_creation(
    *,
    text: str,
    channel: str,
    context: dict[str, Any] | None = None,
) -> OpenShiftCreationExtraction:
    normalized_context = dict(context or {})
    response = await run_structured(
        ai_prompts.build_open_shift_creation_request(
            text=text,
            channel=channel,
            context=normalized_context,
        ),
        provider_override=ai_policy.select_intent_provider(channel=channel),
    )
    parsed = _normalize_open_shift_creation_fields(
        response.parsed_output,
        context=normalized_context,
    )
    return OpenShiftCreationExtraction(
        fields=parsed,
        runtime={
            "policy_provider": ai_policy.select_intent_provider(channel=channel),
            "requested_provider": response.requested_provider,
            "provider": response.provider,
            "model": response.model,
            "request_id": response.request_id,
            "latency_ms": response.latency_ms,
            "usage": dict(response.usage or {}),
            "fallback_used": bool(response.fallback_used),
            "fallback_provider": response.fallback_provider,
            "fallback_reason": response.fallback_reason,
            "primary_error": response.primary_error,
        },
    )


async def extract_shift_edit(
    *,
    text: str,
    channel: str,
    context: dict[str, Any] | None = None,
) -> ShiftEditExtraction:
    normalized_context = dict(context or {})
    response = await run_structured(
        ai_prompts.build_shift_edit_request(
            text=text,
            channel=channel,
            context=normalized_context,
        ),
        provider_override=ai_policy.select_intent_provider(channel=channel),
    )
    parsed = _normalize_shift_edit_fields(
        response.parsed_output,
        context=normalized_context,
    )
    return ShiftEditExtraction(
        fields=parsed,
        runtime={
            "policy_provider": ai_policy.select_intent_provider(channel=channel),
            "requested_provider": response.requested_provider,
            "provider": response.provider,
            "model": response.model,
            "request_id": response.request_id,
            "latency_ms": response.latency_ms,
            "usage": dict(response.usage or {}),
            "fallback_used": bool(response.fallback_used),
            "fallback_provider": response.fallback_provider,
            "fallback_reason": response.fallback_reason,
            "primary_error": response.primary_error,
        },
    )


def _normalize_open_shift_creation_fields(
    raw_fields: dict[str, Any],
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    week_start_hint = _normalize_date(context.get("week_start_date"))

    role = _normalize_role(context.get("role") or raw_fields.get("role"))
    shift_date = _normalize_date(context.get("date") or raw_fields.get("date"), week_start_hint=week_start_hint)
    start_time = _normalize_time(context.get("start_time") or raw_fields.get("start_time"))
    end_time = _normalize_time(
        context.get("end_time") or raw_fields.get("end_time"),
        start_time=start_time,
    )

    spans_midnight = context.get("spans_midnight")
    if spans_midnight is None:
        spans_midnight = raw_fields.get("spans_midnight")
    if spans_midnight is None and start_time and end_time:
        spans_midnight = end_time < start_time

    return {
        "role": role,
        "date": shift_date,
        "start_time": start_time,
        "end_time": end_time,
        "spans_midnight": bool(spans_midnight) if spans_midnight is not None else None,
        "start_open_shift_offer": bool(
            context.get("start_open_shift_offer")
            if "start_open_shift_offer" in context
            else raw_fields.get("start_open_shift_offer")
        ),
        "shift_label": _normalize_optional_text(context.get("shift_label") or raw_fields.get("shift_label")),
        "notes": _normalize_optional_text(context.get("notes") or raw_fields.get("notes")),
        "pay_rate": _normalize_pay_rate(context.get("pay_rate") if "pay_rate" in context else raw_fields.get("pay_rate")),
        "requirements": _normalize_string_list(context.get("requirements") if "requirements" in context else raw_fields.get("requirements")),
    }


def _normalize_shift_edit_fields(
    raw_fields: dict[str, Any],
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    week_start_hint = _normalize_date(context.get("week_start_date"))

    role = _normalize_role(context.get("role") or raw_fields.get("role"))
    shift_date = _normalize_date(context.get("date") or raw_fields.get("date"), week_start_hint=week_start_hint)
    start_time = _normalize_time(context.get("start_time") or raw_fields.get("start_time"))
    end_time = _normalize_time(
        context.get("end_time") or raw_fields.get("end_time"),
        start_time=start_time,
    )

    spans_midnight = context.get("spans_midnight")
    if spans_midnight is None:
        spans_midnight = raw_fields.get("spans_midnight")
    if spans_midnight is None and start_time and end_time:
        spans_midnight = end_time < start_time

    patch: dict[str, Any] = {}
    if role is not None:
        patch["role"] = role
    if shift_date is not None:
        patch["date"] = shift_date
    if start_time is not None:
        patch["start_time"] = start_time
    if end_time is not None:
        patch["end_time"] = end_time
    if spans_midnight is not None and ("start_time" in patch or "end_time" in patch):
        patch["spans_midnight"] = bool(spans_midnight)

    shift_label = _normalize_optional_text(context.get("shift_label") or raw_fields.get("shift_label"))
    notes = _normalize_optional_text(context.get("notes") or raw_fields.get("notes"))
    pay_rate = _normalize_pay_rate(context.get("pay_rate") if "pay_rate" in context else raw_fields.get("pay_rate"))
    requirements = _normalize_string_list(context.get("requirements") if "requirements" in context else raw_fields.get("requirements"))

    if shift_label is not None:
        patch["shift_label"] = shift_label
    if notes is not None:
        patch["notes"] = notes
    if pay_rate is not None:
        patch["pay_rate"] = pay_rate
    if requirements:
        patch["requirements"] = requirements
    return patch


def _normalize_role(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    return normalized or None


def _normalize_optional_text(value: Any) -> str | None:
    raw = str(value or "").strip()
    return raw or None


def _normalize_string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        items = [segment.strip() for segment in value.split(",")]
    elif isinstance(value, list):
        items = [str(item or "").strip() for item in value]
    else:
        return []
    return [item for item in items if item]


def _normalize_pay_rate(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_date(value: Any, *, week_start_hint: str | None = None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    iso_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", raw)
    if iso_match:
        return iso_match.group(1)

    parsed = _parse_month_date(raw, week_start_hint=week_start_hint)
    if parsed:
        return parsed

    weekday_date = _parse_weekday_date(raw, week_start_hint=week_start_hint)
    if weekday_date:
        return weekday_date

    return None


def _parse_month_date(raw: str, *, week_start_hint: str | None = None) -> str | None:
    cleaned = re.sub(r"\s+", " ", raw.replace(",", " ")).strip()
    base_year = None
    if week_start_hint:
        try:
            base_year = date.fromisoformat(week_start_hint).year
        except ValueError:
            base_year = None
    patterns = (
        ("%B %d %Y", cleaned),
        ("%b %d %Y", cleaned),
        ("%B %d", cleaned),
        ("%b %d", cleaned),
    )
    for fmt, candidate in patterns:
        try:
            parsed = datetime.strptime(candidate, fmt)
        except ValueError:
            continue
        year = parsed.year if "%Y" in fmt else (base_year or date.today().year)
        return date(year, parsed.month, parsed.day).isoformat()
    return None


def _parse_weekday_date(raw: str, *, week_start_hint: str | None = None) -> str | None:
    if not week_start_hint:
        return None
    normalized = raw.strip().lower()
    weekdays = {
        "monday": 0,
        "mon": 0,
        "tuesday": 1,
        "tue": 1,
        "tues": 1,
        "wednesday": 2,
        "wed": 2,
        "thursday": 3,
        "thu": 3,
        "thurs": 3,
        "friday": 4,
        "fri": 4,
        "saturday": 5,
        "sat": 5,
        "sunday": 6,
        "sun": 6,
    }
    target = weekdays.get(normalized)
    if target is None:
        return None
    try:
        start = date.fromisoformat(week_start_hint)
    except ValueError:
        return None
    return (start + timedelta(days=target)).isoformat()


def _normalize_time(value: Any, *, start_time: str | None = None) -> str | None:
    raw = str(value or "").strip().lower()
    if not raw:
        return None

    cleaned = raw.replace(".", ":")
    if re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", cleaned):
        return cleaned
    if re.fullmatch(r"\d{1,2}:\d{2}", cleaned):
        hours, minutes = cleaned.split(":")
        return f"{int(hours):02d}:{int(minutes):02d}:00"
    if re.fullmatch(r"\d{1,2}", cleaned):
        hour = int(cleaned)
        if start_time is not None:
            try:
                start_hour = int(start_time[:2])
            except ValueError:
                start_hour = None
            if start_hour is not None and hour <= start_hour and hour < 12:
                hour += 12
        return f"{hour:02d}:00:00"

    time_patterns = (
        "%I:%M %p",
        "%I %p",
        "%I:%M%p",
        "%I%p",
    )
    compact = cleaned.replace("am", " am").replace("pm", " pm")
    compact = re.sub(r"\s+", " ", compact).strip()
    for fmt in time_patterns:
        try:
            parsed = datetime.strptime(compact.upper(), fmt)
        except ValueError:
            continue
        return time(parsed.hour, parsed.minute, 0).isoformat()

    return None
