from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.communications import CommunicationSuppression
from app.models.workforce import Employee
from app.services import workforce

GLOBAL_SCOPE = "global"
EMAIL_CHANNEL = "email"
SMS_CHANNEL = "sms"
_EMAIL_TOKEN_PREFIX = "bfv1unsub"
_SUPPORTED_CHANNELS = {EMAIL_CHANNEL, SMS_CHANNEL}
_SMS_STOP_KEYWORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}
_SMS_START_KEYWORDS = {"START", "UNSTOP"}
_SMS_HELP_KEYWORDS = {"HELP", "INFO"}


@dataclass
class SMSCommandResult:
    handled: bool
    response_text: str | None = None
    action: str | None = None
    created: bool = False
    cleared: bool = False


def _normalized_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, value in metadata.items():
        if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
            normalized[str(key)] = value
        else:
            normalized[str(key)] = str(value)
    return normalized


def _sign_token_payload(payload: str) -> str:
    return hmac.new(
        settings.public_link_signing_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _encode_token_data(data: dict[str, Any]) -> str:
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _decode_token_data(encoded: str) -> dict[str, Any] | None:
    padding = "=" * (-len(encoded) % 4)
    try:
        raw = base64.urlsafe_b64decode(f"{encoded}{padding}".encode("utf-8"))
        decoded = json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def normalize_destination(channel: str, destination: str | None) -> str | None:
    normalized_channel = str(channel or "").strip().lower()
    raw = str(destination or "").strip()
    if not raw:
        return None
    if normalized_channel == EMAIL_CHANNEL:
        return raw.lower()
    if normalized_channel == SMS_CHANNEL:
        digits = re.sub(r"\D", "", raw)
        if raw.startswith("+") and 10 <= len(digits) <= 15:
            return f"+{digits}"
        if len(digits) == 10:
            return f"+1{digits}"
        if len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        return raw
    return raw


def build_email_unsubscribe_token(
    *,
    email: str,
    scope: str = GLOBAL_SCOPE,
) -> str:
    normalized_email = normalize_destination(EMAIL_CHANNEL, email)
    if normalized_email is None:
        raise ValueError("unsubscribe_email_required")
    encoded = _encode_token_data(
        {
            "v": 1,
            "channel": EMAIL_CHANNEL,
            "destination": normalized_email,
            "scope": scope or GLOBAL_SCOPE,
        }
    )
    signature = _sign_token_payload(encoded)
    return f"{_EMAIL_TOKEN_PREFIX}.{encoded}.{signature}"


def parse_email_unsubscribe_token(raw_token: str) -> dict[str, str] | None:
    token = str(raw_token or "").strip()
    prefix = f"{_EMAIL_TOKEN_PREFIX}."
    if not token.startswith(prefix):
        return None
    encoded_and_signature = token[len(prefix) :]
    try:
        encoded, signature = encoded_and_signature.rsplit(".", 1)
    except ValueError:
        return None
    expected_signature = _sign_token_payload(encoded)
    if not hmac.compare_digest(signature, expected_signature):
        return None
    decoded = _decode_token_data(encoded)
    if decoded is None:
        return None
    channel = str(decoded.get("channel") or "").strip().lower()
    destination = normalize_destination(channel, str(decoded.get("destination") or ""))
    scope = str(decoded.get("scope") or GLOBAL_SCOPE).strip() or GLOBAL_SCOPE
    version = int(decoded.get("v") or 0)
    if version != 1 or channel != EMAIL_CHANNEL or destination is None:
        return None
    return {
        "channel": channel,
        "destination": destination,
        "scope": scope,
    }


def build_email_unsubscribe_url(
    *,
    email: str,
    scope: str = GLOBAL_SCOPE,
) -> str:
    token = build_email_unsubscribe_token(email=email, scope=scope)
    return (
        f"{settings.api_base_url}{settings.api_prefix}"
        f"/communications/unsubscribe?token={quote(token)}"
    )


def build_email_list_unsubscribe_headers(
    *,
    email: str,
    scope: str = GLOBAL_SCOPE,
) -> dict[str, str]:
    unsubscribe_url = build_email_unsubscribe_url(email=email, scope=scope)
    return {
        "List-Unsubscribe": f"<{unsubscribe_url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


async def get_active_suppression(
    session: AsyncSession,
    *,
    channel: str,
    destination: str | None,
    scope: str = GLOBAL_SCOPE,
) -> CommunicationSuppression | None:
    normalized_channel = str(channel or "").strip().lower()
    normalized_destination = normalize_destination(normalized_channel, destination)
    if normalized_channel not in _SUPPORTED_CHANNELS or normalized_destination is None:
        return None
    return await session.scalar(
        select(CommunicationSuppression)
        .where(
            CommunicationSuppression.channel == normalized_channel,
            CommunicationSuppression.destination == normalized_destination,
            CommunicationSuppression.scope == (scope or GLOBAL_SCOPE),
            CommunicationSuppression.revoked_at.is_(None),
        )
        .order_by(CommunicationSuppression.suppressed_at.desc())
        .limit(1)
    )


async def is_destination_suppressed(
    session: AsyncSession,
    *,
    channel: str,
    destination: str | None,
    scope: str = GLOBAL_SCOPE,
) -> bool:
    return (
        await get_active_suppression(
            session,
            channel=channel,
            destination=destination,
            scope=scope,
        )
    ) is not None


def _serialized_notification_preferences(preferences: dict[str, object]) -> dict[str, object]:
    return {
        "schedule_publish_email_enabled": bool(preferences["schedule_publish_email_enabled"]),
        "schedule_publish_sms_enabled": bool(preferences["schedule_publish_sms_enabled"]),
        "email_opted_out_at": (
            preferences["email_opted_out_at"].isoformat()
            if isinstance(preferences.get("email_opted_out_at"), datetime)
            else None
        ),
        "sms_opted_out_at": (
            preferences["sms_opted_out_at"].isoformat()
            if isinstance(preferences.get("sms_opted_out_at"), datetime)
            else None
        ),
        "email_opt_out_reason": str(preferences.get("email_opt_out_reason") or "").strip() or None,
        "sms_opt_out_reason": str(preferences.get("sms_opt_out_reason") or "").strip() or None,
    }


async def _matching_employees(
    session: AsyncSession,
    *,
    channel: str,
    destination: str,
) -> list[Employee]:
    if channel == EMAIL_CHANNEL:
        result = await session.execute(
            select(Employee).where(func.lower(Employee.email) == destination.lower())
        )
        return list(result.scalars().all())
    if channel == SMS_CHANNEL:
        result = await session.execute(
            select(Employee).where(Employee.phone_e164 == destination)
        )
        return list(result.scalars().all())
    return []


async def _sync_employee_notification_preferences(
    session: AsyncSession,
    *,
    channel: str,
    destination: str,
    suppressed: bool,
    occurred_at: datetime,
    reason_code: str | None,
) -> None:
    employees = await _matching_employees(session, channel=channel, destination=destination)
    for employee in employees:
        preferences = workforce.normalized_employee_notification_preferences(employee.employee_metadata)
        if channel == EMAIL_CHANNEL:
            preferences["schedule_publish_email_enabled"] = False if suppressed else True
            preferences["email_opted_out_at"] = occurred_at if suppressed else None
            preferences["email_opt_out_reason"] = reason_code if suppressed else None
        elif channel == SMS_CHANNEL:
            preferences["schedule_publish_sms_enabled"] = False if suppressed else True
            preferences["sms_opted_out_at"] = occurred_at if suppressed else None
            preferences["sms_opt_out_reason"] = reason_code if suppressed else None
        employee.employee_metadata = {
            **(employee.employee_metadata or {}),
            "notification_preferences": _serialized_notification_preferences(preferences),
        }
    await session.flush()


async def suppress_destination(
    session: AsyncSession,
    *,
    channel: str,
    destination: str,
    scope: str = GLOBAL_SCOPE,
    source: str,
    reason_code: str,
    metadata: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> tuple[CommunicationSuppression, bool]:
    normalized_channel = str(channel or "").strip().lower()
    normalized_destination = normalize_destination(normalized_channel, destination)
    if normalized_channel not in _SUPPORTED_CHANNELS or normalized_destination is None:
        raise ValueError("unsupported_suppression_destination")

    existing = await get_active_suppression(
        session,
        channel=normalized_channel,
        destination=normalized_destination,
        scope=scope,
    )
    if existing is not None:
        return existing, False

    reference_time = occurred_at or datetime.now(timezone.utc)
    suppression = CommunicationSuppression(
        channel=normalized_channel,
        destination=normalized_destination,
        scope=scope or GLOBAL_SCOPE,
        source=source,
        reason_code=reason_code,
        suppressed_at=reference_time,
        revoked_at=None,
        suppression_metadata=_normalized_metadata(metadata),
    )
    session.add(suppression)
    await session.flush()
    await _sync_employee_notification_preferences(
        session,
        channel=normalized_channel,
        destination=normalized_destination,
        suppressed=True,
        occurred_at=reference_time,
        reason_code=reason_code,
    )
    return suppression, True


async def clear_destination_suppression(
    session: AsyncSession,
    *,
    channel: str,
    destination: str,
    scope: str = GLOBAL_SCOPE,
    source: str,
    reason_code: str | None = None,
    metadata: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> tuple[CommunicationSuppression | None, bool]:
    normalized_channel = str(channel or "").strip().lower()
    normalized_destination = normalize_destination(normalized_channel, destination)
    if normalized_channel not in _SUPPORTED_CHANNELS or normalized_destination is None:
        raise ValueError("unsupported_suppression_destination")

    suppression = await get_active_suppression(
        session,
        channel=normalized_channel,
        destination=normalized_destination,
        scope=scope,
    )
    if suppression is None:
        return None, False

    reference_time = occurred_at or datetime.now(timezone.utc)
    suppression.revoked_at = reference_time
    suppression.suppression_metadata = {
        **(suppression.suppression_metadata or {}),
        "revoked_at": reference_time.isoformat(),
        "revoked_source": source,
        "revoked_reason_code": str(reason_code or "").strip() or None,
        "revoked_metadata": _normalized_metadata(metadata),
    }
    await session.flush()
    await _sync_employee_notification_preferences(
        session,
        channel=normalized_channel,
        destination=normalized_destination,
        suppressed=False,
        occurred_at=reference_time,
        reason_code=reason_code,
    )
    return suppression, True


async def suppress_email_from_token(
    session: AsyncSession,
    *,
    token: str,
    source: str = "email_unsubscribe_link",
    reason_code: str = "user_unsubscribe",
    metadata: dict[str, Any] | None = None,
) -> tuple[CommunicationSuppression, bool]:
    parsed = parse_email_unsubscribe_token(token)
    if parsed is None:
        raise ValueError("invalid_unsubscribe_token")
    return await suppress_destination(
        session,
        channel=parsed["channel"],
        destination=parsed["destination"],
        scope=parsed["scope"],
        source=source,
        reason_code=reason_code,
        metadata=metadata,
    )


async def handle_inbound_sms_command(
    session: AsyncSession,
    *,
    from_phone: str,
    body: str,
    raw_payload: dict[str, Any] | None = None,
) -> SMSCommandResult:
    normalized_body = " ".join(str(body or "").strip().upper().split())
    if normalized_body in _SMS_STOP_KEYWORDS:
        _suppression, created = await suppress_destination(
            session,
            channel=SMS_CHANNEL,
            destination=from_phone,
            source="twilio_inbound",
            reason_code="user_unsubscribe",
            metadata={
                "body": body,
                "raw_payload": _normalized_metadata(raw_payload),
            },
        )
        return SMSCommandResult(
            handled=True,
            action="suppressed",
            created=created,
            response_text="Backfill SMS alerts are off for this number. Reply START to opt back in.",
        )

    if normalized_body in _SMS_START_KEYWORDS:
        _suppression, cleared = await clear_destination_suppression(
            session,
            channel=SMS_CHANNEL,
            destination=from_phone,
            source="twilio_inbound",
            reason_code="user_resubscribe",
            metadata={
                "body": body,
                "raw_payload": _normalized_metadata(raw_payload),
            },
        )
        return SMSCommandResult(
            handled=True,
            action="cleared",
            cleared=cleared,
            response_text="Backfill SMS alerts are back on for this number. Reply STOP to opt out again.",
        )

    if normalized_body in _SMS_HELP_KEYWORDS:
        return SMSCommandResult(
            handled=True,
            action="help",
            response_text="Backfill shift alerts. Reply YES to accept, NO to decline, or STOP to opt out.",
        )

    return SMSCommandResult(handled=False)
