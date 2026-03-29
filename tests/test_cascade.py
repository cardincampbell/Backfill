"""Tests for the tiered cascade engine."""
from datetime import datetime, timedelta

import pytest

from app.config import settings
from app.db.queries import (
    get_cascade,
    get_shift,
    get_shift_assignment_with_worker,
    insert_location,
    insert_schedule,
    insert_shift,
    insert_worker,
    list_workers_by_locations_worked,
    list_workers_for_location,
    list_ops_jobs,
    upsert_shift_assignment,
)
from app.services import cascade as cascade_svc
from app.services import ops_queue
from app.services.shift_manager import create_vacancy


async def _seed_location(db):
    return await insert_location(
        db,
        {
            "name": "Taco Spot",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
        },
)


def _shift_payload(location_id: int, start_delta_hours: int, role: str = "line_cook"):
    start = datetime.utcnow() + timedelta(hours=start_delta_hours)
    end = start + timedelta(hours=8)
    return {
        "location_id": location_id,
        "role": role,
        "date": start.date().isoformat(),
        "start_time": start.strftime("%H:%M:%S"),
        "end_time": end.strftime("%H:%M:%S"),
        "pay_rate": 22.0,
        "requirements": ["food_handler_card"],
        "status": "scheduled",
        "source_platform": "backfill_native",
    }


@pytest.mark.asyncio
async def test_cascade_reaches_best_eligible_worker_and_excludes_called_out_worker(db, monkeypatch):
    location_id = await _seed_location(db)
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550101",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    await insert_worker(
        db,
        {
            "name": "Wrong Role",
            "phone": "+13105550102",
            "roles": ["server"],
            "certifications": ["food_handler_card"],
            "priority_rank": 2,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    eligible_id = await insert_worker(
        db,
        {
            "name": "James",
            "phone": "+13105550103",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 3,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    shift_id = await insert_shift(db, _shift_payload(location_id, start_delta_hours=12))

    sent_messages = []
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: sent_messages.append((to, body, metadata)) or "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    result = await cascade_svc.advance(db, cascade["id"])

    assert result["worker_id"] == eligible_id
    assert result["channels"] == ["sms"]
    assert sent_messages[0][0] == "+13105550103"


@pytest.mark.asyncio
async def test_cascade_queues_outreach_delivery_when_ops_worker_enabled(db, monkeypatch):
    monkeypatch.setattr(settings, "backfill_ops_worker_enabled", True)

    location_id = await _seed_location(db)
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550101",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    eligible_id = await insert_worker(
        db,
        {
            "name": "James",
            "phone": "+13105550103",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 3,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    shift_id = await insert_shift(db, _shift_payload(location_id, start_delta_hours=12))

    sent_messages = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: sent_messages.append((to, body, metadata)) or "SM123",
    )

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    result = await cascade_svc.advance(db, cascade["id"])
    queued_jobs = await list_ops_jobs(db, status="queued", job_type="send_outreach_delivery")

    assert result["worker_id"] == eligible_id
    assert result["channels"] == ["sms"]
    assert not sent_messages
    assert len(result["attempt_ids"]) == 1
    assert len(queued_jobs) == 1
    assert queued_jobs[0]["payload_json"]["attempt_id"] == result["attempt_ids"][0]

    processed = await ops_queue.process_due_jobs(db, limit=10)

    assert processed["processed_count"] == 1
    assert sent_messages[0][0] == "+13105550103"


@pytest.mark.asyncio
async def test_urgent_shift_uses_sms_and_voice(db, monkeypatch):
    location_id = await _seed_location(db)
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550101",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    target_id = await insert_worker(
        db,
        {
            "name": "James",
            "phone": "+13105550103",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 2,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
            "preferred_channel": "both",
        },
    )
    shift_id = await insert_shift(db, _shift_payload(location_id, start_delta_hours=1))

    sent_messages = []
    voice_calls = []
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: sent_messages.append((to, body, metadata)) or "SM123")
    async def _fake_call(*, to_number, metadata, agent_id=None):
        voice_calls.append((to_number, metadata))
        return "CA123"
    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    result = await cascade_svc.advance(db, cascade["id"])

    assert result["worker_id"] == target_id
    assert result["channels"] == ["sms", "voice"]
    assert sent_messages and voice_calls


@pytest.mark.asyncio
async def test_active_worker_query_includes_voice_only_consented_workers(db):
    location_id = await _seed_location(db)
    voice_only_id = await insert_worker(
        db,
        {
            "name": "Voice Only",
            "phone": "+13105550107",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "pending",
            "voice_consent_status": "granted",
        },
    )
    await insert_worker(
        db,
        {
            "name": "No Consent",
            "phone": "+13105550108",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 2,
            "location_id": location_id,
            "sms_consent_status": "pending",
            "voice_consent_status": "pending",
        },
    )

    workers = await list_workers_for_location(db, location_id, active_consent_only=True)

    assert [worker["id"] for worker in workers] == [voice_only_id]


@pytest.mark.asyncio
async def test_schedule_assignment_writeback_tracks_vacancy_and_fill(db, monkeypatch):
    location_id = await _seed_location(db)
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550101",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    replacement_id = await insert_worker(
        db,
        {
            "name": "James",
            "phone": "+13105550103",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 2,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": "2026-04-13",
            "week_end_date": "2026-04-19",
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            **_shift_payload(location_id, start_delta_hours=12),
            "schedule_id": schedule_id,
            "published_state": "published",
        },
    )
    await upsert_shift_assignment(
        db,
        {
            "shift_id": shift_id,
            "worker_id": caller_id,
            "assignment_status": "assigned",
            "source": "manual",
        },
    )

    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    assignment_after_callout = await get_shift_assignment_with_worker(db, shift_id)
    shift_after_callout = await get_shift(db, shift_id)

    assert assignment_after_callout is not None
    assert assignment_after_callout["worker_id"] is None
    assert assignment_after_callout["assignment_status"] == "open"
    assert shift_after_callout["status"] == "vacant"
    assert shift_after_callout["called_out_by"] == caller_id

    await cascade_svc.advance(db, cascade["id"])
    claim = await cascade_svc.claim_shift(db, cascade["id"], replacement_id, summary="Accepted by SMS")

    assignment_after_fill = await get_shift_assignment_with_worker(db, shift_id)
    shift_after_fill = await get_shift(db, shift_id)

    assert claim["status"] == "confirmed"
    assert assignment_after_fill is not None
    assert assignment_after_fill["worker_id"] == replacement_id
    assert assignment_after_fill["worker_name"] == "James"
    assert assignment_after_fill["assignment_status"] == "confirmed"
    assert shift_after_fill["status"] == "filled"
    assert shift_after_fill["filled_by"] == replacement_id


@pytest.mark.asyncio
async def test_claim_can_wait_for_manager_approval_before_fill(db, monkeypatch):
    from app.services import backfill_shifts as backfill_shifts_svc

    manager_sms = []
    worker_notifications = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: (
            manager_sms.append((to, body))
            if to == "+13105550100"
            else worker_notifications.append((to, body))
        ) or "SM-NOTIFY",
    )
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    location_id = await insert_location(
        db,
        {
            "name": "Approval Taco",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
            "coverage_requires_manager_approval": True,
        },
    )
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550101",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    replacement_id = await insert_worker(
        db,
        {
            "name": "James",
            "phone": "+13105550103",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 2,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": "2026-04-13",
            "week_end_date": "2026-04-19",
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            **_shift_payload(location_id, start_delta_hours=12),
            "schedule_id": schedule_id,
            "published_state": "published",
        },
    )
    await upsert_shift_assignment(
        db,
        {
            "shift_id": shift_id,
            "worker_id": caller_id,
            "assignment_status": "assigned",
            "source": "manual",
        },
    )

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    await cascade_svc.advance(db, cascade["id"])

    claim = await cascade_svc.claim_shift(db, cascade["id"], replacement_id, summary="Accepted by SMS")
    shift_after_claim = await get_shift(db, shift_id)
    assignment_after_claim = await get_shift_assignment_with_worker(db, shift_id)
    cascade_after_claim = await get_cascade(db, cascade["id"])
    schedule_view_after_claim = await backfill_shifts_svc.get_schedule_view(
        db,
        location_id=location_id,
        week_start="2026-04-13",
    )

    assert claim["status"] == "awaiting_manager_approval"
    assert shift_after_claim["status"] == "vacant"
    assert shift_after_claim["filled_by"] is None
    assert assignment_after_claim["worker_id"] is None
    assert assignment_after_claim["assignment_status"] == "open"
    assert cascade_after_claim["pending_claim_worker_id"] == replacement_id
    assert cascade_after_claim["confirmed_worker_id"] is None
    assert schedule_view_after_claim["shifts"][0]["coverage"]["status"] == "awaiting_manager_approval"
    assert schedule_view_after_claim["shifts"][0]["coverage"]["manager_action_required"] is True
    assert schedule_view_after_claim["shifts"][0]["coverage"]["pending_action"] == "approve_fill"
    assert schedule_view_after_claim["shifts"][0]["coverage"]["claimed_by_worker_id"] == replacement_id
    assert schedule_view_after_claim["shifts"][0]["coverage"]["claimed_by_worker_name"] == "James"
    assert schedule_view_after_claim["summary"]["action_required_count"] == 1
    assert schedule_view_after_claim["summary"]["critical_count"] == 1
    assert schedule_view_after_claim["exceptions"][0] == {
        "exception_id": f"coverage_fill_approval_required:{shift_id}",
        "type": "coverage",
        "code": "coverage_fill_approval_required",
        "severity": "critical",
        "action_required": True,
        "available_actions": ["approve_fill", "decline_fill"],
        "shift_id": shift_id,
        "role": shift_after_claim["role"],
        "date": shift_after_claim["date"],
        "start_time": shift_after_claim["start_time"],
        "message": "James is waiting for manager approval to cover this shift.",
        "current_status": "vacant",
        "assignment_status": "open",
        "cascade_id": cascade["id"],
        "pending_action": "approve_fill",
        "coverage_status": "awaiting_manager_approval",
        "vacancy_kind": "callout",
        "attendance_status": "not_applicable",
        "worker_id": None,
        "worker_name": None,
        "claimed_by_worker_id": replacement_id,
        "claimed_by_worker_name": "James",
        "late_eta_minutes": None,
    }
    assert manager_sms and "reply yes to approve or no to keep looking" in manager_sms[0][1].lower()

    approval = await cascade_svc.approve_pending_claim(db, cascade["id"])
    shift_after_approval = await get_shift(db, shift_id)
    assignment_after_approval = await get_shift_assignment_with_worker(db, shift_id)
    cascade_after_approval = await get_cascade(db, cascade["id"])

    assert approval["status"] == "confirmed"
    assert shift_after_approval["status"] == "filled"
    assert shift_after_approval["filled_by"] == replacement_id
    assert assignment_after_approval["worker_id"] == replacement_id
    assert assignment_after_approval["assignment_status"] == "confirmed"
    assert cascade_after_approval["pending_claim_worker_id"] is None
    assert cascade_after_approval["confirmed_worker_id"] == replacement_id
    assert worker_notifications and "you're confirmed" in worker_notifications[0][1].lower()


@pytest.mark.asyncio
async def test_broadcast_claim_confirms_first_yes_and_puts_second_yes_on_standby(db, monkeypatch):
    location_id = await _seed_location(db)
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550101",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    first_yes_id = await insert_worker(
        db,
        {
            "name": "James",
            "phone": "+13105550103",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 2,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    second_yes_id = await insert_worker(
        db,
        {
            "name": "Devon",
            "phone": "+13105550104",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 3,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    shift_id = await insert_shift(db, _shift_payload(location_id, start_delta_hours=1))

    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")

    async def _fake_call(*, to_number, metadata, agent_id=None):
        return "CA123"

    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    result = await cascade_svc.advance(db, cascade["id"])

    assert result["mode"] == "broadcast"
    assert set(result["worker_ids"]) == {first_yes_id, second_yes_id}

    confirmed = await cascade_svc.claim_shift(db, cascade["id"], first_yes_id, summary="Accepted by SMS")
    standby = await cascade_svc.claim_shift(db, cascade["id"], second_yes_id, summary="Accepted a moment later")

    updated_cascade = await get_cascade(db, cascade["id"])
    shift = await get_shift(db, shift_id)

    assert confirmed["status"] == "confirmed"
    assert standby["status"] == "standby"
    assert standby["standby_position"] == 1
    assert updated_cascade["confirmed_worker_id"] == first_yes_id
    assert updated_cascade["standby_queue"] == [second_yes_id]
    assert shift["status"] == "filled"
    assert shift["filled_by"] == first_yes_id


@pytest.mark.asyncio
async def test_broadcast_claim_uses_db_reservation_when_reads_are_stale(db, monkeypatch):
    location_id = await _seed_location(db)
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550101",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    first_yes_id = await insert_worker(
        db,
        {
            "name": "James",
            "phone": "+13105550103",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 2,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    second_yes_id = await insert_worker(
        db,
        {
            "name": "Devon",
            "phone": "+13105550104",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 3,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    shift_id = await insert_shift(db, _shift_payload(location_id, start_delta_hours=1))

    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")

    async def _fake_call(*, to_number, metadata, agent_id=None):
        return "CA123"

    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    await cascade_svc.advance(db, cascade["id"])

    stale_cascade = dict(await get_cascade(db, cascade["id"]))
    stale_shift = dict(await get_shift(db, shift_id))
    original_get_cascade = cascade_svc.get_cascade
    original_get_shift = cascade_svc.get_shift
    cascade_calls = {"count": 0}
    shift_calls = {"count": 0}

    async def _stale_then_real_cascade(db_conn, cascade_id):
        cascade_calls["count"] += 1
        if cascade_calls["count"] <= 2:
            return dict(stale_cascade)
        return await original_get_cascade(db_conn, cascade_id)

    async def _stale_then_real_shift(db_conn, current_shift_id):
        shift_calls["count"] += 1
        if shift_calls["count"] <= 2:
            return dict(stale_shift)
        return await original_get_shift(db_conn, current_shift_id)

    monkeypatch.setattr("app.services.cascade.get_cascade", _stale_then_real_cascade)
    monkeypatch.setattr("app.services.cascade.get_shift", _stale_then_real_shift)

    confirmed = await cascade_svc.claim_shift(db, cascade["id"], first_yes_id, summary="First yes")
    standby = await cascade_svc.claim_shift(db, cascade["id"], second_yes_id, summary="Second yes")

    updated_cascade = await original_get_cascade(db, cascade["id"])
    shift = await original_get_shift(db, shift_id)

    assert confirmed["status"] == "confirmed"
    assert standby["status"] == "standby"
    assert updated_cascade["confirmed_worker_id"] == first_yes_id
    assert updated_cascade["standby_queue"] == [second_yes_id]
    assert shift["filled_by"] == first_yes_id


@pytest.mark.asyncio
async def test_cancel_standby_removes_worker_from_queue(db, monkeypatch):
    location_id = await _seed_location(db)
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550101",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    confirmed_id = await insert_worker(
        db,
        {
            "name": "James",
            "phone": "+13105550103",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 2,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    standby_id = await insert_worker(
        db,
        {
            "name": "Devon",
            "phone": "+13105550104",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 3,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    shift_id = await insert_shift(db, _shift_payload(location_id, start_delta_hours=1))

    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")

    async def _fake_call(*, to_number, metadata, agent_id=None):
        return "CA123"

    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    await cascade_svc.advance(db, cascade["id"])
    await cascade_svc.claim_shift(db, cascade["id"], confirmed_id, summary="Confirmed")
    await cascade_svc.claim_shift(db, cascade["id"], standby_id, summary="Standby")

    result = await cascade_svc.cancel_standby(db, cascade["id"], standby_id, summary="Cancelled")
    updated_cascade = await get_cascade(db, cascade["id"])

    assert result["status"] == "standby_cancelled"
    assert updated_cascade["standby_queue"] == []


@pytest.mark.asyncio
async def test_cascade_exhausted_when_no_eligible_workers_and_manager_notified(db, monkeypatch):
    location_id = await _seed_location(db)
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550101",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    shift_id = await insert_shift(db, _shift_payload(location_id, start_delta_hours=8))

    notifications = []
    def _fake_exhausted(**kwargs):
        notifications.append(kwargs)
        return "SM999"
    monkeypatch.setattr("app.services.notifications.notify_cascade_exhausted", _fake_exhausted)

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    result = await cascade_svc.advance(db, cascade["id"])
    updated = await get_cascade(db, cascade["id"])

    assert result["status"] == "exhausted"
    assert updated["status"] == "exhausted"
    assert notifications


@pytest.mark.asyncio
async def test_record_acceptance_marks_shift_filled(db, monkeypatch):
    location_id = await _seed_location(db)
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550101",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    target_id = await insert_worker(
        db,
        {
            "name": "James",
            "phone": "+13105550103",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 2,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    shift_id = await insert_shift(db, _shift_payload(location_id, start_delta_hours=8))

    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    await cascade_svc.advance(db, cascade["id"])
    await cascade_svc.record_response(db, cascade["id"], target_id, accepted=True, summary="Accepted")

    shift = await get_shift(db, shift_id)
    assert shift["status"] == "filled"
    assert shift["filled_by"] == target_id
    assert shift["fill_tier"] == "tier1_internal"


@pytest.mark.asyncio
async def test_create_vacancy_is_idempotent(db):
    location_id = await _seed_location(db)
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550101",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    shift_id = await insert_shift(db, _shift_payload(location_id, start_delta_hours=8))

    cascade_one = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    cascade_two = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")

    assert cascade_one["id"] == cascade_two["id"]


@pytest.mark.asyncio
async def test_tier2_alumni_is_used_after_tier1_exhausts(db, monkeypatch):
    location_id = await _seed_location(db)
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550101",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    alumni_id = await insert_worker(
        db,
        {
            "name": "Devon",
            "phone": "+13105550105",
            "worker_type": "alumni",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 10,
            "location_id": location_id,
            "locations_worked": [location_id],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
            "show_up_rate": 0.99,
            "acceptance_rate": 0.8,
            "response_rate": 0.9,
            "rating": 4.9,
            "total_shifts_filled": 7,
        },
    )
    shift_id = await insert_shift(db, _shift_payload(location_id, start_delta_hours=12))

    sent_messages = []
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: sent_messages.append((to, body, metadata)) or "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    result = await cascade_svc.advance(db, cascade["id"])
    updated = await get_cascade(db, cascade["id"])

    assert result["worker_id"] == alumni_id
    assert updated["current_tier"] == 2
    assert result["channels"] == ["sms"]


@pytest.mark.asyncio
async def test_tier2_acceptance_marks_shift_filled_as_alumni(db, monkeypatch):
    location_id = await _seed_location(db)
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550101",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    alumni_id = await insert_worker(
        db,
        {
            "name": "Devon",
            "phone": "+13105550105",
            "worker_type": "alumni",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 10,
            "location_id": location_id,
            "locations_worked": [location_id],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
            "show_up_rate": 0.99,
        },
    )
    shift_id = await insert_shift(db, _shift_payload(location_id, start_delta_hours=12))

    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    await cascade_svc.advance(db, cascade["id"])
    await cascade_svc.record_response(db, cascade["id"], alumni_id, accepted=True, summary="Accepted")

    shift = await get_shift(db, shift_id)
    assert shift["status"] == "filled"
    assert shift["filled_by"] == alumni_id
    assert shift["fill_tier"] == "tier2_alumni"


@pytest.mark.asyncio
async def test_worker_selection_excludes_inactive_and_terminated_workers(db):
    location_id = await _seed_location(db)
    await insert_worker(
        db,
        {
            "name": "Active Worker",
            "phone": "+13105550901",
            "roles": ["line_cook"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
            "employment_status": "active",
        },
    )
    await insert_worker(
        db,
        {
            "name": "Inactive Worker",
            "phone": "+13105550902",
            "roles": ["line_cook"],
            "priority_rank": 2,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
            "employment_status": "inactive",
        },
    )
    await insert_worker(
        db,
        {
            "name": "Terminated Alumni",
            "phone": "+13105550903",
            "worker_type": "alumni",
            "roles": ["line_cook"],
            "priority_rank": 3,
            "location_id": location_id,
            "locations_worked": [location_id],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
            "employment_status": "terminated",
        },
    )

    current_workers = await list_workers_for_location(db, location_id, active_consent_only=True)
    alumni_workers = await list_workers_by_locations_worked(db, location_id)

    assert [worker["name"] for worker in current_workers] == ["Active Worker"]
    assert [worker["name"] for worker in alumni_workers] == ["Active Worker"]
