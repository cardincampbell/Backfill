from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.business import Location
from app.models.common import CoverageCaseStatus, MembershipRole, MembershipStatus, SessionRiskLevel, ShiftStatus
from app.models.coverage import CoverageCase
from app.models.identity import Membership, Session, User
from app.models.integrations import SchedulerConnection
from app.models.scheduling import Shift
from app.services import scheduler_sync
from app.services.auth import AuthContext


class FakeSchedulerSession:
    def __init__(self):
        self.added: list[object] = []
        self.commits = 0
        self.scalar_queue: list[object] = []
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

    async def scalar(self, _query):
        if self.scalar_queue:
            return self.scalar_queue.pop(0)
        return None

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None


def _make_auth_context(*, business_id: uuid4, location_id):
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        full_name="Owner User",
        email="owner@example.com",
        primary_phone_e164="+15555550100",
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
        expires_at=now + timedelta(days=14),
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
        membership_metadata={},
        created_at=now,
        updated_at=now,
    )
    return AuthContext(user=user, session=session, memberships=[membership])


def test_put_scheduler_connection_route_returns_webhook_path():
    fake_session = FakeSchedulerSession()
    business_id = uuid4()
    location_id = uuid4()
    now = datetime.now(timezone.utc)
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
    fake_session.get_map[(Location, location_id)] = location
    fake_session.scalar_queue = [None]

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.put(
            f"/api/businesses/{business_id}/locations/{location_id}/scheduler-connection",
            json={
                "provider": "7shifts",
                "provider_location_ref": "company-123",
                "credentials": {
                    "client_id": "client-id",
                    "client_secret": "client-secret",
                },
                "webhook_secret": "whsec_test_secret",
                "writeback_enabled": True,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["provider"] == "7shifts"
        assert payload["provider_location_ref"] == "company-123"
        assert payload["writeback_enabled"] is True
        assert payload["webhook_path"].endswith(payload["id"])
        assert location.settings["scheduling_platform"] == "7shifts"
        assert location.settings["writeback_enabled"] is True
    finally:
        app.dependency_overrides.clear()


def test_scheduler_webhook_route_delegates_vacancy_processing(monkeypatch):
    connection = SchedulerConnection(
        id=uuid4(),
        business_id=uuid4(),
        location_id=uuid4(),
        provider="7shifts",
        provider_location_ref="company-123",
        status="active",
        writeback_enabled=True,
        credentials={},
        webhook_secret="whsec_test_secret",
        secret_hint="whse...cret",
        connection_metadata={},
    )

    async def override_db():
        yield object()

    async def fake_resolve(session, *, provider, connection_id=None, payload=None):
        return connection

    async def fake_handle(session, *, provider, payload, connection_id=None):
        return {"status": "queued", "job_id": "job_123"}

    monkeypatch.setattr("app.api.routes.scheduler_provider_webhooks.scheduler_sync.resolve_connection", fake_resolve)
    monkeypatch.setattr("app.api.routes.scheduler_provider_webhooks.scheduler_sync.valid_scheduler_signature", lambda *args: True)
    monkeypatch.setattr("app.api.routes.scheduler_provider_webhooks.scheduler_sync.handle_vacancy_event", fake_handle)

    app.dependency_overrides[get_db_session] = override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/providers/schedulers/seven_shifts",
            json={"type": "shift.deleted", "id": "evt_123", "shift_id": "shift_123"},
        )
        assert response.status_code == 200
        assert response.json()["job_id"] == "job_123"
    finally:
        app.dependency_overrides.clear()


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


class FakeVacancySession:
    def __init__(self, *, shift: Shift, coverage_case: CoverageCase):
        self.shift = shift
        self.coverage_case = coverage_case
        self.scalar_queue: list[object] = [0, coverage_case]
        self.execute_queue: list[list[object]] = [[]]

    async def get(self, model, object_id):
        if model is Shift and object_id == self.shift.id:
            return self.shift
        if model is CoverageCase and object_id == self.coverage_case.id:
            return self.coverage_case
        return None

    async def scalar(self, _query):
        if self.scalar_queue:
            return self.scalar_queue.pop(0)
        return None

    async def execute(self, _query):
        values = self.execute_queue.pop(0) if self.execute_queue else []
        return _ExecuteResult(values)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_create_vacancy_activates_standby_before_general_dispatch(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    case_id = uuid4()
    standby_offer_id = uuid4()
    now = datetime.now(timezone.utc)

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
        status=ShiftStatus.covered,
        seats_requested=1,
        seats_filled=1,
    )
    coverage_case = CoverageCase(
        id=case_id,
        shift_id=shift_id,
        location_id=location_id,
        role_id=role_id,
        status=CoverageCaseStatus.filled,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={"standby_queue": [{"position": 1, "employee_id": str(uuid4()), "offer_id": str(uuid4())}]},
        created_at=now,
        updated_at=now,
    )
    session = FakeVacancySession(shift=shift, coverage_case=coverage_case)

    async def fake_activate(*args, **kwargs):
        return [SimpleNamespace(id=standby_offer_id)]

    async def fail_execute(*args, **kwargs):
        raise AssertionError("general coverage dispatch should not run when standby activates first")

    monkeypatch.setattr(scheduler_sync.coverage_service, "activate_standby_queue", fake_activate)
    monkeypatch.setattr(scheduler_sync.coverage_service, "execute_next_coverage_phase", fail_execute)

    result = await scheduler_sync.create_vacancy_for_shift(
        session,
        shift_id=shift_id,
        triggered_by="scheduler:test",
    )

    assert result["coverage_case_id"] == case_id
    assert result["offers"] == [str(standby_offer_id)]
