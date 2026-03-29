"""
Outreach planning and message formatting.

Policy:
- SMS is always the first written offer when SMS consent exists.
- If the shift starts soon, add an immediate voice call after the SMS to
  maximize attention and confirmation speed.
- If SMS consent is unavailable but voice consent exists, fall back to voice.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

URGENT_SHIFT_HOURS = 4


def _parse_shift_start(shift: dict) -> datetime:
    try:
        return datetime.fromisoformat(f"{shift['date']}T{shift['start_time']}")
    except (ValueError, KeyError) as exc:
        raise ValueError(
            f"Shift {shift.get('id')} has invalid date/time: "
            f"date={shift.get('date')!r} start_time={shift.get('start_time')!r}"
        ) from exc


def hours_until_shift(shift: dict, now: Optional[datetime] = None) -> float:
    current = now or datetime.utcnow()
    delta = _parse_shift_start(shift) - current
    return delta.total_seconds() / 3600


def plan_initial_channels(shift: dict, worker: dict, now: Optional[datetime] = None) -> list[str]:
    hours_to_start = hours_until_shift(shift, now=now)
    sms_ok = worker.get("sms_consent_status") == "granted"
    voice_ok = worker.get("voice_consent_status") == "granted"
    preferred = worker.get("preferred_channel", "sms")

    channels: list[str] = []
    if sms_ok:
        channels.append("sms")

    urgent = hours_to_start <= URGENT_SHIFT_HOURS
    if voice_ok and (urgent or preferred in {"voice", "both"} or not channels):
        channels.append("voice")

    if not channels:
        return []

    deduped: list[str] = []
    for channel in channels:
        if channel not in deduped:
            deduped.append(channel)
    return deduped


def build_reminder_sms(worker: dict, shift: dict, restaurant: Optional[dict]) -> str:
    restaurant_name = restaurant["name"] if restaurant else "the restaurant"
    today = date.today()
    shift_day = None
    try:
        shift_day = date.fromisoformat(str(shift["date"]))
    except (TypeError, ValueError, KeyError):
        shift_day = None
    if shift_day == today:
        day_label = "today"
    elif shift_day == today.fromordinal(today.toordinal() + 1):
        day_label = "tomorrow"
    elif shift_day is not None:
        day_label = shift_day.strftime("on %a %b %d")
    else:
        day_label = f"on {shift.get('date')}"
    return (
        f"⏰ Reminder: {worker['name']}, you're confirmed for {restaurant_name} "
        f"({shift['role']}) {day_label} at {shift['start_time']}. "
        "Reply STOP to opt out of texts."
    )


def vacancy_kind(shift: dict) -> str:
    if shift.get("called_out_by") is not None:
        return "callout"
    if (
        shift.get("confirmation_escalated_at") is not None
        or shift.get("check_in_escalated_at") is not None
        or shift.get("escalated_from_worker_id") is not None
    ):
        return "attendance"
    return "open_shift"


def build_initial_sms(worker: dict, shift: dict, restaurant: dict) -> str:
    requirements = shift.get("requirements") or []
    extra = ""
    if requirements:
        extra = f" Req: {', '.join(requirements)}."
    queue_note = " First yes gets the shift." if hours_until_shift(shift) <= URGENT_SHIFT_HOURS else ""
    kind = vacancy_kind(shift)
    if kind == "open_shift":
        prefix = f"Hi {worker['name']}, Backfill has an open shift available at {restaurant['name']}: "
        action = "Reply YES to claim it or NO to pass. Reply STOP to opt out."
    elif kind == "attendance":
        prefix = f"Hi {worker['name']}, Backfill needs urgent coverage at {restaurant['name']}: "
        action = "Reply YES if you can take it or NO to pass. Reply STOP to opt out."
    else:
        prefix = f"Hi {worker['name']}, Backfill needs coverage at {restaurant['name']}: "
        action = "Reply YES if you can cover it or NO to pass. Reply STOP to opt out."
    return (
        f"{prefix}{shift['role']} on {shift['date']} {shift['start_time']}-{shift['end_time']} "
        f"@ ${shift['pay_rate']}/hr.{extra}{queue_note} {action}"
    )
