from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.db import queries
from app.db.queries import insert_restaurant, insert_shift, insert_worker
from app.services import scheduling, sync_engine
from app.services.shift_manager import mark_filled


def _external_shift_payload(restaurant_id: int, start_delta_hours: int = 2):
    start = datetime.utcnow() + timedelta(hours=start_delta_hours)
    end = start + timedelta(hours=8)
    return {
        "restaurant_id": restaurant_id,
        "scheduling_platform_id": f"shift-{restaurant_id}-{start_delta_hours}",
        "role": "line_cook",
        "date": start.date().isoformat(),
        "start_time": start.strftime("%H:%M:%S"),
        "end_time": end.strftime("%H:%M:%S"),
        "pay_rate": 22.0,
        "requirements": ["food_handler_card"],
        "status": "scheduled",
        "source_platform": "7shifts",
    }


@pytest.mark.asyncio
async def test_mark_filled_enqueues_writeback_for_opted_in_location(db):
    restaurant_id = await insert_restaurant(
        db,
        {
            "name": "Queue Grill",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "7shifts",
            "scheduling_platform_id": "company-123",
            "writeback_enabled": True,
            "writeback_subscription_tier": "premium",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "James",
            "phone": "+13105550103",
            "source_id": "worker-7shifts-1",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "restaurant_id": restaurant_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    shift_id = await insert_shift(db, _external_shift_payload(restaurant_id, start_delta_hours=2))

    await mark_filled(db, shift_id=shift_id, filled_by_worker_id=worker_id, fill_tier="tier1")

    jobs = await queries.list_sync_jobs(db, restaurant_id=restaurant_id, limit=10)
    writeback_jobs = [job for job in jobs if job["job_type"] == "writeback"]
    assert len(writeback_jobs) == 1
    assert writeback_jobs[0]["status"] == "queued"
    assert writeback_jobs[0]["scope_ref"] == str(shift_id)


@pytest.mark.asyncio
async def test_process_writeback_job_records_last_writeback_stamp(db, monkeypatch):
    restaurant_id = await insert_restaurant(
        db,
        {
            "name": "Writeback Grill",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "7shifts",
            "scheduling_platform_id": "company-456",
            "writeback_enabled": True,
            "writeback_subscription_tier": "premium",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Devon",
            "phone": "+13105550104",
            "source_id": "worker-7shifts-2",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "restaurant_id": restaurant_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    shift_id = await insert_shift(db, _external_shift_payload(restaurant_id, start_delta_hours=1))
    await queries.update_shift(
        db,
        shift_id,
        {"status": "filled", "filled_by": worker_id, "fill_tier": "tier1"},
    )

    async def _fake_push_fill_update(conn, sid):
        assert conn is db
        assert sid == shift_id
        return {"status": "ok", "platform": "7shifts", "shift_id": sid}

    monkeypatch.setattr(scheduling, "push_fill_update", _fake_push_fill_update)

    job = await sync_engine.enqueue_writeback(db, shift_id=shift_id)
    result = await sync_engine.process_sync_job(db, int(job["id"]))
    restaurant = await queries.get_restaurant(db, restaurant_id)

    assert result["status"] == "completed"
    assert restaurant is not None
    assert restaurant["last_writeback_at"] is not None


@pytest.mark.asyncio
async def test_queue_rolling_and_daily_due_restaurants_respects_cadence_and_windows(db):
    now = datetime.utcnow()

    suppressed_restaurant = await insert_restaurant(
        db,
        {
            "name": "Fresh Event Grill",
            "scheduling_platform": "7shifts",
            "scheduling_platform_id": "company-fresh",
            "integration_state": "healthy",
            "last_event_sync_at": now.isoformat(),
        },
    )
    due_restaurant = await insert_restaurant(
        db,
        {
            "name": "Stale Grill",
            "scheduling_platform": "deputy",
            "scheduling_platform_id": "install-stale",
            "integration_state": "healthy",
            "last_rolling_sync_at": (now - timedelta(hours=2)).isoformat(),
            "last_daily_sync_at": (now - timedelta(days=2)).isoformat(),
        },
    )

    rolling_jobs = await sync_engine.enqueue_rolling_reconcile_for_due_restaurants(db, now=now)
    daily_jobs = await sync_engine.enqueue_daily_reconcile_for_due_restaurants(db, for_date=date.today())

    assert [job["restaurant_id"] for job in rolling_jobs] == [due_restaurant]
    assert {job["restaurant_id"] for job in daily_jobs} == {suppressed_restaurant, due_restaurant}

    rolling_job = rolling_jobs[0]
    assert rolling_job["window_start"] == (now - timedelta(days=1)).date().isoformat()
    assert rolling_job["window_end"] == (now + timedelta(days=2)).date().isoformat()

    daily_due = [job for job in daily_jobs if job["restaurant_id"] == due_restaurant][0]
    assert daily_due["window_start"] == (date.today() - timedelta(days=1)).isoformat()
    assert daily_due["window_end"] == (date.today() + timedelta(days=14)).isoformat()
