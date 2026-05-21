from __future__ import annotations

from datetime import date, datetime, time, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm.attributes import set_committed_value

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.business import Business, Location, Role
from app.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app.models.coverage import AuditLog
from app.models.identity import Membership, Session, User
from app.models.workforce import Employee, EmployeeAvailabilityRule, EmployeeLocation, EmployeeRole, EmployeeWorkPermit
from app.schemas.workforce import (
    EmployeeAvailabilityRuleReplace,
    EmployeeAvailabilityRuleRead,
    EmployeeBulkImportRead,
    EmployeeDeleteReadinessRead,
    EmployeeEnrollmentRead,
    EmployeeImportErrorRead,
    EmployeeLocationRead,
    EmployeeProfileRead,
    EmployeeRead,
    EmployeeRoleRead,
    EmployeeWorkPermitTemplateRead,
    EmployeeWorkPermitRuleProfile,
    EmployeeWorkPermitRead,
    SelfEmployeeAvailabilityRead,
)
from app.services.auth import AuthContext
from app.services import workforce
from app.services.workforce import build_employee_import_template, parse_employee_import_file


class DummyWorkforceSession:
    def __init__(self):
        self.added: list[object] = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


class DummyEmployeeCreateSession:
    def __init__(self, *, location: Location | None = None):
        self.location = location
        self.added: list[object] = []

    def add(self, obj):
        self.added.append(obj)

    async def get(self, model, object_id):
        if model is Location and self.location is not None and object_id == self.location.id:
            return self.location
        return None

    async def flush(self):
        return None

    async def refresh(self, _obj):
        return None


def _make_auth_context(*, business_id, location_id=None) -> AuthContext:
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
        role=MembershipRole.owner,
        status=MembershipStatus.active,
        accepted_at=now,
        membership_metadata={},
        created_at=now,
        updated_at=now,
    )
    return AuthContext(user=user, session=session, memberships=[membership])


@pytest.mark.asyncio
async def test_create_employee_seeds_all_days_availability(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    business = Business(
        id=business_id,
        name="Casa Vega LLC",
        display_name="Casa Vega",
        slug="casa-vega",
        timezone="America/Los_Angeles",
        settings={},
        place_metadata={},
    )
    location = Location(
        id=location_id,
        business_id=business_id,
        name="Pasadena",
        display_name="Pasadena",
        slug="pasadena",
        timezone="America/Chicago",
        settings={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session = DummyEmployeeCreateSession(location=location)

    async def fake_require_business(_session, incoming_business_id):
        assert incoming_business_id == business_id
        return business

    async def fake_find_duplicate_employee(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.services.workforce._require_business", fake_require_business)
    monkeypatch.setattr("app.services.workforce._find_duplicate_employee", fake_find_duplicate_employee)

    employee = await workforce.create_employee(
        session,
        business_id,
        workforce.EmployeeCreate(
            full_name="Jamie Rivera",
            phone_e164="+15555550123",
            email="jamie@example.com",
            primary_location_id=location_id,
            employee_metadata={"source": "team_ui"},
        ),
    )

    rules = [entry for entry in session.added if isinstance(entry, EmployeeAvailabilityRule)]

    assert employee.primary_location_id == location_id
    assert len(rules) == 7
    assert [rule.day_of_week for rule in rules] == list(range(7))
    assert all(rule.start_local_time == time(0, 0) for rule in rules)
    assert all(rule.end_local_time == time(23, 59) for rule in rules)
    assert all(rule.timezone == "America/Chicago" for rule in rules)
    assert all(rule.availability_type == "available" for rule in rules)
    assert all(rule.availability_metadata["preset"] == "all_days" for rule in rules)


@pytest.mark.asyncio
async def test_create_employee_persists_base_hourly_rate(monkeypatch):
    business_id = uuid4()
    business = Business(
        id=business_id,
        name="Casa Vega LLC",
        display_name="Casa Vega",
        slug="casa-vega",
        timezone="America/Los_Angeles",
        settings={},
        place_metadata={},
    )
    session = DummyEmployeeCreateSession(location=None)

    async def fake_require_business(_session, incoming_business_id):
        assert incoming_business_id == business_id
        return business

    async def fake_find_duplicate_employee(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.services.workforce._require_business", fake_require_business)
    monkeypatch.setattr("app.services.workforce._find_duplicate_employee", fake_find_duplicate_employee)

    employee = await workforce.create_employee(
        session,
        business_id,
        workforce.EmployeeCreate(
            full_name="Jamie Rivera",
            phone_e164="+15555550123",
            email="jamie@example.com",
            base_hourly_rate_cents=2150,
            compliance_regular_rate_cents=2375,
            employee_metadata={"source": "team_ui"},
        ),
    )

    assert employee.base_hourly_rate_cents == 2150
    assert employee.compliance_regular_rate_cents == 2375


@pytest.mark.asyncio
async def test_create_employee_persists_minor_compliance_fields(monkeypatch):
    business_id = uuid4()
    business = Business(
        id=business_id,
        name="Casa Vega LLC",
        display_name="Casa Vega",
        slug="casa-vega",
        timezone="America/Los_Angeles",
        settings={},
        place_metadata={},
    )
    session = DummyEmployeeCreateSession(location=None)

    async def fake_require_business(_session, incoming_business_id):
        assert incoming_business_id == business_id
        return business

    async def fake_find_duplicate_employee(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.services.workforce._require_business", fake_require_business)
    monkeypatch.setattr("app.services.workforce._find_duplicate_employee", fake_find_duplicate_employee)

    employee = await workforce.create_employee(
        session,
        business_id,
        workforce.EmployeeCreate(
            full_name="Jamie Rivera",
            phone_e164="+15555550123",
            email="jamie@example.com",
            date_of_birth=date(2010, 5, 1),
            minor_school_status="in_session",
            work_permits=[
                workforce.EmployeeWorkPermitCreate(
                    permit_number="WP-12345",
                    effective_start_date=date(2026, 1, 1),
                    effective_end_date=date(2026, 8, 31),
                    max_daily_minutes=240,
                    max_weekly_minutes=1200,
                    earliest_start_local_time=time(7, 0),
                    latest_end_local_time=time(19, 0),
                    rule_profile=EmployeeWorkPermitRuleProfile(
                        allowed_weekdays=["monday", "tuesday", "wednesday", "thursday", "friday"],
                        daily_max_minutes_school_day=180,
                        daily_max_minutes_non_school_day=300,
                        latest_end_local_time_school_day=time(18, 0),
                        latest_end_local_time_non_school_day=time(20, 0),
                    ),
                    permit_metadata={"source": "team_ui"},
                )
            ],
            employee_metadata={"source": "team_ui"},
        ),
    )

    assert employee.date_of_birth == date(2010, 5, 1)
    assert employee.minor_school_status == "in_session"
    assert employee.work_permit_number == "WP-12345"
    assert employee.work_permit_effective_start_on == date(2026, 1, 1)
    assert employee.work_permit_expires_on == date(2026, 8, 31)
    assert employee.work_permit_max_daily_minutes == 240
    assert employee.work_permit_max_weekly_minutes == 1200
    assert employee.work_permit_earliest_start_local_time == time(7, 0)
    assert employee.work_permit_latest_end_local_time == time(19, 0)
    assert len(employee.work_permits) == 1
    assert employee.work_permits[0].permit_number == "WP-12345"
    assert employee.work_permits[0].rule_profile is not None
    assert employee.work_permits[0].rule_profile["daily_max_minutes_school_day"] == 180
    assert employee.employee_metadata["work_permit_rule_profile"]["allowed_weekdays"] == [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
    ]


def test_enroll_employee_route_records_audit(monkeypatch):
    fake_session = DummyWorkforceSession()
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    employee_id = uuid4()
    employee_role_id = uuid4()
    now = datetime.now(timezone.utc)

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    async def fake_enroll(_session, incoming_business_id, payload):
        assert incoming_business_id == business_id
        assert payload.location_id == location_id
        assert payload.role_ids == [role_id]
        return EmployeeEnrollmentRead(
            employee=EmployeeRead(
                id=employee_id,
                business_id=business_id,
                primary_location_id=location_id,
                external_ref=None,
                employee_number=None,
                full_name="Jamie Rivera",
                preferred_name="Jamie",
                phone_e164="+15555550123",
                email="jamie@example.com",
                status="active",
                employment_type=None,
                hire_date=None,
                termination_date=None,
                notes=None,
                employee_metadata={},
                created_at=now,
                updated_at=now,
            ),
            roles=[
                EmployeeRoleRead(
                    id=employee_role_id,
                    employee_id=employee_id,
                    role_id=role_id,
                    proficiency_level=1,
                    is_primary=True,
                    acquired_at=None,
                    role_metadata={},
                    created_at=now,
                    updated_at=now,
                )
            ],
        )

    monkeypatch.setattr(
        "app.api.routes.workforce.workforce.enroll_employee_at_location",
        fake_enroll,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/businesses/{business_id}/employees/enroll",
            json={
                "location_id": str(location_id),
                "role_ids": [str(role_id)],
                "full_name": "Jamie Rivera",
                "preferred_name": "Jamie",
                "phone_e164": "+15555550123",
                "email": "jamie@example.com",
            },
        )
        assert response.status_code == 201
        assert response.json()["employee"]["full_name"] == "Jamie Rivera"
        assert any(
            isinstance(entry, AuditLog) and entry.event_name == "employee.enrolled"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()


def test_get_employee_profile_route_returns_profile(monkeypatch):
    fake_session = DummyWorkforceSession()
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    employee_id = uuid4()
    now = datetime.now(timezone.utc)

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    async def fake_get_profile(_session, incoming_business_id, incoming_employee_id):
        assert incoming_business_id == business_id
        assert incoming_employee_id == employee_id
        return EmployeeProfileRead(
            id=employee_id,
            business_id=business_id,
            primary_location_id=location_id,
            primary_location_name="Downtown",
            primary_role_id=role_id,
            primary_role_name="Server",
            external_ref=None,
            employee_number=None,
            full_name="Jamie Rivera",
            preferred_name="Jamie",
            phone_e164="+15555550123",
            email="jamie@example.com",
            status="active",
            employment_type=None,
            hire_date=None,
            termination_date=None,
            notes=None,
            employee_metadata={},
            role_ids=[role_id],
            location_ids=[location_id],
            created_at=now,
            updated_at=now,
            roles=[
                EmployeeRoleRead(
                    id=uuid4(),
                    employee_id=employee_id,
                    role_id=role_id,
                    role_code="server",
                    role_name="Server",
                    proficiency_level=1,
                    is_primary=True,
                    acquired_at=None,
                    role_metadata={},
                    created_at=now,
                    updated_at=now,
                )
            ],
            locations=[
                EmployeeLocationRead(
                    id=uuid4(),
                    employee_id=employee_id,
                    location_id=location_id,
                    location_name="Downtown",
                    location_slug="downtown",
                    is_primary=True,
                    access_level="approved",
                    location_source="seed",
                    can_cover_last_minute=True,
                    can_blast=True,
                    travel_radius_miles=None,
                    location_metadata={},
                    created_at=now,
                    updated_at=now,
                )
            ],
        )

    monkeypatch.setattr(
        "app.api.routes.workforce.workforce.get_employee_profile",
        fake_get_profile,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(f"/api/businesses/{business_id}/employees/{employee_id}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["primary_role_name"] == "Server"
        assert payload["locations"][0]["location_slug"] == "downtown"
    finally:
        app.dependency_overrides.clear()


def test_get_employee_delete_readiness_route_returns_readiness(monkeypatch):
    fake_session = DummyWorkforceSession()
    business_id = uuid4()
    employee_id = uuid4()

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    async def fake_get_readiness(_session, incoming_business_id, incoming_employee_id):
        assert incoming_business_id == business_id
        assert incoming_employee_id == employee_id
        return EmployeeDeleteReadinessRead(
            business_id=business_id,
            employee_id=employee_id,
            can_delete=False,
            reason="This employee has scheduled shifts and cannot be removed until those shifts are cleared.",
        )

    monkeypatch.setattr(
        "app.api.routes.workforce.workforce.get_employee_delete_readiness",
        fake_get_readiness,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/employees/{employee_id}/delete-readiness",
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["can_delete"] is False
        assert "scheduled shifts" in payload["reason"]
    finally:
        app.dependency_overrides.clear()


def test_list_work_permit_templates_route_returns_catalog(monkeypatch):
    fake_session = DummyWorkforceSession()
    business_id = uuid4()

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    def fake_list_templates():
        return [
            EmployeeWorkPermitTemplateRead(
                code="ca_16_17_school_required_v1",
                label="California ages 16-17 while school required",
                description="4 hours on schooldays, 8 hours on non-schooldays.",
                jurisdiction_code="US-CA",
                source_url="https://www.dir.ca.gov/dlse/MinorsSummaryCharts.pdf",
                source_document_title="California Department of Industrial Relations minors summary charts",
                source_version="dir_minors_summary_charts_v1",
                payload_hash="sha256:permit-payload",
                rule_families=["minor_labor", "work_permit"],
                rule_profile=EmployeeWorkPermitRuleProfile(
                    template_code="ca_16_17_school_required_v1",
                    daily_max_minutes_school_day=240,
                    daily_max_minutes_preceding_non_school_day=480,
                    latest_end_local_time_preceding_non_school_day=time(0, 30),
                ),
            )
        ]

    monkeypatch.setattr(
        "app.api.routes.workforce.workforce.list_work_permit_templates",
        fake_list_templates,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/employees/work-permit-templates",
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload[0]["code"] == "ca_16_17_school_required_v1"
        assert payload[0]["source_version"] == "dir_minors_summary_charts_v1"
        assert payload[0]["rule_families"] == ["minor_labor", "work_permit"]
        assert payload[0]["rule_profile"]["daily_max_minutes_school_day"] == 240
        assert payload[0]["rule_profile"]["latest_end_local_time_preceding_non_school_day"] == "00:30:00"
    finally:
        app.dependency_overrides.clear()


def test_get_self_employee_availability_route_returns_rules(monkeypatch):
    fake_session = DummyWorkforceSession()
    business_id = uuid4()
    employee_id = uuid4()
    now = datetime.now(timezone.utc)

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    async def fake_get_self_availability(
        _session,
        incoming_business_id,
        *,
        user_id,
        email,
        phone_e164,
        full_name,
    ):
        assert incoming_business_id == business_id
        assert user_id is not None
        assert email == "owner@example.com"
        assert phone_e164 == "+15555550100"
        assert full_name == "Owner User"
        return (
            EmployeeRead(
                id=employee_id,
                business_id=business_id,
                primary_location_id=None,
                external_ref=None,
                employee_number=None,
                full_name="Owner User",
                preferred_name="Owner",
                phone_e164="+15555550100",
                email="owner@example.com",
                status="active",
                employment_type=None,
                hire_date=None,
                termination_date=None,
                notes=None,
                employee_metadata={},
                created_at=now,
                updated_at=now,
            ),
            [
                EmployeeAvailabilityRuleRead(
                    id=uuid4(),
                    employee_id=employee_id,
                    day_of_week=0,
                    start_local_time="09:00:00",
                    end_local_time="17:00:00",
                    timezone="America/Los_Angeles",
                    availability_type="available",
                    valid_from=None,
                    valid_until=None,
                    priority=0,
                    availability_metadata={},
                    created_at=now,
                    updated_at=now,
                )
            ],
        )

    monkeypatch.setattr(
        "app.api.routes.workforce.workforce.get_self_employee_availability_rules",
        fake_get_self_availability,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/employees/availability-rules/self"
        )
        assert response.status_code == 200
        payload = SelfEmployeeAvailabilityRead.model_validate(response.json())
        assert payload.employee_id == employee_id
        assert payload.employee_name == "Owner"
        assert payload.rules[0].day_of_week == 0
    finally:
        app.dependency_overrides.clear()


def test_replace_self_employee_availability_route_returns_rules(monkeypatch):
    fake_session = DummyWorkforceSession()
    business_id = uuid4()
    employee_id = uuid4()
    now = datetime.now(timezone.utc)

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    async def fake_replace_self_availability(
        _session,
        incoming_business_id,
        *,
        user_id,
        email,
        phone_e164,
        full_name,
        payload,
    ):
        assert incoming_business_id == business_id
        assert user_id is not None
        assert email == "owner@example.com"
        assert phone_e164 == "+15555550100"
        assert full_name == "Owner User"
        assert len(payload.rules) == 2
        return (
            EmployeeRead(
                id=employee_id,
                business_id=business_id,
                primary_location_id=None,
                external_ref=None,
                employee_number=None,
                full_name="Owner User",
                preferred_name=None,
                phone_e164="+15555550100",
                email="owner@example.com",
                status="active",
                employment_type=None,
                hire_date=None,
                termination_date=None,
                notes=None,
                employee_metadata={},
                created_at=now,
                updated_at=now,
            ),
            [
                EmployeeAvailabilityRuleRead(
                    id=uuid4(),
                    employee_id=employee_id,
                    day_of_week=0,
                    start_local_time="09:00:00",
                    end_local_time="17:00:00",
                    timezone="America/Los_Angeles",
                    availability_type="available",
                    valid_from=None,
                    valid_until=None,
                    priority=0,
                    availability_metadata={},
                    created_at=now,
                    updated_at=now,
                ),
                EmployeeAvailabilityRuleRead(
                    id=uuid4(),
                    employee_id=employee_id,
                    day_of_week=1,
                    start_local_time="09:00:00",
                    end_local_time="17:00:00",
                    timezone="America/Los_Angeles",
                    availability_type="available",
                    valid_from=None,
                    valid_until=None,
                    priority=0,
                    availability_metadata={},
                    created_at=now,
                    updated_at=now,
                ),
            ],
        )

    monkeypatch.setattr(
        "app.api.routes.workforce.workforce.replace_self_employee_availability_rules",
        fake_replace_self_availability,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.put(
            f"/api/businesses/{business_id}/employees/availability-rules/self",
            json={
                "rules": [
                    {
                        "day_of_week": 0,
                        "start_local_time": "09:00:00",
                        "end_local_time": "17:00:00",
                        "timezone": "America/Los_Angeles",
                    },
                    {
                        "day_of_week": 1,
                        "start_local_time": "09:00:00",
                        "end_local_time": "17:00:00",
                        "timezone": "America/Los_Angeles",
                    },
                ]
            },
        )
        assert response.status_code == 200
        payload = SelfEmployeeAvailabilityRead.model_validate(response.json())
        assert payload.employee_name == "Owner User"
        assert len(payload.rules) == 2
        assert fake_session.commits == 1
    finally:
        app.dependency_overrides.clear()


def test_employee_profile_read_includes_role_and_location_assignments():
    business_id = uuid4()
    employee_id = uuid4()
    role_id = uuid4()
    location_id = uuid4()
    now = datetime.now(timezone.utc)

    business = Business(
        id=business_id,
        name="Backfill",
        display_name="Backfill",
        slug="backfill",
        timezone="America/Los_Angeles",
        created_at=now,
        updated_at=now,
    )
    role = Role(
        id=role_id,
        business_id=business_id,
        code="server",
        name="Server",
        created_at=now,
        updated_at=now,
    )
    location = Location(
        id=location_id,
        business_id=business_id,
        name="Pasadena",
        display_name="Pasadena",
        slug="pasadena",
        timezone="America/Los_Angeles",
        country_code="US",
        created_at=now,
        updated_at=now,
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Jamie Rivera",
        preferred_name="Jamie",
        phone_e164="+15555550123",
        email="jamie@example.com",
        status="active",
        employee_metadata={},
        created_at=now,
        updated_at=now,
    )
    employee_role = EmployeeRole(
        id=uuid4(),
        employee_id=employee_id,
        role_id=role_id,
        proficiency_level=1,
        is_primary=True,
        role_metadata={},
        created_at=now,
        updated_at=now,
    )
    employee_location = EmployeeLocation(
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

    set_committed_value(role, "business", business)
    set_committed_value(location, "business", business)
    set_committed_value(employee_role, "role", role)
    set_committed_value(employee_location, "location", location)
    set_committed_value(employee, "employee_roles", [employee_role])
    set_committed_value(employee, "employee_locations", [employee_location])

    payload = EmployeeProfileRead.model_validate(employee)

    assert payload.role_ids == [role_id]
    assert payload.location_ids == [location_id]
    assert payload.roles[0].role_id == role_id
    assert payload.roles[0].role_name == "Server"
    assert payload.locations[0].location_id == location_id
    assert payload.locations[0].location_name == "Pasadena"


@pytest.mark.asyncio
async def test_get_employee_profile_hydrates_role_and_location_assignments(monkeypatch):
    business_id = uuid4()
    employee_id = uuid4()
    role_id = uuid4()
    location_id = uuid4()
    now = datetime.now(timezone.utc)

    role = Role(
        id=role_id,
        business_id=business_id,
        code="server",
        name="Server",
        created_at=now,
        updated_at=now,
    )
    location = Location(
        id=location_id,
        business_id=business_id,
        name="Pasadena",
        display_name="Pasadena",
        slug="pasadena",
        timezone="America/Los_Angeles",
        country_code="US",
        created_at=now,
        updated_at=now,
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Jamie Rivera",
        preferred_name="Jamie",
        phone_e164="+15555550123",
        email="jamie@example.com",
        status="active",
        employee_metadata={},
        created_at=now,
        updated_at=now,
    )
    employee_role = EmployeeRole(
        id=uuid4(),
        employee_id=employee_id,
        role_id=role_id,
        proficiency_level=1,
        is_primary=True,
        role_metadata={},
        created_at=now,
        updated_at=now,
    )
    employee_location = EmployeeLocation(
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
    set_committed_value(employee_role, "role", role)
    set_committed_value(employee_location, "location", location)

    async def fake_require_employee(_session, incoming_business_id, incoming_employee_id):
        assert incoming_business_id == business_id
        assert incoming_employee_id == employee_id
        return employee

    async def fake_list_roles(_session, incoming_employee_id):
        assert incoming_employee_id == employee_id
        return [employee_role]

    async def fake_list_locations(_session, incoming_employee_id):
        assert incoming_employee_id == employee_id
        return [employee_location]

    monkeypatch.setattr("app.services.workforce._require_employee", fake_require_employee)
    monkeypatch.setattr("app.services.workforce._list_employee_roles", fake_list_roles)
    monkeypatch.setattr("app.services.workforce._list_employee_locations", fake_list_locations)

    profile = await workforce.get_employee_profile(object(), business_id, employee_id)

    assert profile.role_ids == [role_id]
    assert profile.location_ids == [location_id]
    payload = EmployeeProfileRead.model_validate(profile)
    assert payload.roles[0].role_name == "Server"
    assert payload.locations[0].location_name == "Pasadena"


@pytest.mark.asyncio
async def test_update_employee_hydrates_role_and_location_assignments(monkeypatch):
    business_id = uuid4()
    employee_id = uuid4()
    role_id = uuid4()
    location_id = uuid4()
    now = datetime.now(timezone.utc)

    role = Role(
        id=role_id,
        business_id=business_id,
        code="server",
        name="Server",
        created_at=now,
        updated_at=now,
    )
    location = Location(
        id=location_id,
        business_id=business_id,
        name="Pasadena",
        display_name="Pasadena",
        slug="pasadena",
        timezone="America/Los_Angeles",
        country_code="US",
        created_at=now,
        updated_at=now,
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Jamie Rivera",
        preferred_name="Jamie",
        phone_e164="+15555550123",
        email="jamie@example.com",
        base_hourly_rate_cents=1800,
        compliance_regular_rate_cents=2100,
        status="active",
        employee_metadata={},
        created_at=now,
        updated_at=now,
    )
    employee_role = EmployeeRole(
        id=uuid4(),
        employee_id=employee_id,
        role_id=role_id,
        proficiency_level=1,
        is_primary=True,
        role_metadata={},
        created_at=now,
        updated_at=now,
    )
    employee_location = EmployeeLocation(
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
    set_committed_value(employee_role, "role", role)
    set_committed_value(employee_location, "location", location)

    async def fake_require_employee(_session, incoming_business_id, incoming_employee_id):
        assert incoming_business_id == business_id
        assert incoming_employee_id == employee_id
        return employee

    async def fake_get_employee(_session, incoming_business_id, incoming_employee_id):
        assert incoming_business_id == business_id
        assert incoming_employee_id == employee_id
        return employee

    async def fake_list_roles(_session, incoming_employee_id):
        assert incoming_employee_id == employee_id
        return [employee_role]

    async def fake_list_locations(_session, incoming_employee_id):
        assert incoming_employee_id == employee_id
        return [employee_location]

    async def fake_replace_roles(_session, incoming_employee, incoming_business_id, assignments):
        assert incoming_employee is employee
        assert incoming_business_id == business_id
        assert assignments[0].role_id == role_id

    async def fake_replace_locations(_session, incoming_employee, incoming_business_id, assignments):
        assert incoming_employee is employee
        assert incoming_business_id == business_id
        assert assignments[0].location_id == location_id

    monkeypatch.setattr("app.services.workforce._require_employee", fake_require_employee)
    monkeypatch.setattr("app.services.workforce.get_employee", fake_get_employee)
    monkeypatch.setattr("app.services.workforce._list_employee_roles", fake_list_roles)
    monkeypatch.setattr("app.services.workforce._list_employee_locations", fake_list_locations)
    monkeypatch.setattr("app.services.workforce._replace_employee_roles", fake_replace_roles)
    monkeypatch.setattr("app.services.workforce._replace_employee_locations", fake_replace_locations)

    class DummyUpdateSession:
        async def flush(self):
            return None

    updated = await workforce.update_employee(
        DummyUpdateSession(),
        business_id,
        employee_id,
        workforce.EmployeeUpdate(
            base_hourly_rate_cents=2250,
            compliance_regular_rate_cents=2550,
            notification_preferences=workforce.EmployeeNotificationPreferencesUpdate(
                schedule_publish_sms_enabled=True,
                sms_opt_out_reason="manager_enabled_after_consent",
            ),
            roles=[workforce.EmployeeRoleUpsert(role_id=role_id, is_primary=True)],
            locations=[workforce.EmployeeLocationUpsert(location_id=location_id, is_primary=True)],
        ),
    )

    assert updated.role_ids == [role_id]
    assert updated.location_ids == [location_id]
    assert updated.base_hourly_rate_cents == 2250
    assert updated.compliance_regular_rate_cents == 2550
    payload = EmployeeProfileRead.model_validate(updated)
    assert payload.roles[0].role_name == "Server"
    assert payload.locations[0].location_name == "Pasadena"
    assert payload.notification_preferences.schedule_publish_email_enabled is True
    assert payload.notification_preferences.schedule_publish_sms_enabled is True
    assert payload.notification_preferences.sms_opt_out_reason == "manager_enabled_after_consent"


@pytest.mark.asyncio
async def test_update_employee_persists_minor_compliance_fields(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    employee_id = uuid4()
    now = datetime.now(timezone.utc)

    location = Location(
        id=location_id,
        business_id=business_id,
        name="Pasadena",
        display_name="Pasadena",
        slug="pasadena",
        timezone="America/Los_Angeles",
        country_code="US",
        created_at=now,
        updated_at=now,
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Jamie Rivera",
        preferred_name="Jamie",
        phone_e164="+15555550123",
        email="jamie@example.com",
        status="active",
        employee_metadata={},
        created_at=now,
        updated_at=now,
    )
    existing_work_permit = EmployeeWorkPermit(
        id=uuid4(),
        employee_id=employee_id,
        permit_number="WP-OLD",
        effective_start_date=date(2025, 1, 1),
        effective_end_date=date(2025, 12, 31),
        permit_metadata={},
        created_at=now,
        updated_at=now,
    )
    employee_location = EmployeeLocation(
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
    set_committed_value(employee_location, "location", location)

    async def fake_require_employee(_session, incoming_business_id, incoming_employee_id):
        assert incoming_business_id == business_id
        assert incoming_employee_id == employee_id
        return employee

    async def fake_get_employee(_session, incoming_business_id, incoming_employee_id):
        assert incoming_business_id == business_id
        assert incoming_employee_id == employee_id
        return employee

    async def fake_list_roles(_session, incoming_employee_id):
        assert incoming_employee_id == employee_id
        return []

    async def fake_list_locations(_session, incoming_employee_id):
        assert incoming_employee_id == employee_id
        return [employee_location]

    class DummyUpdateSession:
        def __init__(self):
            self.added: list[object] = []
            self.deleted: list[object] = []

        def add(self, obj):
            self.added.append(obj)

        async def delete(self, obj):
            self.deleted.append(obj)

        async def flush(self):
            return None

    session = DummyUpdateSession()

    async def fake_list_work_permits(_session, incoming_employee_id):
        assert incoming_employee_id == employee_id
        replacement_permits = [
            obj for obj in session.added if isinstance(obj, EmployeeWorkPermit)
        ]
        return replacement_permits or [existing_work_permit]

    monkeypatch.setattr("app.services.workforce._require_employee", fake_require_employee)
    monkeypatch.setattr("app.services.workforce.get_employee", fake_get_employee)
    monkeypatch.setattr("app.services.workforce._list_employee_roles", fake_list_roles)
    monkeypatch.setattr("app.services.workforce._list_employee_locations", fake_list_locations)
    monkeypatch.setattr("app.services.workforce._list_employee_work_permits", fake_list_work_permits)

    updated = await workforce.update_employee(
        session,
        business_id,
        employee_id,
        workforce.EmployeeUpdate(
            date_of_birth=date(2010, 5, 1),
            minor_school_status="summer_break",
                work_permits=[
                    workforce.EmployeeWorkPermitCreate(
                        permit_number="WP-12345",
                        effective_start_date=date(2026, 1, 1),
                        effective_end_date=date(2026, 8, 31),
                        max_daily_minutes=240,
                        max_weekly_minutes=1200,
                        earliest_start_local_time=time(7, 0),
                        latest_end_local_time=time(19, 0),
                        rule_profile=EmployeeWorkPermitRuleProfile(
                            allowed_weekdays=["monday", "tuesday", "wednesday", "thursday", "friday"],
                            daily_max_minutes_school_day=180,
                            daily_max_minutes_non_school_day=300,
                        ),
                        permit_metadata={"source": "team_ui"},
                    )
                ],
        ),
    )

    assert updated.date_of_birth == date(2010, 5, 1)
    assert updated.minor_school_status == "summer_break"
    assert updated.work_permit_number == "WP-12345"
    assert updated.work_permit_effective_start_on == date(2026, 1, 1)
    assert updated.work_permit_expires_on == date(2026, 8, 31)
    assert updated.work_permit_max_daily_minutes == 240
    assert updated.work_permit_max_weekly_minutes == 1200
    assert updated.work_permit_earliest_start_local_time == time(7, 0)
    assert updated.work_permit_latest_end_local_time == time(19, 0)
    assert any(isinstance(obj, EmployeeWorkPermit) and obj.permit_number == "WP-12345" for obj in session.added)
    assert session.deleted == [existing_work_permit]
    payload = EmployeeProfileRead.model_validate(updated)
    assert payload.work_permits[0].permit_number == "WP-12345"
    assert payload.work_permits[0].max_daily_minutes == 240
    assert payload.work_permits[0].rule_profile is not None
    assert payload.work_permits[0].rule_profile.daily_max_minutes_school_day == 180
    assert updated.employee_metadata["work_permit_rule_profile"]["daily_max_minutes_non_school_day"] == 300


def test_resolve_employee_work_permit_context_prefers_active_permit_for_shift_date():
    employee = Employee(
        id=uuid4(),
        business_id=uuid4(),
        full_name="Jamie Rivera",
        status="active",
        employee_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    current_permit = EmployeeWorkPermit(
        id=uuid4(),
        employee_id=employee.id,
        permit_number="WP-CURRENT",
        effective_start_date=date(2026, 4, 1),
        effective_end_date=date(2026, 4, 30),
        max_daily_minutes=180,
        latest_end_local_time=time(19, 0),
        permit_metadata={
            "rule_profile": {
                "allowed_weekdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                "daily_max_minutes_school_day": 180,
            }
        },
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    future_permit = EmployeeWorkPermit(
        id=uuid4(),
        employee_id=employee.id,
        permit_number="WP-FUTURE",
        effective_start_date=date(2026, 5, 1),
        effective_end_date=date(2026, 8, 31),
        max_daily_minutes=300,
        latest_end_local_time=time(21, 0),
        permit_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    set_committed_value(employee, "work_permits", [current_permit, future_permit])

    context = workforce.resolve_employee_work_permit_context(
        employee,
        shift_starts_at=datetime(2026, 4, 18, 18, 0, tzinfo=timezone.utc),
        timezone_name="America/Los_Angeles",
    )

    assert context["permit_number"] == "WP-CURRENT"
    assert context["is_active"] is True
    assert context["max_daily_minutes"] == 180
    assert context["latest_end_local_time"] == time(19, 0)
    assert context["rule_profile"] == {
        "allowed_weekdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "daily_max_minutes_school_day": 180,
    }


def test_resolve_employee_work_permit_context_uses_snapshot_rule_profile_when_permits_unloaded():
    employee = Employee(
        id=uuid4(),
        business_id=uuid4(),
        full_name="Jamie Rivera",
        status="active",
        work_permit_number="WP-SNAPSHOT",
        work_permit_effective_start_on=date(2026, 4, 1),
        work_permit_expires_on=date(2026, 8, 31),
        work_permit_max_daily_minutes=240,
        employee_metadata={
            "work_permit_rule_profile": {
                "allowed_weekdays": ["monday", "wednesday"],
                "daily_max_minutes_school_day": 180,
            }
        },
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    context = workforce.resolve_employee_work_permit_context(
        employee,
        shift_starts_at=datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc),
        timezone_name="America/Los_Angeles",
    )

    assert context["source"] == "employee_snapshot"
    assert context["rule_profile"] == {
        "allowed_weekdays": ["monday", "wednesday"],
        "daily_max_minutes_school_day": 180,
    }


def test_resolve_employee_work_permit_context_expands_template_rule_profile():
    employee = Employee(
        id=uuid4(),
        business_id=uuid4(),
        full_name="Jamie Rivera",
        status="active",
        employee_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    permit = EmployeeWorkPermit(
        id=uuid4(),
        employee_id=employee.id,
        permit_number="WP-TEMPLATE",
        effective_start_date=date(2026, 4, 1),
        effective_end_date=date(2026, 8, 31),
        permit_metadata={
            "rule_profile": {
                "template_code": "ca_16_17_school_required_v1",
            }
        },
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    set_committed_value(employee, "work_permits", [permit])

    context = workforce.resolve_employee_work_permit_context(
        employee,
        shift_starts_at=datetime(2026, 4, 17, 18, 0, tzinfo=timezone.utc),
        timezone_name="America/Los_Angeles",
    )

    assert context["rule_profile"] is not None
    assert context["rule_profile"]["template_code"] == "ca_16_17_school_required_v1"
    assert context["rule_profile"]["daily_max_minutes_school_day"] == 240
    assert context["rule_profile"]["daily_max_minutes_preceding_non_school_day"] == 480
    assert context["rule_profile"]["latest_end_local_time_preceding_non_school_day"] == "00:30:00"


def test_resolve_employee_work_permit_context_prefers_explicit_rule_profile_over_template_defaults():
    employee = Employee(
        id=uuid4(),
        business_id=uuid4(),
        full_name="Jamie Rivera",
        status="active",
        employee_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    permit = EmployeeWorkPermit(
        id=uuid4(),
        employee_id=employee.id,
        permit_number="WP-TEMPLATE-OVERRIDE",
        effective_start_date=date(2026, 4, 1),
        effective_end_date=date(2026, 8, 31),
        permit_metadata={
            "rule_profile": {
                "template_code": "ca_14_15_school_enrolled_v1",
                "daily_max_minutes_school_day": 150,
            }
        },
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    set_committed_value(employee, "work_permits", [permit])

    context = workforce.resolve_employee_work_permit_context(
        employee,
        shift_starts_at=datetime(2026, 4, 16, 18, 0, tzinfo=timezone.utc),
        timezone_name="America/Los_Angeles",
    )

    assert context["rule_profile"] is not None
    assert context["rule_profile"]["template_code"] == "ca_14_15_school_enrolled_v1"
    assert context["rule_profile"]["daily_max_minutes_school_day"] == 150
    assert context["rule_profile"]["latest_end_local_time_summer_break"] == "21:00:00"


@pytest.mark.asyncio
async def test_replace_self_employee_availability_rules_creates_employee_when_unlinked(monkeypatch):
    business_id = uuid4()
    user_id = uuid4()
    employee_id = uuid4()
    location_id = uuid4()
    captured: dict[str, object] = {}

    async def fake_find_self_employee(
        _session,
        incoming_business_id,
        *,
        user_id: object,
        email: object,
        phone_e164: object,
        full_name: object,
    ):
        assert incoming_business_id == business_id
        assert user_id is not None
        assert email == "owner@example.com"
        assert phone_e164 == "+15555550100"
        assert full_name == "Owner User"
        return None

    async def fake_create_employee(
        _session,
        incoming_business_id,
        payload,
        *,
        linked_user_id=None,
    ):
        assert incoming_business_id == business_id
        captured["payload"] = payload
        captured["linked_user_id"] = linked_user_id
        return EmployeeRead(
            id=employee_id,
            business_id=business_id,
            primary_location_id=payload.primary_location_id,
            external_ref=None,
            employee_number=None,
            full_name=payload.full_name,
            preferred_name=None,
            phone_e164=payload.phone_e164,
            email=payload.email,
            status="active",
            employment_type=None,
            hire_date=None,
            termination_date=None,
            notes=None,
            employee_metadata=payload.employee_metadata,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    class DummyLocationScalarResult:
        def __init__(self, values):
            self._values = values

        def all(self):
            return list(self._values)

    class DummySession:
        async def execute(self, _statement):
            return type(
                "Result",
                (),
                {"scalars": lambda self: DummyLocationScalarResult([location_id])},
            )()

    async def fake_replace_rules(_session, incoming_business_id, incoming_employee_id, payload):
        assert incoming_business_id == business_id
        assert incoming_employee_id == employee_id
        return []

    monkeypatch.setattr(
        "app.services.workforce._find_self_service_employee",
        fake_find_self_employee,
    )
    monkeypatch.setattr(
        "app.services.workforce.create_employee",
        fake_create_employee,
    )
    monkeypatch.setattr(
        "app.services.workforce.replace_employee_availability_rules",
        fake_replace_rules,
    )

    employee, rules = await workforce.replace_self_employee_availability_rules(
        DummySession(),
        business_id,
        user_id=user_id,
        email="owner@example.com",
        phone_e164="+15555550100",
        full_name="Owner User",
        payload=EmployeeAvailabilityRuleReplace(rules=[]),
    )

    assert employee.id == employee_id
    assert rules == []
    payload = captured["payload"]
    assert payload.full_name == "Owner User"
    assert payload.email == "owner@example.com"
    assert payload.phone_e164 == "+15555550100"
    assert payload.primary_location_id == location_id
    assert payload.employee_metadata["source"] == "self_service_availability"
    assert payload.employee_metadata["auto_created_from_user"] is True
    assert captured["linked_user_id"] == user_id


def test_create_employee_route_records_audit(monkeypatch):
    fake_session = DummyWorkforceSession()
    business_id = uuid4()
    location_id = uuid4()
    employee_id = uuid4()
    now = datetime.now(timezone.utc)

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    async def fake_create(_session, incoming_business_id, payload):
        assert incoming_business_id == business_id
        assert payload.full_name == "Jamie Rivera"
        assert payload.primary_location_id == location_id
        return EmployeeRead(
            id=employee_id,
            business_id=business_id,
            primary_location_id=location_id,
            primary_location_name="Downtown",
            primary_role_id=None,
            primary_role_name=None,
            external_ref=None,
            employee_number="EMP-100",
            full_name="Jamie Rivera",
            preferred_name="Jamie",
            phone_e164="+15555550123",
            email="jamie@example.com",
            status="active",
            employment_type="part_time",
            hire_date=None,
            termination_date=None,
            notes="Weekend closer",
            employee_metadata={"source": "team_ui"},
            role_ids=[],
            role_names=[],
            location_ids=[location_id],
            location_names=["Downtown"],
            created_at=now,
            updated_at=now,
        )

    monkeypatch.setattr(
        "app.api.routes.workforce.workforce.create_employee",
        fake_create,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/businesses/{business_id}/employees",
            json={
                "full_name": "Jamie Rivera",
                "preferred_name": "Jamie",
                "phone_e164": "+15555550123",
                "email": "jamie@example.com",
                "employee_number": "EMP-100",
                "employment_type": "part_time",
                "primary_location_id": str(location_id),
                "notes": "Weekend closer",
                "employee_metadata": {"source": "team_ui"},
            },
        )
        assert response.status_code == 201
        assert response.json()["employee_number"] == "EMP-100"
        assert any(
            isinstance(entry, AuditLog) and entry.event_name == "employee.created"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()


def test_create_employee_route_returns_conflict_for_duplicate_identity(monkeypatch):
    fake_session = DummyWorkforceSession()
    business_id = uuid4()
    location_id = uuid4()

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    async def fake_create(_session, _incoming_business_id, _payload):
        raise ValueError("employee_duplicate_phone_e164")

    monkeypatch.setattr(
        "app.api.routes.workforce.workforce.create_employee",
        fake_create,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/businesses/{business_id}/employees",
            json={
                "full_name": "Jamie Rivera",
                "phone_e164": "+15555550123",
                "email": "jamie@example.com",
                "primary_location_id": str(location_id),
            },
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "employee_duplicate_phone_e164"
    finally:
        app.dependency_overrides.clear()


def test_bulk_import_route_records_audit(monkeypatch):
    fake_session = DummyWorkforceSession()
    business_id = uuid4()
    location_id = uuid4()
    employee_id = uuid4()
    now = datetime.now(timezone.utc)

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    async def fake_bulk_import(_session, incoming_business_id, *, filename, content):
        assert incoming_business_id == business_id
        assert filename == "employees.csv"
        assert b"first_name" in content
        return EmployeeBulkImportRead(
            created_count=1,
            skipped_count=1,
            employees=[
                EmployeeRead(
                    id=employee_id,
                    business_id=business_id,
                    primary_location_id=location_id,
                    primary_location_name="Downtown",
                    primary_role_id=None,
                    primary_role_name=None,
                    external_ref=None,
                    employee_number=None,
                    full_name="Jamie Rivera",
                    preferred_name="Jamie",
                    phone_e164="+15555550123",
                    email="jamie@example.com",
                    status="active",
                    employment_type=None,
                    hire_date=None,
                    termination_date=None,
                    notes=None,
                    employee_metadata={"source": "bulk_import"},
                    role_ids=[],
                    role_names=[],
                    location_ids=[location_id],
                    location_names=["Downtown"],
                    created_at=now,
                    updated_at=now,
                )
            ],
            errors=[
                EmployeeImportErrorRead(
                    row_number=3,
                    message="missing_required_fields:full_name",
                )
            ],
            default_location_id=location_id,
            default_location_name="Downtown",
        )

    monkeypatch.setattr(
        "app.api.routes.workforce.workforce.bulk_import_employees",
        fake_bulk_import,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/businesses/{business_id}/employees/import",
            files={
                "file": (
                    "employees.csv",
                    b"first_name,last_name,email_address,phone_number\nJamie,Rivera,jamie@example.com,+15555550123\n,,missing@example.com,+15555550124\n",
                    "text/csv",
                )
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["created_count"] == 1
        assert payload["errors"][0]["row_number"] == 3
        assert any(
            isinstance(entry, AuditLog) and entry.event_name == "employee.bulk_imported"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_bulk_import_employees_skips_duplicate_phone_rows(monkeypatch):
    business_id = uuid4()
    first_employee_id = uuid4()
    now = datetime.now(timezone.utc)
    created_payloads: list[object] = []

    class DummyImportSession:
        async def execute(self, _stmt):
            class _ScalarResult:
                def __init__(self):
                    self._values: list[object] = []

                def all(self):
                    return self._values

            class _Result:
                def scalars(self):
                    return _ScalarResult()

            return _Result()

    async def fake_require_business(_session, incoming_business_id):
        assert incoming_business_id == business_id
        return object()

    async def fake_create_employee(_session, incoming_business_id, payload, *, linked_user_id=None):
        assert incoming_business_id == business_id
        assert linked_user_id is None
        created_payloads.append(payload)
        if len(created_payloads) == 1:
                return Employee(
                    id=first_employee_id,
                    business_id=business_id,
                    full_name=payload.full_name,
                    phone_e164=payload.phone_e164,
                    email=payload.email,
                    status="active",
                    employee_metadata=payload.employee_metadata,
                    created_at=now,
                    updated_at=now,
                )
        raise ValueError("employee_duplicate_phone_e164")

    monkeypatch.setattr("app.services.workforce._require_business", fake_require_business)
    monkeypatch.setattr("app.services.workforce.create_employee", fake_create_employee)

    result = await workforce.bulk_import_employees(
        DummyImportSession(),
        business_id,
        filename="employees.csv",
        content=(
            b"first_name,last_name,email_address,phone_number\n"
            b"Jamie,Rivera,jamie@example.com,+15555550123\n"
            b"Jamie,Rivera,jamie.duplicate@example.com,+15555550123\n"
        ),
    )

    assert result.created_count == 1
    assert result.skipped_count == 1
    assert len(result.employees) == 1
    assert result.errors == [
        EmployeeImportErrorRead(
            row_number=3,
            message="employee_duplicate_phone_e164",
        )
    ]


def test_parse_employee_import_file_skips_rows_missing_required_fields():
    employees, errors = parse_employee_import_file(
        "employees.csv",
        (
            b"first_name,last_name,email_address,phone_number\n"
            b"Jamie,Rivera,jamie@example.com,+15555550123\n"
            b"Missing,Email,,+15555550124\n"
            b"Missing,Phone,missing.phone@example.com,\n"
        ),
    )

    assert len(employees) == 1
    assert employees[0].full_name == "Jamie Rivera"
    assert errors == [
        EmployeeImportErrorRead(
            row_number=3,
            message="missing_required_fields:email",
        ),
        EmployeeImportErrorRead(
            row_number=4,
            message="missing_required_fields:phone_e164",
        ),
    ]


def test_parse_employee_import_file_parses_hourly_pay_rate_to_cents():
    employees, errors = parse_employee_import_file(
        "employees.csv",
        (
            b"first_name,last_name,email_address,phone_number,pay_rate\n"
            b"Jamie,Rivera,jamie@example.com,+15555550123,18.75\n"
        ),
    )

    assert errors == []
    assert len(employees) == 1
    assert employees[0].base_hourly_rate_cents == 1875


def test_parse_employee_import_file_parses_compliance_regular_rate_to_cents():
    employees, errors = parse_employee_import_file(
        "employees.csv",
        (
            b"first_name,last_name,email_address,phone_number,regular_rate\n"
            b"Jamie,Rivera,jamie@example.com,+15555550123,21.40\n"
        ),
    )

    assert errors == []
    assert len(employees) == 1
    assert employees[0].compliance_regular_rate_cents == 2140


def test_parse_employee_import_file_parses_minor_compliance_fields():
    employees, errors = parse_employee_import_file(
        "employees.csv",
        (
            b"first_name,last_name,email_address,phone_number,date_of_birth,minor_school_status,work_permit_number,work_permit_expires_on\n"
            b"Jamie,Rivera,jamie@example.com,+15555550123,2010-05-01,in_session,WP-12345,2026-08-31\n"
        ),
    )

    assert errors == []
    assert len(employees) == 1
    assert employees[0].date_of_birth == date(2010, 5, 1)
    assert employees[0].minor_school_status == "in_session"
    assert employees[0].work_permit_number == "WP-12345"
    assert employees[0].work_permit_expires_on == date(2026, 8, 31)


def test_parse_employee_import_file_csv_does_not_require_openpyxl(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("openpyxl"):
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    employees, errors = parse_employee_import_file(
        "employees.csv",
        b"first_name,last_name,email_address,phone_number\nJamie,Rivera,jamie@example.com,+15555550123\n",
    )

    assert len(employees) == 1
    assert errors == []


def test_build_employee_import_template_returns_simple_csv_without_openpyxl(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("openpyxl"):
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    content = build_employee_import_template()

    assert content.startswith(
        b"first_name,last_name,phone_number,email_address,date_of_birth,minor_school_status,work_permit_number,work_permit_expires_on"
    )
    assert b"Taylor,Smith,+15555550123,taylor@example.com,1998-04-12,unknown,," in content


def test_patch_employee_route_records_audit(monkeypatch):
    fake_session = DummyWorkforceSession()
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    employee_id = uuid4()
    now = datetime.now(timezone.utc)

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, location_id=location_id)

    async def fake_update(_session, incoming_business_id, incoming_employee_id, payload):
        assert incoming_business_id == business_id
        assert incoming_employee_id == employee_id
        assert payload.roles[0].role_id == role_id
        return EmployeeProfileRead(
            id=employee_id,
            business_id=business_id,
            primary_location_id=location_id,
            primary_location_name="Downtown",
            primary_role_id=role_id,
            primary_role_name="Server",
            external_ref=None,
            employee_number=None,
            full_name="Jamie Rivera",
            preferred_name="Jamie",
            phone_e164="+15555550123",
            email="jamie@example.com",
            status="active",
            employment_type="part_time",
            hire_date=None,
            termination_date=None,
            notes="Weekend closer",
            employee_metadata={},
            role_ids=[role_id],
            location_ids=[location_id],
            created_at=now,
            updated_at=now,
            roles=[
                EmployeeRoleRead(
                    id=uuid4(),
                    employee_id=employee_id,
                    role_id=role_id,
                    role_code="server",
                    role_name="Server",
                    proficiency_level=1,
                    is_primary=True,
                    acquired_at=None,
                    role_metadata={},
                    created_at=now,
                    updated_at=now,
                )
            ],
            locations=[
                EmployeeLocationRead(
                    id=uuid4(),
                    employee_id=employee_id,
                    location_id=location_id,
                    location_name="Downtown",
                    location_slug="downtown",
                    is_primary=True,
                    access_level="approved",
                    location_source="seed",
                    can_cover_last_minute=True,
                    can_blast=True,
                    travel_radius_miles=None,
                    location_metadata={},
                    created_at=now,
                    updated_at=now,
                )
            ],
        )

    monkeypatch.setattr(
        "app.api.routes.workforce.workforce.update_employee",
        fake_update,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.patch(
            f"/api/businesses/{business_id}/employees/{employee_id}",
            json={
                "full_name": "Jamie Rivera",
                "roles": [{"role_id": str(role_id), "is_primary": True}],
                "locations": [{"location_id": str(location_id), "is_primary": True}],
            },
        )
        assert response.status_code == 200
        assert response.json()["primary_location_name"] == "Downtown"
        assert any(
            isinstance(entry, AuditLog) and entry.event_name == "employee.updated"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()
