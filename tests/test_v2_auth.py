from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app_v2.api.deps import get_auth_context
from app_v2.config import v2_settings
from app_v2.db.session import get_db_session
from app_v2.main import app
from app_v2.models.business import Business
from app_v2.models.common import (
    AuditActorType,
    ChallengeChannel,
    ChallengePurpose,
    ChallengeStatus,
    MembershipRole,
    MembershipStatus,
    SessionRiskLevel,
)
from app_v2.models.coverage import AuditLog
from app_v2.models.identity import Membership, OTPChallenge, Session, User
from app_v2.schemas.auth import OTPChallengeRequest, OTPChallengeVerifyRequest
from app_v2.services import auth
from app_v2.services.auth import AuthContext, OTPChallengeVerificationResult


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


class DummySession:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.flushed = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def flush(self):
        self.flushed += 1


class FakeAuthSession:
    def __init__(self):
        self.added: list[object] = []
        self.commits = 0
        self.flushed = 0
        self.get_map: dict[tuple[type, object], object] = {}
        self.scalar_queue: list[object] = []
        self.execute_queue: list[list[object]] = []

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))

    async def scalar(self, _query):
        if self.scalar_queue:
            return self.scalar_queue.pop(0)
        return None

    async def execute(self, _query):
        values = self.execute_queue.pop(0) if self.execute_queue else []
        return _ExecuteResult(values)

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

    async def flush(self):
        self.flushed += 1
        return None

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None


async def _override_db():
    yield DummySession()


def _make_auth_context(*, with_membership: bool) -> AuthContext:
    business_id = uuid4()
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
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        session_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    memberships = []
    if with_membership:
        memberships.append(
            Membership(
                id=uuid4(),
                user_id=user.id,
                business_id=business_id,
                role=MembershipRole.owner,
                status=MembershipStatus.active,
                membership_metadata={},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
    return AuthContext(user=user, session=session, memberships=memberships)


def _make_step_up_auth_context(*, verified_at: datetime | None) -> AuthContext:
    auth_ctx = _make_auth_context(with_membership=True)
    if verified_at is not None:
        auth_ctx.session.session_metadata = {
            "step_up_verified_at": {
                "step_up_export": verified_at.isoformat(),
            }
        }
        auth_ctx.session.elevated_actions = ["step_up_export"]
    return auth_ctx


def test_v2_auth_me_requires_session():
    app.dependency_overrides[get_db_session] = _override_db
    try:
        client = TestClient(app)
        response = client.get("/api/v2/auth/me")
        assert response.status_code == 401
        assert response.json()["detail"] == "authentication_required"
    finally:
        app.dependency_overrides.clear()


def test_v2_business_read_denies_without_membership():
    target_business_id = uuid4()

    async def override_auth():
        return _make_auth_context(with_membership=False)

    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.get(f"/api/v2/businesses/{target_business_id}")
        assert response.status_code == 403
        assert response.json()["detail"] == "business_access_denied"
    finally:
        app.dependency_overrides.clear()


def test_v2_create_business_bootstraps_owner_membership(monkeypatch):
    auth_ctx = _make_auth_context(with_membership=False)
    session = DummySession()
    created_business = Business(
        id=uuid4(),
        legal_name="Casa Vega LLC",
        brand_name="Casa Vega",
        slug="casa-vega",
        timezone="America/Los_Angeles",
        status="active",
        settings={},
        place_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    async def override_db():
        yield session

    async def override_auth():
        return auth_ctx

    async def fake_create_business(_session, payload):
        return created_business

    monkeypatch.setattr("app_v2.api.routes.businesses.businesses.create_business", fake_create_business)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v2/businesses",
            json={
                "legal_name": "Casa Vega LLC",
                "brand_name": "Casa Vega",
                "timezone": "America/Los_Angeles",
            },
        )
        assert response.status_code == 201
        memberships = [obj for obj in session.added if isinstance(obj, Membership)]
        audits = [obj for obj in session.added if isinstance(obj, AuditLog)]
        assert len(memberships) == 1
        assert memberships[0].user_id == auth_ctx.user.id
        assert memberships[0].business_id == created_business.id
        assert memberships[0].role == MembershipRole.owner
        assert memberships[0].status == MembershipStatus.active
        assert {entry.event_name for entry in audits} == {"business.created", "membership.granted"}
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_v2_request_otp_challenge_records_audit(monkeypatch):
    session = FakeAuthSession()
    existing_user = User(
        id=uuid4(),
        full_name="Existing User",
        email="existing@example.com",
        primary_phone_e164="+15555550123",
        is_phone_verified=True,
        onboarding_completed_at=datetime.now(timezone.utc),
        profile_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.scalar_queue = [existing_user]

    monkeypatch.setattr(
        "app_v2.services.messaging.send_sms_verification",
        lambda to, locale="en": {"sid": "VE123", "status": "pending", "channel": "sms", "to": to},
    )

    challenge, user_exists = await auth.request_otp_challenge(
        session,
        OTPChallengeRequest(phone_e164="+1 (555) 555-0123", purpose="sign_in"),
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    audits = [obj for obj in session.added if isinstance(obj, AuditLog)]
    assert user_exists is True
    assert challenge.external_sid == "VE123"
    assert challenge.status == ChallengeStatus.pending
    assert audits[-1].event_name == "auth.challenge.requested"
    assert audits[-1].actor_type == AuditActorType.user


def test_v2_request_challenge_route_hides_user_existence_and_rate_limits(monkeypatch):
    session = FakeAuthSession()
    existing_user = User(
        id=uuid4(),
        full_name="Existing User",
        email="existing@example.com",
        primary_phone_e164="+15555550123",
        is_phone_verified=True,
        onboarding_completed_at=datetime.now(timezone.utc),
        profile_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.scalar_queue = [existing_user, existing_user]

    async def override_db():
        yield session

    monkeypatch.setattr(
        "app_v2.services.messaging.send_sms_verification",
        lambda to, locale="en": {"sid": "VE123", "status": "pending", "channel": "sms", "to": to},
    )

    app.dependency_overrides[get_db_session] = override_db
    try:
        client = TestClient(app)
        first = client.post(
            "/api/v2/auth/challenges/request",
            json={"phone_e164": "+15555550123", "purpose": "sign_in"},
        )
        assert first.status_code == 201
        assert "user_exists" not in first.json()
        assert "user_id" not in first.json()

        second = client.post(
            "/api/v2/auth/challenges/request",
            json={"phone_e164": "+15555550123", "purpose": "sign_in"},
        )
        assert second.status_code == 429
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_v2_request_sign_in_for_unknown_phone_preserves_public_purpose(monkeypatch):
    session = FakeAuthSession()
    session.scalar_queue = [None]

    monkeypatch.setattr(
        "app_v2.services.messaging.send_sms_verification",
        lambda to, locale="en": {"sid": "VE999", "status": "pending", "channel": "sms", "to": to},
    )

    challenge, user_exists = await auth.request_otp_challenge(
        session,
        OTPChallengeRequest(phone_e164="+1 (555) 555-0199", purpose="sign_in"),
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert user_exists is False
    assert challenge.purpose == ChallengePurpose.sign_in


@pytest.mark.asyncio
async def test_v2_verify_otp_challenge_sign_in_creates_user_and_session_when_missing(monkeypatch):
    session = FakeAuthSession()
    challenge = OTPChallenge(
        id=uuid4(),
        phone_e164="+15555550160",
        channel=ChallengeChannel.sms,
        purpose=ChallengePurpose.sign_in,
        status=ChallengeStatus.pending,
        attempt_count=0,
        max_attempts=5,
        challenge_metadata={},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.get_map[(OTPChallenge, challenge.id)] = challenge
    session.scalar_queue = [None]

    monkeypatch.setattr(
        "app_v2.services.messaging.check_sms_verification",
        lambda to, code: {"sid": "VE789", "status": "approved", "valid": True, "to": to},
    )

    result = await auth.verify_otp_challenge(
        session,
        OTPChallengeVerifyRequest(
            challenge_id=challenge.id,
            phone_e164="+15555550160",
            code="123456",
            device_fingerprint="device-1",
        ),
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    users = [obj for obj in session.added if isinstance(obj, User)]
    sessions = [obj for obj in session.added if isinstance(obj, Session)]

    assert result.token is not None
    assert result.session is not None
    assert challenge.status == ChallengeStatus.approved
    assert len(users) == 1
    assert users[0].primary_phone_e164 == "+15555550160"
    assert len(sessions) == 1


@pytest.mark.asyncio
async def test_v2_verify_otp_challenge_sign_up_creates_user_and_session(monkeypatch):
    session = FakeAuthSession()
    challenge = OTPChallenge(
        id=uuid4(),
        phone_e164="+15555550150",
        channel=ChallengeChannel.sms,
        purpose=ChallengePurpose.sign_up,
        status=ChallengeStatus.pending,
        attempt_count=0,
        max_attempts=5,
        challenge_metadata={},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.get_map[(OTPChallenge, challenge.id)] = challenge
    session.scalar_queue = [None]

    monkeypatch.setattr(
        "app_v2.services.messaging.check_sms_verification",
        lambda to, code: {"sid": "VE456", "status": "approved", "valid": True, "to": to},
    )

    result = await auth.verify_otp_challenge(
        session,
        OTPChallengeVerifyRequest(
            challenge_id=challenge.id,
            phone_e164="+15555550150",
            code="123456",
            device_fingerprint="device-1",
        ),
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    users = [obj for obj in session.added if isinstance(obj, User)]
    sessions = [obj for obj in session.added if isinstance(obj, Session)]
    audits = [obj for obj in session.added if isinstance(obj, AuditLog)]

    assert result.token is not None
    assert result.session is not None
    assert result.step_up_granted is False
    assert challenge.status == ChallengeStatus.approved
    assert len(users) == 1
    assert users[0].is_phone_verified is True
    assert len(sessions) == 1
    assert {entry.event_name for entry in audits} == {
        "auth.challenge.approved",
        "auth.session.created",
    }


@pytest.mark.asyncio
async def test_v2_resolve_auth_context_refreshes_all_active_sessions_for_user():
    user = User(
        id=uuid4(),
        full_name="Session User",
        email="session@example.com",
        primary_phone_e164="+15555550177",
        is_phone_verified=True,
        onboarding_completed_at=datetime.now(timezone.utc),
        profile_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    current_session = Session(
        id=uuid4(),
        user_id=user.id,
        token_hash=auth.hash_session_token("raw-token"),
        risk_level=SessionRiskLevel.low,
        elevated_actions=[],
        last_seen_at=datetime.now(timezone.utc) - timedelta(days=1),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        session_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    current_session.user = user
    sibling_session = Session(
        id=uuid4(),
        user_id=user.id,
        token_hash="sibling",
        risk_level=SessionRiskLevel.low,
        elevated_actions=[],
        last_seen_at=datetime.now(timezone.utc) - timedelta(days=2),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        session_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    membership = Membership(
        id=uuid4(),
        user_id=user.id,
        business_id=uuid4(),
        role=MembershipRole.owner,
        status=MembershipStatus.active,
        membership_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    session = FakeAuthSession()
    session.scalar_queue = [current_session]
    session.execute_queue = [[current_session, sibling_session], [membership]]

    auth_ctx = await auth.resolve_auth_context(session, "raw-token")

    assert auth_ctx is not None
    assert auth_ctx.session.id == current_session.id
    assert auth_ctx.memberships[0].id == membership.id
    assert sibling_session.last_seen_at is not None
    assert sibling_session.expires_at is not None
    assert sibling_session.expires_at > datetime.now(timezone.utc) + timedelta(days=13)


@pytest.mark.asyncio
async def test_v2_verify_otp_step_up_marks_session(monkeypatch):
    auth_ctx = _make_auth_context(with_membership=True)
    session = FakeAuthSession()
    challenge = OTPChallenge(
        id=uuid4(),
        user_id=auth_ctx.user.id,
        phone_e164=auth_ctx.user.primary_phone_e164,
        channel=ChallengeChannel.sms,
        purpose=ChallengePurpose.step_up_export,
        status=ChallengeStatus.pending,
        attempt_count=0,
        max_attempts=5,
        requested_for_business_id=auth_ctx.memberships[0].business_id,
        challenge_metadata={},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.get_map[(OTPChallenge, challenge.id)] = challenge
    session.get_map[(User, auth_ctx.user.id)] = auth_ctx.user

    monkeypatch.setattr(
        "app_v2.services.messaging.check_sms_verification",
        lambda to, code: {"sid": "VE789", "status": "approved", "valid": True, "to": to},
    )

    result = await auth.verify_otp_challenge(
        session,
        OTPChallengeVerifyRequest(
            challenge_id=challenge.id,
            phone_e164=auth_ctx.user.primary_phone_e164,
            code="123456",
        ),
        ip_address="127.0.0.1",
        user_agent="pytest",
        auth_ctx=auth_ctx,
    )

    audits = [obj for obj in session.added if isinstance(obj, AuditLog)]
    assert result.step_up_granted is True
    assert result.token is None
    assert "step_up_export" in auth_ctx.session.elevated_actions
    assert "step_up_export" in auth_ctx.session.session_metadata["step_up_verified_at"]
    assert auth.has_recent_step_up(auth_ctx, ChallengePurpose.step_up_export)
    assert audits[-1].event_name == "auth.step_up.granted"


def test_v2_require_recent_step_up_enforces_recency():
    fresh_auth_ctx = _make_step_up_auth_context(verified_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    stale_auth_ctx = _make_step_up_auth_context(
        verified_at=datetime.now(timezone.utc) - timedelta(minutes=v2_settings.step_up_ttl_minutes + 1)
    )

    auth.require_recent_step_up(fresh_auth_ctx, ChallengePurpose.step_up_export)

    with pytest.raises(PermissionError, match="step_up_required"):
        auth.require_recent_step_up(stale_auth_ctx, ChallengePurpose.step_up_export)


def test_v2_verify_route_sets_http_only_cookie(monkeypatch):
    challenge = OTPChallenge(
        id=uuid4(),
        user_id=uuid4(),
        phone_e164="+15555550199",
        external_sid="VE999",
        channel=ChallengeChannel.sms,
        purpose=ChallengePurpose.sign_in,
        status=ChallengeStatus.approved,
        attempt_count=1,
        max_attempts=5,
        challenge_metadata={},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        approved_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    user = User(
        id=uuid4(),
        full_name="Session User",
        email="session@example.com",
        primary_phone_e164="+15555550199",
        is_phone_verified=True,
        onboarding_completed_at=datetime.now(timezone.utc),
        profile_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    issued_session = Session(
        id=uuid4(),
        user_id=user.id,
        token_hash="hashed",
        risk_level=SessionRiskLevel.low,
        elevated_actions=[],
        last_seen_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=336),
        session_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    async def override_db():
        yield DummySession()

    async def fake_verify(*args, **kwargs):
        return OTPChallengeVerificationResult(
            challenge=challenge,
            user=user,
            session=issued_session,
            token="raw-token",
            onboarding_required=False,
            step_up_granted=False,
        )

    monkeypatch.setattr("app_v2.api.routes.auth.auth.verify_otp_challenge", fake_verify)

    app.dependency_overrides[get_db_session] = override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v2/auth/challenges/verify",
            json={
                "challenge_id": str(challenge.id),
                "phone_e164": "+15555550199",
                "code": "123456",
            },
        )
        assert response.status_code == 200
        set_cookie = response.headers.get("set-cookie", "")
        assert f"{v2_settings.session_cookie_name}=raw-token" in set_cookie
        assert "HttpOnly" in set_cookie
    finally:
        app.dependency_overrides.clear()
