from __future__ import annotations

from fastapi import APIRouter, Form, Request, Response, status

from app.api.deps import SessionDep
from app.services import messaging, provider_callbacks

router = APIRouter(prefix="/providers/twilio", tags=["providers"])
_INBOUND_ACK_MESSAGE = "Thanks, we received your response."


def _twiml(message: str) -> Response:
    escaped = (
        message.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    body = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped}</Message></Response>'
    return Response(content=body, media_type="application/xml")


def _validate_signature(request: Request, params: dict) -> bool:
    signature = request.headers.get("X-Twilio-Signature")
    return messaging.validate_twilio_signature(str(request.url), params, signature)


def _request_headers(request: Request) -> dict[str, str]:
    return {
        key: value
        for key, value in request.headers.items()
    }


@router.post("/sms/status", status_code=status.HTTP_204_NO_CONTENT)
async def twilio_sms_status_callback(
    request: Request,
    session: SessionDep,
    MessageSid: str = Form(...),
    MessageStatus: str = Form(...),
    ErrorCode: str | None = Form(default=None),
    ErrorMessage: str | None = Form(default=None),
):
    form = await request.form()
    form_params = {
        key: value if isinstance(value, str) else str(value)
        for key, value in form.multi_items()
    }
    if not _validate_signature(request, form_params):
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    callback_entry, _created = await provider_callbacks.record_raw_callback(
        session,
        provider="twilio",
        route_key="twilio_sms_status",
        headers=_request_headers(request),
        payload=form_params,
        event_type=MessageStatus,
        provider_event_id=MessageSid,
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sms/inbound")
async def twilio_sms_inbound(
    request: Request,
    session: SessionDep,
    From: str = Form(...),
    Body: str = Form(...),
):
    form = await request.form()
    form_params = {
        key: value if isinstance(value, str) else str(value)
        for key, value in form.multi_items()
    }
    if not _validate_signature(request, form_params):
        return Response(content="Forbidden", status_code=status.HTTP_403_FORBIDDEN)

    callback_entry, _created = await provider_callbacks.record_raw_callback(
        session,
        provider="twilio",
        route_key="twilio_sms_inbound",
        headers=_request_headers(request),
        payload=form_params,
        event_type="sms_inbound",
        provider_event_id=str(form_params.get("SmsSid") or form_params.get("MessageSid") or "").strip() or None,
    )
    result = await provider_callbacks.process_callback_entry_synchronously(
        session,
        callback_entry,
    )
    if result.response_kind == "twiml":
        return _twiml(result.response_text or _INBOUND_ACK_MESSAGE)
    return _twiml(_INBOUND_ACK_MESSAGE)
