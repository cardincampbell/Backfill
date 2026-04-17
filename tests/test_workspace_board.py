from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.business import Business, Location, LocationRole, Role
from app.models.common import (
    AuditActorType,
    AssignmentStatus,
    CoverageCaseStatus,
    MembershipRole,
    MembershipStatus,
    OfferStatus,
    SessionRiskLevel,
    ShiftStatus,
)
from app.models.coverage import CoverageCase, CoverageOffer
from app.models.events import PlatformEvent
from app.models.identity import Membership, Session, User
from app.models.scheduling import Shift, ShiftAssignment
from app.models.workforce import Employee, EmployeeLocation, EmployeeRole
from app.schemas.workspace_board import WorkspaceBoardActionSummaryRead, WorkspaceLocationBoardRead
from app.services import workspace_board
from app.services.auth import AuthContext


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


class FakeWorkspaceBoardSession:
    def __init__(self):
        self.get_map: dict[tuple[type, object], object] = {}
        self.execute_queue: list[list[object]] = []

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))

    async def execute(self, _query):
        values = self.execute_queue.pop(0) if self.execute_queue else []
        return _ExecuteResult(values)


def _make_auth_context(*, business_id, location_id) -> AuthContext:
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
    membership = Membership(
        id=uuid4(),
        user_id=user.id,
        business_id=business_id,
        location_id=location_id,
        role=MembershipRole.owner,
        status=MembershipStatus.active,
        accepted_at=datetime.now(timezone.utc),
        membership_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    return AuthContext(user=user, session=session, memberships=[membership])


def test_location_board_route_returns_snapshot(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    auth_ctx = _make_auth_context(business_id=business_id, location_id=location_id)

    async def override_db():
        yield FakeWorkspaceBoardSession()

    async def override_auth():
        return auth_ctx

    async def fake_get_location_board(_session, *, business_id, location_id, week_start=None):
        assert business_id == auth_ctx.memberships[0].business_id
        assert location_id == auth_ctx.memberships[0].location_id
        return WorkspaceLocationBoardRead(
            business_id=business_id,
            business_name="Casa Vega",
            business_slug="casa-vega",
            location_id=location_id,
            location_name="West Hollywood",
            location_slug="west-hollywood",
            country_code="US",
            timezone="America/Los_Angeles",
            week_start_date=date(2026, 4, 6),
            week_end_date=date(2026, 4, 12),
            roles=[],
            workers=[],
            shifts=[],
            action_summary=WorkspaceBoardActionSummaryRead(
                total=0,
                approval_required=0,
                active_coverage=0,
                open_shifts=0,
            ),
        )

    monkeypatch.setattr(
        "app.api.routes.workspace.workspace_board_service.get_location_board",
        fake_get_location_board,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/workspace/businesses/{business_id}/locations/{location_id}/board"
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["business_name"] == "Casa Vega"
        assert payload["location_name"] == "West Hollywood"
    finally:
        app.dependency_overrides.clear()


def test_board_window_respects_configured_week_start_day():
    window = workspace_board.board_window(
        "America/Los_Angeles",
        "sunday",
        date(2026, 4, 8),
    )

    assert window.week_start == date(2026, 4, 5)
    assert window.week_end == date(2026, 4, 11)


async def _build_board() -> WorkspaceLocationBoardRead:
    session = FakeWorkspaceBoardSession()
    now = datetime(2026, 4, 6, 16, 0, tzinfo=timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    employee_id = uuid4()
    shift_id = uuid4()
    case_id = uuid4()

    business = Business(
        id=business_id,
        name="Whole Foods Market LLC",
        display_name="Whole Foods Market",
        slug="whole-foods-market",
        timezone="America/Los_Angeles",
        status="active",
        settings={},
        place_metadata={},
        created_at=now,
        updated_at=now,
    )
    location = Location(
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
        created_at=now,
        updated_at=now,
    )
    role = Role(
        id=role_id,
        business_id=business_id,
        code="cashier",
        name="Cashier",
        created_at=now,
        updated_at=now,
    )
    location_role = LocationRole(
        id=uuid4(),
        location_id=location_id,
        role_id=role_id,
        role=role,
        is_active=True,
        min_headcount=2,
        max_headcount=5,
        premium_rules={},
        coverage_settings={},
        created_at=now,
        updated_at=now,
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Jamie Rivera",
        phone_e164="+15555550123",
        email="jamie@example.com",
        reliability_score=0.925,
        avg_response_time_seconds=120,
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
            role=role,
            proficiency_level=3,
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
    assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=shift_id,
        employee_id=employee_id,
        employee=employee,
        assigned_via="coverage_offer",
        status=AssignmentStatus.accepted,
        sequence_no=1,
        accepted_at=now,
        assignment_metadata={},
        created_at=now,
        updated_at=now,
    )
    case = CoverageCase(
        id=case_id,
        shift_id=shift_id,
        location_id=location_id,
        role_id=role_id,
        status=CoverageCaseStatus.running,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=True,
        case_metadata={},
        created_at=now,
        updated_at=now,
    )
    case.offers = [
        CoverageOffer(
            id=uuid4(),
            coverage_case_id=case_id,
            employee_id=employee_id,
            channel="sms",
            status=OfferStatus.delivered,
            idempotency_key="offer-delivered",
            offer_metadata={},
            created_at=now,
            updated_at=now,
        ),
        CoverageOffer(
            id=uuid4(),
            coverage_case_id=case_id,
            employee_id=employee_id,
            channel="sms",
            status=OfferStatus.pending,
            idempotency_key="offer-pending",
            offer_metadata={},
            created_at=now,
            updated_at=now,
        ),
    ]
    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        role=role,
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
        status=ShiftStatus.open,
        seats_requested=2,
        seats_filled=1,
        requires_manager_approval=True,
        premium_cents=500,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    shift.assignments = [assignment]
    shift.coverage_cases = [case]

    session.get_map[(Business, business_id)] = business
    session.get_map[(Location, location_id)] = location
    session.execute_queue = [[location_role], [role], [employee], [shift], []]

    return await workspace_board.get_location_board(
        session,
        business_id=business_id,
        location_id=location_id,
        week_start=date(2026, 4, 6),
    )


async def _build_board_without_location_roles() -> WorkspaceLocationBoardRead:
    session = FakeWorkspaceBoardSession()
    now = datetime(2026, 4, 6, 16, 0, tzinfo=timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    employee_id = uuid4()

    business = Business(
        id=business_id,
        name="Whole Foods Market LLC",
        display_name="Whole Foods Market",
        slug="whole-foods-market",
        timezone="America/Los_Angeles",
        status="active",
        settings={},
        place_metadata={},
        created_at=now,
        updated_at=now,
    )
    location = Location(
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
        created_at=now,
        updated_at=now,
    )
    role = Role(
        id=role_id,
        business_id=business_id,
        code="cashier",
        name="Cashier",
        created_at=now,
        updated_at=now,
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Jamie Rivera",
        phone_e164="+15555550123",
        email="jamie@example.com",
        reliability_score=0.925,
        avg_response_time_seconds=120,
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
            role=role,
            proficiency_level=3,
            is_primary=True,
            role_metadata={},
            created_at=now,
            updated_at=now,
        )
    ]
    employee.employee_locations = []

    session.get_map[(Business, business_id)] = business
    session.get_map[(Location, location_id)] = location
    session.execute_queue = [[], [role], [employee], [], []]

    return await workspace_board.get_location_board(
        session,
        business_id=business_id,
        location_id=location_id,
        week_start=date(2026, 4, 6),
    )


async def _build_board_without_location_employee() -> WorkspaceLocationBoardRead:
    session = FakeWorkspaceBoardSession()
    now = datetime(2026, 4, 6, 16, 0, tzinfo=timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    employee_id = uuid4()

    business = Business(
        id=business_id,
        name="Whole Foods Market LLC",
        display_name="Whole Foods Market",
        slug="whole-foods-market",
        timezone="America/Los_Angeles",
        status="active",
        settings={},
        place_metadata={},
        created_at=now,
        updated_at=now,
    )
    location = Location(
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
        created_at=now,
        updated_at=now,
    )
    role = Role(
        id=role_id,
        business_id=business_id,
        code="cashier",
        name="Cashier",
        created_at=now,
        updated_at=now,
    )
    location_role = LocationRole(
        id=uuid4(),
        location_id=location_id,
        role_id=role_id,
        is_active=True,
        min_headcount=1,
        max_headcount=3,
        premium_rules={},
        coverage_settings={},
        created_at=now,
        updated_at=now,
        role=role,
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Jamie Rivera",
        phone_e164="+15555550123",
        email="jamie@example.com",
        reliability_score=0.925,
        avg_response_time_seconds=120,
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
            role=role,
            proficiency_level=3,
            is_primary=True,
            role_metadata={},
            created_at=now,
            updated_at=now,
        )
    ]
    employee.employee_locations = []

    session.get_map[(Business, business_id)] = business
    session.get_map[(Location, location_id)] = location
    session.execute_queue = [[location_role], [role], [employee], [], []]

    return await workspace_board.get_location_board(
        session,
        business_id=business_id,
        location_id=location_id,
        week_start=date(2026, 4, 6),
    )

@pytest.mark.asyncio
async def test_location_board_summarizes_roles_workers_and_actions():
    board = await _build_board()

    assert board.business_name == "Whole Foods Market"
    assert board.location_name == "Downtown Los Angeles"
    assert board.location_role_setup_required is False
    assert board.location_employee_setup_required is False
    assert board.location_setup_required is False
    assert len(board.roles) == 1
    assert board.roles[0].role_name == "Cashier"
    assert len(board.workers) == 1
    assert board.workers[0].full_name == "Jamie Rivera"
    assert board.workers[0].can_cover_here is True
    assert len(board.shifts) == 1
    assert board.shifts[0].current_assignment is not None
    assert board.shifts[0].current_assignment.employee_name == "Jamie Rivera"
    assert board.shifts[0].pending_offer_count == 1
    assert board.shifts[0].delivered_offer_count == 1
    assert board.shifts[0].manager_action_required is True
    assert board.action_summary.approval_required == 1
    assert board.action_summary.active_coverage == 1
    assert board.action_summary.open_shifts == 1


@pytest.mark.asyncio
async def test_location_board_exposes_last_assignment_for_unassigned_shift():
    session = FakeWorkspaceBoardSession()
    now = datetime(2026, 4, 6, 16, 0, tzinfo=timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    employee_id = uuid4()
    shift_id = uuid4()

    business = Business(
        id=business_id,
        name="Whole Foods Market LLC",
        display_name="Whole Foods Market",
        slug="whole-foods-market",
        timezone="America/Los_Angeles",
        status="active",
        settings={},
        place_metadata={},
        created_at=now,
        updated_at=now,
    )
    location = Location(
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
        created_at=now,
        updated_at=now,
    )
    role = Role(
        id=role_id,
        business_id=business_id,
        code="cashier",
        name="Cashier",
        created_at=now,
        updated_at=now,
    )
    location_role = LocationRole(
        id=uuid4(),
        location_id=location_id,
        role_id=role_id,
        role=role,
        is_active=True,
        min_headcount=1,
        max_headcount=3,
        premium_rules={},
        coverage_settings={},
        created_at=now,
        updated_at=now,
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Jamie Rivera",
        phone_e164="+15555550123",
        email="jamie@example.com",
        reliability_score=0.925,
        avg_response_time_seconds=120,
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
            role=role,
            proficiency_level=3,
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
    assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=shift_id,
        employee_id=employee_id,
        employee=employee,
        assigned_via="scheduler_ui",
        status=AssignmentStatus.cancelled,
        sequence_no=1,
        cancelled_at=now,
        assignment_metadata={"employee_name": "Jamie Rivera"},
        created_at=now,
        updated_at=now,
    )
    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        role=role,
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
        requires_manager_approval=False,
        premium_cents=0,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    shift.assignments = [assignment]
    shift.coverage_cases = []

    session.get_map[(Business, business_id)] = business
    session.get_map[(Location, location_id)] = location
    session.execute_queue = [[location_role], [role], [employee], [shift], []]

    board = await workspace_board.get_location_board(
        session,
        business_id=business_id,
        location_id=location_id,
        week_start=date(2026, 4, 6),
    )

    assert board.shifts[0].current_assignment is None
    assert board.shifts[0].last_assignment is not None
    assert board.shifts[0].last_assignment.employee_name == "Jamie Rivera"
    assert board.shifts[0].amended_from_published is True
    assert board.shifts[0].amendment_reason_code == "callout"
    assert board.shifts[0].schedule_break is True
    assert board.shifts[0].historical_display is False


@pytest.mark.asyncio
async def test_location_board_reports_publish_summary_for_live_callout_shift():
    session = FakeWorkspaceBoardSession()
    now = datetime(2026, 4, 6, 16, 0, tzinfo=timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    employee_id = uuid4()
    shift_id = uuid4()

    business = Business(
        id=business_id,
        name="Whole Foods Market LLC",
        display_name="Whole Foods Market",
        slug="whole-foods-market",
        timezone="America/Los_Angeles",
        status="active",
        settings={},
        place_metadata={},
        created_at=now,
        updated_at=now,
    )
    location = Location(
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
        created_at=now,
        updated_at=now,
    )
    role = Role(
        id=role_id,
        business_id=business_id,
        code="cashier",
        name="Cashier",
        created_at=now,
        updated_at=now,
    )
    location_role = LocationRole(
        id=uuid4(),
        location_id=location_id,
        role_id=role_id,
        role=role,
        is_active=True,
        min_headcount=1,
        max_headcount=3,
        premium_rules={},
        coverage_settings={},
        created_at=now,
        updated_at=now,
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Jamie Rivera",
        phone_e164="+15555550123",
        email="jamie@example.com",
        reliability_score=0.925,
        avg_response_time_seconds=120,
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
            role=role,
            proficiency_level=3,
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
    assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=shift_id,
        employee_id=employee_id,
        employee=employee,
        assigned_via="scheduler_ui",
        status=AssignmentStatus.cancelled,
        sequence_no=1,
        cancelled_at=now,
        assignment_metadata={"employee_name": "Jamie Rivera"},
        created_at=now,
        updated_at=now,
    )
    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        role=role,
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
        requires_manager_approval=False,
        premium_cents=0,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    shift.assignments = [assignment]
    shift.coverage_cases = []
    published_event = PlatformEvent(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        schema_version=1,
        event_type="schedule.week.published",
        compatibility_event_name="schedule.week.published",
        entity_type="schedule_week",
        entity_id=None,
        actor_type=AuditActorType.system,
        actor_user_id=None,
        actor_membership_id=None,
        trace_id="trace-1",
        ip_address=None,
        user_agent=None,
        payload={
            "week_start_date": "2026-04-06",
            "week_end_date": "2026-04-12",
        },
        event_metadata={},
        error_message=None,
        occurred_at=now,
        created_at=now,
        updated_at=now,
    )

    session.get_map[(Business, business_id)] = business
    session.get_map[(Location, location_id)] = location
    session.execute_queue = [[location_role], [role], [employee], [shift], [published_event]]

    board = await workspace_board.get_location_board(
        session,
        business_id=business_id,
        location_id=location_id,
        week_start=date(2026, 4, 6),
    )

    assert board.publish_summary.state == "amended"
    assert board.publish_summary.published_at == now
    assert board.publish_summary.amended_shift_ids == [shift_id]
    assert board.publish_summary.amended_employee_ids == [employee_id]


@pytest.mark.asyncio
async def test_location_board_reports_setup_required_when_location_roles_missing():
    board = await _build_board_without_location_roles()

    assert board.location_role_setup_required is True
    assert board.location_employee_setup_required is True
    assert board.location_setup_required is True
    assert board.roles == []
    assert len(board.available_roles) == 1
    assert board.available_roles[0].role_code == "cashier"
    assert board.workers == []


@pytest.mark.asyncio
async def test_location_board_reports_setup_required_when_no_schedulable_location_workers():
    board = await _build_board_without_location_employee()

    assert board.location_role_setup_required is False
    assert board.location_employee_setup_required is True
    assert board.location_setup_required is True
    assert len(board.roles) == 1
    assert len(board.workers) == 1
    assert all(worker.can_cover_here is False for worker in board.workers)


def test_board_window_uses_location_timezone_boundaries():
    window = workspace_board.board_window("America/Los_Angeles", date(2026, 4, 6))

    assert window.week_start == date(2026, 4, 6)
    assert window.week_end == date(2026, 4, 12)
    assert window.starts_at == datetime(2026, 4, 6, 7, 0, tzinfo=timezone.utc)
    assert window.ends_at == datetime(2026, 4, 13, 6, 59, 59, 999999, tzinfo=timezone.utc)
