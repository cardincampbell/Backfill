from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.api.deps import get_auth_context
from app.config import settings
from app.db.session import get_db_session
from app.main import app
from app.models.common import (
    AuditActorType,
    MembershipRole,
    MembershipStatus,
    OutboxChannel,
    OutboxStatus,
    SessionRiskLevel,
    WebhookDeliveryStatus,
    WebhookSubscriptionStatus,
)
from app.models.coverage import AuditLog, OutboxEvent
from app.models.identity import Membership, Session, User
from app.models.webhooks import WebhookDelivery, WebhookSubscription
from app.schemas.webhooks import WebhookSubscriptionCreate
from app.services import webhooks
from app.services.auth import AuthContext


class _ScalarList:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)


class _ExecuteResult:
    def __init__(self, *, values=None, scalar_value=None):
        self._values = values or []
        self._scalar_value = scalar_value

    def scalars(self):
        return _ScalarList(self._values)

    def scalar_one_or_none(self):
        return self._scalar_value


class FakeWebhookSession:
    def __init__(self):
        self.added: list[object] = []
        self.commits = 0
        self.flushed = 0
        self.execute_queue: list[_ExecuteResult] = []
        self.get_map: dict[tuple[type, object], object] = {}

    def add(self, obj):
        now = datetime.now(timezone.utc)
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = now
        if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
            obj.updated_at = now
        if isinstance(obj, OutboxEvent):
            obj.attempt_count = int(obj.attempt_count or 0)
        if isinstance(obj, WebhookDelivery):
            obj.attempt_count = int(obj.attempt_count or 0)
        if isinstance(obj, WebhookSubscription):
            obj.failure_count = int(obj.failure_count or 0)
        self.added.append(obj)
        self.get_map[(type(obj), obj.id)] = obj

    async def flush(self):
        self.flushed += 1

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None

    async def execute(self, _query):
        return self.execute_queue.pop(0)

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))


def _make_auth_context(*, business_id):
    user = User(
        id=uuid4(),
        full_name="Owner User",
        email="owner@example.com",
        primary_phone_e164="+15555550100",
        is_phone_verified=True,
        onboarding_completed_at=datetime.now(timezone.utc),
        profile_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session = Session(
        id=uuid4(),
        user_id=user.id,
        token_hash="hashed",
        risk_level=SessionRiskLevel.low,
        elevated_actions=[],
        last_seen_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
        session_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    membership = Membership(
        id=uuid4(),
        user_id=user.id,
        business_id=business_id,
        role=MembershipRole.owner,
        status=MembershipStatus.active,
        membership_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    return AuthContext(user=user, session=session, memberships=[membership])


def test_create_webhook_route_returns_signing_secret():
    business_id = uuid4()
    session = FakeWebhookSession()
    auth_ctx = _make_auth_context(business_id=business_id)

    async def override_db():
        yield session

    async def override_auth():
        return auth_ctx

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/businesses/{business_id}/webhooks",
            json={
                "endpoint_url": "https://example.com/backfill",
                "description": "Primary endpoint",
                "subscribed_events": ["shift.created"],
            },
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["subscription"]["endpoint_url"] == "https://example.com/backfill"
        assert payload["subscription"]["subscribed_events"] == ["shift.created"]
        assert payload["signing_secret"].startswith("bfwhsec_")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_enqueue_audit_event_creates_delivery_and_outbox():
    business_id = uuid4()
    session = FakeWebhookSession()
    subscription = WebhookSubscription(
        id=uuid4(),
        business_id=business_id,
        created_by_user_id=uuid4(),
        endpoint_url="https://example.com/backfill",
        description="Primary endpoint",
        status=WebhookSubscriptionStatus.active,
        subscribed_events=["shift.created"],
        signing_secret="bfwhsec_test_secret",
        secret_hint="bfwhsec_...cret",
        failure_count=0,
        subscription_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.execute_queue = [_ExecuteResult(values=[subscription])]
    entry = AuditLog(
        id=uuid4(),
        business_id=business_id,
        location_id=uuid4(),
        actor_type=AuditActorType.user,
        actor_user_id=uuid4(),
        actor_membership_id=uuid4(),
        event_name="shift.created",
        target_type="shift",
        target_id=uuid4(),
        ip_address="127.0.0.1",
        user_agent="pytest",
        payload={"shift_id": "shift_123"},
        occurred_at=datetime.now(timezone.utc),
    )
    session.add(entry)

    deliveries = await webhooks.enqueue_audit_event(session, entry)

    outbox = [obj for obj in session.added if isinstance(obj, OutboxEvent)]
    assert len(deliveries) == 1
    assert deliveries[0].event_name == "shift.created"
    assert deliveries[0].status == WebhookDeliveryStatus.pending
    assert len(outbox) == 1
    assert outbox[0].channel == OutboxChannel.webhook
    assert outbox[0].topic == "webhook.delivery"


@pytest.mark.asyncio
async def test_process_webhook_outbox_success(monkeypatch):
    business_id = uuid4()
    subscription = WebhookSubscription(
        id=uuid4(),
        business_id=business_id,
        created_by_user_id=uuid4(),
        endpoint_url="https://example.com/backfill",
        description="Primary endpoint",
        status=WebhookSubscriptionStatus.active,
        subscribed_events=["shift.created"],
        signing_secret="bfwhsec_test_secret",
        secret_hint="bfwhsec_...cret",
        failure_count=0,
        subscription_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    delivery = WebhookDelivery(
        id=uuid4(),
        subscription_id=subscription.id,
        business_id=business_id,
        audit_log_id=uuid4(),
        outbox_event_id=uuid4(),
        event_name="shift.created",
        target_type="shift",
        target_id=uuid4(),
        endpoint_url=subscription.endpoint_url,
        status=WebhookDeliveryStatus.pending,
        attempt_count=0,
        next_attempt_at=datetime.now(timezone.utc),
        request_payload={"id": "evt_123", "type": "shift.created"},
        request_headers={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    delivery.subscription = subscription
    event = OutboxEvent(
        id=delivery.outbox_event_id,
        aggregate_type="webhook_delivery",
        aggregate_id=delivery.id,
        topic="webhook.delivery",
        channel=OutboxChannel.webhook,
        status=OutboxStatus.pending,
        attempt_count=0,
        available_at=datetime.now(timezone.utc),
        payload={"delivery_id": str(delivery.id)},
        result_payload={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    session = FakeWebhookSession()
    session.execute_queue = [
        _ExecuteResult(values=[event]),
        _ExecuteResult(scalar_value=delivery),
    ]

    class FakeResponse:
        status_code = 202
        text = "accepted"

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, content, headers):
            assert url == "https://example.com/backfill"
            assert headers["X-Backfill-Event"] == "shift.created"
            assert headers["X-Backfill-Signature"].startswith("sha256=")
            assert content
            return FakeResponse()

    monkeypatch.setattr("app.services.webhooks.httpx.AsyncClient", FakeAsyncClient)

    result = await webhooks.process_outbox_batch(session, limit=20)

    assert result.claimed_count == 1
    assert result.sent_count == 1
    assert delivery.status == WebhookDeliveryStatus.succeeded
    assert delivery.signature_header is not None
    assert event.status == OutboxStatus.sent
    assert session.commits == 1
