"""
SMS delivery helpers.

Backfill uses SMS as the written control plane for shift offers because it
captures the details and provides a fast YES/NO response path. For urgent
fills, voice can be layered on top as an interruption channel.
"""
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

_twilio_client = None


def _get_twilio():
    global _twilio_client
    if _twilio_client is None:
        try:
            from twilio.rest import Client
        except ImportError as exc:
            raise RuntimeError(
                "twilio package not installed. Add 'twilio' to requirements.txt."
            ) from exc
        _twilio_client = Client(
            settings.twilio_account_sid,
            settings.twilio_auth_token,
        )
    return _twilio_client


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


def send_sms(
    to: str,
    body: str,
    metadata: Optional[dict] = None,
    dynamic_variables: Optional[dict] = None,
) -> Optional[str]:
    if settings.retell_sms_enabled:
        from app.services import retell as retell_svc

        return retell_svc.create_sms_chat(
            to_number=to,
            body=body,
            metadata=metadata,
            dynamic_variables=dynamic_variables,
        )

    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        logger.warning(
            "SMS not sent: TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN not configured. "
            "Set these env vars (and BACKFILL_PHONE_NUMBER) to enable real SMS. "
            "Would have sent to=%s body=%r",
            to,
            body,
        )
        return None

    client = _get_twilio()
    message = client.messages.create(
        to=to,
        from_=settings.backfill_phone_number,
        body=body,
    )
    return message.sid
