from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.business import Business, Location, Role
from app.models.common import ShiftLifecycleStatus, ShiftStaffingStatus
from app.models.scheduling import Shift
from app.services import shift_shaping


def _make_business() -> Business:
    now = datetime.now(timezone.utc)
    return Business(
        id=uuid4(),
        name="Backfill Cafe",
        display_name="Backfill Cafe",
        slug="backfill-cafe",
        timezone="America/Los_Angeles",
        settings={},
        place_metadata={},
        created_at=now,
        updated_at=now,
    )


def _make_location(*, business_id):
    now = datetime.now(timezone.utc)
    return Location(
        id=uuid4(),
        business_id=business_id,
        name="Pasadena",
        display_name="Pasadena",
        slug="pasadena",
        locality="Pasadena",
        region="CA",
        country_code="US",
        timezone="America/Los_Angeles",
        google_place_metadata={},
        settings={},
        created_at=now,
        updated_at=now,
    )


def _make_role(*, business_id):
    now = datetime.now(timezone.utc)
    return Role(
        id=uuid4(),
        business_id=business_id,
        code="server",
        name="Server",
        coverage_priority=100,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )


def _make_shift(*, business_id, location_id, role_id, starts_at: datetime, ends_at: datetime) -> Shift:
    now = datetime.now(timezone.utc)
    return Shift(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        timezone="America/Los_Angeles",
        starts_at=starts_at,
        ends_at=ends_at,
        lifecycle_status=ShiftLifecycleStatus.draft,
        staffing_status=ShiftStaffingStatus.open,
        seats_requested=1,
        seats_filled=0,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_generate_pattern_based_demand_nets_existing_draft_headcount(monkeypatch):
    business = _make_business()
    location = _make_location(business_id=business.id)
    role = _make_role(business_id=business.id)

    historical_shifts = [
        _make_shift(
            business_id=business.id,
            location_id=location.id,
            role_id=role.id,
            starts_at=datetime(2026, 4, 6, 16, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 6, 22, 0, tzinfo=timezone.utc),
        ),
        _make_shift(
            business_id=business.id,
            location_id=location.id,
            role_id=role.id,
            starts_at=datetime(2026, 4, 6, 16, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 6, 22, 0, tzinfo=timezone.utc),
        ),
        _make_shift(
            business_id=business.id,
            location_id=location.id,
            role_id=role.id,
            starts_at=datetime(2026, 4, 13, 16, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 13, 22, 0, tzinfo=timezone.utc),
        ),
        _make_shift(
            business_id=business.id,
            location_id=location.id,
            role_id=role.id,
            starts_at=datetime(2026, 4, 13, 16, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 13, 22, 0, tzinfo=timezone.utc),
        ),
    ]
    current_shifts = [
        _make_shift(
            business_id=business.id,
            location_id=location.id,
            role_id=role.id,
            starts_at=datetime(2026, 4, 20, 16, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 20, 22, 0, tzinfo=timezone.utc),
        )
    ]

    async def fake_load_history(*_args, **_kwargs):
        return historical_shifts

    monkeypatch.setattr(shift_shaping, "_load_historical_pattern_shifts", fake_load_history)

    payload = await shift_shaping.generate_pattern_based_demand(
        object(),
        business=business,
        location=location,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        current_shifts=current_shifts,
    )

    assert len(payload.proposed_shifts) == 1
    proposed_shift = payload.proposed_shifts[0]
    assert proposed_shift.source_type == "historical_pattern"
    assert proposed_shift.demand_key.endswith(":seat:2")
    assert proposed_shift.generation_payload["target_headcount"] == 2
    assert proposed_shift.generation_payload["existing_draft_headcount"] == 1
    assert payload.metadata["generated_shift_count"] == 1
    assert payload.metadata["preserved_draft_headcount"] == 1


@pytest.mark.asyncio
async def test_generate_pattern_based_demand_returns_empty_when_no_history(monkeypatch):
    business = _make_business()
    location = _make_location(business_id=business.id)

    async def fake_load_history(*_args, **_kwargs):
        return []

    monkeypatch.setattr(shift_shaping, "_load_historical_pattern_shifts", fake_load_history)

    payload = await shift_shaping.generate_pattern_based_demand(
        object(),
        business=business,
        location=location,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        current_shifts=[],
    )

    assert payload.proposed_shifts == []
    assert payload.metadata["status"] == "no_historical_pattern_data"
