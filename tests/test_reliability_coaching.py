from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.business import Business, Location, Role
from app.models.common import (
    EmployeeStatus,
    OutboxChannel,
    ReliabilityCoachingAttemptStatus,
    ReliabilityCoachingCaseStatus,
)
from app.models.integrations import RetellConversation
from app.models.reliability import ReliabilityEvent
from app.models.reliability_coaching import ReliabilityCoachingAttempt, ReliabilityCoachingCase
from app.models.scheduling import Shift
from app.models.workforce import Employee
from app.services import reliability_coaching


class _FakeSession:
    def __init__(self):
        self.added: list[object] = []
        self.scalar_queue: list[object] = []
        self.get_map: dict[tuple[type, object], object] = {}
        self.flush_count = 0

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
        self.flush_count += 1

    async def scalar(self, _stmt):
        if self.scalar_queue:
            return self.scalar_queue.pop(0)
        return None

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))


def _business(*, business_id=None, style="supportive") -> Business:
    now = datetime.now(timezone.utc)
    return Business(
        id=business_id or uuid4(),
        name="Backfill",
        display_name="Backfill",
        slug="backfill",
        timezone="America/Los_Angeles",
        settings={"reliability_coaching": {"style": style}},
        place_metadata={},
        status="active",
        created_at=now,
        updated_at=now,
    )


def _employee(*, business_id, employee_id=None) -> Employee:
    now = datetime.now(timezone.utc)
    return Employee(
        id=employee_id or uuid4(),
        business_id=business_id,
        full_name="Jamie Rivera",
        preferred_name="Jamie",
        phone_e164="+15555550123",
        status=EmployeeStatus.active,
        response_profile={},
        employee_metadata={},
        created_at=now,
        updated_at=now,
    )


def _shift(*, business_id, location_id=None, role_id=None) -> Shift:
    now = datetime(2026, 4, 18, 17, 0, tzinfo=timezone.utc)
    location_id = location_id or uuid4()
    role_id = role_id or uuid4()
    location = Location(
        id=location_id,
        business_id=business_id,
        name="Downtown",
        slug="downtown",
        address_line_1="100 Main St",
        locality="Los Angeles",
        region="CA",
        postal_code="90001",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
        google_place_metadata={},
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    role = Role(
        id=role_id,
        business_id=business_id,
        code="server",
        name="Server",
        min_notice_minutes=0,
        coverage_priority=100,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )
    shift = Shift(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=4),
        ends_at=now + timedelta(hours=10),
        status="scheduled",
        lifecycle_status="scheduled",
        staffing_status="open",
        seats_requested=1,
        seats_filled=0,
        requires_manager_approval=False,
        premium_cents=0,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    shift.location = location
    shift.role = role
    return shift


@pytest.mark.asyncio
async def test_record_behavioral_callout_creates_case_on_threshold_crossing(monkeypatch):
    session = _FakeSession()
    business = _business(style="direct")
    employee = _employee(business_id=business.id)
    shift = _shift(business_id=business.id)
    occurred_at = datetime(2026, 4, 18, 18, 0, tzinfo=timezone.utc)
    event = ReliabilityEvent(
        id=uuid4(),
        business_id=business.id,
        employee_id=employee.id,
        shift_id=shift.id,
        location_id=shift.location_id,
        role_id=shift.role_id,
        event_type="callout_submitted",
        occurred_at=occurred_at,
        source="retell_voice",
        event_payload={},
    )

    async def fake_record_event(*_args, **_kwargs):
        return event

    async def fake_refresh(*_args, **_kwargs):
        return None

    async def fake_attempt(*_args, coaching_case, **_kwargs):
        return ReliabilityCoachingAttempt(
            id=uuid4(),
            coaching_case_id=coaching_case.id,
            channel=OutboxChannel.voice,
            status=ReliabilityCoachingAttemptStatus.queued,
            attempt_no=1,
            queued_at=occurred_at,
            prompt_payload={},
            attempt_metadata={},
        )

    async def fake_find_existing(*_args, **_kwargs):
        return None

    async def fake_callout_count(*_args, **_kwargs):
        return 2

    async def fake_active_case(*_args, **_kwargs):
        return None

    monkeypatch.setattr(reliability_coaching, "_find_existing_callout_event", fake_find_existing)
    monkeypatch.setattr(reliability_coaching.reliability_engine, "record_reliability_event", fake_record_event)
    monkeypatch.setattr(
        reliability_coaching.reliability_engine,
        "refresh_employee_reliability_snapshot",
        fake_refresh,
    )
    monkeypatch.setattr(reliability_coaching, "_count_qualifying_callouts", fake_callout_count)
    monkeypatch.setattr(reliability_coaching, "_load_active_case_for_update", fake_active_case)
    monkeypatch.setattr(reliability_coaching, "_create_attempt_and_outbox", fake_attempt)

    result = await reliability_coaching.record_behavioral_callout_and_maybe_trigger_coaching(
        session,
        business=business,
        employee=employee,
        shift=shift,
        source="retell_voice",
        reason_code="sick",
        occurred_at=occurred_at,
    )

    coaching_cases = [entry for entry in session.added if isinstance(entry, ReliabilityCoachingCase)]
    triggers = [entry for entry in session.added if entry.__class__.__name__ == "ReliabilityCoachingTrigger"]
    assert result["status"] == "case_created"
    assert result["qualifying_callout_count"] == 2
    assert len(coaching_cases) == 1
    assert coaching_cases[0].coaching_style == "direct"
    assert len(triggers) == 1


@pytest.mark.asyncio
async def test_record_behavioral_callout_appends_to_suppressed_case_without_new_attempt(monkeypatch):
    session = _FakeSession()
    business = _business()
    employee = _employee(business_id=business.id)
    shift = _shift(business_id=business.id)
    occurred_at = datetime(2026, 4, 18, 19, 0, tzinfo=timezone.utc)
    event = ReliabilityEvent(
        id=uuid4(),
        business_id=business.id,
        employee_id=employee.id,
        shift_id=shift.id,
        location_id=shift.location_id,
        role_id=shift.role_id,
        event_type="callout_submitted",
        occurred_at=occurred_at,
        source="retell_voice",
        event_payload={},
    )
    coaching_case = ReliabilityCoachingCase(
        id=uuid4(),
        business_id=business.id,
        employee_id=employee.id,
        case_status=ReliabilityCoachingCaseStatus.suppressed,
        delivery_status="exhausted",
        coaching_style="supportive",
        policy_version="v1",
        prompt_version="v1",
        trigger_metric="callout_count_rolling_7d",
        trigger_threshold=2,
        trigger_window_days=7,
        trigger_count=1,
        opened_at=occurred_at - timedelta(days=1),
        suppressed_at=occurred_at - timedelta(hours=2),
        suppression_reason_code="manager_review",
        case_metadata={},
    )
    create_attempt_calls: list[object] = []

    async def fake_record_event(*_args, **_kwargs):
        return event

    async def fake_refresh(*_args, **_kwargs):
        return None

    async def fake_create_attempt(*_args, **_kwargs):
        create_attempt_calls.append(True)
        return None

    session.scalar_queue = [None]
    async def fake_find_existing(*_args, **_kwargs):
        return None

    async def fake_callout_count(*_args, **_kwargs):
        return 3

    async def fake_active_case(*_args, **_kwargs):
        return coaching_case

    monkeypatch.setattr(reliability_coaching, "_find_existing_callout_event", fake_find_existing)
    monkeypatch.setattr(reliability_coaching.reliability_engine, "record_reliability_event", fake_record_event)
    monkeypatch.setattr(
        reliability_coaching.reliability_engine,
        "refresh_employee_reliability_snapshot",
        fake_refresh,
    )
    monkeypatch.setattr(reliability_coaching, "_count_qualifying_callouts", fake_callout_count)
    monkeypatch.setattr(reliability_coaching, "_load_active_case_for_update", fake_active_case)
    monkeypatch.setattr(reliability_coaching, "_create_attempt_and_outbox", fake_create_attempt)

    result = await reliability_coaching.record_behavioral_callout_and_maybe_trigger_coaching(
        session,
        business=business,
        employee=employee,
        shift=shift,
        source="retell_voice",
        reason_code="family_emergency",
        occurred_at=occurred_at,
    )

    assert result["status"] == "case_appended"
    assert coaching_case.trigger_count == 2
    assert create_attempt_calls == []


@pytest.mark.asyncio
async def test_process_coaching_conversation_completion_requeues_after_no_answer(monkeypatch):
    session = _FakeSession()
    business = _business()
    employee = _employee(business_id=business.id)
    now = datetime(2026, 4, 18, 20, 0, tzinfo=timezone.utc)
    coaching_case = ReliabilityCoachingCase(
        id=uuid4(),
        business_id=business.id,
        employee_id=employee.id,
        case_status=ReliabilityCoachingCaseStatus.open,
        delivery_status="in_flight",
        coaching_style="supportive",
        policy_version="v1",
        prompt_version="v1",
        trigger_metric="callout_count_rolling_7d",
        trigger_threshold=2,
        trigger_window_days=7,
        trigger_count=2,
        opened_at=now - timedelta(days=1),
        case_metadata={"latest_qualifying_callout_count": 2},
    )
    attempt = ReliabilityCoachingAttempt(
        id=uuid4(),
        coaching_case_id=coaching_case.id,
        channel=OutboxChannel.voice,
        status=ReliabilityCoachingAttemptStatus.in_flight,
        attempt_no=1,
        provider="retell",
        provider_conversation_id="call_123",
        queued_at=now - timedelta(hours=1),
        sent_at=now - timedelta(minutes=30),
        prompt_payload={},
        attempt_metadata={},
    )
    session.get_map[(Business, business.id)] = business
    session.get_map[(Employee, employee.id)] = employee
    session.get_map[(ReliabilityCoachingCase, coaching_case.id)] = coaching_case
    session.scalar_queue = [attempt, None]
    captured: dict[str, object] = {}

    async def fake_create_attempt(*_args, earliest_allowed_at=None, **_kwargs):
        captured["earliest_allowed_at"] = earliest_allowed_at
        return ReliabilityCoachingAttempt(
            id=uuid4(),
            coaching_case_id=coaching_case.id,
            channel=OutboxChannel.voice,
            status=ReliabilityCoachingAttemptStatus.queued,
            attempt_no=2,
            queued_at=now,
            prompt_payload={},
            attempt_metadata={},
        )

    monkeypatch.setattr(
        reliability_coaching,
        "coaching_policy_for_business",
        lambda _business: reliability_coaching.ReliabilityCoachingPolicy(
            style="supportive",
            threshold_count=2,
            window_days=7,
            max_attempts=2,
            no_answer_cooldown_hours=24,
            quiet_hours_start_local_hour=20,
            quiet_hours_end_local_hour=8,
        ),
    )
    async def fake_attempt_count(*_args, **_kwargs):
        return 1

    monkeypatch.setattr(reliability_coaching, "_load_attempt_count", fake_attempt_count)
    monkeypatch.setattr(reliability_coaching, "_create_attempt_and_outbox", fake_create_attempt)

    conversation = RetellConversation(
        id=uuid4(),
        external_id="call_123",
        conversation_type="call",
        metadata_json={},
        raw_payload={},
        analysis={},
        disconnection_reason="no_answer",
        transcript_text="",
        started_at=now - timedelta(minutes=5),
        ended_at=now,
    )

    result = await reliability_coaching.process_coaching_conversation_completion(session, conversation)

    assert result["status"] == "processed"
    assert attempt.status == ReliabilityCoachingAttemptStatus.no_answer
    assert "earliest_allowed_at" in captured
    assert any(entry.__class__.__name__ == "ReliabilityCoachingOutcome" for entry in session.added)


@pytest.mark.asyncio
async def test_process_coaching_conversation_completion_escalates_manager_followup(monkeypatch):
    session = _FakeSession()
    business = _business()
    employee = _employee(business_id=business.id)
    now = datetime(2026, 4, 18, 21, 0, tzinfo=timezone.utc)
    coaching_case = ReliabilityCoachingCase(
        id=uuid4(),
        business_id=business.id,
        employee_id=employee.id,
        case_status=ReliabilityCoachingCaseStatus.open,
        delivery_status="in_flight",
        coaching_style="direct",
        policy_version="v1",
        prompt_version="v1",
        trigger_metric="callout_count_rolling_7d",
        trigger_threshold=2,
        trigger_window_days=7,
        trigger_count=2,
        opened_at=now - timedelta(days=1),
        case_metadata={},
    )
    attempt = ReliabilityCoachingAttempt(
        id=uuid4(),
        coaching_case_id=coaching_case.id,
        channel=OutboxChannel.voice,
        status=ReliabilityCoachingAttemptStatus.in_flight,
        attempt_no=1,
        provider="retell",
        provider_conversation_id="call_456",
        queued_at=now - timedelta(hours=1),
        prompt_payload={},
        attempt_metadata={},
    )
    session.get_map[(ReliabilityCoachingAttempt, attempt.id)] = attempt
    session.get_map[(ReliabilityCoachingCase, coaching_case.id)] = coaching_case
    session.get_map[(Employee, employee.id)] = employee
    session.scalar_queue = [None]

    conversation = RetellConversation(
        id=uuid4(),
        external_id="call_456",
        conversation_type="call",
        metadata_json={"reliability_coaching_attempt_id": str(attempt.id)},
        raw_payload={"custom_analysis_data": {"coaching_result": "manager_followup_requested"}},
        analysis={},
        transcript_text="Please have my manager call me back.",
        started_at=now - timedelta(minutes=5),
        ended_at=now,
    )

    result = await reliability_coaching.process_coaching_conversation_completion(session, conversation)

    assert result["status"] == "processed"
    assert coaching_case.case_status == ReliabilityCoachingCaseStatus.escalated
    assert attempt.status == ReliabilityCoachingAttemptStatus.completed
    assert any(entry.__class__.__name__ == "ReliabilityCoachingOutcome" for entry in session.added)
