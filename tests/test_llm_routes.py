from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.ai import LlmGeneration
from app.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app.models.identity import Membership, Session, User
from app.services import llm_gateway
from app.services.auth import AuthContext


class FakeLlmRouteSession:
    pass


def _make_auth_context(*, business_id, location_id=None, role=MembershipRole.manager) -> AuthContext:
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
        location_id=location_id,
        role=role,
        status=MembershipStatus.active,
        accepted_at=now,
        membership_metadata={},
        created_at=now,
        updated_at=now,
    )
    return AuthContext(user=user, session=session, memberships=[membership])


def _make_generation(*, business_id, location_id=None, generation_id=None) -> LlmGeneration:
    now = datetime(2026, 4, 10, 18, 30, tzinfo=timezone.utc)
    return LlmGeneration(
        id=generation_id or uuid4(),
        business_id=business_id,
        location_id=location_id,
        provider="openai",
        model="gpt-test",
        purpose="intent_resolution",
        status="succeeded",
        trace_id="trace_123",
        provider_generation_id="resp_123",
        finish_reason="stop",
        output_text="Ready to publish.",
        input_tokens=120,
        output_tokens=32,
        total_tokens=152,
        estimated_cost_micros=4100,
        latency_ms=850,
        request_payload={"messages": [{"role": "user", "content": "Publish next week"}]},
        response_payload={"id": "resp_123"},
        tool_calls=[{"name": "schedule.publish", "arguments": {"location_id": "loc_1"}}],
        generation_metadata={"trace_id": "trace_123", "channel": "dashboard"},
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )


def test_list_llm_generations_returns_summaries(monkeypatch):
    fake_session = FakeLlmRouteSession()
    business_id = uuid4()
    location_id = uuid4()
    row = _make_generation(business_id=business_id, location_id=location_id)

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    async def fake_list_generations(_session, **kwargs):
        assert kwargs["business_id"] == business_id
        assert kwargs["location_id"] == location_id
        assert kwargs["purpose"] == "intent_resolution"
        assert kwargs["provider"] == "openai"
        assert kwargs["trace_id"] == "trace_123"
        assert kwargs["limit"] == 10
        return [row]

    monkeypatch.setattr(llm_gateway, "list_generations", fake_list_generations)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/llm-generations"
            f"?location_id={location_id}&purpose=intent_resolution&provider=openai&trace_id=trace_123&limit=10"
        )
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["id"] == str(row.id)
        assert payload[0]["provider"] == "openai"
        assert payload[0]["model"] == "gpt-test"
        assert payload[0]["total_tokens"] == 152
        assert "request_payload" not in payload[0]
    finally:
        app.dependency_overrides.clear()


def test_get_llm_generation_returns_detail(monkeypatch):
    fake_session = FakeLlmRouteSession()
    business_id = uuid4()
    row = _make_generation(business_id=business_id)

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    async def fake_get_generation(_session, **kwargs):
        assert kwargs["business_id"] == business_id
        assert kwargs["generation_id"] == row.id
        return row

    monkeypatch.setattr(llm_gateway, "get_generation", fake_get_generation)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(f"/api/businesses/{business_id}/llm-generations/{row.id}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == str(row.id)
        assert payload["request_payload"]["messages"][0]["content"] == "Publish next week"
        assert payload["tool_calls"][0]["name"] == "schedule.publish"
        assert payload["generation_metadata"]["channel"] == "dashboard"
    finally:
        app.dependency_overrides.clear()


def test_get_llm_generation_enforces_business_access():
    fake_session = FakeLlmRouteSession()
    business_id = uuid4()
    generation_id = uuid4()

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, role=MembershipRole.viewer)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(f"/api/businesses/{business_id}/llm-generations/{generation_id}")
        assert response.status_code == 403
        assert response.json()["detail"] == "business_access_denied"
    finally:
        app.dependency_overrides.clear()
