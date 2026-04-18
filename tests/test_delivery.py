from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.common import AssignmentStatus, CoverageAttemptStatus, CoverageCaseStatus, CoverageRunStatus, OfferStatus, OutboxStatus
from app.models.business import Business, Location, Role
from app.models.coverage import CoverageCandidate, CoverageCase, CoverageCaseRun, CoverageContactAttempt, CoverageOffer, OutboxEvent
from app.models.scheduling import Shift, ShiftAssignment
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

    def all(self):
        return list(self._values)

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


class ExceptionProvider:
    async def send_coverage_offer(self, *, outbox_event, offer, shift):
        raise RuntimeError("provider_down")


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
async def test_process_outbox_batch_sends_schedule_publish_sms(monkeypatch):
    now = datetime.now(timezone.utc)
    event = OutboxEvent(
        id=uuid4(),
        aggregate_type="schedule_publish",
        aggregate_id=uuid4(),
        topic=delivery.SCHEDULE_PUBLISH_NOTIFICATION_TOPIC,
        channel="sms",
        status=OutboxStatus.pending,
        available_at=now,
        payload={
            "business_id": str(uuid4()),
            "phone_e164": "+15555550100",
            "text_body": "EMAIL BODY SHOULD NOT BE USED",
            "sms_body": "Your schedule is live.",
        },
    )
    captured: dict[str, str | None] = {}

    def fake_send_sms(*, to: str, body: str, status_callback: str | None = None):
        captured["to"] = to
        captured["body"] = body
        captured["status_callback"] = status_callback
        return {"sid": "SM-PUBLISH", "status": "queued"}

    monkeypatch.setattr("app.services.messaging.send_sms", fake_send_sms)

    session = FakeDeliverySession()
    session.execute_queue = [[event]]

    result = await delivery.process_outbox_batch(
        session,
        now=now,
        limit=10,
    )

    assert result["claimed_count"] == 1
    assert result["sent_count"] == 1
    assert event.status == OutboxStatus.sent
    assert captured["to"] == "+15555550100"
    assert captured["body"] == "Your schedule is live."


@pytest.mark.asyncio
async def test_process_outbox_batch_cancels_schedule_publish_sms_on_invalid_twilio_number(monkeypatch):
    now = datetime.now(timezone.utc)
    event = OutboxEvent(
        id=uuid4(),
        aggregate_type="schedule_publish",
        aggregate_id=uuid4(),
        topic=delivery.SCHEDULE_PUBLISH_NOTIFICATION_TOPIC,
        channel="sms",
        status=OutboxStatus.pending,
        available_at=now,
        payload={
            "business_id": str(uuid4()),
            "phone_e164": "not-a-real-number",
            "text_body": "Your schedule is live.",
        },
    )

    class FakeTwilioRestException(Exception):
        def __init__(self):
            super().__init__("The 'To' number is not a valid phone number.")
            self.code = 21211
            self.status = 400

    def fake_send_sms(*, to: str, body: str, status_callback: str | None = None):
        raise FakeTwilioRestException()

    monkeypatch.setattr("app.services.messaging.send_sms", fake_send_sms)

    session = FakeDeliverySession()
    session.execute_queue = [[event]]

    result = await delivery.process_outbox_batch(
        session,
        now=now,
        limit=10,
    )

    assert result["claimed_count"] == 1
    assert result["failed_count"] == 1
    assert event.status == OutboxStatus.cancelled
    assert event.error_message == "The 'To' number is not a valid phone number."
    assert event.result_payload["twilio_error_code"] == 21211


@pytest.mark.asyncio
async def test_process_outbox_batch_sends_schedule_publish_email(monkeypatch):
    now = datetime.now(timezone.utc)
    event = OutboxEvent(
        id=uuid4(),
        aggregate_type="schedule_publish",
        aggregate_id=uuid4(),
        topic=delivery.SCHEDULE_PUBLISH_NOTIFICATION_TOPIC,
        channel="email",
        status=OutboxStatus.pending,
        available_at=now,
        payload={
            "business_id": str(uuid4()),
            "email": "worker@example.com",
            "subject": "Your Backfill schedule is live",
            "text_body": "Plain text schedule body",
            "html_body": "<div>Styled schedule email</div>",
            "email_headers": {"List-Unsubscribe": "<mailto:unsubscribe@example.com>"},
        },
    )
    captured: dict[str, object] = {}

    def fake_send_email(
        *,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        captured["to"] = to
        captured["subject"] = subject
        captured["text_body"] = text_body
        captured["html_body"] = html_body or ""
        captured["headers"] = headers or {}
        return "SG-PUBLISH"

    monkeypatch.setattr("app.services.messaging.send_email", fake_send_email)

    session = FakeDeliverySession()
    session.execute_queue = [[event]]

    result = await delivery.process_outbox_batch(
        session,
        now=now,
        limit=10,
    )

    assert result["claimed_count"] == 1
    assert result["sent_count"] == 1
    assert event.status == OutboxStatus.sent
    assert captured["to"] == "worker@example.com"
    assert captured["subject"] == "Your Backfill schedule is live"
    assert captured["text_body"] == "Plain text schedule body"
    assert captured["html_body"] == "<div>Styled schedule email</div>"
    assert captured["headers"] == {"List-Unsubscribe": "<mailto:unsubscribe@example.com>"}


@pytest.mark.asyncio
async def test_process_outbox_batch_cancels_suppressed_schedule_publish_email(monkeypatch):
    now = datetime.now(timezone.utc)
    event = OutboxEvent(
        id=uuid4(),
        aggregate_type="schedule_publish",
        aggregate_id=uuid4(),
        topic=delivery.SCHEDULE_PUBLISH_NOTIFICATION_TOPIC,
        channel="email",
        status=OutboxStatus.pending,
        available_at=now,
        payload={
            "business_id": str(uuid4()),
            "email": "worker@example.com",
            "subject": "Your schedule is live",
            "text_body": "Your schedule is live.",
        },
    )

    class Suppression:
        channel = "email"
        scope = "global"
        reason_code = "user_unsubscribe"
        source = "email_unsubscribe_link"

    async def fake_get_active_suppression(session, *, channel, destination, scope="global"):
        assert channel == "email"
        assert destination == "worker@example.com"
        return Suppression()

    def fake_send_email(*, to: str, subject: str, text_body: str, html_body: str | None = None, headers: dict[str, str] | None = None):
        raise AssertionError("send_email should not be called for suppressed destinations")

    monkeypatch.setattr(
        "app.services.delivery.communication_suppressions.get_active_suppression",
        fake_get_active_suppression,
    )
    monkeypatch.setattr("app.services.messaging.send_email", fake_send_email)

    session = FakeDeliverySession()
    session.execute_queue = [[event]]

    result = await delivery.process_outbox_batch(
        session,
        now=now,
        limit=10,
    )

    assert result["claimed_count"] == 1
    assert result["failed_count"] == 1
    assert event.status == OutboxStatus.cancelled
    assert event.error_message == "destination_suppressed"
    assert event.result_payload["suppressed"] is True
    assert event.result_payload["suppression_reason_code"] == "user_unsubscribe"


@pytest.mark.asyncio
async def test_process_outbox_batch_cancels_suppressed_coverage_sms_and_advances_case(monkeypatch):
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    case_id = uuid4()
    offer_id = uuid4()
    event_id = uuid4()
    employee_id = uuid4()

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
        employee_id=employee_id,
        channel="sms",
        status=OfferStatus.pending,
        idempotency_key="offer-suppressed",
        expires_at=now + timedelta(minutes=5),
        offer_metadata={"shift_id": str(shift_id), "phone_e164": "+15555550100"},
    )
    event = OutboxEvent(
        id=event_id,
        aggregate_type="coverage_offer",
        aggregate_id=offer_id,
        topic="coverage.offer.created",
        channel="sms",
        status=OutboxStatus.pending,
        available_at=now,
        payload={"shift_id": str(shift_id), "phone_e164": "+15555550100"},
    )

    class Suppression:
        channel = "sms"
        scope = "global"
        reason_code = "user_unsubscribe"
        source = "twilio_inbound"

    async def fake_get_active_suppression(session, *, channel, destination, scope="global"):
        assert channel == "sms"
        assert destination == "+15555550100"
        return Suppression()

    async def fake_append_outreach_attempt_event(*args, **kwargs):
        return None

    async def fake_refresh_employee_reliability(*args, **kwargs):
        return None

    async def fake_advance_case_after_terminal_offer(*args, **kwargs):
        return [], None

    monkeypatch.setattr(
        "app.services.delivery.communication_suppressions.get_active_suppression",
        fake_get_active_suppression,
    )
    monkeypatch.setattr(
        "app.services.delivery.outreach_service.append_outreach_attempt_event",
        fake_append_outreach_attempt_event,
    )
    monkeypatch.setattr("app.services.delivery.refresh_employee_reliability", fake_refresh_employee_reliability)
    monkeypatch.setattr("app.services.delivery._advance_case_after_terminal_offer", fake_advance_case_after_terminal_offer)

    session = FakeDeliverySession()
    session.get_map[(CoverageOffer, offer_id)] = offer
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
    assert result["failed_count"] == 1
    assert event.status == OutboxStatus.cancelled
    assert event.error_message == "destination_suppressed"
    assert offer.status == OfferStatus.failed
    assert attempts[0].status == CoverageAttemptStatus.failed
    assert event.result_payload["suppressed"] is True


@pytest.mark.asyncio
async def test_process_outbox_batch_terminal_failure_advances_next_candidate(monkeypatch):
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    case_id = uuid4()
    run_id = uuid4()
    offer_id = uuid4()
    event_id = uuid4()
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
        run_metadata={"dispatch_limit": 1, "offer_ttl_minutes": 2, "operating_mode": "blast", "premium_cents": 500},
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
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
        idempotency_key="offer-main",
        expires_at=now + timedelta(minutes=2),
        offer_metadata={"shift_id": str(shift_id), "phase_no": 2, "operating_mode": "blast"},
    )
    event = OutboxEvent(
        id=event_id,
        aggregate_type="coverage_offer",
        aggregate_id=offer_id,
        topic="coverage.offer.created",
        channel="sms",
        status=OutboxStatus.pending,
        attempt_count=3,
        available_at=now,
        payload={"shift_id": str(shift_id)},
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

    async def fake_refresh(_session, employee_id, *, now=None):
        assert employee_id == employee.id
        employee.reliability_score = 0.55
        return employee

    monkeypatch.setattr(delivery, "refresh_employee_reliability", fake_refresh)

    session = FakeDeliverySession()
    session.get_map[(CoverageOffer, offer_id)] = offer
    session.get_map[(CoverageCase, case_id)] = coverage_case
    session.get_map[(CoverageCaseRun, run_id)] = run
    session.get_map[(Shift, shift_id)] = shift
    session.get_map[(Employee, employee_id)] = employee
    session.execute_queue = [
        [event],
        [(offer.id, business_id)],
        [],
        [],
        [next_candidate],
    ]
    session.scalar_queue = [shift, None, 0]

    result = await delivery.process_outbox_batch(
        session,
        provider=ExceptionProvider(),
        now=now,
        limit=10,
    )

    new_offers = [obj for obj in session.added if isinstance(obj, CoverageOffer)]
    attempts = [obj for obj in session.added if isinstance(obj, CoverageContactAttempt)]
    assert result["claimed_count"] == 1
    assert result["failed_count"] == 1
    assert offer.status == OfferStatus.failed
    assert employee.reliability_score == 0.55
    assert coverage_case.status == CoverageCaseStatus.running
    assert len(new_offers) == 1
    assert new_offers[0].employee_id == next_employee_id
    assert len(attempts) == 1
    assert attempts[0].status == CoverageAttemptStatus.failed
    assert event.status == OutboxStatus.cancelled
    assert event.result_payload["advanced_offer_ids"] == [str(new_offers[0].id)]


@pytest.mark.asyncio
async def test_process_outbox_batch_terminal_failure_exhausts_case_when_no_next_candidate(monkeypatch):
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    case_id = uuid4()
    run_id = uuid4()
    offer_id = uuid4()
    event_id = uuid4()
    employee_id = uuid4()

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
        run_metadata={"dispatch_limit": 1, "offer_ttl_minutes": 2, "operating_mode": "blast", "premium_cents": 500},
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
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
        idempotency_key="offer-main",
        expires_at=now + timedelta(minutes=2),
        offer_metadata={"shift_id": str(shift_id), "phase_no": 2, "operating_mode": "blast"},
    )
    event = OutboxEvent(
        id=event_id,
        aggregate_type="coverage_offer",
        aggregate_id=offer_id,
        topic="coverage.offer.created",
        channel="sms",
        status=OutboxStatus.pending,
        attempt_count=3,
        available_at=now,
        payload={"shift_id": str(shift_id)},
    )

    async def fake_refresh(_session, employee_id, *, now=None):
        assert employee_id == employee.id
        employee.reliability_score = 0.4
        return employee

    monkeypatch.setattr(delivery, "refresh_employee_reliability", fake_refresh)

    session = FakeDeliverySession()
    session.get_map[(CoverageOffer, offer_id)] = offer
    session.get_map[(CoverageCase, case_id)] = coverage_case
    session.get_map[(CoverageCaseRun, run_id)] = run
    session.get_map[(Shift, shift_id)] = shift
    session.get_map[(Employee, employee_id)] = employee
    session.execute_queue = [
        [event],
        [(offer.id, business_id)],
        [],
        [],
        [],
    ]
    session.scalar_queue = [shift, None, 0]

    result = await delivery.process_outbox_batch(
        session,
        provider=ExceptionProvider(),
        now=now,
        limit=10,
    )

    attempts = [obj for obj in session.added if isinstance(obj, CoverageContactAttempt)]
    assert result["claimed_count"] == 1
    assert result["failed_count"] == 1
    assert offer.status == OfferStatus.failed
    assert employee.reliability_score == 0.4
    assert coverage_case.status == CoverageCaseStatus.exhausted
    assert coverage_case.closed_at == now
    assert len(attempts) == 1
    assert attempts[0].status == CoverageAttemptStatus.failed
    assert event.status == OutboxStatus.cancelled
    assert event.result_payload["advanced_offer_ids"] == []
    assert event.result_payload["exhausted_case_id"] == str(case_id)


@pytest.mark.asyncio
async def test_expire_due_offers_advances_next_candidate_and_updates_reliability(monkeypatch):
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
        [attempt],
        [],
        [offer.coverage_candidate_id] if offer.coverage_candidate_id is not None else [],
        [next_candidate],
    ]
    session.scalar_queue = [attempt]

    async def fake_claim_expiring_offers(_session, *, now, limit):
        assert limit == 10
        assert now == reference_time
        return [offer]

    reference_time = now
    monkeypatch.setattr(delivery.worker_runtime, "claim_expiring_coverage_offers", fake_claim_expiring_offers)

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
async def test_expire_due_offers_returns_zero_when_no_offers_are_claimed(monkeypatch):
    now = datetime.now(timezone.utc)

    async def fake_claim_expiring_offers(_session, *, now, limit):
        assert limit == 10
        return []

    monkeypatch.setattr(delivery.worker_runtime, "claim_expiring_coverage_offers", fake_claim_expiring_offers)

    result = await delivery.expire_due_offers(FakeDeliverySession(), now=now, limit=10)

    assert result == {
        "expired_count": 0,
        "exhausted_case_ids": [],
        "advanced_offer_ids": [],
    }


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
async def test_process_outbox_batch_enriches_retell_voice_call_with_employee_shift_context(monkeypatch):
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    offer_id = uuid4()
    case_id = uuid4()
    employee_id = uuid4()

    business = Business(
        id=business_id,
        name="Casa Vega LLC",
        display_name="Casa Vega",
        slug="casa-vega",
        timezone="America/Los_Angeles",
        settings={"week_start_day": "monday"},
        place_metadata={},
    )
    location = Location(
        id=location_id,
        business_id=business_id,
        name="Casa Vega West",
        slug="casa-vega-west",
        timezone="America/Los_Angeles",
        settings={},
    )
    role = Role(
        id=role_id,
        business_id=business_id,
        code="server",
        name="Server",
    )
    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        timezone="America/Los_Angeles",
        starts_at=datetime(2026, 4, 17, 21, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 18, 1, 0, tzinfo=timezone.utc),
    )
    shift.location = location
    shift.role = role
    weekly_shift = Shift(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        timezone="America/Los_Angeles",
        starts_at=datetime(2026, 4, 16, 18, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 17, 2, 0, tzinfo=timezone.utc),
    )
    weekly_shift.location = location
    weekly_shift.role = role
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Taylor Smith",
        phone_e164="+15555550100",
        response_profile={},
        employee_metadata={},
    )
    assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=weekly_shift.id,
        employee_id=employee_id,
        assigned_via="scheduler_ui",
        status=AssignmentStatus.assigned,
        sequence_no=1,
        assignment_metadata={},
    )
    offer = CoverageOffer(
        id=offer_id,
        coverage_case_id=case_id,
        employee_id=employee_id,
        channel="voice",
        status=OfferStatus.pending,
        idempotency_key="offer-retell-voice",
        expires_at=now + timedelta(minutes=5),
        offer_metadata={"shift_id": str(shift_id), "premium_cents": 500},
    )
    event = OutboxEvent(
        id=uuid4(),
        aggregate_type="coverage_offer",
        aggregate_id=offer_id,
        topic="coverage.offer.created",
        channel="voice",
        status=OutboxStatus.pending,
        available_at=now,
        payload={"phone_e164": "+15555550100"},
    )

    session = FakeDeliverySession()
    session.get_map[(CoverageOffer, offer_id)] = offer
    session.get_map[(Employee, employee_id)] = employee
    session.get_map[(Business, business_id)] = business
    session.scalar_queue = [shift, None, 0]
    session.execute_queue = [[weekly_shift]]

    async def fake_claim_outbox_events(_session, *, now, limit, topic, business_resolver):
        assert limit == 10
        return [event]

    captured: dict[str, object] = {}

    async def fake_create_phone_call(*, to_number, metadata, dynamic_variables=None, agent_id=None, agent_kind="outbound"):
        captured["to_number"] = to_number
        captured["metadata"] = metadata
        captured["dynamic_variables"] = dynamic_variables
        captured["agent_kind"] = agent_kind
        return "call_123"

    monkeypatch.setattr(delivery.worker_runtime, "claim_outbox_events", fake_claim_outbox_events)
    monkeypatch.setattr(delivery.retell_service, "create_phone_call", fake_create_phone_call)

    result = await delivery.process_outbox_batch(session, now=now, limit=10)

    assert result["claimed_count"] == 1
    assert result["sent_count"] == 1
    assert captured["to_number"] == "+15555550100"
    assert captured["agent_kind"] == "outbound"
    metadata = captured["metadata"]
    dynamic_variables = captured["dynamic_variables"]
    assert metadata["backfill_metadata_contract_version"] == delivery.RETELL_OUTBOUND_METADATA_CONTRACT_VERSION
    assert metadata["backfill_dynamic_variables_contract_version"] == delivery.RETELL_OUTBOUND_DYNAMIC_VARIABLES_CONTRACT_VERSION
    assert metadata["backfill_callback_contract_version"] == delivery.RETELL_OUTBOUND_CALLBACK_CONTRACT_VERSION
    assert metadata["backfill_linkage"]["offer_id"] == str(offer_id)
    assert metadata["backfill_linkage"]["coverage_case_id"] == str(case_id)
    assert metadata["backfill_linkage"]["shift_id"] == str(shift_id)
    assert metadata["backfill_linkage"]["employee_id"] == str(employee_id)
    assert metadata["backfill_linkage"]["contract_version"] == delivery.RETELL_OUTBOUND_CALLBACK_CONTRACT_VERSION
    assert dynamic_variables["backfill_dynamic_contract_version"] == delivery.RETELL_OUTBOUND_DYNAMIC_VARIABLES_CONTRACT_VERSION
    assert dynamic_variables["backfill_callback_contract_version"] == delivery.RETELL_OUTBOUND_CALLBACK_CONTRACT_VERSION
    assert dynamic_variables["employee_first_name"] == "Taylor"
    assert dynamic_variables["employee_last_name"] == "Smith"
    assert dynamic_variables["location_name"] == "Casa Vega West"
    assert dynamic_variables["shift_date"] == "Friday, April 17"
    assert dynamic_variables["shift_start_time"] == "2:00 PM PDT"
    assert dynamic_variables["shift_end_time"] == "6:00 PM PDT"
    shift_context = json.loads(dynamic_variables["shift_context"])
    assert shift_context["week_start_date"] == "2026-04-13"
    assert shift_context["week_end_date"] == "2026-04-19"
    assert shift_context["offered_shift"]["shift_id"] == str(shift_id)
    assert shift_context["weekly_assigned_shifts"][0]["shift_id"] == str(weekly_shift.id)
    assert metadata["employee_first_name"] == "Taylor"
    assert metadata["shift_context"]["offered_shift"]["shift_id"] == str(shift_id)
    assert offer.status == OfferStatus.pending
    assert event.status == OutboxStatus.sent


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


@pytest.mark.asyncio
async def test_handle_twilio_inbound_reply_returns_stop_confirmation(monkeypatch):
    async def fake_handle_command(session, *, from_phone, body, raw_payload=None):
        return delivery.communication_suppressions.SMSCommandResult(
            handled=True,
            response_text="Backfill SMS alerts are off for this number. Reply START to opt back in.",
            action="suppressed",
            created=True,
        )

    monkeypatch.setattr(
        "app.services.delivery.communication_suppressions.handle_inbound_sms_command",
        fake_handle_command,
    )

    message = await delivery.handle_twilio_inbound_reply(
        FakeDeliverySession(),
        from_phone="+15555550100",
        body="STOP",
        raw_payload={"Body": "STOP"},
    )

    assert "Reply START to opt back in." in message
