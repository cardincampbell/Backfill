from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app.models.identity import Membership, Session, User
from app.schemas.compliance import ShiftComplianceDecisionRead
from app.schemas.events import PlatformEventRead
from app.services import compliance_decisions, platform_events
from app.services.auth import AuthContext


class FakeComplianceDecisionSession:
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


@pytest.mark.asyncio
async def test_list_shift_compliance_decisions_reads_from_feed_events(monkeypatch):
    session = FakeComplianceDecisionSession()
    business_id = uuid4()
    shift_id = uuid4()
    employee_id = uuid4()
    event_id = uuid4()

    async def fake_list_feed_events(_session, **kwargs):
        assert kwargs["business_id"] == business_id
        assert kwargs["entity_type"] == "shift"
        assert kwargs["entity_id"] == shift_id
        assert kwargs["event_type"] == platform_events.PlatformEventType.COMPLIANCE_DECISION_RECORDED
        assert kwargs["limit"] == 10
        return [
            PlatformEventRead(
                id=event_id,
                business_id=business_id,
                location_id=uuid4(),
                schema_version=1,
                event_type=platform_events.PlatformEventType.COMPLIANCE_DECISION_RECORDED,
                compatibility_event_name=platform_events.PlatformEventType.COMPLIANCE_DECISION_RECORDED,
                entity_type="shift",
                entity_id=shift_id,
                actor_type="system",
                actor_user_id=None,
                actor_membership_id=None,
                trace_id="trace_123",
                ip_address=None,
                user_agent=None,
                payload={
                    "shift_id": str(shift_id),
                    "employee_id": str(employee_id),
                    "decision_source": "scheduler_assignment",
                    "decision_outcome": "blocked",
                    "engine_version": "compliance_engine_v1",
                    "blocking_rule_codes": ["minimum_rest_window"],
                    "warning_rule_codes": [],
                    "premium_rule_codes": [],
                    "premium_total_cents": 0,
                    "premium_components": [],
                    "unresolved_premium_rule_codes": [],
                    "override_applied": False,
                    "evaluation": {"status": "block"},
                },
                event_metadata={},
                error_message=None,
                occurred_at=datetime(2026, 4, 24, 18, 0, tzinfo=timezone.utc),
            )
        ]

    monkeypatch.setattr(
        compliance_decisions.feed_projections,
        "list_feed_events",
        fake_list_feed_events,
    )

    result = await compliance_decisions.list_shift_compliance_decisions(
        session,
        business_id=business_id,
        shift_id=shift_id,
        limit=10,
    )

    assert len(result) == 1
    assert result[0].id == event_id
    assert result[0].shift_id == shift_id
    assert result[0].employee_id == employee_id
    assert result[0].decision_source == "scheduler_assignment"
    assert result[0].decision_outcome == "blocked"
    assert result[0].blocking_rule_codes == ["minimum_rest_window"]


def test_list_shift_compliance_decisions_route_returns_history(monkeypatch):
    fake_session = FakeComplianceDecisionSession()
    business_id = uuid4()
    shift_id = uuid4()
    employee_id = uuid4()
    fake_session_business_id = business_id
    fake_session_shift_id = shift_id

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    async def fake_get_shift(_session, requested_business_id, requested_shift_id):
        assert requested_business_id == business_id
        assert requested_shift_id == shift_id
        return SimpleNamespace(id=shift_id, location_id=uuid4())

    async def fake_list_shift_compliance_decisions(_session, *, business_id, shift_id, limit=25):
        assert business_id == fake_session_business_id
        assert shift_id == fake_session_shift_id
        assert limit == 10
        return [
            ShiftComplianceDecisionRead(
                id=uuid4(),
                occurred_at=datetime(2026, 4, 24, 18, 0, tzinfo=timezone.utc),
                actor_type="system",
                actor_user_id=None,
                actor_membership_id=None,
                trace_id="trace_123",
                shift_id=shift_id,
                employee_id=employee_id,
                decision_source="scheduler_assignment",
                decision_outcome="allowed",
                engine_version="compliance_engine_v1",
                profile_code="ca_meal_rest_v1",
                blocking_rule_codes=[],
                warning_rule_codes=["paid_rest_break_quota"],
                premium_rule_codes=["paid_rest_break_quota"],
                premium_total_cents=2100,
                premium_components=[{"rule_code": "paid_rest_break_quota", "premium_cents": 2100}],
                unresolved_premium_rule_codes=[],
                override_applied=False,
                evaluation={"status": "warning"},
            )
        ]

    monkeypatch.setattr("app.api.routes.scheduling.scheduling.get_shift", fake_get_shift)
    monkeypatch.setattr(
        "app.api.routes.scheduling.compliance_decisions.list_shift_compliance_decisions",
        fake_list_shift_compliance_decisions,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/shifts/{shift_id}/compliance-decisions?limit=10"
        )
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["shift_id"] == str(shift_id)
        assert payload[0]["employee_id"] == str(employee_id)
        assert payload[0]["decision_source"] == "scheduler_assignment"
        assert payload[0]["premium_total_cents"] == 2100
    finally:
        app.dependency_overrides.clear()
