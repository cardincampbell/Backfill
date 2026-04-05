from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.business import Business, Location, LocationRole, Role
from app.models.common import ShiftStatus
from app.models.scheduling import Shift
from app.schemas.scheduling import ShiftCreate
from app.schemas.workforce import EmployeeEnrollAtLocationCreate
from app.services import businesses, retell_workflow, role_derivation, scheduler_sync, scheduling, workforce


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
        legal_name="Backfill Test LLC",
        brand_name="Backfill Test",
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


def test_derive_business_catalog_builds_business_level_role_pack():
    business_id = uuid4()
    cafe_location = _make_location(
        business_id=business_id,
        primary_type="coffee_shop",
        types=["cafe", "coffee_shop", "bakery"],
        hours={"periods": [{"open": {"time": "0600"}}]},
    )
    result = role_derivation.derive_business_catalog(
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
    session.execute_queue = [[]]

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
    assert result.employee.home_location_id == location.id
    assert len(location_roles) == 1
    assert location_roles[0].location_id == location.id
    assert location_roles[0].role_id == role.id
    assert location_roles[0].coverage_settings["source"] == "employee_enrollment"


@pytest.mark.asyncio
async def test_create_shift_creates_location_role_from_shift_usage():
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
    session.scalar_queue = [None, None]
    starts_at = datetime.now(timezone.utc)

    shift = await scheduling.create_shift(
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
    assert shift.location_id == location.id
    assert len(location_roles) == 1
    assert location_roles[0].coverage_settings["source"] == "shift_usage"
    assert len(shifts) == 1


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
async def test_scheduler_sync_reuses_shared_role_upsert_and_location_role():
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
    assert len(created_location_roles) == 1
    assert created_location_roles[0].coverage_settings["source"] == "scheduler_sync"


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
