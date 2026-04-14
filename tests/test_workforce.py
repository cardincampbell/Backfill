from __future__ import annotations

from datetime import datetime, timezone
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
from app.models.workforce import Employee, EmployeeLocation, EmployeeRole
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
    payload = EmployeeProfileRead.model_validate(updated)
    assert payload.roles[0].role_name == "Server"
    assert payload.locations[0].location_name == "Pasadena"
    assert payload.notification_preferences.schedule_publish_email_enabled is True
    assert payload.notification_preferences.schedule_publish_sms_enabled is True
    assert payload.notification_preferences.sms_opt_out_reason == "manager_enabled_after_consent"


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

    assert content.startswith(b"first_name,last_name,phone_number,email_address")
    assert b"Taylor,Smith,+15555550123,taylor@example.com" in content


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
