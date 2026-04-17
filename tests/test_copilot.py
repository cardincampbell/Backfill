from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.domain.copilot import registry, runtime as copilot_runtime, validation
from app.main import app
from app.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app.models.identity import Membership, Session, User
from app.schemas.copilot import (
    CopilotActionRunRead,
    CopilotIntentRead,
    CopilotMessageRead,
    CopilotSessionDetailRead,
    CopilotSessionEventRead,
    CopilotSessionRead,
    CopilotTurnRead,
    CopilotValidationResultRead,
)
from app.services import llm_gateway
from app.services.auth import AuthContext


class FakeCopilotSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarResult(self._values)


class FakeReuseLookupSession:
    def __init__(self, entries):
        self._entries = entries

    async def execute(self, _query):
        return _ExecuteResult(self._entries)


class FakeSessionmaker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        session = self._session

        class _ContextManager:
            async def __aenter__(self_inner):
                return session

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _ContextManager()


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
        context_profile={"business_name": "Backfill", "timezone": "America/Los_Angeles"},
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
    tools_by_name = {item["name"]: item for item in payload}
    assert "coverage.list_active_campaigns" in tool_names
    assert "schedule.list_open_shifts" in tool_names
    assert tools_by_name["roster.update_availability"]["mutates_state"] is True
    assert tools_by_name["schedule.publish"]["availability"] == "planned"
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


def test_create_session_route_rejects_inaccessible_location(client: TestClient):
    business_id = uuid4()
    allowed_location_id = uuid4()
    blocked_location_id = uuid4()

    async def override_db():
        yield FakeCopilotSession()

    async def override_auth():
        return _make_auth_context(
            business_id=business_id,
            location_id=allowed_location_id,
        )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        response = client.post(
            f"/api/businesses/{business_id}/copilot/sessions",
            json={
                "location_id": str(blocked_location_id),
                "normalized_channel": "dashboard",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "location_access_denied"


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


def test_copilot_live_socket_sends_ready_and_completed_events(client: TestClient, monkeypatch):
    business_id = uuid4()
    auth_ctx = _make_auth_context(business_id=business_id)
    detail = _detail(business_id=business_id, user_id=auth_ctx.user.id)
    session_id = detail.session.id
    fake_db = FakeCopilotSession()
    now = datetime.now(timezone.utc)

    async def fake_resolve_auth_context(_session, token):
        assert token == "socket-token"
        return auth_ctx

    async def fake_get_session_detail(_db, **kwargs):
        assert kwargs["session_id"] == session_id
        return detail

    async def fake_create_turn(_db, **kwargs):
        publisher = kwargs["live_event_publisher"]
        trace_id = kwargs["live_trace_id"]
        turn = CopilotTurnRead(
            session=detail.session,
            resolved_intent=CopilotIntentRead(
                family="coverage",
                tool_name="coverage.list_active_campaigns",
                reasoning="Test",
                confidence=0.9,
            ),
            inbound_message=CopilotMessageRead(
                id=uuid4(),
                copilot_session_id=session_id,
                direction="inbound",
                normalized_channel="dashboard",
                raw_text="Show active coverage campaigns",
                normalized_text="show active coverage campaigns",
                message_metadata={},
                created_at=now,
            ),
            outbound_message=CopilotMessageRead(
                id=uuid4(),
                copilot_session_id=session_id,
                direction="outbound",
                normalized_channel="dashboard",
                raw_text="There is 1 active campaign.",
                normalized_text="there is 1 active campaign.",
                message_metadata={"message_kind": "tool_result", "tool_name": "coverage.list_active_campaigns"},
                created_at=now,
            ),
            action_run=CopilotActionRunRead(
                id=uuid4(),
                copilot_session_id=session_id,
                tool_name="coverage.list_active_campaigns",
                status="executed",
                input_payload={},
                validation_result=CopilotValidationResultRead(ok=True, code="ok", message="ok"),
                result_payload={"kind": "campaigns", "total_active_campaigns": 1, "items": []},
                error_payload={},
                started_at=now,
                finished_at=now,
            ),
            tools=[],
        )
        await publisher(
            CopilotSessionEventRead(
                event_id=uuid4(),
                event_type="assistant.message.completed",
                trace_id=trace_id,
                session_id=session_id,
                occurred_at=now,
                payload={"turn": turn.model_dump(mode="json")},
            )
        )
        return turn

    monkeypatch.setattr("app.api.routes.copilot.get_async_sessionmaker", lambda: FakeSessionmaker(fake_db))
    monkeypatch.setattr("app.api.routes.copilot.auth_service.resolve_auth_context", fake_resolve_auth_context)
    monkeypatch.setattr("app.api.routes.copilot.copilot_runtime.get_session_detail", fake_get_session_detail)
    monkeypatch.setattr("app.api.routes.copilot.copilot_runtime.create_turn", fake_create_turn)

    with client.websocket_connect(
        f"/api/businesses/{business_id}/copilot/sessions/{session_id}/live",
        headers={"cookie": "backfill_session=socket-token"},
    ) as websocket:
        ready_event = websocket.receive_json()
        assert ready_event["event_type"] == "session.ready"
        assert ready_event["payload"]["detail"]["session"]["id"] == str(session_id)

        websocket.send_json(
            {
                "type": "user.message",
                "text": "Show active coverage campaigns",
                "normalized_channel": "dashboard",
                "trace_id": "trace-live-websocket",
            }
        )
        completed_event = websocket.receive_json()
        assert completed_event["event_type"] == "assistant.message.completed"
        assert completed_event["trace_id"] == "trace-live-websocket"


@pytest.mark.asyncio
async def test_reusable_session_lookup_uses_latest_session_snapshot(monkeypatch):
    business_id = uuid4()
    auth_ctx = _make_auth_context(business_id=business_id)
    detail = _detail(business_id=business_id, user_id=auth_ctx.user.id)
    session_id = detail.session.id

    stale_created_snapshot = detail.session.model_copy(
        update={"expires_at": datetime.now(timezone.utc) - timedelta(minutes=5)}
    )
    latest_snapshot = detail.session.model_copy(
        update={"expires_at": datetime.now(timezone.utc) + timedelta(hours=4)}
    )

    created_entry = type(
        "Entry",
        (),
        {
            "target_id": session_id,
            "payload": {"session": stale_created_snapshot.model_dump(mode="json")},
            "occurred_at": datetime.now(timezone.utc) - timedelta(minutes=10),
        },
    )()
    latest_entry = type(
        "Entry",
        (),
        {
            "target_id": session_id,
            "payload": {"session": latest_snapshot.model_dump(mode="json")},
            "occurred_at": datetime.now(timezone.utc),
        },
    )()

    async def fake_get_session_detail_or_raise(_db, *, business_id, session_id):
        assert session_id == detail.session.id
        return detail.model_copy(update={"session": latest_snapshot})

    monkeypatch.setattr(
        "app.domain.copilot.runtime._get_session_detail_or_raise",
        fake_get_session_detail_or_raise,
    )

    reusable = await copilot_runtime._find_reusable_session(
        FakeReuseLookupSession([latest_entry, created_entry]),
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=None,
    )

    assert reusable is not None
    assert reusable.session.id == detail.session.id


def test_validation_normalizes_roster_update_availability_arguments():
    business_id = uuid4()
    auth_ctx = _make_auth_context(business_id=business_id)

    validated = validation.validate_and_normalize_tool_call(
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=None,
        tool_name="roster.update_availability",
        tool_arguments={
            "timezone": "America/Los_Angeles",
            "rules": [
                {
                    "day_of_week": "monday",
                    "start_local_time": "9:00 AM",
                    "end_local_time": "5:00 PM",
                }
            ],
        },
        default_timezone="America/Los_Angeles",
    )

    assert validated.validation_result.ok is True
    assert validated.normalized_arguments["timezone"] == "America/Los_Angeles"
    assert validated.normalized_arguments["rules"][0]["day_of_week"] == 0
    assert validated.normalized_arguments["rules"][0]["start_local_time"] == "09:00:00"
    assert validated.normalized_arguments["rules"][0]["end_local_time"] == "17:00:00"


def test_validation_rejects_missing_or_implicit_clear_availability_payload():
    business_id = uuid4()
    auth_ctx = _make_auth_context(business_id=business_id)

    missing_rules = validation.validate_and_normalize_tool_call(
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=None,
        tool_name="roster.update_availability",
        tool_arguments={"timezone": "America/Los_Angeles"},
        default_timezone="America/Los_Angeles",
    )
    implicit_clear = validation.validate_and_normalize_tool_call(
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=None,
        tool_name="roster.update_availability",
        tool_arguments={"timezone": "America/Los_Angeles", "rules": []},
        default_timezone="America/Los_Angeles",
    )
    explicit_clear = validation.validate_and_normalize_tool_call(
        auth_ctx=auth_ctx,
        business_id=business_id,
        location_id=None,
        tool_name="roster.update_availability",
        tool_arguments={
            "timezone": "America/Los_Angeles",
            "clear_requested": True,
            "rules": [],
        },
        default_timezone="America/Los_Angeles",
    )

    assert missing_rules.validation_result.ok is False
    assert missing_rules.validation_result.code == "invalid_arguments"
    assert implicit_clear.validation_result.ok is False
    assert implicit_clear.validation_result.code == "invalid_arguments"
    assert explicit_clear.validation_result.ok is True
    assert explicit_clear.normalized_arguments["clear_requested"] is True
    assert explicit_clear.normalized_arguments["rules"] == []


@pytest.mark.asyncio
async def test_plan_tool_call_includes_current_availability_snapshot(monkeypatch):
    business_id = uuid4()
    auth_ctx = _make_auth_context(business_id=business_id)
    detail = _detail(business_id=business_id, user_id=auth_ctx.user.id)

    async def fake_get_self_employee_availability_rules(
        _session,
        _business_id,
        *,
        user_id,
        email,
        phone_e164,
        full_name,
    ):
        assert _business_id == business_id
        assert user_id == auth_ctx.user.id
        assert email == auth_ctx.user.email
        assert phone_e164 == auth_ctx.user.primary_phone_e164
        assert full_name == auth_ctx.user.full_name
        return (
            SimpleNamespace(id=uuid4()),
            [
                SimpleNamespace(
                    day_of_week=1,
                    start_local_time=time(9, 0),
                    end_local_time=time(17, 0),
                    timezone="America/Los_Angeles",
                    availability_type="available",
                )
            ],
        )

    async def fake_generate(_db, *, request):
        planner_context = "\n".join(message.content for message in request.messages)
        assert "Current recurring weekly availability" in planner_context
        assert '"day_label": "Tuesday"' in planner_context
        return llm_gateway.LlmGenerationResult(
            provider="openai",
            model="gpt-test",
            output_text="Use the availability tool.",
            tool_calls=[
                llm_gateway.LlmToolCall(
                    tool_call_id="tool_1",
                    name="roster.update_availability",
                    arguments={
                        "timezone": "America/Los_Angeles",
                        "rules": [
                            {
                                "day_of_week": 1,
                                "start_local_time": "09:00",
                                "end_local_time": "17:00",
                            },
                            {
                                "day_of_week": 4,
                                "start_local_time": "09:00",
                                "end_local_time": "17:00",
                            },
                        ],
                    },
                )
            ],
        )

    monkeypatch.setattr(
        "app.domain.copilot.runtime.workforce.get_self_employee_availability_rules",
        fake_get_self_employee_availability_rules,
    )
    monkeypatch.setattr("app.domain.copilot.runtime.llm_gateway.generate", fake_generate)

    planned = await copilot_runtime._plan_tool_call(
        FakeCopilotSession(),
        auth_ctx=auth_ctx,
        session_state=detail.session,
        history=detail.messages,
        payload=copilot_runtime.CopilotMessageCreate(
            text="Add Friday 9 to 5",
            normalized_channel="dashboard",
        ),
    )

    assert planned.planner_source == "llm"
    assert planned.intent.tool_name == "roster.update_availability"


@pytest.mark.asyncio
async def test_create_turn_uses_llm_planner_for_availability_update(monkeypatch):
    business_id = uuid4()
    auth_ctx = _make_auth_context(business_id=business_id)
    detail = _detail(business_id=business_id, user_id=auth_ctx.user.id)
    session_id = detail.session.id

    async def fake_get_session_detail(_db, **_kwargs):
        return detail

    async def fake_append_event(*_args, **_kwargs):
        return None

    async def fake_current_availability_rules(*_args, **_kwargs):
        return []

    async def fake_generate(_db, *, request):
        assert request.purpose == "copilot_tool_planning"
        return llm_gateway.LlmGenerationResult(
            provider="openai",
            model="gpt-test",
            output_text="Update the operator's weekly availability.",
            tool_calls=[
                llm_gateway.LlmToolCall(
                    tool_call_id="tool_1",
                    name="roster.update_availability",
                    arguments={
                        "timezone": "America/Los_Angeles",
                        "rules": [
                            {
                                "day_of_week": 0,
                                "start_local_time": "09:00",
                                "end_local_time": "17:00",
                            },
                            {
                                "day_of_week": 1,
                                "start_local_time": "09:00",
                                "end_local_time": "17:00",
                            },
                        ],
                    },
                )
            ],
        )

    async def fake_replace_self_employee_availability_rules(
        _session,
        _business_id,
        *,
        user_id,
        email,
        phone_e164,
        full_name,
        payload,
    ):
        assert _business_id == business_id
        assert user_id == auth_ctx.user.id
        assert email == auth_ctx.user.email
        assert phone_e164 == auth_ctx.user.primary_phone_e164
        assert full_name == auth_ctx.user.full_name
        assert len(payload.rules) == 2
        return (
            SimpleNamespace(id=uuid4(), preferred_name="Jordan", full_name="Jordan Lead"),
            [
                SimpleNamespace(
                    day_of_week=rule.day_of_week,
                    start_local_time=rule.start_local_time,
                    end_local_time=rule.end_local_time,
                    timezone=rule.timezone,
                )
                for rule in payload.rules
            ],
        )

    monkeypatch.setattr("app.domain.copilot.runtime.get_session_detail", fake_get_session_detail)
    monkeypatch.setattr("app.domain.copilot.runtime._append_copilot_event", fake_append_event)
    monkeypatch.setattr("app.domain.copilot.runtime._current_availability_rules", fake_current_availability_rules)
    monkeypatch.setattr("app.domain.copilot.runtime.llm_gateway.generate", fake_generate)
    monkeypatch.setattr(
        "app.domain.copilot.runtime.workforce.replace_self_employee_availability_rules",
        fake_replace_self_employee_availability_rules,
    )

    turn = await copilot_runtime.create_turn(
        FakeCopilotSession(),
        auth_ctx=auth_ctx,
        business_id=business_id,
        session_id=session_id,
        payload=copilot_runtime.CopilotMessageCreate(
            text="Update my availability to Monday and Tuesday from 9 AM to 5 PM",
            normalized_channel="dashboard",
        ),
        request_context=copilot_runtime.CopilotRequestContext(),
    )

    assert turn.resolved_intent.tool_name == "roster.update_availability"
    assert turn.action_run.status == "executed"
    assert turn.action_run.input_payload["planner_source"] == "llm"
    assert turn.action_run.result_payload["kind"] == "availability_update"
    assert turn.action_run.result_payload["day_count"] == 2
    assert turn.outbound_message.message_metadata["tool_name"] == "roster.update_availability"


@pytest.mark.asyncio
async def test_create_turn_emits_live_progress_events(monkeypatch):
    business_id = uuid4()
    auth_ctx = _make_auth_context(business_id=business_id)
    detail = _detail(business_id=business_id, user_id=auth_ctx.user.id)
    session_id = detail.session.id
    emitted_events: list[CopilotSessionEventRead] = []

    async def fake_get_session_detail(_db, **_kwargs):
        return detail

    async def fake_append_event(*_args, **_kwargs):
        return None

    async def fake_current_availability_rules(*_args, **_kwargs):
        return []

    async def fake_generate(_db, *, request):
        assert request.metadata["trace_id"]
        return llm_gateway.LlmGenerationResult(
            provider="openai",
            model="gpt-test",
            output_text="List active campaigns.",
            tool_calls=[
                llm_gateway.LlmToolCall(
                    tool_call_id="tool_1",
                    name="coverage.list_active_campaigns",
                    arguments={},
                )
            ],
        )

    async def fake_execute_active_campaigns(_db, **_kwargs):
        return (
            {"kind": "campaigns", "total_active_campaigns": 1, "running_count": 1, "queued_count": 0, "items": []},
            "There is 1 active campaign.",
        )

    async def capture_event(event: CopilotSessionEventRead):
        emitted_events.append(event)

    monkeypatch.setattr("app.domain.copilot.runtime.get_session_detail", fake_get_session_detail)
    monkeypatch.setattr("app.domain.copilot.runtime._append_copilot_event", fake_append_event)
    monkeypatch.setattr("app.domain.copilot.runtime._current_availability_rules", fake_current_availability_rules)
    monkeypatch.setattr("app.domain.copilot.runtime.llm_gateway.generate", fake_generate)
    monkeypatch.setattr("app.domain.copilot.runtime._execute_active_campaigns", fake_execute_active_campaigns)

    turn = await copilot_runtime.create_turn(
        FakeCopilotSession(),
        auth_ctx=auth_ctx,
        business_id=business_id,
        session_id=session_id,
        payload=copilot_runtime.CopilotMessageCreate(
            text="Show active coverage campaigns",
            normalized_channel="dashboard",
        ),
        request_context=copilot_runtime.CopilotRequestContext(),
        live_event_publisher=capture_event,
        live_trace_id="trace-live-1",
    )

    assert turn.action_run.status == "executed"
    assert [event.event_type for event in emitted_events] == [
        "user.message.accepted",
        "assistant.turn.started",
        "assistant.progress",
        "assistant.progress",
        "assistant.progress",
        "tool.started",
        "tool.finished",
        "assistant.message.completed",
    ]
    assert emitted_events[0].trace_id == "trace-live-1"
    assert emitted_events[-1].payload["turn"]["action_run"]["tool_name"] == "coverage.list_active_campaigns"


@pytest.mark.asyncio
async def test_create_turn_falls_back_to_heuristic_when_llm_planner_fails(monkeypatch):
    business_id = uuid4()
    auth_ctx = _make_auth_context(business_id=business_id)
    detail = _detail(business_id=business_id, user_id=auth_ctx.user.id)
    session_id = detail.session.id

    async def fake_get_session_detail(_db, **_kwargs):
        return detail

    async def fake_append_event(*_args, **_kwargs):
        return None

    async def fake_current_availability_rules(*_args, **_kwargs):
        return []

    async def fake_generate(_db, *, request):
        raise RuntimeError(f"planner_unavailable:{request.purpose}")

    async def fake_execute_active_campaigns(_db, **_kwargs):
        return (
            {"kind": "campaigns", "total_active_campaigns": 1, "running_count": 1, "queued_count": 0, "items": []},
            "There is 1 active campaign.",
        )

    monkeypatch.setattr("app.domain.copilot.runtime.get_session_detail", fake_get_session_detail)
    monkeypatch.setattr("app.domain.copilot.runtime._append_copilot_event", fake_append_event)
    monkeypatch.setattr("app.domain.copilot.runtime._current_availability_rules", fake_current_availability_rules)
    monkeypatch.setattr("app.domain.copilot.runtime.llm_gateway.generate", fake_generate)
    monkeypatch.setattr("app.domain.copilot.runtime._execute_active_campaigns", fake_execute_active_campaigns)

    turn = await copilot_runtime.create_turn(
        FakeCopilotSession(),
        auth_ctx=auth_ctx,
        business_id=business_id,
        session_id=session_id,
        payload=copilot_runtime.CopilotMessageCreate(
            text="Show active coverage campaigns",
            normalized_channel="dashboard",
        ),
        request_context=copilot_runtime.CopilotRequestContext(),
    )

    assert turn.resolved_intent.tool_name == "coverage.list_active_campaigns"
    assert turn.action_run.status == "executed"
    assert turn.action_run.input_payload["planner_source"] == "heuristic"
    assert turn.action_run.result_payload["kind"] == "campaigns"
