from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.common import (
    AuditActorType,
    ChallengeChannel,
    ChallengePurpose,
    ChallengeStatus,
    MembershipRole,
    MembershipStatus,
    SessionRiskLevel,
)
from app.models.identity import Membership, OTPChallenge, Session, User
from app.schemas.auth import OTPChallengeRequest, OTPChallengeVerifyRequest, SessionCreateRequest
from app.services import audit as audit_service
from app.services import messaging, rate_limit


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def generate_trusted_device_id() -> str:
    return secrets.token_urlsafe(32)


@dataclass
class AuthContext:
    user: User
    session: Session
    memberships: list[Membership]


@dataclass
class OTPChallengeRequestResult:
    challenge: OTPChallenge | None
    user_exists: bool
    session: Session | None
    token: str | None
    trusted_device_id: str | None
    onboarding_required: bool
    otp_required: bool


@dataclass
class OTPChallengeVerificationResult:
    challenge: OTPChallenge
    user: User
    session: Session | None
    token: str | None
    trusted_device_id: str | None
    onboarding_required: bool
    step_up_granted: bool


@dataclass
class TrustedDeviceSessionRestoreResult:
    user: User
    session: Session
    token: str
    onboarding_required: bool


def _trim_text(value: object | None) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _merged_client_challenge_metadata(value: object | None, *, locale: str | None = None) -> dict:
    metadata = dict(value) if isinstance(value, dict) else {}
    metadata.pop("device_context", None)
    if locale:
        metadata["locale"] = locale
    return metadata


def normalize_phone(value: object | None) -> Optional[str]:
    text = _trim_text(value)
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if text.startswith("+") and 10 <= len(digits) <= 15:
        return f"+{digits}"
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return None


def onboarding_required_for_user(user: User) -> bool:
    return not bool(user.full_name and user.email and user.onboarding_completed_at)


def maybe_complete_onboarding(user: User, *, completed_at: datetime | None = None) -> bool:
    if user.full_name and user.email and user.onboarding_completed_at is None:
        user.onboarding_completed_at = completed_at or datetime.now(timezone.utc)
    return user.onboarding_completed_at is not None


def _normalize_step_up_purpose(purpose: ChallengePurpose | str) -> str:
    raw = purpose.value if isinstance(purpose, ChallengePurpose) else str(purpose).strip()
    if raw not in {
        ChallengePurpose.step_up_billing.value,
        ChallengePurpose.step_up_export.value,
        ChallengePurpose.step_up_phone_change.value,
    }:
        raise ValueError("invalid_step_up_purpose")
    return raw


def _parse_datetime(value: object | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _recent_step_up_map(session: Session) -> dict[str, str]:
    metadata = session.session_metadata or {}
    raw = metadata.get("step_up_verified_at")
    if not isinstance(raw, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in raw.items()
        if str(key).strip() and str(value).strip()
    }


def has_recent_step_up(
    auth: AuthContext,
    purpose: ChallengePurpose | str,
    *,
    now: datetime | None = None,
) -> bool:
    normalized_purpose = _normalize_step_up_purpose(purpose)
    verified_at = _parse_datetime(_recent_step_up_map(auth.session).get(normalized_purpose))
    if verified_at is None:
        return False
    reference_time = now or datetime.now(timezone.utc)
    return verified_at >= reference_time - timedelta(minutes=settings.step_up_ttl_minutes)


def require_recent_step_up(auth: AuthContext, purpose: ChallengePurpose | str) -> None:
    if not has_recent_step_up(auth, purpose):
        raise PermissionError("step_up_required")


def membership_for_scope(
    auth: AuthContext,
    business_id: UUID,
    *,
    location_id: UUID | None = None,
    allowed_roles: Optional[set[MembershipRole]] = None,
) -> Membership | None:
    business_match: Membership | None = None
    exact_match: Membership | None = None
    for membership in auth.memberships:
        if membership.business_id != business_id:
            continue
        if membership.status != MembershipStatus.active:
            continue
        if allowed_roles is not None and membership.role not in allowed_roles:
            continue
        if location_id is None:
            if business_match is None or business_match.location_id is not None:
                business_match = membership
            continue
        if membership.location_id is None:
            if business_match is None:
                business_match = membership
            continue
        if membership.location_id == location_id:
            exact_match = membership
            break
    return exact_match or business_match


async def _issue_session_record(
    session_db: AsyncSession,
    *,
    user: User,
    device_fingerprint: str | None,
    ip_address: str | None,
    user_agent: str | None,
    risk_level: str,
    elevated_actions: list[str] | None,
    ttl_hours: int,
    session_metadata: dict | None,
) -> tuple[str, Session]:
    raw_token = generate_session_token()
    now = datetime.now(timezone.utc)
    record = Session(
        user_id=user.id,
        token_hash=hash_session_token(raw_token),
        device_fingerprint=device_fingerprint,
        ip_address=ip_address,
        user_agent=user_agent,
        risk_level=SessionRiskLevel(risk_level),
        elevated_actions=elevated_actions or [],
        last_seen_at=now,
        expires_at=now + timedelta(hours=ttl_hours),
        session_metadata=session_metadata or {},
    )
    session_db.add(record)
    user.last_sign_in_at = now
    await session_db.flush()
    return raw_token, record


async def _touch_active_sessions_for_user(
    session_db: AsyncSession,
    *,
    user_id: UUID,
    now: datetime | None = None,
) -> None:
    current_time = now or datetime.now(timezone.utc)
    next_expiry = current_time + timedelta(hours=settings.session_ttl_hours)
    result = await session_db.execute(
        select(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
    )
    for record in result.scalars().all():
        if record.expires_at is not None and record.expires_at < current_time:
            continue
        record.last_seen_at = current_time
        record.expires_at = next_expiry


async def _has_active_session_for_user(
    session_db: AsyncSession,
    *,
    user_id: UUID,
    trusted_device_id: str | None = None,
    now: datetime | None = None,
) -> bool:
    if not trusted_device_id:
        return False
    current_time = now or datetime.now(timezone.utc)
    active_session_id = await session_db.scalar(
        select(Session.id)
        .where(
            Session.user_id == user_id,
            Session.device_fingerprint == trusted_device_id,
            Session.revoked_at.is_(None),
            or_(Session.expires_at.is_(None), Session.expires_at >= current_time),
        )
        .limit(1)
    )
    return active_session_id is not None


async def _issue_authenticated_session(
    session_db: AsyncSession,
    *,
    user: User,
    ip_address: str | None,
    user_agent: str | None,
    business_id: UUID | None,
    location_id: UUID | None,
    actor_membership_id: UUID | None = None,
    device_fingerprint: str | None = None,
    risk_level: str = SessionRiskLevel.low.value,
    session_metadata: dict | None = None,
    source: str,
    purpose: str,
) -> tuple[str, Session]:
    raw_token, session_record = await _issue_session_record(
        session_db,
        user=user,
        device_fingerprint=device_fingerprint,
        ip_address=ip_address,
        user_agent=user_agent,
        risk_level=risk_level,
        elevated_actions=[],
        ttl_hours=settings.session_ttl_hours,
        session_metadata=session_metadata,
    )
    await audit_service.append(
        session_db,
        event_name="auth.session.created",
        target_type="session",
        target_id=session_record.id,
        business_id=business_id,
        location_id=location_id,
        actor_type=AuditActorType.user,
        actor_user_id=user.id,
        actor_membership_id=actor_membership_id,
        ip_address=ip_address,
        user_agent=user_agent,
        payload={"source": source, "purpose": purpose},
    )
    return raw_token, session_record


async def create_session(session_db: AsyncSession, payload: SessionCreateRequest) -> tuple[str, Session]:
    user = await session_db.get(User, payload.user_id)
    if user is None:
        raise LookupError("user_not_found")

    raw_token, record = await _issue_session_record(
        session_db,
        user=user,
        device_fingerprint=payload.device_fingerprint,
        ip_address=payload.ip_address,
        user_agent=payload.user_agent,
        risk_level=payload.risk_level,
        elevated_actions=payload.elevated_actions,
        ttl_hours=payload.ttl_hours,
        session_metadata=payload.session_metadata,
    )
    await audit_service.append(
        session_db,
        event_name="auth.session.created",
        target_type="session",
        target_id=record.id,
        actor_type=AuditActorType.user,
        actor_user_id=user.id,
        ip_address=payload.ip_address,
        user_agent=payload.user_agent,
        payload={"reason": "manual_session_create", "risk_level": payload.risk_level},
    )
    await session_db.commit()
    await session_db.refresh(record)
    return raw_token, record


async def resolve_auth_context(session_db: AsyncSession, raw_token: str) -> Optional[AuthContext]:
    hashed = hash_session_token(raw_token)
    record = await session_db.scalar(
        select(Session)
        .options(selectinload(Session.user))
        .where(Session.token_hash == hashed, Session.revoked_at.is_(None))
    )
    if record is None:
        return None

    now = datetime.now(timezone.utc)
    if record.expires_at is not None and record.expires_at < now:
        return None

    await _touch_active_sessions_for_user(
        session_db,
        user_id=record.user_id,
        now=now,
    )
    memberships_result = await session_db.execute(
        select(Membership)
        .where(
            Membership.user_id == record.user_id,
            Membership.status == MembershipStatus.active,
            Membership.revoked_at.is_(None),
        )
        .order_by(Membership.created_at.desc())
    )
    memberships = list(memberships_result.scalars().all())
    await session_db.commit()
    await session_db.refresh(record)
    return AuthContext(user=record.user, session=record, memberships=memberships)


async def restore_trusted_device_session(
    session_db: AsyncSession,
    *,
    trusted_device_id: str | None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    now: datetime | None = None,
) -> TrustedDeviceSessionRestoreResult | None:
    trusted_device_id = _trim_text(trusted_device_id)
    if not trusted_device_id:
        return None

    current_time = now or datetime.now(timezone.utc)
    result = await session_db.execute(
        select(Session)
        .options(selectinload(Session.user))
        .where(
            Session.device_fingerprint == trusted_device_id,
            Session.revoked_at.is_(None),
            or_(Session.expires_at.is_(None), Session.expires_at >= current_time),
        )
    )
    records = list(result.scalars().all())
    if not records:
        return None

    user_ids = {record.user_id for record in records}
    if len(user_ids) != 1:
        return None

    source_session = max(
        records,
        key=lambda record: (
            record.last_seen_at or record.updated_at or record.created_at,
            record.created_at,
        ),
    )
    raw_token, session_record = await _issue_authenticated_session(
        session_db,
        user=source_session.user,
        ip_address=ip_address,
        user_agent=user_agent,
        business_id=None,
        location_id=None,
        device_fingerprint=trusted_device_id,
        session_metadata={"auth_flow": "trusted_device_restore"},
        source="trusted_device_restore",
        purpose="restore",
    )
    await audit_service.append(
        session_db,
        event_name="auth.session.restored",
        target_type="session",
        target_id=session_record.id,
        actor_type=AuditActorType.user,
        actor_user_id=source_session.user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        payload={"restored_from_session_id": str(source_session.id)},
    )
    await session_db.commit()
    await session_db.refresh(source_session.user)
    await session_db.refresh(session_record)
    return TrustedDeviceSessionRestoreResult(
        user=source_session.user,
        session=session_record,
        token=raw_token,
        onboarding_required=onboarding_required_for_user(source_session.user),
    )


async def revoke_session_by_id(
    session_db: AsyncSession,
    session_id: UUID,
    *,
    actor_user_id: UUID | None = None,
    actor_membership_id: UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    record = await session_db.get(Session, session_id)
    if record is None or record.revoked_at is not None:
        return
    record.revoked_at = datetime.now(timezone.utc)
    await audit_service.append(
        session_db,
        event_name="auth.session.revoked",
        target_type="session",
        target_id=record.id,
        actor_type=AuditActorType.user if actor_user_id else AuditActorType.system,
        actor_user_id=actor_user_id,
        actor_membership_id=actor_membership_id,
        ip_address=ip_address,
        user_agent=user_agent,
        payload={"revoked_user_id": str(record.user_id)},
    )
    await session_db.commit()


async def list_active_sessions_for_user(
    session_db: AsyncSession,
    *,
    user_id: UUID,
    now: datetime | None = None,
) -> list[Session]:
    current_time = now or datetime.now(timezone.utc)
    result = await session_db.execute(
        select(Session).where(
            Session.user_id == user_id,
            Session.revoked_at.is_(None),
            or_(Session.expires_at.is_(None), Session.expires_at >= current_time),
        )
    )
    records = list(result.scalars().all())
    records.sort(
        key=lambda record: (
            record.last_seen_at or record.updated_at or record.created_at,
            record.created_at,
        ),
        reverse=True,
    )
    return records


async def revoke_user_session(
    session_db: AsyncSession,
    *,
    session_id: UUID,
    user_id: UUID,
    actor_user_id: UUID | None = None,
    actor_membership_id: UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    record = await session_db.get(Session, session_id)
    if record is None or record.user_id != user_id:
        raise LookupError("session_not_found")
    await revoke_session_by_id(
        session_db,
        session_id,
        actor_user_id=actor_user_id,
        actor_membership_id=actor_membership_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def has_business_access(
    auth: AuthContext,
    business_id: UUID,
    *,
    allowed_roles: Optional[set[MembershipRole]] = None,
) -> bool:
    return membership_for_scope(auth, business_id, allowed_roles=allowed_roles) is not None


def has_location_access(
    auth: AuthContext,
    business_id: UUID,
    location_id: UUID,
    *,
    allowed_roles: Optional[set[MembershipRole]] = None,
) -> bool:
    return membership_for_scope(
        auth,
        business_id,
        location_id=location_id,
        allowed_roles=allowed_roles,
    ) is not None


def _is_step_up_purpose(purpose: ChallengePurpose) -> bool:
    return purpose in {
        ChallengePurpose.step_up_billing,
        ChallengePurpose.step_up_export,
        ChallengePurpose.step_up_phone_change,
    }


async def request_otp_challenge(
    session_db: AsyncSession,
    payload: OTPChallengeRequest,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
    auth_ctx: AuthContext | None = None,
    trusted_device_id: str | None = None,
) -> OTPChallengeRequestResult:
    phone_e164 = normalize_phone(payload.phone_e164)
    if phone_e164 is None:
        raise ValueError("phone_must_be_e164_or_10_digit_us")
    trusted_device_id = _trim_text(trusted_device_id)

    purpose = ChallengePurpose(payload.purpose)
    ip_key = ip_address or "unknown"
    await rate_limit.assert_within_limit(
        "otp_request_ip",
        ip_key,
        limit=5,
        window_seconds=300,
        detail="Too many verification requests. Please wait and try again.",
    )
    now = datetime.now(timezone.utc)
    user = await session_db.scalar(select(User).where(User.primary_phone_e164 == phone_e164))
    if _is_step_up_purpose(purpose):
        if auth_ctx is None:
            raise PermissionError("step_up_auth_required")
        if normalize_phone(auth_ctx.user.primary_phone_e164) != phone_e164:
            raise PermissionError("step_up_phone_mismatch")

    if (
        purpose in {ChallengePurpose.sign_in, ChallengePurpose.sign_up}
        and user is not None
        and await _has_active_session_for_user(
            session_db,
            user_id=user.id,
            trusted_device_id=trusted_device_id,
            now=now,
        )
    ):
        raw_token, session_record = await _issue_authenticated_session(
            session_db,
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            business_id=payload.business_id,
            location_id=payload.location_id,
            device_fingerprint=trusted_device_id,
            session_metadata={"auth_flow": "trusted_reentry"},
            source="trusted_reentry",
            purpose=purpose.value,
        )
        await audit_service.append(
            session_db,
            event_name="auth.challenge.skipped",
            target_type="user",
            target_id=user.id,
            business_id=payload.business_id,
            location_id=payload.location_id,
            actor_type=AuditActorType.user,
            actor_user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            payload={
                "purpose": purpose.value,
                "reason": "recognized_device_with_active_session",
                "phone_e164": phone_e164,
            },
        )
        await session_db.commit()
        await session_db.refresh(user)
        await session_db.refresh(session_record)
        return OTPChallengeRequestResult(
            challenge=None,
            user_exists=True,
            session=session_record,
            token=raw_token,
            trusted_device_id=trusted_device_id,
            onboarding_required=onboarding_required_for_user(user),
            otp_required=False,
        )

    await rate_limit.assert_within_limit(
        "otp_request_phone_cooldown",
        phone_e164,
        limit=1,
        window_seconds=30,
        detail="Please wait before requesting another code.",
    )
    await rate_limit.assert_within_limit(
        "otp_request_phone_window",
        phone_e164,
        limit=5,
        window_seconds=900,
        detail="Too many verification requests for this phone. Please wait and try again.",
    )

    challenge = OTPChallenge(
        user_id=user.id if user is not None else None,
        phone_e164=phone_e164,
        channel=ChallengeChannel(payload.channel),
        purpose=purpose,
        status=ChallengeStatus.pending,
        attempt_count=0,
        max_attempts=5,
        requested_for_business_id=payload.business_id,
        requested_for_location_id=payload.location_id,
        expires_at=now + timedelta(minutes=10),
        challenge_metadata=_merged_client_challenge_metadata(
            payload.challenge_metadata,
            locale=payload.locale,
        ),
    )
    session_db.add(challenge)
    await session_db.flush()

    actor_user_id = auth_ctx.user.id if auth_ctx is not None else (user.id if user is not None else None)
    actor_type = AuditActorType.user if actor_user_id else AuditActorType.service
    actor_membership_id = None
    if auth_ctx is not None and payload.business_id is not None:
        membership = membership_for_scope(auth_ctx, payload.business_id, location_id=payload.location_id)
        actor_membership_id = membership.id if membership is not None else None

    try:
        verification = messaging.send_sms_verification(phone_e164, locale=payload.locale)
    except Exception as exc:
        challenge.status = ChallengeStatus.failed
        challenge.challenge_metadata = {
            **challenge.challenge_metadata,
            "delivery_error": str(exc),
        }
        await audit_service.append(
            session_db,
            event_name="auth.challenge.request_failed",
            target_type="otp_challenge",
            target_id=challenge.id,
            business_id=payload.business_id,
            location_id=payload.location_id,
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            actor_membership_id=actor_membership_id,
            ip_address=ip_address,
            user_agent=user_agent,
            payload={
                "purpose": purpose.value,
                "channel": payload.channel,
                "phone_e164": phone_e164,
                "error": str(exc),
            },
        )
        await session_db.commit()
        raise

    challenge.external_sid = verification.get("sid")
    challenge.challenge_metadata = {
        **challenge.challenge_metadata,
        "delivery_status": verification.get("status"),
        "delivery_channel": verification.get("channel"),
    }
    await audit_service.append(
        session_db,
        event_name="auth.challenge.requested",
        target_type="otp_challenge",
        target_id=challenge.id,
        business_id=payload.business_id,
        location_id=payload.location_id,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        actor_membership_id=actor_membership_id,
        ip_address=ip_address,
        user_agent=user_agent,
        payload={
            "purpose": purpose.value,
            "channel": payload.channel,
            "phone_e164": phone_e164,
            "requested_purpose": payload.purpose,
        },
    )
    await session_db.commit()
    await session_db.refresh(challenge)
    return OTPChallengeRequestResult(
        challenge=challenge,
        user_exists=user is not None,
        session=None,
        token=None,
        trusted_device_id=None,
        onboarding_required=False,
        otp_required=True,
    )


async def verify_otp_challenge(
    session_db: AsyncSession,
    payload: OTPChallengeVerifyRequest,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
    auth_ctx: AuthContext | None = None,
    trusted_device_id: str | None = None,
) -> OTPChallengeVerificationResult:
    phone_e164 = normalize_phone(payload.phone_e164)
    if phone_e164 is None:
        raise ValueError("phone_must_be_e164_or_10_digit_us")
    trusted_device_id = _trim_text(trusted_device_id)

    await rate_limit.assert_within_limit(
        "otp_verify_ip",
        ip_address or "unknown",
        limit=20,
        window_seconds=300,
        detail="Too many verification attempts. Please wait and try again.",
    )

    challenge = await session_db.get(OTPChallenge, payload.challenge_id)
    if challenge is None or challenge.phone_e164 != phone_e164:
        raise LookupError("challenge_not_found")
    if challenge.status != ChallengeStatus.pending:
        raise ValueError("challenge_not_pending")

    now = datetime.now(timezone.utc)
    if challenge.expires_at is not None and challenge.expires_at < now:
        challenge.status = ChallengeStatus.expired
        await audit_service.append(
            session_db,
            event_name="auth.challenge.expired",
            target_type="otp_challenge",
            target_id=challenge.id,
            business_id=challenge.requested_for_business_id,
            location_id=challenge.requested_for_location_id,
            actor_type=AuditActorType.service,
            ip_address=ip_address,
            user_agent=user_agent,
            payload={"phone_e164": phone_e164, "purpose": challenge.purpose.value},
        )
        await session_db.commit()
        raise ValueError("challenge_expired")

    if challenge.attempt_count >= challenge.max_attempts:
        challenge.status = ChallengeStatus.failed
        await session_db.commit()
        raise ValueError("challenge_max_attempts_exceeded")

    if _is_step_up_purpose(challenge.purpose):
        if auth_ctx is None:
            raise PermissionError("step_up_auth_required")
        if normalize_phone(auth_ctx.user.primary_phone_e164) != phone_e164:
            raise PermissionError("step_up_phone_mismatch")

    verification_check = messaging.check_sms_verification(phone_e164, payload.code)
    challenge.attempt_count += 1
    challenge.external_sid = verification_check.get("sid") or challenge.external_sid

    is_valid = bool(verification_check.get("valid")) or verification_check.get("status") == "approved"
    if not is_valid:
        if challenge.attempt_count >= challenge.max_attempts:
            challenge.status = ChallengeStatus.failed
        await audit_service.append(
            session_db,
            event_name="auth.challenge.failed",
            target_type="otp_challenge",
            target_id=challenge.id,
            business_id=challenge.requested_for_business_id,
            location_id=challenge.requested_for_location_id,
            actor_type=AuditActorType.service,
            actor_user_id=auth_ctx.user.id if auth_ctx is not None else challenge.user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            payload={
                "phone_e164": phone_e164,
                "purpose": challenge.purpose.value,
                "attempt_count": challenge.attempt_count,
                "status": verification_check.get("status"),
            },
        )
        await session_db.commit()
        raise ValueError("invalid_otp_code")

    challenge.status = ChallengeStatus.approved
    challenge.approved_at = now

    user = None
    if challenge.user_id is not None:
        user = await session_db.get(User, challenge.user_id)
    if user is None:
        user = await session_db.scalar(select(User).where(User.primary_phone_e164 == phone_e164))

    if user is None:
        user = User(
            primary_phone_e164=phone_e164,
            is_phone_verified=True,
            profile_metadata={"created_from_challenge_purpose": challenge.purpose.value},
        )
        session_db.add(user)
        await session_db.flush()
    else:
        user.primary_phone_e164 = phone_e164
        user.is_phone_verified = True

    challenge.user_id = user.id
    invite_membership = None
    if challenge.purpose == ChallengePurpose.invite_acceptance:
        invite_id = (challenge.challenge_metadata or {}).get("invite_id")
        if not invite_id:
            raise ValueError("invite_id_required")
        from app.services import invites as invite_service

        invite_record, invite_membership = await invite_service.accept_invite_for_verified_user(
            session_db,
            invite_id=UUID(str(invite_id)),
            user=user,
            phone_e164=phone_e164,
            manager_name=_trim_text((challenge.challenge_metadata or {}).get("manager_name")),
        )
        challenge.requested_for_business_id = invite_record.business_id
        challenge.requested_for_location_id = invite_record.location_id
        maybe_complete_onboarding(user, completed_at=now)

    if _is_step_up_purpose(challenge.purpose):
        assert auth_ctx is not None
        elevated_actions = set(auth_ctx.session.elevated_actions or [])
        elevated_actions.add(challenge.purpose.value)
        auth_ctx.session.elevated_actions = sorted(elevated_actions)
        next_session_metadata = dict(auth_ctx.session.session_metadata or {})
        step_up_verified_at = _recent_step_up_map(auth_ctx.session)
        step_up_verified_at[challenge.purpose.value] = now.isoformat()
        next_session_metadata["step_up_verified_at"] = step_up_verified_at
        auth_ctx.session.session_metadata = next_session_metadata
        await _touch_active_sessions_for_user(
            session_db,
            user_id=auth_ctx.user.id,
            now=now,
        )
        membership = None
        if challenge.requested_for_business_id is not None:
            membership = membership_for_scope(
                auth_ctx,
                challenge.requested_for_business_id,
                location_id=challenge.requested_for_location_id,
            )
        await audit_service.append(
            session_db,
            event_name="auth.step_up.granted",
            target_type="session",
            target_id=auth_ctx.session.id,
            business_id=challenge.requested_for_business_id,
            location_id=challenge.requested_for_location_id,
            actor_type=AuditActorType.user,
            actor_user_id=auth_ctx.user.id,
            actor_membership_id=membership.id if membership is not None else None,
            ip_address=ip_address,
            user_agent=user_agent,
            payload={"purpose": challenge.purpose.value},
        )
        await session_db.commit()
        await session_db.refresh(challenge)
        await session_db.refresh(user)
        await session_db.refresh(auth_ctx.session)
        return OTPChallengeVerificationResult(
            challenge=challenge,
            user=user,
            session=auth_ctx.session,
            token=None,
            trusted_device_id=None,
            onboarding_required=onboarding_required_for_user(user),
            step_up_granted=True,
        )

    trusted_device_id = trusted_device_id or generate_trusted_device_id()
    raw_token, session_record = await _issue_authenticated_session(
        session_db,
        user=user,
        ip_address=ip_address,
        user_agent=user_agent,
        business_id=challenge.requested_for_business_id,
        location_id=challenge.requested_for_location_id,
        actor_membership_id=invite_membership.id if invite_membership is not None else None,
        device_fingerprint=trusted_device_id,
        risk_level=payload.risk_level,
        session_metadata={},
        source="otp_challenge",
        purpose=challenge.purpose.value,
    )
    await audit_service.append(
        session_db,
        event_name="auth.challenge.approved",
        target_type="otp_challenge",
        target_id=challenge.id,
        business_id=challenge.requested_for_business_id,
        location_id=challenge.requested_for_location_id,
        actor_type=AuditActorType.user,
        actor_user_id=user.id,
        actor_membership_id=invite_membership.id if invite_membership is not None else None,
        ip_address=ip_address,
        user_agent=user_agent,
        payload={"purpose": challenge.purpose.value, "phone_e164": phone_e164},
    )
    if invite_membership is not None:
        await audit_service.append(
            session_db,
            event_name="manager_invite.accepted",
            target_type="membership",
            target_id=invite_membership.id,
            business_id=invite_membership.business_id,
            location_id=invite_membership.location_id,
            actor_type=AuditActorType.user,
            actor_user_id=user.id,
            actor_membership_id=invite_membership.id,
            ip_address=ip_address,
            user_agent=user_agent,
            payload={
                "phone_e164": phone_e164,
                "invite_id": str(invite_id),
            },
        )
    await session_db.commit()
    await session_db.refresh(challenge)
    await session_db.refresh(user)
    await session_db.refresh(session_record)
    return OTPChallengeVerificationResult(
        challenge=challenge,
        user=user,
        session=session_record,
        token=raw_token,
        trusted_device_id=trusted_device_id,
        onboarding_required=onboarding_required_for_user(user),
        step_up_granted=False,
    )
