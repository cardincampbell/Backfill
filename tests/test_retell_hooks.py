from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db.queries import get_cascade, get_shift, insert_location, insert_shift, insert_worker
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

    response = client.post(
        "/webhooks/retell",
        json={
            "event": "function_call",
            "name": "send_onboarding_link",
            "args": {
                "phone": "+13105550100",
                "kind": "integration",
                "platform": "Homebase",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["platform"] == "homebase"
    assert payload["path"] == "/setup/connect?platform=homebase"
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
