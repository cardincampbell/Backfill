from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Location, Role
from app.models.common import OfferStatus, RetellConversationType, ShiftStatus
from app.models.coverage import CoverageCase, CoverageOffer
from app.models.identity import User
from app.models.integrations import RetellConversation
from app.models.scheduling import Shift
from app.models.workforce import Employee
from app.schemas.coverage import CoverageOfferResponseCreate
from app.schemas.scheduling import ShiftCreate
from app.services import coverage as coverage_service
from app.services import delivery, messaging, scheduler_sync, scheduling
from app.services.utils import role_code_from_name
from app.config import settings


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
    conversation.conversation_summary = summary
    conversation.transcript_text = transcript_text
    conversation.transcript_items = transcript_items
    conversation.analysis = analysis
    conversation.metadata_json = metadata
    conversation.raw_payload = body
    conversation.started_at = _normalize_timestamp(_pick_value(payload, body, keys=("started_at", "start_timestamp", "start_time"))) or conversation.started_at
    conversation.ended_at = _normalize_timestamp(_pick_value(payload, body, keys=("ended_at", "end_timestamp", "end_time"))) or conversation.ended_at
    await session.flush()
    return conversation


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
    user = await session.scalar(select(User).where(User.primary_phone_e164 == normalized))
    employee = await session.scalar(select(Employee).where(Employee.phone_e164 == normalized))
    context = await delivery.find_latest_actionable_offer_for_phone(session, normalized)
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
            "location_id": str(employee.home_location_id) if employee.home_location_id else None,
        } if employee is not None else None,
        "actionable_offer_id": str(context.offer.id) if context is not None else None,
    }


async def get_open_shifts(session: AsyncSession, location_id: UUID | None = None) -> dict:
    stmt = select(Shift).where(Shift.status.in_([ShiftStatus.open, ShiftStatus.filling]))
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
    role_code = role_code_from_name(role_name)
    role = await session.scalar(
        select(Role).where(Role.business_id == location.business_id, Role.code == role_code)
    )
    if role is None:
        role = Role(
            business_id=location.business_id,
            code=role_code,
            name=role_name,
            min_notice_minutes=0,
            coverage_priority=100,
            metadata_json={"source": "retell_voice"},
        )
        session.add(role)
        await session.flush()
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


async def send_onboarding_link(phone: str, *, kind: str, location_id: UUID | None = None, platform: str | None = None) -> dict:
    path = "/try"
    if location_id is not None:
        path = f"/try?location_id={location_id}&kind={kind}"
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
        shift_id = _uuid_from_mapping(args, keys=("shift_id",))
        if shift_id is None:
            raise ValueError("shift_id_required")
        employee_id = _uuid_from_mapping(args, keys=("employee_id", "worker_id"))
        return await scheduler_sync.create_vacancy_for_shift(
            session,
            shift_id=shift_id,
            employee_id=employee_id,
            triggered_by="retell_voice",
            reason_code="voice_callout",
        )
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
            phone,
            kind=str(args.get("kind") or "invite"),
            location_id=location_id,
            platform=str(args.get("platform") or "").strip() or None,
        )
    raise ValueError(f"unsupported_retell_function:{name}")
