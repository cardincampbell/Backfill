from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.business import Business, Location, Role
from app.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app.models.coverage import AuditLog
from app.models.identity import Membership, Session, User
from app.schemas.business import LocationRoleRead, RoleRead
from app.services import businesses as businesses_service, shift_defaults
from app.services.auth import AuthContext


class FakeSettingsSession:
    def __init__(self):
        self.added: list[object] = []
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

    async def scalar(self, _stmt):
        return None

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None


def _make_auth_context(*, business_id, location_id=None, role=MembershipRole.manager) -> AuthContext:
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        full_name="Jordan Lead",
        email="jordan@example.com",
        primary_phone_e164="+15555550131",
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


def _make_location(*, business_id, location_id) -> Location:
    now = datetime.now(timezone.utc)
    return Location(
        id=location_id,
        business_id=business_id,
        name="Santa Monica",
        slug="santa-monica",
        address_line_1="123 Ocean Ave",
        locality="Santa Monica",
        region="CA",
        postal_code="90401",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
        google_place_metadata={},
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _make_role(*, business_id, role_id, name="Server", code="server") -> Role:
    now = datetime.now(timezone.utc)
    return Role(
        id=role_id,
        business_id=business_id,
        code=code,
        name=name,
        category=None,
        description=None,
        min_notice_minutes=0,
        default_shift_length_minutes=None,
        coverage_priority=100,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )


def _make_business(*, business_id, settings=None) -> Business:
    now = datetime.now(timezone.utc)
    return Business(
        id=business_id,
        name="Backfill",
        display_name="Backfill",
        slug="backfill",
        timezone="America/Los_Angeles",
        settings=settings or {},
        place_metadata={},
        status="active",
        created_at=now,
        updated_at=now,
    )


def test_get_location_settings_returns_defaults():
    fake_session = FakeSettingsSession()
    business_id = uuid4()
    location_id = uuid4()
    fake_session.get_map[(Location, location_id)] = _make_location(
        business_id=business_id,
        location_id=location_id,
    )

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(f"/api/businesses/{business_id}/locations/{location_id}/settings")
        assert response.status_code == 200
        assert response.json() == {
            "location_id": str(location_id),
            "coverage_requires_manager_approval": False,
            "late_arrival_policy": "wait",
            "missed_check_in_policy": "manager_action",
            "agency_supply_approved": False,
            "writeback_enabled": False,
            "timezone": "America/Los_Angeles",
            "scheduling_platform": "backfill_native",
            "integration_status": None,
            "backfill_shifts_enabled": False,
            "backfill_shifts_launch_state": "off",
            "backfill_shifts_beta_eligible": False,
            "week_start_day": None,
        }
    finally:
        app.dependency_overrides.clear()


def test_get_business_shift_defaults_returns_saved_defaults():
    fake_session = FakeSettingsSession()
    business_id = uuid4()
    fake_session.get_map[(Business, business_id)] = _make_business(
        business_id=business_id,
        settings={
            "shift_defaults": [
                {"key": "morning", "label": "Open", "start_hour": 8, "end_hour": 12},
                {"key": "afternoon", "label": "Mid", "start_hour": 12, "end_hour": 16},
                {"key": "evening", "label": "Close Prep", "start_hour": 16, "end_hour": 20},
                {"key": "night", "label": "Night", "start_hour": 20, "end_hour": 0},
            ]
        },
    )

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, role=MembershipRole.owner)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
      response = client.get(f"/api/businesses/{business_id}/shift-defaults")
      assert response.status_code == 200
      payload = response.json()
      assert payload["business_id"] == str(business_id)
      assert payload["is_persisted"] is True
      assert payload["presets"][0]["label"] == "Open"
      assert payload["presets"][3]["end_hour"] == 0
    finally:
        app.dependency_overrides.clear()


def test_patch_business_shift_defaults_updates_business_and_audits():
    fake_session = FakeSettingsSession()
    business_id = uuid4()
    business = _make_business(business_id=business_id)
    fake_session.get_map[(Business, business_id)] = business

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id, role=MembershipRole.owner)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.patch(
            f"/api/businesses/{business_id}/shift-defaults",
            json={
                "presets": [
                    {"key": "morning", "label": "Open", "start_hour": 8, "end_hour": 12},
                    {"key": "afternoon", "label": "Mid", "start_hour": 12, "end_hour": 16},
                    {"key": "evening", "label": "Close Prep", "start_hour": 16, "end_hour": 20},
                    {"key": "night", "label": "Night", "start_hour": 20, "end_hour": 0},
                ]
            },
        )
        assert response.status_code == 200
        assert business.settings["shift_defaults"][0]["label"] == "Open"
        assert business.settings["shift_defaults_source"] == "manual"
        assert any(
            isinstance(entry, AuditLog) and entry.event_name == "business.shift_defaults.updated"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()


def test_get_location_shift_defaults_returns_business_defaults_when_unset():
    fake_session = FakeSettingsSession()
    business_id = uuid4()
    location_id = uuid4()
    fake_session.get_map[(Business, business_id)] = _make_business(
        business_id=business_id,
        settings={
            "shift_defaults": [
                {"key": "morning", "label": "Open", "start_hour": 8, "end_hour": 12},
                {"key": "afternoon", "label": "Mid", "start_hour": 12, "end_hour": 16},
                {"key": "evening", "label": "Close Prep", "start_hour": 16, "end_hour": 20},
                {"key": "night", "label": "Night", "start_hour": 20, "end_hour": 0},
            ]
        },
    )
    fake_session.get_map[(Location, location_id)] = _make_location(
        business_id=business_id,
        location_id=location_id,
    )

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(
            business_id=business_id,
            location_id=location_id,
            role=MembershipRole.owner,
        )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.get(
            f"/api/businesses/{business_id}/locations/{location_id}/shift-defaults"
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["has_overrides"] is False
        assert payload["presets"][0]["label"] == "Open"
        assert payload["business_presets"][2]["label"] == "Close Prep"
        assert payload["override_presets"] is None
    finally:
        app.dependency_overrides.clear()


def test_patch_location_shift_defaults_updates_location_and_audits():
    fake_session = FakeSettingsSession()
    business_id = uuid4()
    location_id = uuid4()
    fake_session.get_map[(Business, business_id)] = _make_business(
        business_id=business_id,
        settings={
            "shift_defaults": [
                {"key": "morning", "label": "Morning", "start_hour": 7, "end_hour": 11},
                {"key": "afternoon", "label": "Afternoon", "start_hour": 11, "end_hour": 15},
                {"key": "evening", "label": "Evening", "start_hour": 15, "end_hour": 19},
                {"key": "night", "label": "Night", "start_hour": 19, "end_hour": 23},
            ]
        },
    )
    location = _make_location(business_id=business_id, location_id=location_id)
    fake_session.get_map[(Location, location_id)] = location

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(
            business_id=business_id,
            location_id=location_id,
            role=MembershipRole.owner,
        )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.patch(
            f"/api/businesses/{business_id}/locations/{location_id}/shift-defaults",
            json={
                "presets": [
                    {"key": "morning", "label": "Open", "start_hour": 8, "end_hour": 12},
                    {"key": "afternoon", "label": "Mid", "start_hour": 12, "end_hour": 16},
                    {"key": "evening", "label": "Close Prep", "start_hour": 16, "end_hour": 20},
                    {"key": "night", "label": "Night", "start_hour": 20, "end_hour": 0},
                ]
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["has_overrides"] is True
        assert payload["override_presets"][0]["label"] == "Open"
        assert location.settings["shift_defaults_override"][2]["label"] == "Close Prep"
        assert any(
            isinstance(entry, AuditLog) and entry.event_name == "location.shift_defaults.updated"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()


def test_shift_defaults_seed_from_location_hours():
    location = _make_location(business_id=uuid4(), location_id=uuid4())
    location.google_place_metadata = {
        "regular_opening_hours": {
            "periods": [
                {
                    "open": {"day": 1, "time": "0900"},
                    "close": {"day": 1, "time": "2200"},
                }
            ]
        }
    }

    presets = shift_defaults.derive_shift_presets_from_location(location)

    assert presets == [
        {"key": "morning", "label": "Morning", "start_hour": 9, "end_hour": 12},
        {"key": "afternoon", "label": "Afternoon", "start_hour": 12, "end_hour": 15},
        {"key": "evening", "label": "Evening", "start_hour": 15, "end_hour": 18},
        {"key": "night", "label": "Night", "start_hour": 18, "end_hour": 22},
    ]


def test_patch_location_settings_updates_location_and_audits():
    fake_session = FakeSettingsSession()
    business_id = uuid4()
    location_id = uuid4()
    fake_session.get_map[(Business, business_id)] = _make_business(business_id=business_id)
    location = _make_location(business_id=business_id, location_id=location_id)
    fake_session.get_map[(Location, location_id)] = location

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(business_id=business_id)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.patch(
            f"/api/businesses/{business_id}/locations/{location_id}/settings",
            json={
                "coverage_requires_manager_approval": True,
                "late_arrival_policy": "start_coverage",
                "backfill_shifts_enabled": True,
                "backfill_shifts_launch_state": "beta",
                "integration_status": "connected",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["coverage_requires_manager_approval"] is True
        assert payload["late_arrival_policy"] == "start_coverage"
        assert payload["backfill_shifts_enabled"] is True
        assert payload["backfill_shifts_launch_state"] == "beta"
        assert payload["integration_status"] == "connected"
        assert location.settings["coverage_requires_manager_approval"] is True
        assert location.settings["late_arrival_policy"] == "start_coverage"
        assert location.settings["backfill_shifts_enabled"] is True
        assert location.settings["backfill_shifts_launch_state"] == "beta"
        assert location.settings["integration_status"] == "connected"
        assert any(
            isinstance(entry, AuditLog) and entry.event_name == "location.settings.updated"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()


def test_replace_location_roles_updates_location_roles_and_audits(monkeypatch):
    fake_session = FakeSettingsSession()
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    now = datetime.now(timezone.utc)

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(
            business_id=business_id,
            location_id=location_id,
            role=MembershipRole.owner,
        )

    async def fake_replace(_session, incoming_business_id, incoming_location_id, payload):
        assert incoming_business_id == business_id
        assert incoming_location_id == location_id
        assert payload.roles[0].role_id == role_id
        return [
            LocationRoleRead(
                id=uuid4(),
                location_id=location_id,
                role_id=role_id,
                is_active=True,
                min_headcount=2,
                max_headcount=None,
                premium_rules={},
                coverage_settings={},
                created_at=now,
                updated_at=now,
            )
        ]

    monkeypatch.setattr(
        "app.api.routes.businesses.businesses.replace_location_roles",
        fake_replace,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.put(
            f"/api/businesses/{business_id}/locations/{location_id}/roles",
            json={"roles": [{"role_id": str(role_id), "min_headcount": 2}]},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload[0]["role_id"] == str(role_id)
        assert any(
            isinstance(entry, AuditLog) and entry.event_name == "location.roles.updated"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()


def test_create_and_assign_location_role_creates_role_assignment_and_audits(monkeypatch):
    fake_session = FakeSettingsSession()
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    location_role_id = uuid4()
    now = datetime.now(timezone.utc)

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(
            business_id=business_id,
            location_id=location_id,
            role=MembershipRole.owner,
        )

    async def fake_create_and_assign(_session, incoming_business_id, incoming_location_id, payload):
        assert incoming_business_id == business_id
        assert incoming_location_id == location_id
        assert payload.name == "Surgical Tech"
        return (
            RoleRead(
                id=role_id,
                business_id=business_id,
                code="surgical_tech",
                name="Surgical Tech",
                category="Healthcare",
                description=None,
                min_notice_minutes=0,
                default_shift_length_minutes=None,
                coverage_priority=100,
                metadata_json={},
                created_at=now,
                updated_at=now,
            ),
            LocationRoleRead(
                id=location_role_id,
                location_id=location_id,
                role_id=role_id,
                is_active=True,
                min_headcount=None,
                max_headcount=None,
                premium_rules={},
                coverage_settings={},
                created_at=now,
                updated_at=now,
            ),
        )

    monkeypatch.setattr(
        "app.api.routes.businesses.businesses.create_and_assign_location_role",
        fake_create_and_assign,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/businesses/{business_id}/locations/{location_id}/roles",
            json={"name": "Surgical Tech", "category": "Healthcare"},
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["role"]["id"] == str(role_id)
        assert payload["role"]["name"] == "Surgical Tech"
        assert payload["location_role"]["id"] == str(location_role_id)
        assert payload["location_role"]["role_id"] == str(role_id)
        assert any(
            isinstance(entry, AuditLog)
            and entry.event_name == "location.role.created_and_attached"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()


def test_create_role_route_returns_conflict_for_duplicate_role(monkeypatch):
    fake_session = FakeSettingsSession()
    business_id = uuid4()

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(
            business_id=business_id,
            role=MembershipRole.owner,
        )

    async def fake_create_role(_session, incoming_business_id, payload):
        assert incoming_business_id == business_id
        assert payload.name == "Server"
        raise ValueError("role_already_exists")

    monkeypatch.setattr(
        "app.api.routes.businesses.businesses.create_role",
        fake_create_role,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/businesses/{business_id}/roles",
            json={"name": "Server"},
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "role_already_exists"
    finally:
        app.dependency_overrides.clear()


def test_create_role_route_returns_existing_role_when_normalized_match_is_reused(monkeypatch):
    fake_session = FakeSettingsSession()
    business_id = uuid4()
    role_id = uuid4()
    role = _make_role(business_id=business_id, role_id=role_id, name="Barista", code="barista")

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(
            business_id=business_id,
            role=MembershipRole.owner,
        )

    async def fake_create_role(_session, incoming_business_id, payload):
        assert incoming_business_id == business_id
        assert payload.name == "Barrista"
        return businesses_service.RoleCreateResult(
            role=role,
            decision="reused_existing",
            normalized_name="Barista",
            confidence=0.98,
            reason="Corrected a spelling variation.",
        )

    monkeypatch.setattr(
        "app.api.routes.businesses.businesses.create_role",
        fake_create_role,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/businesses/{business_id}/roles",
            json={"name": "Barrista"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["decision"] == "reused_existing"
        assert payload["normalized_name"] == "Barista"
        assert payload["role"]["id"] == str(role_id)
        assert fake_session.commits == 1
        assert not any(
            isinstance(entry, AuditLog) and entry.event_name == "role.created"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()


def test_create_role_route_returns_created_role_payload(monkeypatch):
    fake_session = FakeSettingsSession()
    business_id = uuid4()
    role_id = uuid4()
    role = _make_role(business_id=business_id, role_id=role_id, name="Shift Captain", code="shift_captain")

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(
            business_id=business_id,
            role=MembershipRole.owner,
        )

    async def fake_create_role(_session, incoming_business_id, payload):
        assert incoming_business_id == business_id
        assert payload.name == "shift captain"
        return businesses_service.RoleCreateResult(
            role=role,
            decision="created_new",
            normalized_name="Shift Captain",
            confidence=0.91,
            reason="Normalized capitalization.",
        )

    monkeypatch.setattr(
        "app.api.routes.businesses.businesses.create_role",
        fake_create_role,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/businesses/{business_id}/roles",
            json={"name": "shift captain"},
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["decision"] == "created_new"
        assert payload["normalized_name"] == "Shift Captain"
        assert payload["role"]["id"] == str(role_id)
        assert any(
            isinstance(entry, AuditLog) and entry.event_name == "role.created"
            for entry in fake_session.added
        )
    finally:
        app.dependency_overrides.clear()


def test_create_role_route_returns_unprocessable_for_rejected_role_name(monkeypatch):
    fake_session = FakeSettingsSession()
    business_id = uuid4()

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(
            business_id=business_id,
            role=MembershipRole.owner,
        )

    async def fake_create_role(_session, incoming_business_id, payload):
        assert incoming_business_id == business_id
        assert payload.name == "test"
        raise businesses_service.role_normalization.RoleNameRejectedError(
            "Enter a real role name instead of a placeholder."
        )

    monkeypatch.setattr(
        "app.api.routes.businesses.businesses.create_role",
        fake_create_role,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/businesses/{business_id}/roles",
            json={"name": "test"},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "Enter a real role name instead of a placeholder."
    finally:
        app.dependency_overrides.clear()


def test_create_location_route_returns_conflict_for_duplicate_location(monkeypatch):
    fake_session = FakeSettingsSession()
    business_id = uuid4()

    async def override_db():
        yield fake_session

    async def override_auth():
        return _make_auth_context(
            business_id=business_id,
            role=MembershipRole.owner,
        )

    async def fake_create_location(_session, incoming_business_id, payload):
        assert incoming_business_id == business_id
        assert payload.google_place_id == "place_pasadena"
        raise ValueError("location_already_exists")

    monkeypatch.setattr(
        "app.api.routes.businesses.businesses.create_location",
        fake_create_location,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/businesses/{business_id}/locations",
            json={
                "name": "Pasadena",
                "display_name": "Pasadena",
                "timezone": "America/Los_Angeles",
                "google_place_id": "place_pasadena",
            },
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "location_already_exists"
    finally:
        app.dependency_overrides.clear()
