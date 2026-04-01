from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app_v2.api.deps import get_auth_context, get_db_session
from app_v2.main import app
from app_v2.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app_v2.models.coverage import AuditLog
from app_v2.models.identity import Membership, Session, User
from app_v2.schemas.workforce import EmployeeEnrollmentRead, EmployeeRead, EmployeeRoleRead
from app_v2.services.auth import AuthContext


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


def test_v2_enroll_employee_route_records_audit(monkeypatch):
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
                home_location_id=location_id,
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
        "app_v2.api.routes.workforce.workforce.enroll_employee_at_location",
        fake_enroll,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/v2/businesses/{business_id}/employees/enroll",
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
