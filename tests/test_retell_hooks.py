from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.config import settings
from app.db.queries import (
    get_cascade,
    get_onboarding_session_by_source_external_id,
    get_organization_by_name,
    get_shift,
    get_shift_status,
    insert_location,
    insert_shift,
    insert_worker,
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
    monkeypatch.setattr("app.services.onboarding.send_sms", lambda to, body: sent.append((to, body)) or "SM900")

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
    assert session["setup_kind"] == "manual_form"
    assert session["status"] == "pending"
    assert sent
    assert "https://usebackfill.com/signup/" in sent[0][1]


@pytest.mark.asyncio
async def test_retell_inbound_business_call_uses_summary_fallback_for_signup_text(db, client, monkeypatch):
    sent = []
    monkeypatch.setattr("app.services.onboarding.send_sms", lambda to, body: sent.append((to, body)) or "SM901")

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
async def test_retell_inbound_business_call_accepts_new_business_inquiry_call_type(db, client, monkeypatch):
    sent = []
    monkeypatch.setattr("app.services.onboarding.send_sms", lambda to, body: sent.append((to, body)) or "SM902")

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

    def _fake_send_sms(to, body):
        if fail_first["value"]:
            fail_first["value"] = False
            raise RuntimeError("temporary sms failure")
        sent.append((to, body))
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
    monkeypatch.setattr("app.services.onboarding.send_sms", lambda to, body: sent.append((to, body)) or "SM904")

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
