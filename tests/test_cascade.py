"""Tests for the tiered cascade engine."""
from datetime import datetime, timedelta

import pytest

from app.db.queries import (
    get_cascade,
    get_shift,
    insert_location,
    insert_shift,
    insert_worker,
)
from app.services import cascade as cascade_svc
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
