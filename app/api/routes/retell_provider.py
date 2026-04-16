from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import SessionDep
from app.config import settings
from app.services import provider_callbacks, rate_limit

router = APIRouter(prefix="/providers/retell", tags=["retell"])
public_router = APIRouter(tags=["retell"])


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
@public_router.post("/webhooks/retell")
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
    callback_entry, _created = await provider_callbacks.record_raw_callback(
        session,
        provider="retell",
        route_key="retell_webhook",
        headers=_request_headers(request),
        payload=body,
        event_type=event,
        provider_event_id=_provider_event_id(body),
    )
    await session.commit()
    if event == "function_call":
        try:
            result = await provider_callbacks.process_callback_entry_synchronously(session, callback_entry)
        except provider_callbacks.CallbackProcessingError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        return result.response_payload or {"status": "duplicate", "event": event}
    return {
        "status": "received",
        "event": event,
        "callback_log_id": str(callback_entry.id),
    }
