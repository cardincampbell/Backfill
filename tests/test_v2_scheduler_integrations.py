from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app_v2.api.deps import get_auth_context, get_db_session
from app_v2.main import app
from app_v2.models.business import Location
from app_v2.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app_v2.models.identity import Membership, Session, User
from app_v2.models.integrations import SchedulerConnection
from app_v2.services.auth import AuthContext


class FakeSchedulerSession:
    def __init__(self):
        self.added: list[object] = []
        self.commits = 0
        self.scalar_queue: list[object] = []
        self.get_map: dict[tuple[type, object], object] = {}

    def add(self, obj):
        now = datetime.now(timezone.utc)
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = now
        if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
            obj.updated_at = now
        self.added.append(obj)
        self.get_map[(type(obj), obj.id)] = obj

    async def scalar(self, _query):
        if self.scalar_queue:
            return self.scalar_queue.pop(0)
        return None

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None


def _make_auth_context(*, business_id: uuid4, location_id):
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        full_name="Owner User",
        email="owner@example.com",
        primary_phone_e164="+15555550100",
        is_phone_verified=True,
        onboarding_completed_at=now,
        profile_metadata={},
        created_at=now,
        updated_at=now,
    )
    session = Session(
        id=uuid4(),
        user_id=user.id,
        token_hash="hashed",
        risk_level=SessionRiskLevel.low,
        elevated_actions=[],
        last_seen_at=now,
        expires_at=now + timedelta(days=14),
        session_metadata={},
        created_at=now,
        updated_at=now,
    )
    membership = Membership(
        id=uuid4(),
        user_id=user.id,
        business_id=business_id,
        location_id=location_id,
        role=MembershipRole.owner,
        status=MembershipStatus.active,
        membership_metadata={},
        created_at=now,
        updated_at=now,
    )
    return AuthContext(user=user, session=session, memberships=[membership])


def test_v2_put_scheduler_connection_route_returns_webhook_path():
    fake_session = FakeSchedulerSession()
    business_id = uuid4()
    location_id = uuid4()
    now = datetime.now(timezone.utc)
    location = Location(
        id=location_id,
        business_id=business_id,
        name="Downtown",
        slug="downtown",
        address_line_1="123 Main",
        locality="Los Angeles",
        region="CA",
        postal_code="90001",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
        google_place_metadata={},
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    fake_session.get_map[(Location, location_id)] = location
    fake_session.scalar_queue = [None]

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.put(
            f"/api/v2/businesses/{business_id}/locations/{location_id}/scheduler-connection",
            json={
                "provider": "7shifts",
                "provider_location_ref": "company-123",
                "credentials": {
                    "client_id": "client-id",
                    "client_secret": "client-secret",
                },
                "webhook_secret": "whsec_test_secret",
                "writeback_enabled": True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["provider"] == "7shifts"
        assert payload["provider_location_ref"] == "company-123"
        assert payload["writeback_enabled"] is True
        assert payload["webhook_path"].endswith(payload["id"])
        assert location.settings["scheduling_platform"] == "7shifts"
        assert location.settings["writeback_enabled"] is True
    finally:
        app.dependency_overrides.clear()


def test_v2_scheduler_webhook_route_delegates_vacancy_processing(monkeypatch):
    connection = SchedulerConnection(
        id=uuid4(),
        business_id=uuid4(),
        location_id=uuid4(),
        provider="7shifts",
        provider_location_ref="company-123",
        status="active",
        writeback_enabled=True,
        credentials={},
        webhook_secret="whsec_test_secret",
        secret_hint="whse...cret",
        connection_metadata={},
    )

    async def override_db():
        yield object()

    async def fake_resolve(session, *, provider, connection_id=None, payload=None):
        return connection

    async def fake_handle(session, *, provider, payload, connection_id=None):
        return {"status": "queued", "job_id": "job_123"}

    monkeypatch.setattr("app_v2.api.routes.scheduler_provider_webhooks.scheduler_sync.resolve_connection", fake_resolve)
    monkeypatch.setattr("app_v2.api.routes.scheduler_provider_webhooks.scheduler_sync.valid_scheduler_signature", lambda *args: True)
    monkeypatch.setattr("app_v2.api.routes.scheduler_provider_webhooks.scheduler_sync.handle_vacancy_event", fake_handle)

    app.dependency_overrides[get_db_session] = override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v2/providers/schedulers/seven_shifts",
            json={"type": "shift.deleted", "id": "evt_123", "shift_id": "shift_123"},
        )
        assert response.status_code == 200
        assert response.json()["job_id"] == "job_123"
    finally:
        app.dependency_overrides.clear()
