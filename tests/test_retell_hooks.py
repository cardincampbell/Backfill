from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.config import settings
from app.db.queries import (
    get_active_cascade_for_shift,
    get_cascade,
    get_onboarding_session_by_source_external_id,
    get_organization_by_name,
    get_schedule,
    get_shift,
    get_shift_status,
    insert_location,
    insert_schedule,
    insert_shift,
    insert_worker,
    list_shifts,
    get_shift_assignment,
    upsert_shift_assignment,
)
from app.services import cascade as cascade_svc
from app.services.shift_manager import create_vacancy


@pytest.mark.asyncio
async def test_retell_claim_shift_function_call_confirms_and_notifies(db, client, monkeypatch):
    notifications = []

    async def _fake_notify(db_conn, cascade_id, worker_id, filled=True):
        notifications.append((cascade_id, worker_id, filled))

    monkeypatch.setattr("app.services.notifications.fire_manager_notification", _fake_notify)

    location_id = await insert_location(
        db,
        {
            "name": "Retell Grill",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
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
    start = datetime.utcnow() + timedelta(hours=12)
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "role": "line_cook",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 22.0,
            "requirements": ["food_handler_card"],
            "status": "scheduled",
            "source_platform": "backfill_native",
        },
    )

    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    await cascade_svc.advance(db, cascade["id"])

    response = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "claim_shift",
            "args": {
                "cascade_id": cascade["id"],
                "worker_id": target_id,
                "conversation_summary": "Accepted over call",
            },
        },
    )

    shift = await get_shift(db, shift_id)
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    assert shift["filled_by"] == target_id
    assert notifications == [(cascade["id"], target_id, True)]


@pytest.mark.asyncio
async def test_retell_promote_standby_function_call_confirms_next_worker(db, client, monkeypatch):
    notifications = []

    async def _fake_notify(db_conn, cascade_id, worker_id, filled=True):
        notifications.append((cascade_id, worker_id, filled))

    monkeypatch.setattr("app.services.notifications.fire_manager_notification", _fake_notify)
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")

    async def _fake_call(*, to_number, metadata, agent_id=None):
        return "CA123"

    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)

    location_id = await insert_location(
        db,
        {
            "name": "Retell Standby Grill",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
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
    start = datetime.utcnow() + timedelta(hours=1)
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "role": "line_cook",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 22.0,
            "requirements": ["food_handler_card"],
            "status": "scheduled",
            "source_platform": "backfill_native",
        },
    )

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    await cascade_svc.advance(db, cascade["id"])
    await cascade_svc.claim_shift(db, cascade["id"], confirmed_id, summary="Confirmed")
    await cascade_svc.claim_shift(db, cascade["id"], standby_id, summary="Standby")

    await db.execute("UPDATE shifts SET filled_by=NULL, status='vacant' WHERE id=?", (shift_id,))
    await db.execute(
        "UPDATE cascades SET confirmed_worker_id=NULL, status='active' WHERE id=?",
        (cascade["id"],),
    )
    await db.commit()

    response = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "promote_standby",
            "args": {
                "cascade_id": cascade["id"],
                "worker_id": standby_id,
                "conversation_summary": "Original worker cancelled",
            },
        },
    )

    shift = await get_shift(db, shift_id)
    updated_cascade = await get_cascade(db, cascade["id"])
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    assert shift["filled_by"] == standby_id
    assert updated_cascade["confirmed_worker_id"] == standby_id
    assert notifications[-1] == (cascade["id"], standby_id, True)


def test_retell_send_onboarding_link_function_call_returns_expected_path(client, monkeypatch):
    sent = []
    monkeypatch.setattr("app.services.onboarding.send_sms", lambda to, body: sent.append((to, body)) or "SM123")
    location = client.post(
        "/api/locations",
        json={
            "name": "Retell Onboarding Location",
            "manager_name": "Sam Lead",
            "manager_phone": "+13105550100",
            "scheduling_platform": "homebase",
        },
    ).json()

    response = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "send_onboarding_link",
            "args": {
                "phone": "+13105550100",
                "kind": "integration",
                "location_id": location["id"],
                "platform": "Homebase",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["platform"] == "homebase"
    assert payload["path"].startswith(f"/setup/connect?location_id={location['id']}")
    assert "setup_token=bfsetup_" in payload["path"]
    assert sent


def test_retell_rejects_stale_restaurant_args_for_get_open_shifts(client):
    response = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "get_open_shifts",
            "args": {
                "restaurant_id": 123,
            },
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["detail"]["message"] == "Invalid args for get_open_shifts"
    assert payload["detail"]["errors"][0]["type"] == "extra_forbidden"


def test_retell_rejects_missing_location_id_for_create_open_shift(client):
    response = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "create_open_shift",
            "args": {
                "role": "line_cook",
                "date": "2026-03-26",
                "start_time": "09:00:00",
                "end_time": "17:00:00",
                "pay_rate": 22.0,
            },
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["detail"]["message"] == "Invalid args for create_open_shift"
    assert payload["detail"]["errors"][0]["type"] == "missing"


@pytest.mark.asyncio
async def test_retell_ai_manager_action_can_publish_after_confirmation(db, client, monkeypatch):
    monkeypatch.setattr("app.services.notifications.send_sms", lambda to, body: "SM-NOTIFY")

    location_id = await insert_location(
        db,
        {
            "name": "Retell AI Publish Cafe",
            "manager_name": "Chef Nina",
            "manager_phone": "+13105550130",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Sam Cook",
            "phone": "+13105550131",
            "roles": ["prep_cook"],
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
            "lifecycle_state": "draft",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "prep_cook",
            "date": "2026-04-14",
            "start_time": "08:00:00",
            "end_time": "16:00:00",
            "pay_rate": 22.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "draft",
        },
    )
    await upsert_shift_assignment(
        db,
        {
            "shift_id": shift_id,
            "worker_id": worker_id,
            "assignment_status": "assigned",
            "source": "manual",
        },
    )

    action = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "ai_manager_action",
            "args": {
                "phone": "+13105550130",
                "text": "publish next week",
                "location_id": location_id,
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
            },
        },
    )
    assert action.status_code == 200
    action_payload = action.json()
    assert action_payload["status"] == "awaiting_confirmation"
    assert action_payload["mode"] == "confirmation"
    assert "publish" in action_payload["summary"].lower()
    assert action_payload["action_request_id"] > 0

    confirmed = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "confirm_ai_action",
            "args": {
                "location_id": location_id,
                "action_request_id": action_payload["action_request_id"],
            },
        },
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "published the schedule" in confirmed_payload["summary"].lower()

    schedule = await get_schedule(db, schedule_id)
    assert schedule is not None
    assert schedule["lifecycle_state"] == "published"


@pytest.mark.asyncio
async def test_retell_ai_manager_action_can_clarify_open_shift_choice(db, client, monkeypatch):
    monkeypatch.setattr("app.services.notifications.send_sms", lambda to, body: "SM-NOTIFY")
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    location_id = await insert_location(
        db,
        {
            "name": "Retell AI Clarify Cafe",
            "manager_name": "Chef Nina",
            "manager_phone": "+13105550132",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    await insert_worker(
        db,
        {
            "name": "Jordan",
            "phone": "+13105550133",
            "roles": ["dishwasher"],
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
            "lifecycle_state": "draft",
            "created_by": "test",
        },
    )
    first_shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
        },
    )
    second_shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "dishwasher",
            "date": "2026-04-16",
            "start_time": "15:00:00",
            "end_time": "23:00:00",
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
        },
    )
    await upsert_shift_assignment(
        db,
        {
            "shift_id": first_shift_id,
            "worker_id": None,
            "assignment_status": "open",
            "source": "manual",
        },
    )
    await upsert_shift_assignment(
        db,
        {
            "shift_id": second_shift_id,
            "worker_id": None,
            "assignment_status": "open",
            "source": "manual",
        },
    )

    action = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "ai_manager_action",
            "args": {
                "phone": "+13105550132",
                "text": "start coverage for the open shift",
                "location_id": location_id,
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
            },
        },
    )
    assert action.status_code == 200
    action_payload = action.json()
    assert action_payload["status"] == "awaiting_clarification"
    assert action_payload["mode"] == "clarification"
    assert len(action_payload["options"]) == 2

    clarified = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "clarify_ai_action",
            "args": {
                "location_id": location_id,
                "action_request_id": action_payload["action_request_id"],
                "selection": {"shift_id": second_shift_id},
            },
        },
    )
    assert clarified.status_code == 200
    clarified_payload = clarified.json()
    assert clarified_payload["status"] == "awaiting_confirmation"
    assert "15:00" in clarified_payload["summary"]

    confirmed = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "confirm_ai_action",
            "args": {
                "location_id": location_id,
                "action_request_id": action_payload["action_request_id"],
            },
        },
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "started coverage" in confirmed_payload["summary"].lower()

    second_cascade = await get_active_cascade_for_shift(db, second_shift_id)
    first_cascade = await get_active_cascade_for_shift(db, first_shift_id)
    assert second_cascade is not None
    assert first_cascade is None


@pytest.mark.asyncio
async def test_retell_ai_manager_action_can_create_open_shift_after_confirmation(db, client, monkeypatch):
    monkeypatch.setattr("app.services.notifications.send_sms", lambda to, body: "SM-NOTIFY")
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    location_id = await insert_location(
        db,
        {
            "name": "Retell AI Create Cafe",
            "manager_name": "Chef Nina",
            "manager_phone": "+13105550135",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": "2026-04-13",
            "week_end_date": "2026-04-19",
            "lifecycle_state": "draft",
            "created_by": "test",
        },
    )

    action = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "ai_manager_action",
            "args": {
                "phone": "+13105550135",
                "text": "Create an open dishwasher shift on 2026-04-15 from 11 to 7",
                "location_id": location_id,
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
            },
        },
    )
    assert action.status_code == 200
    action_payload = action.json()
    assert action_payload["status"] == "awaiting_confirmation"
    assert "create an open dishwasher shift" in action_payload["summary"].lower()

    confirmed = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "confirm_ai_action",
            "args": {
                "location_id": location_id,
                "action_request_id": action_payload["action_request_id"],
            },
        },
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "created the open dishwasher shift" in confirmed_payload["summary"].lower()

    shifts = await list_shifts(db, schedule_id=schedule_id)
    target_shift = next(
        shift
        for shift in shifts
        if shift["role"] == "dishwasher" and shift["date"] == "2026-04-15" and shift["start_time"] == "11:00:00"
    )
    assignment = await get_shift_assignment(db, int(target_shift["id"]))
    assert assignment is not None
    assert assignment["assignment_status"] == "open"


@pytest.mark.asyncio
async def test_retell_ai_manager_action_can_reopen_closed_open_shift_after_confirmation(db, client, monkeypatch):
    monkeypatch.setattr("app.services.notifications.send_sms", lambda to, body: "SM-NOTIFY")
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    location_id = await insert_location(
        db,
        {
            "name": "Retell AI Reopen Cafe",
            "manager_name": "Chef Nina",
            "manager_phone": "+13105550138",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    await insert_worker(
        db,
        {
            "name": "Taylor",
            "phone": "+13105550139",
            "roles": ["dishwasher"],
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
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
        },
    )
    await upsert_shift_assignment(
        db,
        {
            "shift_id": shift_id,
            "worker_id": None,
            "assignment_status": "closed",
            "source": "manual",
        },
    )

    action = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "ai_manager_action",
            "args": {
                "phone": "+13105550138",
                "text": "Reopen and offer the shift",
                "location_id": location_id,
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
                "shift_id": shift_id,
            },
        },
    )
    assert action.status_code == 200
    action_payload = action.json()
    assert action_payload["status"] == "awaiting_confirmation"
    assert "reopen the closed dishwasher shift" in action_payload["summary"].lower()

    confirmed = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "confirm_ai_action",
            "args": {
                "location_id": location_id,
                "action_request_id": action_payload["action_request_id"],
            },
        },
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "started offering it" in confirmed_payload["summary"].lower()

    assignment = await get_shift_assignment(db, shift_id)
    active_cascade = await get_active_cascade_for_shift(db, shift_id)
    assert assignment is not None
    assert assignment["assignment_status"] == "open"
    assert active_cascade is not None


@pytest.mark.asyncio
async def test_retell_ai_manager_action_can_assign_shift_after_confirmation(db, client, monkeypatch):
    monkeypatch.setattr("app.services.notifications.send_sms", lambda to, body: "SM-NOTIFY")
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    location_id = await insert_location(
        db,
        {
            "name": "Retell AI Assign Cafe",
            "manager_name": "Chef Nina",
            "manager_phone": "+13105550142",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Taylor",
            "phone": "+13105550143",
            "roles": ["dishwasher"],
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
            "lifecycle_state": "draft",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
        },
    )
    await upsert_shift_assignment(
        db,
        {
            "shift_id": shift_id,
            "worker_id": None,
            "assignment_status": "open",
            "source": "manual",
        },
    )

    action = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "ai_manager_action",
            "args": {
                "phone": "+13105550142",
                "text": "Assign Taylor to the dishwasher shift",
                "location_id": location_id,
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
                "shift_id": shift_id,
                "worker_id": worker_id,
            },
        },
    )
    assert action.status_code == 200
    action_payload = action.json()
    assert action_payload["status"] == "awaiting_confirmation"
    assert "assign taylor" in action_payload["summary"].lower()

    confirmed = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "confirm_ai_action",
            "args": {
                "location_id": location_id,
                "action_request_id": action_payload["action_request_id"],
            },
        },
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "assigned taylor" in confirmed_payload["summary"].lower()

    assignment = await get_shift_assignment(db, shift_id)
    assert assignment is not None
    assert assignment["worker_id"] == worker_id
    assert assignment["assignment_status"] == "assigned"


@pytest.mark.asyncio
async def test_retell_ai_manager_action_can_edit_shift_after_confirmation(db, client, monkeypatch):
    monkeypatch.setattr("app.services.notifications.send_sms", lambda to, body: "SM-NOTIFY")
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    location_id = await insert_location(
        db,
        {
            "name": "Retell AI Edit Cafe",
            "manager_name": "Chef Nina",
            "manager_phone": "+13105550145",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": "2026-04-13",
            "week_end_date": "2026-04-19",
            "lifecycle_state": "draft",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
        },
    )
    await upsert_shift_assignment(
        db,
        {
            "shift_id": shift_id,
            "worker_id": None,
            "assignment_status": "open",
            "source": "manual",
        },
    )

    action = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "ai_manager_action",
            "args": {
                "phone": "+13105550145",
                "text": "Move the dishwasher shift to 12 to 8",
                "location_id": location_id,
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
                "shift_id": shift_id,
            },
        },
    )
    assert action.status_code == 200
    action_payload = action.json()
    assert action_payload["status"] == "awaiting_confirmation"
    assert "update the dishwasher shift" in action_payload["summary"].lower()

    confirmed = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "confirm_ai_action",
            "args": {
                "location_id": location_id,
                "action_request_id": action_payload["action_request_id"],
            },
        },
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "updated the dishwasher shift" in confirmed_payload["summary"].lower()

    updated_shift = await get_shift(db, shift_id)
    assert updated_shift is not None
    assert updated_shift["start_time"] == "12:00:00"
    assert updated_shift["end_time"] == "20:00:00"


@pytest.mark.asyncio
async def test_retell_ai_manager_action_can_delete_shift_after_confirmation(db, client, monkeypatch):
    monkeypatch.setattr("app.services.notifications.send_sms", lambda to, body: "SM-NOTIFY")
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    location_id = await insert_location(
        db,
        {
            "name": "Retell AI Delete Cafe",
            "manager_name": "Chef Nina",
            "manager_phone": "+13105550147",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": "2026-04-13",
            "week_end_date": "2026-04-19",
            "lifecycle_state": "draft",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "dishwasher",
            "date": "2026-04-15",
            "start_time": "11:00:00",
            "end_time": "19:00:00",
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
        },
    )
    await upsert_shift_assignment(
        db,
        {
            "shift_id": shift_id,
            "worker_id": None,
            "assignment_status": "open",
            "source": "manual",
        },
    )

    action = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "ai_manager_action",
            "args": {
                "phone": "+13105550147",
                "text": "Delete the dishwasher shift",
                "location_id": location_id,
                "schedule_id": schedule_id,
                "week_start_date": "2026-04-13",
                "shift_id": shift_id,
            },
        },
    )
    assert action.status_code == 200
    action_payload = action.json()
    assert action_payload["status"] == "awaiting_confirmation"
    assert "delete the dishwasher shift" in action_payload["summary"].lower()

    confirmed = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "confirm_ai_action",
            "args": {
                "location_id": location_id,
                "action_request_id": action_payload["action_request_id"],
            },
        },
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "completed"
    assert "deleted the dishwasher shift" in confirmed_payload["summary"].lower()

    deleted_shift = await get_shift(db, shift_id)
    assert deleted_shift is None


@pytest.mark.asyncio
async def test_retell_call_analyzed_persists_transcript_and_updates_attempt_summary(db, client, monkeypatch):
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")

    async def _fake_call(*, to_number, metadata, agent_id=None, agent_kind="outbound"):
        return "call_seed"

    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)

    location_id = await insert_location(
        db,
        {
            "name": "Retell Persistence Grill",
            "manager_name": "Chef Ana",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
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
    start = datetime.utcnow() + timedelta(hours=2)
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "role": "line_cook",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 22.0,
            "requirements": ["food_handler_card"],
            "status": "scheduled",
            "source_platform": "backfill_native",
        },
    )

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    await cascade_svc.advance(db, cascade["id"])

    response = client.post(
        "/webhooks/retell",
        json={
            "event": "call_analyzed",
            "call": {
                "call_id": "call_transcript_123",
                "agent_id": "agent_voice",
                "direction": "outbound",
                "call_status": "ended",
                "from_number": "+14244992663",
                "to_number": "+13105550103",
                "metadata": {
                    "location_id": location_id,
                    "shift_id": shift_id,
                    "cascade_id": cascade["id"],
                    "worker_id": target_id,
                },
                "transcript": "Agent: Can you take the shift?\nWorker: Yes, I can be there in 10 minutes.",
                "transcript_object": [
                    {"speaker": "agent", "text": "Can you take the shift?"},
                    {"speaker": "worker", "text": "Yes, I can be there in 10 minutes."},
                ],
                "call_analysis": {
                    "call_summary": "Worker accepted and said they can arrive in 10 minutes."
                },
            },
        },
    )

    assert response.status_code == 200
    payload = await get_shift_status(db, shift_id)
    assert payload is not None
    assert len(payload["retell_conversations"]) == 1
    conversation = payload["retell_conversations"][0]
    assert conversation["external_id"] == "call_transcript_123"
    assert conversation["conversation_type"] == "call"
    assert conversation["worker_id"] == target_id
    assert conversation["cascade_id"] == cascade["id"]
    assert conversation["transcript_text"].startswith("Agent: Can you take the shift?")
    assert conversation["analysis"]["call_summary"] == "Worker accepted and said they can arrive in 10 minutes."
    assert payload["outreach_attempts"][0]["conversation_summary"] == "Worker accepted and said they can arrive in 10 minutes."


@pytest.mark.asyncio
async def test_retell_inbound_business_call_creates_signup_session_and_texts_link(db, client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.onboarding.send_sms",
        lambda to, body, **kwargs: sent.append((to, body, kwargs)) or "SM900",
    )

    response = client.post(
        "/webhooks/retell",
        json={
            "event": "call_analyzed",
            "call": {
                "call_id": "call_business_signup_123",
                "agent_id": "agent_inbound",
                "direction": "inbound",
                "call_status": "ended",
                "from_number": "+13105550177",
                "to_number": "+14244992663",
                "transcript": "Caller wants pricing and onboarding help.",
                "call_analysis": {
                    "call_type": "business_inquiry",
                    "caller_name": "Jordan Lee",
                    "business_name": "South Bay Ops",
                    "location_name": "South Bay Fulfillment",
                    "role_name": "Operations Manager",
                    "business_email": "jordan@southbayops.com",
                    "location_count": 3,
                    "lead_source": "referral",
                    "pain_point_summary": "Need faster call-out coverage across warehouse shifts.",
                    "urgency": "high",
                    "notes": "Interested in getting started this week.",
                },
            },
        },
    )

    assert response.status_code == 200
    organization = await get_organization_by_name(db, "South Bay Ops")
    assert organization is not None
    assert organization["location_count_estimate"] == 3

    session = await get_onboarding_session_by_source_external_id(db, "call_business_signup_123")
    assert session is not None
    assert session["organization_id"] == organization["id"]
    assert session["contact_phone"] == "+13105550177"
    assert session["business_name"] == "South Bay Ops"
    assert session["setup_kind"] == "csv_upload"
    assert session["status"] == "pending"
    assert session["lead_source"] == "referral"
    assert sent
    assert "https://usebackfill.com/signup/" in sent[0][1]
    assert "dynamic_variables" in sent[0][2]
    assert sent[0][2]["dynamic_variables"]["business_name"] == "South Bay Ops"
    assert "signup_url" in sent[0][2]["dynamic_variables"]


@pytest.mark.asyncio
async def test_retell_inbound_business_call_uses_summary_fallback_for_signup_text(db, client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.onboarding.send_sms",
        lambda to, body, **kwargs: sent.append((to, body, kwargs)) or "SM901",
    )

    response = client.post(
        "/webhooks/retell",
        json={
            "event": "call_analyzed",
            "call": {
                "call_id": "call_business_summary_fallback",
                "agent_id": "agent_inbound",
                "direction": "inbound",
                "call_status": "ended",
                "from_number": "+13105550999",
                "to_number": "+14244992663",
                "transcript": (
                    "Agent: Are you calling about using Backfill for a business?\n"
                    "User: For business.\n"
                    "User: I'm with Whole Foods.\n"
                    "User: We need help covering shifts when someone calls out.\n"
                ),
                "call_analysis": {
                    "call_successful": True,
                    "call_summary": (
                        "The caller contacted Backfill to discuss using the service for covering "
                        "last-minute shift gaps when employees call out."
                    ),
                    "custom_analysis_data": {},
                },
            },
        },
    )

    assert response.status_code == 200
    session = await get_onboarding_session_by_source_external_id(db, "call_business_summary_fallback")
    assert session is not None
    assert session["contact_phone"] == "+13105550999"
    assert sent
    assert "https://usebackfill.com/signup/" in sent[0][1]


@pytest.mark.asyncio
async def test_retell_inbound_business_call_prefills_from_summary_and_transcript(db, client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.onboarding.send_sms",
        lambda to, body, **kwargs: sent.append((to, body, kwargs)) or "SM905",
    )

    response = client.post(
        "/webhooks/retell",
        json={
            "event": "call_analyzed",
            "call": {
                "call_id": "call_business_prefill_123",
                "agent_id": "agent_inbound",
                "direction": "inbound",
                "call_status": "ended",
                "from_number": "+16462065103",
                "to_number": "+14244992663",
                "transcript": (
                    "User: My name is Carden, and I'm with Whole Foods.\n"
                    "User: I am the general manager for about a hundred stores.\n"
                    "User: My number is six four six two zero six five one zero three.\n"
                ),
                "call_analysis": {
                    "call_type": "phone_call",
                    "call_summary": (
                        "The caller, Carden from Whole Foods, expressed interest in using Backfill. "
                        "The agent gathered contact details and confirmed Carden's role managing about 100 stores."
                    ),
                    "custom_analysis_data": {},
                },
            },
        },
    )

    assert response.status_code == 200
    session = await get_onboarding_session_by_source_external_id(db, "call_business_prefill_123")
    assert session is not None
    assert session["call_type"] == "new_business_inquiry"
    assert session["contact_name"] == "Carden"
    assert session["business_name"] == "Whole Foods"
    assert session["role_name"] == "general manager"
    assert session["location_count"] == 100
    assert session["contact_phone"] == "+16462065103"
    assert sent


@pytest.mark.asyncio
async def test_retell_inbound_business_call_captures_lead_source_without_exposing_it_in_sms(
    db,
    client,
    monkeypatch,
):
    sent = []
    monkeypatch.setattr(
        "app.services.onboarding.send_sms",
        lambda to, body, **kwargs: sent.append((to, body, kwargs)) or "SM906",
    )

    response = client.post(
        "/webhooks/retell",
        json={
            "event": "call_analyzed",
            "call": {
                "call_id": "call_lead_source_123",
                "direction": "inbound",
                "call_status": "ended",
                "from_number": "+13105550701",
                "to_number": "+14244992663",
                "call_analysis": {
                    "call_type": "new_business_inquiry",
                    "business_name": "Northstar Care",
                    "caller_name": "Ari Fox",
                    "lead_source": "podcast",
                },
            },
        },
    )

    assert response.status_code == 200
    session = await get_onboarding_session_by_source_external_id(db, "call_lead_source_123")
    assert session is not None
    assert session["lead_source"] == "podcast"
    assert sent
    assert "podcast" not in sent[0][1].lower()


@pytest.mark.asyncio
async def test_retell_inbound_business_call_accepts_new_business_inquiry_call_type(db, client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.onboarding.send_sms",
        lambda to, body, **kwargs: sent.append((to, body, kwargs)) or "SM902",
    )

    response = client.post(
        "/webhooks/retell",
        json={
            "event": "call_analyzed",
            "call": {
                "call_id": "call_new_business_inquiry_123",
                "agent_id": "agent_inbound",
                "direction": "inbound",
                "call_status": "ended",
                "from_number": "+13105550777",
                "to_number": "+14244992663",
                "call_analysis": {
                    "call_type": "new_business_inquiry",
                    "caller_name": "Taylor Kim",
                    "business_name": "Northside Logistics",
                    "business_email": "taylor@northside.example",
                },
            },
        },
    )

    assert response.status_code == 200
    session = await get_onboarding_session_by_source_external_id(db, "call_new_business_inquiry_123")
    assert session is not None
    assert session["contact_phone"] == "+13105550777"
    assert sent


@pytest.mark.asyncio
async def test_retell_inbound_business_call_normalizes_callback_number_and_retries_unsent_session(
    db,
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "retell_from_number", "+14244992663")
    sent = []
    fail_first = {"value": True}

    def _fake_send_sms(to, body, **kwargs):
        if fail_first["value"]:
            fail_first["value"] = False
            raise RuntimeError("temporary sms failure")
        sent.append((to, body, kwargs))
        return "SM903"

    monkeypatch.setattr("app.services.onboarding.send_sms", _fake_send_sms)

    payload = {
        "event": "call_analyzed",
        "call": {
            "call_id": "call_retry_signup_123",
            "agent_id": "agent_inbound",
            "call_status": "ended",
            "from_number": "+16462065103",
            "to_number": "+14244992663",
            "call_analysis": {
                "call_type": "new_business_inquiry",
                "caller_name": "Carden Campbell",
                "business_name": "Whole Foods",
                "callback_number": "(646) 206-5103",
                "business_email": "gm@wholefoods.example",
            },
        },
    }

    first = client.post("/webhooks/retell", json=payload)
    assert first.status_code == 200

    session = await get_onboarding_session_by_source_external_id(db, "call_retry_signup_123")
    assert session is not None
    assert session["contact_phone"] == "+16462065103"
    assert session["sent_message_sid"] is None

    second = client.post("/webhooks/retell", json=payload)
    assert second.status_code == 200

    session = await get_onboarding_session_by_source_external_id(db, "call_retry_signup_123")
    assert session is not None
    assert session["sent_message_sid"] == "SM903"
    assert sent
    assert sent[0][0] == "+16462065103"


@pytest.mark.asyncio
async def test_retell_inbound_business_call_infers_inbound_direction_from_phone_numbers(db, client, monkeypatch):
    monkeypatch.setattr(settings, "retell_from_number", "+14244992663")
    sent = []
    monkeypatch.setattr(
        "app.services.onboarding.send_sms",
        lambda to, body, **kwargs: sent.append((to, body, kwargs)) or "SM904",
    )

    response = client.post(
        "/webhooks/retell",
        json={
            "event": "call_analyzed",
            "call": {
                "call_id": "call_infer_direction_123",
                "agent_id": "agent_inbound",
                "call_status": "ended",
                "from_number": "+13105550888",
                "to_number": "+14244992663",
                "call_analysis": {
                    "call_type": "new_business_inquiry",
                    "business_name": "Bright Care",
                    "business_email": "ops@brightcare.example",
                },
            },
        },
    )

    assert response.status_code == 200
    session = await get_onboarding_session_by_source_external_id(db, "call_infer_direction_123")
    assert session is not None
    assert session["contact_phone"] == "+13105550888"
    assert sent


@pytest.mark.asyncio
async def test_retell_chat_analyzed_persists_text_exchange(db, client):
    location_id = await insert_location(
        db,
        {
            "name": "Retell SMS Shop",
            "manager_name": "Nina",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Alex",
            "phone": "+13105550105",
            "roles": ["picker"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    start = datetime.utcnow() + timedelta(hours=6)
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "role": "picker",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 19.0,
            "requirements": [],
            "status": "vacant",
            "source_platform": "backfill_native",
        },
    )

    response = client.post(
        "/webhooks/retell",
        json={
            "event": "chat_analyzed",
            "chat": {
                "chat_id": "chat_123",
                "agent_id": "agent_sms",
                "direction": "inbound",
                "status": "ended",
                "from_number": "+13105550103",
                "to_number": "+14244992663",
                "metadata": {
                    "location_id": location_id,
                    "shift_id": shift_id,
                    "worker_id": worker_id,
                },
                "messages": [
                    {"role": "worker", "content": "YES but I need 15 minutes."},
                    {"role": "agent", "content": "Understood. Checking shift timing now."},
                ],
                "chat_analysis": {
                    "summary": "Worker accepted by text and requested a 15 minute ETA."
                },
            },
        },
    )

    assert response.status_code == 200
    async with db.execute(
        "SELECT external_id, conversation_type, transcript_text, transcript_items, analysis, metadata FROM retell_conversations WHERE external_id=?",
        ("chat_123",),
    ) as cur:
        row = await cur.fetchone()
    assert row is not None
    assert row["external_id"] == "chat_123"
    assert row["conversation_type"] == "chat"
    assert "YES but I need 15 minutes." in row["transcript_text"]
    assert "Worker accepted by text and requested a 15 minute ETA." in row["analysis"]
    assert f'"shift_id": {shift_id}' in row["metadata"]


@pytest.mark.asyncio
async def test_retell_claim_shift_requires_eta_for_started_shift(db, client, monkeypatch):
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")

    async def _fake_call(*, to_number, metadata, agent_id=None, agent_kind="outbound"):
        return "CA123"

    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)

    location_id = await insert_location(
        db,
        {
            "name": "Late Response Diner",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
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
    start = datetime.utcnow() - timedelta(minutes=2)
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "role": "line_cook",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 22.0,
            "requirements": ["food_handler_card"],
            "status": "scheduled",
            "source_platform": "backfill_native",
        },
    )

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    await cascade_svc.advance(db, cascade["id"])

    response = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "claim_shift",
            "args": {
                "cascade_id": cascade["id"],
                "worker_id": target_id,
                "conversation_summary": "Worker said yes but did not provide ETA yet.",
            },
        },
    )

    shift = await get_shift(db, shift_id)
    assert response.status_code == 200
    assert response.json()["status"] == "eta_required"
    assert shift["filled_by"] is None
    assert shift["status"] == "vacant"


@pytest.mark.asyncio
async def test_retell_claim_shift_confirms_within_late_grace_window(db, client, monkeypatch):
    notifications = []

    async def _fake_notify(db_conn, cascade_id, worker_id, filled=True):
        notifications.append((cascade_id, worker_id, filled))

    monkeypatch.setattr("app.services.notifications.fire_manager_notification", _fake_notify)
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")

    async def _fake_call(*, to_number, metadata, agent_id=None, agent_kind="outbound"):
        return "CA123"

    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)

    location_id = await insert_location(
        db,
        {
            "name": "Grace Window Cafe",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
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
    start = datetime.utcnow() - timedelta(minutes=5)
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "role": "line_cook",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 22.0,
            "requirements": ["food_handler_card"],
            "status": "scheduled",
            "source_platform": "backfill_native",
        },
    )

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    await cascade_svc.advance(db, cascade["id"])

    response = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "claim_shift",
            "args": {
                "cascade_id": cascade["id"],
                "worker_id": target_id,
                "eta_minutes": 5,
                "conversation_summary": "Worker accepted and can arrive in 5 minutes.",
            },
        },
    )

    shift = await get_shift(db, shift_id)
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    assert response.json()["late_by_minutes"] >= 9
    assert shift["filled_by"] == target_id
    assert notifications == [(cascade["id"], target_id, True)]
