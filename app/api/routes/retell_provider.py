from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import SessionDep
from app.config import settings
from app.services import provider_callbacks, rate_limit, retell_workflow

router = APIRouter(prefix="/providers/retell", tags=["retell"])


def _validate_signature(raw_body: bytes, signature: str | None) -> bool:
    if not settings.retell_api_key:
        return False
    normalized_signature = (signature or "").strip()
    if not normalized_signature:
        return False
    try:
        from retell.lib import verify
    except ImportError:
        return False
    try:
        return bool(verify(raw_body.decode("utf-8"), settings.retell_api_key, normalized_signature))
    except Exception:
        return False


def _request_headers(request: Request) -> dict[str, str]:
    return {
        key: value
        for key, value in request.headers.items()
    }


def _provider_event_id(body: dict) -> str | None:
    event = str(body.get("event") or "").strip().lower()
    if event.startswith("call_"):
        candidate = body.get("call") or body.get("call_detail") or body.get("data") or {}
        if isinstance(candidate, dict):
            value = candidate.get("call_id") or candidate.get("id")
            if value not in (None, ""):
                return str(value).strip()
    if event.startswith("chat_"):
        candidate = body.get("chat") or body.get("chat_detail") or body.get("data") or {}
        if isinstance(candidate, dict):
            value = candidate.get("chat_id") or candidate.get("id")
            if value not in (None, ""):
                return str(value).strip()
    return None


@router.post("/webhook")
async def retell_webhook(request: Request, session: SessionDep):
    client_ip = request.client.host if request.client is not None else "unknown"
    await rate_limit.assert_within_limit(
        "retell_webhook",
        client_ip,
        limit=settings.retell_webhook_limit_per_minute,
        window_seconds=60,
        detail="Too many Retell webhook requests.",
    )
    raw_body = await request.body()
    if not _validate_signature(raw_body, request.headers.get("X-Retell-Signature")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid_webhook_signature")
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_json_payload") from exc
    event = str(body.get("event") or "").strip()
    callback_entry, created = await provider_callbacks.record_raw_callback(
        session,
        provider="retell",
        route_key="retell_webhook",
        headers=_request_headers(request),
        payload=body,
        event_type=event,
        provider_event_id=_provider_event_id(body),
    )
    await session.commit()
    if not created and callback_entry.status == "processed":
        previous = callback_entry.result_payload or {}
        return previous or {"status": "duplicate", "event": event}
    try:
        if event in {"call_started", "call_ended", "call_analyzed", "chat_started", "chat_ended", "chat_analyzed"}:
            conversation = await retell_workflow.persist_payload(session, body)
            response_payload = {
                "status": "ok",
                "conversation_id": str(conversation.id) if conversation is not None else None,
            }
            await session.commit()
            await provider_callbacks.mark_processed(session, callback_entry, result_payload=response_payload)
            await session.commit()
            return response_payload
        if event == "function_call":
            result = await retell_workflow.dispatch_function_call(
                session,
                str(body.get("name") or "").strip(),
                body.get("args") or {},
            )
            await session.commit()
            await provider_callbacks.mark_processed(session, callback_entry, result_payload=result)
            await session.commit()
            return result
        conversation = await retell_workflow.persist_payload(session, body)
        response_payload = {
            "status": "ignored",
            "conversation_id": str(conversation.id) if conversation is not None else None,
            "event": event,
        }
        await session.commit()
        await provider_callbacks.mark_processed(session, callback_entry, result_payload=response_payload)
        await session.commit()
        return response_payload
    except LookupError as exc:
        if hasattr(session, "rollback"):
            await session.rollback()
        await provider_callbacks.mark_failed(session, callback_entry, error_message=str(exc))
        await session.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        if hasattr(session, "rollback"):
            await session.rollback()
        await provider_callbacks.mark_failed(session, callback_entry, error_message=str(exc))
        await session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        if hasattr(session, "rollback"):
            await session.rollback()
        await provider_callbacks.mark_failed(session, callback_entry, error_message=str(exc))
        await session.commit()
        raise
