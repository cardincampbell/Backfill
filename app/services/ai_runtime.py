from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import json
import re
from time import perf_counter
from typing import Any

import httpx

from app.config import settings


class AiRuntimeError(RuntimeError):
    pass


class AiStructuredOutputError(AiRuntimeError):
    pass


@dataclass
class AiStructuredRequest:
    task_name: str
    system_prompt: str
    user_prompt: str
    json_schema: dict[str, Any]
    schema_name: str | None = None
    schema_description: str | None = None
    temperature: float = 0.0
    max_output_tokens: int = 500
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AiStructuredResponse:
    requested_provider: str
    provider: str
    model: str
    parsed_output: dict[str, Any]
    raw_text: str
    usage: dict[str, Any]
    latency_ms: int
    request_id: str
    fallback_used: bool = False
    fallback_provider: str | None = None
    fallback_reason: str | None = None
    primary_error: str | None = None


async def run_structured(
    request: AiStructuredRequest,
    *,
    provider_override: str | None = None,
) -> AiStructuredResponse:
    provider = (provider_override or settings.backfill_ai_provider or "rules").strip().lower() or "rules"
    if provider == "rules":
        return _run_rules_response(
            request,
            requested_provider="rules",
        )
    if provider == "openai":
        try:
            return await _run_openai_provider(request)
        except (AiRuntimeError, AiStructuredOutputError, httpx.HTTPError) as exc:
            if not settings.backfill_ai_fallback_enabled:
                raise
            fallback_provider = (
                settings.backfill_ai_fallback_provider or "rules"
            ).strip().lower() or "rules"
            if fallback_provider != "rules":
                raise AiRuntimeError(
                    f"Unsupported fallback AI provider {fallback_provider!r}; expected 'rules'"
                ) from exc
            return _run_rules_response(
                request,
                requested_provider="openai",
                fallback_used=True,
                fallback_provider="rules",
                fallback_reason=exc.__class__.__name__,
                primary_error=str(exc),
            )
    raise AiRuntimeError(
        f"Unsupported AI provider {provider!r}; expected 'rules' or 'openai'"
    )


def _run_rules_provider(request: AiStructuredRequest) -> dict[str, Any]:
    if request.task_name == "intent_classification":
        return _classify_intent_rules(
            str(request.metadata.get("text") or request.user_prompt or ""),
            channel=str(request.metadata.get("channel") or "web"),
        )
    if request.task_name == "open_shift_creation_extraction":
        return _extract_open_shift_creation_rules(
            str(request.metadata.get("text") or request.user_prompt or ""),
            context=dict(request.metadata.get("context") or {}),
        )
    if request.task_name == "shift_edit_extraction":
        return _extract_shift_edit_rules(
            str(request.metadata.get("text") or request.user_prompt or ""),
            context=dict(request.metadata.get("context") or {}),
        )
    raise AiRuntimeError(f"Unsupported structured task {request.task_name!r}")


async def _run_openai_provider(request: AiStructuredRequest) -> AiStructuredResponse:
    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        raise AiRuntimeError("OPENAI_API_KEY is not configured for the OpenAI provider")

    payload = {
        "model": settings.backfill_ai_model or "gpt-4.1-mini",
        "input": [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_prompt},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": request.schema_name or request.task_name,
                "description": request.schema_description or request.task_name,
                "schema": request.json_schema,
                "strict": True,
            }
        },
        "max_output_tokens": request.max_output_tokens,
        "temperature": request.temperature,
    }

    started_at = perf_counter()
    async with httpx.AsyncClient(timeout=settings.backfill_ai_timeout_seconds) as client:
        response = await client.post(
            f"{settings.openai_base_url}/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    latency_ms = int((perf_counter() - started_at) * 1000)

    try:
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise AiRuntimeError(
            f"OpenAI structured request failed with status {getattr(response, 'status_code', 'unknown')}: {response.text}"
        ) from exc

    body = response.json()
    raw_text = _extract_openai_output_text(body)
    try:
        parsed_output = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AiStructuredOutputError(
            f"OpenAI structured output was not valid JSON for task {request.task_name!r}"
        ) from exc

    if not isinstance(parsed_output, dict):
        raise AiStructuredOutputError(
            f"OpenAI structured output must decode to an object for task {request.task_name!r}"
        )

    return AiStructuredResponse(
        requested_provider="openai",
        provider="openai",
        model=str(body.get("model") or settings.backfill_ai_model or "gpt-4.1-mini"),
        parsed_output=parsed_output,
        raw_text=raw_text,
        usage=dict(body.get("usage") or {}),
        latency_ms=latency_ms,
        request_id=str(body.get("id") or f"openai:{request.task_name}"),
    )


def _run_rules_response(
    request: AiStructuredRequest,
    *,
    requested_provider: str,
    fallback_used: bool = False,
    fallback_provider: str | None = None,
    fallback_reason: str | None = None,
    primary_error: str | None = None,
) -> AiStructuredResponse:
    started_at = perf_counter()
    parsed_output = _run_rules_provider(request)
    latency_ms = int((perf_counter() - started_at) * 1000)
    return AiStructuredResponse(
        requested_provider=requested_provider,
        provider="rules",
        model=(
            (settings.backfill_ai_model or "rules-v1")
            if requested_provider == "rules"
            else "rules-v1"
        ),
        parsed_output=parsed_output,
        raw_text=str(parsed_output),
        usage={"input_tokens": 0, "output_tokens": 0},
        latency_ms=latency_ms,
        request_id=f"rules:{request.task_name}",
        fallback_used=fallback_used,
        fallback_provider=fallback_provider,
        fallback_reason=fallback_reason,
        primary_error=primary_error,
    )


def _extract_openai_output_text(body: dict[str, Any]) -> str:
    output = list(body.get("output") or [])
    chunks: list[str] = []
    for item in output:
        item_type = str(item.get("type") or "")
        if item_type == "refusal":
            refusal_text = str(item.get("refusal") or item.get("content") or "").strip()
            raise AiStructuredOutputError(refusal_text or "Model refused the request")
        if item_type != "message":
            continue
        for content in list(item.get("content") or []):
            content_type = str(content.get("type") or "")
            if content_type == "refusal":
                refusal_text = str(content.get("refusal") or content.get("text") or "").strip()
                raise AiStructuredOutputError(refusal_text or "Model refused the request")
            if content_type in {"output_text", "text"}:
                text = str(content.get("text") or "").strip()
                if text:
                    chunks.append(text)
    if chunks:
        return "\n".join(chunks)

    fallback_text = str(body.get("output_text") or "").strip()
    if fallback_text:
        return fallback_text
    raise AiStructuredOutputError("OpenAI response did not contain structured text output")


def _classify_intent_rules(text: str, *, channel: str) -> dict[str, Any]:
    normalized = " ".join(text.lower().split())

    if (
        re.search(r"\b(?:create|add|schedule)\s+(?:an?\s+)?open\s+[a-z0-9 _/-]+?\s+shift\b", normalized)
        or re.search(r"\b(?:create|add|schedule)\s+(?:an?\s+)?[a-z0-9 _/-]+?\s+shift\b", normalized)
        or re.search(r"\bnew\s+[a-z0-9 _/-]+?\s+shift\b", normalized)
        or any(
            phrase in normalized
            for phrase in (
                "create an open shift",
                "create open shift",
                "add an open shift",
                "add open shift",
                "new open shift",
                "create a shift",
                "create shift",
                "add a shift",
                "add shift",
                "schedule a shift",
                "schedule an open shift",
            )
        )
    ):
        return {
            "intent_type": "command",
            "domain": "schedule",
            "action_candidates": ["create_open_shift"],
            "confidence_score": 0.92,
            "channel": channel,
        }
    if (
        re.search(r"\b(?:move|change|update|edit)\s+(?:the\s+)?(?:open\s+)?[a-z0-9 _/-]*shift\b", normalized)
        or re.search(r"\b(?:change|update|edit)\s+(?:the\s+)?(?:time|start time|end time|date|role|notes?|label|pay rate)\b", normalized)
    ):
        return {
            "intent_type": "command",
            "domain": "schedule",
            "action_candidates": ["edit_shift"],
            "confidence_score": 0.91,
            "channel": channel,
        }
    if (
        re.search(r"\bdelete\s+(?:the\s+)?(?:[a-z0-9 _/-]+\s+)?shift\b", normalized)
        or re.search(r"\bremove\s+(?:the\s+)?(?:[a-z0-9 _/-]+\s+)?shift\s+from\s+(?:the\s+)?schedule\b", normalized)
    ) and "open shift" not in normalized:
        return {
            "intent_type": "command",
            "domain": "schedule",
            "action_candidates": ["delete_shift"],
            "confidence_score": 0.92,
            "channel": channel,
        }
    if any(
        phrase in normalized
        for phrase in (
            "clear the assignment",
            "clear assignment",
            "unassign the shift",
            "unassign this shift",
            "remove them from the shift",
            "take them off the shift",
            "open up the shift",
            "make the shift open again",
        )
    ):
        return {
            "intent_type": "command",
            "domain": "schedule",
            "action_candidates": ["clear_shift_assignment"],
            "confidence_score": 0.93,
            "channel": channel,
        }
    if any(
        phrase in normalized
        for phrase in (
            "assign ",
            "reassign ",
            "put ",
            "schedule ",
        )
    ) and " shift" in normalized:
        return {
            "intent_type": "command",
            "domain": "schedule",
            "action_candidates": ["assign_shift"],
            "confidence_score": 0.91,
            "channel": channel,
        }
    if any(
        phrase in normalized
        for phrase in (
            "reopen and offer the shift",
            "reopen and offer the open shift",
            "reopen and send the shift",
            "reopen and start offering",
            "reopen and send it out",
        )
    ):
        return {
            "intent_type": "command",
            "domain": "coverage",
            "action_candidates": ["reopen_and_offer_open_shift"],
            "confidence_score": 0.94,
            "channel": channel,
        }
    if any(
        phrase in normalized
        for phrase in (
            "reopen the closed shift",
            "reopen the open shift",
            "reopen the shift",
            "reopen this shift",
        )
    ):
        return {
            "intent_type": "command",
            "domain": "schedule",
            "action_candidates": ["reopen_open_shift"],
            "confidence_score": 0.93,
            "channel": channel,
        }
    if any(
        phrase in normalized
        for phrase in (
            "approve fill",
            "approve claim",
            "approve coverage",
            "approve worker",
            "approve this",
            "approve him",
            "approve her",
        )
    ) or normalized.startswith("approve "):
        return {
            "intent_type": "command",
            "domain": "coverage",
            "action_candidates": ["approve_fill"],
            "confidence_score": 0.95,
            "channel": channel,
        }
    if any(
        phrase in normalized
        for phrase in (
            "decline fill",
            "decline claim",
            "reject claim",
            "keep looking",
            "decline this",
            "reject this",
        )
    ) or normalized.startswith("decline "):
        return {
            "intent_type": "command",
            "domain": "coverage",
            "action_candidates": ["decline_fill"],
            "confidence_score": 0.94,
            "channel": channel,
        }
    if any(
        phrase in normalized
        for phrase in (
            "cancel the open shift offer",
            "cancel open shift offer",
            "cancel the offer",
            "stop offering the open shift",
            "stop the open shift offer",
            "stop outreach for the open shift",
            "cancel coverage for the open shift",
        )
    ):
        return {
            "intent_type": "command",
            "domain": "coverage",
            "action_candidates": ["cancel_open_shift_offer"],
            "confidence_score": 0.93,
            "channel": channel,
        }
    if any(
        phrase in normalized
        for phrase in (
            "close the open shift",
            "close open shift",
            "remove the open shift",
            "shut down the open shift",
        )
    ):
        return {
            "intent_type": "command",
            "domain": "schedule",
            "action_candidates": ["close_open_shift"],
            "confidence_score": 0.93,
            "channel": channel,
        }
    if any(
        phrase in normalized
        for phrase in (
            "start coverage",
            "start outreach",
            "offer this shift",
            "offer the shift",
            "offer the open shift",
            "send this shift",
            "send the open shift",
            "open this shift",
            "open the shift",
            "fill this open shift",
        )
    ):
        return {
            "intent_type": "command",
            "domain": "coverage",
            "action_candidates": ["open_shift"],
            "confidence_score": 0.93,
            "channel": channel,
        }
    if any(phrase in normalized for phrase in ("ready to publish", "can i publish", "publish readiness")):
        return {
            "intent_type": "query",
            "domain": "schedule",
            "action_candidates": ["get_publish_readiness"],
            "confidence_score": 0.97,
            "channel": channel,
        }
    if "publish" in normalized:
        return {
            "intent_type": "command",
            "domain": "schedule",
            "action_candidates": ["publish_schedule"],
            "confidence_score": 0.95,
            "channel": channel,
        }
    if any(phrase in normalized for phrase in ("unfilled", "at risk", "open shifts", "open shift list")):
        return {
            "intent_type": "query",
            "domain": "coverage",
            "action_candidates": ["get_unfilled_shifts"],
            "confidence_score": 0.93,
            "channel": channel,
        }
    if any(phrase in normalized for phrase in ("coverage status", "coverage", "fill status", "what is covered")):
        return {
            "intent_type": "query",
            "domain": "coverage",
            "action_candidates": ["get_coverage_status"],
            "confidence_score": 0.9,
            "channel": channel,
        }
    if any(phrase in normalized for phrase in ("issues", "exceptions", "what changed", "review", "problems")):
        return {
            "intent_type": "query",
            "domain": "schedule",
            "action_candidates": ["explain_schedule_issues"],
            "confidence_score": 0.88,
            "channel": channel,
        }
    return {
        "intent_type": "query",
        "domain": "schedule",
        "action_candidates": ["get_schedule_summary"],
        "confidence_score": 0.72,
        "channel": channel,
    }


def _extract_open_shift_creation_rules(text: str, *, context: dict[str, Any]) -> dict[str, Any]:
    normalized = " ".join(text.lower().split())
    shift_date = _extract_shift_date(normalized, context=context)
    start_time, end_time = _extract_time_range(normalized)
    role = _extract_shift_role(normalized)
    start_open_shift_offer = any(
        phrase in normalized
        for phrase in (
            "offer it now",
            "send it out now",
            "start coverage right away",
            "start offering it",
            "offer this immediately",
            "send this shift now",
        )
    )
    spans_midnight = None
    if start_time and end_time:
        spans_midnight = end_time < start_time
    return {
        "role": role,
        "date": shift_date,
        "start_time": start_time,
        "end_time": end_time,
        "spans_midnight": spans_midnight,
        "start_open_shift_offer": start_open_shift_offer,
        "shift_label": None,
        "notes": None,
        "pay_rate": None,
        "requirements": [],
    }


def _extract_shift_edit_rules(text: str, *, context: dict[str, Any]) -> dict[str, Any]:
    normalized = " ".join(text.lower().split())
    shift_date = _extract_shift_date(normalized, context=context)
    start_time, end_time = _extract_time_range(normalized)
    spans_midnight = None
    if start_time and end_time:
        spans_midnight = end_time < start_time
    return {
        "role": None,
        "date": shift_date,
        "start_time": start_time,
        "end_time": end_time,
        "spans_midnight": spans_midnight,
        "shift_label": None,
        "notes": None,
        "pay_rate": None,
        "requirements": [],
    }


def _extract_shift_role(normalized: str) -> str | None:
    patterns = (
        r"(?:create|add|schedule)\s+(?:an?\s+)?open\s+([a-z0-9 _/-]+?)\s+shift\b",
        r"(?:create|add|schedule)\s+(?:an?\s+)?([a-z0-9 _/-]+?)\s+shift\b",
        r"\bnew\s+([a-z0-9 _/-]+?)\s+shift\b",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        raw_role = re.sub(r"\s+", "_", match.group(1).strip())
        raw_role = re.sub(r"[^a-z0-9_]+", "_", raw_role).strip("_")
        if raw_role:
            return raw_role
    return None


def _extract_shift_date(normalized: str, *, context: dict[str, Any]) -> str | None:
    iso_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", normalized)
    if iso_match:
        return iso_match.group(1)

    week_start_hint = str(context.get("week_start_date") or "").strip()
    weekday_date = _extract_weekday_date_from_text(normalized, week_start_hint=week_start_hint)
    if weekday_date:
        return weekday_date

    month_date = _extract_month_date_from_text(normalized, week_start_hint=week_start_hint)
    if month_date:
        return month_date
    return None


def _extract_weekday_date_from_text(normalized: str, *, week_start_hint: str) -> str | None:
    if not week_start_hint:
        return None
    weekday_map = {
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
    try:
        start = date.fromisoformat(week_start_hint)
    except ValueError:
        return None
    for token, weekday_index in weekday_map.items():
        if re.search(rf"\b{re.escape(token)}\b", normalized):
            return (start + timedelta(days=weekday_index)).isoformat()
    return None


def _extract_month_date_from_text(normalized: str, *, week_start_hint: str) -> str | None:
    month_match = re.search(
        r"\b("
        r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|sept|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?"
        r")\s+(\d{1,2})(?:,\s*(20\d{2}))?\b",
        normalized,
    )
    if not month_match:
        return None
    month_names = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }
    month = month_names[month_match.group(1)]
    day_of_month = int(month_match.group(2))
    if month_match.group(3):
        year = int(month_match.group(3))
    elif week_start_hint:
        try:
            year = date.fromisoformat(week_start_hint).year
        except ValueError:
            year = date.today().year
    else:
        year = date.today().year
    try:
        return date(year, month, day_of_month).isoformat()
    except ValueError:
        return None


def _extract_time_range(normalized: str) -> tuple[str | None, str | None]:
    patterns = (
        r"\bfrom\s+([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?)\s+(?:to|-)\s+([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?)\b",
        r"\b([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?)\s*(?:to|-)\s*([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        start_time = _parse_time_token(match.group(1))
        end_time = _parse_time_token(match.group(2), start_time=start_time)
        if start_time and end_time:
            return start_time, end_time
    return None, None


def _parse_time_token(value: str, *, start_time: str | None = None) -> str | None:
    raw = re.sub(r"\s+", "", value.lower())
    if not raw:
        return None

    if raw.endswith(("am", "pm")):
        meridiem = raw[-2:]
        clock = raw[:-2]
        if ":" in clock:
            hour_text, minute_text = clock.split(":", 1)
        else:
            hour_text, minute_text = clock, "00"
        try:
            hour = int(hour_text)
            minute = int(minute_text)
        except ValueError:
            return None
        if hour == 12:
            hour = 0
        if meridiem == "pm":
            hour += 12
        return f"{hour:02d}:{minute:02d}:00"

    if ":" in raw:
        hour_text, minute_text = raw.split(":", 1)
    else:
        hour_text, minute_text = raw, "00"
    try:
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError:
        return None
    if start_time is not None:
        try:
            start_hour = int(start_time[:2])
        except ValueError:
            start_hour = None
        if start_hour is not None and hour <= start_hour and hour < 12:
            hour += 12
    return f"{hour:02d}:{minute:02d}:00"
