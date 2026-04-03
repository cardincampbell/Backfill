from __future__ import annotations

from typing import Optional

import httpx

from app.config import settings

_twilio_client = None


def _get_twilio():
    global _twilio_client
    if _twilio_client is None:
        try:
            from twilio.rest import Client
        except ImportError as exc:
            raise RuntimeError("twilio package not installed. Add 'twilio' to requirements.txt.") from exc
        _twilio_client = Client(
            settings.twilio_account_sid,
            settings.twilio_auth_token,
        )
    return _twilio_client


def send_sms(
    *,
    to: str,
    body: str,
    status_callback: str | None = None,
) -> dict:
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise RuntimeError("Twilio SMS is not configured. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN.")
    if not settings.backfill_phone_number:
        raise RuntimeError("BACKFILL_PHONE_NUMBER is required for outbound coverage SMS.")

    client = _get_twilio()
    message = client.messages.create(
        to=to,
        from_=settings.backfill_phone_number,
        body=body,
        status_callback=status_callback,
    )
    return {
        "sid": getattr(message, "sid", None),
        "status": getattr(message, "status", None),
        "to": getattr(message, "to", to),
        "from": getattr(message, "from_", settings.backfill_phone_number),
    }


def send_sms_verification(
    to: str,
    *,
    locale: str = "en",
) -> dict:
    if (
        not settings.twilio_account_sid
        or not settings.twilio_auth_token
        or not settings.twilio_verify_service_sid
    ):
        raise RuntimeError(
            "Twilio Verify is not configured. Set TWILIO_ACCOUNT_SID, "
            "TWILIO_AUTH_TOKEN, and TWILIO_VERIFY_SERVICE_SID."
        )

    client = _get_twilio()
    verification = client.verify.v2.services(
        settings.twilio_verify_service_sid
    ).verifications.create(
        to=to,
        channel="sms",
        locale=locale,
    )
    return {
        "sid": getattr(verification, "sid", None),
        "status": getattr(verification, "status", None),
        "channel": getattr(verification, "channel", "sms"),
        "to": getattr(verification, "to", to),
    }


def check_sms_verification(
    to: str,
    code: str,
) -> dict:
    if (
        not settings.twilio_account_sid
        or not settings.twilio_auth_token
        or not settings.twilio_verify_service_sid
    ):
        raise RuntimeError(
            "Twilio Verify is not configured. Set TWILIO_ACCOUNT_SID, "
            "TWILIO_AUTH_TOKEN, and TWILIO_VERIFY_SERVICE_SID."
        )

    client = _get_twilio()
    verification_check = client.verify.v2.services(
        settings.twilio_verify_service_sid
    ).verification_checks.create(
        to=to,
        code=code,
    )
    return {
        "sid": getattr(verification_check, "sid", None),
        "status": getattr(verification_check, "status", None),
        "valid": getattr(verification_check, "valid", None),
        "to": getattr(verification_check, "to", to),
    }


def validate_twilio_signature(url: str, params: dict, signature: Optional[str]) -> bool:
    if not settings.twilio_auth_token:
        return True
    try:
        from twilio.request_validator import RequestValidator
    except ImportError:
        return False

    validator = RequestValidator(settings.twilio_auth_token)
    return validator.validate(url, params, signature or "")


def send_email(
    *,
    to: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> str | None:
    if not settings.sendgrid_api_key or not settings.backfill_email_from:
        raise RuntimeError(
            "Twilio SendGrid email is not configured. Set SENDGRID_API_KEY and BACKFILL_EMAIL_FROM."
        )

    content = [{"type": "text/plain", "value": text_body}]
    if html_body:
        content.append({"type": "text/html", "value": html_body})

    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {
            "email": settings.backfill_email_from,
            "name": settings.backfill_email_from_name or "Backfill",
        },
        "subject": subject,
        "content": content,
    }

    response = httpx.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={
            "Authorization": f"Bearer {settings.sendgrid_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15.0,
    )
    response.raise_for_status()
    return response.headers.get("x-message-id")
