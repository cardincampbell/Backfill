from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.business import Business, Location, Role
from app.models.common import (
    AssignmentStatus,
    CoverageCaseStatus,
    MembershipRole,
    MembershipStatus,
    SchedulerSyncEventStatus,
    SchedulerSyncJobStatus,
    SessionRiskLevel,
    ShiftStatus,
)
from app.models.coverage import CoverageCase
from app.models.identity import Membership, Session, User
from app.models.integrations import SchedulerConnection, SchedulerEvent, SchedulerSyncJob
from app.models.scheduling import Shift, ShiftAssignment
from app.services import scheduler_sync
from app.services.auth import AuthContext


class FakeSchedulerSession:
    def __init__(self):
        self.added: list[object] = []
        self.commits = 0
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

    async def scalar(self, _query):
        if self.scalar_queue:
            return self.scalar_queue.pop(0)
        return None

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))

    async def execute(self, _query):
        values = self.execute_queue.pop(0) if self.execute_queue else []
        return _ExecuteResult(values)

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


def test_scheduler_webhook_route_delegates_attendance_processing(monkeypatch):
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
        return {"status": "processed", "job_id": "job_attendance_123"}

    monkeypatch.setattr("app.api.routes.scheduler_provider_webhooks.scheduler_sync.resolve_connection", fake_resolve)
    monkeypatch.setattr("app.api.routes.scheduler_provider_webhooks.scheduler_sync.valid_scheduler_signature", lambda *args: True)
    monkeypatch.setattr("app.api.routes.scheduler_provider_webhooks.scheduler_sync.handle_attendance_event", fake_handle)

    app.dependency_overrides[get_db_session] = override_db
    try:
        client = TestClient(app)
        response = client.post(
            "/api/providers/schedulers/seven_shifts",
            json={
                "type": "punch.in",
                "id": "evt_456",
                "shift_id": "shift_123",
                "employee_id": "emp_123",
                "checked_in_at": "2026-04-21T17:00:00Z",
            },
        )
        assert response.status_code == 200
        assert response.json()["job_id"] == "job_attendance_123"
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
    def __init__(self, *, shift: Shift, coverage_case: CoverageCase | None):
        self.shift = shift
        self.coverage_case = coverage_case
        self.added: list[object] = []
        self.scalar_queue: list[object] = [0, coverage_case]
        self.execute_queue: list[list[object]] = [[]]

    def add(self, obj):
        now = datetime.now(timezone.utc)
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = now
        if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
            obj.updated_at = now
        self.added.append(obj)
        if isinstance(obj, CoverageCase):
            self.coverage_case = obj

    async def get(self, model, object_id, **kwargs):
        if model is Shift and object_id == self.shift.id:
            return self.shift
        if self.coverage_case is not None and model is CoverageCase and object_id == self.coverage_case.id:
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


async def _noop_async(*args, **kwargs):
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
    monkeypatch.setattr(scheduler_sync.coverage_runtime, "execute_queued_case", fail_execute)
    monkeypatch.setattr(scheduler_sync.forecast_history, "sync_attendance_history_fact_for_assignment", _noop_async)
    monkeypatch.setattr(scheduler_sync.forecast_history, "sync_callout_history_fact_for_case", _noop_async)

    result = await scheduler_sync.create_vacancy_for_shift(
        session,
        shift_id=shift_id,
        triggered_by="scheduler:test",
    )

    assert result["coverage_case_id"] == case_id
    assert result["offers"] == [str(standby_offer_id)]


@pytest.mark.asyncio
async def test_create_vacancy_delegates_general_dispatch_to_shared_runtime(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    case_id = uuid4()
    dispatched_offer_id = uuid4()
    now = datetime.now(timezone.utc)

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
    )
    coverage_case = CoverageCase(
        id=case_id,
        shift_id=shift_id,
        location_id=location_id,
        role_id=role_id,
        status=CoverageCaseStatus.queued,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
        created_at=now,
        updated_at=now,
    )
    session = FakeVacancySession(shift=shift, coverage_case=coverage_case)

    async def fake_activate(*args, **kwargs):
        return []

    async def fake_execute(_session, *, business_id, coverage_case_id, channel=None, dispatch_limit=None, offer_ttl_minutes=None, run_metadata=None):
        assert business_id == shift.business_id
        assert coverage_case_id == coverage_case.id
        assert channel == scheduler_sync.default_dispatch_channel()
        assert run_metadata == {"triggered_by": "scheduler:test"}
        return SimpleNamespace(offers=[SimpleNamespace(id=dispatched_offer_id)])

    monkeypatch.setattr(scheduler_sync.coverage_service, "activate_standby_queue", fake_activate)
    monkeypatch.setattr(scheduler_sync.coverage_runtime, "execute_queued_case", fake_execute)
    monkeypatch.setattr(scheduler_sync.forecast_history, "sync_attendance_history_fact_for_assignment", _noop_async)
    monkeypatch.setattr(scheduler_sync.forecast_history, "sync_callout_history_fact_for_case", _noop_async)

    result = await scheduler_sync.create_vacancy_for_shift(
        session,
        shift_id=shift_id,
        triggered_by="scheduler:test",
    )

    assert result["coverage_case_id"] == case_id
    assert result["offers"] == [str(dispatched_offer_id)]


@pytest.mark.asyncio
async def test_create_vacancy_reuses_active_offers_and_skips_duplicate_dispatch(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    case_id = uuid4()
    employee_id = uuid4()
    existing_offer_id = uuid4()
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
        status=CoverageCaseStatus.running,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
        created_at=now,
        updated_at=now,
    )
    session = FakeVacancySession(shift=shift, coverage_case=coverage_case)
    session.execute_queue = [
        [
            ShiftAssignment(
                shift_id=shift_id,
                employee_id=employee_id,
                status=AssignmentStatus.assigned,
                assigned_via="scheduler_sync",
                sequence_no=1,
            )
        ],
        [SimpleNamespace(id=existing_offer_id)],
    ]

    async def fail_activate(*args, **kwargs):
        raise AssertionError("standby activation should not run when active offers already exist")

    async def fail_execute(*args, **kwargs):
        raise AssertionError("general coverage dispatch should not run when active offers already exist")

    monkeypatch.setattr(scheduler_sync.coverage_service, "activate_standby_queue", fail_activate)
    monkeypatch.setattr(scheduler_sync.coverage_runtime, "execute_queued_case", fail_execute)
    monkeypatch.setattr(scheduler_sync.forecast_history, "sync_attendance_history_fact_for_assignment", _noop_async)
    monkeypatch.setattr(scheduler_sync.forecast_history, "sync_callout_history_fact_for_case", _noop_async)

    result = await scheduler_sync.create_vacancy_for_shift(
        session,
        shift_id=shift_id,
        employee_id=employee_id,
        triggered_by="scheduler:test",
    )

    assert result["coverage_case_id"] == case_id
    assert result["offers"] == [str(existing_offer_id)]
    assert coverage_case.case_metadata["excluded_employee_ids"] == [str(employee_id)]


@pytest.mark.asyncio
async def test_process_sync_job_attendance_scope_runs_schedule_and_attendance_reconcile(monkeypatch):
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    connection = SchedulerConnection(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        provider="7shifts",
        provider_location_ref="company-123",
        status="active",
        writeback_enabled=True,
        credentials={},
        webhook_secret="whsec_test_secret",
        secret_hint="whse...cret",
        connection_metadata={},
    )
    event = SchedulerEvent(
        id=uuid4(),
        connection_id=connection.id,
        business_id=business_id,
        location_id=location_id,
        provider="7shifts",
        source_event_id="7shifts:punch.in:evt_456",
        event_type="punch.in",
        event_scope="attendance",
        payload={
            "type": "punch.in",
            "id": "evt_456",
            "shift_id": "shift_123",
            "employee_id": "emp_123",
        },
        received_at=now,
        status=SchedulerSyncEventStatus.queued,
    )
    job = SchedulerSyncJob(
        id=uuid4(),
        connection_id=connection.id,
        scheduler_event_id=event.id,
        business_id=business_id,
        location_id=location_id,
        provider="7shifts",
        job_type="event_reconcile",
        priority=10,
        scope="attendance",
        scope_ref="shift_123",
        window_start=now - timedelta(days=1),
        window_end=now + timedelta(days=1),
        status=SchedulerSyncJobStatus.running,
        attempt_count=1,
        max_attempts=3,
        next_run_at=now,
        started_at=now,
    )
    session = FakeSchedulerSession()
    session.get_map[(SchedulerSyncJob, job.id)] = job
    session.get_map[(SchedulerConnection, connection.id)] = connection
    session.get_map[(SchedulerEvent, event.id)] = event

    async def fake_sync_schedule(_session, _connection, *, window_start, window_end):
        assert window_start == job.window_start
        assert window_end == job.window_end
        return {"created": 1, "updated": 2, "skipped": 0}

    async def fake_reconcile(_session, _connection, payload):
        assert payload == event.payload
        return {"created": 0, "updated": 1, "skipped": 0}

    monkeypatch.setattr(scheduler_sync, "sync_connection_schedule", fake_sync_schedule)
    monkeypatch.setattr(scheduler_sync, "reconcile_attendance_event", fake_reconcile)

    result = await scheduler_sync.process_sync_job(session, job.id)

    assert result == {
        "status": "completed",
        "job_id": str(job.id),
        "created": 1,
        "updated": 3,
        "skipped": 0,
    }
    assert job.status == SchedulerSyncJobStatus.completed
    assert event.status == SchedulerSyncEventStatus.processed
    assert session.commits == 1


@pytest.mark.asyncio
async def test_reconcile_attendance_event_updates_assignment_and_syncs_history(monkeypatch):
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    employee_id = uuid4()

    connection = SchedulerConnection(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        provider="7shifts",
        provider_location_ref="company-123",
        status="active",
        writeback_enabled=True,
        credentials={},
        webhook_secret="whsec_test_secret",
        secret_hint="whse...cret",
        connection_metadata={},
    )
    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        source_system="7shifts",
        source_shift_id="shift_123",
        timezone="America/Los_Angeles",
        starts_at=now - timedelta(hours=4),
        ends_at=now + timedelta(hours=4),
        seats_requested=1,
        seats_filled=1,
        status=ShiftStatus.covered,
    )
    employee = SimpleNamespace(id=employee_id)
    assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=shift_id,
        employee_id=employee_id,
        assigned_via="scheduler_sync",
        status=AssignmentStatus.assigned,
        sequence_no=1,
        assignment_metadata={"source": "scheduler_sync"},
        created_at=now - timedelta(hours=5),
        updated_at=now - timedelta(hours=5),
    )
    session = FakeSchedulerSession()
    session.scalar_queue = [shift, employee]
    session.execute_queue = [[assignment]]

    synced_history: list[dict[str, object]] = []

    async def fake_sync_history(
        _session,
        *,
        shift,
        assignment,
        source_system,
        source_payload=None,
    ):
        synced_history.append(
            {
                "shift_id": shift.id,
                "assignment_id": assignment.id,
                "status": assignment.status,
                "checked_in_at": assignment.checked_in_at,
                "checked_out_at": assignment.checked_out_at,
                "source_system": source_system,
                "source_payload": dict(source_payload or {}),
            }
        )
        return None

    monkeypatch.setattr(
        scheduler_sync.forecast_history,
        "sync_attendance_history_fact_for_assignment",
        fake_sync_history,
    )

    result = await scheduler_sync.reconcile_attendance_event(
        session,
        connection,
        {
            "type": "punch.out",
            "id": "evt_789",
            "shift_id": "shift_123",
            "employee_id": "emp_123",
            "checked_in_at": "2026-04-21T16:00:00Z",
            "checked_out_at": "2026-04-21T22:00:00Z",
        },
    )

    assert result == {"created": 0, "updated": 1, "skipped": 0}
    assert assignment.status == AssignmentStatus.completed
    assert assignment.checked_in_at == datetime(2026, 4, 21, 16, 0, tzinfo=timezone.utc)
    assert assignment.checked_out_at == datetime(2026, 4, 21, 22, 0, tzinfo=timezone.utc)
    assert shift.lifecycle_status.value == "completed"
    assert shift.staffing_status.value == "covered"
    assert len(synced_history) == 1
    assert synced_history[0]["source_system"] == "7shifts"
    assert synced_history[0]["source_payload"]["sync_origin"] == "scheduler_webhook"
    assert synced_history[0]["source_payload"]["shift_external_ref"] == "shift_123"
    assert synced_history[0]["source_payload"]["employee_external_ref"] == "emp_123"


@pytest.mark.asyncio
async def test_sync_connection_schedule_syncs_attendance_history_for_provider_assignments(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    old_employee_id = uuid4()
    new_employee_id = uuid4()
    now = datetime.now(timezone.utc)

    connection = SchedulerConnection(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        provider="7shifts",
        provider_location_ref="company-123",
        status="active",
        writeback_enabled=True,
        credentials={},
        webhook_secret="whsec_test_secret",
        secret_hint="whse...cret",
        connection_metadata={},
    )
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
        name="Cashier",
        code="cashier",
        metadata_json={},
        created_at=now,
        updated_at=now,
    )
    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        source_system="7shifts",
        source_shift_id="shift_123",
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
        seats_requested=1,
        seats_filled=1,
        requires_manager_approval=False,
        premium_cents=0,
        notes=None,
        shift_metadata={"source": "scheduler_sync"},
    )
    existing_assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=shift_id,
        employee_id=old_employee_id,
        assigned_via="scheduler_sync",
        status=AssignmentStatus.assigned,
        sequence_no=1,
        assignment_metadata={"source": "scheduler_sync"},
        created_at=now,
        updated_at=now,
    )
    employee = SimpleNamespace(id=new_employee_id)
    session = FakeSchedulerSession()
    session.get_map[(Location, location_id)] = location
    session.scalar_queue = [shift, employee]
    session.execute_queue = [[existing_assignment]]

    async def fake_get_or_create_role(*args, **kwargs):
        return role

    async def fake_sync_schedule(_connection, *, window_start, window_end):
        assert window_start < window_end
        return [
            SimpleNamespace(
                external_ref="shift_123",
                role_name="Cashier",
                timezone="America/Los_Angeles",
                starts_at=now + timedelta(hours=3),
                ends_at=now + timedelta(hours=11),
                seats_requested=1,
                requires_manager_approval=False,
                premium_cents=0,
                notes="Imported shift",
                metadata={"provider_status": "published"},
                assigned_external_refs=["emp_456"],
                status="published",
            )
        ]

    synced_assignments: list[dict[str, object]] = []

    async def fake_sync_attendance(
        _session,
        *,
        shift,
        assignment,
        source_system,
        source_payload=None,
    ):
        synced_assignments.append(
            {
                "shift_id": shift.id,
                "employee_id": assignment.employee_id,
                "status": assignment.status,
                "source_system": source_system,
                "source_payload": dict(source_payload or {}),
            }
        )
        return None

    monkeypatch.setattr(scheduler_sync, "_get_or_create_role", fake_get_or_create_role)
    monkeypatch.setattr(
        scheduler_sync,
        "adapter_for_connection",
        lambda _connection: SimpleNamespace(sync_schedule=fake_sync_schedule),
    )
    monkeypatch.setattr(
        scheduler_sync.forecast_history,
        "sync_attendance_history_fact_for_assignment",
        fake_sync_attendance,
    )

    result = await scheduler_sync.sync_connection_schedule(
        session,
        connection,
        window_start=now,
        window_end=now + timedelta(days=7),
    )

    assert result == {"created": 0, "updated": 1, "skipped": 0}
    assert shift.starts_at == now + timedelta(hours=3)
    assert shift.ends_at == now + timedelta(hours=11)
    assert shift.seats_filled == 1

    synced_by_employee = {entry["employee_id"]: entry for entry in synced_assignments}
    assert set(synced_by_employee) == {old_employee_id, new_employee_id}
    assert synced_by_employee[new_employee_id]["status"] == AssignmentStatus.assigned
    assert synced_by_employee[old_employee_id]["status"] == AssignmentStatus.cancelled
    assert all(entry["source_system"] == "7shifts" for entry in synced_assignments)
    assert all(entry["source_payload"]["sync_origin"] == "scheduler_sync" for entry in synced_assignments)
    assert all(entry["source_payload"]["shift_external_ref"] == "shift_123" for entry in synced_assignments)


@pytest.mark.asyncio
async def test_create_vacancy_syncs_scheduler_history_facts(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    employee_id = uuid4()
    now = datetime.now(timezone.utc)

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        source_system="7shifts",
        source_shift_id="shift_123",
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
        status=ShiftStatus.covered,
        seats_requested=1,
        seats_filled=1,
    )
    session = FakeVacancySession(shift=shift, coverage_case=None)
    session.scalar_queue = [0, None]
    session.execute_queue = [
        [
            ShiftAssignment(
                id=uuid4(),
                shift_id=shift_id,
                employee_id=employee_id,
                status=AssignmentStatus.assigned,
                assigned_via="scheduler_sync",
                sequence_no=1,
                assignment_metadata={"source": "scheduler_sync"},
                created_at=now,
                updated_at=now,
            )
        ]
    ]

    synced_attendance: list[dict[str, object]] = []
    synced_callouts: list[dict[str, object]] = []

    async def fake_sync_attendance(
        _session,
        *,
        shift,
        assignment,
        source_system,
        source_payload=None,
    ):
        synced_attendance.append(
            {
                "shift_id": shift.id,
                "employee_id": assignment.employee_id,
                "status": assignment.status,
                "source_system": source_system,
                "source_payload": dict(source_payload or {}),
            }
        )
        return None

    async def fake_sync_callout(
        _session,
        *,
        coverage_case,
        shift,
        source_system,
        source_payload=None,
    ):
        synced_callouts.append(
            {
                "coverage_case_id": coverage_case.id,
                "shift_id": shift.id,
                "status": coverage_case.status,
                "source_system": source_system,
                "source_payload": dict(source_payload or {}),
            }
        )
        return None

    monkeypatch.setattr(
        scheduler_sync.forecast_history,
        "sync_attendance_history_fact_for_assignment",
        fake_sync_attendance,
    )
    monkeypatch.setattr(
        scheduler_sync.forecast_history,
        "sync_callout_history_fact_for_case",
        fake_sync_callout,
    )

    result = await scheduler_sync.create_vacancy_for_shift(
        session,
        shift_id=shift_id,
        employee_id=employee_id,
        triggered_by="scheduler:test",
        auto_execute=False,
    )

    assert result["shift_id"] == shift_id
    assert result["coverage_case_id"] is not None
    assert result["offers"] == []
    assert len(synced_attendance) == 1
    assert synced_attendance[0]["employee_id"] == employee_id
    assert synced_attendance[0]["status"] == AssignmentStatus.cancelled
    assert synced_attendance[0]["source_system"] == "7shifts"
    assert synced_attendance[0]["source_payload"]["sync_origin"] == "scheduler_sync"
    assert len(synced_callouts) == 1
    assert synced_callouts[0]["coverage_case_id"] == result["coverage_case_id"]
    assert synced_callouts[0]["status"] == CoverageCaseStatus.queued
    assert synced_callouts[0]["source_system"] == "7shifts"
    assert synced_callouts[0]["source_payload"]["vacancy_reason_code"] == "scheduler_vacancy"


@pytest.mark.asyncio
async def test_get_or_create_employee_uses_business_timezone_when_location_missing_timezone():
    business_id = uuid4()
    location_id = uuid4()
    connection = SchedulerConnection(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        provider="7shifts",
        provider_location_ref="company-123",
        status="active",
        writeback_enabled=True,
        credentials={},
        webhook_secret="whsec_test_secret",
        secret_hint="whse...cret",
        connection_metadata={},
    )
    business = Business(
        id=business_id,
        name="Casa Vega LLC",
        display_name="Casa Vega",
        slug="casa-vega",
        timezone="America/Denver",
        settings={},
        place_metadata={},
    )
    location = Location(
        id=location_id,
        business_id=business_id,
        name="Downtown",
        display_name="Downtown",
        slug="downtown",
        timezone="",
        settings={},
        google_place_metadata={},
        is_active=True,
    )
    session = FakeSchedulerSession()
    session.get_map[(Business, business_id)] = business
    session.get_map[(Location, location_id)] = location
    session.scalar_queue = [None, None, None]

    employee, created = await scheduler_sync._get_or_create_employee(
        session,
        connection=connection,
        record=SimpleNamespace(
            external_ref="emp_123",
            full_name="Jamie Rivera",
            phone_e164="+15555550123",
            email="jamie@example.com",
            metadata={},
        ),
    )

    availability_rules = [
        entry for entry in session.added if entry.__class__.__name__ == "EmployeeAvailabilityRule"
    ]

    assert created is True
    assert employee.business_id == business_id
    assert len(availability_rules) == 7
    assert all(rule.timezone == "America/Denver" for rule in availability_rules)
