from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.common import CoverageAttemptStatus, CoverageCaseStatus, OfferStatus, OutboxStatus
from app.models.coverage import CoverageCandidate, CoverageCase, CoverageCaseRun, CoverageContactAttempt, CoverageOffer, OutboxEvent
from app.models.scheduling import Shift
from app.models.workforce import Employee
from app.schemas.coverage import CoverageOfferResponseCreate
from app.services import messaging, retell as retell_service


@dataclass
class DeliverySendResult:
    success: bool
    provider: str = "stub"
    provider_message_id: str | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    error_message: str | None = None
    result_payload: dict = field(default_factory=dict)


class DeliveryProvider(Protocol):
    async def send_coverage_offer(
        self,
        *,
        outbox_event: OutboxEvent,
        offer: CoverageOffer,
        shift: Shift,
    ) -> DeliverySendResult: ...


class StubDeliveryProvider:
    async def send_coverage_offer(
        self,
        *,
        outbox_event: OutboxEvent,
        offer: CoverageOffer,
        shift: Shift,
    ) -> DeliverySendResult:
        now = datetime.now(timezone.utc)
        return DeliverySendResult(
            success=True,
            provider="stub",
            provider_message_id=f"stub-{offer.id}",
            sent_at=now,
            delivered_at=now,
            result_payload={
                "topic": outbox_event.topic,
                "offer_id": str(offer.id),
                "shift_id": str(shift.id),
            },
        )


class TwilioSMSDeliveryProvider:
    async def send_coverage_offer(
        self,
        *,
        outbox_event: OutboxEvent,
        offer: CoverageOffer,
        shift: Shift,
    ) -> DeliverySendResult:
        body = build_coverage_offer_sms(offer=offer, shift=shift)
        callback_url = f"{settings.api_base_url}{settings.api_prefix}/providers/twilio/sms/status"
        to_number = str(outbox_event.payload.get("phone_e164") or offer.offer_metadata.get("phone_e164") or "").strip()
        if not to_number:
            return DeliverySendResult(
                success=False,
                provider="twilio",
                error_message="missing_destination_phone",
                result_payload={"status_callback": callback_url},
            )
        message = messaging.send_sms(
            to=to_number,
            body=body,
            status_callback=callback_url,
        )
        now = datetime.now(timezone.utc)
        return DeliverySendResult(
            success=True,
            provider="twilio",
            provider_message_id=message.get("sid"),
            sent_at=now,
            delivered_at=None,
            result_payload={
                "twilio_status": message.get("status"),
                "status_callback": callback_url,
            },
        )


class RetellVoiceDeliveryProvider:
    async def send_coverage_offer(
        self,
        *,
        outbox_event: OutboxEvent,
        offer: CoverageOffer,
        shift: Shift,
    ) -> DeliverySendResult:
        to_number = str(outbox_event.payload.get("phone_e164") or offer.offer_metadata.get("phone_e164") or "").strip()
        if not to_number:
            return DeliverySendResult(
                success=False,
                provider="retell",
                error_message="missing_destination_phone",
            )
        metadata = build_coverage_offer_voice_metadata(offer=offer, shift=shift)
        call_id = await retell_service.create_phone_call(
            to_number=to_number,
            metadata=metadata,
            agent_kind="outbound",
        )
        now = datetime.now(timezone.utc)
        return DeliverySendResult(
            success=True,
            provider="retell",
            provider_message_id=call_id,
            sent_at=now,
            result_payload={"call_id": call_id, "metadata": metadata},
        )


@dataclass
class ActionableOfferContext:
    offer: CoverageOffer
    business_id: UUID


def build_coverage_offer_sms(*, offer: CoverageOffer, shift: Shift) -> str:
    shift_timezone = getattr(shift, "timezone", None) or "America/Los_Angeles"
    try:
        tz = ZoneInfo(shift_timezone)
    except Exception:
        tz = timezone.utc
    starts_local = shift.starts_at.astimezone(tz)
    ends_local = shift.ends_at.astimezone(tz)
    premium_cents = int(offer.offer_metadata.get("premium_cents", 0) or 0)
    premium_copy = f" + ${premium_cents / 100:.2f} premium" if premium_cents > 0 else ""
    location_name = getattr(getattr(shift, "location", None), "name", None) or "your location"
    role_name = getattr(getattr(shift, "role", None), "name", None) or "team member"
    start_label = starts_local.strftime("%a %b %d %I:%M%p").replace(" 0", " ")
    end_label = ends_local.strftime("%I:%M%p").lstrip("0")
    return (
        f"Backfill: {location_name} needs a {role_name} for {start_label}-{end_label}{premium_copy}. "
        "Reply YES to take it or NO to decline."
    )


def build_coverage_offer_voice_metadata(*, offer: CoverageOffer, shift: Shift) -> dict:
    location_name = getattr(getattr(shift, "location", None), "name", None) or "your location"
    role_name = getattr(getattr(shift, "role", None), "name", None) or "team member"
    return {
        "offer_id": str(offer.id),
        "coverage_case_id": str(offer.coverage_case_id),
        "coverage_case_run_id": str(offer.coverage_case_run_id) if offer.coverage_case_run_id else None,
        "employee_id": str(offer.employee_id),
        "shift_id": str(shift.id),
        "location_id": str(shift.location_id),
        "role_id": str(shift.role_id),
        "location_name": location_name,
        "role_name": role_name,
        "shift_timezone": shift.timezone,
        "shift_starts_at": shift.starts_at.isoformat(),
        "shift_ends_at": shift.ends_at.isoformat(),
        "premium_cents": int(offer.offer_metadata.get("premium_cents", 0) or 0),
        "offer_channel": "voice",
    }


def _resolve_provider_for_channel(channel) -> DeliveryProvider:
    channel_value = channel.value if hasattr(channel, "value") else str(channel)
    if channel_value == "sms":
        return TwilioSMSDeliveryProvider()
    if channel_value == "voice":
        return RetellVoiceDeliveryProvider()
    return StubDeliveryProvider()


async def refresh_employee_reliability(
    session: AsyncSession,
    employee_id: UUID,
    *,
    now: datetime | None = None,
) -> Employee | None:
    employee = await session.get(Employee, employee_id)
    if employee is None:
        return None

    reference_time = now or datetime.now(timezone.utc)
    window_start = reference_time - timedelta(days=30)
    result = await session.execute(
        select(CoverageContactAttempt).where(
            CoverageContactAttempt.employee_id == employee_id,
            CoverageContactAttempt.requested_at >= window_start,
            CoverageContactAttempt.status.in_(
                [
                    CoverageAttemptStatus.accepted,
                    CoverageAttemptStatus.declined,
                    CoverageAttemptStatus.expired,
                ]
            ),
        )
    )
    attempts = list(result.scalars().all())
    if not attempts:
        employee.reliability_score = 0.7
        employee.avg_response_time_seconds = None
        employee.response_profile = {
            "window_days": 30,
            "attempt_count": 0,
            "accepted_count": 0,
        }
        await session.flush()
        return employee

    total_attempts = len(attempts)
    accepted_count = sum(1 for attempt in attempts if attempt.status == CoverageAttemptStatus.accepted)
    response_times = [attempt.response_time_seconds for attempt in attempts if attempt.response_time_seconds is not None]
    acceptance_rate = accepted_count / total_attempts
    response_speed_score = 0.5
    avg_response_time_seconds = None
    if response_times:
        avg_response_time_seconds = int(sum(response_times) / len(response_times))
        response_speed_score = sum(max(0.0, min(1.0, 1 - (seconds / 1800))) for seconds in response_times) / len(
            response_times
        )
    recent_positive_rate = acceptance_rate
    raw_score = (acceptance_rate * 0.5) + (response_speed_score * 0.3) + (recent_positive_rate * 0.2)
    trusted_attempts = min(total_attempts, 5)
    if total_attempts < 5:
        raw_score = ((raw_score * trusted_attempts) + (0.7 * (5 - trusted_attempts))) / 5

    employee.reliability_score = round(max(0.0, min(1.0, raw_score)), 3)
    employee.avg_response_time_seconds = avg_response_time_seconds
    employee.response_profile = {
        "window_days": 30,
        "attempt_count": total_attempts,
        "accepted_count": accepted_count,
        "acceptance_rate": round(acceptance_rate, 3),
        "response_speed_score": round(response_speed_score, 3),
        "avg_response_time_seconds": avg_response_time_seconds,
        "updated_at": reference_time.isoformat(),
    }
    await session.flush()
    return employee


async def mark_offer_attempt_outcome(
    session: AsyncSession,
    offer: CoverageOffer,
    *,
    status: CoverageAttemptStatus,
    occurred_at: datetime,
    response_payload: dict | None = None,
) -> CoverageContactAttempt | None:
    attempt = await session.scalar(
        select(CoverageContactAttempt)
        .where(CoverageContactAttempt.coverage_offer_id == offer.id)
        .order_by(CoverageContactAttempt.attempt_no.desc())
        .limit(1)
    )
    if attempt is None:
        return None

    attempt.status = status
    if status in {
        CoverageAttemptStatus.accepted,
        CoverageAttemptStatus.declined,
        CoverageAttemptStatus.expired,
        CoverageAttemptStatus.cancelled,
        CoverageAttemptStatus.failed,
    }:
        attempt.responded_at = occurred_at
    base_time = attempt.sent_at or attempt.requested_at
    if base_time is not None:
        attempt.response_time_seconds = max(0, int((occurred_at - base_time).total_seconds()))
    if response_payload:
        attempt.attempt_metadata = {**attempt.attempt_metadata, "response_payload": response_payload}
    await session.flush()
    return attempt


async def _claim_due_outbox_events(
    session: AsyncSession,
    *,
    now: datetime,
    limit: int,
) -> list[OutboxEvent]:
    result = await session.execute(
        select(OutboxEvent)
        .where(
            OutboxEvent.status.in_([OutboxStatus.pending, OutboxStatus.failed]),
            OutboxEvent.available_at <= now,
            OutboxEvent.topic == "coverage.offer.created",
        )
        .order_by(OutboxEvent.available_at.asc(), OutboxEvent.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    events = list(result.scalars().all())
    for event in events:
        event.status = OutboxStatus.processing
        event.locked_at = now
        event.attempt_count = int(event.attempt_count or 0) + 1
    await session.flush()
    return events


async def _get_or_create_contact_attempt(
    session: AsyncSession,
    *,
    outbox_event: OutboxEvent,
    offer: CoverageOffer,
    shift: Shift,
    now: datetime,
) -> CoverageContactAttempt:
    attempt = await session.scalar(
        select(CoverageContactAttempt).where(CoverageContactAttempt.outbox_event_id == outbox_event.id).limit(1)
    )
    if attempt is not None:
        return attempt

    current_attempt_no = await session.scalar(
        select(func.coalesce(func.max(CoverageContactAttempt.attempt_no), 0)).where(
            CoverageContactAttempt.coverage_offer_id == offer.id
        )
    )
    attempt = CoverageContactAttempt(
        coverage_offer_id=offer.id,
        coverage_case_id=offer.coverage_case_id,
        coverage_case_run_id=offer.coverage_case_run_id,
        outbox_event_id=outbox_event.id,
        shift_id=shift.id,
        location_id=shift.location_id,
        employee_id=offer.employee_id,
        channel=offer.channel,
        status=CoverageAttemptStatus.pending,
        attempt_no=int(current_attempt_no or 0) + 1,
        requested_at=outbox_event.available_at or now,
        expires_at=offer.expires_at,
        attempt_metadata={"topic": outbox_event.topic},
    )
    session.add(attempt)
    await session.flush()
    return attempt


async def process_outbox_batch(
    session: AsyncSession,
    *,
    provider: DeliveryProvider | None = None,
    now: datetime | None = None,
    limit: int = 20,
) -> dict:
    reference_time = now or datetime.now(timezone.utc)
    events = await _claim_due_outbox_events(session, now=reference_time, limit=limit)

    sent_count = 0
    failed_count = 0
    processed_event_ids: list[str] = []

    for event in events:
        offer = await session.get(CoverageOffer, event.aggregate_id)
        if offer is None:
            event.status = OutboxStatus.failed
            event.processed_at = reference_time
            event.error_message = "coverage_offer_not_found"
            failed_count += 1
            processed_event_ids.append(str(event.id))
            continue

        shift_id_raw = offer.offer_metadata.get("shift_id")
        shift = (
            await session.scalar(
                select(Shift)
                .options(selectinload(Shift.location), selectinload(Shift.role))
                .where(Shift.id == UUID(str(shift_id_raw)))
            )
            if shift_id_raw
            else None
        )
        if shift is None:
            event.status = OutboxStatus.failed
            event.processed_at = reference_time
            event.error_message = "shift_not_found"
            offer.status = OfferStatus.failed
            failed_count += 1
            processed_event_ids.append(str(event.id))
            continue

        attempt = await _get_or_create_contact_attempt(
            session,
            outbox_event=event,
            offer=offer,
            shift=shift,
            now=reference_time,
        )

        active_provider = provider or _resolve_provider_for_channel(offer.channel)
        result = await active_provider.send_coverage_offer(
            outbox_event=event,
            offer=offer,
            shift=shift,
        )
        if result.success:
            sent_at = result.sent_at or reference_time
            delivered_at = result.delivered_at
            offer.delivery_provider = result.provider
            offer.provider_message_id = result.provider_message_id
            offer.sent_at = sent_at
            offer.status = OfferStatus.delivered if delivered_at is not None else OfferStatus.pending

            attempt.status = CoverageAttemptStatus.delivered if delivered_at is not None else CoverageAttemptStatus.pending
            attempt.delivery_provider = result.provider
            attempt.provider_message_id = result.provider_message_id
            attempt.sent_at = sent_at
            attempt.delivered_at = delivered_at
            attempt.attempt_metadata = {**attempt.attempt_metadata, **result.result_payload}

            event.status = OutboxStatus.sent
            event.processed_at = reference_time
            event.result_payload = result.result_payload
            sent_count += 1
        else:
            offer.status = OfferStatus.failed
            attempt.status = CoverageAttemptStatus.failed
            attempt.responded_at = reference_time
            attempt.attempt_metadata = {**attempt.attempt_metadata, **result.result_payload}
            event.status = OutboxStatus.failed
            event.processed_at = reference_time
            event.error_message = result.error_message
            event.result_payload = result.result_payload
            failed_count += 1

        processed_event_ids.append(str(event.id))

    await session.commit()
    return {
        "claimed_count": len(events),
        "sent_count": sent_count,
        "failed_count": failed_count,
        "processed_event_ids": processed_event_ids,
    }


async def _advance_case_after_terminal_offer(
    session: AsyncSession,
    *,
    offer: CoverageOffer,
    reference_time: datetime,
) -> tuple[list[str], str | None]:
    from app.services import coverage as coverage_service

    next_offers, exhausted_case_id = await coverage_service.advance_case_after_terminal_offer(
        session,
        offer=offer,
        reference_time=reference_time,
    )
    return [str(next_offer.id) for next_offer in next_offers], exhausted_case_id


async def expire_due_offers(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 100,
) -> dict:
    reference_time = now or datetime.now(timezone.utc)
    result = await session.execute(
        select(CoverageOffer)
        .where(
            CoverageOffer.status.in_([OfferStatus.pending, OfferStatus.delivered]),
            CoverageOffer.expires_at.is_not(None),
            CoverageOffer.expires_at <= reference_time,
        )
        .order_by(CoverageOffer.expires_at.asc())
        .limit(limit)
    )
    offers = list(result.scalars().all())

    exhausted_case_ids: list[str] = []
    advanced_offer_ids: list[str] = []

    for offer in offers:
        offer.status = OfferStatus.expired
        offer.offer_metadata = {**offer.offer_metadata, "expired_at": reference_time.isoformat()}
        await mark_offer_attempt_outcome(
            session,
            offer,
            status=CoverageAttemptStatus.expired,
            occurred_at=reference_time,
        )
        await refresh_employee_reliability(session, offer.employee_id, now=reference_time)

        next_offer_ids, exhausted_case_id = await _advance_case_after_terminal_offer(
            session,
            offer=offer,
            reference_time=reference_time,
        )
        advanced_offer_ids.extend(next_offer_ids)
        if exhausted_case_id is not None:
            exhausted_case_ids.append(exhausted_case_id)

    await session.commit()
    return {
        "expired_count": len(offers),
        "exhausted_case_ids": exhausted_case_ids,
        "advanced_offer_ids": advanced_offer_ids,
    }


async def find_latest_actionable_offer_for_phone(
    session: AsyncSession,
    phone_e164: str,
) -> ActionableOfferContext | None:
    result = await session.execute(
        select(CoverageOffer, Shift.business_id)
        .join(CoverageCase, CoverageOffer.coverage_case_id == CoverageCase.id)
        .join(Shift, CoverageCase.shift_id == Shift.id)
        .join(Employee, Employee.id == CoverageOffer.employee_id)
        .where(
            Employee.phone_e164 == phone_e164,
            CoverageOffer.status.in_([OfferStatus.pending, OfferStatus.delivered]),
            CoverageCase.status == CoverageCaseStatus.running,
        )
        .order_by(func.coalesce(CoverageOffer.sent_at, CoverageOffer.created_at).desc())
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None
    offer, business_id = row
    return ActionableOfferContext(offer=offer, business_id=business_id)


async def apply_twilio_status_callback(
    session: AsyncSession,
    *,
    message_sid: str,
    message_status: str,
    error_code: str | None = None,
    error_message: str | None = None,
    raw_payload: dict | None = None,
    occurred_at: datetime | None = None,
) -> dict:
    reference_time = occurred_at or datetime.now(timezone.utc)
    offer = await session.scalar(
        select(CoverageOffer).where(CoverageOffer.provider_message_id == message_sid).limit(1)
    )
    if offer is None:
        return {"matched": False}

    attempt = await session.scalar(
        select(CoverageContactAttempt)
        .where(CoverageContactAttempt.coverage_offer_id == offer.id)
        .order_by(CoverageContactAttempt.attempt_no.desc())
        .limit(1)
    )
    normalized_status = message_status.strip().lower()
    terminal_failure = normalized_status in {"failed", "undelivered"}
    advanced_offer_ids: list[str] = []
    exhausted_case_id = None
    if normalized_status in {"sent", "delivered"}:
        offer.status = OfferStatus.delivered
        if attempt is not None:
            attempt.status = CoverageAttemptStatus.delivered
            attempt.sent_at = attempt.sent_at or reference_time
            if normalized_status == "delivered":
                attempt.delivered_at = reference_time
            attempt.attempt_metadata = {
                **attempt.attempt_metadata,
                "callback": raw_payload or {},
            }
    elif terminal_failure:
        offer.status = OfferStatus.failed
        if attempt is not None:
            attempt.status = CoverageAttemptStatus.failed
            attempt.responded_at = reference_time
            attempt.attempt_metadata = {
                **attempt.attempt_metadata,
                "callback": raw_payload or {},
                "error_code": error_code,
                "error_message": error_message,
            }
        await refresh_employee_reliability(session, offer.employee_id, now=reference_time)
        advanced_offer_ids, exhausted_case_id = await _advance_case_after_terminal_offer(
            session,
            offer=offer,
            reference_time=reference_time,
        )
    else:
        advanced_offer_ids = []
        exhausted_case_id = None

    await session.commit()
    return {
        "matched": True,
        "offer_id": str(offer.id),
        "status": offer.status.value if hasattr(offer.status, "value") else str(offer.status),
        "terminal_failure": terminal_failure,
        "advanced_offer_ids": advanced_offer_ids,
        "advanced_offer_id": advanced_offer_ids[0] if advanced_offer_ids else None,
        "exhausted_case_id": exhausted_case_id,
    }


async def handle_twilio_inbound_reply(
    session: AsyncSession,
    *,
    from_phone: str,
    body: str,
    raw_payload: dict | None = None,
) -> str:
    normalized = " ".join(body.strip().upper().split())
    if normalized not in {"YES", "Y", "ACCEPT", "CONFIRM", "NO", "N", "DECLINE"}:
        return "Reply YES to take the shift or NO to decline."

    context = await find_latest_actionable_offer_for_phone(session, from_phone)
    if context is None:
        return "No active Backfill shift offer is waiting right now."

    action = "accepted" if normalized in {"YES", "Y", "ACCEPT", "CONFIRM"} else "declined"
    from app.services import coverage as coverage_service

    try:
        await coverage_service.respond_to_offer(
            session,
            context.business_id,
            context.offer.id,
            CoverageOfferResponseCreate(
                response=action,
                response_channel="sms",
                response_text=body,
                response_payload=raw_payload or {},
            ),
        )
    except (LookupError, ValueError):
        return "That shift offer is no longer available."

    if action == "accepted":
        return "You're confirmed for the shift. We'll text any final details shortly."
    return "Got it. We'll keep looking for coverage."
