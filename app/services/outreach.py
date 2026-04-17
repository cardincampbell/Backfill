from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import NO_VALUE
from sqlalchemy.orm import selectinload

from app.models.common import AuditActorType, CoverageAttemptStatus, OfferStatus
from app.models.coverage import CoverageCase, CoverageContactAttempt, CoverageOffer
from app.models.scheduling import Shift
from app.schemas.coverage import CoverageOutreachAttemptRead
from app.services import platform_events


def _enum_text(value: object | None) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        return str(value.value)
    text = str(value).strip()
    return text or None


def _latest_attempt(offer: CoverageOffer) -> CoverageContactAttempt | None:
    state = inspect(offer)
    attempts_attr = state.attrs.attempts
    loaded_value = attempts_attr.loaded_value
    if loaded_value is NO_VALUE:
        return None
    attempts = list(loaded_value or [])
    if not attempts:
        return None
    return max(
        attempts,
        key=lambda attempt: (
            int(getattr(attempt, "attempt_no", 0) or 0),
            getattr(attempt, "requested_at", None) or getattr(attempt, "created_at", None),
        ),
    )


def _safe_attr(instance: object, name: str) -> object | None:
    try:
        state = inspect(instance)
    except NoInspectionAvailable:
        return getattr(instance, name, None)
    if name in state.dict:
        return state.dict.get(name)
    if name not in state.attrs:
        return None
    attr_state = state.attrs[name]
    loaded_value = attr_state.loaded_value
    if loaded_value is NO_VALUE:
        return None
    return loaded_value


def logical_outreach_status(
    offer: CoverageOffer,
    *,
    attempt: CoverageContactAttempt | None = None,
) -> str:
    raw_offer_status = _enum_text(_safe_attr(offer, "status")) or "pending"
    raw_attempt_status = _enum_text(_safe_attr(attempt, "status")) if attempt is not None else None
    channel = _enum_text(_safe_attr(offer, "channel")) or "sms"

    if raw_offer_status == OfferStatus.pending.value:
        if attempt is not None and attempt.sent_at is not None:
            if channel == "voice":
                return "voice_initiated"
            return "sms_sent"
        return "queued"
    if raw_offer_status == OfferStatus.delivered.value:
        if channel == "voice":
            return "voice_initiated"
        if raw_attempt_status == CoverageAttemptStatus.delivered.value:
            return "awaiting_response"
        return "sms_sent"
    if raw_offer_status == OfferStatus.accepted.value:
        return "accepted"
    if raw_offer_status == OfferStatus.declined.value:
        return "declined"
    if raw_offer_status == OfferStatus.expired.value:
        return "expired"
    if raw_offer_status == OfferStatus.cancelled.value:
        return "cancelled"
    if raw_offer_status == OfferStatus.failed.value:
        return "failed"
    return raw_offer_status


def outreach_attempt_read_from_offer(
    offer: CoverageOffer,
    *,
    attempt: CoverageContactAttempt | None = None,
) -> CoverageOutreachAttemptRead:
    latest_attempt = attempt or _latest_attempt(offer)
    offer_created_at = _safe_attr(offer, "created_at")
    offer_updated_at = _safe_attr(offer, "updated_at")
    offer_sent_at = _safe_attr(offer, "sent_at")
    offer_expires_at = _safe_attr(offer, "expires_at")
    offer_accepted_at = _safe_attr(offer, "accepted_at")
    offer_declined_at = _safe_attr(offer, "declined_at")
    offer_channel = _enum_text(_safe_attr(offer, "channel")) or "sms"
    offer_status = _enum_text(_safe_attr(offer, "status")) or "pending"
    offer_delivery_provider = _safe_attr(offer, "delivery_provider")
    offer_provider_message_id = _safe_attr(offer, "provider_message_id")
    offer_idempotency_key = _safe_attr(offer, "idempotency_key")
    offer_metadata = dict((_safe_attr(offer, "offer_metadata") or {}))

    attempt_requested_at = _safe_attr(latest_attempt, "requested_at")
    attempt_created_at = _safe_attr(latest_attempt, "created_at")
    attempt_status = _enum_text(_safe_attr(latest_attempt, "status")) if latest_attempt is not None else None
    attempt_no = int((_safe_attr(latest_attempt, "attempt_no") or 0)) if latest_attempt is not None else 0
    attempt_outbox_event_id = _safe_attr(latest_attempt, "outbox_event_id")
    attempt_delivery_provider = _safe_attr(latest_attempt, "delivery_provider")
    attempt_provider_message_id = _safe_attr(latest_attempt, "provider_message_id")
    attempt_sent_at = _safe_attr(latest_attempt, "sent_at")
    attempt_delivered_at = _safe_attr(latest_attempt, "delivered_at")
    attempt_responded_at = _safe_attr(latest_attempt, "responded_at")
    attempt_expires_at = _safe_attr(latest_attempt, "expires_at")
    attempt_metadata = dict((_safe_attr(latest_attempt, "attempt_metadata") or {}))
    attempt_updated_at = _safe_attr(latest_attempt, "updated_at")

    reference_time = (
        offer_created_at
        or offer_updated_at
        or attempt_requested_at
        or attempt_created_at
        or datetime.now(timezone.utc)
    )
    requested_at = (
        attempt_requested_at
        if latest_attempt is not None
        else offer_sent_at or reference_time
    )
    return CoverageOutreachAttemptRead(
        id=offer.id,
        campaign_id=_safe_attr(offer, "coverage_case_id"),
        campaign_run_id=_safe_attr(offer, "coverage_case_run_id"),
        coverage_candidate_id=_safe_attr(offer, "coverage_candidate_id"),
        employee_id=_safe_attr(offer, "employee_id"),
        channel=offer_channel,
        status=logical_outreach_status(offer, attempt=latest_attempt),
        offer_status=offer_status,
        attempt_status=attempt_status,
        attempt_no=attempt_no,
        outbox_event_id=attempt_outbox_event_id,
        delivery_provider=(
            attempt_delivery_provider
            or offer_delivery_provider
        ),
        provider_message_id=(
            attempt_provider_message_id
            or offer_provider_message_id
        ),
        idempotency_key=offer_idempotency_key,
        requested_at=requested_at,
        sent_at=attempt_sent_at or offer_sent_at,
        delivered_at=attempt_delivered_at,
        responded_at=attempt_responded_at,
        expires_at=attempt_expires_at or offer_expires_at,
        accepted_at=offer_accepted_at,
        declined_at=offer_declined_at,
        offer_metadata=offer_metadata,
        attempt_metadata=attempt_metadata,
        created_at=offer_created_at or reference_time,
        updated_at=max(
            [
                value
                for value in [offer_updated_at, attempt_updated_at, reference_time]
                if value is not None
            ],
            default=reference_time,
        ),
    )


def outreach_attempt_reads_from_offers(
    offers: Iterable[CoverageOffer],
) -> list[CoverageOutreachAttemptRead]:
    return [outreach_attempt_read_from_offer(offer) for offer in offers]


async def build_outreach_attempt_read(
    session: AsyncSession,
    offer: CoverageOffer,
) -> CoverageOutreachAttemptRead:
    latest_attempt = _latest_attempt(offer)
    if latest_attempt is None and hasattr(session, "scalar"):
        latest_attempt = await session.scalar(
            select(CoverageContactAttempt)
            .where(CoverageContactAttempt.coverage_offer_id == offer.id)
            .order_by(CoverageContactAttempt.attempt_no.desc(), CoverageContactAttempt.requested_at.desc())
            .limit(1)
        )
    return outreach_attempt_read_from_offer(offer, attempt=latest_attempt)


async def list_campaign_outreach_attempts(
    session: AsyncSession,
    *,
    business_id: UUID,
    campaign_id: UUID,
) -> list[CoverageOutreachAttemptRead]:
    coverage_case = await session.scalar(
        select(CoverageCase)
        .join(Shift, CoverageCase.shift_id == Shift.id)
        .where(
            CoverageCase.id == campaign_id,
            Shift.business_id == business_id,
        )
        .limit(1)
    )
    if coverage_case is None:
        raise LookupError("coverage_case_not_found")

    result = await session.execute(
        select(CoverageOffer)
        .options(selectinload(CoverageOffer.attempts))
        .where(CoverageOffer.coverage_case_id == campaign_id)
        .order_by(CoverageOffer.created_at.asc())
    )
    offers = list(result.scalars().all())
    return outreach_attempt_reads_from_offers(offers)


async def append_outreach_attempt_event(
    session: AsyncSession,
    *,
    event_type: str,
    offer: CoverageOffer,
    compatibility_event_name: str | None = None,
    business_id: UUID | None = None,
    location_id: UUID | None = None,
    shift_id: UUID | None = None,
    attempt: CoverageContactAttempt | None = None,
    actor_type: AuditActorType = AuditActorType.system,
    actor_user_id: UUID | None = None,
    actor_membership_id: UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict | None = None,
) -> None:
    resolved_location_id = location_id
    resolved_shift_id = shift_id
    resolved_business_id = business_id

    if resolved_business_id is None or resolved_location_id is None or resolved_shift_id is None:
        coverage_case = await session.get(CoverageCase, offer.coverage_case_id)
        if coverage_case is not None:
            resolved_location_id = resolved_location_id or coverage_case.location_id
            resolved_shift_id = resolved_shift_id or coverage_case.shift_id
            if resolved_business_id is None:
                shift = await session.get(Shift, coverage_case.shift_id)
                if shift is not None:
                    resolved_business_id = shift.business_id

    resolved_attempt = attempt or _latest_attempt(offer)
    if resolved_attempt is None and hasattr(session, "scalar"):
        resolved_attempt = await session.scalar(
            select(CoverageContactAttempt)
            .where(CoverageContactAttempt.coverage_offer_id == offer.id)
            .order_by(CoverageContactAttempt.attempt_no.desc(), CoverageContactAttempt.requested_at.desc())
            .limit(1)
        )

    payload = outreach_attempt_read_from_offer(
        offer,
        attempt=resolved_attempt,
    ).model_dump(mode="json")
    payload.update(
        {
            "outreach_attempt_id": str(offer.id),
            "coverage_offer_id": str(offer.id),
            "shift_id": str(resolved_shift_id) if resolved_shift_id is not None else None,
        }
    )
    await platform_events.append(
        session,
        event_type=event_type,
        compatibility_event_name=compatibility_event_name,
        target_type="coverage_outreach_attempt",
        target_id=offer.id,
        business_id=resolved_business_id,
        location_id=resolved_location_id,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        actor_membership_id=actor_membership_id,
        ip_address=ip_address,
        user_agent=user_agent,
        payload=payload,
        metadata=metadata or {},
    )
