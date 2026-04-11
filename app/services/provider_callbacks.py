from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Location
from app.models.coverage import CoverageCase, CoverageOffer
from app.models.integrations import ProviderCallbackLog, RetellConversation
from app.models.scheduling import Shift
from app.services import delivery, retell_workflow, worker_runtime

_CALLBACK_MAX_ATTEMPTS = 3
_NON_RETRYABLE_STATUS_CODES = {400, 404, 422}


def _normalized_mapping(mapping: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        return {}
    return {
        str(key): value
        if isinstance(value, (dict, list, str, int, float, bool)) or value is None
        else str(value)
        for key, value in mapping.items()
    }


def _stable_payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _normalized_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _normalized_uuid(value: Any) -> UUID | None:
    text = _normalized_text(value)
    if text is None:
        return None
    try:
        return UUID(text)
    except (TypeError, ValueError):
        return None


@dataclass
class CallbackProcessingResult:
    callback_log_id: UUID
    response_kind: Literal["empty", "json", "twiml"] = "json"
    response_payload: dict[str, Any] = field(default_factory=dict)
    response_text: str | None = None
    duplicate: bool = False


class CallbackProcessingError(Exception):
    def __init__(
        self,
        error_message: str,
        *,
        status_code: int = 500,
        detail: str | None = None,
        result_payload: dict[str, Any] | None = None,
    ) -> None:
        normalized_error = error_message.strip() or "callback_processing_failed"
        super().__init__(normalized_error)
        self.error_message = normalized_error
        self.status_code = status_code
        self.detail = (detail or normalized_error).strip() or normalized_error
        self.result_payload = _normalized_mapping(result_payload)


CallbackProcessor = Callable[[AsyncSession, ProviderCallbackLog], Awaitable[CallbackProcessingResult]]
_PROCESSOR_REGISTRY: dict[tuple[str, str], CallbackProcessor] = {}


def callback_processor(provider: str, route_key: str) -> Callable[[CallbackProcessor], CallbackProcessor]:
    normalized_key = (provider.strip().lower(), route_key.strip())

    def decorator(processor: CallbackProcessor) -> CallbackProcessor:
        _PROCESSOR_REGISTRY[normalized_key] = processor
        return processor

    return decorator


def dedupe_key_for_callback(
    *,
    provider: str,
    provider_event_id: str | None,
    payload: dict[str, Any] | None,
) -> str:
    normalized_provider = provider.strip().lower()
    normalized_event_id = str(provider_event_id or "").strip()
    if normalized_event_id:
        return f"{normalized_provider}:{normalized_event_id}"
    return f"{normalized_provider}:{_stable_payload_hash(_normalized_mapping(payload))}"


async def record_raw_callback(
    session: AsyncSession,
    *,
    provider: str,
    route_key: str,
    headers: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    event_type: str | None = None,
    provider_event_id: str | None = None,
) -> tuple[ProviderCallbackLog, bool]:
    dedupe_key = dedupe_key_for_callback(
        provider=provider,
        provider_event_id=provider_event_id,
        payload=payload,
    )
    existing = await session.scalar(
        select(ProviderCallbackLog).where(
            ProviderCallbackLog.provider == provider.strip().lower(),
            ProviderCallbackLog.dedupe_key == dedupe_key,
        )
    )
    if existing is not None:
        return existing, False

    entry = ProviderCallbackLog(
        provider=provider.strip().lower(),
        route_key=route_key.strip(),
        event_type=(str(event_type).strip() if event_type is not None else None) or None,
        provider_event_id=(str(provider_event_id).strip() if provider_event_id is not None else None)
        or None,
        dedupe_key=dedupe_key,
        status="received",
        headers=_normalized_mapping(headers),
        payload=_normalized_mapping(payload),
    )
    session.add(entry)
    await session.flush()
    return entry, True


async def list_callback_logs(
    session: AsyncSession,
    *,
    provider: str | None = None,
    route_key: str | None = None,
    status: str | None = None,
    event_type: str | None = None,
    provider_event_id: str | None = None,
    dedupe_key: str | None = None,
    limit: int = 50,
) -> list[ProviderCallbackLog]:
    stmt = (
        select(ProviderCallbackLog)
        .order_by(ProviderCallbackLog.received_at.desc(), ProviderCallbackLog.created_at.desc())
        .limit(max(1, min(limit, 250)))
    )
    if provider is not None:
        stmt = stmt.where(ProviderCallbackLog.provider == provider.strip().lower())
    if route_key is not None:
        stmt = stmt.where(ProviderCallbackLog.route_key == route_key.strip())
    if status is not None:
        stmt = stmt.where(ProviderCallbackLog.status == status.strip())
    if event_type is not None:
        stmt = stmt.where(ProviderCallbackLog.event_type == event_type.strip())
    if provider_event_id is not None:
        stmt = stmt.where(ProviderCallbackLog.provider_event_id == provider_event_id.strip())
    if dedupe_key is not None:
        stmt = stmt.where(ProviderCallbackLog.dedupe_key == dedupe_key.strip())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_callback_log(
    session: AsyncSession,
    *,
    callback_log_id: UUID,
) -> ProviderCallbackLog | None:
    return await session.get(ProviderCallbackLog, callback_log_id)


async def mark_processed(
    session: AsyncSession,
    entry: ProviderCallbackLog,
    *,
    result_payload: dict[str, Any] | None = None,
) -> ProviderCallbackLog:
    entry.status = "processed"
    entry.processed_at = datetime.now(timezone.utc)
    entry.result_payload = _normalized_mapping(result_payload)
    entry.error_message = None
    await session.flush()
    return entry


async def mark_failed(
    session: AsyncSession,
    entry: ProviderCallbackLog,
    *,
    error_message: str,
    result_payload: dict[str, Any] | None = None,
    status_code: int | None = None,
    terminal: bool = False,
    failure_count: int | None = None,
) -> ProviderCallbackLog:
    reference_time = datetime.now(timezone.utc)
    payload = {
        **_normalized_mapping(entry.result_payload),
        **_normalized_mapping(result_payload),
    }
    if failure_count is not None:
        payload["failure_count"] = failure_count
    if status_code is not None:
        payload["last_status_code"] = status_code
    if terminal:
        payload["terminal_state"] = "dead_lettered"
        payload["dead_lettered_at"] = reference_time.isoformat()
        if status_code is not None:
            payload["terminal_status_code"] = status_code

    entry.status = "dead_lettered" if terminal else "failed"
    entry.processed_at = reference_time
    entry.error_message = error_message.strip() or "callback_processing_failed"
    entry.result_payload = payload
    await session.flush()
    return entry


def _existing_result(entry: ProviderCallbackLog) -> CallbackProcessingResult:
    payload = _normalized_mapping(entry.result_payload)
    if entry.route_key == "twilio_sms_status":
        return CallbackProcessingResult(
            callback_log_id=entry.id,
            response_kind="empty",
            response_payload=payload,
            duplicate=True,
        )
    if entry.route_key == "twilio_sms_inbound":
        reply_message = _normalized_text(payload.get("reply_message")) or "Thanks, we already received that response."
        return CallbackProcessingResult(
            callback_log_id=entry.id,
            response_kind="twiml",
            response_payload=payload,
            response_text=reply_message,
            duplicate=True,
        )
    return CallbackProcessingResult(
        callback_log_id=entry.id,
        response_kind="json",
        response_payload=payload or {"status": "duplicate", "event": entry.event_type},
        duplicate=True,
    )


def _callback_failure_count(entry: ProviderCallbackLog) -> int:
    payload = _normalized_mapping(entry.result_payload)
    try:
        return int(payload.get("failure_count") or 0)
    except (TypeError, ValueError):
        return 0


def _should_dead_letter_callback(
    *,
    failure_count: int,
    status_code: int | None,
) -> bool:
    if status_code in _NON_RETRYABLE_STATUS_CODES:
        return True
    return failure_count >= _CALLBACK_MAX_ATTEMPTS


def _dead_letter_error(entry: ProviderCallbackLog) -> CallbackProcessingError:
    payload = _normalized_mapping(entry.result_payload)
    status_code = payload.get("terminal_status_code") or payload.get("last_status_code") or 422
    try:
        normalized_status = int(status_code)
    except (TypeError, ValueError):
        normalized_status = 422
    detail = _normalized_text(payload.get("terminal_detail")) or entry.error_message or "callback_dead_lettered"
    return CallbackProcessingError(
        entry.error_message or "callback_dead_lettered",
        status_code=normalized_status,
        detail=detail,
        result_payload=payload,
    )


def _resolve_processor(entry: ProviderCallbackLog) -> CallbackProcessor:
    normalized_key = (entry.provider.strip().lower(), entry.route_key.strip())
    processor = _PROCESSOR_REGISTRY.get(normalized_key)
    if processor is None:
        raise CallbackProcessingError(
            f"unsupported_provider_callback_route:{entry.provider}:{entry.route_key}",
            status_code=422,
            detail=f"unsupported_provider_callback_route:{entry.provider}:{entry.route_key}",
        )
    return processor


async def _reload_callback_entry(
    session: AsyncSession,
    callback_log_id: UUID,
    fallback: ProviderCallbackLog,
) -> ProviderCallbackLog:
    refreshed = await session.get(ProviderCallbackLog, callback_log_id)
    return refreshed or fallback


async def process_callback_entry(
    session: AsyncSession,
    entry: ProviderCallbackLog,
) -> CallbackProcessingResult:
    if entry.status == "processed":
        return _existing_result(entry)
    if entry.status == "dead_lettered":
        raise _dead_letter_error(entry)

    processor = _resolve_processor(entry)
    try:
        result = await processor(session, entry)
    except CallbackProcessingError as exc:
        if hasattr(session, "rollback"):
            await session.rollback()
        failed_entry = await _reload_callback_entry(session, entry.id, entry)
        failure_count = _callback_failure_count(failed_entry) + 1
        terminal = _should_dead_letter_callback(
            failure_count=failure_count,
            status_code=exc.status_code,
        )
        await mark_failed(
            session,
            failed_entry,
            error_message=exc.error_message,
            result_payload={
                **exc.result_payload,
                "terminal_detail": exc.detail,
            },
            status_code=exc.status_code,
            terminal=terminal,
            failure_count=failure_count,
        )
        await session.commit()
        raise
    except Exception as exc:
        if hasattr(session, "rollback"):
            await session.rollback()
        failed_entry = await _reload_callback_entry(session, entry.id, entry)
        failure_count = _callback_failure_count(failed_entry) + 1
        terminal = _should_dead_letter_callback(
            failure_count=failure_count,
            status_code=None,
        )
        await mark_failed(
            session,
            failed_entry,
            error_message=str(exc),
            terminal=terminal,
            failure_count=failure_count,
        )
        await session.commit()
        raise

    processed_entry = await _reload_callback_entry(session, entry.id, entry)
    await mark_processed(session, processed_entry, result_payload=result.response_payload)
    await session.commit()
    return result


async def _load_callback_entry_for_update(
    session: AsyncSession,
    callback_log_id: UUID,
) -> ProviderCallbackLog | None:
    result = await session.execute(
        select(ProviderCallbackLog)
        .where(ProviderCallbackLog.id == callback_log_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def process_callback_entry_synchronously(
    session: AsyncSession,
    entry: ProviderCallbackLog,
) -> CallbackProcessingResult:
    locked_entry = await _load_callback_entry_for_update(session, entry.id)
    if locked_entry is None:
        raise CallbackProcessingError(
            "callback_log_not_found",
            status_code=404,
            detail="callback_log_not_found",
        )

    if locked_entry.status == "processed":
        await session.commit()
        return _existing_result(locked_entry)

    if locked_entry.status == "dead_lettered":
        await session.commit()
        raise _dead_letter_error(locked_entry)

    if locked_entry.status == "processing":
        await session.commit()
        raise CallbackProcessingError(
            "callback_processing_in_progress",
            status_code=409,
            detail="callback_processing_in_progress",
        )

    locked_entry.status = "processing"
    locked_entry.processed_at = datetime.now(timezone.utc)
    await session.commit()

    refreshed_entry = await _reload_callback_entry(session, locked_entry.id, locked_entry)
    return await process_callback_entry(session, refreshed_entry)


async def process_callback_batch(
    session: AsyncSession,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    entries = await worker_runtime.claim_provider_callback_logs(
        session,
        limit=limit,
        now=datetime.now(timezone.utc),
        business_resolver=_callback_business_keys,
    )
    processed_count = 0
    failed_count = 0
    dead_lettered_count = 0
    processed_callback_ids: list[str] = []

    for entry in entries:
        try:
            await process_callback_entry(session, entry)
            processed_count += 1
        except Exception:
            failed_count += 1
            refreshed_entry = await _reload_callback_entry(session, entry.id, entry)
            if refreshed_entry.status == "dead_lettered":
                dead_lettered_count += 1
        processed_callback_ids.append(str(entry.id))

    return {
        "claimed_count": len(entries),
        "processed_count": processed_count,
        "failed_count": failed_count,
        "dead_lettered_count": dead_lettered_count,
        "processed_callback_ids": processed_callback_ids,
    }


async def _business_id_for_offer(
    session: AsyncSession,
    offer_id: UUID,
) -> UUID | None:
    offer = await session.get(CoverageOffer, offer_id)
    if offer is None:
        return None
    coverage_case = await session.get(CoverageCase, offer.coverage_case_id)
    if coverage_case is None:
        return None
    shift = await session.get(Shift, coverage_case.shift_id)
    return shift.business_id if shift is not None else None


async def _business_id_for_shift(
    session: AsyncSession,
    shift_id: UUID,
) -> UUID | None:
    shift = await session.get(Shift, shift_id)
    return shift.business_id if shift is not None else None


async def _business_id_for_location(
    session: AsyncSession,
    location_id: UUID,
) -> UUID | None:
    location = await session.get(Location, location_id)
    return location.business_id if location is not None else None


async def _business_id_for_twilio_status_entry(
    session: AsyncSession,
    entry: ProviderCallbackLog,
) -> UUID | None:
    payload = _normalized_mapping(entry.payload)
    message_sid = (
        _normalized_text(payload.get("MessageSid"))
        or _normalized_text(payload.get("SmsSid"))
        or _normalized_text(entry.provider_event_id)
    )
    if message_sid is None:
        return None
    result = await session.execute(
        select(Shift.business_id)
        .join(CoverageCase, CoverageCase.shift_id == Shift.id)
        .join(CoverageOffer, CoverageOffer.coverage_case_id == CoverageCase.id)
        .where(CoverageOffer.provider_message_id == message_sid)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _business_id_for_twilio_inbound_entry(
    session: AsyncSession,
    entry: ProviderCallbackLog,
) -> UUID | None:
    payload = _normalized_mapping(entry.payload)
    from_phone = _normalized_text(payload.get("From"))
    if from_phone is None:
        return None
    context = await delivery.find_latest_actionable_offer_for_phone(session, from_phone)
    return context.business_id if context is not None else None


async def _business_id_for_retell_entry(
    session: AsyncSession,
    entry: ProviderCallbackLog,
) -> UUID | None:
    payload = _normalized_mapping(entry.payload)
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

    business_id = _normalized_uuid(metadata.get("business_id")) or _normalized_uuid(payload.get("business_id"))
    if business_id is not None:
        return business_id

    location_id = _normalized_uuid(metadata.get("location_id")) or _normalized_uuid(payload.get("location_id"))
    if location_id is not None:
        return await _business_id_for_location(session, location_id)

    shift_id = _normalized_uuid(metadata.get("shift_id")) or _normalized_uuid(payload.get("shift_id"))
    if shift_id is not None:
        return await _business_id_for_shift(session, shift_id)

    offer_id = (
        _normalized_uuid(metadata.get("offer_id"))
        or _normalized_uuid(metadata.get("coverage_offer_id"))
        or _normalized_uuid(payload.get("offer_id"))
        or _normalized_uuid(payload.get("coverage_offer_id"))
    )
    if offer_id is not None:
        return await _business_id_for_offer(session, offer_id)

    event = _normalized_text(payload.get("event")) or _normalized_text(entry.event_type) or ""
    if event == "function_call":
        args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
        offer_id = _normalized_uuid(args.get("offer_id")) or _normalized_uuid(args.get("coverage_offer_id"))
        if offer_id is not None:
            return await _business_id_for_offer(session, offer_id)

        shift_id = _normalized_uuid(args.get("shift_id"))
        if shift_id is not None:
            return await _business_id_for_shift(session, shift_id)

        location_id = _normalized_uuid(args.get("location_id"))
        if location_id is not None:
            return await _business_id_for_location(session, location_id)

    provider_event_id = _normalized_text(entry.provider_event_id)
    if provider_event_id is None:
        return None
    result = await session.execute(
        select(RetellConversation.business_id)
        .where(RetellConversation.external_id == provider_event_id)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _callback_business_keys(
    session: AsyncSession,
    entries: list[ProviderCallbackLog],
) -> dict[object, UUID | None]:
    business_keys: dict[object, UUID | None] = {}

    for entry in entries:
        if entry.provider == "twilio" and entry.route_key == "twilio_sms_status":
            business_keys[entry.id] = await _business_id_for_twilio_status_entry(session, entry)
            continue
        if entry.provider == "twilio" and entry.route_key == "twilio_sms_inbound":
            business_keys[entry.id] = await _business_id_for_twilio_inbound_entry(session, entry)
            continue
        if entry.provider == "retell" and entry.route_key == "retell_webhook":
            business_keys[entry.id] = await _business_id_for_retell_entry(session, entry)
            continue
        business_keys[entry.id] = None

    return business_keys


@callback_processor("twilio", "twilio_sms_status")
async def _process_twilio_sms_status(
    session: AsyncSession,
    entry: ProviderCallbackLog,
) -> CallbackProcessingResult:
    payload = _normalized_mapping(entry.payload)
    message_sid = (
        _normalized_text(payload.get("MessageSid"))
        or _normalized_text(payload.get("SmsSid"))
        or _normalized_text(entry.provider_event_id)
    )
    message_status = _normalized_text(payload.get("MessageStatus")) or _normalized_text(entry.event_type)
    if message_sid is None or message_status is None:
        raise CallbackProcessingError(
            "invalid_twilio_status_callback",
            status_code=400,
            detail="invalid_twilio_status_callback",
        )

    result = await delivery.apply_twilio_status_callback(
        session,
        message_sid=message_sid,
        message_status=message_status,
        error_code=_normalized_text(payload.get("ErrorCode")),
        error_message=_normalized_text(payload.get("ErrorMessage")),
        raw_payload=payload,
    )
    return CallbackProcessingResult(
        callback_log_id=entry.id,
        response_kind="empty",
        response_payload=result,
    )


@callback_processor("twilio", "twilio_sms_inbound")
async def _process_twilio_sms_inbound(
    session: AsyncSession,
    entry: ProviderCallbackLog,
) -> CallbackProcessingResult:
    payload = _normalized_mapping(entry.payload)
    from_phone = _normalized_text(payload.get("From"))
    body = _normalized_text(payload.get("Body"))
    if from_phone is None or body is None:
        raise CallbackProcessingError(
            "invalid_twilio_inbound_callback",
            status_code=400,
            detail="invalid_twilio_inbound_callback",
        )

    reply = await delivery.handle_twilio_inbound_reply(
        session,
        from_phone=from_phone,
        body=body,
        raw_payload=payload,
    )
    return CallbackProcessingResult(
        callback_log_id=entry.id,
        response_kind="twiml",
        response_payload={"reply_message": reply},
        response_text=reply,
    )


@callback_processor("retell", "retell_webhook")
async def _process_retell_webhook(
    session: AsyncSession,
    entry: ProviderCallbackLog,
) -> CallbackProcessingResult:
    payload = _normalized_mapping(entry.payload)
    event = _normalized_text(payload.get("event")) or _normalized_text(entry.event_type)
    if event is None:
        raise CallbackProcessingError(
            "missing_retell_event",
            status_code=400,
            detail="missing_retell_event",
        )

    try:
        if event in {
            "call_started",
            "call_ended",
            "call_analyzed",
            "chat_started",
            "chat_ended",
            "chat_analyzed",
        }:
            conversation = await retell_workflow.persist_payload(session, payload)
            response_payload = {
                "status": "ok",
                "conversation_id": str(conversation.id) if conversation is not None else None,
            }
            return CallbackProcessingResult(
                callback_log_id=entry.id,
                response_kind="json",
                response_payload=response_payload,
            )

        if event == "function_call":
            result = await retell_workflow.dispatch_function_call(
                session,
                _normalized_text(payload.get("name")) or "",
                payload.get("args") if isinstance(payload.get("args"), dict) else {},
            )
            return CallbackProcessingResult(
                callback_log_id=entry.id,
                response_kind="json",
                response_payload=_normalized_mapping(result),
            )

        conversation = await retell_workflow.persist_payload(session, payload)
        response_payload = {
            "status": "ignored",
            "conversation_id": str(conversation.id) if conversation is not None else None,
            "event": event,
        }
        return CallbackProcessingResult(
            callback_log_id=entry.id,
            response_kind="json",
            response_payload=response_payload,
        )
    except LookupError as exc:
        raise CallbackProcessingError(
            str(exc),
            status_code=404,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise CallbackProcessingError(
            str(exc),
            status_code=400,
            detail=str(exc),
        ) from exc
