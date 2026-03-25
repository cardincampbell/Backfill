"""Tests for caller lookup service."""
import pytest

from app.db.queries import insert_restaurant, insert_worker
from app.services.caller_lookup import lookup


@pytest.mark.asyncio
async def test_lookup_known_worker(db):
    worker_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550101",
            "roles": ["line_cook"],
            "restaurant_id": None,
        },
    )

    result = await lookup(db, "+13105550101")

    assert result["found"] is True
    assert result["caller_type"] == "worker"
    assert result["record"]["id"] == worker_id


@pytest.mark.asyncio
async def test_lookup_known_manager(db):
    restaurant_id = await insert_restaurant(
        db,
        {
            "name": "Taco Spot",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
        },
    )

    result = await lookup(db, "+13105550100")

    assert result["found"] is True
    assert result["caller_type"] == "manager"
    assert result["record"]["id"] == restaurant_id


@pytest.mark.asyncio
async def test_lookup_unknown(db):
    result = await lookup(db, "+13105550999")

    assert result == {
        "found": False,
        "caller_type": "unknown",
        "record": None,
    }
