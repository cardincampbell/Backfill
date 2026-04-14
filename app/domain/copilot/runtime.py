from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.copilot.registry import get_tool, list_tools, planner_tools, resolve_intent
from app.domain.copilot.validation import validate_and_normalize_tool_call
from app.models.business import Business, Location
from app.models.common import (
    AuditActorType,
    CoverageCaseStatus,
    MembershipRole,
    ShiftLifecycleStatus,
    ShiftStaffingStatus,
)
from app.models.coverage import AuditLog, CoverageCase
from app.models.scheduling import Shift
from app.schemas.copilot import (
    CopilotActionRunRead,
    CopilotIntentRead,
    CopilotMessageCreate,
    CopilotMessageRead,
    CopilotSessionCreate,
    CopilotSessionDetailRead,
    CopilotSessionEventRead,
    CopilotSessionRead,
    CopilotTurnRead,
    CopilotValidationResultRead,
)
from app.schemas.workforce import EmployeeAvailabilityRuleCreate, EmployeeAvailabilityRuleReplace
from app.services import auth as auth_service
from app.services import llm_gateway
from app.services import platform_events
from app.services import workforce
from app.services.auth import AuthContext

SESSION_TARGET_TYPE = "copilot_session"
SESSION_TTL_HOURS = 12
DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
READ_ROLES = {
    MembershipRole.owner,
    MembershipRole.admin,
    MembershipRole.manager,
    MembershipRole.viewer,
}


@dataclass(frozen=True)
class CopilotRequestContext:
    ip_address: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True)
class CopilotPlannedToolCall:
    intent: CopilotIntentRead
    tool_arguments: dict[str, Any]
    planner_source: str


CopilotLiveEventPublisher = Callable[[CopilotSessionEventRead], Awaitable[None]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _first_name(auth_ctx: AuthContext) -> str:
    full_name = (auth_ctx.user.full_name or "").strip()
    if not full_name:
        return "there"
    return full_name.split()[0]


def _session_state_is_active(state: str) -> bool:
    return state in {"active", "awaiting_confirmation", "awaiting_clarification"}


def _session_from_entry(entry: AuditLog) -> CopilotSessionRead | None:
    payload = entry.payload or {}
    raw = payload.get("session")
    if not isinstance(raw, dict):
        return None
    return CopilotSessionRead.model_validate(raw)


def _message_from_entry(entry: AuditLog) -> CopilotMessageRead | None:
    payload = entry.payload or {}
    raw = payload.get("message")
    if not isinstance(raw, dict):
        return None
    return CopilotMessageRead.model_validate(raw)


def _action_run_from_entry(entry: AuditLog) -> CopilotActionRunRead | None:
    payload = entry.payload or {}
    raw = payload.get("action_run")
    if not isinstance(raw, dict):
        return None
    return CopilotActionRunRead.model_validate(raw)


def _base_session_read(
    *,
    session_id: UUID,
    business_id: UUID,
    location_id: UUID | None,
    auth_ctx: AuthContext,
    normalized_channel: str,
    context_profile: dict,
) -> CopilotSessionRead:
    created_at = _now()
    return CopilotSessionRead(
        id=session_id,
        business_id=business_id,
        location_id=location_id,
        operator_user_id=auth_ctx.user.id,
        channel_last_seen=normalized_channel,
        state="active",
        intent_family=None,
        context_profile=context_profile,
        working_memory={},
        created_at=created_at,
        expires_at=created_at + timedelta(hours=SESSION_TTL_HOURS),
        last_message_at=None,
    )


def _session_with_updates(
    session_state: CopilotSessionRead,
    *,
    normalized_channel: str | None = None,
    intent_family: str | None = None,
    last_message_at: datetime | None = None,
) -> CopilotSessionRead:
    working_memory = dict(session_state.working_memory or {})
    if intent_family is not None:
        working_memory["last_intent_family"] = intent_family
    return session_state.model_copy(
        update={
            "channel_last_seen": normalized_channel or session_state.channel_last_seen,
            "intent_family": intent_family if intent_family is not None else session_state.intent_family,
            "working_memory": working_memory,
            "last_message_at": last_message_at if last_message_at is not None else session_state.last_message_at,
            "expires_at": _now() + timedelta(hours=SESSION_TTL_HOURS),
        }
    )


def _build_message(
    *,
    session_id: UUID,
    direction: str,
    normalized_channel: str,
    raw_text: str,
    message_metadata: dict | None = None,
) -> CopilotMessageRead:
    created_at = _now()
    return CopilotMessageRead(
        id=uuid4(),
        copilot_session_id=session_id,
        direction=direction,
        normalized_channel=normalized_channel,
        raw_text=raw_text,
        normalized_text=" ".join(raw_text.lower().split()),
        message_metadata=message_metadata or {},
        created_at=created_at,
    )


def _build_action_run(
    *,
    session_id: UUID,
    tool_name: str,
    status: str,
    input_payload: dict,
    validation_result: CopilotValidationResultRead,
    result_payload: dict | None = None,
    error_payload: dict | None = None,
    started_at: datetime | None = None,
) -> CopilotActionRunRead:
    start_time = started_at or _now()
    finished_at = _now() if status in {"executed", "failed", "cancelled"} else None
    return CopilotActionRunRead(
        id=uuid4(),
        copilot_session_id=session_id,
        tool_name=tool_name,
        status=status,
        input_payload=input_payload,
        validation_result=validation_result,
        result_payload=result_payload or {},
        error_payload=error_payload or {},
        started_at=start_time,
        finished_at=finished_at,
    )


async def _emit_live_event(
    publisher: CopilotLiveEventPublisher | None,
    *,
    event_type: str,
    trace_id: str,
    session_id: UUID,
    payload: dict[str, Any] | None = None,
) -> None:
    if publisher is None:
        return
    await publisher(
        CopilotSessionEventRead(
            event_id=uuid4(),
            event_type=event_type,
            trace_id=trace_id,
            session_id=session_id,
            occurred_at=_now(),
            payload=payload or {},
        )
    )


async def _append_copilot_event(
    db: AsyncSession,
    *,
    auth_ctx: AuthContext,
    business_id: UUID,
    location_id: UUID | None,
    session_state: CopilotSessionRead,
    event_type: str,
    payload: dict,
    request_context: CopilotRequestContext,
    trace_id: str | None = None,
) -> AuditLog:
    membership = auth_service.membership_for_scope(
        auth_ctx,
        business_id,
        location_id=location_id,
        allowed_roles=READ_ROLES,
    )
    return await platform_events.append(
        db,
        event_type=event_type,
        target_type=SESSION_TARGET_TYPE,
        target_id=session_state.id,
        business_id=business_id,
        location_id=location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=request_context.ip_address,
        user_agent=request_context.user_agent,
        payload={**payload, "session": session_state.model_dump(mode="json")},
        metadata={
            "channel": session_state.channel_last_seen,
            "session_id": session_state.id,
            **({"trace_id": trace_id} if trace_id else {}),
        },
    )


async def _load_business_context(
    db: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None,
) -> tuple[Business, Location | None]:
    business = await db.get(Business, business_id)
    if business is None:
        raise LookupError("business_not_found")
    location = None
    if location_id is not None:
        location = await db.get(Location, location_id)
        if location is None or location.business_id != business_id:
            raise LookupError("location_not_found")
    return business, location


def _session_context_profile(*, business: Business, location: Location | None) -> dict:
    profile = {
        "business_name": business.display_name,
        "business_slug": business.slug,
        "timezone": business.timezone,
    }
    if location is not None:
        profile.update(
            {
                "location_name": location.location_display_name,
                "location_slug": location.slug,
                "location_timezone": location.timezone,
            }
        )
    return profile


async def _session_entries(
    db: AsyncSession,
    *,
    business_id: UUID,
    session_id: UUID,
) -> list[AuditLog]:
    result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.business_id == business_id,
            AuditLog.target_type == SESSION_TARGET_TYPE,
            AuditLog.target_id == session_id,
        )
        .order_by(AuditLog.occurred_at.asc())
    )
    return list(result.scalars().all())


def _session_detail_from_entries(entries: list[AuditLog]) -> CopilotSessionDetailRead | None:
    session_state: CopilotSessionRead | None = None
    messages_by_id: dict[UUID, CopilotMessageRead] = {}
    action_runs_by_id: dict[UUID, CopilotActionRunRead] = {}

    for entry in entries:
        next_session = _session_from_entry(entry)
        if next_session is not None:
            session_state = next_session
        message = _message_from_entry(entry)
        if message is not None:
            messages_by_id[message.id] = message
        action_run = _action_run_from_entry(entry)
        if action_run is not None:
            action_runs_by_id[action_run.id] = action_run

    if session_state is None:
        return None

    messages = sorted(messages_by_id.values(), key=lambda item: item.created_at)
    action_runs = sorted(action_runs_by_id.values(), key=lambda item: item.started_at)
    return CopilotSessionDetailRead(
        session=session_state,
        tools=list_tools(),
        messages=messages,
        action_runs=action_runs,
    )


async def _get_session_detail_or_raise(
    db: AsyncSession,
    *,
    business_id: UUID,
    session_id: UUID,
) -> CopilotSessionDetailRead:
    detail = _session_detail_from_entries(
        await _session_entries(db, business_id=business_id, session_id=session_id)
    )
    if detail is None:
        raise LookupError("copilot_session_not_found")
    return detail


async def _find_reusable_session(
    db: AsyncSession,
    *,
    auth_ctx: AuthContext,
    business_id: UUID,
    location_id: UUID | None,
) -> CopilotSessionDetailRead | None:
    result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.business_id == business_id,
            AuditLog.target_type == SESSION_TARGET_TYPE,
            AuditLog.actor_user_id == auth_ctx.user.id,
        )
        .order_by(AuditLog.occurred_at.desc())
        .limit(200)
    )
    seen_session_ids: set[UUID] = set()
    for entry in result.scalars().all():
        session_id = entry.target_id
        if session_id is None or session_id in seen_session_ids:
            continue
        seen_session_ids.add(session_id)
        detail = await _get_session_detail_or_raise(
            db,
            business_id=business_id,
            session_id=session_id,
        )
        session_state = detail.session
        if session_state.operator_user_id != auth_ctx.user.id:
            continue
        if location_id is not None and session_state.location_id != location_id:
            continue
        if location_id is None and session_state.location_id is not None:
            continue
        if not _session_state_is_active(session_state.state):
            continue
        if session_state.expires_at is not None and session_state.expires_at <= _now():
            continue
        return detail
    return None


async def _current_availability_rules(
    db: AsyncSession,
    *,
    auth_ctx: AuthContext,
    business_id: UUID,
) -> list[dict[str, Any]]:
    try:
        _, rules = await workforce.get_self_employee_availability_rules(
            db,
            business_id,
            user_id=auth_ctx.user.id,
            email=auth_ctx.user.email,
            phone_e164=auth_ctx.user.primary_phone_e164,
            full_name=auth_ctx.user.full_name,
        )
    except LookupError:
        return []
    return [
        {
            "day_of_week": rule.day_of_week,
            "day_label": DAY_LABELS[rule.day_of_week] if 0 <= rule.day_of_week < len(DAY_LABELS) else str(rule.day_of_week),
            "start_local_time": rule.start_local_time.isoformat() if hasattr(rule.start_local_time, "isoformat") else str(rule.start_local_time),
            "end_local_time": rule.end_local_time.isoformat() if hasattr(rule.end_local_time, "isoformat") else str(rule.end_local_time),
            "timezone": rule.timezone,
        }
        for rule in rules
        if getattr(rule, "availability_type", "available") == "available"
    ]


def _planner_tool_definitions() -> list[llm_gateway.LlmToolDefinition]:
    return [
        llm_gateway.LlmToolDefinition(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
        )
        for tool in planner_tools()
    ]


def _preferred_timezone(session_state: CopilotSessionRead) -> str | None:
    context_profile = session_state.context_profile or {}
    raw_timezone = context_profile.get("location_timezone") or context_profile.get("timezone")
    return raw_timezone if isinstance(raw_timezone, str) and raw_timezone.strip() else None


def _planner_messages(
    *,
    session_state: CopilotSessionRead,
    history: list[CopilotMessageRead],
    current_availability_rules: list[dict[str, Any]],
    user_text: str,
) -> list[llm_gateway.LlmMessage]:
    context_profile = session_state.context_profile or {}
    business_name = context_profile.get("business_name") or "this business"
    location_name = context_profile.get("location_name") or "all accessible locations"
    timezone_name = _preferred_timezone(session_state) or "UTC"
    messages = [
        llm_gateway.LlmMessage(
            role="system",
            content=(
                "You are Backfill Copilot. Choose exactly one available tool for the operator's request. "
                "Use roster.update_availability only for the signed-in operator's own general weekly availability. "
                "That tool replaces the full weekly availability set, so return the complete replacement rules array. "
                "For availability rules, day_of_week uses 0=Monday through 6=Sunday and times should be plain local clock values. "
                "If the request does not clearly map to an execution tool, choose copilot.help. "
                "Do not choose planned or unavailable tools."
            ),
        ),
        llm_gateway.LlmMessage(
            role="system",
            content=(
                f"Business context: {business_name}. "
                f"Location context: {location_name}. "
                f"Default timezone: {timezone_name}."
            ),
        ),
        llm_gateway.LlmMessage(
            role="system",
            content=(
                "Current recurring weekly availability for the signed-in operator is: "
                f"{json.dumps(current_availability_rules)}. "
                "If the user asks to add, remove, or adjust availability, preserve unaffected existing rules and return the full replacement rules array. "
                "Use an empty rules array only when the operator explicitly asks to clear all availability, and set clear_requested=true in that case."
            ),
        ),
    ]
    for message in history[-6:]:
        messages.append(
            llm_gateway.LlmMessage(
                role="assistant" if message.direction == "outbound" else "user",
                content=message.raw_text,
            )
        )
    messages.append(llm_gateway.LlmMessage(role="user", content=user_text))
    return messages


def _llm_reasoning_text(result: llm_gateway.LlmGenerationResult, tool_name: str) -> str:
    if result.output_text and result.output_text.strip():
        return result.output_text.strip()
    tool_definition = get_tool(tool_name)
    tool_title = tool_definition.title if tool_definition is not None else tool_name
    return f"The planner selected {tool_title} for this request."


def _heuristic_intent(text: str) -> CopilotIntentRead:
    normalized = " ".join(text.lower().split())
    if any(
        phrase in normalized
        for phrase in (
            "set my availability",
            "update my availability",
            "clear my availability",
            "clear availability",
            "set my hours",
            "update my hours",
            "make my availability",
        )
    ):
        return CopilotIntentRead(
            family="roster",
            tool_name="roster.update_availability",
            reasoning="The request appears to be about updating the signed-in operator's recurring availability.",
            confidence=0.78,
        )
    return resolve_intent(text)


def _normalize_heuristic_time_token(value: str) -> str | None:
    raw = value.strip().lower().replace(".", "")
    patterns = ("%I:%M %p", "%I %p", "%I:%M%p", "%I%p", "%H:%M", "%H")
    normalized = raw.upper()
    for pattern in patterns:
        try:
            parsed = datetime.strptime(normalized, pattern)
            return parsed.strftime("%H:%M:%S")
        except ValueError:
            continue
    return None


def _time_phrase_to_range(text: str) -> tuple[str, str] | None:
    lowered = text.lower()
    if "all day" in lowered:
        return "00:00:00", "23:59:00"
    matches = [
        match.group(0)
        for match in re.finditer(
            r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b",
            text,
            flags=re.IGNORECASE,
        )
    ]
    if len(matches) < 2:
        return None
    start_raw, end_raw = matches[0], matches[1]
    start = _normalize_heuristic_time_token(start_raw)
    end = _normalize_heuristic_time_token(end_raw)
    if start is None or end is None:
        return None
    if end <= start and ("am" not in end_raw.lower() and "pm" not in end_raw.lower()):
        end_hour = int(end.split(":", maxsplit=1)[0])
        if end_hour < 12:
            candidate = f"{end_hour + 12:02d}{end[2:]}"
            if candidate > start:
                end = candidate
    return (start, end) if end > start else None


def _availability_days_from_text(text: str) -> list[int]:
    lowered = text.lower()
    if "weekdays" in lowered:
        return [0, 1, 2, 3, 4]
    if "weekends" in lowered:
        return [5, 6]
    if any(token in lowered for token in ("every day", "all days", "daily", "all week")):
        return list(range(7))

    day_patterns = {
        0: ("monday", "mon"),
        1: ("tuesday", "tue", "tues"),
        2: ("wednesday", "wed"),
        3: ("thursday", "thu", "thurs"),
        4: ("friday", "fri"),
        5: ("saturday", "sat"),
        6: ("sunday", "sun"),
    }
    token_to_day = {
        pattern: index
        for index, patterns in day_patterns.items()
        for pattern in patterns
    }
    for match in re.finditer(
        r"\b(monday|mon|tuesday|tue|tues|wednesday|wed|thursday|thu|thurs|friday|fri|saturday|sat|sunday|sun)\b\s*(?:through|thru|to|-)\s*\b(monday|mon|tuesday|tue|tues|wednesday|wed|thursday|thu|thurs|friday|fri|saturday|sat|sunday|sun)\b",
        lowered,
    ):
        start_day = token_to_day.get(match.group(1))
        end_day = token_to_day.get(match.group(2))
        if start_day is None or end_day is None:
            continue
        if start_day <= end_day:
            return list(range(start_day, end_day + 1))
        return list(range(start_day, 7)) + list(range(0, end_day + 1))

    days: list[int] = []
    for index, patterns in day_patterns.items():
        if any(re.search(rf"\b{pattern}\b", lowered) for pattern in patterns):
            days.append(index)
    if days:
        return sorted(set(days))
    return []


def _heuristic_availability_arguments(
    *,
    text: str,
    default_timezone: str | None,
) -> dict[str, Any] | None:
    lowered = text.lower()
    if any(token in lowered for token in (" add ", " remove ", " delete ", " except ", " also ", " plus ", " minus ")):
        return None
    if any(phrase in lowered for phrase in ("clear my availability", "clear availability", "remove all availability")):
        return {
            "timezone": default_timezone or "UTC",
            "clear_requested": True,
            "rules": [],
        }
    days = _availability_days_from_text(text)
    if not days:
        return None
    time_range = _time_phrase_to_range(text)
    if time_range is None:
        return None
    start_local_time, end_local_time = time_range
    timezone_name = default_timezone or "UTC"
    return {
        "timezone": timezone_name,
        "clear_requested": False,
        "rules": [
            {
                "day_of_week": day_of_week,
                "start_local_time": start_local_time,
                "end_local_time": end_local_time,
                "timezone": timezone_name,
            }
            for day_of_week in days
        ],
    }


async def _plan_tool_call(
    db: AsyncSession,
    *,
    auth_ctx: AuthContext,
    session_state: CopilotSessionRead,
    history: list[CopilotMessageRead],
    payload: CopilotMessageCreate,
    trace_id: str | None = None,
) -> CopilotPlannedToolCall:
    current_availability_rules = await _current_availability_rules(
        db,
        auth_ctx=auth_ctx,
        business_id=session_state.business_id,
    )
    planner_request = llm_gateway.LlmGenerationRequest(
        purpose="copilot_tool_planning",
        business_id=session_state.business_id,
        location_id=payload.location_id or session_state.location_id,
        messages=_planner_messages(
            session_state=session_state,
            history=history,
            current_availability_rules=current_availability_rules,
            user_text=payload.text.strip(),
        ),
        tools=_planner_tool_definitions(),
        tool_choice="required",
        metadata={
            "channel": payload.normalized_channel or session_state.channel_last_seen or "dashboard",
            "copilot_session_id": str(session_state.id),
            **({"trace_id": trace_id} if trace_id else {}),
        },
    )
    try:
        result = await llm_gateway.generate(db, request=planner_request)
    except Exception:
        result = None

    if result is not None and result.tool_calls:
        selected_call = result.tool_calls[0]
        tool_definition = get_tool(selected_call.name)
        if tool_definition is not None and tool_definition.availability == "available":
            return CopilotPlannedToolCall(
                intent=CopilotIntentRead(
                    family=tool_definition.intent_family,
                    tool_name=tool_definition.name,
                    reasoning=_llm_reasoning_text(result, tool_definition.name),
                    confidence=0.88,
                ),
                tool_arguments=dict(selected_call.arguments or {}),
                planner_source="llm",
            )

    heuristic_intent = _heuristic_intent(payload.text)
    heuristic_arguments: dict[str, Any] = {}
    if heuristic_intent.tool_name == "roster.update_availability":
        heuristic_arguments = _heuristic_availability_arguments(
            text=payload.text,
            default_timezone=_preferred_timezone(session_state),
        ) or {}
        if not heuristic_arguments:
            heuristic_intent = CopilotIntentRead(
                family="copilot",
                tool_name="copilot.help",
                reasoning="Availability updates need a clearer day-and-time request when the LLM planner is unavailable.",
                confidence=0.45,
            )
    return CopilotPlannedToolCall(
        intent=heuristic_intent,
        tool_arguments=heuristic_arguments,
        planner_source="heuristic",
    )


async def list_copilot_tools() -> list:
    return list_tools()


async def create_or_reuse_session(
    db: AsyncSession,
    *,
    auth_ctx: AuthContext,
    business_id: UUID,
    payload: CopilotSessionCreate,
    request_context: CopilotRequestContext,
) -> CopilotSessionDetailRead:
    normalized_channel = (payload.normalized_channel or "dashboard").strip() or "dashboard"
    if payload.location_id is not None and not auth_service.has_location_access(
        auth_ctx,
        business_id,
        payload.location_id,
        allowed_roles=READ_ROLES,
    ):
        raise PermissionError("location_access_denied")
    if payload.reuse_active:
        reusable = await _find_reusable_session(
            db,
            auth_ctx=auth_ctx,
            business_id=business_id,
            location_id=payload.location_id,
        )
        if reusable is not None:
            return reusable

    business, location = await _load_business_context(
        db,
        business_id=business_id,
        location_id=payload.location_id,
    )
    session_state = _base_session_read(
        session_id=uuid4(),
        business_id=business_id,
        location_id=payload.location_id,
        auth_ctx=auth_ctx,
        normalized_channel=normalized_channel,
        context_profile=_session_context_profile(business=business, location=location),
    )
    await _append_copilot_event(
        db,
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=payload.location_id,
        session_state=session_state,
        event_type=platform_events.PlatformEventType.COPILOT_SESSION_CREATED,
        payload={},
        request_context=request_context,
    )

    greeting_text = (
        f"Hi {_first_name(auth_ctx)}. I can summarize open shifts, active campaigns, manager actions, and update your availability."
    )
    greeting = _build_message(
        session_id=session_state.id,
        direction="outbound",
        normalized_channel=normalized_channel,
        raw_text=greeting_text,
        message_metadata={"message_kind": "greeting"},
    )
    updated_session = _session_with_updates(
        session_state,
        normalized_channel=normalized_channel,
        last_message_at=greeting.created_at,
    )
    await _append_copilot_event(
        db,
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=payload.location_id,
        session_state=updated_session,
        event_type=platform_events.PlatformEventType.COPILOT_MESSAGE_RECORDED,
        payload={"message": greeting.model_dump(mode="json")},
        request_context=request_context,
    )
    return CopilotSessionDetailRead(
        session=updated_session,
        tools=list_tools(),
        messages=[greeting],
        action_runs=[],
    )


async def get_session_detail(
    db: AsyncSession,
    *,
    auth_ctx: AuthContext,
    business_id: UUID,
    session_id: UUID,
) -> CopilotSessionDetailRead:
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=READ_ROLES):
        raise PermissionError("business_access_denied")
    detail = await _get_session_detail_or_raise(db, business_id=business_id, session_id=session_id)
    if detail.session.operator_user_id != auth_ctx.user.id:
        raise PermissionError("copilot_session_access_denied")
    if detail.session.location_id is not None and not auth_service.has_location_access(
        auth_ctx,
        business_id,
        detail.session.location_id,
        allowed_roles=READ_ROLES,
    ):
        raise PermissionError("location_access_denied")
    return detail


async def _accessible_locations(
    db: AsyncSession,
    *,
    auth_ctx: AuthContext,
    business_id: UUID,
    location_id: UUID | None,
) -> list[Location]:
    if location_id is not None:
        location = await db.get(Location, location_id)
        return [location] if location is not None and location.business_id == business_id else []

    has_business_scope = any(
        membership.business_id == business_id
        and membership.role in READ_ROLES
        and membership.location_id is None
        for membership in auth_ctx.memberships
    )
    if has_business_scope:
        result = await db.execute(
            select(Location)
            .where(Location.business_id == business_id, Location.is_active.is_(True))
            .order_by(Location.created_at.asc())
        )
        return list(result.scalars().all())

    allowed_location_ids = [
        membership.location_id
        for membership in auth_ctx.memberships
        if membership.business_id == business_id
        and membership.role in READ_ROLES
        and membership.location_id is not None
    ]
    if not allowed_location_ids:
        return []
    result = await db.execute(
        select(Location)
        .where(Location.id.in_(allowed_location_ids), Location.is_active.is_(True))
        .order_by(Location.created_at.asc())
    )
    return list(result.scalars().all())


async def _execute_open_shifts(
    db: AsyncSession,
    *,
    auth_ctx: AuthContext,
    business_id: UUID,
    location_id: UUID | None,
) -> tuple[dict, str]:
    locations = await _accessible_locations(
        db,
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=location_id,
    )
    if not locations:
        return {"kind": "open_shifts", "total_open_shifts": 0, "items": []}, "No accessible locations are available in this business context."

    location_ids = [item.id for item in locations]
    now = _now()
    result = await db.execute(
        select(Shift)
        .options(selectinload(Shift.location), selectinload(Shift.role))
        .where(
            Shift.business_id == business_id,
            Shift.location_id.in_(location_ids),
            Shift.starts_at >= now - timedelta(hours=1),
            Shift.lifecycle_status.in_([
                ShiftLifecycleStatus.scheduled,
                ShiftLifecycleStatus.in_progress,
            ]),
            Shift.staffing_status.in_([
                ShiftStaffingStatus.open,
                ShiftStaffingStatus.filling,
                ShiftStaffingStatus.no_fill,
                ShiftStaffingStatus.covered,
            ]),
        )
        .order_by(Shift.starts_at.asc())
        .limit(25)
    )
    shifts = [shift for shift in result.scalars().all() if shift.seats_filled < shift.seats_requested]
    items = [
        {
            "shift_id": str(shift.id),
            "location_id": str(shift.location_id),
            "location_name": shift.location.location_display_name if shift.location is not None else None,
            "role_name": shift.role.name if shift.role is not None else None,
            "starts_at": shift.starts_at.isoformat(),
            "ends_at": shift.ends_at.isoformat(),
            "status": shift.status.value if hasattr(shift.status, "value") else str(shift.status),
        }
        for shift in shifts[:5]
    ]
    if not shifts:
        return {"kind": "open_shifts", "total_open_shifts": 0, "items": []}, "No open shifts need coverage right now."

    location_names = sorted(
        {
            shift.location.location_display_name
            for shift in shifts
            if shift.location is not None and shift.location.location_display_name
        }
    )
    lead = items[0]
    summary = (
        f"I found {len(shifts)} open shift{'s' if len(shifts) != 1 else ''} across {len(location_names)} location"
        f"{'s' if len(location_names) != 1 else ''}. "
        f"Next up is {lead['role_name'] or 'an open role'} at {lead['location_name'] or 'this location'}."
    )
    return {
        "kind": "open_shifts",
        "total_open_shifts": len(shifts),
        "location_count": len(location_names),
        "items": items,
    }, summary


async def _execute_active_campaigns(
    db: AsyncSession,
    *,
    auth_ctx: AuthContext,
    business_id: UUID,
    location_id: UUID | None,
) -> tuple[dict, str]:
    locations = await _accessible_locations(
        db,
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=location_id,
    )
    if not locations:
        return {"kind": "campaigns", "total_active_campaigns": 0, "items": []}, "No accessible locations are available in this business context."
    location_ids = [item.id for item in locations]
    result = await db.execute(
        select(CoverageCase)
        .options(
            selectinload(CoverageCase.shift).selectinload(Shift.location),
            selectinload(CoverageCase.shift).selectinload(Shift.role),
        )
        .where(
            CoverageCase.location_id.in_(location_ids),
            CoverageCase.status.in_([CoverageCaseStatus.queued, CoverageCaseStatus.running]),
        )
        .order_by(CoverageCase.created_at.desc())
        .limit(25)
    )
    campaigns = list(result.scalars().all())
    items = [
        {
            "campaign_id": str(item.id),
            "shift_id": str(item.shift_id),
            "location_name": item.shift.location.location_display_name if item.shift and item.shift.location else None,
            "role_name": item.shift.role.name if item.shift and item.shift.role else None,
            "status": item.status.value if hasattr(item.status, "value") else str(item.status),
            "phase_target": item.phase_target,
            "opened_at": item.opened_at.isoformat() if item.opened_at is not None else None,
        }
        for item in campaigns[:5]
    ]
    if not campaigns:
        return {"kind": "campaigns", "total_active_campaigns": 0, "items": []}, "There are no active campaigns right now."
    running_count = sum(1 for item in campaigns if item.status == CoverageCaseStatus.running)
    queued_count = sum(1 for item in campaigns if item.status == CoverageCaseStatus.queued)
    return {
        "kind": "campaigns",
        "total_active_campaigns": len(campaigns),
        "running_count": running_count,
        "queued_count": queued_count,
        "items": items,
    }, (
        f"There are {len(campaigns)} active campaign{'s' if len(campaigns) != 1 else ''}: "
        f"{running_count} running and {queued_count} queued."
    )


async def _execute_manager_actions(
    db: AsyncSession,
    *,
    auth_ctx: AuthContext,
    business_id: UUID,
    location_id: UUID | None,
) -> tuple[dict, str]:
    locations = await _accessible_locations(
        db,
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=location_id,
    )
    if not locations:
        return {"kind": "manager_actions", "total_actions": 0, "items": []}, "No accessible locations are available in this business context."
    location_ids = [item.id for item in locations]
    result = await db.execute(
        select(CoverageCase)
        .options(
            selectinload(CoverageCase.shift).selectinload(Shift.location),
            selectinload(CoverageCase.shift).selectinload(Shift.role),
        )
        .where(
            CoverageCase.location_id.in_(location_ids),
            CoverageCase.requires_manager_approval.is_(True),
            CoverageCase.status.in_([CoverageCaseStatus.queued, CoverageCaseStatus.running]),
        )
        .order_by(CoverageCase.created_at.asc())
        .limit(25)
    )
    actions = [
        item for item in result.scalars().all() if item.shift is not None and item.shift.seats_filled < item.shift.seats_requested
    ]
    items = [
        {
            "campaign_id": str(item.id),
            "shift_id": str(item.shift_id),
            "location_name": item.shift.location.location_display_name if item.shift and item.shift.location else None,
            "role_name": item.shift.role.name if item.shift and item.shift.role else None,
            "starts_at": item.shift.starts_at.isoformat() if item.shift is not None else None,
            "status": item.status.value if hasattr(item.status, "value") else str(item.status),
        }
        for item in actions[:5]
    ]
    if not actions:
        return {"kind": "manager_actions", "total_actions": 0, "items": []}, "No manager actions need attention right now."
    return {
        "kind": "manager_actions",
        "total_actions": len(actions),
        "items": items,
    }, f"There are {len(actions)} manager action{'s' if len(actions) != 1 else ''} waiting for review."


async def _execute_help() -> tuple[dict, str]:
    tools = list_tools()
    return {
        "kind": "help",
        "tools": [tool.model_dump(mode="json") for tool in tools],
    }, "I can summarize open shifts, active campaigns, and manager actions, and I can update your availability. Schedule publishing is still planned, and coverage-starting tools are intentionally not enabled in this scaffold."


def _display_local_time(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%H:%M:%S")
    except ValueError:
        return value
    return parsed.strftime("%-I:%M %p")


def _availability_update_summary(result_payload: dict[str, Any]) -> str:
    rules = result_payload.get("rules", [])
    if not isinstance(rules, list) or not rules:
        return "Cleared your general availability."
    if all(isinstance(rule, dict) for rule in rules):
        first_rule = rules[0]
        shared_hours = all(
            rule.get("start_local_time") == first_rule.get("start_local_time")
            and rule.get("end_local_time") == first_rule.get("end_local_time")
            for rule in rules
        )
        if shared_hours:
            day_labels = ", ".join(
                DAY_LABELS[int(rule["day_of_week"])]
                for rule in rules
                if isinstance(rule.get("day_of_week"), int)
            )
            return (
                f"Updated your availability for {day_labels} from "
                f"{_display_local_time(first_rule.get('start_local_time', ''))} to "
                f"{_display_local_time(first_rule.get('end_local_time', ''))}."
            )
    day_count = result_payload.get("day_count") or len(rules)
    return f"Updated your general availability across {day_count} day{'s' if day_count != 1 else ''}."


async def _execute_update_availability(
    db: AsyncSession,
    *,
    auth_ctx: AuthContext,
    business_id: UUID,
    tool_arguments: dict[str, Any],
) -> tuple[dict, str]:
    payload = EmployeeAvailabilityRuleReplace(
        rules=[
            EmployeeAvailabilityRuleCreate.model_validate(rule)
            for rule in tool_arguments.get("rules", [])
        ]
    )
    employee, rules = await workforce.replace_self_employee_availability_rules(
        db,
        business_id,
        user_id=auth_ctx.user.id,
        email=auth_ctx.user.email,
        phone_e164=auth_ctx.user.primary_phone_e164,
        full_name=auth_ctx.user.full_name,
        payload=payload,
    )
    serialized_rules = [
        {
            "day_of_week": rule.day_of_week,
            "start_local_time": rule.start_local_time.isoformat() if hasattr(rule.start_local_time, "isoformat") else str(rule.start_local_time),
            "end_local_time": rule.end_local_time.isoformat() if hasattr(rule.end_local_time, "isoformat") else str(rule.end_local_time),
            "timezone": rule.timezone,
        }
        for rule in rules
    ]
    result_payload = {
        "kind": "availability_update",
        "employee_id": str(employee.id),
        "employee_name": employee.preferred_name or employee.full_name,
        "timezone": rules[0].timezone if rules else tool_arguments.get("timezone") or "UTC",
        "day_count": len({rule["day_of_week"] for rule in serialized_rules}),
        "rule_count": len(serialized_rules),
        "rules": serialized_rules,
    }
    return result_payload, _availability_update_summary(result_payload)


async def _execute_tool(
    db: AsyncSession,
    *,
    auth_ctx: AuthContext,
    business_id: UUID,
    location_id: UUID | None,
    tool_name: str,
    tool_arguments: dict[str, Any] | None = None,
) -> tuple[dict, str]:
    if tool_name == "schedule.list_open_shifts":
        return await _execute_open_shifts(
            db,
            auth_ctx=auth_ctx,
            business_id=business_id,
            location_id=location_id,
        )
    if tool_name == "coverage.list_active_campaigns":
        return await _execute_active_campaigns(
            db,
            auth_ctx=auth_ctx,
            business_id=business_id,
            location_id=location_id,
        )
    if tool_name == "schedule.list_manager_actions":
        return await _execute_manager_actions(
            db,
            auth_ctx=auth_ctx,
            business_id=business_id,
            location_id=location_id,
        )
    if tool_name == "roster.update_availability":
        return await _execute_update_availability(
            db,
            auth_ctx=auth_ctx,
            business_id=business_id,
            tool_arguments=tool_arguments or {},
        )
    return await _execute_help()


async def create_turn(
    db: AsyncSession,
    *,
    auth_ctx: AuthContext,
    business_id: UUID,
    session_id: UUID,
    payload: CopilotMessageCreate,
    request_context: CopilotRequestContext,
    live_event_publisher: CopilotLiveEventPublisher | None = None,
    live_trace_id: str | None = None,
) -> CopilotTurnRead:
    trace_id = live_trace_id or str(uuid4())
    detail = await get_session_detail(
        db,
        auth_ctx=auth_ctx,
        business_id=business_id,
        session_id=session_id,
    )
    normalized_channel = (payload.normalized_channel or detail.session.channel_last_seen or "dashboard").strip() or "dashboard"
    effective_location_id = payload.location_id or detail.session.location_id

    inbound = _build_message(
        session_id=session_id,
        direction="inbound",
        normalized_channel=normalized_channel,
        raw_text=payload.text.strip(),
    )
    session_after_inbound = _session_with_updates(
        detail.session,
        normalized_channel=normalized_channel,
        last_message_at=inbound.created_at,
    )
    await _append_copilot_event(
        db,
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=effective_location_id,
        session_state=session_after_inbound,
        event_type=platform_events.PlatformEventType.COPILOT_MESSAGE_RECORDED,
        payload={"message": inbound.model_dump(mode="json")},
        request_context=request_context,
        trace_id=trace_id,
    )
    await _emit_live_event(
        live_event_publisher,
        event_type="user.message.accepted",
        trace_id=trace_id,
        session_id=session_id,
        payload={
            "message": inbound.model_dump(mode="json"),
            "session": session_after_inbound.model_dump(mode="json"),
        },
    )
    await _emit_live_event(
        live_event_publisher,
        event_type="assistant.turn.started",
        trace_id=trace_id,
        session_id=session_id,
        payload={
            "session": session_after_inbound.model_dump(mode="json"),
            "message_id": str(inbound.id),
        },
    )
    await _emit_live_event(
        live_event_publisher,
        event_type="assistant.progress",
        trace_id=trace_id,
        session_id=session_id,
        payload={"state": "thinking", "label": "Understanding your request."},
    )

    planned_tool_call = await _plan_tool_call(
        db,
        auth_ctx=auth_ctx,
        session_state=detail.session,
        history=detail.messages,
        payload=payload,
        trace_id=trace_id,
    )
    intent = planned_tool_call.intent

    session_after_intent = _session_with_updates(
        session_after_inbound,
        normalized_channel=normalized_channel,
        intent_family=intent.family,
        last_message_at=inbound.created_at,
    )
    await _append_copilot_event(
        db,
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=effective_location_id,
        session_state=session_after_intent,
        event_type=platform_events.PlatformEventType.COPILOT_INTENT_RESOLVED,
        payload={
            "resolved_intent": intent.model_dump(mode="json"),
            "planner_source": planned_tool_call.planner_source,
        },
        request_context=request_context,
        trace_id=trace_id,
    )
    await _emit_live_event(
        live_event_publisher,
        event_type="assistant.progress",
        trace_id=trace_id,
        session_id=session_id,
        payload={
            "state": "planning",
            "label": "Planning the next action.",
            "resolved_intent": intent.model_dump(mode="json"),
            "planner_source": planned_tool_call.planner_source,
        },
    )

    validated_tool_call = validate_and_normalize_tool_call(
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=effective_location_id,
        tool_name=intent.tool_name,
        tool_arguments=planned_tool_call.tool_arguments,
        default_timezone=_preferred_timezone(detail.session),
    )
    validation_result = validated_tool_call.validation_result
    tool_input = {
        "business_id": str(business_id),
        "location_id": str(effective_location_id) if effective_location_id is not None else None,
        "message_id": str(inbound.id),
        "text": inbound.raw_text,
        "planner_source": planned_tool_call.planner_source,
        "tool_arguments": validated_tool_call.normalized_arguments,
    }

    if not validation_result.ok:
        action_run = _build_action_run(
            session_id=session_id,
            tool_name=intent.tool_name,
            status="failed",
            input_payload=tool_input,
            validation_result=validation_result,
            error_payload={"code": validation_result.code, "message": validation_result.message},
        )
        outbound = _build_message(
            session_id=session_id,
            direction="outbound",
            normalized_channel=normalized_channel,
            raw_text=validation_result.message,
            message_metadata={"message_kind": "validation_error"},
        )
        session_after_outbound = _session_with_updates(
            session_after_intent,
            normalized_channel=normalized_channel,
            last_message_at=outbound.created_at,
        )
        turn = CopilotTurnRead(
            session=session_after_outbound,
            resolved_intent=intent,
            inbound_message=inbound,
            outbound_message=outbound,
            action_run=action_run,
            tools=list_tools(),
        )
        await _append_copilot_event(
            db,
            auth_ctx=auth_ctx,
            business_id=business_id,
            location_id=effective_location_id,
            session_state=session_after_outbound,
            event_type=platform_events.PlatformEventType.COPILOT_ACTION_FAILED,
            payload={"action_run": action_run.model_dump(mode="json")},
            request_context=request_context,
            trace_id=trace_id,
        )
        await _append_copilot_event(
            db,
            auth_ctx=auth_ctx,
            business_id=business_id,
            location_id=effective_location_id,
            session_state=session_after_outbound,
            event_type=platform_events.PlatformEventType.COPILOT_MESSAGE_RECORDED,
            payload={"message": outbound.model_dump(mode="json")},
            request_context=request_context,
            trace_id=trace_id,
        )
        await _emit_live_event(
            live_event_publisher,
            event_type="assistant.turn.failed",
            trace_id=trace_id,
            session_id=session_id,
            payload={
                "error": {
                    "code": validation_result.code,
                    "message": validation_result.message,
                },
                "turn": turn.model_dump(mode="json"),
            },
        )
        return turn

    await _emit_live_event(
        live_event_publisher,
        event_type="assistant.progress",
        trace_id=trace_id,
        session_id=session_id,
        payload={
            "state": "running_tool",
            "label": f"Running {intent.tool_name}.",
        },
    )
    await _emit_live_event(
        live_event_publisher,
        event_type="tool.started",
        trace_id=trace_id,
        session_id=session_id,
        payload={
            "tool_name": intent.tool_name,
            "input_payload": tool_input,
            "validation_result": validation_result.model_dump(mode="json"),
        },
    )

    result_payload, outbound_text = await _execute_tool(
        db,
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=effective_location_id,
        tool_name=intent.tool_name,
        tool_arguments=validated_tool_call.normalized_arguments,
    )
    action_run = _build_action_run(
        session_id=session_id,
        tool_name=intent.tool_name,
        status="executed",
        input_payload=tool_input,
        validation_result=validation_result,
        result_payload=result_payload,
    )
    outbound = _build_message(
        session_id=session_id,
        direction="outbound",
        normalized_channel=normalized_channel,
        raw_text=outbound_text,
        message_metadata={"message_kind": "tool_result", "tool_name": intent.tool_name},
    )
    session_after_outbound = _session_with_updates(
        session_after_intent,
        normalized_channel=normalized_channel,
        last_message_at=outbound.created_at,
    )
    turn = CopilotTurnRead(
        session=session_after_outbound,
        resolved_intent=intent,
        inbound_message=inbound,
        outbound_message=outbound,
        action_run=action_run,
        tools=list_tools(),
    )
    await _append_copilot_event(
        db,
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=effective_location_id,
        session_state=session_after_outbound,
        event_type=platform_events.PlatformEventType.COPILOT_ACTION_EXECUTED,
        payload={"action_run": action_run.model_dump(mode="json")},
        request_context=request_context,
        trace_id=trace_id,
    )
    await _append_copilot_event(
        db,
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=effective_location_id,
        session_state=session_after_outbound,
        event_type=platform_events.PlatformEventType.COPILOT_MESSAGE_RECORDED,
        payload={"message": outbound.model_dump(mode="json")},
        request_context=request_context,
        trace_id=trace_id,
    )
    await _emit_live_event(
        live_event_publisher,
        event_type="tool.finished",
        trace_id=trace_id,
        session_id=session_id,
        payload={"action_run": action_run.model_dump(mode="json")},
    )
    await _emit_live_event(
        live_event_publisher,
        event_type="assistant.message.completed",
        trace_id=trace_id,
        session_id=session_id,
        payload={"turn": turn.model_dump(mode="json")},
    )
    return turn
