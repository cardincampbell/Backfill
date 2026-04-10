from __future__ import annotations

from fastapi import APIRouter, Form, Request, Response, status

from app.api.deps import SessionDep
from app.services import delivery, messaging, provider_callbacks

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

    callback_entry, created = await provider_callbacks.record_raw_callback(
        session,
        provider="twilio",
        route_key="twilio_sms_status",
        headers=_request_headers(request),
        payload=form_params,
        event_type=MessageStatus,
        provider_event_id=MessageSid,
    )
    await session.commit()
    if not created and callback_entry.status == "processed":
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    try:
        result = await delivery.apply_twilio_status_callback(
            session,
            message_sid=MessageSid,
            message_status=MessageStatus,
            error_code=ErrorCode,
            error_message=ErrorMessage,
            raw_payload=form_params,
        )
    except Exception as exc:
        if hasattr(session, "rollback"):
            await session.rollback()
        await provider_callbacks.mark_failed(
            session,
            callback_entry,
            error_message=str(exc),
        )
        await session.commit()
        raise
    await provider_callbacks.mark_processed(session, callback_entry, result_payload=result)
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

    callback_entry, created = await provider_callbacks.record_raw_callback(
        session,
        provider="twilio",
        route_key="twilio_sms_inbound",
        headers=_request_headers(request),
        payload=form_params,
        event_type="sms_inbound",
        provider_event_id=str(form_params.get("SmsSid") or form_params.get("MessageSid") or "").strip() or None,
    )
    await session.commit()
    if not created and callback_entry.status == "processed":
        previous_reply = str((callback_entry.result_payload or {}).get("reply_message") or "").strip()
        return _twiml(previous_reply or "Thanks, we already received that response.")

    try:
        reply = await delivery.handle_twilio_inbound_reply(
            session,
            from_phone=From.strip(),
            body=Body,
            raw_payload=form_params,
        )
    except Exception as exc:
        if hasattr(session, "rollback"):
            await session.rollback()
        await provider_callbacks.mark_failed(
            session,
            callback_entry,
            error_message=str(exc),
        )
        await session.commit()
        raise
    await provider_callbacks.mark_processed(
        session,
        callback_entry,
        result_payload={"reply_message": reply},
    )
    await session.commit()
    return _twiml(reply)
