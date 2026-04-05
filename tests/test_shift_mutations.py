from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.business import Location, LocationRole, Role
from app.models.common import MembershipRole, MembershipStatus, SessionRiskLevel, ShiftStatus
from app.models.coverage import AuditLog
from app.models.identity import Membership, Session, User
from app.models.scheduling import Shift
from app.services.auth import AuthContext


class FakeSchedulingSession:
    def __init__(self):
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.scalar_queue: list[object] = []
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

    async def scalar(self, _query):
        if self.scalar_queue:
            return self.scalar_queue.pop(0)
        return None

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None

    async def delete(self, obj):
        self.deleted.append(obj)
        self.get_map.pop((type(obj), obj.id), None)


def _make_auth_context(*, business_id, location_id=None) -> AuthContext:
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        full_name="Manager Operator",
        email="manager@example.com",
        primary_phone_e164="+15555550199",
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
        expires_at=now + timedelta(hours=24),
        session_metadata={},
        created_at=now,
        updated_at=now,
    )
    membership = Membership(
        id=uuid4(),
        user_id=user.id,
        business_id=business_id,
        location_id=location_id,
        role=MembershipRole.owner,
        status=MembershipStatus.active,
        accepted_at=now,
        membership_metadata={},
        created_at=now,
        updated_at=now,
    )
    return AuthContext(user=user, session=session, memberships=[membership])


def test_update_shift_route_updates_shift():
    fake_session = FakeSchedulingSession()
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()

    location = Location(
        id=location_id,
        business_id=business_id,
        name="Downtown",
        slug="downtown",
        address_line_1="123 Main",
        locality="Los Angeles",
        region="CA",
        postal_code="90001",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
        google_place_metadata={},
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    role = Role(
        id=role_id,
        business_id=business_id,
        code="server",
        name="Server",
        min_notice_minutes=0,
        coverage_priority=100,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )
    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=now,
        ends_at=now + timedelta(hours=8),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
        requires_manager_approval=False,
        premium_cents=0,
        notes=None,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    fake_session.get_map[(Location, location_id)] = location
    fake_session.get_map[(Role, role_id)] = role
    fake_session.get_map[(Shift, shift_id)] = shift

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
      response = client.patch(
          f"/api/businesses/{business_id}/shifts/{shift_id}",
          json={
              "seats_requested": 2,
              "premium_cents": 1500,
              "requires_manager_approval": True,
              "notes": "Dinner rush coverage",
          },
      )
      assert response.status_code == 200
      payload = response.json()
      assert payload["seats_requested"] == 2
      assert payload["premium_cents"] == 1500
      assert payload["requires_manager_approval"] is True
      assert payload["notes"] == "Dinner rush coverage"
      assert any(
          isinstance(entry, AuditLog) and entry.event_name == "shift.updated"
          for entry in fake_session.added
      )
    finally:
      app.dependency_overrides.clear()


def test_create_shift_route_rejects_end_before_start():
    fake_session = FakeSchedulingSession()
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()

    location = Location(
        id=location_id,
        business_id=business_id,
        name="Downtown",
        slug="downtown",
        address_line_1="123 Main",
        locality="Los Angeles",
        region="CA",
        postal_code="90001",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
        google_place_metadata={},
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    role = Role(
        id=role_id,
        business_id=business_id,
        code="server",
        name="Server",
        min_notice_minutes=0,
        coverage_priority=100,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )
    location_role = LocationRole(
        id=uuid4(),
        location_id=location_id,
        role_id=role_id,
        is_active=True,
        premium_rules={},
        coverage_settings={},
        created_at=now,
        updated_at=now,
    )
    fake_session.get_map[(Location, location_id)] = location
    fake_session.get_map[(Role, role_id)] = role
    fake_session.scalar_queue = [location_role]

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/businesses/{business_id}/shifts",
            json={
                "location_id": str(location_id),
                "role_id": str(role_id),
                "source_system": "backfill_native",
                "timezone": "America/Los_Angeles",
                "starts_at": (now + timedelta(hours=8)).isoformat(),
                "ends_at": (now + timedelta(hours=2)).isoformat(),
                "seats_requested": 1,
                "requires_manager_approval": False,
                "premium_cents": 0,
                "notes": None,
                "shift_metadata": {},
            },
        )
        assert response.status_code == 400
        assert response.json() == {"detail": "shift_end_must_be_after_start"}
        assert all(not isinstance(entry, Shift) for entry in fake_session.added)
    finally:
        app.dependency_overrides.clear()


def test_delete_shift_route_deletes_empty_shift():
    fake_session = FakeSchedulingSession()
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=now,
        ends_at=now + timedelta(hours=8),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
        requires_manager_approval=False,
        premium_cents=0,
        notes=None,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    fake_session.get_map[(Shift, shift_id)] = shift
    fake_session.scalar_queue = [0, 0]

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
      response = client.delete(f"/api/businesses/{business_id}/shifts/{shift_id}")
      assert response.status_code == 200
      assert response.json() == {"deleted": True, "shift_id": str(shift_id)}
      assert fake_session.deleted == [shift]
      assert any(
          isinstance(entry, AuditLog) and entry.event_name == "shift.deleted"
          for entry in fake_session.added
      )
    finally:
      app.dependency_overrides.clear()
