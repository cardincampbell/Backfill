from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app_v2.api.deps import get_auth_context, get_db_session
from app_v2.main import app
from app_v2.models.business import Location
from app_v2.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app_v2.models.coverage import AuditLog
from app_v2.models.identity import Membership, Session, User
from app_v2.services.auth import AuthContext


class FakeSettingsSession:
    def __init__(self):
        self.added: list[object] = []
        self.get_map: dict[tuple[type, object], object] = {}
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
        self.get_map[(type(obj), obj.id)] = obj

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None


def _make_auth_context(*, business_id, location_id=None) -> AuthContext:
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
        role=MembershipRole.manager,
        status=MembershipStatus.active,
        accepted_at=now,
        membership_metadata={},
        created_at=now,
        updated_at=now,
    )
    return AuthContext(user=user, session=session, memberships=[membership])


def _make_location(*, business_id, location_id) -> Location:
    now = datetime.now(timezone.utc)
    return Location(
        id=location_id,
        business_id=business_id,
        name="Santa Monica",
        slug="santa-monica",
        address_line_1="123 Ocean Ave",
        locality="Santa Monica",
        region="CA",
        postal_code="90401",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
        google_place_metadata={},
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def test_v2_get_location_settings_returns_defaults():
    fake_session = FakeSettingsSession()
    business_id = uuid4()
    location_id = uuid4()
    fake_session.get_map[(Location, location_id)] = _make_location(
        business_id=business_id,
        location_id=location_id,
    )

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(f"/api/v2/businesses/{business_id}/locations/{location_id}/settings")
        assert response.status_code == 200
        assert response.json() == {
            "location_id": str(location_id),
            "coverage_requires_manager_approval": False,
            "late_arrival_policy": "wait",
            "missed_check_in_policy": "manager_action",
            "agency_supply_approved": False,
            "writeback_enabled": False,
            "timezone": "America/Los_Angeles",
            "scheduling_platform": "backfill_native",
            "integration_status": None,
            "backfill_shifts_enabled": False,
            "backfill_shifts_launch_state": "off",
            "backfill_shifts_beta_eligible": False,
        }
    finally:
        app.dependency_overrides.clear()


def test_v2_patch_location_settings_updates_location_and_audits():
    fake_session = FakeSettingsSession()
    business_id = uuid4()
    location_id = uuid4()
    location = _make_location(business_id=business_id, location_id=location_id)
    fake_session.get_map[(Location, location_id)] = location

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.patch(
            f"/api/v2/businesses/{business_id}/locations/{location_id}/settings",
            json={
                "coverage_requires_manager_approval": True,
                "late_arrival_policy": "start_coverage",
                "backfill_shifts_enabled": True,
                "backfill_shifts_launch_state": "beta",
                "integration_status": "connected",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["coverage_requires_manager_approval"] is True
        assert payload["late_arrival_policy"] == "start_coverage"
        assert payload["backfill_shifts_enabled"] is True
        assert payload["backfill_shifts_launch_state"] == "beta"
        assert payload["integration_status"] == "connected"
        assert location.settings["coverage_requires_manager_approval"] is True
        assert location.settings["late_arrival_policy"] == "start_coverage"
        assert location.settings["backfill_shifts_enabled"] is True
        assert location.settings["backfill_shifts_launch_state"] == "beta"
        assert location.settings["integration_status"] == "connected"
        assert any(
            isinstance(entry, AuditLog) and entry.event_name == "location.settings.updated"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()
