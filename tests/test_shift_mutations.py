from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.business import Business, Location, LocationRole, Role
from app.models.common import (
    AssignmentStatus,
    CoverageAttemptStatus,
    CoverageCaseStatus,
    CoverageRunStatus,
    EmployeeStatus,
    MembershipRole,
    MembershipStatus,
    OfferStatus,
    OutboxChannel,
    OutboxStatus,
    SessionRiskLevel,
    ShiftLifecycleStatus,
    ShiftStaffingStatus,
    ShiftStatus,
)
from app.models.coverage import AuditLog, CoverageCase, CoverageCaseRun, CoverageContactAttempt, CoverageOffer, OutboxEvent
from app.models.identity import Membership, Session, User
from app.models.events import PlatformEvent
from app.models.scheduling import Shift, ShiftAssignment
from app.models.workforce import Employee, EmployeeLocation, EmployeeRole
from app.services.auth import AuthContext
from app.services import scheduling


class FakeSchedulingSession:
    def __init__(self):
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.scalar_queue: list[object] = []
        self.execute_queue: list[list[object]] = []
        self.get_map: dict[tuple[type, object], object] = {}
        self.get_kwargs: list[tuple[type, object, dict]] = []
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

    async def get(self, model, object_id, **_kwargs):
        self.get_kwargs.append((model, object_id, dict(_kwargs)))
        return self.get_map.get((model, object_id))

    async def scalar(self, _query):
        if self.scalar_queue:
            return self.scalar_queue.pop(0)
        return None

    async def execute(self, _query):
        rows = self.execute_queue.pop(0) if self.execute_queue else []

        class _ScalarResult:
            def __init__(self, values):
                self._values = values

            def all(self):
                return list(self._values)

        class _Result:
            def __init__(self, values):
                self._values = values

            def scalars(self):
                return _ScalarResult(self._values)

        return _Result(rows)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None

    async def delete(self, obj):
        self.deleted.append(obj)
        self.get_map.pop((type(obj), obj.id), None)


class ExplodingEmployeeRelationshipAssignment:
    def __init__(
        self,
        *,
        assignment_id,
        shift_id,
        employee_id,
        assigned_via,
        status,
        accepted_at=None,
        assignment_metadata=None,
    ):
        self.id = assignment_id
        self.shift_id = shift_id
        self.employee_id = employee_id
        self.assigned_via = assigned_via
        self.status = status
        self.accepted_at = accepted_at
        self.assignment_metadata = assignment_metadata or {}

    @property
    def employee(self):
        raise RuntimeError("lazy employee load attempted")


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
        lifecycle_status=ShiftLifecycleStatus.draft,
        staffing_status=ShiftStaffingStatus.open,
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
      get_call = next(
          call for call in fake_session.get_kwargs if call[0] is Shift and call[1] == shift_id
      )
      assert get_call[2].get("options")
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
        lifecycle_status=ShiftLifecycleStatus.draft,
        staffing_status=ShiftStaffingStatus.open,
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


def test_delete_shift_route_allows_assigned_draft_shift_without_coverage_history():
    fake_session = FakeSchedulingSession()
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    employee_id = uuid4()

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=now,
        ends_at=now + timedelta(hours=8),
        lifecycle_status=ShiftLifecycleStatus.draft,
        staffing_status=ShiftStaffingStatus.covered,
        seats_requested=1,
        seats_filled=1,
        requires_manager_approval=False,
        premium_cents=0,
        notes=None,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=shift_id,
        employee_id=employee_id,
        assigned_via="scheduler_ui",
        status=AssignmentStatus.assigned,
        sequence_no=1,
        assignment_metadata={},
        created_at=now,
        updated_at=now,
    )
    fake_session.get_map[(Shift, shift_id)] = shift
    fake_session.get_map[(ShiftAssignment, assignment.id)] = assignment
    fake_session.scalar_queue = [0]

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
    finally:
        app.dependency_overrides.clear()


def test_delete_shift_route_rejects_scheduled_shift_without_coverage_history():
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
        lifecycle_status=ShiftLifecycleStatus.scheduled,
        staffing_status=ShiftStaffingStatus.open,
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

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.delete(f"/api/businesses/{business_id}/shifts/{shift_id}")
        assert response.status_code == 409
        assert response.json()["detail"] == "scheduled_shift_delete_requires_republish"
        assert fake_session.deleted == []
    finally:
        app.dependency_overrides.clear()


def test_update_shift_assignment_route_emits_schedule_event():
    fake_session = FakeSchedulingSession()
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    shift_id = uuid4()
    employee_id = uuid4()
    assignment_id = uuid4()

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=uuid4(),
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=now,
        ends_at=now + timedelta(hours=8),
        status=ShiftStatus.covered,
        seats_requested=1,
        seats_filled=1,
        requires_manager_approval=False,
        premium_cents=0,
        notes=None,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Casey Server",
        status=EmployeeStatus.active,
        response_profile={},
        employee_metadata={},
        created_at=now,
        updated_at=now,
    )
    assignment = ShiftAssignment(
        id=assignment_id,
        shift_id=shift_id,
        employee_id=employee_id,
        assigned_via="scheduler_ui",
        status=AssignmentStatus.assigned,
        sequence_no=1,
        assignment_metadata={},
        created_at=now,
        updated_at=now,
    )
    assignment.employee = employee

    async def fake_set_shift_assignment(*_args, **_kwargs):
        return scheduling.ShiftAssignmentMutationResult(
            shift=shift,
            action="assigned",
            source="scheduler_ui",
            previous_assignment=None,
            current_assignment=assignment,
            cancelled_cases=[],
            cancelled_offers=[],
        )

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    original = scheduling.set_shift_assignment
    scheduling.set_shift_assignment = fake_set_shift_assignment
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.patch(
            f"/api/businesses/{business_id}/shifts/{shift_id}/assignment",
            json={
                "employee_id": str(employee_id),
                "source": "scheduler_ui",
                "expected_assignment_id": None,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["current_assignment"]["employee_id"] == str(employee_id)
        assert any(
            isinstance(entry, PlatformEvent)
            and entry.event_type == "schedule.shift.assigned"
            for entry in fake_session.added
        )
    finally:
        scheduling.set_shift_assignment = original
        app.dependency_overrides.clear()


def test_update_shift_assignment_route_returns_conflict_snapshot():
    fake_session = FakeSchedulingSession()
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    shift_id = uuid4()
    employee_id = uuid4()
    assignment_id = uuid4()

    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Current Owner",
        status=EmployeeStatus.active,
        response_profile={},
        employee_metadata={},
        created_at=now,
        updated_at=now,
    )
    assignment = ShiftAssignment(
        id=assignment_id,
        shift_id=shift_id,
        employee_id=employee_id,
        assigned_via="scheduler_ui",
        status=AssignmentStatus.assigned,
        sequence_no=1,
        assignment_metadata={},
        created_at=now,
        updated_at=now,
    )
    assignment.employee = employee

    async def fake_set_shift_assignment(*_args, **_kwargs):
        raise scheduling.ShiftAssignmentConflictError(assignment)

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    original = scheduling.set_shift_assignment
    scheduling.set_shift_assignment = fake_set_shift_assignment
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.patch(
            f"/api/businesses/{business_id}/shifts/{shift_id}/assignment",
            json={
                "employee_id": str(uuid4()),
                "source": "scheduler_ui",
                "expected_assignment_id": str(uuid4()),
            },
        )
        assert response.status_code == 409
        payload = response.json()
        assert payload["detail"]["code"] == "stale_assignment_conflict"
        assert payload["detail"]["current_assignment"]["assignment_id"] == str(assignment_id)
    finally:
        scheduling.set_shift_assignment = original
        app.dependency_overrides.clear()


def test_update_shift_assignment_route_tolerates_unloaded_employee_relation():
    fake_session = FakeSchedulingSession()
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    shift_id = uuid4()
    employee_id = uuid4()
    assignment_id = uuid4()

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=uuid4(),
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=now,
        ends_at=now + timedelta(hours=8),
        status=ShiftStatus.covered,
        seats_requested=1,
        seats_filled=1,
        requires_manager_approval=False,
        premium_cents=0,
        notes=None,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    assignment = ExplodingEmployeeRelationshipAssignment(
        assignment_id=assignment_id,
        shift_id=shift_id,
        employee_id=employee_id,
        assigned_via="scheduler_ui",
        status=AssignmentStatus.assigned,
        assignment_metadata={"employee_name": "Casey Server"},
    )

    async def fake_set_shift_assignment(*_args, **_kwargs):
        return scheduling.ShiftAssignmentMutationResult(
            shift=shift,
            action="assigned",
            source="scheduler_ui",
            previous_assignment=None,
            current_assignment=assignment,
            cancelled_cases=[],
            cancelled_offers=[],
        )

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    original = scheduling.set_shift_assignment
    scheduling.set_shift_assignment = fake_set_shift_assignment
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.patch(
            f"/api/businesses/{business_id}/shifts/{shift_id}/assignment",
            json={
                "employee_id": str(employee_id),
                "source": "scheduler_ui",
                "expected_assignment_id": None,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["current_assignment"]["employee_name"] == "Casey Server"
    finally:
        scheduling.set_shift_assignment = original
        app.dependency_overrides.clear()


def test_update_shift_assignment_conflict_tolerates_unloaded_employee_relation():
    fake_session = FakeSchedulingSession()
    business_id = uuid4()
    location_id = uuid4()
    shift_id = uuid4()
    employee_id = uuid4()
    assignment_id = uuid4()

    assignment = ExplodingEmployeeRelationshipAssignment(
        assignment_id=assignment_id,
        shift_id=shift_id,
        employee_id=employee_id,
        assigned_via="scheduler_ui",
        status=AssignmentStatus.assigned,
        assignment_metadata={"employee_name": "Current Owner"},
    )

    async def fake_set_shift_assignment(*_args, **_kwargs):
        raise scheduling.ShiftAssignmentConflictError(assignment)

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    original = scheduling.set_shift_assignment
    scheduling.set_shift_assignment = fake_set_shift_assignment
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.patch(
            f"/api/businesses/{business_id}/shifts/{shift_id}/assignment",
            json={
                "employee_id": str(uuid4()),
                "source": "scheduler_ui",
                "expected_assignment_id": str(uuid4()),
            },
        )
        assert response.status_code == 409
        payload = response.json()
        assert payload["detail"]["current_assignment"]["employee_name"] == "Current Owner"
    finally:
        scheduling.set_shift_assignment = original
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_set_shift_assignment_reassigns_and_cancels_active_automation():
    fake_session = FakeSchedulingSession()
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    current_employee_id = uuid4()
    next_employee_id = uuid4()
    current_assignment_id = uuid4()
    outbox_event_id = uuid4()

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
        code="barista",
        name="Barista",
        min_notice_minutes=0,
        coverage_priority=100,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )
    current_employee = Employee(
        id=current_employee_id,
        business_id=business_id,
        full_name="Alex Current",
        status=EmployeeStatus.active,
        response_profile={},
        employee_metadata={},
        created_at=now,
        updated_at=now,
    )
    next_employee = Employee(
        id=next_employee_id,
        business_id=business_id,
        full_name="Riley Next",
        status=EmployeeStatus.active,
        response_profile={},
        employee_metadata={},
        created_at=now,
        updated_at=now,
    )
    next_employee.employee_roles = [
        EmployeeRole(
            id=uuid4(),
            employee_id=next_employee_id,
            role_id=role_id,
            is_primary=True,
            role_metadata={},
            created_at=now,
            updated_at=now,
        )
    ]
    next_employee.employee_locations = [
        EmployeeLocation(
            id=uuid4(),
            employee_id=next_employee_id,
            location_id=location_id,
            is_primary=True,
            access_level="approved",
            can_cover_last_minute=True,
            can_blast=True,
            location_metadata={},
            created_at=now,
            updated_at=now,
        )
    ]

    current_assignment = ShiftAssignment(
        id=current_assignment_id,
        shift_id=shift_id,
        employee_id=current_employee_id,
        assigned_via="coverage_offer",
        status=AssignmentStatus.accepted,
        sequence_no=1,
        accepted_at=now - timedelta(minutes=10),
        assignment_metadata={},
        created_at=now - timedelta(minutes=10),
        updated_at=now - timedelta(minutes=10),
    )
    current_assignment.employee = current_employee

    outbox_event = OutboxEvent(
        id=outbox_event_id,
        aggregate_type="coverage_offer",
        aggregate_id=uuid4(),
        topic="coverage.offer.created",
        channel=OutboxChannel.sms,
        status=OutboxStatus.pending,
        attempt_count=0,
        payload={},
        result_payload={},
        created_at=now,
        updated_at=now,
    )
    offer = CoverageOffer(
        id=outbox_event.aggregate_id,
        coverage_case_id=uuid4(),
        coverage_case_run_id=uuid4(),
        employee_id=current_employee_id,
        channel=OutboxChannel.sms,
        status=OfferStatus.pending,
        idempotency_key="offer-key",
        offer_metadata={},
        created_at=now,
        updated_at=now,
    )
    attempt = CoverageContactAttempt(
        id=uuid4(),
        coverage_offer_id=offer.id,
        coverage_case_id=offer.coverage_case_id,
        coverage_case_run_id=offer.coverage_case_run_id,
        outbox_event_id=outbox_event_id,
        shift_id=shift_id,
        location_id=location_id,
        employee_id=current_employee_id,
        channel=OutboxChannel.sms,
        status=CoverageAttemptStatus.pending,
        attempt_no=1,
        requested_at=now - timedelta(minutes=5),
        attempt_metadata={},
        created_at=now,
        updated_at=now,
    )
    attempt.outbox_event = outbox_event
    offer.attempts = [attempt]

    run = CoverageCaseRun(
        id=offer.coverage_case_run_id,
        coverage_case_id=offer.coverage_case_id,
        phase_no=1,
        strategy="phase_1",
        status=CoverageRunStatus.running,
        run_metadata={},
        created_at=now,
        updated_at=now,
    )
    coverage_case = CoverageCase(
        id=offer.coverage_case_id,
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
    coverage_case.offers = [offer]
    coverage_case.runs = [run]

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=now,
        ends_at=now + timedelta(hours=8),
        status=ShiftStatus.filling,
        seats_requested=1,
        seats_filled=1,
        requires_manager_approval=False,
        premium_cents=0,
        notes=None,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    shift.location = location
    shift.role = role
    shift.assignments = [current_assignment]
    shift.coverage_cases = [coverage_case]

    fake_session.get_map[(Shift, shift_id)] = shift
    fake_session.get_map[(Employee, next_employee_id)] = next_employee
    fake_session.execute_queue = [[outbox_event]]

    result = await scheduling.set_shift_assignment(
        fake_session,
        business_id,
        shift_id,
        scheduling.ShiftAssignmentWrite(
            employee_id=next_employee_id,
            source="scheduler_ui",
            expected_assignment_id=current_assignment_id,
        ),
        assigned_by_user_id=uuid4(),
    )

    assert result.action == "reassigned"
    assert result.previous_assignment is current_assignment
    assert current_assignment.status == AssignmentStatus.replaced
    assert result.current_assignment is not None
    assert result.current_assignment.employee_id == next_employee_id
    assert shift.status == ShiftStatus.covered
    assert shift.seats_filled == 1
    assert coverage_case.status == CoverageCaseStatus.cancelled
    assert run.status == CoverageRunStatus.cancelled
    assert offer.status == OfferStatus.cancelled
    assert outbox_event.status == OutboxStatus.cancelled


@pytest.mark.asyncio
async def test_set_shift_assignment_rejects_multi_seat_shift():
    fake_session = FakeSchedulingSession()
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    shift_id = uuid4()

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=uuid4(),
        role_id=uuid4(),
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=now,
        ends_at=now + timedelta(hours=8),
        status=ShiftStatus.open,
        seats_requested=2,
        seats_filled=0,
        requires_manager_approval=False,
        premium_cents=0,
        notes=None,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    shift.assignments = []
    shift.coverage_cases = []
    fake_session.get_map[(Shift, shift_id)] = shift

    with pytest.raises(ValueError, match="single_seat_only_v1"):
        await scheduling.set_shift_assignment(
            fake_session,
            business_id,
            shift_id,
            scheduling.ShiftAssignmentWrite(
                employee_id=None,
                source="scheduler_ui",
                expected_assignment_id=None,
            ),
        )


@pytest.mark.asyncio
async def test_set_shift_assignment_keeps_draft_lifecycle_until_publish():
    fake_session = FakeSchedulingSession()
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    employee_id = uuid4()

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
        code="barista",
        name="Barista",
        min_notice_minutes=0,
        coverage_priority=100,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Jordan Draft",
        status=EmployeeStatus.active,
        response_profile={},
        employee_metadata={},
        created_at=now,
        updated_at=now,
    )
    employee.employee_roles = [
        EmployeeRole(
            id=uuid4(),
            employee_id=employee_id,
            role_id=role_id,
            is_primary=True,
            role_metadata={},
            created_at=now,
            updated_at=now,
        )
    ]
    employee.employee_locations = [
        EmployeeLocation(
            id=uuid4(),
            employee_id=employee_id,
            location_id=location_id,
            is_primary=True,
            access_level="approved",
            can_cover_last_minute=True,
            can_blast=True,
            location_metadata={},
            created_at=now,
            updated_at=now,
        )
    ]
    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=now,
        ends_at=now + timedelta(hours=8),
        lifecycle_status=ShiftLifecycleStatus.draft,
        staffing_status=ShiftStaffingStatus.open,
        seats_requested=1,
        seats_filled=0,
        requires_manager_approval=False,
        premium_cents=0,
        notes=None,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    shift.location = location
    shift.role = role
    shift.assignments = []
    shift.coverage_cases = []
    fake_session.get_map[(Shift, shift_id)] = shift
    fake_session.get_map[(Employee, employee_id)] = employee

    result = await scheduling.set_shift_assignment(
        fake_session,
        business_id,
        shift_id,
        scheduling.ShiftAssignmentWrite(
            employee_id=employee_id,
            source="scheduler_ui",
            expected_assignment_id=None,
        ),
    )

    assert result.current_assignment is not None
    assert shift.lifecycle_status == ShiftLifecycleStatus.draft
    assert shift.staffing_status == ShiftStaffingStatus.covered
    assert shift.status == ShiftStatus.draft


@pytest.mark.asyncio
async def test_publish_schedule_week_schedules_only_drafts_and_enqueues_notifications():
    fake_session = FakeSchedulingSession()
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    employee_id = uuid4()
    week_start = datetime(2026, 4, 13, tzinfo=timezone.utc).date()

    business = Business(
        id=business_id,
        name="Backfill Coffee",
        display_name="Backfill Coffee",
        slug="backfill-coffee",
        timezone="America/Los_Angeles",
        status="active",
        settings={"week_start_day": "monday"},
        place_metadata={},
        created_at=now,
        updated_at=now,
    )
    location = Location(
        id=location_id,
        business_id=business_id,
        name="Downtown",
        display_name="Downtown",
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
        code="barista",
        name="Barista",
        min_notice_minutes=0,
        coverage_priority=100,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Taylor Schedule",
        phone_e164="+15555550100",
        email="taylor@example.com",
        status=EmployeeStatus.active,
        response_profile={},
        employee_metadata={},
        created_at=now,
        updated_at=now,
    )
    published_assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=uuid4(),
        employee_id=employee_id,
        assigned_via="scheduler_ui",
        status=AssignmentStatus.assigned,
        sequence_no=1,
        assignment_metadata={"employee_name": employee.full_name},
        created_at=now,
        updated_at=now,
    )
    published_assignment.employee = employee
    draft_shift = Shift(
        id=published_assignment.shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=now,
        ends_at=now + timedelta(hours=8),
        lifecycle_status=ShiftLifecycleStatus.draft,
        staffing_status=ShiftStaffingStatus.covered,
        seats_requested=1,
        seats_filled=1,
        requires_manager_approval=False,
        premium_cents=0,
        notes=None,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    draft_shift.location = location
    draft_shift.role = role
    draft_shift.assignments = [published_assignment]
    draft_shift.coverage_cases = []

    already_scheduled_shift = Shift(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=1, hours=8),
        lifecycle_status=ShiftLifecycleStatus.scheduled,
        staffing_status=ShiftStaffingStatus.open,
        seats_requested=1,
        seats_filled=0,
        requires_manager_approval=False,
        premium_cents=0,
        notes=None,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    already_scheduled_shift.location = location
    already_scheduled_shift.role = role
    already_scheduled_shift.assignments = []
    already_scheduled_shift.coverage_cases = []

    fake_session.get_map[(Business, business_id)] = business
    fake_session.get_map[(Location, location_id)] = location
    fake_session.execute_queue = [[draft_shift, already_scheduled_shift]]

    result = await scheduling.publish_schedule_week(
        fake_session,
        business_id,
        location_id,
        week_start,
        scheduling.ScheduleWeekPublishWrite(
            source="scheduler_ui",
            notify_channels=["sms", "email"],
            expected_shift_ids=[draft_shift.id],
        ),
    )

    queued_events = [entry for entry in fake_session.added if isinstance(entry, OutboxEvent)]
    assert draft_shift.lifecycle_status == ShiftLifecycleStatus.scheduled
    assert already_scheduled_shift.lifecycle_status == ShiftLifecycleStatus.scheduled
    assert len(result.published_shifts) == 1
    assert len(result.already_scheduled_shifts) == 1
    assert result.notification_enqueued_assignment_count == 1
    assert result.notification_enqueued_employee_count == 1
    assert {event.channel.value for event in queued_events} == {"email"}
    assert all(event.payload.get("schedule_url") for event in queued_events)
    assert all(event.payload.get("unsubscribe_url") for event in queued_events)
    assert all("View your schedule:" in str(event.payload.get("text_body") or "") for event in queued_events)
    assert all(
        isinstance(event.payload.get("email_headers"), dict)
        and "List-Unsubscribe" in event.payload["email_headers"]
        for event in queued_events
    )


@pytest.mark.asyncio
async def test_publish_schedule_week_enqueues_sms_only_when_employee_opted_in():
    fake_session = FakeSchedulingSession()
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    employee_id = uuid4()
    week_start = datetime(2026, 4, 13, tzinfo=timezone.utc).date()

    business = Business(
        id=business_id,
        name="Backfill Coffee",
        display_name="Backfill Coffee",
        slug="backfill-coffee",
        timezone="America/Los_Angeles",
        status="active",
        settings={"week_start_day": "monday"},
        place_metadata={},
        created_at=now,
        updated_at=now,
    )
    location = Location(
        id=location_id,
        business_id=business_id,
        name="Downtown",
        display_name="Downtown",
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
        code="barista",
        name="Barista",
        min_notice_minutes=0,
        coverage_priority=100,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Taylor Schedule",
        phone_e164="+15555550100",
        email="taylor@example.com",
        status=EmployeeStatus.active,
        response_profile={},
        employee_metadata={
            "notification_preferences": {
                "schedule_publish_email_enabled": True,
                "schedule_publish_sms_enabled": True,
            }
        },
        created_at=now,
        updated_at=now,
    )
    assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=uuid4(),
        employee_id=employee_id,
        assigned_via="scheduler_ui",
        status=AssignmentStatus.assigned,
        sequence_no=1,
        assignment_metadata={"employee_name": employee.full_name},
        created_at=now,
        updated_at=now,
    )
    assignment.employee = employee
    draft_shift = Shift(
        id=assignment.shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=now,
        ends_at=now + timedelta(hours=8),
        lifecycle_status=ShiftLifecycleStatus.draft,
        staffing_status=ShiftStaffingStatus.covered,
        seats_requested=1,
        seats_filled=1,
        requires_manager_approval=False,
        premium_cents=0,
        notes=None,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    draft_shift.location = location
    draft_shift.role = role
    draft_shift.assignments = [assignment]
    draft_shift.coverage_cases = []

    fake_session.get_map[(Business, business_id)] = business
    fake_session.get_map[(Location, location_id)] = location
    fake_session.execute_queue = [[draft_shift]]

    result = await scheduling.publish_schedule_week(
        fake_session,
        business_id,
        location_id,
        week_start,
        scheduling.ScheduleWeekPublishWrite(
            source="scheduler_ui",
            notify_channels=["sms", "email"],
            expected_shift_ids=[draft_shift.id],
        ),
    )

    queued_events = [entry for entry in fake_session.added if isinstance(entry, OutboxEvent)]
    assert result.notification_enqueued_assignment_count == 1
    assert result.notification_enqueued_employee_count == 1
    assert {event.channel.value for event in queued_events} == {"sms", "email"}


@pytest.mark.asyncio
async def test_publish_schedule_week_skips_opted_out_email_notifications():
    fake_session = FakeSchedulingSession()
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    employee_id = uuid4()
    week_start = datetime(2026, 4, 13, tzinfo=timezone.utc).date()

    business = Business(
        id=business_id,
        name="Backfill Coffee",
        display_name="Backfill Coffee",
        slug="backfill-coffee",
        timezone="America/Los_Angeles",
        status="active",
        settings={"week_start_day": "monday"},
        place_metadata={},
        created_at=now,
        updated_at=now,
    )
    location = Location(
        id=location_id,
        business_id=business_id,
        name="Downtown",
        display_name="Downtown",
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
        code="barista",
        name="Barista",
        min_notice_minutes=0,
        coverage_priority=100,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Taylor Schedule",
        phone_e164="+15555550100",
        email="taylor@example.com",
        status=EmployeeStatus.active,
        response_profile={},
        employee_metadata={
            "notification_preferences": {
                "schedule_publish_email_enabled": True,
                "email_opted_out_at": now.isoformat(),
                "email_opt_out_reason": "employee_request",
            }
        },
        created_at=now,
        updated_at=now,
    )
    assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=uuid4(),
        employee_id=employee_id,
        assigned_via="scheduler_ui",
        status=AssignmentStatus.assigned,
        sequence_no=1,
        assignment_metadata={"employee_name": employee.full_name},
        created_at=now,
        updated_at=now,
    )
    assignment.employee = employee
    draft_shift = Shift(
        id=assignment.shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=now,
        ends_at=now + timedelta(hours=8),
        lifecycle_status=ShiftLifecycleStatus.draft,
        staffing_status=ShiftStaffingStatus.covered,
        seats_requested=1,
        seats_filled=1,
        requires_manager_approval=False,
        premium_cents=0,
        notes=None,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    draft_shift.location = location
    draft_shift.role = role
    draft_shift.assignments = [assignment]
    draft_shift.coverage_cases = []

    fake_session.get_map[(Business, business_id)] = business
    fake_session.get_map[(Location, location_id)] = location
    fake_session.execute_queue = [[draft_shift]]

    result = await scheduling.publish_schedule_week(
        fake_session,
        business_id,
        location_id,
        week_start,
        scheduling.ScheduleWeekPublishWrite(
            source="scheduler_ui",
            notify_channels=["email"],
            expected_shift_ids=[draft_shift.id],
        ),
    )

    queued_events = [entry for entry in fake_session.added if isinstance(entry, OutboxEvent)]
    assert result.notification_enqueued_assignment_count == 0
    assert result.notification_enqueued_employee_count == 0
    assert queued_events == []


@pytest.mark.asyncio
async def test_publish_schedule_week_skips_globally_suppressed_email_notifications(monkeypatch):
    fake_session = FakeSchedulingSession()
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    employee_id = uuid4()
    week_start = datetime(2026, 4, 13, tzinfo=timezone.utc).date()

    business = Business(
        id=business_id,
        name="Backfill Coffee",
        display_name="Backfill Coffee",
        slug="backfill-coffee",
        timezone="America/Los_Angeles",
        status="active",
        settings={"week_start_day": "monday"},
        place_metadata={},
        created_at=now,
        updated_at=now,
    )
    location = Location(
        id=location_id,
        business_id=business_id,
        name="Downtown",
        display_name="Downtown",
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
        code="barista",
        name="Barista",
        min_notice_minutes=0,
        coverage_priority=100,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Taylor Schedule",
        phone_e164="+15555550100",
        email="taylor@example.com",
        status=EmployeeStatus.active,
        response_profile={},
        employee_metadata={},
        created_at=now,
        updated_at=now,
    )
    assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=uuid4(),
        employee_id=employee_id,
        assigned_via="scheduler_ui",
        status=AssignmentStatus.assigned,
        sequence_no=1,
        assignment_metadata={"employee_name": employee.full_name},
        created_at=now,
        updated_at=now,
    )
    assignment.employee = employee
    draft_shift = Shift(
        id=assignment.shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=now,
        ends_at=now + timedelta(hours=8),
        lifecycle_status=ShiftLifecycleStatus.draft,
        staffing_status=ShiftStaffingStatus.covered,
        seats_requested=1,
        seats_filled=1,
        requires_manager_approval=False,
        premium_cents=0,
        notes=None,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    draft_shift.location = location
    draft_shift.role = role
    draft_shift.assignments = [assignment]
    draft_shift.coverage_cases = []

    async def fake_is_destination_suppressed(session, *, channel, destination, scope="global"):
        return channel == "email" and destination == "taylor@example.com"

    monkeypatch.setattr(
        "app.services.scheduling.communication_suppressions.is_destination_suppressed",
        fake_is_destination_suppressed,
    )

    fake_session.get_map[(Business, business_id)] = business
    fake_session.get_map[(Location, location_id)] = location
    fake_session.execute_queue = [[draft_shift]]

    result = await scheduling.publish_schedule_week(
        fake_session,
        business_id,
        location_id,
        week_start,
        scheduling.ScheduleWeekPublishWrite(
            source="scheduler_ui",
            notify_channels=["email"],
            expected_shift_ids=[draft_shift.id],
        ),
    )

    queued_events = [entry for entry in fake_session.added if isinstance(entry, OutboxEvent)]
    assert result.notification_enqueued_assignment_count == 0
    assert result.notification_enqueued_employee_count == 0
    assert queued_events == []


def test_publish_schedule_week_route_emits_shift_and_week_events():
    fake_session = FakeSchedulingSession()
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    shift_id = uuid4()

    published_shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=uuid4(),
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=now,
        ends_at=now + timedelta(hours=8),
        lifecycle_status=ShiftLifecycleStatus.scheduled,
        staffing_status=ShiftStaffingStatus.covered,
        seats_requested=1,
        seats_filled=1,
        requires_manager_approval=False,
        premium_cents=0,
        notes=None,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    published_shift.assignments = []

    async def fake_publish_schedule_week(*_args, **_kwargs):
        return scheduling.ScheduleWeekPublishResult(
            business_id=business_id,
            location_id=location_id,
            week_start_date=now.date(),
            week_end_date=(now + timedelta(days=6)).date(),
            published_shifts=[published_shift],
            already_scheduled_shifts=[],
            notification_enqueued_assignment_count=0,
            notification_enqueued_employee_count=0,
        )

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    original = scheduling.publish_schedule_week
    scheduling.publish_schedule_week = fake_publish_schedule_week
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/businesses/{business_id}/locations/{location_id}/schedule-weeks/{now.date().isoformat()}/publish",
            json={
                "source": "scheduler_ui",
                "notify_channels": ["sms", "email"],
                "expected_shift_ids": [str(shift_id)],
            },
        )
        assert response.status_code == 200
        assert any(
            isinstance(entry, PlatformEvent) and entry.event_type == "schedule.shift.published"
            for entry in fake_session.added
        )
        assert any(
            isinstance(entry, PlatformEvent) and entry.event_type == "schedule.week.published"
            for entry in fake_session.added
        )
    finally:
        scheduling.publish_schedule_week = original
        app.dependency_overrides.clear()


def test_publish_schedule_week_route_returns_conflict_snapshot():
    fake_session = FakeSchedulingSession()
    business_id = uuid4()
    location_id = uuid4()
    shift_id = uuid4()
    week_start = datetime(2026, 4, 13, tzinfo=timezone.utc).date()

    async def fake_publish_schedule_week(*_args, **_kwargs):
        raise scheduling.ScheduleWeekPublishConflictError(
            week_start_date=week_start,
            publishable_shift_ids=[shift_id],
            draft_shift_count=1,
            already_scheduled_shift_count=2,
        )

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    original = scheduling.publish_schedule_week
    scheduling.publish_schedule_week = fake_publish_schedule_week
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/businesses/{business_id}/locations/{location_id}/schedule-weeks/{week_start.isoformat()}/publish",
            json={
                "source": "scheduler_ui",
                "notify_channels": ["sms"],
                "expected_shift_ids": [str(uuid4())],
            },
        )
        assert response.status_code == 409
        payload = response.json()
        assert payload["detail"]["code"] == "stale_publish_conflict"
        assert payload["detail"]["current"]["publishable_shift_ids"] == [str(shift_id)]
        assert payload["detail"]["current"]["draft_shift_count"] == 1
    finally:
        scheduling.publish_schedule_week = original
        app.dependency_overrides.clear()


def test_publish_schedule_week_route_requires_target_location_access():
    fake_session = FakeSchedulingSession()
    business_id = uuid4()
    target_location_id = uuid4()
    other_location_id = uuid4()
    week_start = datetime(2026, 4, 13, tzinfo=timezone.utc).date()

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=other_location_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/businesses/{business_id}/locations/{target_location_id}/schedule-weeks/{week_start.isoformat()}/publish",
            json={
                "source": "scheduler_ui",
                "notify_channels": ["sms"],
                "expected_shift_ids": [],
            },
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "location_access_denied"
    finally:
        app.dependency_overrides.clear()


def test_publish_schedule_week_route_allows_target_location_manager():
    fake_session = FakeSchedulingSession()
    business_id = uuid4()
    location_id = uuid4()
    week_start = datetime(2026, 4, 13, tzinfo=timezone.utc).date()

    async def fake_publish_schedule_week(*_args, **_kwargs):
        return scheduling.ScheduleWeekPublishResult(
            business_id=business_id,
            location_id=location_id,
            week_start_date=week_start,
            week_end_date=(week_start + timedelta(days=6)),
            published_shifts=[],
            already_scheduled_shifts=[],
            notification_enqueued_assignment_count=0,
            notification_enqueued_employee_count=0,
        )

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    original = scheduling.publish_schedule_week
    scheduling.publish_schedule_week = fake_publish_schedule_week
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/businesses/{business_id}/locations/{location_id}/schedule-weeks/{week_start.isoformat()}/publish",
            json={
                "source": "scheduler_ui",
                "notify_channels": ["sms"],
                "expected_shift_ids": [],
            },
        )
        assert response.status_code == 200
        assert response.json()["week_start_date"] == week_start.isoformat()
    finally:
        scheduling.publish_schedule_week = original
        app.dependency_overrides.clear()
