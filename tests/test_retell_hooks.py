from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db.queries import get_cascade, get_shift, insert_restaurant, insert_shift, insert_worker
from app.services import cascade as cascade_svc
from app.services.shift_manager import create_vacancy


@pytest.mark.asyncio
async def test_retell_claim_shift_function_call_confirms_and_notifies(db, client, monkeypatch):
    notifications = []

    async def _fake_notify(db_conn, cascade_id, worker_id, filled=True):
        notifications.append((cascade_id, worker_id, filled))

    monkeypatch.setattr("app.services.notifications.fire_manager_notification", _fake_notify)

    restaurant_id = await insert_restaurant(
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
            "restaurant_id": restaurant_id,
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
            "restaurant_id": restaurant_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    start = datetime.utcnow() + timedelta(hours=12)
    shift_id = await insert_shift(
        db,
        {
            "restaurant_id": restaurant_id,
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

    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body: "SM123")
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
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body: "SM123")

    async def _fake_call(*, to_number, metadata, agent_id=None):
        return "CA123"

    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)

    restaurant_id = await insert_restaurant(
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
            "restaurant_id": restaurant_id,
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
            "restaurant_id": restaurant_id,
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
            "restaurant_id": restaurant_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    start = datetime.utcnow() + timedelta(hours=1)
    shift_id = await insert_shift(
        db,
        {
            "restaurant_id": restaurant_id,
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
