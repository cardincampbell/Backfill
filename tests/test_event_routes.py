from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app.models.identity import Membership, Session, User
from app.schemas.events import PlatformEventRead
from app.services import feed_projections
from app.services.auth import AuthContext


class FakeEventSession:
    pass


def _make_auth_context(*, business_id, role=MembershipRole.manager) -> AuthContext:
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        full_name="Jordan Lead",
        email="jordan@example.com",
        primary_phone_e164="+15555550131",
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
        expires_at=now,
        session_metadata={},
        created_at=now,
        updated_at=now,
    )
    membership = Membership(
        id=uuid4(),
        user_id=user.id,
        business_id=business_id,
        role=role,
        status=MembershipStatus.active,
        accepted_at=now,
        membership_metadata={},
        created_at=now,
        updated_at=now,
    )
    return AuthContext(user=user, session=session, memberships=[membership])


def test_list_platform_events_returns_canonical_events(monkeypatch):
    fake_session = FakeEventSession()
    business_id = uuid4()
    location_id = uuid4()
    event_id = uuid4()
    now = datetime(2026, 4, 10, 18, 30, tzinfo=timezone.utc)

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    async def fake_list_events(_session, **kwargs):
        assert kwargs["business_id"] == business_id
        assert kwargs["location_id"] == location_id
        return [
            PlatformEventRead(
                id=event_id,
                business_id=business_id,
                location_id=location_id,
                schema_version=1,
                event_type="billing.fill.charged",
                compatibility_event_name="billing.fill.charged",
                entity_type="coverage_case",
                entity_id=uuid4(),
                actor_type="system",
                actor_user_id=None,
                actor_membership_id=None,
                trace_id="trace_123",
                ip_address=None,
                user_agent=None,
                payload={"amount_cents": 2000},
                event_metadata={"channel": "system"},
                error_message=None,
                occurred_at=now,
            )
        ]

    monkeypatch.setattr(feed_projections, "list_feed_events", fake_list_events)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(f"/api/businesses/{business_id}/events?location_id={location_id}")
        assert response.status_code == 200
        assert response.json() == [
            {
                "id": str(event_id),
                "business_id": str(business_id),
                "location_id": str(location_id),
                "schema_version": 1,
                "event_type": "billing.fill.charged",
                "compatibility_event_name": "billing.fill.charged",
                "entity_type": "coverage_case",
                "entity_id": response.json()[0]["entity_id"],
                "actor_type": "system",
                "actor_user_id": None,
                "actor_membership_id": None,
                "trace_id": "trace_123",
                "ip_address": None,
                "user_agent": None,
                "payload": {"amount_cents": 2000},
                "event_metadata": {"channel": "system"},
                "error_message": None,
                "occurred_at": "2026-04-10T18:30:00Z",
            }
        ]
    finally:
        app.dependency_overrides.clear()


def test_list_platform_events_requires_business_access():
    fake_session = FakeEventSession()
    business_id = uuid4()

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, role=MembershipRole.viewer)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(f"/api/businesses/{business_id}/events")
        assert response.status_code == 403
        assert response.json()["detail"] == "business_access_denied"
    finally:
        app.dependency_overrides.clear()
