from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_auth_context, get_db_session
from app.main import app
from app.models.business import Business, Location
from app.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app.models.coverage import AuditLog
from app.models.identity import Membership, Session, User
from app.schemas.onboarding import OwnerWorkspaceBootstrapRequest
from app.services import onboarding, role_derivation, workspace
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


class FakeSession:
    def __init__(self):
        self.added: list[object] = []
        self.commits = 0
        self.flushed = 0
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

    async def commit(self):
        self.commits += 1

    async def flush(self):
        self.flushed += 1

    async def refresh(self, _obj):
        return None

    async def scalar(self, _query):
        if self.scalar_queue:
            return self.scalar_queue.pop(0)
        return None

    async def execute(self, _query):
        values = self.execute_queue.pop(0) if self.execute_queue else []
        return _ExecuteResult(values)

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))


def _make_auth_context() -> AuthContext:
    user = User(
        id=uuid4(),
        full_name=None,
        email=None,
        primary_phone_e164="+15555550111",
        is_phone_verified=True,
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
        expires_at=datetime.now(timezone.utc),
        session_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    return AuthContext(user=user, session=session, memberships=[])


@pytest.mark.asyncio
async def test_bootstrap_owner_workspace_creates_business_location_membership():
    session = FakeSession()
    auth_ctx = _make_auth_context()

    user, business, location, owner_membership = await onboarding.bootstrap_owner_workspace(
        session,
        auth_ctx,
        OwnerWorkspaceBootstrapRequest(
            profile={"full_name": "Cardin Campbell", "email": "cardin@example.com"},
            business={
                "legal_name": "Whole Foods Market LLC",
                "brand_name": "Whole Foods Market",
                "vertical": "retail",
                "timezone": "America/Los_Angeles",
            },
            location={
                "name": "Downtown Los Angeles",
                "address_line_1": "788 S Grand Ave",
                "locality": "Los Angeles",
                "region": "CA",
                "postal_code": "90017",
                "timezone": "America/Los_Angeles",
                "google_place_id": "place_123",
            },
        ),
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    audits = [obj for obj in session.added if isinstance(obj, AuditLog)]
    assert user.full_name == "Cardin Campbell"
    assert user.email == "cardin@example.com"
    assert user.onboarding_completed_at is not None
    assert business.brand_name == "Whole Foods Market"
    assert location.business_id == business.id
    assert owner_membership.business_id == business.id
    assert owner_membership.role == MembershipRole.owner
    assert owner_membership.status == MembershipStatus.active
    assert {entry.event_name for entry in audits} == {
        "business.created",
        "membership.granted",
        "location.created",
        "onboarding.workspace.bootstrapped",
    }


@pytest.mark.asyncio
async def test_bootstrap_owner_workspace_derives_roles_once_after_location_exists(monkeypatch):
    session = FakeSession()
    auth_ctx = _make_auth_context()
    derive_calls: list[tuple[str, list[str]]] = []
    original_sync = role_derivation.sync_business_role_catalog

    async def instrumented_sync(db_session, business, *, locations=None):
        derive_calls.append(
            (
                str(business.id),
                [str(location.id) for location in (locations or [])],
            )
        )
        return await original_sync(db_session, business, locations=locations)

    monkeypatch.setattr(role_derivation, "sync_business_role_catalog", instrumented_sync)

    await onboarding.bootstrap_owner_workspace(
        session,
        auth_ctx,
        OwnerWorkspaceBootstrapRequest(
            profile={"full_name": "Cardin Campbell", "email": "cardin@example.com"},
            business={
                "legal_name": "Whole Foods Market LLC",
                "brand_name": "Whole Foods Market",
                "vertical": "retail",
                "timezone": "America/Los_Angeles",
            },
            location={
                "name": "Downtown Los Angeles",
                "address_line_1": "788 S Grand Ave",
                "locality": "Los Angeles",
                "region": "CA",
                "postal_code": "90017",
                "timezone": "America/Los_Angeles",
                "google_place_id": "place_123",
            },
        ),
    )

    assert len(derive_calls) == 1
    assert len(derive_calls[0][1]) == 1


@pytest.mark.asyncio
async def test_workspace_expands_business_membership_to_all_locations():
    session = FakeSession()
    business_id = uuid4()
    owner_membership = Membership(
        id=uuid4(),
        user_id=uuid4(),
        business_id=business_id,
        role=MembershipRole.owner,
        status=MembershipStatus.active,
        membership_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    auth_ctx = AuthContext(
        user=User(
            id=owner_membership.user_id,
            full_name="Owner",
            email="owner@example.com",
            primary_phone_e164="+15555550122",
            is_phone_verified=True,
            onboarding_completed_at=datetime.now(timezone.utc),
            profile_metadata={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        session=Session(
            id=uuid4(),
            user_id=owner_membership.user_id,
            token_hash="hashed",
            risk_level=SessionRiskLevel.low,
            elevated_actions=[],
            last_seen_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc),
            session_metadata={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        memberships=[owner_membership],
    )

    business = Business(
        id=business_id,
        legal_name="Whole Foods Market LLC",
        brand_name="Whole Foods Market",
        slug="whole-foods-market",
        timezone="America/Los_Angeles",
        status="active",
        settings={},
        place_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    location_one = Location(
        id=uuid4(),
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
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    location_two = Location(
        id=uuid4(),
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
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    session.execute_queue = [[business], [location_one, location_two]]
    rows = await workspace.list_workspace_locations(session, auth_ctx)
    assert len(rows) == 2
    assert {row.location.id for row in rows} == {location_one.id, location_two.id}
    assert all(row.membership_scope == "business" for row in rows)


def test_workspace_route_returns_locations(monkeypatch):
    auth_ctx = _make_auth_context()
    business_id = uuid4()
    location_id = uuid4()
    membership = Membership(
        id=uuid4(),
        user_id=auth_ctx.user.id,
        business_id=business_id,
        location_id=location_id,
        role=MembershipRole.manager,
        status=MembershipStatus.active,
        membership_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    auth_ctx.user.full_name = "Manager"
    auth_ctx.user.email = "manager@example.com"
    auth_ctx.user.onboarding_completed_at = datetime.now(timezone.utc)
    auth_ctx.memberships = [membership]

    async def override_db():
        yield FakeSession()

    async def override_auth():
        return auth_ctx

    async def fake_list_workspace_locations(_session, _auth_ctx):
        return [
            workspace.WorkspaceLocation(
                membership=membership,
                business=Business(
                    id=business_id,
                    legal_name="Whole Foods Market LLC",
                    brand_name="Whole Foods Market",
                    slug="whole-foods-market",
                    timezone="America/Los_Angeles",
                    status="active",
                    settings={},
                    place_metadata={},
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                ),
                location=Location(
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
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                ),
                membership_scope="location",
            )
        ]

    monkeypatch.setattr("app.api.routes.workspace.workspace_service.list_workspace_locations", fake_list_workspace_locations)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.get("/api/workspace")
        assert response.status_code == 200
        payload = response.json()
        assert payload["onboarding_required"] is False
        assert len(payload["locations"]) == 1
        assert payload["locations"][0]["membership_scope"] == "location"
    finally:
        app.dependency_overrides.clear()


def test_workspace_route_includes_business_without_locations(monkeypatch):
    auth_ctx = _make_auth_context()
    business_id = uuid4()
    membership = Membership(
        id=uuid4(),
        user_id=auth_ctx.user.id,
        business_id=business_id,
        role=MembershipRole.owner,
        status=MembershipStatus.active,
        membership_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    auth_ctx.user.full_name = "Operator"
    auth_ctx.user.email = "operator@example.com"
    auth_ctx.user.onboarding_completed_at = datetime.now(timezone.utc)
    auth_ctx.memberships = [membership]

    async def override_db():
        yield FakeSession()

    async def override_auth():
        return auth_ctx

    async def fake_list_workspace_locations(_session, _auth_ctx):
        return []

    async def fake_list_businesses(_session, business_ids=None):
        assert business_ids == [business_id]
        return [
            Business(
                id=business_id,
                legal_name="Urth Caffe LLC",
                brand_name="Urth Caffe",
                slug="urth-caffe",
                timezone="America/Los_Angeles",
                status="active",
                settings={},
                place_metadata={},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        ]

    monkeypatch.setattr(
        "app.api.routes.workspace.workspace_service.list_workspace_locations",
        fake_list_workspace_locations,
    )
    monkeypatch.setattr(
        "app.api.routes.workspace.businesses_service.list_businesses",
        fake_list_businesses,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_auth_context] = override_auth
    try:
        client = TestClient(app)
        response = client.get("/api/workspace")
        assert response.status_code == 200
        payload = response.json()
        assert payload["businesses"] == [
            {
                "business_id": str(business_id),
                "business_name": "Urth Caffe",
                "business_slug": "urth-caffe",
                "membership_role": "owner",
                "location_count": 0,
                "locations": [],
            }
        ]
        assert payload["locations"] == []
    finally:
        app.dependency_overrides.clear()
