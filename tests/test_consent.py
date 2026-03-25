"""Tests for consent ledger."""
import pytest

from app.db.queries import get_worker, insert_worker
from app.services.consent import grant, revoke, handle_stop_keyword, has_sms_consent


@pytest.mark.asyncio
async def test_grant_consent(db):
    worker_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550101",
            "roles": ["line_cook"],
        },
    )

    await grant(db, worker_id, channel="inbound_call")

    worker = await get_worker(db, worker_id)
    assert worker["sms_consent_status"] == "granted"
    assert worker["voice_consent_status"] == "granted"
    assert worker["consent_channel"] == "inbound_call"


@pytest.mark.asyncio
async def test_revoke_consent(db):
    worker_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550101",
            "roles": ["line_cook"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )

    await revoke(db, worker_id, channel="sms_reply")

    worker = await get_worker(db, worker_id)
    assert worker["sms_consent_status"] == "revoked"
    assert worker["voice_consent_status"] == "revoked"
    assert worker["opt_out_channel"] == "sms_reply"


@pytest.mark.asyncio
async def test_handle_stop_keyword(db):
    worker_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550101",
            "roles": ["line_cook"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )

    handled = await handle_stop_keyword(db, "+13105550101")

    worker = await get_worker(db, worker_id)
    assert handled is True
    assert worker["sms_consent_status"] == "revoked"


@pytest.mark.asyncio
async def test_no_sms_to_revoked_worker(db):
    worker_id = await insert_worker(
        db,
        {
            "name": "Maria",
            "phone": "+13105550101",
            "roles": ["line_cook"],
            "sms_consent_status": "granted",
            "voice_consent_status": "granted",
        },
    )
    await revoke(db, worker_id, channel="manual")

    assert await has_sms_consent(db, worker_id) is False
