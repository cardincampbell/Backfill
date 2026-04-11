from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.common import CoverageAttemptStatus, OfferStatus
from app.models.coverage import CoverageContactAttempt, CoverageOffer
from app.services import outreach


def test_outreach_attempt_read_maps_pending_offer_to_queued():
    now = datetime.now(timezone.utc)
    offer = CoverageOffer(
        id=uuid4(),
        coverage_case_id=uuid4(),
        employee_id=uuid4(),
        channel="sms",
        status=OfferStatus.pending,
        idempotency_key="case:1:employee:sms",
        offer_metadata={"phase_no": 1},
        created_at=now,
        updated_at=now,
    )

    attempt = outreach.outreach_attempt_read_from_offer(offer)

    assert attempt.coverage_offer_id == offer.id
    assert attempt.status == "queued"
    assert attempt.offer_status == "pending"
    assert attempt.attempt_status is None


def test_outreach_attempt_read_maps_sent_attempt_to_sms_sent():
    now = datetime.now(timezone.utc)
    offer = CoverageOffer(
        id=uuid4(),
        coverage_case_id=uuid4(),
        employee_id=uuid4(),
        channel="sms",
        status=OfferStatus.pending,
        idempotency_key="case:1:employee:sms",
        offer_metadata={"phase_no": 1},
        created_at=now,
        updated_at=now,
    )
    attempt = CoverageContactAttempt(
        id=uuid4(),
        coverage_offer_id=offer.id,
        coverage_case_id=offer.coverage_case_id,
        shift_id=uuid4(),
        location_id=uuid4(),
        employee_id=offer.employee_id,
        channel="sms",
        status=CoverageAttemptStatus.pending,
        attempt_no=1,
        requested_at=now,
        sent_at=now,
        attempt_metadata={},
        created_at=now,
        updated_at=now,
    )

    result = outreach.outreach_attempt_read_from_offer(offer, attempt=attempt)

    assert result.status == "sms_sent"
    assert result.attempt_status == "pending"
    assert result.requested_at == now
    assert result.sent_at == now


def test_outreach_attempt_read_maps_delivered_voice_to_voice_initiated():
    now = datetime.now(timezone.utc)
    offer = CoverageOffer(
        id=uuid4(),
        coverage_case_id=uuid4(),
        employee_id=uuid4(),
        channel="voice",
        status=OfferStatus.delivered,
        idempotency_key="case:1:employee:voice",
        offer_metadata={"phase_no": 2},
        created_at=now,
        updated_at=now,
    )

    result = outreach.outreach_attempt_read_from_offer(offer)

    assert result.status == "voice_initiated"
    assert result.offer_status == "delivered"


class _FakeSession:
    pass


@pytest.mark.asyncio
async def test_append_outreach_attempt_event_uses_logical_outreach_entity(monkeypatch):
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    shift_id = uuid4()
    offer = CoverageOffer(
        id=uuid4(),
        coverage_case_id=uuid4(),
        employee_id=uuid4(),
        channel="sms",
        status=OfferStatus.accepted,
        idempotency_key="case:1:employee:sms",
        offer_metadata={"phase_no": 1},
        created_at=now,
        updated_at=now,
    )
    captured: dict = {}

    async def fake_append(_session, **kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(outreach.platform_events, "append", fake_append)

    await outreach.append_outreach_attempt_event(
        _FakeSession(),
        event_type="coverage.outreach_attempt.accepted",
        compatibility_event_name="coverage.offer.accepted",
        offer=offer,
        business_id=business_id,
        location_id=location_id,
        shift_id=shift_id,
        metadata={"channel": "test"},
    )

    assert captured["event_type"] == "coverage.outreach_attempt.accepted"
    assert captured["compatibility_event_name"] == "coverage.offer.accepted"
    assert captured["target_type"] == "coverage_outreach_attempt"
    assert captured["target_id"] == offer.id
    assert captured["payload"]["outreach_attempt_id"] == str(offer.id)
    assert captured["payload"]["coverage_offer_id"] == str(offer.id)
