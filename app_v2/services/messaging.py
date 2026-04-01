from __future__ import annotations

from typing import Optional

import httpx

from app_v2.config import v2_settings

_twilio_client = None


def _get_twilio():
    global _twilio_client
    if _twilio_client is None:
        try:
            from twilio.rest import Client
        except ImportError as exc:
            raise RuntimeError("twilio package not installed. Add 'twilio' to requirements.txt.") from exc
        _twilio_client = Client(
            v2_settings.twilio_account_sid,
            v2_settings.twilio_auth_token,
        )
    return _twilio_client


def send_sms(
    *,
    to: str,
    body: str,
    status_callback: str | None = None,
) -> dict:
    if not v2_settings.twilio_account_sid or not v2_settings.twilio_auth_token:
        raise RuntimeError("Twilio SMS is not configured. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN.")
    if not v2_settings.backfill_phone_number:
        raise RuntimeError("BACKFILL_PHONE_NUMBER is required for outbound coverage SMS.")

    client = _get_twilio()
    message = client.messages.create(
        to=to,
        from_=v2_settings.backfill_phone_number,
        body=body,
        status_callback=status_callback,
    )
    return {
        "sid": getattr(message, "sid", None),
        "status": getattr(message, "status", None),
        "to": getattr(message, "to", to),
        "from": getattr(message, "from_", v2_settings.backfill_phone_number),
    }


def validate_twilio_signature(url: str, params: dict, signature: Optional[str]) -> bool:
    if not v2_settings.twilio_auth_token:
        return True
    try:
        from twilio.request_validator import RequestValidator
    except ImportError:
        return False

    validator = RequestValidator(v2_settings.twilio_auth_token)
    return validator.validate(url, params, signature or "")


def send_email(
    *,
    to: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> str | None:
    if not v2_settings.sendgrid_api_key or not v2_settings.backfill_email_from:
        raise RuntimeError(
            "Twilio SendGrid email is not configured. Set SENDGRID_API_KEY and BACKFILL_EMAIL_FROM."
        )

    content = [{"type": "text/plain", "value": text_body}]
    if html_body:
        content.append({"type": "text/html", "value": html_body})

    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {
            "email": v2_settings.backfill_email_from,
            "name": v2_settings.backfill_email_from_name or "Backfill",
        },
        "subject": subject,
        "content": content,
    }

    response = httpx.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={
            "Authorization": f"Bearer {v2_settings.sendgrid_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15.0,
    )
    response.raise_for_status()
    return response.headers.get("x-message-id")
