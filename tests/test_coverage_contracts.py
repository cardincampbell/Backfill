from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app.models.identity import Membership, Session, User
from app.schemas.coverage import (
    CoverageCampaignCreate,
    CoverageCampaignDispatchResult,
    CoverageCampaignExecutionDecision,
    CoverageCampaignRead,
    CoverageExecutionPlan,
)
from app.services import platform_events
from app.services.auth import AuthContext


class _FakeSession:
    async def commit(self):
        return None


def _make_auth_context(*, business_id) -> AuthContext:
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
        location_id=None,
        role=MembershipRole.manager,
        status=MembershipStatus.active,
        accepted_at=now,
        membership_metadata={},
        created_at=now,
        updated_at=now,
    )
    return AuthContext(user=user, session=session, memberships=[membership])


def _make_campaign(*, business_id: str | None = None) -> CoverageCampaignRead:
    now = datetime.now(timezone.utc)
    return CoverageCampaignRead(
        id=uuid4(),
        shift_id=uuid4(),
        location_id=uuid4(),
        role_id=uuid4(),
        status="queued",
        phase_target="phase_1",
        reason_code=None,
        priority=100,
        requires_manager_approval=False,
        triggered_by="manager_workspace",
        campaign_metadata={"source": "workspace"},
        opened_at=now,
        closed_at=None,
        created_at=now,
        updated_at=now,
    )


def _make_decision(*, campaign_id) -> CoverageCampaignExecutionDecision:
    plan = CoverageExecutionPlan(
        phase="phase_1",
        operating_mode="standard_queue",
        strategy="phase_1_sequential_standard",
        time_to_shift_minutes=180,
        dispatch_limit=1,
        offer_ttl_minutes=5,
        premium_cents=0,
        phase_2_eligible=False,
        phase_2_reason="phase_1_candidates_available",
    )
    return CoverageCampaignExecutionDecision(
        campaign_id=campaign_id,
        shift_id=uuid4(),
        recommended_phase="phase_1",
        recommendation_reason="phase_1_candidates_available",
        phase_1_candidate_count=2,
        phase_2_candidate_count=0,
        phase_1_plan=plan,
        phase_2_plan=plan.model_copy(update={"phase": "phase_2"}),
    )


def test_campaign_create_schema_accepts_legacy_case_metadata_alias():
    payload = CoverageCampaignCreate.model_validate(
        {
            "shift_id": str(uuid4()),
            "case_metadata": {"source": "legacy"},
        }
    )

    assert payload.campaign_metadata == {"source": "legacy"}
    dumped = payload.model_dump(mode="json")
    assert dumped["campaign_metadata"] == {"source": "legacy"}
    assert dumped["case_metadata"] == {"source": "legacy"}


def test_create_campaign_route_returns_canonical_and_legacy_metadata(monkeypatch):
    business_id = uuid4()
    fake_session = _FakeSession()
    auth_ctx = _make_auth_context(business_id=business_id)
    campaign = _make_campaign()

    async def override_db():
        yield fake_session

    async def override_auth():
        return auth_ctx

    async def fake_create_campaign(session, requested_business_id, payload):
        assert session is fake_session
        assert requested_business_id == business_id
        assert payload.campaign_metadata == {"source": "workspace"}
        return campaign

    async def fake_append(*args, **kwargs):
        return None

    monkeypatch.setattr("app.api.routes.coverage.coverage.create_campaign", fake_create_campaign)
    monkeypatch.setattr(platform_events, "append", fake_append)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/businesses/{business_id}/coverage-campaigns",
            json={
                "shift_id": str(campaign.shift_id),
                "campaign_metadata": {"source": "workspace"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["campaign_metadata"] == {"source": "workspace"}
    assert body["case_metadata"] == {"source": "workspace"}


def test_legacy_execute_route_returns_campaign_aliases(monkeypatch):
    business_id = uuid4()
    fake_session = _FakeSession()
    auth_ctx = _make_auth_context(business_id=business_id)
    campaign = _make_campaign()
    decision = _make_decision(campaign_id=campaign.id)
    dispatch = CoverageCampaignDispatchResult(
        decision=decision,
        phase_executed="phase_1",
        campaign=campaign,
        candidate_count=2,
        offers=[],
    )

    async def override_db():
        yield fake_session

    async def override_auth():
        return auth_ctx

    async def fake_execute_campaign(session, requested_business_id, campaign_id, payload):
        assert session is fake_session
        assert requested_business_id == business_id
        assert campaign_id == campaign.id
        assert payload.channel == "sms"
        return dispatch

    async def fake_append(*args, **kwargs):
        return None

    monkeypatch.setattr("app.api.routes.coverage.coverage.execute_next_campaign_phase", fake_execute_campaign)
    monkeypatch.setattr(platform_events, "append", fake_append)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/businesses/{business_id}/coverage-cases/{campaign.id}/execute",
            json={"channel": "sms"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["campaign"]["id"] == str(campaign.id)
    assert body["coverage_case"]["id"] == str(campaign.id)
    assert body["decision"]["campaign_id"] == str(campaign.id)
    assert body["decision"]["coverage_case_id"] == str(campaign.id)
