from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.business import Business, Location
from app.schemas.business import BusinessCreate, BusinessProfileUpdate, LocationCreate
from app.schemas.onboarding import OwnerWorkspaceBootstrapRequest
from app.services import business_identity_derivation, businesses, onboarding, role_derivation
from app.services.auth import AuthContext
from app.models.identity import Session, User
from app.models.common import MembershipRole, MembershipStatus, SessionRiskLevel
from app.models.identity import Membership


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


def _make_business(
    *,
    name: str | None = None,
    display_name: str,
    settings: dict | None = None,
    place_metadata: dict | None = None,
) -> Business:
    now = datetime.now(timezone.utc)
    return Business(
        id=uuid4(),
        name=name or display_name,
        display_name=display_name,
        slug="urth-caffe",
        timezone="America/Los_Angeles",
        status="active",
        settings=settings or {},
        place_metadata=place_metadata or {},
        created_at=now,
        updated_at=now,
    )


def _make_location(
    *,
    business_id,
    raw_place_name: str,
    locality: str,
    location_label: str | None = None,
) -> Location:
    now = datetime.now(timezone.utc)
    return Location(
        id=uuid4(),
        business_id=business_id,
        name=raw_place_name,
        slug=raw_place_name.lower().replace(" ", "-"),
        address_line_1="123 Main St",
        locality=locality,
        region="CA",
        postal_code="91101",
        country_code="US",
        timezone="America/Los_Angeles",
        google_place_id=f"place_{uuid4()}",
        google_place_metadata={
            "display_name": raw_place_name,
            "location_label": location_label or locality,
            "city": locality,
            "primary_type": "coffee_shop",
            "types": ["cafe", "coffee_shop"],
            "address_components": [
                {"longText": locality, "shortText": locality, "types": ["locality"]},
            ],
        },
        settings={},
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _make_auth_context() -> AuthContext:
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        full_name=None,
        email=None,
        primary_phone_e164="+15555550111",
        is_phone_verified=True,
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
        business_id=uuid4(),
        role=MembershipRole.owner,
        status=MembershipStatus.active,
        membership_metadata={},
        created_at=now,
        updated_at=now,
    )
    return AuthContext(user=user, session=session, memberships=[membership])


def _make_role_taxonomy() -> role_derivation.RoleDerivationTaxonomy:
    return role_derivation.RoleDerivationTaxonomy(
        business_vertical_type_mappings={
            "cafe": ("cafe", "cafe"),
            "coffee_shop": ("cafe", "coffee_shop"),
        },
        business_vertical_role_archetypes={
            "cafe": (
                "general_manager",
                "shift_lead",
                "barista",
                "cashier",
                "prep_kitchen",
            ),
            "mixed_unknown": ("general_manager",),
        },
        business_role_archetypes={
            "general_manager": role_derivation.BusinessRoleArchetypeDefinition("General Manager", "management"),
            "shift_lead": role_derivation.BusinessRoleArchetypeDefinition("Shift Lead", "operations"),
            "barista": role_derivation.BusinessRoleArchetypeDefinition("Barista", "front_of_house"),
            "cashier": role_derivation.BusinessRoleArchetypeDefinition("Cashier", "front_of_house"),
            "prep_kitchen": role_derivation.BusinessRoleArchetypeDefinition("Prep Kitchen", "back_of_house"),
            "assistant_manager": role_derivation.BusinessRoleArchetypeDefinition("Assistant Manager", "management"),
            "baker": role_derivation.BusinessRoleArchetypeDefinition("Baker", "back_of_house"),
        },
        active_vertical_codes=("cafe", "mixed_unknown"),
        subverticals_by_vertical={
            "cafe": ("cafe", "coffee_shop"),
            "mixed_unknown": (),
        },
    )


def test_derive_business_identity_confirms_sibling_locality_suffixes():
    business = _make_business(
        display_name="Urth Caffe Pasadena",
        place_metadata={"name": "Urth Caffe Pasadena"},
    )
    pasadena = _make_location(
        business_id=business.id,
        raw_place_name="Urth Caffe Pasadena",
        locality="Pasadena",
    )
    santa_monica = _make_location(
        business_id=business.id,
        raw_place_name="Urth Caffe Santa Monica",
        locality="Santa Monica",
    )

    result = business_identity_derivation.derive_business_identity(
        business,
        locations=[pasadena, santa_monica],
    )

    assert result.canonical_business_name == "Urth Caffe"
    assert result.derivation_method == "multi_location_locality_suffix_match"
    assert result.support_location_count == 2
    location_map = {identity.location_id: identity for identity in result.locations}
    assert location_map[pasadena.id].location_label == "Pasadena"
    assert location_map[pasadena.id].suggested_location_name == "Pasadena"
    assert location_map[santa_monica.id].location_label == "Santa Monica"


def test_derive_business_identity_protects_intrinsic_city_names():
    business = _make_business(
        display_name="Boston Market Pasadena",
        place_metadata={"name": "Boston Market Pasadena"},
    )
    pasadena = _make_location(
        business_id=business.id,
        raw_place_name="Boston Market Pasadena",
        locality="Pasadena",
    )

    result = business_identity_derivation.derive_business_identity(business, locations=[pasadena])

    assert result.canonical_business_name == "Boston Market Pasadena"
    assert result.derivation_method == "raw_place_name_fallback"


@pytest.mark.asyncio
async def test_sync_business_identity_promotes_clean_business_name_and_persists_evidence():
    session = FakeSession()
    business = _make_business(
        display_name="Urth Caffe Pasadena",
        place_metadata={"name": "Urth Caffe Pasadena"},
    )
    pasadena = _make_location(
        business_id=business.id,
        raw_place_name="Urth Caffe Pasadena",
        locality="Pasadena",
    )
    santa_monica = _make_location(
        business_id=business.id,
        raw_place_name="Urth Caffe Santa Monica",
        locality="Santa Monica",
    )

    result = await business_identity_derivation.sync_business_identity(
        session,
        business,
        locations=[pasadena, santa_monica],
    )

    assert business.display_name == "Urth Caffe"
    assert business.settings["display_name_source"] == "derived"
    assert business.settings["derived_identity"]["canonical_business_name"] == "Urth Caffe"
    assert pasadena.settings["derived_identity"]["suggested_location_name"] == "Pasadena"
    assert pasadena.settings["derived_identity"]["location_name_promoted"] is False
    assert pasadena.name == "Urth Caffe Pasadena"
    assert pasadena.display_name == "Pasadena"
    assert result.support_location_count == 2


@pytest.mark.asyncio
async def test_sync_business_identity_respects_manual_brand_override():
    session = FakeSession()
    business = _make_business(
        display_name="Urth Caffe",
        settings={"display_name_source": "manual"},
        place_metadata={"name": "Urth Caffe Pasadena"},
    )
    pasadena = _make_location(
        business_id=business.id,
        raw_place_name="Urth Caffe Pasadena",
        locality="Pasadena",
    )
    santa_monica = _make_location(
        business_id=business.id,
        raw_place_name="Urth Caffe Santa Monica",
        locality="Santa Monica",
    )

    await business_identity_derivation.sync_business_identity(
        session,
        business,
        locations=[pasadena, santa_monica],
    )

    assert business.display_name == "Urth Caffe"
    assert business.settings["display_name_source"] == "manual"
    assert business.settings["derived_identity"]["manual_override_active"] is True


@pytest.mark.asyncio
async def test_sync_business_identity_does_not_promote_single_location_name():
    session = FakeSession()
    business = _make_business(
        display_name="Urth Caffe Pasadena",
        place_metadata={"name": "Urth Caffe Pasadena"},
    )
    pasadena = _make_location(
        business_id=business.id,
        raw_place_name="Urth Caffe Pasadena",
        locality="Pasadena",
    )

    await business_identity_derivation.sync_business_identity(
        session,
        business,
        locations=[pasadena],
    )

    assert business.display_name == "Urth Caffe"
    assert pasadena.settings["derived_identity"]["location_name_promoted"] is False
    assert pasadena.name == "Urth Caffe Pasadena"


@pytest.mark.asyncio
async def test_bootstrap_owner_workspace_derives_identity_once_after_first_location(monkeypatch):
    session = FakeSession()
    auth_ctx = _make_auth_context()
    identity_calls: list[list[str]] = []
    original_sync = business_identity_derivation.sync_business_identity

    async def fake_load_taxonomy(_session):
        return _make_role_taxonomy()

    async def instrumented_sync(db_session, business, *, locations=None):
        identity_calls.append([str(location.id) for location in (locations or [])])
        return await original_sync(db_session, business, locations=locations)

    monkeypatch.setattr(role_derivation, "load_role_derivation_taxonomy", fake_load_taxonomy)
    monkeypatch.setattr(business_identity_derivation, "sync_business_identity", instrumented_sync)

    await onboarding.bootstrap_owner_workspace(
        session,
        auth_ctx,
        OwnerWorkspaceBootstrapRequest(
            profile={"full_name": "Cardin Campbell", "email": "cardin@example.com"},
            business={
                "name": "Urth Caffe LLC",
                "display_name": "Urth Caffe Pasadena",
                "timezone": "America/Los_Angeles",
                "place_metadata": {"name": "Urth Caffe Pasadena"},
            },
            location={
                "name": "Urth Caffe Pasadena",
                "address_line_1": "123 Main St",
                "locality": "Pasadena",
                "region": "CA",
                "postal_code": "91101",
                "timezone": "America/Los_Angeles",
                "google_place_id": "place_123",
                "google_place_metadata": {
                    "display_name": "Urth Caffe Pasadena",
                    "location_label": "Pasadena",
                    "city": "Pasadena",
                    "primary_type": "coffee_shop",
                    "types": ["cafe", "coffee_shop"],
                    "address_components": [
                        {"longText": "Pasadena", "shortText": "Pasadena", "types": ["locality"]},
                    ],
                },
            },
        ),
    )

    assert len(identity_calls) == 1
    assert len(identity_calls[0]) == 1


@pytest.mark.asyncio
async def test_bootstrap_owner_workspace_promotes_clean_business_name(monkeypatch):
    session = FakeSession()
    auth_ctx = _make_auth_context()

    async def fake_load_taxonomy(_session):
        return _make_role_taxonomy()

    monkeypatch.setattr(role_derivation, "load_role_derivation_taxonomy", fake_load_taxonomy)

    _user, business, location, _owner_membership = await onboarding.bootstrap_owner_workspace(
        session,
        auth_ctx,
        OwnerWorkspaceBootstrapRequest(
            profile={"full_name": "Cardin Campbell", "email": "cardin@example.com"},
            business={
                "name": "Urth Caffe LLC",
                "display_name": "Urth Caffe Pasadena",
                "timezone": "America/Los_Angeles",
                "place_metadata": {"name": "Urth Caffe Pasadena"},
            },
            location={
                "name": "Urth Caffe Pasadena",
                "address_line_1": "123 Main St",
                "locality": "Pasadena",
                "region": "CA",
                "postal_code": "91101",
                "timezone": "America/Los_Angeles",
                "google_place_id": "place_123",
                "google_place_metadata": {
                    "display_name": "Urth Caffe Pasadena",
                    "location_label": "Pasadena",
                    "city": "Pasadena",
                    "primary_type": "coffee_shop",
                    "types": ["cafe", "coffee_shop"],
                    "address_components": [
                        {"longText": "Pasadena", "shortText": "Pasadena", "types": ["locality"]},
                    ],
                },
            },
        ),
    )

    assert business.display_name == "Urth Caffe"
    assert business.settings["derived_identity"]["canonical_business_name"] == "Urth Caffe"
    assert location.settings["derived_identity"]["suggested_location_name"] == "Pasadena"
    assert location.settings["derived_identity"]["location_name_promoted"] is False


@pytest.mark.asyncio
async def test_update_business_profile_marks_brand_name_as_manual():
    session = FakeSession()
    business = _make_business(display_name="Backfill")

    await businesses.update_business_profile(
        session,
        business,
        payload=BusinessProfileUpdate(
            display_name="Backfill Works",
            vertical="healthcare",
            primary_email="hello@backfill.com",
            timezone="America/New_York",
            company_address="100 Market St, San Francisco, CA 94105",
            week_start_day="monday",
            same_day_second_shift_allowed=True,
            same_location_overlap_minutes=0,
            cross_location_shift_coverage_allowed=False,
            cross_location_min_gap_minutes=60,
            cross_location_max_radius_miles=20,
            auto_scheduler_labor_rule_mode="hard_block",
            auto_scheduler_fairness_mode="balanced_hours",
        ),
    )

    assert business.display_name == "Backfill Works"
    assert business.settings["display_name_source"] == "manual"
    assert business.settings["vertical_source"] == "manual"
    assert business.settings["week_start_day"] == "monday"
    assert business.settings["coverage"]["same_day_second_shift_allowed"] is True
    assert business.settings["coverage"]["same_location_overlap_minutes"] == 0
    assert business.settings["coverage"]["cross_location_shift_coverage_allowed"] is False
    assert business.settings["coverage"]["cross_location_min_gap_minutes"] == 60
    assert business.settings["coverage"]["cross_location_max_radius_miles"] == 20
    assert business.settings["auto_scheduler"]["labor_rule_mode"] == "hard_block"
    assert business.settings["auto_scheduler"]["fairness_mode"] == "balanced_hours"


@pytest.mark.asyncio
async def test_create_business_record_seeds_slug_from_display_name():
    session = FakeSession()

    business = await businesses.create_business_record(
        session,
        BusinessCreate(
            name="Urth Caffe Pasadena",
            display_name="Urth Caffe",
            timezone="America/Los_Angeles",
        ),
        derive_identity=False,
        derive_roles=False,
    )

    assert business.name == "Urth Caffe Pasadena"
    assert business.display_name == "Urth Caffe"
    assert business.slug == "urth-caffe"


@pytest.mark.asyncio
async def test_create_location_record_seeds_slug_from_display_name_or_location_label():
    session = FakeSession()
    business = _make_business(name="Urth Caffe Pasadena", display_name="Urth Caffe")
    session.add(business)

    location = await businesses.create_location_record(
        session,
        business.id,
        LocationCreate(
            name="Urth Caffe Pasadena",
            timezone="America/Los_Angeles",
            google_place_id="place_pasadena",
            google_place_metadata={"location_label": "Pasadena"},
        ),
        derive_identity=False,
        derive_roles=False,
    )

    assert location.name == "Urth Caffe Pasadena"
    assert location.display_name == "Pasadena"
    assert location.slug == "pasadena"
