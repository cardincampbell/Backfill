from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.business import Business, Location, Role
from app.models.common import (
    AssignmentStatus,
    EmployeeStatus,
    MembershipRole,
    MembershipStatus,
    SessionRiskLevel,
    ShiftLifecycleStatus,
    ShiftStaffingStatus,
)
from app.models.identity import Membership, Session, User
from app.models.scheduling import Shift, ShiftAssignment
from app.models.workforce import Employee, EmployeeLocation, EmployeeScheduleAccessLink
from app.services import employee_schedule_links as svc
from app.services.auth import AuthContext


class FakeScalarResult:
    def __init__(self, items: list[object]):
        self._items = items

    def all(self) -> list[object]:
        return list(self._items)


class FakeExecuteResult:
    def __init__(self, items: list[object]):
        self._items = items

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self._items)


class FakeEmployeeScheduleSession:
    def __init__(self):
        self.get_map: dict[tuple[type, object], object] = {}
        self.scalar_queue: list[object] = []
        self.execute_queue: list[list[object]] = []
        self.added: list[object] = []
        self.flushed = 0
        self.commits = 0

    def add(self, obj):
        now = datetime.now(timezone.utc)
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = now
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = now
        self.added.append(obj)
        self.get_map[(type(obj), obj.id)] = obj

    async def get(self, model, object_id, **_kwargs):
        return self.get_map.get((model, object_id))

    async def scalar(self, _query):
        if self.scalar_queue:
            return self.scalar_queue.pop(0)
        return None

    async def execute(self, _query):
        rows = self.execute_queue.pop(0) if self.execute_queue else []
        return FakeExecuteResult(rows)

    async def flush(self):
        self.flushed += 1

    async def commit(self):
        self.commits += 1


def _make_auth_context(*, business_id) -> AuthContext:
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
        location_id=None,
        role=MembershipRole.owner,
        status=MembershipStatus.active,
        accepted_at=now,
        membership_metadata={},
        created_at=now,
        updated_at=now,
    )
    return AuthContext(user=user, session=session, memberships=[membership])


def _make_business(*, business_id) -> Business:
    now = datetime.now(timezone.utc)
    return Business(
        id=business_id,
        name="Coastal Hospitality Group",
        display_name="Coastal Hospitality Group",
        slug="coastal-hospitality-group",
        timezone="America/Los_Angeles",
        status="active",
        settings={"week_start_day": "monday"},
        place_metadata={},
        created_at=now,
        updated_at=now,
    )


def _make_location(*, business_id, location_id, name="Downtown") -> Location:
    now = datetime.now(timezone.utc)
    return Location(
        id=location_id,
        business_id=business_id,
        name=name,
        display_name=name,
        slug=name.lower(),
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


def _make_employee(*, business_id, employee_id) -> Employee:
    now = datetime.now(timezone.utc)
    return Employee(
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


def _make_link(*, business_id, employee_id, token_version=1) -> EmployeeScheduleAccessLink:
    now = datetime.now(timezone.utc)
    return EmployeeScheduleAccessLink(
        id=uuid4(),
        business_id=business_id,
        employee_id=employee_id,
        token_version=token_version,
        rotated_at=now,
        revoked_at=None,
        last_accessed_at=None,
        link_metadata={},
        created_at=now,
        updated_at=now,
    )


def _make_shift(*, business_id, location_id, role_id, employee_id, employee: Employee, location: Location) -> Shift:
    now = datetime.now(timezone.utc)
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
    shift = Shift(
        id=assignment.shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
        lifecycle_status=ShiftLifecycleStatus.scheduled,
        staffing_status=ShiftStaffingStatus.covered,
        seats_requested=1,
        seats_filled=1,
        requires_manager_approval=False,
        premium_cents=0,
        notes="Bring apron",
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    shift.role = role
    shift.location = location
    shift.assignments = [assignment]
    return shift


def test_schedule_token_round_trip():
    link = _make_link(business_id=uuid4(), employee_id=uuid4(), token_version=3)
    token = svc.build_employee_schedule_token(link)
    parsed = svc.parse_employee_schedule_token(token)
    assert parsed == (link.id, 3)


def test_schedule_link_includes_week_and_location():
    token = "bfv2sched_example"
    location_id = uuid4()
    url = svc.build_employee_schedule_link(
        token,
        week_start_date=datetime(2026, 4, 13, tzinfo=timezone.utc).date(),
        location_id=location_id,
    )
    assert "/schedule/" in url
    assert "week_start=2026-04-13" in url
    assert str(location_id) in url


def test_get_employee_schedule_link_route_creates_and_commits():
    fake_session = FakeEmployeeScheduleSession()
    business_id = uuid4()
    employee_id = uuid4()
    employee = _make_employee(business_id=business_id, employee_id=employee_id)
    fake_session.get_map[(Employee, employee_id)] = employee

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(f"/api/ops/businesses/{business_id}/employees/{employee_id}/schedule-link")
        assert response.status_code == 200
        payload = response.json()
        assert "/schedule/" in payload["schedule_url"]
        assert fake_session.commits == 1
    finally:
        app.dependency_overrides.clear()


def test_rotate_employee_schedule_link_route_returns_new_url():
    fake_session = FakeEmployeeScheduleSession()
    business_id = uuid4()
    employee_id = uuid4()
    employee = _make_employee(business_id=business_id, employee_id=employee_id)
    link = _make_link(business_id=business_id, employee_id=employee_id, token_version=1)
    first_url = svc.build_employee_schedule_link(svc.build_employee_schedule_token(link))
    fake_session.get_map[(Employee, employee_id)] = employee
    fake_session.scalar_queue = [link]

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(f"/api/ops/businesses/{business_id}/employees/{employee_id}/schedule-link/rotate")
        assert response.status_code == 200
        payload = response.json()
        assert payload["schedule_url"] != first_url
        assert fake_session.commits == 1
    finally:
        app.dependency_overrides.clear()


def test_public_employee_schedule_route_returns_schedule_and_headers():
    fake_session = FakeEmployeeScheduleSession()
    business_id = uuid4()
    employee_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    business = _make_business(business_id=business_id)
    location = _make_location(business_id=business_id, location_id=location_id)
    employee = _make_employee(business_id=business_id, employee_id=employee_id)
    employee_location = EmployeeLocation(
        id=uuid4(),
        employee_id=employee_id,
        location_id=location_id,
        is_primary=True,
        access_level="approved",
        can_cover_last_minute=True,
        can_blast=True,
        location_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    employee_location.location = location
    employee.employee_locations = [employee_location]
    link = _make_link(business_id=business_id, employee_id=employee_id)
    link.employee = employee
    link.business = business
    token = svc.build_employee_schedule_token(link)
    shift = _make_shift(
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        employee_id=employee_id,
        employee=employee,
        location=location,
    )

    fake_session.get_map[(EmployeeScheduleAccessLink, link.id)] = link
    fake_session.execute_queue = [[shift]]

    async def override_db():
        yield fake_session

    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/employee-schedules/{token}",
            params={"week_start": "2026-04-13", "location_id": str(location_id)},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["employee_name"] == employee.full_name
        assert payload["selected_location_name"] == location.location_display_name
        assert payload["shifts"][0]["role_name"] == "Barista"
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["x-robots-tag"] == "noindex, nofollow"
        assert fake_session.commits == 1
    finally:
        app.dependency_overrides.clear()


def test_public_employee_schedule_route_rejects_invalid_token():
    fake_session = FakeEmployeeScheduleSession()

    async def override_db():
        yield fake_session

    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)
    try:
        response = client.get("/api/employee-schedules/not-a-real-token")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
