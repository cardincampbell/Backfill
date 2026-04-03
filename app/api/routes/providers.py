from __future__ import annotations

from fastapi import APIRouter, Form, Request, Response, status

from app.api.deps import SessionDep
from app.services import delivery, messaging

router = APIRouter(prefix="/providers/twilio", tags=["providers"])


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

    await delivery.apply_twilio_status_callback(
        session,
        message_sid=MessageSid,
        message_status=MessageStatus,
        error_code=ErrorCode,
        error_message=ErrorMessage,
        raw_payload=form_params,
    )
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

    reply = await delivery.handle_twilio_inbound_reply(
        session,
        from_phone=From.strip(),
        body=Body,
        raw_payload=form_params,
    )
    return _twiml(reply)
