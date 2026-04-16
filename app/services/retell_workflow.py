from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.business import Location
from app.models.common import (
    AssignmentStatus,
    CoverageCaseStatus,
    OfferStatus,
    RetellConversationType,
    ShiftLifecycleStatus,
    ShiftStaffingStatus,
    ShiftStatus,
)
from app.models.coverage import CoverageCase, CoverageOffer
from app.models.identity import User
from app.models.integrations import RetellConversation
from app.models.scheduling import Shift, ShiftAssignment
from app.models.workforce import Employee
from app.schemas.coverage import CoverageOfferResponseCreate
from app.schemas.scheduling import PublishedShiftAmendmentWrite, ShiftCreate
from app.services import businesses, communication_suppressions, coverage as coverage_service
from app.services import delivery, messaging, scheduler_sync, scheduling, shift_assignments, workforce
from app.config import settings

_CALL_OUT_PATTERNS = (
    re.compile(r"\bcall(?:ing)?\s*out\b"),
    re.compile(r"\bcan(?:not|'?t)\s+make\s+it\b"),
    re.compile(r"\bwon'?t\s+make\s+it\b"),
    re.compile(r"\bwill\s+not\s+make\s+it\b"),
    re.compile(r"\bcan(?:not|'?t)\s+come\s+in\b"),
    re.compile(r"\bwon'?t\s+be\s+able\s+to\s+make\s+it\b"),
    re.compile(r"\bnot\s+coming\s+in\b"),
    re.compile(r"\bneed\s+to\s+call\s+out\b"),
    re.compile(r"\bcalling\s+out\b"),
    re.compile(r"\bsick\b"),
)
_SMS_OPT_OUT_PATTERNS = (
    re.compile(r"\b(?:do\s+not|don't)\s+text\b"),
    re.compile(r"\b(?:do\s+not|don't)\s+call\b"),
    re.compile(r"\bopt\s+out\b"),
    re.compile(r"\bunsubscribe\b"),
    re.compile(r"\bstop\s+text(?:ing)?\b"),
    re.compile(r"\bstop\s+calling\b"),
)
_TODAY_PATTERNS = (
    re.compile(r"\btoday\b"),
    re.compile(r"\blater\s+today\b"),
    re.compile(r"\bthis\s+morning\b"),
    re.compile(r"\bthis\s+afternoon\b"),
    re.compile(r"\bthis\s+evening\b"),
    re.compile(r"\btonight\b"),
)
_TOMORROW_PATTERNS = (re.compile(r"\btomorrow\b"),)
_WEEKDAY_NAMES = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def _first_name(full_name: str | None) -> str | None:
    text = str(full_name or "").strip()
    if not text:
        return None
    return text.split()[0]


def _coerce_retell_dynamic_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _current_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _shift_display_timezone(shift: Shift) -> str:
    timezone_name = str(getattr(shift, "timezone", "") or "").strip()
    if timezone_name:
        return timezone_name
    location_timezone = str(getattr(getattr(shift, "location", None), "timezone", "") or "").strip()
    return location_timezone or "UTC"


def _to_local_shift_time(value: datetime, timezone_name: str) -> datetime:
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        zone = timezone.utc
    return value.astimezone(zone)


def _format_calendar_label(value: datetime) -> str:
    return value.strftime("%A, %B %d").replace(" 0", " ")


def _format_clock_label(value: datetime) -> str:
    return value.strftime("%I:%M %p").lstrip("0")


def _relative_day_label(value: datetime, reference_value: datetime) -> str | None:
    delta_days = (value.date() - reference_value.date()).days
    if delta_days == 0:
        return "Today"
    if delta_days == 1:
        return "Tomorrow"
    if delta_days == -1:
        return "Yesterday"
    return None


def _format_shift_summary(
    *,
    role_name: str | None,
    location_name: str | None,
    starts_at: datetime,
    ends_at: datetime,
    timezone_name: str,
    reference_time: datetime,
) -> dict[str, str]:
    local_start = _to_local_shift_time(starts_at, timezone_name)
    local_end = _to_local_shift_time(ends_at, timezone_name)
    local_reference = _to_local_shift_time(reference_time, timezone_name)
    timezone_abbr = local_start.tzname() or timezone_name
    base_date_label = _format_calendar_label(local_start)
    relative_label = _relative_day_label(local_start, local_reference)
    date_label = (
        f"{relative_label} ({base_date_label})"
        if relative_label is not None
        else base_date_label
    )
    start_time_label = _format_clock_label(local_start)
    end_time_label = _format_clock_label(local_end)
    local_time_range = f"{start_time_label} to {end_time_label} {timezone_abbr}".strip()
    role_text = str(role_name or "shift").strip() or "shift"
    location_text = str(location_name or "").strip()
    summary = f"{date_label} from {local_time_range} as {role_text}"
    if location_text:
        summary += f" at {location_text}"
    return {
        "date_label": date_label,
        "start_time_label": start_time_label,
        "end_time_label": end_time_label,
        "local_time_range": local_time_range,
        "timezone": timezone_name,
        "timezone_abbr": timezone_abbr,
        "relative_day_label": relative_label or "",
        "summary": summary,
    }


def _format_assigned_shift_schedule_summary(assigned_shifts: list[dict[str, Any]]) -> str:
    if not assigned_shifts:
        return ""
    return "\n".join(
        f"{index}. {str(shift.get('summary') or '').strip()}"
        for index, shift in enumerate(assigned_shifts, start=1)
        if str(shift.get("summary") or "").strip()
    )


def _format_inbound_shift_phrase(shift: dict[str, Any]) -> str:
    role_name = str(shift.get("role_name") or "shift").strip()
    location_name = str(shift.get("location_name") or "").strip()
    date_label = str(shift.get("date_label") or "").strip()
    local_time_range = str(shift.get("local_time_range") or "").strip()
    if date_label and local_time_range:
        phrase = f"your upcoming {role_name} shift on {date_label} from {local_time_range}"
    else:
        starts_at_raw = str(shift.get("starts_at") or "").strip()
        try:
            starts_at = datetime.fromisoformat(starts_at_raw.replace("Z", "+00:00"))
        except ValueError:
            starts_at = None
        time_text = None
        if starts_at is not None:
            time_text = starts_at.astimezone(timezone.utc).strftime("%a %b %-d at %-I:%M %p UTC")
        parts = [f"your upcoming {role_name} shift"]
        if time_text:
            parts.append(time_text)
        phrase = " ".join(parts)
    if location_name:
        phrase += f" at {location_name}"
    return phrase


def _build_begin_message(
    *,
    employee_found: bool,
    caller_first_name: str | None,
    assigned_shifts: list[dict[str, Any]],
) -> str:
    disclosure = (
        "This is Backfill's AI assistant. We may use this number to call or text you about shift coverage, "
        "and you can opt out anytime by saying so or replying STOP."
    )
    if employee_found and caller_first_name and len(assigned_shifts) == 1:
        shift_phrase = _format_inbound_shift_phrase(assigned_shifts[0])
        return f"Hi {caller_first_name}, {disclosure} Are you calling about {shift_phrase}?"
    if employee_found and caller_first_name and len(assigned_shifts) > 1:
        next_shift_phrase = _format_inbound_shift_phrase(assigned_shifts[0])
        return (
            f"Hi {caller_first_name}, {disclosure} I have {len(assigned_shifts)} upcoming published shifts "
            f"on your schedule, starting with {next_shift_phrase}. Are you calling about one of those shifts?"
        )
    return f"Hi, {disclosure} Are you calling about an upcoming shift?"


def _conversation_type_from_event(event: str) -> RetellConversationType:
    return RetellConversationType.chat if event.startswith("chat_") else RetellConversationType.call


def _conversation_payload(body: dict, conversation_type: RetellConversationType) -> dict[str, Any]:
    kind = conversation_type.value
    candidates = (
        body.get(kind),
        body.get(f"{kind}_detail"),
        body.get("conversation"),
        body.get("data"),
        body,
    )
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return {}


def _pick_value(*mappings: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        for key in keys:
            value = mapping.get(key)
            if value not in (None, ""):
                return value
    return None


def _normalize_timestamp(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        if value > 1_000_000_000_000:
            value = value / 1000.0
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _extract_transcript_items(body: dict, payload: dict) -> list[dict[str, Any]]:
    candidate = _pick_value(
        payload,
        body,
        keys=(
            "transcript_with_tool_calls",
            "transcript_items",
            "transcript_object",
            "messages",
            "message_history",
            "utterances",
            "conversation",
        ),
    )
    if isinstance(candidate, list):
        return [item for item in candidate if isinstance(item, dict)]
    if isinstance(candidate, dict):
        return [candidate]
    return []


def _transcript_text_from_items(items: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in items:
        speaker = item.get("speaker") or item.get("role") or item.get("sender")
        text = item.get("text") or item.get("message") or item.get("content")
        if not text:
            continue
        lines.append(f"{speaker}: {text}" if speaker else str(text))
    return "\n".join(lines)


def _extract_summary(body: dict, payload: dict, analysis: dict[str, Any], conversation_type: str) -> str | None:
    summary = _pick_value(
        analysis,
        payload,
        body,
        keys=(f"{conversation_type}_summary", "summary", "conversation_summary", "call_summary", "chat_summary"),
    )
    return summary.strip() if isinstance(summary, str) and summary.strip() else None


def _uuid_from_mapping(*mappings: dict[str, Any], keys: tuple[str, ...]) -> UUID | None:
    value = _pick_value(*mappings, keys=keys)
    if value in (None, ""):
        return None
    try:
        return UUID(str(value).strip())
    except (ValueError, TypeError):
        return None


async def persist_payload(session: AsyncSession, body: dict) -> RetellConversation | None:
    event = str(body.get("event") or "").strip()
    if not event:
        return None
    conversation_type = _conversation_type_from_event(event)
    payload = _conversation_payload(body, conversation_type)
    external_id = _pick_value(payload, body, keys=(f"{conversation_type.value}_id", "id"))
    if not isinstance(external_id, str) or not external_id.strip():
        return None

    metadata_value = _pick_value(payload, body, keys=("metadata",))
    metadata = metadata_value if isinstance(metadata_value, dict) else {}
    transcript_items = _extract_transcript_items(body, payload)
    transcript_text = _pick_value(payload, body, keys=("transcript_text", "transcript"))
    if not (isinstance(transcript_text, str) and transcript_text.strip()):
        transcript_text = _transcript_text_from_items(transcript_items) or None
    analysis_value = _pick_value(payload, body, keys=(f"{conversation_type.value}_analysis", "analysis"))
    analysis = analysis_value if isinstance(analysis_value, dict) else {}
    summary = _extract_summary(body, payload, analysis, conversation_type.value)

    conversation = await session.scalar(
        select(RetellConversation).where(RetellConversation.external_id == external_id.strip())
    )
    if conversation is None:
        conversation = RetellConversation(
            external_id=external_id.strip(),
            conversation_type=conversation_type,
            transcript_items=[],
            analysis={},
            metadata_json={},
            raw_payload={},
        )
        session.add(conversation)
        await session.flush()

    conversation.business_id = _uuid_from_mapping(metadata, body, keys=("business_id",))
    conversation.location_id = _uuid_from_mapping(metadata, body, keys=("location_id",))
    conversation.coverage_case_id = _uuid_from_mapping(metadata, body, keys=("coverage_case_id",))
    conversation.coverage_offer_id = _uuid_from_mapping(metadata, body, keys=("offer_id", "coverage_offer_id"))
    conversation.shift_id = _uuid_from_mapping(metadata, body, keys=("shift_id",))
    conversation.employee_id = _uuid_from_mapping(metadata, body, keys=("employee_id", "worker_id"))
    conversation.event_type = event
    conversation.direction = _pick_value(payload, body, keys=("direction",))
    conversation.status = _pick_value(payload, body, keys=("status", f"{conversation_type.value}_status", "call_status", "chat_status"))
    conversation.agent_id = _pick_value(payload, body, keys=("agent_id", "override_agent_id"))
    conversation.phone_from = _pick_value(payload, body, keys=("from_number", "from"))
    conversation.phone_to = _pick_value(payload, body, keys=("to_number", "to"))
    conversation.disconnection_reason = _pick_value(payload, body, keys=("disconnection_reason", "disconnect_reason"))
    if summary:
        conversation.conversation_summary = summary
    if transcript_text:
        conversation.transcript_text = transcript_text
    conversation.transcript_items = transcript_items or list(conversation.transcript_items or [])
    existing_analysis = conversation.analysis if isinstance(conversation.analysis, dict) else {}
    conversation.analysis = {
        **existing_analysis,
        **analysis,
    }
    existing_metadata = conversation.metadata_json if isinstance(conversation.metadata_json, dict) else {}
    conversation.metadata_json = {
        **existing_metadata,
        **metadata,
    }
    conversation.raw_payload = body
    conversation.started_at = _normalize_timestamp(_pick_value(payload, body, keys=("started_at", "start_timestamp", "start_time"))) or conversation.started_at
    conversation.ended_at = _normalize_timestamp(_pick_value(payload, body, keys=("ended_at", "end_timestamp", "end_time"))) or conversation.ended_at
    await session.flush()
    return conversation


def _processing_state(conversation: RetellConversation) -> dict[str, Any]:
    analysis = conversation.analysis if isinstance(conversation.analysis, dict) else {}
    state = analysis.get("backfill_processing")
    return state if isinstance(state, dict) else {}


def _set_processing_state(conversation: RetellConversation, state: dict[str, Any]) -> None:
    analysis = conversation.analysis if isinstance(conversation.analysis, dict) else {}
    conversation.analysis = {
        **analysis,
        "backfill_processing": state,
    }


def _conversation_assigned_shifts(conversation: RetellConversation) -> list[dict[str, Any]]:
    metadata = conversation.metadata_json if isinstance(conversation.metadata_json, dict) else {}
    assigned_shifts = metadata.get("assigned_shifts")
    if not isinstance(assigned_shifts, list):
        return []
    return [shift for shift in assigned_shifts if isinstance(shift, dict)]


def _conversation_user_utterances(conversation: RetellConversation) -> list[str]:
    utterances: list[str] = []
    for item in conversation.transcript_items or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or item.get("speaker") or item.get("sender") or "").strip().lower()
        if role not in {"user", "caller", "human"}:
            continue
        content = str(item.get("content") or item.get("text") or item.get("message") or "").strip()
        if content:
            utterances.append(content)
    return utterances


def _combined_user_text(conversation: RetellConversation) -> str:
    chunks = _conversation_user_utterances(conversation)
    summary = str(conversation.conversation_summary or "").strip()
    if summary:
        chunks.append(summary)
    return "\n".join(chunks).strip()


def _matches_any_pattern(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    lowered = text.lower()
    return any(pattern.search(lowered) for pattern in patterns)


def _metadata_shift_id(conversation: RetellConversation) -> str | None:
    metadata = conversation.metadata_json if isinstance(conversation.metadata_json, dict) else {}
    for key in ("selected_shift_id", "shift_id", "next_assigned_shift_id"):
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return None


def _shift_local_start_hour(shift: dict[str, Any]) -> int | None:
    starts_at_raw = str(shift.get("starts_at") or "").strip()
    timezone_name = str(shift.get("timezone") or "UTC").strip() or "UTC"
    if not starts_at_raw:
        return None
    try:
        starts_at = datetime.fromisoformat(starts_at_raw.replace("Z", "+00:00"))
        return _to_local_shift_time(starts_at, timezone_name).hour
    except ValueError:
        return None


def _shift_reference_score(shift: dict[str, Any], text: str) -> int:
    lowered = text.lower()
    score = 0
    relative_day = str(shift.get("relative_day_label") or "").strip().lower()
    if relative_day == "today" and _matches_any_pattern(lowered, _TODAY_PATTERNS):
        score += 20
    if relative_day == "tomorrow" and _matches_any_pattern(lowered, _TOMORROW_PATTERNS):
        score += 20

    date_label = str(shift.get("date_label") or "").lower()
    for weekday_name in _WEEKDAY_NAMES:
        if weekday_name in date_label and weekday_name in lowered:
            score += 12

    role_name = str(shift.get("role_name") or "").strip().lower()
    if role_name and role_name in lowered:
        score += 6

    location_name = str(shift.get("location_name") or "").strip().lower()
    if location_name and location_name in lowered:
        score += 6

    start_time_label = str(shift.get("start_time_label") or "").strip().lower()
    if start_time_label:
        variants = {
            start_time_label,
            start_time_label.replace(":00", ""),
            start_time_label.replace(" ", ""),
            start_time_label.replace(":00", "").replace(" ", ""),
        }
        if any(variant and variant in lowered for variant in variants):
            score += 5

    local_hour = _shift_local_start_hour(shift)
    if local_hour is not None:
        if 5 <= local_hour < 12 and "morning" in lowered:
            score += 5
        if 12 <= local_hour < 17 and "afternoon" in lowered:
            score += 5
        if local_hour >= 17 and ("evening" in lowered or "tonight" in lowered):
            score += 5
    return score


def _resolve_callout_shift(
    conversation: RetellConversation,
    user_text: str,
) -> tuple[dict[str, Any] | None, str]:
    assigned_shifts = _conversation_assigned_shifts(conversation)
    if not assigned_shifts:
        return None, "no_assigned_shifts"

    selected_shift_id = _metadata_shift_id(conversation)
    if selected_shift_id:
        for shift in assigned_shifts:
            if str(shift.get("id") or "").strip() == selected_shift_id:
                return shift, "metadata_shift_id"

    if len(assigned_shifts) == 1:
        return assigned_shifts[0], "single_assigned_shift"

    scored_shifts = [
        (shift, _shift_reference_score(shift, user_text))
        for shift in assigned_shifts
    ]
    scored_shifts.sort(key=lambda item: item[1], reverse=True)
    if scored_shifts and scored_shifts[0][1] > 0:
        top_shift, top_score = scored_shifts[0]
        second_score = scored_shifts[1][1] if len(scored_shifts) > 1 else -1
        if top_score > second_score:
            return top_shift, "transcript_shift_match"

    return None, "ambiguous_shift_reference"


def _trimmed_conversation_summary(conversation: RetellConversation) -> str | None:
    summary = str(conversation.conversation_summary or "").strip()
    if summary:
        return summary[:500]
    user_text = _combined_user_text(conversation)
    return user_text[:500] or None


async def process_inbound_conversation_completion(
    session: AsyncSession,
    conversation: RetellConversation | None,
) -> dict[str, Any]:
    if conversation is None:
        return {"status": "no_conversation"}
    if conversation.conversation_type != RetellConversationType.call:
        return {"status": "ignored", "reason": "not_call"}
    if str(conversation.direction or "").strip().lower() != "inbound":
        return {"status": "ignored", "reason": "not_inbound"}

    processing_state = _processing_state(conversation)
    user_text = _combined_user_text(conversation)
    metadata = conversation.metadata_json if isinstance(conversation.metadata_json, dict) else {}
    employee_id = str(metadata.get("employee_id") or conversation.employee_id or "").strip() or None
    caller_phone = (
        str(metadata.get("caller_phone") or conversation.phone_from or "").strip() or None
    )

    consent_state = processing_state.get("consent") if isinstance(processing_state.get("consent"), dict) else {}
    if consent_state.get("status") in {"consent_revoked", "consent_granted"}:
        consent_result = dict(consent_state)
    elif caller_phone and _matches_any_pattern(user_text, _SMS_OPT_OUT_PATTERNS):
        consent_result = await log_consent(
            session,
            {
                "employee_id": employee_id,
                "phone": caller_phone,
                "granted": False,
                "channel": "inbound_call",
            },
        )
    else:
        consent_result = {"status": "no_consent_change"}

    callout_state = processing_state.get("callout") if isinstance(processing_state.get("callout"), dict) else {}
    if callout_state.get("status") == "vacancy_created":
        callout_result = dict(callout_state)
    elif not _matches_any_pattern(user_text, _CALL_OUT_PATTERNS):
        callout_result = {"status": "no_callout_detected"}
    elif employee_id is None:
        callout_result = {"status": "employee_context_missing"}
    else:
        selected_shift, resolution = _resolve_callout_shift(conversation, user_text)
        if selected_shift is None:
            callout_result = {
                "status": "shift_reference_unresolved",
                "resolution": resolution,
            }
        else:
            try:
                vacancy = await create_vacancy(
                    session,
                    {
                        "shift_id": str(selected_shift.get("id") or "").strip(),
                        "employee_id": employee_id,
                        "conversation_summary": _trimmed_conversation_summary(conversation),
                        "source": "retell_post_call",
                    },
                )
                callout_result = {
                    **vacancy,
                    "resolution": resolution,
                }
            except (LookupError, ValueError) as exc:
                callout_result = {
                    "status": str(exc),
                    "shift_id": str(selected_shift.get("id") or "").strip() or None,
                    "resolution": resolution,
                }

    updated_state = {
        **processing_state,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "consent": consent_result,
        "callout": callout_result,
    }
    _set_processing_state(conversation, updated_state)
    await session.flush()
    return {
        "status": "processed",
        "consent": consent_result,
        "callout": callout_result,
    }


async def _resolve_offer_context(
    session: AsyncSession,
    *,
    args: dict,
) -> tuple[CoverageOffer, UUID]:
    offer_id = _uuid_from_mapping(args, keys=("offer_id", "coverage_offer_id"))
    if offer_id is not None:
        offer = await session.get(CoverageOffer, offer_id)
        if offer is None:
            raise LookupError("offer_not_found")
        coverage_case = await session.get(CoverageCase, offer.coverage_case_id)
        shift = await session.get(Shift, coverage_case.shift_id) if coverage_case is not None else None
        if coverage_case is None or shift is None:
            raise LookupError("shift_not_found")
        return offer, shift.business_id

    coverage_case_id = _uuid_from_mapping(args, keys=("coverage_case_id",))
    employee_id = _uuid_from_mapping(args, keys=("employee_id", "worker_id"))
    shift_id = _uuid_from_mapping(args, keys=("shift_id",))
    phone = str(args.get("phone") or "").strip()

    if phone:
        context = await delivery.find_latest_actionable_offer_for_phone(session, phone)
        if context is not None:
            return context.offer, context.business_id

    if coverage_case_id is not None and employee_id is not None:
        offer = await session.scalar(
            select(CoverageOffer).where(
                CoverageOffer.coverage_case_id == coverage_case_id,
                CoverageOffer.employee_id == employee_id,
                CoverageOffer.status.in_([OfferStatus.pending, OfferStatus.delivered]),
            )
        )
        if offer is not None:
            coverage_case = await session.get(CoverageCase, coverage_case_id)
            shift = await session.get(Shift, coverage_case.shift_id) if coverage_case is not None else None
            if coverage_case is not None and shift is not None:
                return offer, shift.business_id

    if shift_id is not None and employee_id is not None:
        result = await session.execute(
            select(CoverageOffer, Shift.business_id)
            .join(CoverageCase, CoverageOffer.coverage_case_id == CoverageCase.id)
            .join(Shift, CoverageCase.shift_id == Shift.id)
            .where(
                CoverageCase.shift_id == shift_id,
                CoverageOffer.employee_id == employee_id,
                CoverageOffer.status.in_([OfferStatus.pending, OfferStatus.delivered]),
            )
            .order_by(CoverageOffer.created_at.desc())
            .limit(1)
        )
        row = result.first()
        if row is not None:
            return row[0], row[1]

    raise LookupError("offer_not_found")


async def _respond_to_offer(
    session: AsyncSession,
    *,
    args: dict,
    accepted: bool,
) -> dict:
    offer, business_id = await _resolve_offer_context(session, args=args)
    action = "accepted" if accepted else "declined"
    payload = CoverageOfferResponseCreate(
        response=action,
        response_channel="voice",
        response_text=str(args.get("conversation_summary") or ""),
        response_payload={
            "eta_minutes": args.get("eta_minutes"),
            "retell": args,
        },
    )
    result = await coverage_service.respond_to_offer(session, business_id, offer.id, payload)
    return {
        "status": result.offer.status,
        "offer_id": str(result.offer.id),
        "shift_id": str(result.shift_id),
        "assignment_id": str(result.assignment_id) if result.assignment_id else None,
    }


async def lookup_caller(session: AsyncSession, phone: str) -> dict:
    normalized = phone.strip()
    reference_now = _current_utc_now()
    user = await session.scalar(select(User).where(User.primary_phone_e164 == normalized))
    employee = await session.scalar(
        select(Employee)
        .options(selectinload(Employee.employee_locations))
        .where(Employee.phone_e164 == normalized)
    )
    context = await delivery.find_latest_actionable_offer_for_phone(session, normalized)
    assigned_shifts: list[dict[str, Any]] = []
    if employee is not None:
        result = await session.execute(
            select(Shift)
            .options(
                selectinload(Shift.location),
                selectinload(Shift.role),
                selectinload(Shift.assignments),
            )
            .join(ShiftAssignment, ShiftAssignment.shift_id == Shift.id)
            .where(
                ShiftAssignment.employee_id == employee.id,
                ShiftAssignment.status.in_([AssignmentStatus.assigned, AssignmentStatus.accepted]),
                Shift.lifecycle_status.in_(
                    [ShiftLifecycleStatus.scheduled, ShiftLifecycleStatus.in_progress]
                ),
                Shift.ends_at >= reference_now - timedelta(hours=4),
            )
            .order_by(Shift.starts_at.asc())
        )
        seen_shift_ids: set[UUID] = set()
        for shift in result.scalars().all():
            if shift.id in seen_shift_ids:
                continue
            seen_shift_ids.add(shift.id)
            location_name = (
                getattr(shift.location, "location_display_name", None)
                or getattr(shift.location, "display_name", None)
                or getattr(shift.location, "name", None)
            )
            timezone_name = _shift_display_timezone(shift)
            shift_summary = _format_shift_summary(
                role_name=getattr(shift.role, "name", None),
                location_name=location_name,
                starts_at=shift.starts_at,
                ends_at=shift.ends_at,
                timezone_name=timezone_name,
                reference_time=reference_now,
            )
            assigned_shifts.append(
                {
                    "id": str(shift.id),
                    "location_id": str(shift.location_id),
                    "location_name": location_name,
                    "role_id": str(shift.role_id),
                    "role_name": getattr(shift.role, "name", None),
                    "starts_at": shift.starts_at.isoformat(),
                    "ends_at": shift.ends_at.isoformat(),
                    "status": shift.status,
                    "lifecycle_status": shift.lifecycle_status,
                    "staffing_status": shift.staffing_status,
                    "notes": shift.notes,
                    **shift_summary,
                }
            )
    assigned_shift_schedule_summary = _format_assigned_shift_schedule_summary(assigned_shifts)
    return {
        "phone": normalized,
        "user": {
            "id": str(user.id),
            "full_name": user.full_name,
            "email": user.email,
        } if user is not None else None,
        "employee": {
            "id": str(employee.id),
            "full_name": employee.full_name,
            "business_id": str(employee.business_id),
            "location_id": str(employee.primary_location_id) if employee.primary_location_id else None,
        } if employee is not None else None,
        "assigned_shifts": assigned_shifts,
        "assigned_shift_count": len(assigned_shifts),
        "assigned_shift_schedule_summary": assigned_shift_schedule_summary,
        "next_assigned_shift_id": assigned_shifts[0]["id"] if assigned_shifts else None,
        "actionable_offer_id": str(context.offer.id) if context is not None else None,
    }


async def build_inbound_webhook_response(session: AsyncSession, body: dict) -> dict[str, Any]:
    event = str(body.get("event") or "").strip().lower()
    inbound_key = "chat_inbound" if event == "chat_inbound" else "call_inbound"
    inbound_payload = body.get(inbound_key) if isinstance(body.get(inbound_key), dict) else {}
    phone = str(
        inbound_payload.get("from_number")
        or body.get("from_number")
        or ""
    ).strip()
    lookup = await lookup_caller(session, phone) if phone else {
        "phone": phone,
        "user": None,
        "employee": None,
        "assigned_shifts": [],
        "actionable_offer_id": None,
    }
    employee = lookup.get("employee") if isinstance(lookup.get("employee"), dict) else None
    user = lookup.get("user") if isinstance(lookup.get("user"), dict) else None
    assigned_shifts = list(lookup.get("assigned_shifts") or [])
    assigned_shift_schedule_summary = str(lookup.get("assigned_shift_schedule_summary") or "").strip()
    employee_found = employee is not None
    caller_name = (
        str((employee or {}).get("full_name") or "").strip()
        or str((user or {}).get("full_name") or "").strip()
        or None
    )
    caller_first_name = _first_name(caller_name)
    selected_shift = assigned_shifts[0] if len(assigned_shifts) == 1 else None
    next_shift = assigned_shifts[0] if assigned_shifts else None

    metadata: dict[str, Any] = {
        "caller_phone": phone,
        "employee_found": employee_found,
        "upcoming_shift_count": len(assigned_shifts),
        "assigned_shifts": assigned_shifts,
        "assigned_shift_schedule_summary": assigned_shift_schedule_summary,
    }
    if employee is not None:
        metadata["employee_id"] = employee.get("id")
        metadata["business_id"] = employee.get("business_id")
        if employee.get("location_id"):
            metadata["location_id"] = employee.get("location_id")
    if next_shift is not None:
        metadata["next_shift_summary"] = next_shift.get("summary")
    if selected_shift is not None:
        metadata["shift_id"] = selected_shift.get("id")
        if selected_shift.get("location_id"):
            metadata["location_id"] = selected_shift.get("location_id")

    dynamic_variables = {
        "caller_phone": _coerce_retell_dynamic_value(phone),
        "employee_found": _coerce_retell_dynamic_value(employee_found),
        "caller_name": _coerce_retell_dynamic_value(caller_name),
        "caller_first_name": _coerce_retell_dynamic_value(caller_first_name),
        "upcoming_shift_count": _coerce_retell_dynamic_value(len(assigned_shifts)),
        "assigned_shift_schedule_summary": _coerce_retell_dynamic_value(assigned_shift_schedule_summary),
        "next_shift_role": _coerce_retell_dynamic_value(
            next_shift.get("role_name") if next_shift is not None else None
        ),
        "next_shift_location": _coerce_retell_dynamic_value(
            next_shift.get("location_name") if next_shift is not None else None
        ),
        "next_shift_starts_at": _coerce_retell_dynamic_value(
            next_shift.get("starts_at") if next_shift is not None else None
        ),
        "next_shift_summary": _coerce_retell_dynamic_value(
            next_shift.get("summary") if next_shift is not None else None
        ),
        "selected_shift_id": _coerce_retell_dynamic_value(
            selected_shift.get("id") if selected_shift is not None else None
        ),
        "selected_shift_summary": _coerce_retell_dynamic_value(
            selected_shift.get("summary") if selected_shift is not None else None
        ),
    }
    response_payload: dict[str, Any] = {
        "dynamic_variables": dynamic_variables,
        "metadata": metadata,
    }
    if event == "call_inbound":
        response_payload["override_agent_id"] = (
            str(inbound_payload.get("agent_id") or "").strip()
            or settings.retell_agent_id_inbound
            or settings.retell_agent_id
        )
        response_payload["agent_override"] = {
            "retell_llm": {
                "begin_message": _build_begin_message(
                    employee_found=employee_found,
                    caller_first_name=caller_first_name,
                    assigned_shifts=assigned_shifts,
                )
            }
        }
    if event == "chat_inbound":
        response_payload["override_agent_id"] = (
            settings.retell_chat_agent_id_inbound
            or settings.retell_chat_agent_id
        )
    return {inbound_key: response_payload}


async def get_open_shifts(session: AsyncSession, location_id: UUID | None = None) -> dict:
    stmt = select(Shift).where(
        Shift.lifecycle_status.in_([ShiftLifecycleStatus.scheduled, ShiftLifecycleStatus.in_progress]),
        Shift.staffing_status.in_([ShiftStaffingStatus.open, ShiftStaffingStatus.filling]),
    )
    if location_id is not None:
        stmt = stmt.where(Shift.location_id == location_id)
    result = await session.execute(stmt.order_by(Shift.starts_at.asc()).limit(10))
    shifts = list(result.scalars().all())
    return {
        "shifts": [
            {
                "id": str(shift.id),
                "location_id": str(shift.location_id),
                "role_id": str(shift.role_id),
                "starts_at": shift.starts_at.isoformat(),
                "ends_at": shift.ends_at.isoformat(),
                "status": shift.status,
                "lifecycle_status": shift.lifecycle_status,
                "staffing_status": shift.staffing_status,
            }
            for shift in shifts
        ]
    }


async def get_shift_status(session: AsyncSession, shift_id: UUID) -> dict:
    shift = await session.get(Shift, shift_id)
    if shift is None:
        raise LookupError("shift_not_found")
    active_case = await session.scalar(
        select(CoverageCase).where(
            CoverageCase.shift_id == shift.id,
            CoverageCase.status.in_([CoverageCaseStatus.queued, CoverageCaseStatus.running, CoverageCaseStatus.filled]),
        )
    )
    return {
        "shift_id": str(shift.id),
        "status": shift.status,
        "lifecycle_status": shift.lifecycle_status,
        "staffing_status": shift.staffing_status,
        "seats_requested": shift.seats_requested,
        "seats_filled": shift.seats_filled,
        "coverage_case_id": str(active_case.id) if active_case is not None else None,
        "coverage_status": active_case.status if active_case is not None else None,
    }


def _parse_shift_datetimes(args: dict, timezone_name: str) -> tuple[datetime, datetime]:
    starts_at = args.get("starts_at")
    ends_at = args.get("ends_at")
    if starts_at and ends_at:
        parsed_start = datetime.fromisoformat(str(starts_at).replace("Z", "+00:00"))
        parsed_end = datetime.fromisoformat(str(ends_at).replace("Z", "+00:00"))
        if parsed_start.tzinfo is None:
            parsed_start = parsed_start.replace(tzinfo=ZoneInfo(timezone_name))
        if parsed_end.tzinfo is None:
            parsed_end = parsed_end.replace(tzinfo=ZoneInfo(timezone_name))
        return parsed_start.astimezone(timezone.utc), parsed_end.astimezone(timezone.utc)

    date_text = str(args.get("date") or "").strip()
    start_time = str(args.get("start_time") or "").strip()
    end_time = str(args.get("end_time") or "").strip()
    if not (date_text and start_time and end_time):
        raise ValueError("shift_time_fields_required")
    local_zone = ZoneInfo(timezone_name)
    parsed_start = datetime.fromisoformat(f"{date_text}T{start_time}").replace(tzinfo=local_zone)
    parsed_end = datetime.fromisoformat(f"{date_text}T{end_time}").replace(tzinfo=local_zone)
    return parsed_start.astimezone(timezone.utc), parsed_end.astimezone(timezone.utc)


async def create_open_shift(session: AsyncSession, args: dict) -> dict:
    location_id = _uuid_from_mapping(args, keys=("location_id",))
    if location_id is None:
        raise ValueError("location_id_required")
    location = await session.get(Location, location_id)
    if location is None:
        raise LookupError("location_not_found")
    role_name = str(args.get("role") or "").strip()
    if not role_name:
        raise ValueError("role_required")
    role = await businesses.ensure_business_role(
        session,
        business_id=location.business_id,
        role_name=role_name,
        source="retell_voice",
        source_metadata={"role_name": role_name},
    )
    starts_at, ends_at = _parse_shift_datetimes(args, location.timezone)
    shift = await scheduling.create_shift(
        session,
        location.business_id,
        ShiftCreate(
            location_id=location.id,
            role_id=role.id,
            source_system="backfill_native",
            timezone=location.timezone,
            starts_at=starts_at,
            ends_at=ends_at,
            seats_requested=max(1, int(args.get("seats_requested") or 1)),
            requires_manager_approval=bool(args.get("requires_manager_approval") or False),
            premium_cents=max(0, int(float(args.get("pay_rate") or 0) * 100)) if args.get("pay_rate") else 0,
            notes=str(args.get("notes") or "").strip() or None,
            shift_metadata={"source": "retell_voice", "requirements": args.get("requirements") or []},
        ),
    )
    shift.status = ShiftStatus.open
    await session.flush()
    return {"status": "shift_created", "shift_id": str(shift.id)}


async def log_consent(session: AsyncSession, args: dict) -> dict:
    employee_id = _uuid_from_mapping(args, keys=("employee_id", "worker_id"))
    granted = bool(args.get("granted"))
    channel = str(args.get("channel") or "inbound_call").strip().lower() or "inbound_call"
    employee = await session.get(Employee, employee_id) if employee_id is not None else None
    phone = communication_suppressions.normalize_destination(
        communication_suppressions.SMS_CHANNEL,
        str(args.get("phone") or getattr(employee, "phone_e164", "") or "").strip() or None,
    )
    if phone is None:
        raise ValueError("phone_or_employee_required")

    metadata = {
        "channel": channel,
        "retell": {key: value for key, value in args.items() if key != "conversation_summary"},
    }
    changed = False
    if granted:
        _suppression, changed = await communication_suppressions.clear_destination_suppression(
            session,
            channel=communication_suppressions.SMS_CHANNEL,
            destination=phone,
            source="retell_voice_consent",
            reason_code="voice_consent_granted",
            metadata=metadata,
        )
    else:
        _suppression, changed = await communication_suppressions.suppress_destination(
            session,
            channel=communication_suppressions.SMS_CHANNEL,
            destination=phone,
            source="retell_voice_consent",
            reason_code="voice_consent_revoked",
            metadata=metadata,
        )

    if employee is not None:
        preferences = workforce.normalized_employee_notification_preferences(employee.employee_metadata)
        preferences["schedule_publish_sms_enabled"] = granted
        preferences["sms_opted_out_at"] = None if granted else datetime.now(timezone.utc)
        preferences["sms_opt_out_reason"] = None if granted else "voice_consent_revoked"
        employee.employee_metadata = {
            **(employee.employee_metadata or {}),
            "notification_preferences": workforce._serialized_employee_notification_preferences(preferences),
            "voice_consent": {
                "granted": granted,
                "channel": channel,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "source": "retell_voice",
            },
        }
        await session.flush()

    return {
        "status": "consent_granted" if granted else "consent_revoked",
        "employee_id": str(employee.id) if employee is not None else None,
        "phone": phone,
        "changed": changed,
    }


async def create_vacancy(session: AsyncSession, args: dict) -> dict:
    shift_id = _uuid_from_mapping(args, keys=("shift_id",))
    if shift_id is None:
        raise ValueError("shift_id_required")
    shift = await session.get(
        Shift,
        shift_id,
        options=[selectinload(Shift.assignments)],
    )
    if shift is None:
        raise LookupError("shift_not_found")
    if shift.lifecycle_status in {ShiftLifecycleStatus.cancelled, ShiftLifecycleStatus.completed}:
        raise ValueError("shift_not_open_for_callout")

    employee_id = _uuid_from_mapping(args, keys=("employee_id", "worker_id"))
    source = str(args.get("source") or "retell_voice").strip() or "retell_voice"
    current_assignment = shift_assignments.current_assignment(shift.assignments or [])
    effective_employee_id = employee_id or (
        current_assignment.employee_id if current_assignment is not None else None
    )
    if (
        current_assignment is not None
        and effective_employee_id is not None
        and current_assignment.employee_id != effective_employee_id
    ):
        raise ValueError("shift_not_assigned_to_employee")

    used_published_amendment = False
    if (
        current_assignment is not None
        and shift.lifecycle_status
        in {ShiftLifecycleStatus.scheduled, ShiftLifecycleStatus.in_progress}
    ):
        await scheduling.apply_published_shift_amendment(
            session,
            shift.business_id,
            shift.id,
            PublishedShiftAmendmentWrite(
                action="unassign_shift",
                reason_code="callout",
                source=source,
                note=str(args.get("conversation_summary") or args.get("note") or "").strip() or None,
            ),
        )
        used_published_amendment = True

    vacancy = await scheduler_sync.create_vacancy_for_shift(
        session,
        shift_id=shift.id,
        employee_id=effective_employee_id,
        triggered_by=source,
        reason_code="callout",
    )
    return {
        "status": "vacancy_created",
        "shift_id": str(vacancy["shift_id"]),
        "coverage_case_id": (
            str(vacancy["coverage_case_id"])
            if vacancy.get("coverage_case_id") is not None
            else None
        ),
        "offers": vacancy.get("offers", []),
        "used_published_amendment": used_published_amendment,
    }


async def send_onboarding_link(
    session: AsyncSession,
    phone: str,
    *,
    kind: str,
    location_id: UUID | None = None,
    platform: str | None = None,
) -> dict:
    path = "/try"
    if location_id is not None:
        path = f"/try?location_id={location_id}&kind={kind}"
    if await communication_suppressions.is_destination_suppressed(
        session,
        channel="sms",
        destination=phone,
    ):
        return {
            "status": "suppressed",
            "path": path,
            "platform": (platform or "").strip().lower() or None,
        }
    body = "Backfill: Finish setting up your account here: " + f"{settings.web_base_url}{path}"
    messaging.send_sms(to=phone, body=body)
    return {
        "status": "sent",
        "path": path,
        "platform": (platform or "").strip().lower() or None,
    }


async def dispatch_function_call(session: AsyncSession, name: str, args: dict) -> dict:
    if name == "lookup_caller":
        phone = str(args.get("phone") or "").strip()
        if not phone:
            raise ValueError("phone_required")
        return await lookup_caller(session, phone)
    if name == "log_consent":
        return await log_consent(session, args)
    if name == "get_open_shifts":
        return await get_open_shifts(session, location_id=_uuid_from_mapping(args, keys=("location_id",)))
    if name == "get_shift_status":
        shift_id = _uuid_from_mapping(args, keys=("shift_id",))
        if shift_id is None:
            raise ValueError("shift_id_required")
        return await get_shift_status(session, shift_id)
    if name == "create_open_shift":
        return await create_open_shift(session, args)
    if name == "create_vacancy":
        return await create_vacancy(session, args)
    if name in {"claim_shift", "promote_standby"}:
        return await _respond_to_offer(session, args=args, accepted=True)
    if name in {"decline_shift", "cancel_standby"}:
        return await _respond_to_offer(session, args=args, accepted=False)
    if name == "confirm_fill":
        return await _respond_to_offer(session, args=args, accepted=bool(args.get("accepted")))
    if name == "send_onboarding_link":
        phone = str(args.get("phone") or "").strip()
        if not phone:
            raise ValueError("phone_required")
        location_id = _uuid_from_mapping(args, keys=("location_id",))
        return await send_onboarding_link(
            session,
            phone,
            kind=str(args.get("kind") or "invite"),
            location_id=location_id,
            platform=str(args.get("platform") or "").strip() or None,
        )
    raise ValueError(f"unsupported_retell_function:{name}")
