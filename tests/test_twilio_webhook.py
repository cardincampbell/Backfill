from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from twilio.request_validator import RequestValidator

from app.config import settings
from app.db.queries import (
    get_active_cascade_for_shift,
    get_cascade,
    get_schedule,
    get_schedule_by_location_week,
    get_shift,
    get_worker,
    insert_import_job,
    insert_import_row_result,
    insert_agency_partner,
    insert_location,
    insert_schedule,
    insert_shift,
    insert_worker,
    list_agency_requests,
    upsert_shift_assignment,
)
from app.services import cascade as cascade_svc
from app.services.shift_manager import create_vacancy


def _signed_sms_headers(token: str, params: dict[str, str]) -> dict[str, str]:
    validator = RequestValidator(token)
    signature = validator.compute_signature("http://testserver/webhooks/twilio/sms", params)
    return {"X-Twilio-Signature": signature}


@pytest.mark.asyncio
async def test_yes_reply_confirms_shift(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    location_id = await insert_location(
        db,
        {
            "name": "Taco Spot",
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
    monkeypatch.setattr("app.services.agency_router.send_sms", lambda to, body: "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    notifications = []

    async def _fake_notification(db_conn, cascade_id, worker_id, filled=True):
        notifications.append((cascade_id, worker_id, filled))

    monkeypatch.setattr("app.services.notifications.fire_manager_notification", _fake_notification)

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    await cascade_svc.advance(db, cascade["id"])

    params = {"From": "+13105550103", "Body": "YES"}
    response = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=_signed_sms_headers("test-token", params),
    )

    shift = await get_shift(db, shift_id)
    assert response.status_code == 200
    assert "confirmed" in response.text.lower()
    assert shift["status"] == "filled"
    assert shift["filled_by"] == target_id
    assert notifications


@pytest.mark.asyncio
async def test_yes_reply_queues_manager_notification_when_ops_worker_enabled(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")
    monkeypatch.setattr(settings, "backfill_ops_worker_enabled", True)

    location_id = await insert_location(
        db,
        {
            "name": "Queued Taco Spot",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550120",
            "scheduling_platform": "backfill_native",
        },
    )
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550121",
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
            "phone": "+13105550122",
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
    monkeypatch.setattr("app.services.agency_router.send_sms", lambda to, body: "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    notifications = []

    async def _fake_notification(db_conn, cascade_id, worker_id, filled=True):
        notifications.append((cascade_id, worker_id, filled))

    monkeypatch.setattr("app.services.notifications.fire_manager_notification", _fake_notification)

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    await cascade_svc.advance(db, cascade["id"])

    params = {"From": "+13105550122", "Body": "YES"}
    response = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=_signed_sms_headers("test-token", params),
    )

    queued_jobs = client.get("/api/internal/ops/jobs?status=queued&job_type=send_notification")
    processed = client.post("/api/internal/ops/process-due?limit=10")

    assert response.status_code == 200
    assert "confirmed" in response.text.lower()
    assert queued_jobs.status_code == 200
    assert len(queued_jobs.json()["jobs"]) == 1
    assert queued_jobs.json()["jobs"][0]["payload_json"]["notification_type"] == "manager_notification"
    assert processed.status_code == 200
    assert notifications == [(cascade["id"], target_id, True)]


@pytest.mark.asyncio
async def test_duplicate_message_sid_replays_same_yes_response_without_reprocessing(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    location_id = await insert_location(
        db,
        {
            "name": "Replay Taco",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550110",
            "scheduling_platform": "backfill_native",
        },
    )
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550111",
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
            "phone": "+13105550112",
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
    monkeypatch.setattr("app.services.agency_router.send_sms", lambda to, body: "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    notifications = []

    async def _fake_notification(db_conn, cascade_id, worker_id, filled=True):
        notifications.append((cascade_id, worker_id, filled))

    monkeypatch.setattr("app.services.notifications.fire_manager_notification", _fake_notification)

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    await cascade_svc.advance(db, cascade["id"])

    params = {"From": "+13105550112", "Body": "YES", "MessageSid": "SMREPLAY1"}
    first = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=_signed_sms_headers("test-token", params),
    )
    second = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=_signed_sms_headers("test-token", params),
    )
    webhook_health = client.get("/api/internal/backfill-shifts/webhook-health?days=30&limit=10")

    shift = await get_shift(db, shift_id)
    assert first.status_code == 200
    assert second.status_code == 200
    assert webhook_health.status_code == 200
    assert first.text == second.text
    assert "confirmed" in first.text.lower()
    assert shift["status"] == "filled"
    assert shift["filled_by"] == target_id
    assert notifications == [(cascade["id"], target_id, True)]
    assert webhook_health.json()["summary"] == {
        "receipt_count": 1,
        "completed_count": 1,
        "processing_count": 0,
        "receipts_with_retries": 1,
        "duplicate_retry_count": 1,
    }
    assert webhook_health.json()["recent_receipts"][0]["from_phone"] == "+13105550112"
    assert webhook_health.json()["recent_receipts"][0]["body_preview"] == "YES"


@pytest.mark.asyncio
async def test_worker_yes_can_wait_for_manager_approval_and_manager_yes_confirms(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    manager_notifications = []
    worker_notifications = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: (
            manager_notifications.append((to, body))
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
            "operating_mode": "backfill_shifts",
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
    candidate_id = await insert_worker(
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
    week_start = start.date() - timedelta(days=start.date().weekday())
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

    worker_yes = {"From": "+13105550103", "Body": "YES"}
    worker_response = client.post(
        "/webhooks/twilio/sms",
        data=worker_yes,
        headers=_signed_sms_headers("test-token", worker_yes),
    )
    coverage_pending = client.get(
        f"/api/locations/{location_id}/coverage?week_start={week_start.isoformat()}"
    )

    assert worker_response.status_code == 200
    assert "sent your claim to the manager for approval" in worker_response.text.lower()
    assert coverage_pending.status_code == 200
    pending_payload = coverage_pending.json()["at_risk_shifts"][0]
    assert pending_payload["coverage_status"] == "awaiting_manager_approval"
    assert pending_payload["manager_action_required"] is True
    assert pending_payload["claimed_by_worker_id"] == candidate_id
    assert pending_payload["claimed_by_worker_name"] == "James"
    assert pending_payload["claimed_at"] is not None
    assert manager_notifications and "reply yes to approve or no to keep looking" in manager_notifications[0][1].lower()

    manager_yes = {"From": "+13105550100", "Body": "YES"}
    manager_response = client.post(
        "/webhooks/twilio/sms",
        data=manager_yes,
        headers=_signed_sms_headers("test-token", manager_yes),
    )

    shift = await get_shift(db, shift_id)
    cascade_after = await get_cascade(db, cascade["id"])

    assert manager_response.status_code == 200
    assert "approved" in manager_response.text.lower()
    assert shift["status"] == "filled"
    assert shift["filled_by"] == candidate_id
    assert cascade_after["pending_claim_worker_id"] is None
    assert worker_notifications and "you're confirmed" in worker_notifications[0][1].lower()


@pytest.mark.asyncio
async def test_manager_action_queue_and_api_fill_approval_flow(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")
    monkeypatch.setattr("app.services.notifications.send_sms", lambda to, body: "SM-NOTIFY")
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    location_id = await insert_location(
        db,
        {
            "name": "Queue Taco",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550114",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
            "coverage_requires_manager_approval": True,
        },
    )
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550115",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    candidate_id = await insert_worker(
        db,
        {
            "name": "James",
            "phone": "+13105550116",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 2,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )

    start = datetime.utcnow() + timedelta(hours=12)
    week_start = start.date() - timedelta(days=start.date().weekday())
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
    claim = await cascade_svc.claim_shift(db, cascade["id"], candidate_id, summary="Accepted by SMS")

    assert claim["status"] == "awaiting_manager_approval"

    queue = client.get(
        f"/api/locations/{location_id}/manager-actions?week_start={week_start.isoformat()}"
    )
    approve = client.post(f"/api/cascades/{cascade['id']}/approve-fill")
    queue_after = client.get(
        f"/api/locations/{location_id}/manager-actions?week_start={week_start.isoformat()}"
    )
    shift_after = await get_shift(db, shift_id)

    assert queue.status_code == 200
    assert queue.json()["summary"] == {
        "pending_actions": 1,
        "fill_approvals": 1,
        "agency_approvals": 0,
        "attendance_reviews": 0,
    }
    assert queue.json()["actions"][0] == {
        "action_type": "approve_fill",
        "cascade_id": cascade["id"],
        "shift_id": shift_id,
        "role": "line_cook",
        "date": start.date().isoformat(),
        "start_time": start.strftime("%H:%M:%S"),
        "coverage_status": "awaiting_manager_approval",
        "requested_at": claim["claimed_at"],
        "worker_id": candidate_id,
        "worker_name": "James",
        "available_actions": ["approve_fill", "decline_fill"],
    }
    assert approve.status_code == 200
    assert approve.json()["status"] == "confirmed"
    assert approve.json()["worker_id"] == candidate_id
    assert shift_after["status"] == "filled"
    assert shift_after["filled_by"] == candidate_id
    assert queue_after.status_code == 200
    assert queue_after.json()["summary"]["pending_actions"] == 0
    assert queue_after.json()["actions"] == []


@pytest.mark.asyncio
async def test_schedule_assignment_reminder_route_sends_once_for_published_shift(db, client, monkeypatch):
    reminders = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: reminders.append((to, body)) or "SM-REMINDER",
    )

    location_id = await insert_location(
        db,
        {
            "name": "Reminder Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550119",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Terry Cook",
            "phone": "+13105550120",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    start = datetime.utcnow() + timedelta(minutes=20)
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": (start.date() - timedelta(days=start.date().weekday())).isoformat(),
            "week_end_date": (start.date() - timedelta(days=start.date().weekday()) + timedelta(days=6)).isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 22.0,
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
            "worker_id": worker_id,
            "assignment_status": "assigned",
            "source": "manual",
        },
    )

    first = client.post(f"/api/shifts/send-reminders?within_minutes=30&location_id={location_id}")
    second = client.post(f"/api/shifts/send-reminders?within_minutes=30&location_id={location_id}")

    assert first.status_code == 200
    assert first.json() == {
        "location_id": location_id,
        "within_minutes": 30,
        "reminders_sent": 1,
        "shift_ids": [shift_id],
        "skipped_shift_ids": [],
    }
    assert second.status_code == 200
    assert second.json()["reminders_sent"] == 0
    assert second.json()["shift_ids"] == []
    assert len(reminders) == 1
    assert reminders[0][0] == "+13105550120"
    assert "reminder" in reminders[0][1].lower()
    assert "reminder cafe" in reminders[0][1].lower()


@pytest.mark.asyncio
async def test_second_yes_reply_enters_standby_and_cancel_removes_it(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    location_id = await insert_location(
        db,
        {
            "name": "Taco Spot",
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

    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    monkeypatch.setattr("app.services.agency_router.send_sms", lambda to, body: "SM123")

    async def _fake_call(*, to_number, metadata, agent_id=None):
        return "CA123"

    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)

    async def _fake_notification(*args, **kwargs):
        return None

    monkeypatch.setattr("app.services.notifications.fire_manager_notification", _fake_notification)

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    await cascade_svc.advance(db, cascade["id"])

    yes_params = {"From": "+13105550103", "Body": "YES"}
    yes_response = client.post(
        "/webhooks/twilio/sms",
        data=yes_params,
        headers=_signed_sms_headers("test-token", yes_params),
    )
    standby_params = {"From": "+13105550104", "Body": "YES"}
    standby_response = client.post(
        "/webhooks/twilio/sms",
        data=standby_params,
        headers=_signed_sms_headers("test-token", standby_params),
    )
    cancel_params = {"From": "+13105550104", "Body": "CANCEL"}
    cancel_response = client.post(
        "/webhooks/twilio/sms",
        data=cancel_params,
        headers=_signed_sms_headers("test-token", cancel_params),
    )

    shift = await get_shift(db, shift_id)
    updated_cascade = await get_cascade(db, cascade["id"])

    assert yes_response.status_code == 200
    assert "confirmed" in yes_response.text.lower()
    assert standby_response.status_code == 200
    assert "standby" in standby_response.text.lower()
    assert cancel_response.status_code == 200
    assert "off standby" in cancel_response.text.lower()
    assert shift["filled_by"] == confirmed_id
    assert updated_cascade["standby_queue"] == []


@pytest.mark.asyncio
async def test_manager_no_promotes_next_standby_claim_when_approval_is_required(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    manager_notifications = []
    worker_notifications = []
    worker_offers = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: (
            manager_notifications.append((to, body))
            if to == "+13105550110"
            else worker_notifications.append((to, body))
        ) or "SM-NOTIFY",
    )
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM123",
    )
    async def _fake_call(*, to_number, metadata, agent_id=None):
        return "CA123"

    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)

    location_id = await insert_location(
        db,
        {
            "name": "Broadcast Taco",
            "manager_name": "Chef Nina",
            "manager_phone": "+13105550110",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
            "coverage_requires_manager_approval": True,
        },
    )
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550111",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    first_candidate_id = await insert_worker(
        db,
        {
            "name": "James",
            "phone": "+13105550112",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 2,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    second_candidate_id = await insert_worker(
        db,
        {
            "name": "Avery",
            "phone": "+13105550113",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 3,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )

    start = datetime.utcnow() + timedelta(hours=2)
    week_start = start.date() - timedelta(days=start.date().weekday())
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
    advance = await cascade_svc.advance(db, cascade["id"])
    assert advance["mode"] == "broadcast"
    assert {delivery["worker_id"] for delivery in advance["deliveries"]} == {first_candidate_id, second_candidate_id}
    assert len(worker_offers) == 2

    first_yes = {"From": "+13105550112", "Body": "YES"}
    first_response = client.post(
        "/webhooks/twilio/sms",
        data=first_yes,
        headers=_signed_sms_headers("test-token", first_yes),
    )
    second_yes = {"From": "+13105550113", "Body": "YES"}
    second_response = client.post(
        "/webhooks/twilio/sms",
        data=second_yes,
        headers=_signed_sms_headers("test-token", second_yes),
    )
    manager_no = {"From": "+13105550110", "Body": "NO"}
    manager_response = client.post(
        "/webhooks/twilio/sms",
        data=manager_no,
        headers=_signed_sms_headers("test-token", manager_no),
    )
    coverage_after = client.get(
        f"/api/locations/{location_id}/coverage?week_start={week_start.isoformat()}"
    )

    assert first_response.status_code == 200
    assert "sent your claim to the manager for approval" in first_response.text.lower()
    assert second_response.status_code == 200
    assert "on standby as #1" in second_response.text.lower()
    assert manager_response.status_code == 200
    assert "another worker is now waiting for approval" in manager_response.text.lower()
    assert coverage_after.status_code == 200
    coverage_payload = coverage_after.json()["at_risk_shifts"][0]
    assert coverage_payload["coverage_status"] == "awaiting_manager_approval"
    assert coverage_payload["manager_action_required"] is True
    assert coverage_payload["claimed_by_worker_id"] == second_candidate_id
    assert coverage_payload["claimed_by_worker_name"] == "Avery"
    assert coverage_payload["standby_depth"] == 0
    assert len(manager_notifications) == 2
    assert "james wants to cover" in manager_notifications[0][1].lower()
    assert "avery wants to cover" in manager_notifications[1][1].lower()
    assert any("passed on your claim" in body.lower() for _, body in worker_notifications)
    assert any("sent it to the manager for approval" in body.lower() for _, body in worker_notifications)


def test_invalid_twilio_signature_is_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    response = client.post(
        "/webhooks/twilio/sms",
        data={"From": "+13105550103", "Body": "YES"},
        headers={"X-Twilio-Signature": "bad-signature"},
    )

    assert response.status_code == 403
    assert response.text == "Forbidden"


@pytest.mark.asyncio
async def test_manager_agency_reply_routes_tier3(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    location_id = await insert_location(
        db,
        {
            "name": "Agency Taco Spot",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "backfill_native",
            "agency_supply_approved": True,
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
    shift_start = datetime.utcnow() + timedelta(hours=8)
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "role": "line_cook",
            "date": shift_start.date().isoformat(),
            "start_time": shift_start.strftime("%H:%M:%S"),
            "end_time": (shift_start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 22.0,
            "requirements": ["food_handler_card"],
            "status": "scheduled",
            "source_platform": "backfill_native",
        },
    )
    await insert_agency_partner(
        db,
        {
            "name": "Fast Temps",
            "coverage_areas": ["taco"],
            "roles_supported": ["line_cook"],
            "certifications_supported": ["food_handler_card"],
            "contact_channel": "sms",
            "contact_info": "+13105550199",
            "avg_response_time_minutes": 10,
            "acceptance_rate": 0.9,
            "fill_rate": 0.9,
            "sla_tier": "priority",
        },
    )

    sent = []
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    monkeypatch.setattr("app.services.agency_router.send_sms", lambda to, body: sent.append((to, body)) or "SM999")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    result = await cascade_svc.advance(db, cascade["id"])
    assert result["status"] == "awaiting_tier3_approval"

    week_start = shift_start.date() - timedelta(days=shift_start.date().weekday())
    coverage_before = client.get(
        f"/api/locations/{location_id}/coverage?week_start={week_start.isoformat()}"
    )

    params = {"From": "+13105550100", "Body": "AGENCY"}
    response = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=_signed_sms_headers("test-token", params),
    )

    requests = await list_agency_requests(db, cascade_id=cascade["id"])
    updated_cascade = await get_cascade(db, cascade["id"])
    coverage_after = client.get(
        f"/api/locations/{location_id}/coverage?week_start={week_start.isoformat()}"
    )

    assert response.status_code == 200
    assert "agency routing approved" in response.text.lower()
    assert updated_cascade["manager_approved_tier3"] is True
    assert requests
    assert sent
    assert coverage_before.status_code == 200
    assert coverage_before.json()["at_risk_shifts"][0]["coverage_status"] == "awaiting_agency_approval"
    assert coverage_before.json()["at_risk_shifts"][0]["current_tier"] == 3
    assert coverage_before.json()["at_risk_shifts"][0]["manager_action_required"] is True
    assert coverage_after.status_code == 200
    assert coverage_after.json()["at_risk_shifts"][0]["coverage_status"] == "agency_routing"
    assert coverage_after.json()["at_risk_shifts"][0]["current_tier"] == 3
    assert coverage_after.json()["at_risk_shifts"][0]["manager_action_required"] is False


@pytest.mark.asyncio
async def test_manager_action_queue_and_api_agency_approval_flow(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    sent = []
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    monkeypatch.setattr("app.services.agency_router.send_sms", lambda to, body: sent.append((to, body)) or "SM999")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    location_id = await insert_location(
        db,
        {
            "name": "Agency Queue Taco",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550117",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
            "agency_supply_approved": True,
        },
    )
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550118",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    start = datetime.utcnow() + timedelta(hours=8)
    week_start = start.date() - timedelta(days=start.date().weekday())
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
    await insert_agency_partner(
        db,
        {
            "name": "Fast Temps",
            "coverage_areas": ["agency"],
            "roles_supported": ["line_cook"],
            "certifications_supported": ["food_handler_card"],
            "contact_channel": "sms",
            "contact_info": "+13105550199",
            "avg_response_time_minutes": 10,
            "acceptance_rate": 0.9,
            "fill_rate": 0.9,
            "sla_tier": "priority",
        },
    )

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    result = await cascade_svc.advance(db, cascade["id"])

    assert result["status"] == "awaiting_tier3_approval"

    queue = client.get(
        f"/api/locations/{location_id}/manager-actions?week_start={week_start.isoformat()}"
    )
    approve = client.post(f"/api/cascades/{cascade['id']}/approve-agency")
    queue_after = client.get(
        f"/api/locations/{location_id}/manager-actions?week_start={week_start.isoformat()}"
    )
    requests = await list_agency_requests(db, cascade_id=cascade["id"])
    updated_cascade = await get_cascade(db, cascade["id"])

    assert queue.status_code == 200
    assert queue.json()["summary"] == {
        "pending_actions": 1,
        "fill_approvals": 0,
        "agency_approvals": 1,
        "attendance_reviews": 0,
    }
    assert queue.json()["actions"][0]["action_type"] == "approve_agency"
    assert queue.json()["actions"][0]["coverage_status"] == "awaiting_agency_approval"
    assert queue.json()["actions"][0]["cascade_id"] == cascade["id"]
    assert queue.json()["actions"][0]["shift_id"] == shift_id
    assert queue.json()["actions"][0]["available_actions"] == ["approve_agency"]
    assert approve.status_code == 200
    assert approve.json()["status"] == "agency_routed"
    assert requests
    assert sent
    assert updated_cascade["manager_approved_tier3"] is True
    assert queue_after.status_code == 200
    assert queue_after.json()["summary"]["pending_actions"] == 0
    assert queue_after.json()["actions"] == []


@pytest.mark.asyncio
async def test_manager_digest_route_summarizes_upcoming_exceptions(db, client, monkeypatch):
    manager_messages = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: manager_messages.append((to, body)) or "SM-DIGEST",
    )
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    location_id = await insert_location(
        db,
        {
            "name": "Digest Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550121",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
            "coverage_requires_manager_approval": True,
        },
    )
    caller_id = await insert_worker(
        db,
        {
            "name": "Mario Cook",
            "phone": "+13105550122",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    candidate_id = await insert_worker(
        db,
        {
            "name": "Priya Cover",
            "phone": "+13105550123",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 2,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    schedule_start = date.today() - timedelta(days=date.today().weekday())
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": schedule_start.isoformat(),
            "week_end_date": (schedule_start + timedelta(days=6)).isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    coverage_shift_start = datetime.utcnow() + timedelta(hours=6)
    coverage_shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": coverage_shift_start.date().isoformat(),
            "start_time": coverage_shift_start.strftime("%H:%M:%S"),
            "end_time": (coverage_shift_start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 22.0,
            "requirements": ["food_handler_card"],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
        },
    )
    await upsert_shift_assignment(
        db,
        {
            "shift_id": coverage_shift_id,
            "worker_id": caller_id,
            "assignment_status": "assigned",
            "source": "manual",
        },
    )
    open_shift_start = datetime.utcnow() + timedelta(hours=8)
    open_shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "dishwasher",
            "date": open_shift_start.date().isoformat(),
            "start_time": open_shift_start.strftime("%H:%M:%S"),
            "end_time": (open_shift_start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 20.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
        },
    )
    await upsert_shift_assignment(
        db,
        {
            "shift_id": open_shift_id,
            "worker_id": None,
            "assignment_status": "open",
            "source": "manual",
        },
    )

    cascade = await create_vacancy(db, coverage_shift_id, caller_id, actor=f"worker:{caller_id}")
    await cascade_svc.advance(db, cascade["id"])
    claim = await cascade_svc.claim_shift(db, cascade["id"], candidate_id, summary="Accepted by SMS")

    assert claim["status"] == "awaiting_manager_approval"
    manager_messages.clear()

    digest = client.post(f"/api/locations/{location_id}/manager-digest?lookahead_hours=24")

    assert digest.status_code == 200
    assert digest.json()["summary"] == {
        "scheduled_shifts": 2,
        "open_shifts": 2,
        "active_coverage": 1,
        "attendance_issues": 0,
        "late_arrivals": 0,
        "late_arrivals_awaiting_decision": 0,
        "missed_check_ins": 0,
        "missed_check_ins_awaiting_decision": 0,
        "missed_check_ins_escalated": 0,
        "pending_actions": 1,
        "pending_fill_approvals": 1,
        "pending_agency_approvals": 0,
        "pending_attendance_reviews": 0,
    }
    expected_review_week = (
        coverage_shift_start.date() - timedelta(days=coverage_shift_start.date().weekday())
    ).isoformat()
    assert digest.json()["review_link"].endswith(
        f"/dashboard/locations/{location_id}?tab=coverage&week_start={expected_review_week}"
    )
    assert digest.json()["message_sid"] == "SM-DIGEST"
    assert manager_messages == [
        (
            "+13105550121",
            (
                f"Backfill: Next 24h for Digest Cafe: 2 shifts, 2 open shifts, "
                f"1 in coverage workflow, 1 manager action needed. Review: "
                f"{settings.backfill_web_base_url}/dashboard/locations/{location_id}?tab=coverage&week_start={expected_review_week}"
            ),
        )
    ]


@pytest.mark.asyncio
async def test_manager_schedule_sms_commands_publish_review_and_copy(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    location_id = await insert_location(
        db,
        {
            "name": "Backfill Bakery",
            "manager_name": "Ari Lead",
            "manager_phone": "+13105550200",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Sam Cook",
            "phone": "+13105550201",
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
            "date": "2026-04-13",
            "start_time": "08:00:00",
            "end_time": "16:00:00",
            "pay_rate": 21.0,
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

    approve_params = {"From": "+13105550200", "Body": "APPROVE"}
    approve = client.post(
        "/webhooks/twilio/sms",
        data=approve_params,
        headers=_signed_sms_headers("test-token", approve_params),
    )
    review_params = {"From": "+13105550200", "Body": "REVIEW"}
    review = client.post(
        "/webhooks/twilio/sms",
        data=review_params,
        headers=_signed_sms_headers("test-token", review_params),
    )
    copy_params = {"From": "+13105550200", "Body": "COPY LAST WEEK"}
    copied = client.post(
        "/webhooks/twilio/sms",
        data=copy_params,
        headers=_signed_sms_headers("test-token", copy_params),
    )

    published_schedule = await get_schedule(db, schedule_id)
    copied_schedule = await get_schedule_by_location_week(db, location_id, "2026-04-20")

    assert approve.status_code == 200
    assert "published backfill bakery" in approve.text.lower()
    assert published_schedule["lifecycle_state"] == "published"

    assert review.status_code == 200
    assert f"/dashboard/locations/{location_id}?tab=schedule" in review.text
    assert "week_start=2026-04-13" in review.text

    assert copied.status_code == 200
    assert "new draft" in copied.text.lower()
    assert copied_schedule is not None
    assert copied_schedule["lifecycle_state"] == "draft"


@pytest.mark.asyncio
async def test_manager_open_shifts_sms_command_starts_batch_offers(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    worker_offers = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    location_id = await insert_location(
        db,
        {
            "name": "Offer Command Cafe",
            "manager_name": "Ari Lead",
            "manager_phone": "+13105550205",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Nora Cover",
            "phone": "+13105550206",
            "roles": ["prep_cook"],
            "location_id": location_id,
            "priority_rank": 1,
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
            "role": "prep_cook",
            "date": "2026-04-15",
            "start_time": "09:00:00",
            "end_time": "17:00:00",
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
            "assignment_status": "open",
            "source": "manual",
        },
    )

    params = {"From": "+13105550205", "Body": "OPEN SHIFTS"}
    response = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=_signed_sms_headers("test-token", params),
    )
    cascade = await get_active_cascade_for_shift(db, shift_id)

    assert response.status_code == 200
    assert "started offering 1 open shift" in response.text.lower()
    assert "review:" in response.text.lower()
    assert cascade is not None
    assert worker_id is not None
    assert len(worker_offers) == 1
    assert worker_offers[0][0] == "+13105550206"
    assert "open shift available at offer command cafe" in worker_offers[0][1].lower()


@pytest.mark.asyncio
async def test_manager_review_prefers_action_needed_import_link(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    location_id = await insert_location(
        db,
        {
            "name": "Import Review Market",
            "manager_name": "Drew Lead",
            "manager_phone": "+13105550210",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    job_id = await insert_import_job(
        db,
        {
            "location_id": location_id,
            "import_type": "combined",
            "filename": "schedule.csv",
            "status": "action_needed",
            "mapping_json": {"mobile": "phone"},
            "summary_json": {"failed_rows": 1},
            "columns_json": ["mobile", "role"],
            "uploaded_csv": "mobile,role\n5550123,cashier\n",
        },
    )
    await insert_import_row_result(
        db,
        {
            "import_job_id": job_id,
            "row_number": 2,
            "entity_type": "shift",
            "outcome": "failed",
            "error_code": "phone_malformed",
            "error_message": "Phone number must be E.164",
            "raw_payload": {"mobile": "5550123", "role": "cashier"},
            "normalized_payload": {"phone": "5550123", "role": "cashier"},
        },
    )

    params = {"From": "+13105550210", "Body": "REVIEW"}
    response = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=_signed_sms_headers("test-token", params),
    )

    assert response.status_code == 200
    assert f"/dashboard/locations/{location_id}?tab=imports" in response.text
    assert f"job_id={job_id}" in response.text
    assert "row=2" in response.text


@pytest.mark.asyncio
async def test_manager_help_reply_is_used_for_unknown_text_without_worker_attempt(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    await insert_location(
        db,
        {
            "name": "Help Desk Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550220",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )

    params = {"From": "+13105550220", "Body": "what now"}
    response = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=_signed_sms_headers("test-token", params),
    )

    assert response.status_code == 200
    assert "reply approve or publish" in response.text.lower()


@pytest.mark.asyncio
async def test_worker_join_enrolls_and_returns_current_schedule(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    location_id = await insert_location(
        db,
        {
            "name": "Enrollment Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550230",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Maria Cook",
            "phone": "+13105550231",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "pending",
            "voice_consent_status": "pending",
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
            "role": "line_cook",
            "date": "2026-04-14",
            "start_time": "09:00:00",
            "end_time": "17:00:00",
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
            "worker_id": worker_id,
            "assignment_status": "assigned",
            "source": "manual",
        },
    )

    params = {"From": "+13105550231", "Body": "JOIN"}
    response = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=_signed_sms_headers("test-token", params),
    )

    worker = await get_worker(db, worker_id)

    assert response.status_code == 200
    response_text = response.text.lower()
    assert "enrolled for schedule updates" in response_text
    assert "current schedule for apr 13-19" in response_text
    assert "tue apr 14 09:00-17:00 line_cook" in response_text
    assert worker["sms_consent_status"] == "granted"
    assert worker["voice_consent_status"] == "granted"


@pytest.mark.asyncio
async def test_worker_callout_text_creates_vacancy_and_notifies_manager(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    manager_sms = []
    worker_offers = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: manager_sms.append((to, body)) or "SM-MANAGER",
    )
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    shift_day = date.today() + timedelta(days=1)
    week_start = shift_day - timedelta(days=shift_day.weekday())
    week_end = week_start + timedelta(days=6)

    location_id = await insert_location(
        db,
        {
            "name": "Callout Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550240",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    caller_id = await insert_worker(
        db,
        {
            "name": "Mario Cook",
            "phone": "+13105550241",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "pending",
            "voice_consent_status": "pending",
        },
    )
    replacement_id = await insert_worker(
        db,
        {
            "name": "Priya Cover",
            "phone": "+13105550242",
            "roles": ["line_cook"],
            "location_id": location_id,
            "priority_rank": 1,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": week_start.isoformat(),
            "week_end_date": week_end.isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": shift_day.isoformat(),
            "start_time": "17:00:00",
            "end_time": "23:00:00",
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
            "worker_id": caller_id,
            "assignment_status": "assigned",
            "source": "manual",
        },
    )

    params = {"From": "+13105550241", "Body": "call out tomorrow 5pm"}
    response = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=_signed_sms_headers("test-token", params),
    )

    shift = await get_shift(db, shift_id)
    cascade = await get_active_cascade_for_shift(db, shift_id)
    schedule_after_callout = client.get(
        f"/api/locations/{location_id}/schedules/current?week_start={week_start.isoformat()}"
    )
    coverage_after_callout = client.get(
        f"/api/locations/{location_id}/coverage?week_start={week_start.isoformat()}"
    )

    assert response.status_code == 200
    assert "recorded your callout" in response.text.lower()
    assert shift["status"] == "vacant"
    assert shift["called_out_by"] == caller_id
    assert cascade is not None
    assert schedule_after_callout.status_code == 200
    assert coverage_after_callout.status_code == 200
    shift_payload = schedule_after_callout.json()["shifts"][0]
    coverage_payload = coverage_after_callout.json()["at_risk_shifts"][0]
    assert shift_payload["assignment"]["worker_id"] is None
    assert shift_payload["assignment"]["assignment_status"] == "open"
    assert shift_payload["assignment"]["source"] == "coverage_engine"
    assert shift_payload["assignment"]["filled_via_backfill"] is False
    assert shift_payload["coverage"] == {
        "is_active": True,
        "status": "active",
        "vacancy_kind": "callout",
        "cascade_id": cascade["id"],
        "manager_action_required": False,
        "pending_action": None,
        "current_tier": 1,
        "claimed_by_worker_id": None,
        "claimed_by_worker_name": None,
        "claimed_at": None,
        "called_out_by": caller_id,
        "filled_by": None,
        "filled_via_backfill": False,
    }
    assert coverage_payload["coverage_status"] == "offering"
    assert coverage_payload["current_tier"] == 1
    assert coverage_payload["outreach_mode"] == "cascade"
    assert coverage_payload["manager_action_required"] is False
    assert coverage_payload["standby_depth"] == 0
    assert coverage_payload["offered_worker_count"] == 1
    assert coverage_payload["responded_worker_count"] == 0
    assert coverage_payload["last_outreach_at"] is not None
    assert coverage_payload["last_response_at"] is None
    assert len(worker_offers) == 1
    assert worker_offers[0][0] == "+13105550242"
    assert "needs coverage at callout cafe" in worker_offers[0][1].lower()
    expected_link = (
        f"{settings.backfill_web_base_url}/dashboard/locations/{location_id}"
        f"?tab=coverage&shift_id={shift_id}"
    )
    assert manager_sms == [
        (
            "+13105550240",
            (
                f"Backfill: Mario Cook called out for Callout Cafe's line_cook shift on "
                f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} at 17:00. "
                f"Coverage has started. Review: {expected_link}"
            ),
        )
    ]

    claim = await cascade_svc.claim_shift(db, cascade["id"], replacement_id, summary="Accepted by SMS")
    schedule_after_fill = client.get(
        f"/api/locations/{location_id}/schedules/current?week_start={week_start.isoformat()}"
    )
    coverage_after_fill = client.get(
        f"/api/locations/{location_id}/coverage?week_start={week_start.isoformat()}"
    )

    assert claim["status"] == "confirmed"
    assert schedule_after_fill.status_code == 200
    assert coverage_after_fill.status_code == 200
    filled_shift_payload = schedule_after_fill.json()["shifts"][0]
    assert filled_shift_payload["assignment"]["worker_id"] == replacement_id
    assert filled_shift_payload["assignment"]["worker_name"] == "Priya Cover"
    assert filled_shift_payload["assignment"]["assignment_status"] == "confirmed"
    assert filled_shift_payload["assignment"]["source"] == "coverage_engine"
    assert filled_shift_payload["assignment"]["filled_via_backfill"] is True
    assert filled_shift_payload["coverage"] == {
        "is_active": False,
        "status": "backfilled",
        "vacancy_kind": "callout",
        "cascade_id": None,
        "manager_action_required": False,
        "pending_action": None,
        "current_tier": None,
        "claimed_by_worker_id": None,
        "claimed_by_worker_name": None,
        "claimed_at": None,
        "called_out_by": caller_id,
        "filled_by": replacement_id,
        "filled_via_backfill": True,
    }
    assert coverage_after_fill.json()["at_risk_shifts"] == []


@pytest.mark.asyncio
async def test_worker_callout_text_requests_clarification_when_multiple_shifts_match(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    shift_day = date.today() + timedelta(days=1)
    week_start = shift_day - timedelta(days=shift_day.weekday())
    week_end = week_start + timedelta(days=6)

    location_id = await insert_location(
        db,
        {
            "name": "Ambiguous Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550250",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Taylor Cook",
            "phone": "+13105550251",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": week_start.isoformat(),
            "week_end_date": week_end.isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    morning_shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": shift_day.isoformat(),
            "start_time": "09:00:00",
            "end_time": "13:00:00",
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
        },
    )
    evening_shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": shift_day.isoformat(),
            "start_time": "17:00:00",
            "end_time": "21:00:00",
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
        },
    )
    for shift_id in (morning_shift_id, evening_shift_id):
        await upsert_shift_assignment(
            db,
            {
                "shift_id": shift_id,
                "worker_id": worker_id,
                "assignment_status": "assigned",
                "source": "manual",
            },
        )

    params = {"From": "+13105550251", "Body": "call out tomorrow"}
    response = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=_signed_sms_headers("test-token", params),
    )

    morning_shift = await get_shift(db, morning_shift_id)
    evening_shift = await get_shift(db, evening_shift_id)

    assert response.status_code == 200
    assert "more than one upcoming scheduled shift" in response.text.lower()
    assert morning_shift["status"] == "scheduled"
    assert evening_shift["status"] == "scheduled"
    assert await get_active_cascade_for_shift(db, morning_shift_id) is None
    assert await get_active_cascade_for_shift(db, evening_shift_id) is None


@pytest.mark.asyncio
async def test_internal_confirmation_request_route_marks_shift_pending(db, client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: sent.append((to, body)) or "SM-CONFIRM",
    )

    location_id = await insert_location(
        db,
        {
            "name": "Confirm Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550260",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Ari Cook",
            "phone": "+13105550261",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    start = datetime.utcnow() + timedelta(minutes=90)
    week_start = start.date() - timedelta(days=start.date().weekday())
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": week_start.isoformat(),
            "week_end_date": (week_start + timedelta(days=6)).isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
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
            "worker_id": worker_id,
            "assignment_status": "assigned",
            "source": "manual",
        },
    )

    response = client.post("/api/internal/backfill-shifts/send-confirmation-requests?within_minutes=120")
    shift = await get_shift(db, shift_id)
    schedule_view = client.get(
        f"/api/locations/{location_id}/schedules/current?week_start={week_start.isoformat()}"
    )

    assert response.status_code == 200
    assert response.json() == {
        "within_minutes": 120,
        "sent_count": 1,
        "sent_shift_ids": [shift_id],
        "skipped_shift_ids": [],
        "failed_shift_ids": [],
    }
    assert shift["confirmation_requested_at"] is not None
    assert schedule_view.status_code == 200
    assert schedule_view.json()["shifts"][0]["confirmation"]["status"] == "pending"
    assert len(sent) == 1
    assert sent[0][0] == "+13105550261"
    assert "please confirm your line_cook shift" in sent[0][1].lower()
    assert "reply yes if you're still coming or no if you can't make it" in sent[0][1].lower()


@pytest.mark.asyncio
async def test_worker_yes_confirms_pending_shift_confirmation(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    worker_messages = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: worker_messages.append((to, body)) or "SM-WORKER",
    )

    location_id = await insert_location(
        db,
        {
            "name": "Confirm Reply Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550270",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Nina Cook",
            "phone": "+13105550271",
            "roles": ["line_cook"],
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
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
            "confirmation_requested_at": datetime.utcnow().isoformat(),
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
    await db.execute(
        "UPDATE shifts SET confirmation_requested_at=? WHERE id=?",
        (datetime.utcnow().isoformat(), shift_id),
    )
    await db.commit()

    params = {"From": "+13105550271", "Body": "YES"}
    response = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=_signed_sms_headers("test-token", params),
    )
    shift = await get_shift(db, shift_id)

    assert response.status_code == 200
    assert "confirmed" in response.text.lower()
    assert shift["worker_confirmed_at"] is not None
    assert len(worker_messages) == 1
    assert worker_messages[0][0] == "+13105550271"
    assert "thanks, you're confirmed" in worker_messages[0][1].lower()


@pytest.mark.asyncio
async def test_worker_no_from_pending_confirmation_starts_coverage(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    manager_messages = []
    worker_offers = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: manager_messages.append((to, body)) or "SM-MANAGER",
    )
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )
    async def _fake_call(*, to_number, metadata, agent_id=None):
        return "CA123"

    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)

    location_id = await insert_location(
        db,
        {
            "name": "Decline Confirm Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550280",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Declining Cook",
            "phone": "+13105550281",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    replacement_id = await insert_worker(
        db,
        {
            "name": "Backup Cook",
            "phone": "+13105550282",
            "roles": ["line_cook"],
            "location_id": location_id,
            "priority_rank": 1,
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
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
            "confirmation_requested_at": datetime.utcnow().isoformat(),
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
    await db.execute(
        "UPDATE shifts SET confirmation_requested_at=? WHERE id=?",
        (datetime.utcnow().isoformat(), shift_id),
    )
    await db.commit()

    params = {"From": "+13105550281", "Body": "NO"}
    response = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=_signed_sms_headers("test-token", params),
    )
    shift = await get_shift(db, shift_id)
    cascade = await get_active_cascade_for_shift(db, shift_id)

    assert response.status_code == 200
    assert "started finding coverage" in response.text.lower()
    assert shift["status"] == "vacant"
    assert shift["called_out_by"] == worker_id
    assert cascade is not None
    assert len(worker_offers) == 1
    assert worker_offers[0][0] == "+13105550282"
    assert len(manager_messages) == 1
    assert "called out" in manager_messages[0][1].lower()
    assert replacement_id is not None


@pytest.mark.asyncio
async def test_internal_unconfirmed_escalation_route_starts_coverage(db, client, monkeypatch):
    manager_messages = []
    worker_offers = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: manager_messages.append((to, body)) or "SM-MANAGER",
    )
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )
    async def _fake_call(*, to_number, metadata, agent_id=None):
        return "CA123"

    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)

    location_id = await insert_location(
        db,
        {
            "name": "No Show Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550290",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Missing Cook",
            "phone": "+13105550291",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    await insert_worker(
        db,
        {
            "name": "Cover Cook",
            "phone": "+13105550292",
            "roles": ["line_cook"],
            "location_id": location_id,
            "priority_rank": 1,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    start = datetime.utcnow() + timedelta(minutes=10)
    week_start = start.date() - timedelta(days=start.date().weekday())
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": week_start.isoformat(),
            "week_end_date": (week_start + timedelta(days=6)).isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
            "confirmation_requested_at": (datetime.utcnow() - timedelta(minutes=30)).isoformat(),
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
    await db.execute(
        "UPDATE shifts SET confirmation_requested_at=? WHERE id=?",
        ((datetime.utcnow() - timedelta(minutes=30)).isoformat(), shift_id),
    )
    await db.commit()

    response = client.post("/api/internal/backfill-shifts/escalate-unconfirmed-shifts?within_minutes=15")
    shift = await get_shift(db, shift_id)
    cascade = await get_active_cascade_for_shift(db, shift_id)
    schedule_view = client.get(
        f"/api/locations/{location_id}/schedules/current?week_start={week_start.isoformat()}"
    )

    assert response.status_code == 200
    assert response.json() == {
        "within_minutes": 15,
        "escalated_count": 1,
        "escalated_shift_ids": [shift_id],
        "skipped_shift_ids": [],
    }
    assert shift["status"] == "vacant"
    assert shift["called_out_by"] is None
    assert shift["confirmation_escalated_at"] is not None
    assert cascade is not None
    assert len(worker_offers) == 1
    assert len(manager_messages) == 1
    assert "hasn't confirmed" in manager_messages[0][1].lower()
    assert schedule_view.status_code == 200
    shift_payload = schedule_view.json()["shifts"][0]
    assert shift_payload["confirmation"]["status"] == "escalated"
    assert shift_payload["coverage"]["status"] == "active"


@pytest.mark.asyncio
async def test_internal_check_in_request_route_marks_attendance_pending(db, client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: sent.append((to, body)) or "SM-CHECKIN",
    )

    location_id = await insert_location(
        db,
        {
            "name": "Check In Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550300",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Check In Cook",
            "phone": "+13105550301",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    start = datetime.utcnow() + timedelta(minutes=10)
    week_start = start.date() - timedelta(days=start.date().weekday())
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": week_start.isoformat(),
            "week_end_date": (week_start + timedelta(days=6)).isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
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
            "worker_id": worker_id,
            "assignment_status": "assigned",
            "source": "manual",
        },
    )

    response = client.post("/api/internal/backfill-shifts/send-check-in-requests?within_minutes=15")
    shift = await get_shift(db, shift_id)
    schedule_view = client.get(
        f"/api/locations/{location_id}/schedules/current?week_start={week_start.isoformat()}"
    )

    assert response.status_code == 200
    assert response.json() == {
        "within_minutes": 15,
        "sent_count": 1,
        "sent_shift_ids": [shift_id],
        "skipped_shift_ids": [],
        "failed_shift_ids": [],
    }
    assert shift["check_in_requested_at"] is not None
    assert schedule_view.status_code == 200
    assert schedule_view.json()["shifts"][0]["attendance"]["status"] == "pending"
    assert len(sent) == 1
    assert sent[0][0] == "+13105550301"
    assert "reply here when you arrive or late 15" in sent[0][1].lower()


@pytest.mark.asyncio
async def test_worker_here_checks_in_after_request(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    location_id = await insert_location(
        db,
        {
            "name": "Here Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550310",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Arriving Cook",
            "phone": "+13105550311",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    start = datetime.utcnow() + timedelta(minutes=5)
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "role": "line_cook",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
            "check_in_requested_at": datetime.utcnow().isoformat(),
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
    await db.execute(
        "UPDATE shifts SET check_in_requested_at=? WHERE id=?",
        (datetime.utcnow().isoformat(), shift_id),
    )
    await db.commit()

    params = {"From": "+13105550311", "Body": "HERE"}
    response = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=_signed_sms_headers("test-token", params),
    )
    shift = await get_shift(db, shift_id)

    assert response.status_code == 200
    assert "checked in" in response.text.lower()
    assert shift["checked_in_at"] is not None
    assert shift["late_reported_at"] is None


@pytest.mark.asyncio
async def test_worker_late_reply_updates_attendance_and_notifies_manager(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    manager_messages = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: manager_messages.append((to, body)) or "SM-MANAGER",
    )

    location_id = await insert_location(
        db,
        {
            "name": "Late Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550320",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Late Cook",
            "phone": "+13105550321",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    start = datetime.utcnow() + timedelta(minutes=5)
    week_start = start.date() - timedelta(days=start.date().weekday())
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": week_start.isoformat(),
            "week_end_date": (week_start + timedelta(days=6)).isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
            "check_in_requested_at": datetime.utcnow().isoformat(),
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
    await db.execute(
        "UPDATE shifts SET check_in_requested_at=? WHERE id=?",
        (datetime.utcnow().isoformat(), shift_id),
    )
    await db.commit()

    params = {"From": "+13105550321", "Body": "late 20"}
    response = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=_signed_sms_headers("test-token", params),
    )
    shift = await get_shift(db, shift_id)
    schedule_view = client.get(
        f"/api/locations/{location_id}/schedules/current?week_start={week_start.isoformat()}"
    )

    assert response.status_code == 200
    assert "20 minutes late" in response.text.lower()
    assert shift["late_reported_at"] is not None
    assert shift["late_eta_minutes"] == 20
    assert len(manager_messages) == 1
    assert "20 minutes late" in manager_messages[0][1].lower()
    assert schedule_view.status_code == 200
    assert schedule_view.json()["shifts"][0]["attendance"]["status"] == "late"
    assert schedule_view.json()["summary"]["attendance_issues"] == 1

    manager_messages.clear()
    digest = client.post(f"/api/locations/{location_id}/manager-digest?lookahead_hours=24")
    assert digest.status_code == 200
    assert digest.json()["summary"]["attendance_issues"] == 1
    assert digest.json()["summary"]["late_arrivals"] == 1
    assert digest.json()["summary"]["late_arrivals_awaiting_decision"] == 0
    assert digest.json()["summary"]["missed_check_ins"] == 0
    assert len(manager_messages) == 1
    assert "1 late reported" in manager_messages[0][1].lower()


@pytest.mark.asyncio
async def test_manager_digest_breaks_out_late_decisions_and_missed_check_in_escalations(db, client, monkeypatch):
    manager_messages = []
    worker_offers = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: manager_messages.append((to, body)) or "SM-DIGEST",
    )
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )

    async def _fake_call(*, to_number, metadata, agent_id=None):
        return "CA123"

    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)

    location_id = await insert_location(
        db,
        {
            "name": "Digest Attendance Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550324",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
            "late_arrival_policy": "manager_action",
        },
    )
    late_worker_id = await insert_worker(
        db,
        {
            "name": "Late Digest Cook",
            "phone": "+13105550344",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    missed_worker_id = await insert_worker(
        db,
        {
            "name": "Missed Digest Cook",
            "phone": "+13105550345",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    await insert_worker(
        db,
        {
            "name": "Coverage Backup Cook",
            "phone": "+13105550346",
            "roles": ["line_cook"],
            "location_id": location_id,
            "priority_rank": 1,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    now = datetime.utcnow()
    week_start = now.date() - timedelta(days=now.date().weekday())
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": week_start.isoformat(),
            "week_end_date": (week_start + timedelta(days=6)).isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    late_start = now + timedelta(hours=1)
    late_shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": late_start.date().isoformat(),
            "start_time": late_start.strftime("%H:%M:%S"),
            "end_time": (late_start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
            "check_in_requested_at": datetime.utcnow().isoformat(),
            "late_reported_at": datetime.utcnow().isoformat(),
            "late_eta_minutes": 20,
        },
    )
    missed_start = now - timedelta(minutes=20)
    missed_shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": missed_start.date().isoformat(),
            "start_time": missed_start.strftime("%H:%M:%S"),
            "end_time": (missed_start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
            "check_in_requested_at": (datetime.utcnow() - timedelta(minutes=25)).isoformat(),
        },
    )
    await upsert_shift_assignment(
        db,
        {
            "shift_id": late_shift_id,
            "worker_id": late_worker_id,
            "assignment_status": "assigned",
            "source": "manual",
        },
    )
    await upsert_shift_assignment(
        db,
        {
            "shift_id": missed_shift_id,
            "worker_id": missed_worker_id,
            "assignment_status": "assigned",
            "source": "manual",
        },
    )

    escalated = client.post(
        f"/api/internal/backfill-shifts/escalate-missed-check-ins?grace_minutes=10&location_id={location_id}"
    )
    manager_messages.clear()
    digest = client.post(f"/api/locations/{location_id}/manager-digest?lookahead_hours=24")

    assert escalated.status_code == 200
    assert digest.status_code == 200
    assert digest.json()["summary"] == {
        "scheduled_shifts": 2,
        "open_shifts": 1,
        "active_coverage": 1,
        "attendance_issues": 2,
        "late_arrivals": 1,
        "late_arrivals_awaiting_decision": 1,
        "missed_check_ins": 1,
        "missed_check_ins_awaiting_decision": 0,
        "missed_check_ins_escalated": 1,
        "pending_actions": 1,
        "pending_fill_approvals": 0,
        "pending_agency_approvals": 0,
        "pending_attendance_reviews": 1,
    }
    assert len(manager_messages) == 1
    assert "1 late awaiting decision" in manager_messages[0][1].lower()
    assert "1 missed check-in escalated" in manager_messages[0][1].lower()


@pytest.mark.asyncio
async def test_worker_late_reply_can_start_coverage_per_location_policy(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    manager_messages = []
    worker_offers = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: manager_messages.append((to, body)) or "SM-MANAGER",
    )
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )

    async def _fake_call(*, to_number, metadata, agent_id=None):
        return "CA123"

    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)

    location_id = await insert_location(
        db,
        {
            "name": "Late Auto Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550325",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
            "late_arrival_policy": "start_coverage",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Late Cook",
            "phone": "+13105550326",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    await insert_worker(
        db,
        {
            "name": "Backup Cook",
            "phone": "+13105550327",
            "roles": ["line_cook"],
            "location_id": location_id,
            "priority_rank": 1,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    start = datetime.utcnow() + timedelta(minutes=5)
    week_start = start.date() - timedelta(days=start.date().weekday())
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": week_start.isoformat(),
            "week_end_date": (week_start + timedelta(days=6)).isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
            "check_in_requested_at": datetime.utcnow().isoformat(),
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

    params = {"From": "+13105550326", "Body": "late 15"}
    response = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=_signed_sms_headers("test-token", params),
    )
    shift = await get_shift(db, shift_id)
    cascade = await get_active_cascade_for_shift(db, shift_id)

    assert response.status_code == 200
    assert "started coverage" in response.text.lower()
    assert shift["status"] == "vacant"
    assert shift["check_in_escalated_at"] is not None
    assert cascade is not None
    assert len(worker_offers) == 1
    assert len(manager_messages) == 1
    assert "coverage has started" in manager_messages[0][1].lower()


@pytest.mark.asyncio
async def test_late_arrival_manager_action_queue_can_wait_or_start_coverage(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    manager_messages = []
    worker_offers = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: manager_messages.append((to, body)) or "SM-MANAGER",
    )
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )

    async def _fake_call(*, to_number, metadata, agent_id=None):
        return "CA123"

    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)

    location_id = await insert_location(
        db,
        {
            "name": "Late Queue Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550328",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
            "late_arrival_policy": "manager_action",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Late Queue Cook",
            "phone": "+13105550329",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    await insert_worker(
        db,
        {
            "name": "Backup Queue Cook",
            "phone": "+13105550340",
            "roles": ["line_cook"],
            "location_id": location_id,
            "priority_rank": 1,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    start = datetime.utcnow() + timedelta(minutes=5)
    week_start = start.date() - timedelta(days=start.date().weekday())
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": week_start.isoformat(),
            "week_end_date": (week_start + timedelta(days=6)).isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
            "check_in_requested_at": datetime.utcnow().isoformat(),
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

    params = {"From": "+13105550329", "Body": "late 20"}
    response = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=_signed_sms_headers("test-token", params),
    )
    queue = client.get(
        f"/api/locations/{location_id}/manager-actions?week_start={week_start.isoformat()}"
    )
    schedule_view = client.get(
        f"/api/locations/{location_id}/schedules/current?week_start={week_start.isoformat()}"
    )

    assert response.status_code == 200
    assert "20 minutes late" in response.text.lower()
    assert len(manager_messages) == 1
    assert queue.status_code == 200
    assert schedule_view.status_code == 200
    queue_payload = queue.json()
    assert queue_payload["summary"]["attendance_reviews"] == 1
    assert queue_payload["actions"][0]["action_type"] == "review_late_arrival"
    assert queue_payload["actions"][0]["available_actions"] == ["wait_for_worker", "start_coverage"]
    assert schedule_view.json()["summary"]["action_required_count"] == 1
    assert schedule_view.json()["summary"]["critical_count"] == 0
    assert schedule_view.json()["exceptions"][0]["code"] == "late_arrival_needs_review"
    assert schedule_view.json()["exceptions"][0]["action_required"] is True
    assert schedule_view.json()["exceptions"][0]["available_actions"] == ["wait_for_worker", "start_coverage"]
    assert schedule_view.json()["exceptions"][0]["late_eta_minutes"] == 20

    wait = client.post(f"/api/shifts/{shift_id}/attendance/wait")
    queue_after_wait = client.get(
        f"/api/locations/{location_id}/manager-actions?week_start={week_start.isoformat()}"
    )

    assert wait.status_code == 200
    assert wait.json()["status"] == "waiting_for_worker"
    assert queue_after_wait.status_code == 200
    assert queue_after_wait.json()["actions"] == []

    start_coverage = client.post(f"/api/shifts/{shift_id}/attendance/start-coverage")
    shift = await get_shift(db, shift_id)
    cascade = await get_active_cascade_for_shift(db, shift_id)

    assert start_coverage.status_code == 200
    assert start_coverage.json()["status"] == "coverage_started"
    assert start_coverage.json()["issue_type"] == "late_arrival"
    assert shift["status"] == "vacant"
    assert cascade is not None
    assert len(worker_offers) == 1


@pytest.mark.asyncio
async def test_schedule_exception_queue_groups_schedule_attention_items(db, client, monkeypatch):
    monkeypatch.setattr("app.services.notifications.send_sms", lambda to, body: "SM-NOTIFY")
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    location_id = await insert_location(
        db,
        {
            "name": "Exception Queue Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550347",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
            "coverage_requires_manager_approval": True,
            "late_arrival_policy": "manager_action",
        },
    )
    caller_id = await insert_worker(
        db,
        {
            "name": "Mario Cook",
            "phone": "+13105550348",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    replacement_id = await insert_worker(
        db,
        {
            "name": "Priya Cover",
            "phone": "+13105550349",
            "roles": ["line_cook"],
            "location_id": location_id,
            "priority_rank": 1,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    late_review_worker_id = await insert_worker(
        db,
        {
            "name": "Late Review Cook",
            "phone": "+13105550350",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    late_wait_worker_id = await insert_worker(
        db,
        {
            "name": "Late Wait Cook",
            "phone": "+13105550351",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )

    shift_day = date.today() + timedelta(days=1)
    week_start = shift_day - timedelta(days=shift_day.weekday())
    week_end = week_start + timedelta(days=6)
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": week_start.isoformat(),
            "week_end_date": week_end.isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )

    fill_shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": shift_day.isoformat(),
            "start_time": "09:00:00",
            "end_time": "17:00:00",
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
        },
    )
    late_review_shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": shift_day.isoformat(),
            "start_time": "12:00:00",
            "end_time": "20:00:00",
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
            "check_in_requested_at": datetime.utcnow().isoformat(),
            "late_reported_at": datetime.utcnow().isoformat(),
            "late_eta_minutes": 20,
        },
    )
    late_wait_shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": shift_day.isoformat(),
            "start_time": "14:00:00",
            "end_time": "22:00:00",
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
            "check_in_requested_at": datetime.utcnow().isoformat(),
            "late_reported_at": datetime.utcnow().isoformat(),
            "late_eta_minutes": 10,
            "attendance_action_state": "waiting_for_worker",
        },
    )

    await upsert_shift_assignment(
        db,
        {
            "shift_id": fill_shift_id,
            "worker_id": caller_id,
            "assignment_status": "assigned",
            "source": "manual",
        },
    )
    await upsert_shift_assignment(
        db,
        {
            "shift_id": late_review_shift_id,
            "worker_id": late_review_worker_id,
            "assignment_status": "assigned",
            "source": "manual",
        },
    )
    await upsert_shift_assignment(
        db,
        {
            "shift_id": late_wait_shift_id,
            "worker_id": late_wait_worker_id,
            "assignment_status": "assigned",
            "source": "manual",
        },
    )

    cascade = await create_vacancy(db, fill_shift_id, caller_id, actor=f"worker:{caller_id}")
    await cascade_svc.advance(db, cascade["id"])
    claim = await cascade_svc.claim_shift(db, cascade["id"], replacement_id, summary="Accepted by SMS")

    response = client.get(
        f"/api/locations/{location_id}/schedule-exceptions?week_start={week_start.isoformat()}"
    )
    action_only = client.get(
        f"/api/locations/{location_id}/schedule-exceptions?week_start={week_start.isoformat()}&action_required_only=true"
    )

    assert claim["status"] == "awaiting_manager_approval"
    assert response.status_code == 200
    assert action_only.status_code == 200

    payload = response.json()
    assert payload["schedule"]["id"] == schedule_id
    assert payload["filters"] == {"action_required_only": False}
    assert payload["summary"] == {
        "total_items": 3,
        "action_required": 2,
        "critical": 1,
        "coverage": 1,
        "attendance": 2,
        "open_shifts": 0,
    }
    assert [group["key"] for group in payload["groups"]] == [
        "action_required",
        "coverage",
        "attendance",
    ]
    assert payload["groups"][0]["count"] == 2
    assert payload["groups"][1]["count"] == 1
    assert payload["groups"][2]["count"] == 2
    assert [item["code"] for item in payload["items"]] == [
        "coverage_fill_approval_required",
        "late_arrival_needs_review",
        "late_arrival_reported",
    ]
    assert payload["items"][0]["claimed_by_worker_id"] == replacement_id
    assert payload["items"][0]["claimed_by_worker_name"] == "Priya Cover"
    assert payload["items"][1]["shift_id"] == late_review_shift_id
    assert payload["items"][2]["shift_id"] == late_wait_shift_id

    action_only_payload = action_only.json()
    assert action_only_payload["filters"] == {"action_required_only": True}
    assert action_only_payload["summary"] == {
        "total_items": 2,
        "action_required": 2,
        "critical": 1,
        "coverage": 1,
        "attendance": 1,
        "open_shifts": 0,
    }
    assert [item["code"] for item in action_only_payload["items"]] == [
        "coverage_fill_approval_required",
        "late_arrival_needs_review",
    ]


@pytest.mark.asyncio
async def test_schedule_exception_actions_route_dispatches_and_refreshes_queue(db, client, monkeypatch):
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM-OFFER")
    monkeypatch.setattr("app.services.notifications.send_sms", lambda to, body: "SM-NOTIFY")
    monkeypatch.setattr("app.services.agency_router.send_sms", lambda to, body: "SM-AGENCY")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    location_id = await insert_location(
        db,
        {
            "name": "Action Queue Grill",
            "manager_name": "Ivy Lead",
            "manager_phone": "+13105550331",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
            "coverage_requires_manager_approval": True,
            "late_arrival_policy": "manager_action",
        },
    )
    caller_id = await insert_worker(
        db,
        {
            "name": "Maria Caller",
            "phone": "+13105550332",
            "roles": ["line_cook"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    replacement_id = await insert_worker(
        db,
        {
            "name": "Priya Cover",
            "phone": "+13105550333",
            "roles": ["line_cook"],
            "priority_rank": 2,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    late_worker_id = await insert_worker(
        db,
        {
            "name": "Late Cook",
            "phone": "+13105550334",
            "roles": ["line_cook"],
            "priority_rank": 10,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )

    week_start = date(2026, 4, 13)
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": week_start.isoformat(),
            "week_end_date": (week_start + timedelta(days=6)).isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    fill_shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": (week_start + timedelta(days=1)).isoformat(),
            "start_time": "09:00:00",
            "end_time": "17:00:00",
            "pay_rate": 22.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
        },
    )
    late_shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": (week_start + timedelta(days=1)).isoformat(),
            "start_time": "12:00:00",
            "end_time": "20:00:00",
            "pay_rate": 22.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
            "check_in_requested_at": datetime.utcnow().isoformat(),
            "late_reported_at": datetime.utcnow().isoformat(),
            "late_eta_minutes": 15,
        },
    )

    await upsert_shift_assignment(
        db,
        {
            "shift_id": fill_shift_id,
            "worker_id": caller_id,
            "assignment_status": "assigned",
            "source": "manual",
        },
    )
    await upsert_shift_assignment(
        db,
        {
            "shift_id": late_shift_id,
            "worker_id": late_worker_id,
            "assignment_status": "assigned",
            "source": "manual",
        },
    )

    cascade = await create_vacancy(db, fill_shift_id, caller_id, actor=f"worker:{caller_id}")
    await cascade_svc.advance(db, cascade["id"])
    claim = await cascade_svc.claim_shift(db, cascade["id"], replacement_id, summary="Accepted by SMS")

    response = client.post(
        f"/api/locations/{location_id}/schedule-exceptions/actions",
        json={
            "week_start": week_start.isoformat(),
            "actions": [
                {
                    "shift_id": fill_shift_id,
                    "code": "coverage_fill_approval_required",
                    "action": "approve_fill",
                },
                {
                    "shift_id": late_shift_id,
                    "code": "late_arrival_needs_review",
                    "action": "wait_for_worker",
                },
            ],
        },
    )

    fill_shift_after = await get_shift(db, fill_shift_id)
    late_shift_after = await get_shift(db, late_shift_id)
    cascade_after = await get_cascade(db, cascade["id"])

    assert claim["status"] == "awaiting_manager_approval"
    assert response.status_code == 200
    payload = response.json()
    assert payload["processed_count"] == 2
    assert payload["success_count"] == 2
    assert payload["error_count"] == 0
    assert [item["code"] for item in payload["results"]] == [
        "coverage_fill_approval_required",
        "late_arrival_needs_review",
    ]
    assert payload["results"][0]["status"] == "ok"
    assert payload["results"][0]["result"]["status"] == "confirmed"
    assert payload["results"][1]["status"] == "ok"
    assert payload["results"][1]["result"]["status"] == "waiting_for_worker"
    assert fill_shift_after["status"] == "filled"
    assert fill_shift_after["filled_by"] == replacement_id
    assert cascade_after["confirmed_worker_id"] == replacement_id
    assert cascade_after["pending_claim_worker_id"] is None
    assert late_shift_after["attendance_action_state"] == "waiting_for_worker"
    assert payload["queue"]["summary"] == {
        "total_items": 1,
        "action_required": 0,
        "critical": 0,
        "coverage": 0,
        "attendance": 1,
        "open_shifts": 0,
    }
    assert [item["code"] for item in payload["queue"]["items"]] == ["late_arrival_reported"]
    assert payload["queue"]["items"][0]["shift_id"] == late_shift_id


@pytest.mark.asyncio
async def test_open_shift_exception_can_start_coverage_and_refresh_queue(db, client, monkeypatch):
    worker_offers = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )
    monkeypatch.setattr("app.services.agency_router.send_sms", lambda to, body: "SM-AGENCY")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    location_id = await insert_location(
        db,
        {
            "name": "Open Shift Bistro",
            "manager_name": "Alex Lead",
            "manager_phone": "+13105550351",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    candidate_id = await insert_worker(
        db,
        {
            "name": "Casey Cover",
            "phone": "+13105550352",
            "roles": ["line_cook"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    week_start = date(2026, 4, 20)
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": week_start.isoformat(),
            "week_end_date": (week_start + timedelta(days=6)).isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": (week_start + timedelta(days=2)).isoformat(),
            "start_time": "09:00:00",
            "end_time": "17:00:00",
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
            "assignment_status": "open",
            "source": "manual",
        },
    )

    queue_before = client.get(
        f"/api/locations/{location_id}/schedule-exceptions?week_start={week_start.isoformat()}"
    )
    assert queue_before.status_code == 200
    assert queue_before.json()["items"] == [
        {
            "exception_id": f"open_shift_unassigned:{shift_id}",
            "type": "open_shift",
            "code": "open_shift_unassigned",
            "severity": "warning",
            "action_required": True,
            "available_actions": ["start_coverage", "close_shift"],
            "shift_id": shift_id,
            "role": "line_cook",
            "date": (week_start + timedelta(days=2)).isoformat(),
            "start_time": "09:00:00",
            "message": f"No assignee found for line_cook on {(week_start + timedelta(days=2)).isoformat()}",
            "current_status": "scheduled",
            "assignment_status": "open",
            "cascade_id": None,
            "pending_action": None,
            "coverage_status": "none",
            "vacancy_kind": "open_shift",
            "attendance_status": "not_applicable",
            "worker_id": None,
            "worker_name": None,
            "claimed_by_worker_id": None,
            "claimed_by_worker_name": None,
            "late_eta_minutes": None,
        }
    ]

    started = client.post(
        f"/api/locations/{location_id}/schedule-exceptions/actions",
        json={
            "week_start": week_start.isoformat(),
            "actions": [
                {
                    "shift_id": shift_id,
                    "code": "open_shift_unassigned",
                    "action": "start_coverage",
                }
            ],
        },
    )
    shift_after = await get_shift(db, shift_id)
    active_cascade = await get_active_cascade_for_shift(db, shift_id)
    schedule_view = client.get(
        f"/api/locations/{location_id}/schedules/current?week_start={week_start.isoformat()}"
    )
    route_idempotent = client.post(f"/api/shifts/{shift_id}/coverage/start")

    assert started.status_code == 200
    assert started.json()["processed_count"] == 1
    assert started.json()["success_count"] == 1
    assert started.json()["error_count"] == 0
    assert started.json()["results"][0]["code"] == "open_shift_unassigned"
    assert started.json()["results"][0]["action"] == "start_coverage"
    assert started.json()["results"][0]["result"]["status"] == "coverage_started"
    assert shift_after["status"] == "vacant"
    assert active_cascade is not None
    assert started.json()["results"][0]["result"]["cascade_id"] == active_cascade["id"]
    assert route_idempotent.status_code == 200
    assert route_idempotent.json() == {
        "status": "coverage_active",
        "shift_id": shift_id,
        "cascade_id": active_cascade["id"],
        "idempotent": True,
    }
    assert schedule_view.status_code == 200
    assert schedule_view.json()["summary"]["action_required_count"] == 0
    assert schedule_view.json()["exceptions"][0]["code"] == "coverage_active"
    assert schedule_view.json()["exceptions"][0]["action_required"] is False
    assert started.json()["queue"]["summary"] == {
        "total_items": 1,
        "action_required": 0,
        "critical": 1,
        "coverage": 1,
        "attendance": 0,
        "open_shifts": 0,
    }
    assert [item["code"] for item in started.json()["queue"]["items"]] == ["coverage_active"]
    assert worker_offers
    assert "open shift available at open shift bistro" in worker_offers[0][1].lower()


@pytest.mark.asyncio
async def test_open_shift_offer_can_cancel_and_refresh_queue(db, client, monkeypatch):
    worker_offers = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )
    monkeypatch.setattr("app.services.agency_router.send_sms", lambda to, body: "SM-AGENCY")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    location_id = await insert_location(
        db,
        {
            "name": "Cancel Offer Cafe",
            "manager_name": "Alex Lead",
            "manager_phone": "+13105550353",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    await insert_worker(
        db,
        {
            "name": "Casey Cover",
            "phone": "+13105550354",
            "roles": ["line_cook"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    week_start = date(2026, 4, 20)
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": week_start.isoformat(),
            "week_end_date": (week_start + timedelta(days=6)).isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": (week_start + timedelta(days=2)).isoformat(),
            "start_time": "09:00:00",
            "end_time": "17:00:00",
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
            "assignment_status": "open",
            "source": "manual",
        },
    )

    started = client.post(f"/api/shifts/{shift_id}/coverage/start")
    cancelled = client.post(f"/api/shifts/{shift_id}/coverage/cancel")
    shift_after = await get_shift(db, shift_id)
    active_cascade_after = await get_active_cascade_for_shift(db, shift_id)
    schedule_view = client.get(
        f"/api/locations/{location_id}/schedules/current?week_start={week_start.isoformat()}"
    )
    queue_view = client.get(
        f"/api/locations/{location_id}/schedule-exceptions?week_start={week_start.isoformat()}"
    )
    idempotent_cancel = client.post(f"/api/shifts/{shift_id}/coverage/cancel")

    assert started.status_code == 200
    assert cancelled.status_code == 200
    assert cancelled.json() == {
        "status": "offer_cancelled",
        "shift_id": shift_id,
        "cascade_id": started.json()["cascade_id"],
        "idempotent": False,
        "shift": shift_after,
    }
    assert shift_after["status"] == "scheduled"
    assert active_cascade_after is None
    assert schedule_view.status_code == 200
    assert schedule_view.json()["summary"]["open_shifts"] == 1
    assert schedule_view.json()["exceptions"][0]["code"] == "open_shift_unassigned"
    assert schedule_view.json()["exceptions"][0]["available_actions"] == ["start_coverage", "close_shift"]
    assert schedule_view.json()["exceptions"][0]["vacancy_kind"] == "open_shift"
    assert queue_view.status_code == 200
    assert [item["code"] for item in queue_view.json()["items"]] == ["open_shift_unassigned"]
    assert queue_view.json()["items"][0]["available_actions"] == ["start_coverage", "close_shift"]
    assert idempotent_cancel.status_code == 200
    assert idempotent_cancel.json() == {
        "status": "offer_not_active",
        "shift_id": shift_id,
        "idempotent": True,
    }
    assert worker_offers


@pytest.mark.asyncio
async def test_open_shift_can_close_without_deleting_and_drop_from_exceptions(db, client):
    location_id = await insert_location(
        db,
        {
            "name": "Close Shift Cafe",
            "manager_name": "Alex Lead",
            "manager_phone": "+13105550355",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    week_start = date(2026, 4, 20)
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": week_start.isoformat(),
            "week_end_date": (week_start + timedelta(days=6)).isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": (week_start + timedelta(days=2)).isoformat(),
            "start_time": "09:00:00",
            "end_time": "17:00:00",
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
            "assignment_status": "open",
            "source": "manual",
        },
    )

    closed = client.post(f"/api/shifts/{shift_id}/open-shift/close")
    schedule_view = client.get(
        f"/api/locations/{location_id}/schedules/current?week_start={week_start.isoformat()}"
    )
    coverage_view = client.get(
        f"/api/locations/{location_id}/coverage?week_start={week_start.isoformat()}"
    )
    queue_view = client.get(
        f"/api/locations/{location_id}/schedule-exceptions?week_start={week_start.isoformat()}"
    )
    restarted = client.post(f"/api/shifts/{shift_id}/coverage/start")
    idempotent_close = client.post(f"/api/shifts/{shift_id}/open-shift/close")

    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert closed.json()["cascade_cancelled"] is False
    assert closed.json()["assignment"]["assignment_status"] == "closed"
    assert closed.json()["coverage"]["status"] == "closed"
    assert closed.json()["coverage"]["vacancy_kind"] == "open_shift"
    assert schedule_view.status_code == 200
    assert schedule_view.json()["summary"]["open_shifts"] == 0
    assert schedule_view.json()["summary"]["filled_shifts"] == 0
    assert schedule_view.json()["exceptions"] == []
    assert schedule_view.json()["shifts"][0]["id"] == shift_id
    assert schedule_view.json()["shifts"][0]["assignment"]["assignment_status"] == "closed"
    assert schedule_view.json()["shifts"][0]["coverage"]["status"] == "closed"
    assert coverage_view.status_code == 200
    assert coverage_view.json()["at_risk_shifts"] == []
    assert queue_view.status_code == 200
    assert queue_view.json()["items"] == []
    assert restarted.status_code == 400
    assert restarted.json() == {"detail": "Shift is closed"}
    assert idempotent_close.status_code == 200
    assert idempotent_close.json() == {
        "status": "closed",
        "shift_id": shift_id,
        "cascade_cancelled": False,
        "idempotent": True,
    }


@pytest.mark.asyncio
async def test_open_shift_close_from_exception_queue_notifies_pending_claimant(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    worker_notifications = []
    manager_notifications = []
    worker_offers = []
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: (
            manager_notifications.append((to, body))
            if to == "+13105550361"
            else worker_notifications.append((to, body))
        ) or "SM-NOTIFY",
    )
    monkeypatch.setattr("app.services.agency_router.send_sms", lambda to, body: "SM-AGENCY")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    location_id = await insert_location(
        db,
        {
            "name": "Claim Close Cafe",
            "manager_name": "Morgan Lead",
            "manager_phone": "+13105550361",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
            "coverage_requires_manager_approval": True,
        },
    )
    claimant_id = await insert_worker(
        db,
        {
            "name": "Priya Cover",
            "phone": "+13105550362",
            "roles": ["line_cook"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    week_start = date(2026, 4, 20)
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": week_start.isoformat(),
            "week_end_date": (week_start + timedelta(days=6)).isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": (week_start + timedelta(days=2)).isoformat(),
            "start_time": "09:00:00",
            "end_time": "17:00:00",
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
            "assignment_status": "open",
            "source": "manual",
        },
    )

    started = client.post(f"/api/shifts/{shift_id}/coverage/start")
    assert started.status_code == 200
    worker_notifications.clear()
    manager_notifications.clear()

    worker_yes = {"From": "+13105550362", "Body": "YES"}
    worker_response = client.post(
        "/webhooks/twilio/sms",
        data=worker_yes,
        headers=_signed_sms_headers("test-token", worker_yes),
    )
    queue_before = client.get(
        f"/api/locations/{location_id}/schedule-exceptions?week_start={week_start.isoformat()}"
    )
    closed = client.post(
        f"/api/locations/{location_id}/schedule-exceptions/actions",
        json={
            "week_start": week_start.isoformat(),
            "actions": [
                {
                    "shift_id": shift_id,
                    "code": "coverage_fill_approval_required",
                    "action": "close_shift",
                }
            ],
        },
    )
    shift_after = await get_shift(db, shift_id)
    active_cascade_after = await get_active_cascade_for_shift(db, shift_id)
    schedule_view = client.get(
        f"/api/locations/{location_id}/schedules/current?week_start={week_start.isoformat()}"
    )

    assert worker_response.status_code == 200
    assert "we sent your open shift claim to the manager for approval" in worker_response.text.lower()
    assert queue_before.status_code == 200
    assert queue_before.json()["items"][0]["code"] == "coverage_fill_approval_required"
    assert queue_before.json()["items"][0]["available_actions"] == ["approve_fill", "decline_fill", "close_shift"]
    assert closed.status_code == 200
    assert closed.json()["success_count"] == 1
    assert closed.json()["results"][0]["status"] == "ok"
    assert closed.json()["results"][0]["result"]["status"] == "closed"
    assert closed.json()["results"][0]["result"]["cascade_cancelled"] is True
    assert closed.json()["queue"]["items"] == []
    assert shift_after["status"] == "scheduled"
    assert active_cascade_after is None
    assert schedule_view.status_code == 200
    assert schedule_view.json()["summary"]["open_shifts"] == 0
    assert schedule_view.json()["shifts"][0]["assignment"]["assignment_status"] == "closed"
    assert schedule_view.json()["shifts"][0]["coverage"]["status"] == "closed"
    assert any("no longer available" in body.lower() for _, body in worker_notifications)
    assert worker_offers
    assert claimant_id is not None


@pytest.mark.asyncio
async def test_open_shift_claim_sms_flow_uses_open_shift_language(db, client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "test-token")

    manager_notifications = []
    worker_notifications = []
    worker_offers = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: (
            manager_notifications.append((to, body))
            if to == "+13105550361"
            else worker_notifications.append((to, body))
        ) or "SM-NOTIFY",
    )
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    location_id = await insert_location(
        db,
        {
            "name": "Open Claim Cafe",
            "manager_name": "Leah Lead",
            "manager_phone": "+13105550361",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
            "coverage_requires_manager_approval": True,
        },
    )
    await insert_worker(
        db,
        {
            "name": "Jamie Open",
            "phone": "+13105550362",
            "roles": ["line_cook"],
            "priority_rank": 1,
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    week_start = date(2026, 4, 20)
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": week_start.isoformat(),
            "week_end_date": (week_start + timedelta(days=6)).isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": (week_start + timedelta(days=3)).isoformat(),
            "start_time": "11:00:00",
            "end_time": "19:00:00",
            "pay_rate": 22.0,
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
            "assignment_status": "open",
            "source": "manual",
        },
    )

    start_coverage = client.post(f"/api/shifts/{shift_id}/coverage/start")
    worker_yes = {"From": "+13105550362", "Body": "YES"}
    worker_response = client.post(
        "/webhooks/twilio/sms",
        data=worker_yes,
        headers=_signed_sms_headers("test-token", worker_yes),
    )
    manager_yes = {"From": "+13105550361", "Body": "YES"}
    manager_response = client.post(
        "/webhooks/twilio/sms",
        data=manager_yes,
        headers=_signed_sms_headers("test-token", manager_yes),
    )

    assert start_coverage.status_code == 200
    assert start_coverage.json()["status"] == "coverage_started"
    assert len(worker_offers) == 1
    assert "open shift available at open claim cafe" in worker_offers[0][1].lower()
    assert worker_response.status_code == 200
    assert "sent your open shift claim to the manager for approval" in worker_response.text.lower()
    assert len(manager_notifications) == 1
    assert "wants to claim your open line_cook shift" in manager_notifications[0][1].lower()
    assert manager_response.status_code == 200
    assert "confirmed for the open line_cook shift" in manager_response.text.lower()
    assert any("confirmed for the open line_cook shift" in body.lower() for _, body in worker_notifications)


@pytest.mark.asyncio
async def test_missed_check_in_manager_action_queue_waits_for_manager(db, client, monkeypatch):
    manager_messages = []
    worker_offers = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: manager_messages.append((to, body)) or "SM-MANAGER",
    )
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )

    async def _fake_call(*, to_number, metadata, agent_id=None):
        return "CA123"

    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)

    location_id = await insert_location(
        db,
        {
            "name": "Missed Queue Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550341",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
            "missed_check_in_policy": "manager_action",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "Missed Queue Cook",
            "phone": "+13105550342",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    await insert_worker(
        db,
        {
            "name": "Backup Missed Cook",
            "phone": "+13105550343",
            "roles": ["line_cook"],
            "location_id": location_id,
            "priority_rank": 1,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    start = datetime.utcnow() - timedelta(minutes=15)
    week_start = start.date() - timedelta(days=start.date().weekday())
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": week_start.isoformat(),
            "week_end_date": (week_start + timedelta(days=6)).isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
            "check_in_requested_at": (datetime.utcnow() - timedelta(minutes=20)).isoformat(),
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

    response = client.post("/api/internal/backfill-shifts/escalate-missed-check-ins?grace_minutes=10")
    shift = await get_shift(db, shift_id)
    cascade = await get_active_cascade_for_shift(db, shift_id)
    queue = client.get(
        f"/api/locations/{location_id}/manager-actions?week_start={week_start.isoformat()}"
    )

    assert response.status_code == 200
    assert response.json()["escalated_shift_ids"] == [shift_id]
    assert shift["status"] == "scheduled"
    assert shift["check_in_escalated_at"] is not None
    assert cascade is None
    assert len(worker_offers) == 0
    assert len(manager_messages) == 1
    assert "reply review or open" in manager_messages[0][1].lower()
    assert queue.status_code == 200
    assert queue.json()["summary"]["attendance_reviews"] == 1
    assert queue.json()["actions"][0]["action_type"] == "review_missed_check_in"

    start_coverage = client.post(f"/api/shifts/{shift_id}/attendance/start-coverage")
    shift_after = await get_shift(db, shift_id)
    cascade_after = await get_active_cascade_for_shift(db, shift_id)

    assert start_coverage.status_code == 200
    assert start_coverage.json()["status"] == "coverage_started"
    assert start_coverage.json()["issue_type"] == "missed_check_in"
    assert shift_after["status"] == "vacant"
    assert cascade_after is not None
    assert len(worker_offers) == 1


@pytest.mark.asyncio
async def test_internal_missed_check_in_escalation_route_starts_coverage(db, client, monkeypatch):
    manager_messages = []
    worker_offers = []
    monkeypatch.setattr(
        "app.services.notifications.send_sms",
        lambda to, body: manager_messages.append((to, body)) or "SM-MANAGER",
    )
    monkeypatch.setattr(
        "app.services.messaging.send_sms",
        lambda to, body, metadata=None: worker_offers.append((to, body, metadata)) or "SM-OFFER",
    )
    async def _fake_call(*, to_number, metadata, agent_id=None):
        return "CA123"

    monkeypatch.setattr("app.services.retell.create_phone_call", _fake_call)

    location_id = await insert_location(
        db,
        {
            "name": "No Show Start Cafe",
            "manager_name": "June Lead",
            "manager_phone": "+13105550330",
            "scheduling_platform": "backfill_native",
            "operating_mode": "backfill_shifts",
        },
    )
    worker_id = await insert_worker(
        db,
        {
            "name": "No Show Cook",
            "phone": "+13105550331",
            "roles": ["line_cook"],
            "location_id": location_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    await insert_worker(
        db,
        {
            "name": "Backup Start Cook",
            "phone": "+13105550332",
            "roles": ["line_cook"],
            "location_id": location_id,
            "priority_rank": 1,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    start = datetime.utcnow() - timedelta(minutes=15)
    week_start = start.date() - timedelta(days=start.date().weekday())
    schedule_id = await insert_schedule(
        db,
        {
            "location_id": location_id,
            "week_start_date": week_start.isoformat(),
            "week_end_date": (week_start + timedelta(days=6)).isoformat(),
            "lifecycle_state": "published",
            "created_by": "test",
        },
    )
    shift_id = await insert_shift(
        db,
        {
            "location_id": location_id,
            "schedule_id": schedule_id,
            "role": "line_cook",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 21.0,
            "requirements": [],
            "status": "scheduled",
            "source_platform": "backfill_native",
            "published_state": "published",
            "check_in_requested_at": (datetime.utcnow() - timedelta(minutes=20)).isoformat(),
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
    await db.execute(
        "UPDATE shifts SET check_in_requested_at=? WHERE id=?",
        ((datetime.utcnow() - timedelta(minutes=20)).isoformat(), shift_id),
    )
    await db.commit()

    response = client.post("/api/internal/backfill-shifts/escalate-missed-check-ins?grace_minutes=10")
    shift = await get_shift(db, shift_id)
    cascade = await get_active_cascade_for_shift(db, shift_id)
    schedule_view = client.get(
        f"/api/locations/{location_id}/schedules/current?week_start={week_start.isoformat()}"
    )

    assert response.status_code == 200
    assert response.json() == {
        "grace_minutes": 10,
        "escalated_count": 1,
        "escalated_shift_ids": [shift_id],
        "skipped_shift_ids": [],
    }
    assert shift["status"] == "vacant"
    assert shift["check_in_escalated_at"] is not None
    assert cascade is not None
    assert len(worker_offers) == 1
    assert len(manager_messages) == 1
    assert "didn't check in" in manager_messages[0][1].lower()
    assert schedule_view.status_code == 200
    shift_payload = schedule_view.json()["shifts"][0]
    assert shift_payload["attendance"]["status"] == "escalated"
    assert shift_payload["coverage"]["status"] == "active"
