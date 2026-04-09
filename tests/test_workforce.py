from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app.models.coverage import AuditLog
from app.models.identity import Membership, Session, User
from app.schemas.workforce import (
    EmployeeAvailabilityRuleReplace,
    EmployeeAvailabilityRuleRead,
    EmployeeBulkImportRead,
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


@pytest.mark.asyncio
async def test_replace_self_employee_availability_rules_creates_employee_when_unlinked(monkeypatch):
    business_id = uuid4()
    user_id = uuid4()
    employee_id = uuid4()
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
            primary_location_id=None,
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
        object(),
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
        assert b"full_name" in content
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
                    b"full_name,email\nJamie Rivera,jamie@example.com\n,missing@example.com\n",
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


def test_parse_employee_import_file_skips_rows_missing_required_fields():
    employees, errors = parse_employee_import_file(
        "employees.csv",
        (
            b"full_name,email,phone_e164\n"
            b"Jamie Rivera,jamie@example.com,+15555550123\n"
            b"Missing Email,,+15555550124\n"
            b"Missing Phone,missing.phone@example.com,\n"
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
        b"full_name,email,phone_e164\nJamie Rivera,jamie@example.com,+15555550123\n",
    )

    assert len(employees) == 1
    assert errors == []


def test_build_employee_import_template_raises_clear_error_when_openpyxl_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("openpyxl"):
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="employee_import_xlsx_dependency_missing"):
        build_employee_import_template()


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
