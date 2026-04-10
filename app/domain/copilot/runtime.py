from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.copilot.registry import list_tools, resolve_intent
from app.domain.copilot.validation import validate_tool_call
from app.models.business import Business, Location
from app.models.common import AuditActorType, CoverageCaseStatus, MembershipRole, ShiftStatus
from app.models.coverage import AuditLog, CoverageCase
from app.models.scheduling import Shift
from app.schemas.copilot import (
    CopilotActionRunRead,
    CopilotMessageCreate,
    CopilotMessageRead,
    CopilotSessionCreate,
    CopilotSessionDetailRead,
    CopilotSessionRead,
    CopilotTurnRead,
    CopilotValidationResultRead,
)
from app.services import auth as auth_service
from app.services import platform_events
from app.services.auth import AuthContext

SESSION_TARGET_TYPE = "copilot_session"
SESSION_TTL_HOURS = 12
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
        metadata={"channel": session_state.channel_last_seen, "session_id": session_state.id},
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
            AuditLog.event_name == platform_events.PlatformEventType.COPILOT_SESSION_CREATED,
        )
        .order_by(AuditLog.occurred_at.desc())
        .limit(25)
    )
    for entry in result.scalars().all():
        session_state = _session_from_entry(entry)
        if session_state is None:
            continue
        if location_id is not None and session_state.location_id != location_id:
            continue
        if location_id is None and session_state.location_id is not None:
            continue
        if not _session_state_is_active(session_state.state):
            continue
        if session_state.expires_at is not None and session_state.expires_at <= _now():
            continue
        return await _get_session_detail_or_raise(
            db,
            business_id=business_id,
            session_id=session_state.id,
        )
    return None


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
        f"Hi {_first_name(auth_ctx)}. I can summarize open shifts, active campaigns, and manager actions for you."
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
            Shift.status.in_([
                ShiftStatus.scheduled,
                ShiftStatus.open,
                ShiftStatus.filling,
                ShiftStatus.no_fill,
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
    }, "I can summarize open shifts, active campaigns, and manager actions. Coverage-starting tools are intentionally not enabled in this scaffold."


async def _execute_tool(
    db: AsyncSession,
    *,
    auth_ctx: AuthContext,
    business_id: UUID,
    location_id: UUID | None,
    tool_name: str,
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
    return await _execute_help()


async def create_turn(
    db: AsyncSession,
    *,
    auth_ctx: AuthContext,
    business_id: UUID,
    session_id: UUID,
    payload: CopilotMessageCreate,
    request_context: CopilotRequestContext,
) -> CopilotTurnRead:
    detail = await get_session_detail(
        db,
        auth_ctx=auth_ctx,
        business_id=business_id,
        session_id=session_id,
    )
    normalized_channel = (payload.normalized_channel or detail.session.channel_last_seen or "dashboard").strip() or "dashboard"
    effective_location_id = payload.location_id or detail.session.location_id
    intent = resolve_intent(payload.text)

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
    )

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
        payload={"resolved_intent": intent.model_dump(mode="json")},
        request_context=request_context,
    )

    validation_result = validate_tool_call(
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=effective_location_id,
        tool_name=intent.tool_name,
    )
    tool_input = {
        "business_id": str(business_id),
        "location_id": str(effective_location_id) if effective_location_id is not None else None,
        "message_id": str(inbound.id),
        "text": inbound.raw_text,
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
        await _append_copilot_event(
            db,
            auth_ctx=auth_ctx,
            business_id=business_id,
            location_id=effective_location_id,
            session_state=session_after_outbound,
            event_type=platform_events.PlatformEventType.COPILOT_ACTION_FAILED,
            payload={"action_run": action_run.model_dump(mode="json")},
            request_context=request_context,
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
        )
        return CopilotTurnRead(
            session=session_after_outbound,
            resolved_intent=intent,
            inbound_message=inbound,
            outbound_message=outbound,
            action_run=action_run,
            tools=list_tools(),
        )

    result_payload, outbound_text = await _execute_tool(
        db,
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=effective_location_id,
        tool_name=intent.tool_name,
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
    await _append_copilot_event(
        db,
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=effective_location_id,
        session_state=session_after_outbound,
        event_type=platform_events.PlatformEventType.COPILOT_ACTION_EXECUTED,
        payload={"action_run": action_run.model_dump(mode="json")},
        request_context=request_context,
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
    )
    return CopilotTurnRead(
        session=session_after_outbound,
        resolved_intent=intent,
        inbound_message=inbound,
        outbound_message=outbound,
        action_run=action_run,
        tools=list_tools(),
    )
