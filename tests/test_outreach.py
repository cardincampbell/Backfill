from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.orm.attributes import NO_VALUE

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


class _FakeScalarSession:
    def __init__(self, attempt):
        self._attempt = attempt

    async def scalar(self, _query):
        return self._attempt


@pytest.mark.asyncio
async def test_append_outreach_attempt_event_uses_scalar_fallback_when_attempts_unloaded(monkeypatch):
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    shift_id = uuid4()
    offer = CoverageOffer(
        id=uuid4(),
        coverage_case_id=uuid4(),
        employee_id=uuid4(),
        channel="sms",
        status=OfferStatus.delivered,
        idempotency_key="case:1:employee:sms",
        offer_metadata={"phase_no": 1},
        created_at=now,
        updated_at=now,
    )
    attempt = CoverageContactAttempt(
        id=uuid4(),
        coverage_offer_id=offer.id,
        coverage_case_id=offer.coverage_case_id,
        shift_id=shift_id,
        location_id=location_id,
        employee_id=offer.employee_id,
        channel="sms",
        status=CoverageAttemptStatus.delivered,
        attempt_no=1,
        requested_at=now,
        delivered_at=now,
        attempt_metadata={},
        created_at=now,
        updated_at=now,
    )
    captured: dict = {}

    async def fake_append(_session, **kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(outreach.platform_events, "append", fake_append)

    await outreach.append_outreach_attempt_event(
        _FakeScalarSession(attempt),
        event_type="coverage.outreach_attempt.delivered",
        compatibility_event_name="coverage.offer.delivered",
        offer=offer,
        business_id=business_id,
        location_id=location_id,
        shift_id=shift_id,
        metadata={"channel": "test"},
    )

    assert captured["payload"]["attempt_status"] == "delivered"
    assert captured["payload"]["status"] == "awaiting_response"


@pytest.mark.asyncio
async def test_outreach_attempt_read_does_not_touch_expired_offer_updated_at(monkeypatch):
    now = datetime.now(timezone.utc)

    class _ExplodingOffer:
        def __init__(self):
            self.id = uuid4()

        def __getattribute__(self, name):
            if name == "updated_at":
                raise MissingGreenlet("expired attribute access")
            return object.__getattribute__(self, name)

    class _FakeAttrState:
        def __init__(self, loaded_value):
            self.loaded_value = loaded_value

    class _FakeState:
        def __init__(self):
            self.dict = {
                "coverage_case_id": uuid4(),
                "coverage_case_run_id": uuid4(),
                "coverage_candidate_id": uuid4(),
                "employee_id": uuid4(),
                "channel": "voice",
                "status": OfferStatus.delivered,
                "idempotency_key": "case:1:employee:voice",
                "offer_metadata": {"phase_no": 1},
                "created_at": now,
            }
            self.attrs = {
                **{name: _FakeAttrState(value) for name, value in self.dict.items()},
                "updated_at": _FakeAttrState(NO_VALUE),
            }

    offer = _ExplodingOffer()

    monkeypatch.setattr(outreach, "_latest_attempt", lambda _offer: None)
    monkeypatch.setattr(outreach, "inspect", lambda _instance: _FakeState())

    result = outreach.outreach_attempt_read_from_offer(offer)

    assert result.coverage_offer_id == offer.id
    assert result.offer_status == "delivered"
    assert result.status == "voice_initiated"
    assert result.updated_at == now
