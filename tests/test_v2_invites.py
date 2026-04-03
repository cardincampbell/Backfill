from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app_v2.api.deps import get_db_session
from app_v2.main import app
from app_v2.models.business import Business, Location
from app_v2.models.common import (
    ChallengePurpose,
    ChallengeStatus,
    InviteStatus,
    MembershipRole,
    MembershipStatus,
    SessionRiskLevel,
)
from app_v2.models.identity import ManagerInvite, Membership, OTPChallenge, Session, User
from app_v2.schemas.auth import OTPChallengeVerifyRequest
from app_v2.services import auth, invites
from app_v2.services.auth import AuthContext


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

    def all(self):
        return list(self._values)


class FakeInviteSession:
    def __init__(self):
        self.added: list[object] = []
        self.scalar_queue: list[object] = []
        self.execute_queue: list[list[object]] = []
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

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))

    async def scalar(self, _query):
        if self.scalar_queue:
            return self.scalar_queue.pop(0)
        return None

    async def execute(self, _query):
        values = self.execute_queue.pop(0) if self.execute_queue else []
        return _ExecuteResult(values)

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None


@pytest.mark.asyncio
async def test_v2_create_manager_invite_uses_business_name_in_email_subject(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    inviter_id = uuid4()
    session = FakeInviteSession()
    session.get_map[(Business, business_id)] = Business(
        id=business_id,
        legal_name="Whole Foods Market LLC",
        brand_name="Whole Foods Market",
        slug="whole-foods-market",
        timezone="America/Los_Angeles",
        status="active",
        settings={},
        place_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.get_map[(Location, location_id)] = Location(
        id=location_id,
        business_id=business_id,
        name="Downtown Los Angeles",
        slug="downtown-los-angeles",
        address_line_1="788 S Grand Ave",
        locality="Los Angeles",
        region="CA",
        postal_code="90017",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
        google_place_metadata={},
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.scalar_queue = [None, None]

    captured: dict[str, str] = {}

    def fake_send_email(*, to: str, subject: str, text_body: str, html_body: str | None = None):
        captured["to"] = to
        captured["subject"] = subject
        captured["text_body"] = text_body
        captured["html_body"] = html_body or ""
        return "sg_msg_123"

    monkeypatch.setattr("app_v2.services.invites.messaging.send_email", fake_send_email)

    invite, created, delivery_id = await invites.create_manager_invite(
        session,
        business_id=business_id,
        location_id=location_id,
        email="manager@example.com",
        manager_name="Jamie",
        role="manager",
        invited_by_user_id=inviter_id,
        inviter_name="Cardin Campbell",
    )

    assert invite is not None
    assert created is True
    assert delivery_id == "sg_msg_123"
    assert captured["to"] == "manager@example.com"
    assert captured["subject"] == "You're invited to manage Whole Foods Market in Backfill"
    assert "Backfill handles callouts and last-minute shift changes automatically" in captured["text_body"]
    assert "Callouts covered." in captured["html_body"]


@pytest.mark.asyncio
async def test_v2_verify_invite_acceptance_uses_invited_name_to_complete_onboarding(monkeypatch):
    session = FakeInviteSession()
    challenge_id = uuid4()
    business_id = uuid4()
    location_id = uuid4()
    invite_id = uuid4()
    now = datetime.now(timezone.utc)

    challenge = OTPChallenge(
        id=challenge_id,
        phone_e164="+15555550123",
        channel="sms",
        purpose=ChallengePurpose.invite_acceptance,
        status=ChallengeStatus.pending,
        attempt_count=0,
        max_attempts=5,
        requested_for_business_id=business_id,
        requested_for_location_id=location_id,
        expires_at=now + timedelta(minutes=10),
        challenge_metadata={
            "invite_id": str(invite_id),
            "invite_email": "manager@example.com",
            "manager_name": "Jamie Rivera",
        },
        created_at=now,
        updated_at=now,
    )
    invite = ManagerInvite(
        id=invite_id,
        business_id=business_id,
        location_id=location_id,
        role=MembershipRole.manager,
        recipient_email="manager@example.com",
        token_hash="hashed",
        status=InviteStatus.pending,
        expires_at=now + timedelta(hours=24),
        invite_metadata={"manager_name": "Jamie Rivera"},
        created_at=now,
        updated_at=now,
    )
    session.get_map[(OTPChallenge, challenge_id)] = challenge
    session.get_map[(ManagerInvite, invite_id)] = invite
    session.scalar_queue = [None, None, None]

    monkeypatch.setattr(
        "app_v2.services.messaging.check_sms_verification",
        lambda to, code: {"sid": "VE123", "status": "approved", "valid": True, "to": to},
    )

    result = await auth.verify_otp_challenge(
        session,
        OTPChallengeVerifyRequest(
            challenge_id=challenge_id,
            phone_e164="+1 (555) 555-0123",
            code="123456",
        ),
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    memberships = [obj for obj in session.added if isinstance(obj, Membership)]
    assert result.session is not None
    assert result.token is not None
    assert result.user.email == "manager@example.com"
    assert result.user.primary_phone_e164 == "+15555550123"
    assert result.onboarding_required is False
    assert result.user.full_name == "Jamie Rivera"
    assert result.user.onboarding_completed_at is not None
    assert invite.status == InviteStatus.accepted
    assert invite.accepted_at is not None
    assert len(memberships) == 1
    assert memberships[0].business_id == business_id
    assert memberships[0].location_id == location_id
    assert memberships[0].status == MembershipStatus.active


@pytest.mark.asyncio
async def test_v2_verify_invite_acceptance_requires_onboarding_when_name_missing(monkeypatch):
    session = FakeInviteSession()
    challenge_id = uuid4()
    business_id = uuid4()
    location_id = uuid4()
    invite_id = uuid4()
    now = datetime.now(timezone.utc)

    challenge = OTPChallenge(
        id=challenge_id,
        phone_e164="+15555550124",
        channel="sms",
        purpose=ChallengePurpose.invite_acceptance,
        status=ChallengeStatus.pending,
        attempt_count=0,
        max_attempts=5,
        requested_for_business_id=business_id,
        requested_for_location_id=location_id,
        expires_at=now + timedelta(minutes=10),
        challenge_metadata={
            "invite_id": str(invite_id),
            "invite_email": "manager@example.com",
        },
        created_at=now,
        updated_at=now,
    )
    invite = ManagerInvite(
        id=invite_id,
        business_id=business_id,
        location_id=location_id,
        role=MembershipRole.manager,
        recipient_email="manager@example.com",
        token_hash="hashed",
        status=InviteStatus.pending,
        expires_at=now + timedelta(hours=24),
        invite_metadata={},
        created_at=now,
        updated_at=now,
    )
    session.get_map[(OTPChallenge, challenge_id)] = challenge
    session.get_map[(ManagerInvite, invite_id)] = invite
    session.scalar_queue = [None, None, None]

    monkeypatch.setattr(
        "app_v2.services.messaging.check_sms_verification",
        lambda to, code: {"sid": "VE124", "status": "approved", "valid": True, "to": to},
    )

    result = await auth.verify_otp_challenge(
        session,
        OTPChallengeVerifyRequest(
            challenge_id=challenge_id,
            phone_e164="+1 (555) 555-0124",
            code="123456",
        ),
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    memberships = [obj for obj in session.added if isinstance(obj, Membership)]
    assert result.session is not None
    assert result.token is not None
    assert result.user.email == "manager@example.com"
    assert result.user.full_name is None
    assert result.user.onboarding_completed_at is None
    assert result.onboarding_required is True
    assert invite.status == InviteStatus.accepted
    assert len(memberships) == 1


def test_v2_request_manager_invite_challenge_sets_invite_acceptance_purpose(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    invite_id = uuid4()
    preview = invites.ManagerInvitePreview(
        invite=ManagerInvite(
            id=invite_id,
            business_id=business_id,
            location_id=location_id,
            role=MembershipRole.manager,
            recipient_email="manager@example.com",
            token_hash="hashed",
            status=InviteStatus.pending,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            invite_metadata={"manager_name": "Jamie Rivera"},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        business=Business(
            id=business_id,
            legal_name="Whole Foods Market LLC",
            brand_name="Whole Foods Market",
            slug="whole-foods-market",
            timezone="America/Los_Angeles",
            status="active",
            settings={},
            place_metadata={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        location=Location(
            id=location_id,
            business_id=business_id,
            name="Downtown Los Angeles",
            slug="downtown-los-angeles",
            address_line_1="788 S Grand Ave",
            locality="Los Angeles",
            region="CA",
            postal_code="90017",
            country_code="US",
            timezone="America/Los_Angeles",
            settings={},
            google_place_metadata={},
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        recipient_has_phone=True,
        manager_name="Jamie Rivera",
    )

    captured: dict[str, object] = {}

    async def override_db():
        yield FakeInviteSession()

    async def fake_get_preview(_session, *, raw_token: str):
        assert raw_token == "token_123"
        return preview

    async def fake_request_challenge(_session, payload, *, ip_address=None, user_agent=None, auth_ctx=None):
        captured["payload"] = payload
        challenge = OTPChallenge(
            id=uuid4(),
            phone_e164=payload.phone_e164,
            channel="sms",
            purpose=ChallengePurpose.invite_acceptance,
            status=ChallengeStatus.pending,
            attempt_count=0,
            max_attempts=5,
            requested_for_business_id=payload.business_id,
            requested_for_location_id=payload.location_id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            challenge_metadata=payload.challenge_metadata,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        return challenge, True

    monkeypatch.setattr("app_v2.api.routes.invites.invites.get_invite_preview", fake_get_preview)
    monkeypatch.setattr("app_v2.api.routes.invites.auth_service.request_otp_challenge", fake_request_challenge)

    app.dependency_overrides[get_db_session] = override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v2/manager-invites/token_123/request-challenge",
            json={
                "phone_e164": "+15555550123",
                "manager_name": "Jamie Rivera",
            },
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["invite_mode"] == "existing_user"
        request_payload = captured["payload"]
        assert request_payload.purpose == "invite_acceptance"
        assert str(request_payload.business_id) == str(business_id)
        assert str(request_payload.location_id) == str(location_id)
        assert request_payload.challenge_metadata["invite_id"] == str(invite_id)
        assert request_payload.challenge_metadata["invite_email"] == "manager@example.com"
        assert request_payload.challenge_metadata["manager_name"] == "Jamie Rivera"
    finally:
        app.dependency_overrides.clear()
