from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.common import CoverageAttemptStatus, CoverageCaseStatus, CoverageRunStatus, OfferStatus, OutboxStatus
from app.models.business import Location, Role
from app.models.coverage import CoverageCandidate, CoverageCase, CoverageCaseRun, CoverageContactAttempt, CoverageOffer, OutboxEvent
from app.models.scheduling import Shift
from app.models.workforce import Employee
from app.services import delivery


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarResult(self._values)

    def first(self):
        return self._values[0] if self._values else None


class FakeDeliverySession:
    def __init__(self):
        self.added: list[object] = []
        self.execute_queue: list[list[object]] = []
        self.scalar_queue: list[object] = []
        self.get_map: dict[tuple[type, object], object] = {}

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))

    async def scalar(self, _query):
        if self.scalar_queue:
            return self.scalar_queue.pop(0)
        return None

    async def execute(self, _query):
        values = self.execute_queue.pop(0) if self.execute_queue else []
        return _ExecuteResult(values)

    def add(self, obj):
        now = datetime.now(timezone.utc)
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = now
        if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
            obj.updated_at = now
        self.added.append(obj)
        self.get_map[(type(obj), obj.id)] = obj

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None


class SuccessProvider:
    async def send_coverage_offer(self, *, outbox_event, offer, shift):
        now = datetime.now(timezone.utc)
        return delivery.DeliverySendResult(
            success=True,
            provider="stub",
            provider_message_id=f"msg-{offer.id}",
            sent_at=now,
            delivered_at=now,
            result_payload={"channel": offer.channel.value if hasattr(offer.channel, "value") else str(offer.channel)},
        )


@pytest.mark.asyncio
async def test_process_outbox_batch_marks_offer_delivered_and_creates_attempt():
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    case_id = uuid4()
    offer_id = uuid4()
    event_id = uuid4()

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
    )
    offer = CoverageOffer(
        id=offer_id,
        coverage_case_id=case_id,
        employee_id=uuid4(),
        channel="sms",
        status=OfferStatus.pending,
        idempotency_key="offer-1",
        expires_at=now + timedelta(minutes=5),
        offer_metadata={"shift_id": str(shift_id)},
    )
    event = OutboxEvent(
        id=event_id,
        aggregate_type="coverage_offer",
        aggregate_id=offer_id,
        topic="coverage.offer.created",
        channel="sms",
        status=OutboxStatus.pending,
        available_at=now,
        payload={"shift_id": str(shift_id)},
    )

    session = FakeDeliverySession()
    session.get_map[(CoverageOffer, offer_id)] = offer
    session.get_map[(Shift, shift_id)] = shift
    session.execute_queue = [[event]]
    session.scalar_queue = [shift, None, 0]

    result = await delivery.process_outbox_batch(
        session,
        provider=SuccessProvider(),
        now=now,
        limit=10,
    )

    attempts = [obj for obj in session.added if isinstance(obj, CoverageContactAttempt)]
    assert result["claimed_count"] == 1
    assert result["sent_count"] == 1
    assert offer.status == OfferStatus.delivered
    assert offer.provider_message_id is not None
    assert event.status == OutboxStatus.sent
    assert len(attempts) == 1
    assert attempts[0].status == CoverageAttemptStatus.delivered
    assert attempts[0].outbox_event_id == event.id


@pytest.mark.asyncio
async def test_expire_due_offers_advances_next_candidate_and_updates_reliability():
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    case_id = uuid4()
    run_id = uuid4()
    offer_id = uuid4()
    employee_id = uuid4()
    next_employee_id = uuid4()

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(minutes=40),
        ends_at=now + timedelta(hours=8),
    )
    coverage_case = CoverageCase(
        id=case_id,
        shift_id=shift_id,
        location_id=location_id,
        role_id=role_id,
        status=CoverageCaseStatus.running,
        phase_target="phase_2",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
    )
    run = CoverageCaseRun(
        id=run_id,
        coverage_case_id=case_id,
        phase_no=2,
        strategy="phase_2_blast",
        status=CoverageRunStatus.completed,
        run_metadata={"offer_ttl_minutes": 2, "operating_mode": "blast", "premium_cents": 500},
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        home_location_id=location_id,
        full_name="Taylor Smith",
        phone_e164="+15555550100",
        reliability_score=0.7,
        response_profile={},
        employee_metadata={},
    )
    offer = CoverageOffer(
        id=offer_id,
        coverage_case_id=case_id,
        coverage_case_run_id=run_id,
        employee_id=employee_id,
        channel="sms",
        status=OfferStatus.delivered,
        idempotency_key="offer-main",
        sent_at=now - timedelta(minutes=3),
        expires_at=now - timedelta(seconds=5),
        offer_metadata={"shift_id": str(shift_id), "phase_no": 2, "operating_mode": "blast"},
    )
    attempt = CoverageContactAttempt(
        id=uuid4(),
        coverage_offer_id=offer_id,
        coverage_case_id=case_id,
        coverage_case_run_id=run_id,
        shift_id=shift_id,
        location_id=location_id,
        employee_id=employee_id,
        channel="sms",
        status=CoverageAttemptStatus.delivered,
        attempt_no=1,
        requested_at=now - timedelta(minutes=4),
        sent_at=now - timedelta(minutes=3),
        expires_at=offer.expires_at,
        attempt_metadata={},
    )
    next_candidate = CoverageCandidate(
        id=uuid4(),
        coverage_case_run_id=run_id,
        employee_id=next_employee_id,
        source="phase_2",
        rank=2,
        score=82.0,
        qualification_status="qualified",
        exclusion_reasons=[],
        scoring_factors={"total": 82.0},
        availability_snapshot={"rule_match": True},
        candidate_metadata={"employee_name": "Next Person"},
    )

    session = FakeDeliverySession()
    session.get_map[(CoverageCase, case_id)] = coverage_case
    session.get_map[(Shift, shift_id)] = shift
    session.get_map[(Employee, employee_id)] = employee
    session.get_map[(CoverageCaseRun, run_id)] = run
    session.execute_queue = [
        [offer],
        [attempt],
        [],
        [offer.coverage_candidate_id] if offer.coverage_candidate_id is not None else [],
        [next_candidate],
    ]
    session.scalar_queue = [attempt]

    result = await delivery.expire_due_offers(session, now=now, limit=10)

    new_offers = [obj for obj in session.added if isinstance(obj, CoverageOffer)]
    assert result["expired_count"] == 1
    assert offer.status == OfferStatus.expired
    assert attempt.status == CoverageAttemptStatus.expired
    assert employee.reliability_score < 0.7
    assert len(new_offers) == 1
    assert new_offers[0].employee_id == next_employee_id
    assert new_offers[0].offer_metadata["premium_cents"] == 500


@pytest.mark.asyncio
async def test_twilio_sms_provider_builds_callback_and_message(monkeypatch):
    now = datetime.now(timezone.utc)
    shift = Shift(
        id=uuid4(),
        business_id=uuid4(),
        location_id=uuid4(),
        role_id=uuid4(),
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
    )
    shift.location = Location(
        id=shift.location_id,
        business_id=shift.business_id,
        name="Casa Vega West",
        slug="casa-vega-west",
        timezone="America/Los_Angeles",
    )
    shift.role = Role(
        id=shift.role_id,
        business_id=shift.business_id,
        code="server",
        name="Server",
    )
    offer = CoverageOffer(
        id=uuid4(),
        coverage_case_id=uuid4(),
        employee_id=uuid4(),
        channel="sms",
        status=OfferStatus.pending,
        idempotency_key="offer-provider",
        offer_metadata={"premium_cents": 500},
    )
    event = OutboxEvent(
        id=uuid4(),
        aggregate_type="coverage_offer",
        aggregate_id=offer.id,
        topic="coverage.offer.created",
        channel="sms",
        status=OutboxStatus.pending,
        available_at=now,
        payload={"phone_e164": "+15555550100"},
    )

    captured: dict = {}

    def fake_send_sms(*, to: str, body: str, status_callback: str | None = None):
        captured["to"] = to
        captured["body"] = body
        captured["status_callback"] = status_callback
        return {"sid": "SM123", "status": "queued"}

    monkeypatch.setattr("app.services.messaging.send_sms", fake_send_sms)

    provider = delivery.TwilioSMSDeliveryProvider()
    result = await provider.send_coverage_offer(outbox_event=event, offer=offer, shift=shift)

    assert result.success is True
    assert result.provider == "twilio"
    assert captured["to"] == "+15555550100"
    assert "Casa Vega West" in captured["body"]
    assert "Server" in captured["body"]
    assert "Reply YES" in captured["body"]
    assert captured["status_callback"].endswith("/api/providers/twilio/sms/status")


@pytest.mark.asyncio
async def test_apply_twilio_status_callback_advances_next_candidate_on_failure():
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    case_id = uuid4()
    run_id = uuid4()
    offer_id = uuid4()
    employee_id = uuid4()
    next_employee_id = uuid4()

    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(minutes=40),
        ends_at=now + timedelta(hours=8),
    )
    coverage_case = CoverageCase(
        id=case_id,
        shift_id=shift_id,
        location_id=location_id,
        role_id=role_id,
        status=CoverageCaseStatus.running,
        phase_target="phase_2",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
    )
    run = CoverageCaseRun(
        id=run_id,
        coverage_case_id=case_id,
        phase_no=2,
        strategy="phase_2_blast",
        status=CoverageRunStatus.completed,
        run_metadata={"offer_ttl_minutes": 2, "operating_mode": "blast", "premium_cents": 500},
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        home_location_id=location_id,
        full_name="Taylor Smith",
        phone_e164="+15555550100",
        reliability_score=0.7,
        response_profile={},
        employee_metadata={},
    )
    offer = CoverageOffer(
        id=offer_id,
        coverage_case_id=case_id,
        coverage_case_run_id=run_id,
        employee_id=employee_id,
        channel="sms",
        status=OfferStatus.pending,
        idempotency_key="offer-status",
        provider_message_id="SM-FAIL",
        sent_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=1),
        offer_metadata={"shift_id": str(shift_id), "phase_no": 2, "operating_mode": "blast"},
    )
    attempt = CoverageContactAttempt(
        id=uuid4(),
        coverage_offer_id=offer_id,
        coverage_case_id=case_id,
        coverage_case_run_id=run_id,
        shift_id=shift_id,
        location_id=location_id,
        employee_id=employee_id,
        channel="sms",
        status=CoverageAttemptStatus.pending,
        attempt_no=1,
        requested_at=now - timedelta(minutes=2),
        sent_at=now - timedelta(minutes=1),
        attempt_metadata={},
    )
    next_candidate = CoverageCandidate(
        id=uuid4(),
        coverage_case_run_id=run_id,
        employee_id=next_employee_id,
        source="phase_2",
        rank=2,
        score=80.0,
        qualification_status="qualified",
        exclusion_reasons=[],
        scoring_factors={"total": 80.0},
        availability_snapshot={"rule_match": True},
        candidate_metadata={"employee_name": "Next Person", "phone_e164": "+15555550101"},
    )

    session = FakeDeliverySession()
    session.get_map[(CoverageCase, case_id)] = coverage_case
    session.get_map[(Shift, shift_id)] = shift
    session.get_map[(CoverageCaseRun, run_id)] = run
    session.get_map[(Employee, employee_id)] = employee
    session.scalar_queue = [offer, attempt]
    session.execute_queue = [
        [attempt],
        [],
        [offer.coverage_candidate_id] if offer.coverage_candidate_id is not None else [],
        [next_candidate],
    ]

    result = await delivery.apply_twilio_status_callback(
        session,
        message_sid="SM-FAIL",
        message_status="undelivered",
        error_code="30003",
        error_message="unreachable",
        raw_payload={"MessageStatus": "undelivered"},
        occurred_at=now,
    )

    new_offers = [obj for obj in session.added if isinstance(obj, CoverageOffer)]
    assert result["matched"] is True
    assert result["terminal_failure"] is True
    assert offer.status == OfferStatus.failed
    assert attempt.status == CoverageAttemptStatus.failed
    assert employee.reliability_score < 0.7
    assert len(new_offers) == 1
    assert result["advanced_offer_ids"] == [str(new_offers[0].id)]
    assert result["advanced_offer_id"] == str(new_offers[0].id)


@pytest.mark.asyncio
async def test_handle_twilio_inbound_reply_accepts_latest_offer(monkeypatch):
    offer = CoverageOffer(
        id=uuid4(),
        coverage_case_id=uuid4(),
        employee_id=uuid4(),
        channel="sms",
        status=OfferStatus.pending,
        idempotency_key="offer-inbound",
        offer_metadata={},
    )

    async def fake_find_latest_actionable_offer_for_phone(_session, phone_e164):
        assert phone_e164 == "+15555550100"
        return delivery.ActionableOfferContext(offer=offer, business_id=uuid4())

    captured: dict = {}

    async def fake_respond_to_offer(_session, business_id, offer_id, payload):
        captured["business_id"] = business_id
        captured["offer_id"] = offer_id
        captured["payload"] = payload
        return object()

    monkeypatch.setattr(delivery, "find_latest_actionable_offer_for_phone", fake_find_latest_actionable_offer_for_phone)
    monkeypatch.setattr("app.services.coverage.respond_to_offer", fake_respond_to_offer)

    message = await delivery.handle_twilio_inbound_reply(
        FakeDeliverySession(),
        from_phone="+15555550100",
        body="YES",
        raw_payload={"Body": "YES"},
    )

    assert message.startswith("You're confirmed")
    assert captured["offer_id"] == offer.id
    assert captured["payload"].response == "accepted"
