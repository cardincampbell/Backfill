from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.business import Business, Location, LocationRole, Role
from app.models.common import ShiftStatus
from app.models.role_taxonomy import (
    BusinessVertical,
    BusinessVerticalTypeMapping,
    BusinessSubvertical,
    BusinessRoleArchetype,
    BusinessVerticalRoleArchetype,
)
from app.models.scheduling import Shift
from app.schemas.scheduling import ShiftCreate
from app.schemas.workforce import EmployeeEnrollAtLocationCreate
from app.services import (
    business_classification,
    businesses,
    retell_workflow,
    role_derivation,
    scheduler_sync,
    scheduling,
    workforce,
)


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
        self.scalar_queue: list[object] = []
        self.execute_queue: list[list[object]] = []
        self.get_map: dict[tuple[type, object], object] = {}

    def add(self, obj):
        now = datetime.now(timezone.utc)
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if hasattr(obj, "status") and getattr(obj, "status", None) is None:
            obj.status = "active"
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = now
        if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
            obj.updated_at = now
        self.added.append(obj)
        self.get_map[(type(obj), obj.id)] = obj

    async def flush(self):
        return None

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


@pytest.fixture(autouse=True)
def disable_llm_refinement_by_default(monkeypatch):
    monkeypatch.setattr(
        role_derivation,
        "settings",
        SimpleNamespace(role_derivation_model="", openai_api_key=""),
    )
    monkeypatch.setattr(
        business_classification,
        "settings",
        SimpleNamespace(
            business_classification_model="",
            business_classification_mode="shadow",
        ),
    )


def _make_location(*, business_id, primary_type: str, types: list[str], hours: dict | None = None) -> Location:
    now = datetime.now(timezone.utc)
    return Location(
        id=uuid4(),
        business_id=business_id,
        name="Sample Location",
        slug="sample-location",
        address_line_1="123 Main St",
        locality="Los Angeles",
        region="CA",
        postal_code="90001",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
        google_place_id="place_123",
        google_place_metadata={
            "primary_type": primary_type,
            "types": types,
            "regular_opening_hours": hours or {},
        },
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def _make_business(*, vertical: str | None = None, place_metadata: dict | None = None) -> Business:
    now = datetime.now(timezone.utc)
    return Business(
        id=uuid4(),
        name="Backfill Test LLC",
        display_name="Backfill Test",
        slug="backfill-test",
        vertical=vertical,
        primary_email="ops@example.com",
        timezone="America/Los_Angeles",
        status="active",
        settings={},
        place_metadata=place_metadata or {},
        created_at=now,
        updated_at=now,
    )


def _make_taxonomy() -> role_derivation.RoleDerivationTaxonomy:
    return role_derivation.RoleDerivationTaxonomy(
        business_vertical_type_mappings={
            "restaurant": ("restaurant", "full_service_restaurant"),
            "bar": ("bar", "bar"),
            "cafe": ("cafe", "cafe"),
            "coffee_shop": ("cafe", "coffee_shop"),
            "bakery": ("bakery", "bakery"),
            "store": ("retail", None),
        },
        business_vertical_role_archetypes={
            "restaurant": (
                "general_manager",
                "assistant_manager",
                "shift_lead",
                "server",
                "host",
                "line_cook",
                "dishwasher",
            ),
            "cafe": (
                "general_manager",
                "shift_lead",
                "barista",
                "cashier",
                "prep_kitchen",
            ),
            "bakery": (
                "general_manager",
                "shift_lead",
                "baker",
                "cashier",
                "prep_kitchen",
            ),
            "retail": (
                "store_manager",
                "assistant_manager",
                "shift_lead",
                "sales_associate",
                "cashier",
                "stock_associate",
            ),
            "bar": (
                "general_manager",
                "assistant_manager",
                "shift_lead",
                "bartender",
                "barback",
                "host",
            ),
            "mixed_unknown": ("general_manager",),
        },
        business_role_archetypes={
            "general_manager": role_derivation.BusinessRoleArchetypeDefinition("General Manager", "management"),
            "assistant_manager": role_derivation.BusinessRoleArchetypeDefinition("Assistant Manager", "management"),
            "shift_lead": role_derivation.BusinessRoleArchetypeDefinition("Shift Lead", "operations"),
            "server": role_derivation.BusinessRoleArchetypeDefinition("Server", "front_of_house"),
            "host": role_derivation.BusinessRoleArchetypeDefinition("Host", "front_of_house"),
            "line_cook": role_derivation.BusinessRoleArchetypeDefinition("Line Cook", "back_of_house"),
            "dishwasher": role_derivation.BusinessRoleArchetypeDefinition("Dishwasher", "back_of_house"),
            "bartender": role_derivation.BusinessRoleArchetypeDefinition("Bartender", "front_of_house"),
            "barback": role_derivation.BusinessRoleArchetypeDefinition("Barback", "front_of_house"),
            "barista": role_derivation.BusinessRoleArchetypeDefinition("Barista", "front_of_house"),
            "cashier": role_derivation.BusinessRoleArchetypeDefinition("Cashier", "front_of_house"),
            "prep_kitchen": role_derivation.BusinessRoleArchetypeDefinition("Prep Kitchen", "back_of_house"),
            "baker": role_derivation.BusinessRoleArchetypeDefinition("Baker", "back_of_house"),
            "store_manager": role_derivation.BusinessRoleArchetypeDefinition("Store Manager", "management"),
            "sales_associate": role_derivation.BusinessRoleArchetypeDefinition("Sales Associate", "sales"),
            "stock_associate": role_derivation.BusinessRoleArchetypeDefinition("Stock Associate", "inventory"),
            "delivery_coordinator": role_derivation.BusinessRoleArchetypeDefinition("Delivery Coordinator", "operations"),
            "expeditor": role_derivation.BusinessRoleArchetypeDefinition("Expeditor", "operations"),
            "inventory_lead": role_derivation.BusinessRoleArchetypeDefinition("Inventory Lead", "inventory"),
        },
        active_vertical_codes=("bakery", "bar", "cafe", "mixed_unknown", "restaurant", "retail"),
        subverticals_by_vertical={
            "restaurant": ("full_service_restaurant",),
            "bar": ("bar",),
            "cafe": ("cafe", "coffee_shop"),
            "bakery": ("bakery",),
            "retail": (),
            "mixed_unknown": (),
        },
    )


def _make_taxonomy_execute_queue() -> list[list[object]]:
    verticals = [
        BusinessVertical(code="restaurant", display_name="Restaurant", is_active=True, metadata_json={}),
        BusinessVertical(code="cafe", display_name="Cafe", is_active=True, metadata_json={}),
        BusinessVertical(code="bakery", display_name="Bakery", is_active=True, metadata_json={}),
        BusinessVertical(code="bar", display_name="Bar", is_active=True, metadata_json={}),
        BusinessVertical(code="retail", display_name="Retail", is_active=True, metadata_json={}),
        BusinessVertical(code="mixed_unknown", display_name="Mixed / Unknown", is_active=True, metadata_json={}),
    ]
    mappings = [
        BusinessVerticalTypeMapping(place_type="restaurant", business_vertical_code="restaurant", subvertical_code="full_service_restaurant", is_active=True, metadata_json={}),
        BusinessVerticalTypeMapping(place_type="bar", business_vertical_code="bar", subvertical_code="bar", is_active=True, metadata_json={}),
        BusinessVerticalTypeMapping(place_type="cafe", business_vertical_code="cafe", subvertical_code="cafe", is_active=True, metadata_json={}),
        BusinessVerticalTypeMapping(place_type="coffee_shop", business_vertical_code="cafe", subvertical_code="coffee_shop", is_active=True, metadata_json={}),
        BusinessVerticalTypeMapping(place_type="bakery", business_vertical_code="bakery", subvertical_code="bakery", is_active=True, metadata_json={}),
        BusinessVerticalTypeMapping(place_type="store", business_vertical_code="retail", subvertical_code=None, is_active=True, metadata_json={}),
    ]
    subverticals = [
        BusinessSubvertical(code="full_service_restaurant", business_vertical_code="restaurant", display_name="Full Service Restaurant", is_active=True, metadata_json={}),
        BusinessSubvertical(code="bar", business_vertical_code="bar", display_name="Bar", is_active=True, metadata_json={}),
        BusinessSubvertical(code="cafe", business_vertical_code="cafe", display_name="Cafe", is_active=True, metadata_json={}),
        BusinessSubvertical(code="coffee_shop", business_vertical_code="cafe", display_name="Coffee Shop", is_active=True, metadata_json={}),
        BusinessSubvertical(code="bakery", business_vertical_code="bakery", display_name="Bakery", is_active=True, metadata_json={}),
    ]
    role_templates = [
        BusinessRoleArchetype(code="general_manager", display_name="General Manager", role_family="management", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="assistant_manager", display_name="Assistant Manager", role_family="management", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="shift_lead", display_name="Shift Lead", role_family="operations", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="server", display_name="Server", role_family="front_of_house", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="host", display_name="Host", role_family="front_of_house", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="line_cook", display_name="Line Cook", role_family="back_of_house", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="dishwasher", display_name="Dishwasher", role_family="back_of_house", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="bartender", display_name="Bartender", role_family="front_of_house", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="barback", display_name="Barback", role_family="front_of_house", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="barista", display_name="Barista", role_family="front_of_house", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="cashier", display_name="Cashier", role_family="front_of_house", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="prep_kitchen", display_name="Prep Kitchen", role_family="back_of_house", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="baker", display_name="Baker", role_family="back_of_house", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="store_manager", display_name="Store Manager", role_family="management", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="sales_associate", display_name="Sales Associate", role_family="sales", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="stock_associate", display_name="Stock Associate", role_family="inventory", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="delivery_coordinator", display_name="Delivery Coordinator", role_family="operations", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="expeditor", display_name="Expeditor", role_family="operations", is_active=True, metadata_json={}),
        BusinessRoleArchetype(code="inventory_lead", display_name="Inventory Lead", role_family="inventory", is_active=True, metadata_json={}),
    ]
    vertical_roles = [
        BusinessVerticalRoleArchetype(business_vertical_code="restaurant", business_role_code="general_manager", sort_order=10, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="restaurant", business_role_code="assistant_manager", sort_order=20, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="restaurant", business_role_code="shift_lead", sort_order=30, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="restaurant", business_role_code="server", sort_order=40, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="restaurant", business_role_code="host", sort_order=50, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="restaurant", business_role_code="line_cook", sort_order=60, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="restaurant", business_role_code="dishwasher", sort_order=70, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="cafe", business_role_code="general_manager", sort_order=10, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="cafe", business_role_code="shift_lead", sort_order=20, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="cafe", business_role_code="barista", sort_order=30, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="cafe", business_role_code="cashier", sort_order=40, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="cafe", business_role_code="prep_kitchen", sort_order=50, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="bakery", business_role_code="general_manager", sort_order=10, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="bakery", business_role_code="shift_lead", sort_order=20, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="bakery", business_role_code="baker", sort_order=30, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="bakery", business_role_code="cashier", sort_order=40, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="bakery", business_role_code="prep_kitchen", sort_order=50, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="retail", business_role_code="store_manager", sort_order=10, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="retail", business_role_code="assistant_manager", sort_order=20, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="retail", business_role_code="shift_lead", sort_order=30, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="retail", business_role_code="sales_associate", sort_order=40, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="retail", business_role_code="cashier", sort_order=50, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="retail", business_role_code="stock_associate", sort_order=60, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="bar", business_role_code="general_manager", sort_order=10, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="bar", business_role_code="assistant_manager", sort_order=20, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="bar", business_role_code="shift_lead", sort_order=30, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="bar", business_role_code="bartender", sort_order=40, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="bar", business_role_code="barback", sort_order=50, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="bar", business_role_code="host", sort_order=60, is_active=True, metadata_json={}),
        BusinessVerticalRoleArchetype(business_vertical_code="mixed_unknown", business_role_code="general_manager", sort_order=10, is_active=True, metadata_json={}),
    ]
    return [verticals, mappings, subverticals, role_templates, vertical_roles, verticals, subverticals]


def test_derive_business_catalog_builds_business_level_role_pack():
    business_id = uuid4()
    cafe_location = _make_location(
        business_id=business_id,
        primary_type="coffee_shop",
        types=["cafe", "coffee_shop", "bakery"],
        hours={"periods": [{"open": {"time": "0600"}}]},
    )
    result = role_derivation.derive_business_catalog(
        taxonomy=_make_taxonomy(),
        business_place_metadata={"primary_type": "coffee_shop", "types": ["cafe", "coffee_shop"]},
        locations=[cafe_location],
    )

    assert result.classification.vertical == "cafe"
    assert result.classification.subvertical == "coffee_shop"
    role_keys = {role.role_key for role in result.roles}
    assert {"barista", "cashier", "prep_kitchen"}.issubset(role_keys)
    assert "baker" in role_keys
    baker = next(role for role in result.roles if role.role_key == "baker")
    assert baker.derivation_type == "modifier"
    assert cafe_location.id in baker.support_location_ids


@pytest.mark.asyncio
async def test_sync_business_role_catalog_persists_classification_and_roles():
    business = _make_business(place_metadata={"primary_type": "restaurant", "types": ["restaurant", "bar"]})
    location = _make_location(
        business_id=business.id,
        primary_type="restaurant",
        types=["restaurant", "bar"],
        hours={"periods": [{"open": {"time": "1700"}}]},
    )
    session = FakeSession()
    session.execute_queue = [*_make_taxonomy_execute_queue(), []]

    derivation = await role_derivation.sync_business_role_catalog(session, business, locations=[location])

    assert business.vertical == "restaurant"
    assert business.settings["vertical_source"] == "derived"
    assert business.settings["derived_classification"]["vertical"] == "restaurant"
    created_roles = [obj for obj in session.added if isinstance(obj, Role)]
    created_role_codes = {role.code for role in created_roles}
    assert {"general_manager", "line_cook", "bartender", "barback"}.issubset(created_role_codes)
    bartender = next(role for role in created_roles if role.code == "bartender")
    assert bartender.metadata_json["derivation"]["support_location_count"] == 1
    assert derivation.classification.vertical == "restaurant"


@pytest.mark.asyncio
async def test_sync_business_role_catalog_applies_high_confidence_llm_refinement(monkeypatch):
    business = _make_business(place_metadata={"primary_type": "coffee_shop", "types": ["cafe", "coffee_shop"]})
    location = _make_location(
        business_id=business.id,
        primary_type="coffee_shop",
        types=["cafe", "coffee_shop", "bakery"],
        hours={"periods": [{"open": {"time": "0600"}}]},
    )
    session = FakeSession()
    session.execute_queue = [*_make_taxonomy_execute_queue(), []]

    async def fake_generate(_session, request):
        assert request.provider == business_classification.llm_gateway.LlmProvider.OPENAI
        assert request.model == "gpt-derive"
        return business_classification.llm_gateway.LlmGenerationResult(
            provider=request.provider or "",
            model=request.model or "",
            tool_calls=[
                business_classification.llm_gateway.LlmToolCall(
                    tool_call_id="call_1",
                    name="submit_business_classification",
                    arguments={
                        "decision": "classify",
                        "vertical_code": "bakery",
                        "subvertical_code": "bakery",
                        "selected_role_codes": ["delivery_coordinator"],
                        "confidence": 0.88,
                        "reason": "Bakery signal is strong and delivery support looks relevant.",
                        "reason_codes": ["llm.vertical.bakery"],
                        "gap_suggestions": [],
                    },
                )
            ],
        )

    async def fake_lookup(*args, **kwargs):
        return uuid4()

    monkeypatch.setattr("app.services.business_classification.llm_gateway.generate", fake_generate)
    monkeypatch.setattr("app.services.business_classification._lookup_llm_generation_id", fake_lookup)
    monkeypatch.setattr(
        business_classification,
        "settings",
        SimpleNamespace(
            business_classification_model="gpt-derive",
            business_classification_mode="primary",
        ),
    )
    monkeypatch.setattr("app.services.business_classification.llm_gateway.provider_is_configured", lambda _provider: True)

    derivation = await role_derivation.sync_business_role_catalog(session, business, locations=[location])

    assert business.vertical == "bakery"
    assert business.settings["derived_classification"]["vertical"] == "bakery"
    assert business.settings["derived_classification"]["llm_candidate"]["applied"] is True
    assert derivation.classification.vertical == "bakery"
    created_roles = [obj for obj in session.added if isinstance(obj, Role)]
    delivery = next(role for role in created_roles if role.code == "delivery_coordinator")
    assert delivery.metadata_json["derivation"]["derivation_type"] == "llm_selected"


@pytest.mark.asyncio
async def test_sync_business_role_catalog_ignores_low_confidence_llm_refinement(monkeypatch):
    business = _make_business(place_metadata={"primary_type": "store", "types": ["store"]})
    location = _make_location(
        business_id=business.id,
        primary_type="store",
        types=["store"],
        hours={},
    )
    session = FakeSession()
    session.execute_queue = [*_make_taxonomy_execute_queue(), []]

    async def fake_generate(_session, request):
        return business_classification.llm_gateway.LlmGenerationResult(
            provider=request.provider or "",
            model=request.model or "",
            tool_calls=[
                business_classification.llm_gateway.LlmToolCall(
                    tool_call_id="call_1",
                    name="submit_business_classification",
                    arguments={
                        "decision": "classify",
                        "vertical_code": "restaurant",
                        "subvertical_code": "full_service_restaurant",
                        "selected_role_codes": ["bartender"],
                        "confidence": 0.42,
                        "reason": "Weak cross-domain guess.",
                        "reason_codes": ["llm.low_confidence"],
                        "gap_suggestions": [],
                    },
                )
            ],
        )

    async def fake_lookup(*args, **kwargs):
        return uuid4()

    monkeypatch.setattr("app.services.business_classification.llm_gateway.generate", fake_generate)
    monkeypatch.setattr("app.services.business_classification._lookup_llm_generation_id", fake_lookup)
    monkeypatch.setattr(
        business_classification,
        "settings",
        SimpleNamespace(
            business_classification_model="gpt-derive",
            business_classification_mode="primary",
        ),
    )
    monkeypatch.setattr("app.services.business_classification.llm_gateway.provider_is_configured", lambda _provider: True)

    derivation = await role_derivation.sync_business_role_catalog(session, business, locations=[location])

    assert business.vertical == "retail"
    assert derivation.classification.vertical == "retail"
    assert business.settings["derived_classification"]["llm_candidate"]["applied"] is False
    created_role_codes = {role.code for role in session.added if isinstance(role, Role)}
    assert "bartender" not in created_role_codes


@pytest.mark.asyncio
async def test_enroll_employee_at_location_creates_location_role_from_employee_assignment():
    session = FakeSession()
    business = _make_business(vertical="retail")
    location = _make_location(business_id=business.id, primary_type="store", types=["store"])
    role = Role(
        id=uuid4(),
        business_id=business.id,
        code="cashier",
        name="Cashier",
        category="front_of_house",
        min_notice_minutes=0,
        coverage_priority=100,
        metadata_json={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.get_map[(Business, business.id)] = business
    session.get_map[(Location, location.id)] = location
    session.get_map[(Role, role.id)] = role
    session.scalar_queue = [None]

    result = await workforce.enroll_employee_at_location(
        session,
        business.id,
        EmployeeEnrollAtLocationCreate(
            location_id=location.id,
            role_ids=[role.id],
            full_name="Jamie Rivera",
            phone_e164="+15555550123",
            email="jamie@example.com",
        ),
    )

    location_roles = [obj for obj in session.added if isinstance(obj, LocationRole)]
    assert result.employee.primary_location_id == location.id
    assert location_roles == []


@pytest.mark.asyncio
async def test_create_shift_requires_explicit_location_role():
    session = FakeSession()
    business = _make_business(vertical="retail")
    location = _make_location(business_id=business.id, primary_type="store", types=["store"])
    role = Role(
        id=uuid4(),
        business_id=business.id,
        code="cashier",
        name="Cashier",
        category="front_of_house",
        min_notice_minutes=0,
        coverage_priority=100,
        metadata_json={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.get_map[(Location, location.id)] = location
    session.get_map[(Role, role.id)] = role
    session.scalar_queue = [None]
    starts_at = datetime.now(timezone.utc)

    with pytest.raises(ValueError, match="location_role_not_enabled"):
        await scheduling.create_shift(
            session,
            business.id,
            ShiftCreate(
                location_id=location.id,
                role_id=role.id,
                source_system="backfill_native",
                timezone="America/Los_Angeles",
                starts_at=starts_at,
                ends_at=starts_at + timedelta(hours=1),
                seats_requested=1,
                requires_manager_approval=False,
                premium_cents=0,
                notes=None,
                shift_metadata={},
            ),
        )

    location_roles = [obj for obj in session.added if isinstance(obj, LocationRole)]
    shifts = [obj for obj in session.added if isinstance(obj, Shift)]
    assert location_roles == []
    assert shifts == []


@pytest.mark.asyncio
async def test_ensure_business_role_merges_source_metadata_without_clobbering_derivation():
    session = FakeSession()
    business = _make_business(vertical="cafe")
    existing_role = Role(
        id=uuid4(),
        business_id=business.id,
        code="barista",
        name="Barista",
        category="front_of_house",
        min_notice_minutes=0,
        coverage_priority=100,
        metadata_json={"derivation": {"source": "places_role_derivation", "confidence": 0.91}},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.scalar_queue = [existing_role]

    role = await businesses.ensure_business_role(
        session,
        business_id=business.id,
        role_name="Barista",
        source="scheduler_sync",
        source_metadata={"role_name": "Barista"},
    )

    assert role is existing_role
    assert role.metadata_json["derivation"]["confidence"] == 0.91
    assert "scheduler_sync" in role.metadata_json["sources"]
    assert role.metadata_json["source_details"]["scheduler_sync"]["role_name"] == "Barista"


@pytest.mark.asyncio
async def test_scheduler_sync_reuses_shared_role_upsert_without_location_role_side_effect():
    session = FakeSession()
    business = _make_business(vertical="retail")
    location = _make_location(business_id=business.id, primary_type="store", types=["store"])
    session.get_map[(Location, location.id)] = location
    session.scalar_queue = [None, None]

    role = await scheduler_sync._get_or_create_role(
        session,
        business_id=business.id,
        location_id=location.id,
        role_name="Cashier",
        cache={},
    )

    created_roles = [obj for obj in session.added if isinstance(obj, Role)]
    created_location_roles = [obj for obj in session.added if isinstance(obj, LocationRole)]
    assert role.code == "cashier"
    assert len(created_roles) == 1
    assert created_roles[0].metadata_json["sources"] == ["scheduler_sync"]
    assert created_roles[0].metadata_json["source_details"]["scheduler_sync"]["role_name"] == "Cashier"
    assert created_location_roles == []


@pytest.mark.asyncio
async def test_retell_open_shift_uses_shared_business_role_upsert(monkeypatch):
    session = FakeSession()
    business = _make_business(vertical="retail")
    location = _make_location(business_id=business.id, primary_type="store", types=["store"])
    session.get_map[(Location, location.id)] = location
    session.scalar_queue = [None]

    async def fake_create_shift(_session, _business_id, payload):
        return Shift(
            id=uuid4(),
            business_id=_business_id,
            location_id=payload.location_id,
            role_id=payload.role_id,
            timezone=payload.timezone,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            status=ShiftStatus.scheduled,
            seats_requested=payload.seats_requested,
            seats_filled=0,
            requires_manager_approval=payload.requires_manager_approval,
            premium_cents=payload.premium_cents,
            notes=payload.notes,
            shift_metadata=payload.shift_metadata,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(retell_workflow.scheduling, "create_shift", fake_create_shift)

    result = await retell_workflow.create_open_shift(
        session,
        {
            "location_id": str(location.id),
            "role": "Cashier",
            "date": "2026-04-04",
            "start_time": "09:00",
            "end_time": "17:00",
        },
    )

    created_roles = [obj for obj in session.added if isinstance(obj, Role)]
    assert result["status"] == "shift_created"
    assert len(created_roles) == 1
    assert created_roles[0].code == "cashier"
    assert created_roles[0].metadata_json["sources"] == ["retell_voice"]
    assert created_roles[0].metadata_json["source_details"]["retell_voice"]["role_name"] == "Cashier"
