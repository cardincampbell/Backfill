from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.domain.copilot import registry, validation
from app.main import app
from app.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app.models.identity import Membership, Session, User
from app.schemas.copilot import (
    CopilotActionRunRead,
    CopilotIntentRead,
    CopilotMessageRead,
    CopilotSessionDetailRead,
    CopilotSessionRead,
    CopilotValidationResultRead,
)
from app.services.auth import AuthContext


class FakeCopilotSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


def _make_auth_context(*, business_id, location_id=None, role=MembershipRole.manager) -> AuthContext:
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        full_name="Jordan Lead",
        email="jordan@example.com",
        primary_phone_e164="+15555550111",
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
        expires_at=now + timedelta(days=1),
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


def _detail(*, business_id, user_id, location_id=None) -> CopilotSessionDetailRead:
    now = datetime.now(timezone.utc)
    session_id = uuid4()
    session = CopilotSessionRead(
        id=session_id,
        business_id=business_id,
        location_id=location_id,
        operator_user_id=user_id,
        channel_last_seen="dashboard",
        state="active",
        context_profile={"business_name": "Backfill"},
        working_memory={},
        created_at=now,
        expires_at=now + timedelta(hours=12),
        last_message_at=now,
    )
    greeting = CopilotMessageRead(
        id=uuid4(),
        copilot_session_id=session_id,
        direction="outbound",
        normalized_channel="dashboard",
        raw_text="Hi Jordan. I can summarize open shifts, active campaigns, and manager actions for you.",
        normalized_text="hi jordan. i can summarize open shifts, active campaigns, and manager actions for you.",
        message_metadata={"message_kind": "greeting"},
        created_at=now,
    )
    return CopilotSessionDetailRead(session=session, tools=registry.list_tools(), messages=[greeting], action_runs=[])


@pytest.mark.asyncio
async def test_registry_resolves_campaign_and_schedule_intents():
    active_campaigns = registry.resolve_intent("Show active coverage campaigns")
    open_shifts = registry.resolve_intent("Show me open shifts this week")

    assert active_campaigns.tool_name == "coverage.list_active_campaigns"
    assert active_campaigns.family == "coverage"
    assert open_shifts.tool_name == "schedule.list_open_shifts"
    assert open_shifts.family == "schedule"


def test_validation_rejects_campaign_start_tool():
    business_id = uuid4()
    auth_ctx = _make_auth_context(business_id=business_id)

    result = validation.validate_tool_call(
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=None,
        tool_name="coverage.start_campaign",
    )

    assert result.ok is False
    assert result.code == "tool_not_available"


def test_list_tools_route_returns_campaign_oriented_tools(client: TestClient):
    business_id = uuid4()

    async def override_db():
        yield FakeCopilotSession()

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        response = client.get(f"/api/businesses/{business_id}/copilot/tools")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    tool_names = {item["name"] for item in payload}
    assert "coverage.list_active_campaigns" in tool_names
    assert "schedule.list_open_shifts" in tool_names
    assert "coverage.start_campaign" not in tool_names


def test_create_session_route_returns_copilot_session_shape(client: TestClient, monkeypatch):
    business_id = uuid4()
    auth_ctx = _make_auth_context(business_id=business_id)
    fake_db = FakeCopilotSession()
    detail = _detail(business_id=business_id, user_id=auth_ctx.user.id)

    async def override_db():
        yield fake_db

    async def override_auth():
        return auth_ctx

    async def fake_create_or_reuse_session(_db, **kwargs):
        assert kwargs["business_id"] == business_id
        return detail

    monkeypatch.setattr(
        "app.api.routes.copilot.copilot_runtime.create_or_reuse_session",
        fake_create_or_reuse_session,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        response = client.post(
            f"/api/businesses/{business_id}/copilot/sessions",
            json={"normalized_channel": "dashboard", "reuse_active": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["session"]["business_id"] == str(business_id)
    assert payload["messages"][0]["message_metadata"]["message_kind"] == "greeting"
    assert fake_db.commits == 1


def test_create_message_route_returns_turn_shape(client: TestClient, monkeypatch):
    business_id = uuid4()
    auth_ctx = _make_auth_context(business_id=business_id)
    fake_db = FakeCopilotSession()
    detail = _detail(business_id=business_id, user_id=auth_ctx.user.id)
    session_id = detail.session.id
    now = datetime.now(timezone.utc)
    turn = {
        "session": detail.session.model_dump(mode="json"),
        "resolved_intent": CopilotIntentRead(
            family="coverage",
            tool_name="coverage.list_active_campaigns",
            reasoning="The request is asking for campaign status.",
            confidence=0.9,
        ).model_dump(mode="json"),
        "inbound_message": CopilotMessageRead(
            id=uuid4(),
            copilot_session_id=session_id,
            direction="inbound",
            normalized_channel="dashboard",
            raw_text="Show active coverage campaigns",
            normalized_text="show active coverage campaigns",
            message_metadata={},
            created_at=now,
        ).model_dump(mode="json"),
        "outbound_message": CopilotMessageRead(
            id=uuid4(),
            copilot_session_id=session_id,
            direction="outbound",
            normalized_channel="dashboard",
            raw_text="There are 2 active campaigns: 1 running and 1 queued.",
            normalized_text="there are 2 active campaigns: 1 running and 1 queued.",
            message_metadata={"message_kind": "tool_result"},
            created_at=now,
        ).model_dump(mode="json"),
        "action_run": CopilotActionRunRead(
            id=uuid4(),
            copilot_session_id=session_id,
            tool_name="coverage.list_active_campaigns",
            status="executed",
            input_payload={"business_id": str(business_id)},
            validation_result=CopilotValidationResultRead(ok=True, code="ok", message="Tool call validated."),
            result_payload={"kind": "campaigns", "total_active_campaigns": 2},
            error_payload={},
            started_at=now,
            finished_at=now,
        ).model_dump(mode="json"),
        "tools": [tool.model_dump(mode="json") for tool in registry.list_tools()],
    }

    async def override_db():
        yield fake_db

    async def override_auth():
        return auth_ctx

    async def fake_create_turn(_db, **kwargs):
        assert kwargs["session_id"] == session_id
        return turn

    monkeypatch.setattr(
        "app.api.routes.copilot.copilot_runtime.create_turn",
        fake_create_turn,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        response = client.post(
            f"/api/businesses/{business_id}/copilot/sessions/{session_id}/messages",
            json={"text": "Show active coverage campaigns", "normalized_channel": "dashboard"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["resolved_intent"]["tool_name"] == "coverage.list_active_campaigns"
    assert payload["action_run"]["status"] == "executed"
    assert payload["outbound_message"]["message_metadata"]["message_kind"] == "tool_result"
    assert fake_db.commits == 1
