from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta

import pytest

from app.config import settings
from app.db.queries import get_shift, insert_location, insert_shift, insert_worker, list_sync_jobs


def _signed_json(secret: str, body: dict) -> tuple[str, str]:
    raw = json.dumps(body).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    return raw.decode("utf-8"), base64.b64encode(digest).decode("utf-8")


@pytest.mark.asyncio
async def test_seven_shifts_webhook_creates_vacancy(db, client, monkeypatch):
    monkeypatch.setattr(settings, "sevenshifts_webhook_secret", "seven-secret")

    location_id = await insert_location(
        db,
        {
            "name": "Sync Taco",
            "manager_name": "Chef Mike",
            "manager_phone": "+13105550100",
            "scheduling_platform": "7shifts",
            "scheduling_platform_id": "company-123",
        },
    )
    await insert_worker(
        db,
        {
            "name": "Caller",
            "phone": "+13105550101",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 1,
            "location_id": location_id,
            "source_id": "worker-ext-1",
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    replacement_id = await insert_worker(
        db,
        {
            "name": "Replacement",
            "phone": "+13105550102",
            "roles": ["line_cook"],
            "certifications": ["food_handler_card"],
            "priority_rank": 2,
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
            "scheduling_platform_id": "shift-ext-1",
            "role": "line_cook",
            "date": start.date().isoformat(),
            "start_time": start.strftime("%H:%M:%S"),
            "end_time": (start + timedelta(hours=8)).strftime("%H:%M:%S"),
            "pay_rate": 24.0,
            "requirements": ["food_handler_card"],
            "status": "scheduled",
            "source_platform": "7shifts",
        },
    )

    monkeypatch.setattr("app.services.messaging.send_sms", lambda to, body, metadata=None: "SM123")
    monkeypatch.setattr("app.services.retell.create_phone_call", pytest.fail)

    body = {
        "type": "punch.callout",
        "data": {
            "shift_id": "shift-ext-1",
            "user_id": "worker-ext-1",
        },
    }
    raw, signature = _signed_json("seven-secret", body)
    response = client.post(
        "/webhooks/scheduling/seven_shifts",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-7shifts-Signature": signature,
        },
    )

    shift = await get_shift(db, shift_id)
    sync_jobs = await list_sync_jobs(db, location_id=location_id, limit=10)

    assert response.status_code == 200
    assert response.json()["status"] == "vacancy_created"
    assert response.json()["result"]["worker_id"] == replacement_id
    assert shift["status"] == "vacant"
    assert any(job["job_type"] == "event_reconcile" for job in sync_jobs)


def test_deputy_webhook_rejects_invalid_signature(client, monkeypatch):
    monkeypatch.setattr(settings, "deputy_webhook_secret", "deputy-secret")

    response = client.post(
        "/webhooks/scheduling/deputy",
        content='{"topic":"Roster","event":"Delete"}',
        headers={
            "Content-Type": "application/json",
            "X-Deputy-Signature": "invalid",
        },
    )

    assert response.status_code == 403
