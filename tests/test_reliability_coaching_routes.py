from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.common import (
    MembershipRole,
    MembershipStatus,
    ReliabilityCoachingCaseStatus,
    ReliabilityCoachingDeliveryStatus,
    SessionRiskLevel,
)
from app.models.coverage import AuditLog
from app.models.identity import Membership, Session, User
from app.models.reliability_coaching import ReliabilityCoachingCase
from app.services.auth import AuthContext


class _FakeSession:
    def __init__(self):
        self.added: list[object] = []
        self.commits = 0

    def add(self, obj):
        now = datetime.now(timezone.utc)
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = now
        if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
            obj.updated_at = now
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None


def _make_auth_context(*, business_id) -> AuthContext:
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        full_name="Morgan Manager",
        email="morgan@example.com",
        primary_phone_e164="+15555550144",
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
        role=MembershipRole.manager,
        status=MembershipStatus.active,
        accepted_at=now,
        membership_metadata={},
        created_at=now,
        updated_at=now,
    )
    return AuthContext(user=user, session=session, memberships=[membership])


def _case(*, business_id, employee_id=None) -> ReliabilityCoachingCase:
    now = datetime.now(timezone.utc)
    coaching_case = ReliabilityCoachingCase(
        id=uuid4(),
        business_id=business_id,
        employee_id=employee_id or uuid4(),
        case_status=ReliabilityCoachingCaseStatus.open,
        delivery_status=ReliabilityCoachingDeliveryStatus.pending,
        coaching_style="supportive",
        policy_version="v1",
        prompt_version="v1",
        trigger_metric="callout_count_rolling_7d",
        trigger_threshold=2,
        trigger_window_days=7,
        trigger_count=2,
        opened_at=now,
        case_metadata={},
        created_at=now,
        updated_at=now,
    )
    coaching_case.attempts = []
    coaching_case.outcomes = []
    return coaching_case


def test_list_reliability_coaching_cases_route_returns_cases(monkeypatch):
    fake_session = _FakeSession()
    business_id = uuid4()
    coaching_case = _case(business_id=business_id)
    auth_ctx = _make_auth_context(business_id=business_id)

    async def override_db():
        yield fake_session

    async def override_auth():
        return auth_ctx

    async def fake_list_cases(_session, *, business_id, employee_id=None, limit=50):
        assert business_id == auth_ctx.memberships[0].business_id
        assert employee_id is None
        assert limit == 50
        return [coaching_case]

    monkeypatch.setattr(
        "app.api.routes.businesses.reliability_coaching.list_business_coaching_cases",
        fake_list_cases,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.get(f"/api/businesses/{business_id}/reliability-coaching/cases")
        assert response.status_code == 200
        payload = response.json()
        assert payload[0]["id"] == str(coaching_case.id)
        assert payload[0]["case_status"] == "open"
    finally:
        app.dependency_overrides.clear()


def test_suppress_reliability_coaching_case_route_commits_and_audits(monkeypatch):
    fake_session = _FakeSession()
    business_id = uuid4()
    coaching_case = _case(business_id=business_id)
    coaching_case.case_status = ReliabilityCoachingCaseStatus.suppressed
    coaching_case.delivery_status = ReliabilityCoachingDeliveryStatus.exhausted
    auth_ctx = _make_auth_context(business_id=business_id)

    async def override_db():
        yield fake_session

    async def override_auth():
        return auth_ctx

    async def fake_suppress_case(
        _session,
        *,
        business_id,
        coaching_case_id,
        actor_user_id,
        reason_code,
        note,
        expires_at,
    ):
        assert business_id == auth_ctx.memberships[0].business_id
        assert coaching_case_id == coaching_case.id
        assert actor_user_id == auth_ctx.user.id
        assert reason_code == "temporary_hardship"
        assert note == "Human follow-up already underway."
        assert expires_at is None
        return coaching_case

    monkeypatch.setattr(
        "app.api.routes.businesses.reliability_coaching.suppress_coaching_case",
        fake_suppress_case,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/businesses/{business_id}/reliability-coaching/cases/{coaching_case.id}/suppress",
            json={"reason_code": "temporary_hardship", "note": "Human follow-up already underway."},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["case_status"] == "suppressed"
        assert fake_session.commits == 1
        assert any(
            isinstance(entry, AuditLog) and entry.event_name == "reliability_coaching.case.suppressed"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()


def test_close_reliability_coaching_case_route_commits_and_audits(monkeypatch):
    fake_session = _FakeSession()
    business_id = uuid4()
    coaching_case = _case(business_id=business_id)
    coaching_case.case_status = ReliabilityCoachingCaseStatus.closed
    coaching_case.delivery_status = ReliabilityCoachingDeliveryStatus.exhausted
    auth_ctx = _make_auth_context(business_id=business_id)

    async def override_db():
        yield fake_session

    async def override_auth():
        return auth_ctx

    async def fake_close_case(_session, *, business_id, coaching_case_id, reason_code, note):
        assert business_id == auth_ctx.memberships[0].business_id
        assert coaching_case_id == coaching_case.id
        assert reason_code == "manager_completed_followup"
        assert note == "Resolved manually."
        return coaching_case

    monkeypatch.setattr(
        "app.api.routes.businesses.reliability_coaching.close_coaching_case",
        fake_close_case,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/businesses/{business_id}/reliability-coaching/cases/{coaching_case.id}/close",
            json={"reason_code": "manager_completed_followup", "note": "Resolved manually."},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["case_status"] == "closed"
        assert fake_session.commits == 1
        assert any(
            isinstance(entry, AuditLog) and entry.event_name == "reliability_coaching.case.closed"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()
