from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.business import Business
from app.models.common import AssignmentStatus, CoverageAttemptStatus, CoverageCaseStatus, OfferStatus, OutboxStatus
from app.models.coverage import CoverageCandidate, CoverageCase, CoverageCaseRun, CoverageContactAttempt, CoverageOffer, OutboxEvent
from app.models.scheduling import Shift, ShiftAssignment
from app.models.workforce import Employee
from app.schemas.coverage import CoverageOfferResponseCreate
from app.services import (
    communication_suppressions,
    messaging,
    outreach as outreach_service,
    platform_events,
    retell as retell_service,
    worker_runtime,
)
from app.services.schedule_weeks import effective_week_start_day, schedule_week_window


@dataclass
class DeliverySendResult:
    success: bool
    provider: str = "stub"
    provider_message_id: str | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    error_message: str | None = None
    retryable: bool = False
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
        metadata = build_coverage_offer_voice_metadata(
            offer=offer,
            shift=shift,
            outbox_payload=outbox_event.payload,
        )
        dynamic_variables = build_coverage_offer_voice_dynamic_variables(
            offer=offer,
            shift=shift,
            outbox_payload=outbox_event.payload,
        )
        call_id = await retell_service.create_phone_call(
            to_number=to_number,
            metadata=metadata,
            dynamic_variables=dynamic_variables,
            agent_kind="outbound",
        )
        now = datetime.now(timezone.utc)
        return DeliverySendResult(
            success=True,
            provider="retell",
            provider_message_id=call_id,
            sent_at=now,
            result_payload={"call_id": call_id, "metadata": metadata, "dynamic_variables": dynamic_variables},
        )


@dataclass
class ActionableOfferContext:
    offer: CoverageOffer
    business_id: UUID


_DELIVERY_MAX_ATTEMPTS = 3
COVERAGE_OFFER_OUTBOX_TOPIC = "coverage.offer.created"
SCHEDULE_PUBLISH_NOTIFICATION_TOPIC = "schedule.week.published_notification"


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


def _full_name_parts(full_name: str | None) -> tuple[str, str]:
    text = str(full_name or "").strip()
    if not text:
        return "", ""
    parts = text.split()
    first_name = parts[0].strip()
    last_name = " ".join(parts[1:]).strip()
    return first_name, last_name


def _shift_timezone_name(shift: Shift) -> str:
    return (
        str(getattr(shift, "timezone", "") or "").strip()
        or str(getattr(getattr(shift, "location", None), "timezone", "") or "").strip()
        or "UTC"
    )


def _format_shift_date_label(value: datetime) -> str:
    return value.strftime("%A, %B %d").replace(" 0", " ")


def _format_shift_time_label(value: datetime) -> str:
    return value.strftime("%I:%M %p %Z").lstrip("0").strip()


def _offered_shift_context(*, shift: Shift) -> dict:
    timezone_name = _shift_timezone_name(shift)
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        zone = timezone.utc
    local_start = shift.starts_at.astimezone(zone)
    local_end = shift.ends_at.astimezone(zone)
    location_name = getattr(getattr(shift, "location", None), "name", None) or "your location"
    role_name = getattr(getattr(shift, "role", None), "name", None) or "team member"
    return {
        "shift_id": str(shift.id),
        "location_id": str(shift.location_id),
        "role_id": str(shift.role_id),
        "location_name": location_name,
        "role_name": role_name,
        "date": _format_shift_date_label(local_start),
        "start_time": _format_shift_time_label(local_start),
        "end_time": _format_shift_time_label(local_end),
        "starts_at": shift.starts_at.isoformat(),
        "ends_at": shift.ends_at.isoformat(),
        "timezone": timezone_name,
    }


async def _build_retell_voice_outbound_context(
    session: AsyncSession,
    *,
    offer: CoverageOffer,
    shift: Shift,
) -> dict:
    employee = await session.get(Employee, offer.employee_id)
    business = await session.get(Business, shift.business_id)
    timezone_name = _shift_timezone_name(shift)
    location_settings = getattr(getattr(shift, "location", None), "settings", None)
    business_settings = getattr(business, "settings", None)
    week_start_day = effective_week_start_day(
        business_settings=business_settings if isinstance(business_settings, dict) else None,
        location_settings=location_settings if isinstance(location_settings, dict) else None,
    )
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        zone = timezone.utc
    local_shift_start = shift.starts_at.astimezone(zone)
    week_window = schedule_week_window(timezone_name, week_start_day, local_shift_start.date())

    weekly_assigned_shifts: list[dict] = []
    if employee is not None:
        result = await session.execute(
            select(Shift)
            .options(
                selectinload(Shift.location),
                selectinload(Shift.role),
            )
            .join(ShiftAssignment, ShiftAssignment.shift_id == Shift.id)
            .where(
                ShiftAssignment.employee_id == employee.id,
                ShiftAssignment.status.in_([AssignmentStatus.assigned, AssignmentStatus.accepted]),
                Shift.ends_at >= week_window.starts_at,
                Shift.starts_at <= week_window.ends_at,
            )
            .order_by(Shift.starts_at.asc())
        )
        seen_shift_ids: set[UUID] = set()
        for assigned_shift in result.scalars().all():
            if assigned_shift.id in seen_shift_ids:
                continue
            seen_shift_ids.add(assigned_shift.id)
            assigned_timezone_name = _shift_timezone_name(assigned_shift)
            try:
                assigned_zone = ZoneInfo(assigned_timezone_name)
            except Exception:
                assigned_zone = timezone.utc
            assigned_local_start = assigned_shift.starts_at.astimezone(assigned_zone)
            assigned_local_end = assigned_shift.ends_at.astimezone(assigned_zone)
            weekly_assigned_shifts.append(
                {
                    "shift_id": str(assigned_shift.id),
                    "location_name": getattr(getattr(assigned_shift, "location", None), "name", None) or "your location",
                    "role_name": getattr(getattr(assigned_shift, "role", None), "name", None) or "team member",
                    "date": _format_shift_date_label(assigned_local_start),
                    "start_time": _format_shift_time_label(assigned_local_start),
                    "end_time": _format_shift_time_label(assigned_local_end),
                    "starts_at": assigned_shift.starts_at.isoformat(),
                    "ends_at": assigned_shift.ends_at.isoformat(),
                    "timezone": assigned_timezone_name,
                }
            )

    full_name = getattr(employee, "full_name", None) if employee is not None else (
        str((offer.offer_metadata or {}).get("employee_name") or "").strip() or None
    )
    employee_first_name, employee_last_name = _full_name_parts(full_name)
    offered_shift = _offered_shift_context(shift=shift)
    shift_context = {
        "employee_id": str(offer.employee_id),
        "employee_first_name": employee_first_name,
        "employee_last_name": employee_last_name,
        "week_start_day": week_start_day,
        "week_start_date": week_window.week_start.isoformat(),
        "week_end_date": week_window.week_end.isoformat(),
        "offered_shift": offered_shift,
        "weekly_assigned_shifts": weekly_assigned_shifts,
    }
    return {
        "employee_first_name": employee_first_name,
        "employee_last_name": employee_last_name,
        "location_name": offered_shift["location_name"],
        "role_name": offered_shift["role_name"],
        "shift_date": offered_shift["date"],
        "shift_start_time": offered_shift["start_time"],
        "shift_end_time": offered_shift["end_time"],
        "shift_context": shift_context,
        "shift_context_json": json.dumps(shift_context, separators=(",", ":"), default=str),
    }


def build_coverage_offer_voice_metadata(*, offer: CoverageOffer, shift: Shift, outbox_payload: dict | None = None) -> dict:
    location_name = getattr(getattr(shift, "location", None), "name", None) or "your location"
    role_name = getattr(getattr(shift, "role", None), "name", None) or "team member"
    payload = outbox_payload if isinstance(outbox_payload, dict) else {}
    shift_context = payload.get("shift_context") if isinstance(payload.get("shift_context"), dict) else None
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
        "employee_first_name": str(payload.get("employee_first_name") or "").strip() or None,
        "employee_last_name": str(payload.get("employee_last_name") or "").strip() or None,
        "shift_date": str(payload.get("shift_date") or "").strip() or None,
        "shift_start_time": str(payload.get("shift_start_time") or "").strip() or None,
        "shift_end_time": str(payload.get("shift_end_time") or "").strip() or None,
        "shift_context": shift_context,
    }


def build_coverage_offer_voice_dynamic_variables(
    *,
    offer: CoverageOffer,
    shift: Shift,
    outbox_payload: dict | None = None,
) -> dict:
    payload = outbox_payload if isinstance(outbox_payload, dict) else {}
    location_name = str(payload.get("location_name") or "").strip() or (
        getattr(getattr(shift, "location", None), "name", None) or "your location"
    )
    role_name = str(payload.get("role_name") or "").strip() or (
        getattr(getattr(shift, "role", None), "name", None) or "team member"
    )
    shift_date = str(payload.get("shift_date") or "").strip()
    shift_start_time = str(payload.get("shift_start_time") or "").strip()
    shift_end_time = str(payload.get("shift_end_time") or "").strip()
    if not shift_date or not shift_start_time or not shift_end_time:
        offered_shift = _offered_shift_context(shift=shift)
        shift_date = shift_date or str(offered_shift.get("date") or "")
        shift_start_time = shift_start_time or str(offered_shift.get("start_time") or "")
        shift_end_time = shift_end_time or str(offered_shift.get("end_time") or "")
    return {
        "employee_first_name": str(payload.get("employee_first_name") or "").strip(),
        "employee_last_name": str(payload.get("employee_last_name") or "").strip(),
        "location_name": location_name,
        "role_name": role_name,
        "shift_date": shift_date,
        "shift_start_time": shift_start_time,
        "shift_end_time": shift_end_time,
        "shift_context": str(payload.get("shift_context_json") or "").strip(),
        "offer_id": str(offer.id),
        "premium_cents": int(offer.offer_metadata.get("premium_cents", 0) or 0),
    }


def _resolve_provider_for_channel(channel) -> DeliveryProvider:
    channel_value = channel.value if hasattr(channel, "value") else str(channel)
    if channel_value == "sms":
        return TwilioSMSDeliveryProvider()
    if channel_value == "voice":
        return RetellVoiceDeliveryProvider()
    return StubDeliveryProvider()


def _schedule_notification_destination(
    outbox_event: OutboxEvent,
) -> str | None:
    channel_value = outbox_event.channel.value if hasattr(outbox_event.channel, "value") else str(outbox_event.channel)
    if channel_value == "sms":
        raw_phone = outbox_event.payload.get("phone_e164")
        return str(raw_phone).strip() if raw_phone else None
    if channel_value == "email":
        raw_email = outbox_event.payload.get("email")
        return str(raw_email).strip() if raw_email else None
    return None


async def _suppressed_delivery_result(
    session: AsyncSession,
    *,
    channel_value: str,
    destination: str | None,
    topic: str,
) -> DeliverySendResult | None:
    suppression = await communication_suppressions.get_active_suppression(
        session,
        channel=channel_value,
        destination=destination,
    )
    if suppression is None:
        return None
    return DeliverySendResult(
        success=False,
        provider="suppression",
        error_message="destination_suppressed",
        retryable=False,
        result_payload={
            "topic": topic,
            "suppressed": True,
            "suppression_channel": suppression.channel,
            "suppression_scope": suppression.scope,
            "suppression_reason_code": suppression.reason_code,
            "suppression_source": suppression.source,
        },
    )


def _schedule_notification_failure_result(
    *,
    channel_value: str,
    outbox_event: OutboxEvent,
    exc: Exception,
) -> DeliverySendResult:
    result_payload = {"topic": outbox_event.topic}

    if channel_value == "sms":
        twilio_code = getattr(exc, "code", None)
        twilio_status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
        if twilio_code is not None:
            result_payload["twilio_error_code"] = twilio_code
        if twilio_status is not None:
            result_payload["twilio_status_code"] = twilio_status
        retryable = not (
            twilio_code == 21211
            or (isinstance(twilio_status, int) and 400 <= twilio_status < 500)
        )
        return DeliverySendResult(
            success=False,
            provider="twilio",
            error_message=str(exc),
            retryable=retryable,
            result_payload=result_payload,
        )

    if channel_value == "email":
        retryable = True
        if isinstance(exc, httpx.HTTPStatusError):
            result_payload["sendgrid_status_code"] = exc.response.status_code
            retryable = exc.response.status_code >= 500
        return DeliverySendResult(
            success=False,
            provider="sendgrid",
            error_message=str(exc),
            retryable=retryable,
            result_payload=result_payload,
        )

    return DeliverySendResult(
        success=False,
        provider="stub",
        error_message=str(exc),
        retryable=False,
        result_payload=result_payload,
    )


async def _send_schedule_publish_notification(
    session: AsyncSession,
    *,
    outbox_event: OutboxEvent,
) -> DeliverySendResult:
    channel_value = outbox_event.channel.value if hasattr(outbox_event.channel, "value") else str(outbox_event.channel)
    destination = _schedule_notification_destination(outbox_event)
    if not destination:
        return DeliverySendResult(
            success=False,
            provider="stub",
            error_message="missing_destination",
            result_payload={"topic": outbox_event.topic},
        )

    suppressed = await _suppressed_delivery_result(
        session,
        channel_value=channel_value,
        destination=destination,
        topic=outbox_event.topic,
    )
    if suppressed is not None:
        return suppressed

    subject = str(outbox_event.payload.get("subject") or "Your Backfill schedule is live")
    text_body = str(outbox_event.payload.get("text_body") or "").strip()
    sms_body = str(outbox_event.payload.get("sms_body") or text_body).strip()
    html_body_raw = outbox_event.payload.get("html_body")
    html_body = str(html_body_raw) if isinstance(html_body_raw, str) and html_body_raw.strip() else None
    email_headers_raw = outbox_event.payload.get("email_headers")
    email_headers = (
        {
            str(key): str(value)
            for key, value in email_headers_raw.items()
            if str(key).strip() and str(value).strip()
        }
        if isinstance(email_headers_raw, dict)
        else None
    )
    now = datetime.now(timezone.utc)

    if channel_value == "sms":
        try:
            message = messaging.send_sms(to=destination, body=sms_body)
        except Exception as exc:
            return _schedule_notification_failure_result(
                channel_value=channel_value,
                outbox_event=outbox_event,
                exc=exc,
            )
        return DeliverySendResult(
            success=True,
            provider="twilio",
            provider_message_id=message.get("sid"),
            sent_at=now,
            result_payload={
                "topic": outbox_event.topic,
                "status": message.get("status"),
            },
        )

    if channel_value == "email":
        try:
            message_id = messaging.send_email(
                to=destination,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                headers=email_headers,
            )
        except Exception as exc:
            return _schedule_notification_failure_result(
                channel_value=channel_value,
                outbox_event=outbox_event,
                exc=exc,
            )
        return DeliverySendResult(
            success=True,
            provider="sendgrid",
            provider_message_id=message_id,
            sent_at=now,
            result_payload={"topic": outbox_event.topic},
        )

    return DeliverySendResult(
        success=False,
        provider="stub",
        error_message="unsupported_notification_channel",
        result_payload={"channel": channel_value, "topic": outbox_event.topic},
    )


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
        attempt.attempt_metadata = {
            **(attempt.attempt_metadata or {}),
            "response_payload": response_payload,
        }
    await session.flush()
    return attempt


async def _coverage_outbox_business_keys(
    session: AsyncSession,
    events: list[OutboxEvent],
) -> dict[object, object | None]:
    business_by_event_id: dict[object, object | None] = {}
    offer_ids = [
        event.aggregate_id
        for event in events
        if event.aggregate_id is not None and event.topic == COVERAGE_OFFER_OUTBOX_TOPIC
    ]
    if not offer_ids:
        for event in events:
            if event.topic == SCHEDULE_PUBLISH_NOTIFICATION_TOPIC:
                raw_business_id = event.payload.get("business_id")
                business_by_event_id[event.id] = raw_business_id
        return business_by_event_id
    result = await session.execute(
        select(CoverageOffer.id, Shift.business_id)
        .join(CoverageCase, CoverageOffer.coverage_case_id == CoverageCase.id)
        .join(Shift, CoverageCase.shift_id == Shift.id)
        .where(CoverageOffer.id.in_(offer_ids))
    )
    business_by_offer_id = {
        offer_id: business_id
        for offer_id, business_id in result.all()
    }
    for event in events:
        if event.topic == COVERAGE_OFFER_OUTBOX_TOPIC:
            business_by_event_id[event.id] = business_by_offer_id.get(event.aggregate_id)
            continue
        if event.topic == SCHEDULE_PUBLISH_NOTIFICATION_TOPIC:
            business_by_event_id[event.id] = event.payload.get("business_id")
    return business_by_event_id


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
    events = await worker_runtime.claim_outbox_events(
        session,
        now=reference_time,
        limit=limit,
        topic=(COVERAGE_OFFER_OUTBOX_TOPIC, SCHEDULE_PUBLISH_NOTIFICATION_TOPIC),
        business_resolver=_coverage_outbox_business_keys,
    )

    sent_count = 0
    failed_count = 0
    processed_event_ids: list[str] = []

    for event in events:
        if event.topic == SCHEDULE_PUBLISH_NOTIFICATION_TOPIC:
            try:
                result = await _send_schedule_publish_notification(session, outbox_event=event)
            except Exception as exc:
                retryable = event.attempt_count < _DELIVERY_MAX_ATTEMPTS
                error_message = str(exc)
                if retryable:
                    worker_runtime.mark_outbox_event_retry(
                        event,
                        now=reference_time,
                        next_attempt_at=reference_time + worker_runtime.retry_delay_for_attempt(event.attempt_count),
                        error_message=error_message,
                        result_payload={"topic": event.topic},
                    )
                else:
                    worker_runtime.mark_outbox_event_cancelled(
                        event,
                        now=reference_time,
                        error_message=error_message,
                        result_payload={"topic": event.topic},
                    )
                failed_count += 1
                processed_event_ids.append(str(event.id))
                continue

            if result.success:
                worker_runtime.mark_outbox_event_sent(
                    event,
                    now=reference_time,
                    result_payload=result.result_payload,
                )
                sent_count += 1
            else:
                retryable = bool(result.retryable) and event.attempt_count < _DELIVERY_MAX_ATTEMPTS
                if retryable:
                    worker_runtime.mark_outbox_event_retry(
                        event,
                        now=reference_time,
                        next_attempt_at=reference_time + worker_runtime.retry_delay_for_attempt(event.attempt_count),
                        error_message=result.error_message or "delivery_retry_scheduled",
                        result_payload=result.result_payload,
                    )
                else:
                    worker_runtime.mark_outbox_event_cancelled(
                        event,
                        now=reference_time,
                        error_message=result.error_message or "delivery_failed",
                        result_payload=result.result_payload,
                    )
                failed_count += 1
            processed_event_ids.append(str(event.id))
            continue

        offer = await session.get(CoverageOffer, event.aggregate_id)
        if offer is None:
            worker_runtime.mark_outbox_event_cancelled(
                event,
                now=reference_time,
                error_message="coverage_offer_not_found",
            )
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
            worker_runtime.mark_outbox_event_cancelled(
                event,
                now=reference_time,
                error_message="shift_not_found",
            )
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

        destination = None
        channel_value = offer.channel.value if hasattr(offer.channel, "value") else str(offer.channel)
        if channel_value == "sms":
            raw_phone = event.payload.get("phone_e164") or offer.offer_metadata.get("phone_e164")
            destination = str(raw_phone).strip() if raw_phone else None
        elif channel_value == "email":
            raw_email = event.payload.get("email") or offer.offer_metadata.get("email")
            destination = str(raw_email).strip() if raw_email else None

        suppressed_result = await _suppressed_delivery_result(
            session,
            channel_value=channel_value,
            destination=destination,
            topic=event.topic,
        )
        if suppressed_result is not None:
            advanced_offer_ids, exhausted_case_id = await _handle_terminal_offer_failure(
                session,
                offer=offer,
                attempt=attempt,
                reference_time=reference_time,
                error_message=suppressed_result.error_message or "destination_suppressed",
                result_payload=suppressed_result.result_payload,
            )
            worker_runtime.mark_outbox_event_cancelled(
                event,
                now=reference_time,
                error_message=suppressed_result.error_message or "destination_suppressed",
                result_payload={
                    **suppressed_result.result_payload,
                    "advanced_offer_ids": advanced_offer_ids,
                    "exhausted_case_id": exhausted_case_id,
                },
            )
            failed_count += 1
            processed_event_ids.append(str(event.id))
            continue

        active_provider = provider or _resolve_provider_for_channel(offer.channel)
        if channel_value == "voice":
            retell_context = await _build_retell_voice_outbound_context(
                session,
                offer=offer,
                shift=shift,
            )
            event.payload = {
                **(event.payload or {}),
                **retell_context,
            }
        try:
            result = await active_provider.send_coverage_offer(
                outbox_event=event,
                offer=offer,
                shift=shift,
            )
        except Exception as exc:
            retryable = event.attempt_count < _DELIVERY_MAX_ATTEMPTS
            error_message = str(exc)
            if retryable:
                attempt.status = CoverageAttemptStatus.failed
                attempt.responded_at = reference_time
                attempt.attempt_metadata = {
                    **(attempt.attempt_metadata or {}),
                    "worker_error": error_message,
                }
                offer.status = OfferStatus.pending
                worker_runtime.mark_outbox_event_retry(
                    event,
                    now=reference_time,
                    next_attempt_at=reference_time + worker_runtime.retry_delay_for_attempt(event.attempt_count),
                    error_message=error_message,
                )
            else:
                advanced_offer_ids, exhausted_case_id = await _handle_terminal_offer_failure(
                    session,
                    offer=offer,
                    attempt=attempt,
                    reference_time=reference_time,
                    error_message=error_message,
                )
                worker_runtime.mark_outbox_event_cancelled(
                    event,
                    now=reference_time,
                    error_message=error_message,
                    result_payload={
                        "advanced_offer_ids": advanced_offer_ids,
                        "exhausted_case_id": exhausted_case_id,
                    },
                )
            failed_count += 1
            processed_event_ids.append(str(event.id))
            continue

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
            attempt.attempt_metadata = {
                **(attempt.attempt_metadata or {}),
                **result.result_payload,
            }

            worker_runtime.mark_outbox_event_sent(
                event,
                now=reference_time,
                result_payload=result.result_payload,
            )
            await outreach_service.append_outreach_attempt_event(
                session,
                event_type=platform_events.PlatformEventType.COVERAGE_OUTREACH_ATTEMPT_AWAITING_RESPONSE,
                offer=offer,
                business_id=shift.business_id,
                location_id=shift.location_id,
                shift_id=shift.id,
                attempt=attempt,
                metadata={
                    "channel": "worker_runtime",
                    "provider": result.provider,
                },
            )
            sent_count += 1
        else:
            retryable = bool(result.retryable) and event.attempt_count < _DELIVERY_MAX_ATTEMPTS
            if retryable:
                attempt.status = CoverageAttemptStatus.failed
                attempt.responded_at = reference_time
                attempt.attempt_metadata = {
                    **(attempt.attempt_metadata or {}),
                    **result.result_payload,
                }
                offer.status = OfferStatus.pending
                worker_runtime.mark_outbox_event_retry(
                    event,
                    now=reference_time,
                    next_attempt_at=reference_time + worker_runtime.retry_delay_for_attempt(event.attempt_count),
                    error_message=result.error_message or "delivery_retry_scheduled",
                    result_payload=result.result_payload,
                )
            else:
                advanced_offer_ids, exhausted_case_id = await _handle_terminal_offer_failure(
                    session,
                    offer=offer,
                    attempt=attempt,
                    reference_time=reference_time,
                    error_message=result.error_message or "delivery_failed",
                    result_payload=result.result_payload,
                )
                worker_runtime.mark_outbox_event_cancelled(
                    event,
                    now=reference_time,
                    error_message=result.error_message or "delivery_failed",
                    result_payload={
                        **result.result_payload,
                        "advanced_offer_ids": advanced_offer_ids,
                        "exhausted_case_id": exhausted_case_id,
                    },
                )
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


async def _handle_terminal_offer_failure(
    session: AsyncSession,
    *,
    offer: CoverageOffer,
    attempt: CoverageContactAttempt | None,
    reference_time: datetime,
    error_message: str,
    result_payload: dict | None = None,
) -> tuple[list[str], str | None]:
    offer.status = OfferStatus.failed
    offer.offer_metadata = {
        **(offer.offer_metadata or {}),
        "terminal_failure_at": reference_time.isoformat(),
        "terminal_failure_reason": error_message,
    }
    if attempt is not None:
        attempt.status = CoverageAttemptStatus.failed
        attempt.responded_at = reference_time
        attempt.attempt_metadata = {
            **(attempt.attempt_metadata or {}),
            **(result_payload or {}),
            "worker_error": error_message,
        }
    await outreach_service.append_outreach_attempt_event(
        session,
        event_type=platform_events.PlatformEventType.COVERAGE_OUTREACH_ATTEMPT_FAILED,
        offer=offer,
        attempt=attempt,
        metadata={
            "channel": "worker_runtime",
            "error_message": error_message,
        },
    )
    await refresh_employee_reliability(session, offer.employee_id, now=reference_time)
    return await _advance_case_after_terminal_offer(
        session,
        offer=offer,
        reference_time=reference_time,
    )


async def expire_due_offers(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 100,
) -> dict:
    reference_time = now or datetime.now(timezone.utc)
    offers = await worker_runtime.claim_expiring_coverage_offers(
        session,
        now=reference_time,
        limit=limit,
    )

    exhausted_case_ids: list[str] = []
    advanced_offer_ids: list[str] = []

    for offer in offers:
        offer.status = OfferStatus.expired
        offer.offer_metadata = {**offer.offer_metadata, "expired_at": reference_time.isoformat()}
        attempt = await mark_offer_attempt_outcome(
            session,
            offer,
            status=CoverageAttemptStatus.expired,
            occurred_at=reference_time,
        )
        await outreach_service.append_outreach_attempt_event(
            session,
            event_type=platform_events.PlatformEventType.COVERAGE_OUTREACH_ATTEMPT_EXPIRED,
            offer=offer,
            attempt=attempt,
            metadata={
                "channel": "worker_runtime",
            },
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
                **(attempt.attempt_metadata or {}),
                "callback": raw_payload or {},
            }
    elif terminal_failure:
        offer.status = OfferStatus.failed
        if attempt is not None:
            attempt.status = CoverageAttemptStatus.failed
            attempt.responded_at = reference_time
            attempt.attempt_metadata = {
                **(attempt.attempt_metadata or {}),
                "callback": raw_payload or {},
                "error_code": error_code,
                "error_message": error_message,
            }
        await outreach_service.append_outreach_attempt_event(
            session,
            event_type=platform_events.PlatformEventType.COVERAGE_OUTREACH_ATTEMPT_FAILED,
            offer=offer,
            attempt=attempt,
            metadata={
                "channel": "provider_callback",
                "provider": "twilio",
                "error_code": error_code,
            },
        )
        await refresh_employee_reliability(session, offer.employee_id, now=reference_time)
        advanced_offer_ids, exhausted_case_id = await _advance_case_after_terminal_offer(
            session,
            offer=offer,
            reference_time=reference_time,
        )
    else:
        advanced_offer_ids = []
        exhausted_case_id = None

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
    command_result = await communication_suppressions.handle_inbound_sms_command(
        session,
        from_phone=from_phone,
        body=body,
        raw_payload=raw_payload,
    )
    if command_result.handled:
        return command_result.response_text or "Backfill SMS preference updated."

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
