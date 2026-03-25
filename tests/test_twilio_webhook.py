from datetime import datetime, timedelta

import pytest
from twilio.request_validator import RequestValidator

from app.config import settings
from app.db.queries import (
    get_cascade,
    get_shift,
    insert_agency_partner,
    insert_restaurant,
    insert_shift,
    insert_worker,
    list_agency_requests,
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

    restaurant_id = await insert_restaurant(
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

    restaurant_id = await insert_restaurant(
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
            "restaurant_id": restaurant_id,
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    shift_start = datetime.utcnow() + timedelta(hours=8)
    shift_id = await insert_shift(
        db,
        {
            "restaurant_id": restaurant_id,
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
    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body: "SM123")
    monkeypatch.setattr("app.services.agency_router.send_sms", lambda to, body: sent.append((to, body)) or "SM999")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    cascade = await create_vacancy(db, shift_id, caller_id, actor=f"worker:{caller_id}")
    result = await cascade_svc.advance(db, cascade["id"])
    assert result["status"] == "awaiting_tier3_approval"

    params = {"From": "+13105550100", "Body": "AGENCY"}
    response = client.post(
        "/webhooks/twilio/sms",
        data=params,
        headers=_signed_sms_headers("test-token", params),
    )

    requests = await list_agency_requests(db, cascade_id=cascade["id"])
    updated_cascade = await get_cascade(db, cascade["id"])

    assert response.status_code == 200
    assert "agency routing approved" in response.text.lower()
    assert updated_cascade["manager_approved_tier3"] is True
    assert requests
    assert sent
