from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import urlparse
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.common import OutboxChannel, OutboxStatus, WebhookDeliveryStatus, WebhookSubscriptionStatus
from app.models.coverage import AuditLog, OutboxEvent
from app.models.webhooks import WebhookDelivery, WebhookSubscription
from app.schemas.webhooks import WebhookSubscriptionCreate, WebhookSubscriptionUpdate

SUPPORTED_WEBHOOK_EVENTS = [
    "business.created",
    "business.profile.updated",
    "coverage.case.created",
    "coverage.dispatch.executed",
    "coverage.phase_1.executed",
    "coverage.phase_2.executed",
    "employee.enrolled",
    "location.created",
    "location.deleted",
    "location.settings.updated",
    "manager_invite.accepted",
    "manager_invite.created",
    "manager_invite.revoked",
    "membership.granted",
    "membership.revoked",
    "onboarding.workspace.bootstrapped",
    "role.created",
    "shift.created",
    "shift.deleted",
    "shift.updated",
]
_SUPPORTED_EVENT_SET = set(SUPPORTED_WEBHOOK_EVENTS)
_RETRY_DELAYS_SECONDS = (60, 300, 900, 3600, 21600)
_RESPONSE_PREVIEW_LIMIT = 1000


@dataclass
class WebhookProcessResult:
    claimed_count: int
    sent_count: int
    failed_count: int
    cancelled_count: int
    processed_event_ids: list[str]


def supported_events() -> list[str]:
    return list(SUPPORTED_WEBHOOK_EVENTS)


def _normalize_event_name(value: object) -> str:
    return str(value).strip()


def normalize_subscribed_events(events: Iterable[str] | None) -> list[str]:
    if not events:
        return []
    normalized: list[str] = []
    for raw in events:
        value = _normalize_event_name(raw)
        if not value:
            continue
        if value not in _SUPPORTED_EVENT_SET:
            raise ValueError(f"unsupported_webhook_event:{value}")
        if value not in normalized:
            normalized.append(value)
    return normalized


def _subscription_accepts_event(subscription: WebhookSubscription, event_name: str) -> bool:
    subscribed_events = list(subscription.subscribed_events or [])
    if not subscribed_events:
        return event_name in _SUPPORTED_EVENT_SET
    return event_name in subscribed_events


def _assert_valid_endpoint_url(endpoint_url: str) -> str:
    parsed = urlparse(endpoint_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("invalid_webhook_endpoint_url")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("webhook_endpoint_must_use_https")
    return endpoint_url.strip()


def generate_signing_secret() -> str:
    return f"bfwhsec_{secrets.token_urlsafe(24)}"


def signing_secret_hint(secret: str) -> str:
    stripped = secret.strip()
    if len(stripped) <= 8:
        return stripped
    return f"{stripped[:8]}...{stripped[-4:]}"


def build_delivery_payload(entry: AuditLog) -> dict:
    return {
        "id": str(entry.id),
        "type": entry.event_name,
        "occurred_at": entry.occurred_at.isoformat() if entry.occurred_at else None,
        "business_id": str(entry.business_id) if entry.business_id else None,
        "location_id": str(entry.location_id) if entry.location_id else None,
        "target": {
            "type": entry.target_type,
            "id": str(entry.target_id) if entry.target_id else None,
        },
        "actor": {
            "type": entry.actor_type.value if hasattr(entry.actor_type, "value") else str(entry.actor_type),
            "user_id": str(entry.actor_user_id) if entry.actor_user_id else None,
            "membership_id": str(entry.actor_membership_id) if entry.actor_membership_id else None,
        },
        "payload": entry.payload or {},
    }


def _signed_body_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_signature(secret: str, *, timestamp: str, payload: dict) -> str:
    signed_payload = f"{timestamp}.".encode("utf-8") + _signed_body_bytes(payload)
    digest = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def build_delivery_headers(*, delivery: WebhookDelivery, secret: str, timestamp: str) -> dict[str, str]:
    signature = build_signature(secret, timestamp=timestamp, payload=delivery.request_payload)
    return {
        "Content-Type": "application/json",
        "User-Agent": "Backfill-Webhooks/1.0",
        "X-Backfill-Delivery-ID": str(delivery.id),
        "X-Backfill-Event": delivery.event_name,
        "X-Backfill-Timestamp": timestamp,
        "X-Backfill-Signature": signature,
    }


def _retry_delay_for_attempt(attempt_count: int) -> int:
    index = max(0, min(attempt_count - 1, len(_RETRY_DELAYS_SECONDS) - 1))
    return _RETRY_DELAYS_SECONDS[index]


async def list_subscriptions(session: AsyncSession, *, business_id: UUID) -> list[WebhookSubscription]:
    result = await session.execute(
        select(WebhookSubscription)
        .where(WebhookSubscription.business_id == business_id)
        .order_by(WebhookSubscription.created_at.asc())
    )
    return list(result.scalars().all())


async def get_subscription(session: AsyncSession, *, business_id: UUID, subscription_id: UUID) -> WebhookSubscription | None:
    subscription = await session.get(WebhookSubscription, subscription_id)
    if subscription is None or subscription.business_id != business_id:
        return None
    return subscription


async def create_subscription(
    session: AsyncSession,
    *,
    business_id: UUID,
    created_by_user_id: UUID,
    payload: WebhookSubscriptionCreate,
) -> tuple[WebhookSubscription, str]:
    secret = generate_signing_secret()
    subscription = WebhookSubscription(
        business_id=business_id,
        created_by_user_id=created_by_user_id,
        endpoint_url=_assert_valid_endpoint_url(payload.endpoint_url),
        description=(payload.description or "").strip() or None,
        status=WebhookSubscriptionStatus.active,
        subscribed_events=normalize_subscribed_events(payload.subscribed_events),
        signing_secret=secret,
        secret_hint=signing_secret_hint(secret),
        subscription_metadata={},
    )
    session.add(subscription)
    await session.flush()
    await session.refresh(subscription)
    return subscription, secret


async def update_subscription(
    session: AsyncSession,
    subscription: WebhookSubscription,
    payload: WebhookSubscriptionUpdate,
) -> WebhookSubscription:
    if payload.endpoint_url is not None:
        subscription.endpoint_url = _assert_valid_endpoint_url(payload.endpoint_url)
    if payload.description is not None:
        subscription.description = payload.description.strip() or None
    if payload.status is not None:
        subscription.status = WebhookSubscriptionStatus(payload.status)
    if payload.subscribed_events is not None:
        subscription.subscribed_events = normalize_subscribed_events(payload.subscribed_events)
    await session.flush()
    await session.refresh(subscription)
    return subscription


async def rotate_subscription_secret(
    session: AsyncSession,
    subscription: WebhookSubscription,
) -> tuple[WebhookSubscription, str]:
    secret = generate_signing_secret()
    subscription.signing_secret = secret
    subscription.secret_hint = signing_secret_hint(secret)
    await session.flush()
    await session.refresh(subscription)
    return subscription, secret


async def list_deliveries(
    session: AsyncSession,
    *,
    business_id: UUID,
    subscription_id: UUID,
    limit: int = 50,
) -> list[WebhookDelivery]:
    result = await session.execute(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.business_id == business_id,
            WebhookDelivery.subscription_id == subscription_id,
        )
        .order_by(WebhookDelivery.created_at.desc())
        .limit(max(1, min(limit, 200)))
    )
    return list(result.scalars().all())


async def enqueue_audit_event(session: AsyncSession, entry: AuditLog) -> list[WebhookDelivery]:
    if entry.business_id is None or entry.event_name not in _SUPPORTED_EVENT_SET:
        return []
    if not hasattr(session, "flush") or not hasattr(session, "execute"):
        return []

    await session.flush()
    result = await session.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.business_id == entry.business_id,
            WebhookSubscription.status == WebhookSubscriptionStatus.active,
        )
    )
    subscriptions = list(result.scalars().all())
    deliveries: list[WebhookDelivery] = []
    for subscription in subscriptions:
        if not _subscription_accepts_event(subscription, entry.event_name):
            continue
        delivery = WebhookDelivery(
            subscription_id=subscription.id,
            business_id=entry.business_id,
            audit_log_id=entry.id,
            event_name=entry.event_name,
            target_type=entry.target_type,
            target_id=entry.target_id,
            endpoint_url=subscription.endpoint_url,
            status=WebhookDeliveryStatus.pending,
            attempt_count=0,
            next_attempt_at=entry.occurred_at,
            request_payload=build_delivery_payload(entry),
            request_headers={},
        )
        session.add(delivery)
        await session.flush()
        outbox_event = OutboxEvent(
            aggregate_type="webhook_delivery",
            aggregate_id=delivery.id,
            topic="webhook.delivery",
            channel=OutboxChannel.webhook,
            status=OutboxStatus.pending,
            attempt_count=0,
            available_at=entry.occurred_at,
            payload={"delivery_id": str(delivery.id)},
            result_payload={},
        )
        session.add(outbox_event)
        await session.flush()
        delivery.outbox_event_id = outbox_event.id
        deliveries.append(delivery)
    return deliveries


async def _claim_due_outbox_events(
    session: AsyncSession,
    *,
    now: datetime,
    limit: int,
) -> list[OutboxEvent]:
    result = await session.execute(
        select(OutboxEvent)
        .where(
            OutboxEvent.channel == OutboxChannel.webhook,
            OutboxEvent.topic == "webhook.delivery",
            OutboxEvent.status.in_([OutboxStatus.pending, OutboxStatus.failed]),
            OutboxEvent.available_at <= now,
        )
        .order_by(OutboxEvent.available_at.asc(), OutboxEvent.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    events = list(result.scalars().all())
    for event in events:
        event.status = OutboxStatus.processing
        event.locked_at = now
    await session.flush()
    return events


def _response_preview(response: httpx.Response | None = None, error_message: str | None = None) -> str | None:
    if response is not None:
        text = response.text.strip()
        return text[:_RESPONSE_PREVIEW_LIMIT] if text else None
    if error_message:
        return error_message[:_RESPONSE_PREVIEW_LIMIT]
    return None


async def _load_delivery(session: AsyncSession, delivery_id: UUID) -> WebhookDelivery | None:
    result = await session.execute(
        select(WebhookDelivery)
        .options(selectinload(WebhookDelivery.subscription))
        .where(WebhookDelivery.id == delivery_id)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _mark_cancelled(
    session: AsyncSession,
    *,
    event: OutboxEvent,
    delivery: WebhookDelivery | None,
    error_message: str,
    now: datetime,
) -> None:
    event.status = OutboxStatus.cancelled
    event.processed_at = now
    event.locked_at = None
    event.error_message = error_message
    if delivery is not None:
        delivery.status = WebhookDeliveryStatus.cancelled
        delivery.error_message = error_message
        delivery.next_attempt_at = None
    await session.flush()


async def process_outbox_batch(session: AsyncSession, *, limit: int = 20) -> WebhookProcessResult:
    reference_time = datetime.now(timezone.utc)
    events = await _claim_due_outbox_events(session, now=reference_time, limit=limit)
    sent_count = 0
    failed_count = 0
    cancelled_count = 0
    processed_event_ids: list[str] = []

    async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
        for event in events:
            processed_event_ids.append(str(event.id))
            delivery_id_raw = (event.payload or {}).get("delivery_id")
            try:
                delivery_id = UUID(str(delivery_id_raw))
            except (TypeError, ValueError):
                await _mark_cancelled(
                    session,
                    event=event,
                    delivery=None,
                    error_message="invalid_webhook_delivery_reference",
                    now=reference_time,
                )
                cancelled_count += 1
                continue

            delivery = await _load_delivery(session, delivery_id)
            if delivery is None or delivery.subscription is None:
                await _mark_cancelled(
                    session,
                    event=event,
                    delivery=delivery,
                    error_message="webhook_delivery_not_found",
                    now=reference_time,
                )
                cancelled_count += 1
                continue

            subscription = delivery.subscription
            if subscription.status != WebhookSubscriptionStatus.active:
                await _mark_cancelled(
                    session,
                    event=event,
                    delivery=delivery,
                    error_message="webhook_subscription_inactive",
                    now=reference_time,
                )
                cancelled_count += 1
                continue

            timestamp = reference_time.isoformat()
            headers = build_delivery_headers(delivery=delivery, secret=subscription.signing_secret, timestamp=timestamp)
            delivery.signature_header = headers["X-Backfill-Signature"]
            delivery.request_headers = headers
            delivery.last_attempted_at = reference_time
            delivery.attempt_count += 1
            delivery.status = WebhookDeliveryStatus.processing
            event.attempt_count += 1
            await session.flush()

            response: httpx.Response | None = None
            error_message: str | None = None
            try:
                response = await client.post(
                    delivery.endpoint_url,
                    content=_signed_body_bytes(delivery.request_payload),
                    headers=headers,
                )
                if 200 <= response.status_code < 300:
                    delivery.status = WebhookDeliveryStatus.succeeded
                    delivery.delivered_at = reference_time
                    delivery.response_status_code = response.status_code
                    delivery.response_body_preview = _response_preview(response=response)
                    delivery.error_message = None
                    delivery.next_attempt_at = None
                    subscription.last_delivery_at = reference_time
                    subscription.failure_count = 0
                    event.status = OutboxStatus.sent
                    event.processed_at = reference_time
                    event.locked_at = None
                    event.result_payload = {"status_code": response.status_code}
                    event.error_message = None
                    sent_count += 1
                    await session.flush()
                    continue
                error_message = f"webhook_http_{response.status_code}"
            except httpx.HTTPError as exc:
                error_message = str(exc)

            delivery.status = WebhookDeliveryStatus.failed
            delivery.response_status_code = response.status_code if response is not None else None
            delivery.response_body_preview = _response_preview(response=response, error_message=error_message)
            delivery.error_message = error_message
            subscription.failure_count = int(subscription.failure_count or 0) + 1

            if delivery.attempt_count >= settings.webhook_max_attempts:
                delivery.next_attempt_at = None
                event.status = OutboxStatus.cancelled
                event.processed_at = reference_time
                event.locked_at = None
                event.error_message = error_message
                cancelled_count += 1
            else:
                next_attempt_at = reference_time + timedelta(seconds=_retry_delay_for_attempt(delivery.attempt_count))
                delivery.next_attempt_at = next_attempt_at
                event.status = OutboxStatus.failed
                event.available_at = next_attempt_at
                event.locked_at = None
                event.error_message = error_message
                event.result_payload = {
                    "status_code": response.status_code if response is not None else None,
                    "retry_at": next_attempt_at.isoformat(),
                }
                failed_count += 1
            await session.flush()

    await session.commit()
    return WebhookProcessResult(
        claimed_count=len(events),
        sent_count=sent_count,
        failed_count=failed_count,
        cancelled_count=cancelled_count,
        processed_event_ids=processed_event_ids,
    )
