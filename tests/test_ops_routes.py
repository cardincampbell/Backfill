from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.ai import LlmGeneration
from app.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app.models.events import PlatformEvent
from app.models.finance import BillingLedgerEntry, CostLedgerEntry
from app.models.identity import Membership, Session, User
from app.services import ops_reporting
from app.services.auth import AuthContext


class FakeOpsRouteSession:
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


def test_get_trace_report_returns_combined_operational_view(monkeypatch):
    fake_session = FakeOpsRouteSession()
    business_id = uuid4()
    location_id = uuid4()
    trace_id = "trace_abc123"
    now = datetime(2026, 4, 10, 19, 15, tzinfo=timezone.utc)
    event = PlatformEvent(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        schema_version=1,
        event_type="finance.cost.recorded",
        compatibility_event_name="finance.cost.recorded",
        entity_type="coverage_case",
        entity_id=uuid4(),
        actor_type="system",
        actor_user_id=None,
        actor_membership_id=None,
        trace_id=trace_id,
        ip_address=None,
        user_agent=None,
        payload={"total_cost_micros": 4100},
        event_metadata={"trace_id": trace_id, "provider": "openai"},
        error_message=None,
        occurred_at=now,
        created_at=now,
        updated_at=now,
    )
    generation = LlmGeneration(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        provider="openai",
        model="gpt-test",
        purpose="intent_resolution",
        status="succeeded",
        trace_id=trace_id,
        provider_generation_id="resp_123",
        finish_reason="stop",
        output_text="Ready.",
        input_tokens=100,
        output_tokens=20,
        total_tokens=120,
        estimated_cost_micros=4100,
        latency_ms=850,
        request_payload={"messages": [{"role": "user", "content": "Who can cover tonight?"}]},
        response_payload={"id": "resp_123"},
        tool_calls=[],
        generation_metadata={"trace_id": trace_id},
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )
    cost_entry = CostLedgerEntry(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        coverage_case_id=uuid4(),
        shift_id=uuid4(),
        employee_id=None,
        provider="openai",
        product="llm_generation",
        reference_type="llm_generation",
        reference_id="gen_123",
        idempotency_key="llm_generation:gen_123",
        quantity=Decimal("1"),
        unit_cost_micros=4100,
        total_cost_micros=4100,
        cost_metadata={"trace_id": trace_id},
        error_message=None,
        occurred_at=now,
        created_at=now,
        updated_at=now,
    )
    billing_entry = BillingLedgerEntry(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        coverage_case_id=uuid4(),
        shift_id=uuid4(),
        employee_id=uuid4(),
        billing_event_type="fill_charged",
        billing_cycle_start=datetime(2026, 4, 1, 7, 0, tzinfo=timezone.utc),
        amount_cents=2000,
        cap_applied=False,
        idempotency_key="fill:case_123:fill_charged",
        billing_metadata={"trace_id": trace_id},
        error_message=None,
        occurred_at=now,
        created_at=now,
        updated_at=now,
    )

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    async def fake_trace_report(_session, **kwargs):
        assert kwargs["business_id"] == business_id
        assert kwargs["trace_id"] == trace_id
        assert kwargs["location_id"] == location_id
        assert kwargs["limit"] == 25
        return ops_reporting.TraceReport(
            trace_id=trace_id,
            platform_events=[event],
            llm_generations=[generation],
            cost_entries=[cost_entry],
            billing_entries=[billing_entry],
            total_cost_micros=4100,
            total_billed_cents=2000,
        )

    monkeypatch.setattr(ops_reporting, "trace_report", fake_trace_report)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/ops/traces/{trace_id}?location_id={location_id}&limit=25"
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["trace_id"] == trace_id
        assert payload["platform_event_count"] == 1
        assert payload["llm_generation_count"] == 1
        assert payload["cost_entry_count"] == 1
        assert payload["billing_entry_count"] == 1
        assert payload["total_cost_micros"] == 4100
        assert payload["total_billed_cents"] == 2000
        assert payload["platform_events"][0]["event_type"] == "finance.cost.recorded"
        assert payload["llm_generations"][0]["provider"] == "openai"
        assert payload["cost_entries"][0]["product"] == "llm_generation"
        assert payload["billing_entries"][0]["billing_event_type"] == "fill_charged"
    finally:
        app.dependency_overrides.clear()


def test_get_trace_report_requires_business_access():
    fake_session = FakeOpsRouteSession()
    business_id = uuid4()

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, role=MembershipRole.viewer)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(f"/api/businesses/{business_id}/ops/traces/trace_123")
        assert response.status_code == 403
        assert response.json() == {"detail": "business_access_denied"}
    finally:
        app.dependency_overrides.clear()
