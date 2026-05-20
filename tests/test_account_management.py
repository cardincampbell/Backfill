from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.business import Business, Location
from app.models.compliance import CompliancePolicyVersion
from app.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app.models.coverage import AuditLog
from app.models.identity import Membership, Session, User
from app.services.auth import AuthContext
from app.services import settings as settings_service


class FakeAccountSession:
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


def _make_auth_context(
    *,
    business_id,
    location_id=None,
    role: MembershipRole = MembershipRole.owner,
) -> AuthContext:
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        full_name="Owner Operator",
        email="owner@example.com",
        primary_phone_e164="+15555550101",
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
        role=role,
        status=MembershipStatus.active,
        accepted_at=now,
        membership_metadata={},
        created_at=now,
        updated_at=now,
    )
    return AuthContext(user=user, session=session, memberships=[membership])


def _make_location(*, business_id, location_id, name="Downtown Los Angeles") -> Location:
    now = datetime.now(timezone.utc)
    return Location(
        id=location_id,
        business_id=business_id,
        name=name,
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


def _make_business(*, business_id, name="Backfill Works, Inc.") -> Business:
    now = datetime.now(timezone.utc)
    return Business(
        id=business_id,
        name=name,
        display_name="Backfill",
        slug="backfill",
        vertical="staffing",
        primary_email="ops@backfill.io",
        timezone="America/Los_Angeles",
        status="active",
        settings={},
        place_metadata={},
        created_at=now,
        updated_at=now,
    )


def test_delete_empty_location_route_deletes_location():
    fake_session = FakeAccountSession()
    business_id = uuid4()
    location_id = uuid4()
    location = _make_location(business_id=business_id, location_id=location_id)
    fake_session.get_map[(Location, location_id)] = location
    fake_session.scalar_queue = [0]

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.delete(f"/api/businesses/{business_id}/locations/{location_id}")
        assert response.status_code == 200
        assert response.json() == {"deleted": True, "location_id": str(location_id)}
        assert fake_session.deleted == [location]
        assert any(
            isinstance(entry, AuditLog) and entry.event_name == "location.deleted"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()


def test_delete_location_with_operational_data_returns_conflict():
    fake_session = FakeAccountSession()
    business_id = uuid4()
    location_id = uuid4()
    location = _make_location(business_id=business_id, location_id=location_id, name="Protected Site")
    fake_session.get_map[(Location, location_id)] = location
    fake_session.scalar_queue = [2]

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.delete(f"/api/businesses/{business_id}/locations/{location_id}")
        assert response.status_code == 409
        assert "cannot be deleted" in response.json()["detail"].lower()
        assert fake_session.deleted == []
    finally:
        app.dependency_overrides.clear()


def test_location_delete_readiness_route_allows_empty_location():
    fake_session = FakeAccountSession()
    business_id = uuid4()
    location_id = uuid4()
    location = _make_location(business_id=business_id, location_id=location_id)
    fake_session.get_map[(Location, location_id)] = location
    fake_session.scalar_queue = [0]

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/locations/{location_id}/delete-readiness"
        )
        assert response.status_code == 200
        assert response.json() == {
            "business_id": str(business_id),
            "location_id": str(location_id),
            "can_delete": True,
            "reason": None,
        }
    finally:
        app.dependency_overrides.clear()


def test_location_delete_readiness_route_blocks_location_with_shifts():
    fake_session = FakeAccountSession()
    business_id = uuid4()
    location_id = uuid4()
    location = _make_location(business_id=business_id, location_id=location_id)
    fake_session.get_map[(Location, location_id)] = location
    fake_session.scalar_queue = [3]

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/locations/{location_id}/delete-readiness"
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["business_id"] == str(business_id)
        assert payload["location_id"] == str(location_id)
        assert payload["can_delete"] is False
        assert "cannot be removed" in payload["reason"].lower()
    finally:
        app.dependency_overrides.clear()


def test_revoke_location_manager_access_route_revokes_membership():
    fake_session = FakeAccountSession()
    business_id = uuid4()
    location_id = uuid4()
    membership_id = uuid4()
    now = datetime.now(timezone.utc)
    membership = Membership(
        id=membership_id,
        user_id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        role=MembershipRole.manager,
        status=MembershipStatus.active,
        accepted_at=now,
        membership_metadata={},
        created_at=now,
        updated_at=now,
    )
    fake_session.get_map[(Membership, membership_id)] = membership

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.delete(
            f"/api/businesses/{business_id}/locations/{location_id}/manager-access/{membership_id}"
        )
        assert response.status_code == 200
        assert response.json() == {
            "revoked": True,
            "location_id": str(location_id),
            "access_kind": "membership",
            "access_id": str(membership_id),
        }
        assert membership.status == MembershipStatus.revoked
        assert membership.revoked_at is not None
        assert any(
            isinstance(entry, AuditLog) and entry.event_name == "membership.revoked"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()


def test_account_profile_route_updates_current_user():
    fake_session = FakeAccountSession()
    business_id = uuid4()
    auth_ctx = _make_auth_context(business_id=business_id)
    original_completed_at = auth_ctx.user.onboarding_completed_at
    fake_session.scalar_queue = [None]

    async def override_db():
        yield fake_session

    async def override_auth():
        return auth_ctx

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.patch(
            "/api/account/profile",
            json={
                "full_name": "Cardin Campbell",
                "email": "cardin@example.com",
                "appearance_preference": "dark",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["user"]["full_name"] == "Cardin Campbell"
        assert payload["user"]["email"] == "cardin@example.com"
        assert payload["user"]["profile_metadata"]["appearance_preference"] == "dark"
        assert payload["onboarding_required"] is False
        assert auth_ctx.user.full_name == "Cardin Campbell"
        assert auth_ctx.user.email == "cardin@example.com"
        assert auth_ctx.user.profile_metadata["appearance_preference"] == "dark"
        assert auth_ctx.user.onboarding_completed_at == original_completed_at
        assert fake_session.commits == 1
        assert any(
            isinstance(entry, AuditLog) and entry.event_name == "account.profile.updated"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()


def test_account_profile_route_rejects_duplicate_email():
    fake_session = FakeAccountSession()
    business_id = uuid4()
    auth_ctx = _make_auth_context(business_id=business_id)
    now = datetime.now(timezone.utc)
    fake_session.scalar_queue = [
        User(
            id=uuid4(),
            full_name="Existing User",
            email="taken@example.com",
            primary_phone_e164="+15555550123",
            is_phone_verified=True,
            onboarding_completed_at=now,
            profile_metadata={},
            created_at=now,
            updated_at=now,
        )
    ]

    async def override_db():
        yield fake_session

    async def override_auth():
        return auth_ctx

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.patch(
            "/api/account/profile",
            json={
                "full_name": "Owner Operator",
                "email": "taken@example.com",
            },
        )
        assert response.status_code == 400
        assert response.json() == {"detail": "email_already_in_use"}
        assert fake_session.commits == 0
    finally:
        app.dependency_overrides.clear()


def test_business_profile_route_updates_current_business():
    fake_session = FakeAccountSession()
    business_id = uuid4()
    business = _make_business(business_id=business_id)
    fake_session.get_map[(Business, business_id)] = business
    auth_ctx = _make_auth_context(business_id=business_id)

    async def override_db():
        yield fake_session

    async def override_auth():
        return auth_ctx

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.patch(
            f"/api/businesses/{business_id}",
            json={
                "display_name": "Backfill Works",
                "vertical": "healthcare",
                "primary_email": "hello@backfill.com",
                "timezone": "America/New_York",
                "company_address": "100 Market St, San Francisco, CA 94105",
                "week_start_day": "monday",
                "same_day_second_shift_allowed": True,
                "same_location_overlap_minutes": 0,
                "cross_location_shift_coverage_allowed": False,
                "cross_location_min_gap_minutes": 60,
                "cross_location_max_radius_miles": 20,
                "auto_scheduler_labor_rule_mode": "hard_block",
                "auto_scheduler_fairness_mode": "balanced_hours",
                "reliability_coaching_style": "direct",
                "compliance": {
                    "minimum_rest_hours": 12,
                    "written_consent_allowed": False,
                    "require_structured_break_plans": True,
                    "block_unresolved_premiums": True,
                    "max_consecutive_work_days": None,
                    "required_rest_days_per_workweek": None,
                    "max_daily_minutes": 480,
                    "max_weekly_minutes": 2400,
                    "school_day_weekdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                    "school_dates": ["2026-04-18"],
                    "non_school_dates": ["2026-04-21"],
                },
                "compliance_payroll_export": {
                    "provider_profile": "gusto_csv_v1",
                    "employee_identifier_priority": ["external_ref", "employee_number"],
                    "allow_internal_employee_id_fallback": True,
                    "default_earning_code": "COMPPREM",
                    "default_earning_label": "Compliance Premium",
                    "earning_codes": {
                        "meal_break_first_window": {"code": "MEALPREM"},
                        "spread_of_hours_premium": {"code": "SPREADPREM"},
                    },
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["display_name"] == "Backfill Works"
        assert payload["vertical"] == "healthcare"
        assert payload["primary_email"] == "hello@backfill.com"
        assert payload["timezone"] == "America/New_York"
        assert business.display_name == "Backfill Works"
        assert business.vertical == "healthcare"
        assert business.primary_email == "hello@backfill.com"
        assert business.timezone == "America/New_York"
        assert business.settings["company_profile_address"] == "100 Market St, San Francisco, CA 94105"
        assert business.settings["week_start_day"] == "monday"
        assert business.settings["coverage"]["same_day_second_shift_allowed"] is True
        assert business.settings["coverage"]["same_location_overlap_minutes"] == 0
        assert business.settings["coverage"]["cross_location_shift_coverage_allowed"] is False
        assert business.settings["coverage"]["cross_location_min_gap_minutes"] == 60
        assert business.settings["coverage"]["cross_location_max_radius_miles"] == 20
        assert business.settings["auto_scheduler"]["labor_rule_mode"] == "hard_block"
        assert business.settings["auto_scheduler"]["fairness_mode"] == "balanced_hours"
        assert business.settings["reliability_coaching"]["style"] == "direct"
        assert business.settings["compliance"]["minimum_rest_hours"] == 12
        assert business.settings["compliance"]["written_consent_allowed"] is False
        assert business.settings["compliance"]["require_structured_break_plans"] is True
        assert business.settings["compliance"]["block_unresolved_premiums"] is True
        assert business.settings["compliance"]["max_daily_minutes"] == 480
        assert business.settings["compliance"]["max_weekly_minutes"] == 2400
        assert business.settings["compliance"]["school_day_weekdays"] == [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
        ]
        assert business.settings["compliance"]["school_dates"] == ["2026-04-18"]
        assert business.settings["compliance"]["non_school_dates"] == ["2026-04-21"]
        assert business.settings["compliance_payroll_export"]["employee_identifier_priority"] == [
            "external_ref",
            "employee_number",
        ]
        assert business.settings["compliance_payroll_export"]["provider_profile"] == "gusto_csv_v1"
        assert business.settings["compliance_payroll_export"]["allow_internal_employee_id_fallback"] is True
        assert business.settings["compliance_payroll_export"]["default_earning_code"] == "COMPPREM"
        assert business.settings["compliance_payroll_export"]["earning_codes"][
            "meal_break_first_window"
        ]["code"] == "MEALPREM"
        assert business.settings["compliance_payroll_export"]["earning_codes"][
            "spread_of_hours_premium"
        ]["code"] == "SPREADPREM"
        assert business.settings["compliance_policy_scope"] == "business"
        assert business.settings["compliance_policy_hash"] == settings_service.compliance_policy_hash(
            {
                "minimum_rest_hours": 12,
                "written_consent_allowed": False,
                "first_meal_waiver_allowed": None,
                "second_meal_waiver_allowed": None,
                "require_structured_break_plans": True,
                "block_unresolved_premiums": True,
                "max_consecutive_work_days": None,
                "required_rest_days_per_workweek": None,
                "max_daily_minutes": 480,
                "max_weekly_minutes": 2400,
                "school_day_weekdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                "school_dates": ["2026-04-18"],
                "non_school_dates": ["2026-04-21"],
            }
        )
        assert any(isinstance(entry, CompliancePolicyVersion) for entry in fake_session.added)
        assert business.settings["display_name_source"] == "manual"
        assert business.settings["vertical_source"] == "manual"
        assert fake_session.commits == 1
        assert any(
            isinstance(entry, AuditLog) and entry.event_name == "business.profile.updated"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()


def test_business_profile_route_rejects_stale_compliance_preview():
    fake_session = FakeAccountSession()
    business_id = uuid4()
    business = _make_business(business_id=business_id)
    business.settings = {
        "compliance": {
            "minimum_rest_hours": 10,
            "block_unresolved_premiums": True,
        }
    }
    fake_session.get_map[(Business, business_id)] = business

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.patch(
            f"/api/businesses/{business_id}",
            json={
                "display_name": business.display_name,
                "timezone": business.timezone,
                "expected_compliance_policy_hash": "stale_preview_hash",
                "compliance": {
                    "minimum_rest_hours": 12,
                    "require_structured_break_plans": True,
                },
            },
        )
        assert response.status_code == 409
        payload = response.json()["detail"]
        assert payload["code"] == "business_compliance_policy_preview_stale"
        assert payload["current_compliance_policy_hash"] == settings_service.compliance_policy_hash(
            business.settings["compliance"]
        )
        assert payload["current_compliance_settings"]["minimum_rest_hours"] == 10
        assert payload["current_compliance_settings"]["block_unresolved_premiums"] is True
        assert fake_session.commits == 0
    finally:
        app.dependency_overrides.clear()


def test_restore_business_compliance_policy_version_route_creates_new_version(monkeypatch):
    fake_session = FakeAccountSession()
    business_id = uuid4()
    version_id = uuid4()
    business = _make_business(business_id=business_id)
    fake_session.get_map[(Business, business_id)] = business

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    async def fake_restore(_session, **kwargs):
        assert kwargs["business"].id == business_id
        assert kwargs["policy_scope"] == "business"
        assert kwargs["version_id"] == version_id
        assert kwargs["expected_current_policy_hash"] == "hash_business_current"
        return CompliancePolicyVersion(
            id=uuid4(),
            business_id=business_id,
            location_id=None,
            policy_scope="business",
            policy_hash="hash_business_restored",
            settings_payload={
                "minimum_rest_hours": 11,
                "written_consent_allowed": False,
                "first_meal_waiver_allowed": None,
                "second_meal_waiver_allowed": None,
                "require_structured_break_plans": True,
                "block_unresolved_premiums": True,
                "max_consecutive_work_days": None,
                "required_rest_days_per_workweek": None,
                "max_daily_minutes": 480,
                "max_weekly_minutes": None,
            },
            effective_at=datetime(2026, 4, 24, 19, 0, tzinfo=timezone.utc),
            superseded_at=None,
            replaces_version_id=version_id,
            created_at=datetime(2026, 4, 24, 19, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 24, 19, 0, tzinfo=timezone.utc),
        )

    monkeypatch.setattr(settings_service, "restore_compliance_policy_version", fake_restore)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/businesses/{business_id}/compliance-policy-versions/{version_id}/restore",
            json={"expected_current_policy_hash": "hash_business_current"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["policy_scope"] == "business"
        assert payload["policy_hash"] == "hash_business_restored"
        assert payload["settings"]["minimum_rest_hours"] == 11
        assert fake_session.commits == 1
        assert any(
            isinstance(entry, AuditLog)
            and entry.event_name == "business.compliance_policy_version.restored"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()
