from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.business import Location, Role
from app.models.common import (
    AssignmentStatus,
    EmployeeStatus,
    RetellConversationType,
    ShiftLifecycleStatus,
    ShiftStaffingStatus,
    ShiftStatus,
)
from app.models.identity import User
from app.models.integrations import RetellConversation
from app.models.scheduling import Shift, ShiftAssignment
from app.models.workforce import Employee
from app.services import retell_workflow


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)

    def unique(self):
        return self


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarResult(self._values)

    def scalar_one_or_none(self):
        if not self._values:
            return None
        return self._values[0]


class FakeSession:
    def __init__(self):
        self.scalar_queue: list[object] = []
        self.execute_queue: list[list[object]] = []
        self.get_map: dict[tuple[type, object], object] = {}
        self.flushed = 0
        self.added: list[object] = []

    async def scalar(self, _query):
        if self.scalar_queue:
            return self.scalar_queue.pop(0)
        return None

    async def execute(self, _query):
        descriptions = getattr(_query, "column_descriptions", [])
        entity = descriptions[0].get("entity") if descriptions else None
        if entity is RetellConversation:
            return _ExecuteResult([])
        values = self.execute_queue.pop(0) if self.execute_queue else []
        return _ExecuteResult(values)

    async def get(self, model, object_id, **_kwargs):
        return self.get_map.get((model, object_id))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1
        return None


@pytest.mark.asyncio
async def test_lookup_caller_returns_upcoming_assigned_shifts(monkeypatch):
    session = FakeSession()
    now = datetime(2026, 4, 16, 16, 0, tzinfo=timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    employee_id = uuid4()
    user = User(
        id=uuid4(),
        full_name="Taylor Caller",
        email="taylor@example.com",
        primary_phone_e164="+15555550100",
        is_phone_verified=True,
        onboarding_completed_at=now,
        profile_metadata={},
        created_at=now,
        updated_at=now,
    )
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Taylor Caller",
        phone_e164="+15555550100",
        email="taylor@example.com",
        status=EmployeeStatus.active,
        response_profile={},
        employee_metadata={},
        created_at=now,
        updated_at=now,
    )
    location = Location(
        id=location_id,
        business_id=business_id,
        name="Downtown",
        slug="downtown",
        address_line_1="123 Main",
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
        code="barista",
        name="Barista",
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
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
        status=ShiftStatus.scheduled,
        lifecycle_status=ShiftLifecycleStatus.scheduled,
        staffing_status=ShiftStaffingStatus.covered,
        seats_requested=1,
        seats_filled=1,
        requires_manager_approval=False,
        premium_cents=0,
        notes=None,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=shift.id,
        employee_id=employee_id,
        assigned_via="scheduler_ui",
        status=AssignmentStatus.assigned,
        sequence_no=1,
        assignment_metadata={},
        created_at=now,
        updated_at=now,
    )
    shift.location = location
    shift.role = role
    shift.assignments = [assignment]

    async def fake_find_latest_actionable_offer_for_phone(_session, _phone_e164):
        return None

    monkeypatch.setattr(
        retell_workflow.delivery,
        "find_latest_actionable_offer_for_phone",
        fake_find_latest_actionable_offer_for_phone,
    )
    monkeypatch.setattr(retell_workflow, "_current_utc_now", lambda: now)

    session.scalar_queue = [user, employee]
    session.execute_queue = [[shift]]

    result = await retell_workflow.lookup_caller(session, "+15555550100")

    assert result["user"]["id"] == str(user.id)
    assert result["employee"]["id"] == str(employee.id)
    assert result["actionable_offer_id"] is None
    assert result["assigned_shift_count"] == 1
    assert result["next_assigned_shift_id"] == str(shift.id)
    assert result["assigned_shifts"] == [
        {
            "id": str(shift.id),
            "location_id": str(location.id),
            "location_name": "Downtown",
            "role_id": str(role.id),
            "role_name": "Barista",
            "starts_at": shift.starts_at.isoformat(),
            "ends_at": shift.ends_at.isoformat(),
            "status": shift.status,
            "lifecycle_status": ShiftLifecycleStatus.scheduled,
            "staffing_status": ShiftStaffingStatus.covered,
            "notes": None,
            "date_label": "Today (Thursday, April 16)",
            "start_time_label": "11:00 AM",
            "end_time_label": "7:00 PM",
            "local_time_range": "11:00 AM to 7:00 PM PDT",
            "timezone": "America/Los_Angeles",
            "timezone_abbr": "PDT",
            "relative_day_label": "Today",
            "summary": "Today (Thursday, April 16) from 11:00 AM to 7:00 PM PDT as Barista at Downtown",
        }
    ]
    assert result["assigned_shift_schedule_summary"] == (
        "1. Today (Thursday, April 16) from 11:00 AM to 7:00 PM PDT as Barista at Downtown"
    )


@pytest.mark.asyncio
async def test_lookup_caller_returns_full_future_published_schedule(monkeypatch):
    session = FakeSession()
    now = datetime(2026, 4, 16, 16, 0, tzinfo=timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    employee_id = uuid4()
    employee = Employee(
        id=employee_id,
        business_id=business_id,
        full_name="Taylor Caller",
        phone_e164="+15555550100",
        email="taylor@example.com",
        status=EmployeeStatus.active,
        response_profile={},
        employee_metadata={},
        created_at=now,
        updated_at=now,
    )
    location = Location(
        id=location_id,
        business_id=business_id,
        name="Downtown",
        slug="downtown",
        address_line_1="123 Main",
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
        code="barista",
        name="Barista",
        min_notice_minutes=0,
        coverage_priority=100,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )

    def build_shift(start_offset_days: int, start_hour_utc: int, end_hour_utc: int, *, end_offset_days: int = 0):
        shift = Shift(
            id=uuid4(),
            business_id=business_id,
            location_id=location_id,
            role_id=role_id,
            source_system="backfill_native",
            timezone="America/Los_Angeles",
            starts_at=datetime(2026, 4, 16 + start_offset_days, start_hour_utc, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 16 + start_offset_days + end_offset_days, end_hour_utc, 0, tzinfo=timezone.utc),
            status=ShiftStatus.scheduled,
            lifecycle_status=ShiftLifecycleStatus.scheduled,
            staffing_status=ShiftStaffingStatus.covered,
            seats_requested=1,
            seats_filled=1,
            requires_manager_approval=False,
            premium_cents=0,
            notes=None,
            shift_metadata={},
            created_at=now,
            updated_at=now,
        )
        assignment = ShiftAssignment(
            id=uuid4(),
            shift_id=shift.id,
            employee_id=employee_id,
            assigned_via="scheduler_ui",
            status=AssignmentStatus.assigned,
            sequence_no=1,
            assignment_metadata={},
            created_at=now,
            updated_at=now,
        )
        shift.location = location
        shift.role = role
        shift.assignments = [assignment]
        return shift

    first_shift = build_shift(0, 18, 22)
    second_shift = build_shift(6, 16, 0, end_offset_days=1)

    async def fake_find_latest_actionable_offer_for_phone(_session, _phone_e164):
        return None

    monkeypatch.setattr(
        retell_workflow.delivery,
        "find_latest_actionable_offer_for_phone",
        fake_find_latest_actionable_offer_for_phone,
    )
    monkeypatch.setattr(retell_workflow, "_current_utc_now", lambda: now)

    session.scalar_queue = [None, employee]
    session.execute_queue = [[first_shift, second_shift]]

    result = await retell_workflow.lookup_caller(session, "+15555550100")

    assert result["assigned_shift_count"] == 2
    assert result["next_assigned_shift_id"] == str(first_shift.id)
    assert len(result["assigned_shifts"]) == 2
    assert "Today (Thursday, April 16)" in result["assigned_shift_schedule_summary"]
    assert "Wednesday, April 22" in result["assigned_shift_schedule_summary"]
    assert "Barista at Downtown" in result["assigned_shift_schedule_summary"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("granted", "expected_status", "expected_reason"),
    [
        (True, "consent_granted", "voice_consent_granted"),
        (False, "consent_revoked", "voice_consent_revoked"),
    ],
)
async def test_log_consent_updates_sms_suppression_and_employee_preferences(
    monkeypatch,
    granted,
    expected_status,
    expected_reason,
):
    session = FakeSession()
    now = datetime.now(timezone.utc)
    employee = Employee(
        id=uuid4(),
        business_id=uuid4(),
        full_name="Taylor Caller",
        phone_e164="+15555550100",
        email="taylor@example.com",
        status=EmployeeStatus.active,
        response_profile={},
        employee_metadata={},
        created_at=now,
        updated_at=now,
    )
    session.get_map[(Employee, employee.id)] = employee
    captured: dict[str, object] = {}

    async def fake_clear(*_args, **kwargs):
        captured.update(kwargs)
        return object(), True

    async def fake_suppress(*_args, **kwargs):
        captured.update(kwargs)
        return object(), True

    monkeypatch.setattr(
        retell_workflow.communication_suppressions,
        "clear_destination_suppression",
        fake_clear,
    )
    monkeypatch.setattr(
        retell_workflow.communication_suppressions,
        "suppress_destination",
        fake_suppress,
    )

    result = await retell_workflow.log_consent(
        session,
        {
            "employee_id": str(employee.id),
            "granted": granted,
            "channel": "inbound_call",
        },
    )

    assert result["status"] == expected_status
    assert result["employee_id"] == str(employee.id)
    assert result["phone"] == "+15555550100"
    assert result["changed"] is True
    assert captured["channel"] == "sms"
    assert captured["destination"] == "+15555550100"
    assert captured["source"] == "retell_voice_consent"
    assert captured["reason_code"] == expected_reason
    preferences = employee.employee_metadata["notification_preferences"]
    assert preferences["schedule_publish_sms_enabled"] is granted
    if granted:
        assert preferences["sms_opted_out_at"] is None
        assert preferences["sms_opt_out_reason"] is None
    else:
        assert preferences["sms_opted_out_at"] is not None
        assert preferences["sms_opt_out_reason"] == "voice_consent_revoked"
    assert employee.employee_metadata["voice_consent"]["granted"] is granted


@pytest.mark.asyncio
async def test_create_vacancy_uses_published_callout_amendment_before_coverage(monkeypatch):
    session = FakeSession()
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift_id = uuid4()
    employee_id = uuid4()
    assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=shift_id,
        employee_id=employee_id,
        assigned_via="scheduler_ui",
        status=AssignmentStatus.assigned,
        sequence_no=1,
        assignment_metadata={},
        created_at=now,
        updated_at=now,
    )
    shift = Shift(
        id=shift_id,
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=now,
        ends_at=now + timedelta(hours=8),
        status=ShiftStatus.scheduled,
        lifecycle_status=ShiftLifecycleStatus.scheduled,
        staffing_status=ShiftStaffingStatus.covered,
        seats_requested=1,
        seats_filled=1,
        requires_manager_approval=False,
        premium_cents=0,
        notes=None,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )
    shift.assignments = [assignment]
    session.get_map[(Shift, shift_id)] = shift
    captured: dict[str, object] = {}
    coverage_case_id = uuid4()

    async def fake_apply(_session, _business_id, _shift_id, payload):
        captured["business_id"] = _business_id
        captured["shift_id"] = _shift_id
        captured["payload"] = payload
        return object()

    async def fake_create_vacancy_for_shift(
        _session,
        *,
        shift_id,
        employee_id=None,
        triggered_by,
        reason_code="scheduler_vacancy",
        auto_execute=True,
    ):
        captured["coverage_shift_id"] = shift_id
        captured["coverage_employee_id"] = employee_id
        captured["triggered_by"] = triggered_by
        captured["reason_code"] = reason_code
        captured["auto_execute"] = auto_execute
        return {
            "shift_id": shift_id,
            "coverage_case_id": coverage_case_id,
            "offers": ["offer_123"],
        }

    monkeypatch.setattr(retell_workflow.scheduling, "apply_published_shift_amendment", fake_apply)
    monkeypatch.setattr(retell_workflow.scheduler_sync, "create_vacancy_for_shift", fake_create_vacancy_for_shift)

    result = await retell_workflow.create_vacancy(
        session,
        {
            "shift_id": str(shift_id),
            "employee_id": str(employee_id),
            "source": "retell_post_call",
            "conversation_summary": "Taylor called out sick for the morning shift.",
        },
    )

    payload = captured["payload"]
    assert payload.action == "unassign_shift"
    assert payload.reason_code == "callout"
    assert payload.source == "retell_voice"
    assert payload.note == "Taylor called out sick for the morning shift."
    assert captured["business_id"] == business_id
    assert captured["shift_id"] == shift_id
    assert captured["coverage_shift_id"] == shift_id
    assert captured["coverage_employee_id"] == employee_id
    assert captured["triggered_by"] == "retell_post_call"
    assert captured["reason_code"] == "callout"
    assert result == {
        "status": "vacancy_created",
        "shift_id": str(shift_id),
        "coverage_case_id": str(coverage_case_id),
        "offers": ["offer_123"],
        "used_published_amendment": True,
        "reason_code": "callout",
    }


@pytest.mark.asyncio
async def test_build_inbound_webhook_response_personalizes_recognized_single_shift(monkeypatch):
    session = FakeSession()
    shift_id = uuid4()

    async def fake_lookup(_session, phone: str):
        assert phone == "+15555550100"
        return {
            "phone": phone,
            "user": None,
            "employee": {
                "id": str(uuid4()),
                "full_name": "Taylor Caller",
                "business_id": str(uuid4()),
                "location_id": str(uuid4()),
            },
            "assigned_shifts": [
                {
                    "id": str(shift_id),
                    "location_id": str(uuid4()),
                    "location_name": "Downtown",
                    "role_id": str(uuid4()),
                    "role_name": "Barista",
                    "starts_at": "2026-04-16T18:00:00+00:00",
                    "ends_at": "2026-04-17T02:00:00+00:00",
                    "status": "covered",
                    "lifecycle_status": "scheduled",
                    "staffing_status": "covered",
                    "date_label": "Thursday, April 16",
                    "local_time_range": "11:00 AM to 7:00 PM PDT",
                    "summary": "Thursday, April 16 from 11:00 AM to 7:00 PM PDT as Barista at Downtown",
                }
            ],
            "assigned_shift_schedule_summary": (
                "1. Thursday, April 16 from 11:00 AM to 7:00 PM PDT as Barista at Downtown"
            ),
            "actionable_offer_id": None,
        }

    monkeypatch.setattr(retell_workflow, "lookup_caller", fake_lookup)

    result = await retell_workflow.build_inbound_webhook_response(
        session,
        {
            "event": "call_inbound",
            "call_inbound": {
                "from_number": "+15555550100",
                "agent_id": "agent_inbound_123",
            },
        },
    )

    payload = result["call_inbound"]
    assert payload["override_agent_id"] == "agent_inbound_123"
    assert payload["metadata"]["caller_phone"] == "+15555550100"
    assert payload["metadata"]["employee_found"] is True
    assert payload["metadata"]["upcoming_shift_count"] == 1
    assert payload["metadata"]["shift_id"] == str(shift_id)
    assert payload["metadata"]["assigned_shift_schedule_summary"].startswith("1. Thursday, April 16")
    assert payload["dynamic_variables"]["caller_first_name"] == "Taylor"
    assert payload["dynamic_variables"]["employee_found"] == "true"
    assert payload["dynamic_variables"]["selected_shift_id"] == str(shift_id)
    assert payload["dynamic_variables"]["selected_shift_summary"].startswith("Thursday, April 16")
    assert payload["dynamic_variables"]["assigned_shift_schedule_summary"].startswith("1. Thursday, April 16")
    begin_message = payload["agent_override"]["retell_llm"]["begin_message"]
    assert "Hi Taylor" in begin_message
    assert "upcoming Barista shift" in begin_message
    assert "Backfill's AI assistant" in begin_message


@pytest.mark.asyncio
async def test_build_inbound_webhook_response_preloads_full_schedule_summary(monkeypatch):
    session = FakeSession()

    async def fake_lookup(_session, phone: str):
        assert phone == "+15555550100"
        return {
            "phone": phone,
            "user": None,
            "employee": {
                "id": str(uuid4()),
                "full_name": "Taylor Caller",
                "business_id": str(uuid4()),
                "location_id": str(uuid4()),
            },
            "assigned_shifts": [
                {
                    "id": str(uuid4()),
                    "location_id": str(uuid4()),
                    "location_name": "Downtown",
                    "role_id": str(uuid4()),
                    "role_name": "Barista",
                    "starts_at": "2026-04-16T18:00:00+00:00",
                    "ends_at": "2026-04-17T02:00:00+00:00",
                    "status": "covered",
                    "lifecycle_status": "scheduled",
                    "staffing_status": "covered",
                    "date_label": "Thursday, April 16",
                    "local_time_range": "11:00 AM to 7:00 PM PDT",
                    "summary": "Thursday, April 16 from 11:00 AM to 7:00 PM PDT as Barista at Downtown",
                },
                {
                    "id": str(uuid4()),
                    "location_id": str(uuid4()),
                    "location_name": "Downtown",
                    "role_id": str(uuid4()),
                    "role_name": "Barista",
                    "starts_at": "2026-04-22T16:00:00+00:00",
                    "ends_at": "2026-04-23T00:00:00+00:00",
                    "status": "covered",
                    "lifecycle_status": "scheduled",
                    "staffing_status": "covered",
                    "date_label": "Wednesday, April 22",
                    "local_time_range": "9:00 AM to 5:00 PM PDT",
                    "summary": "Wednesday, April 22 from 9:00 AM to 5:00 PM PDT as Barista at Downtown",
                },
            ],
            "assigned_shift_schedule_summary": (
                "1. Thursday, April 16 from 11:00 AM to 7:00 PM PDT as Barista at Downtown\n"
                "2. Wednesday, April 22 from 9:00 AM to 5:00 PM PDT as Barista at Downtown"
            ),
            "actionable_offer_id": None,
        }

    monkeypatch.setattr(retell_workflow, "lookup_caller", fake_lookup)

    result = await retell_workflow.build_inbound_webhook_response(
        session,
        {
            "event": "call_inbound",
            "call_inbound": {
                "from_number": "+15555550100",
                "agent_id": "agent_inbound_123",
            },
        },
    )

    payload = result["call_inbound"]
    assert payload["metadata"]["upcoming_shift_count"] == 2
    assert len(payload["metadata"]["assigned_shifts"]) == 2
    assert "Thursday, April 16" in payload["dynamic_variables"]["assigned_shift_schedule_summary"]
    assert "Wednesday, April 22" in payload["dynamic_variables"]["assigned_shift_schedule_summary"]
    begin_message = payload["agent_override"]["retell_llm"]["begin_message"]
    assert "2 upcoming published shifts" in begin_message
    assert "starting with your upcoming Barista shift on Thursday, April 16" in begin_message


@pytest.mark.asyncio
async def test_build_inbound_webhook_response_prefers_env_inbound_agent_id(monkeypatch):
    session = FakeSession()

    async def fake_lookup(_session, phone: str):
        return {
            "phone": phone,
            "user": None,
            "employee": None,
            "assigned_shifts": [],
            "assigned_shift_schedule_summary": "",
            "actionable_offer_id": None,
        }

    monkeypatch.setattr(retell_workflow, "lookup_caller", fake_lookup)
    monkeypatch.setattr(
        retell_workflow,
        "settings",
        SimpleNamespace(
            retell_agent_id_inbound="agent_env_123",
            retell_agent_id="",
        ),
    )

    result = await retell_workflow.build_inbound_webhook_response(
        session,
        {
            "event": "call_inbound",
            "call_inbound": {
                "from_number": "+15555550100",
                "agent_id": "agent_payload_456",
            },
        },
    )

    assert result["call_inbound"]["override_agent_id"] == "agent_env_123"


@pytest.mark.asyncio
async def test_persist_payload_preserves_existing_transcript_and_metadata_on_call_end():
    session = FakeSession()
    call_id = "call_123"
    existing = RetellConversation(
        id=uuid4(),
        external_id=call_id,
        conversation_type=RetellConversationType.call,
        event_type="transcript_updated",
        direction="inbound",
        status="ongoing",
        agent_id="agent_inbound_123",
        phone_from="+15555550100",
        phone_to="+18002225345",
        transcript_text="user: I can't make it today.",
        transcript_items=[{"role": "user", "content": "I can't make it today."}],
        analysis={"backfill_processing": {"callout": {"status": "pending"}}},
        metadata_json={"employee_id": "emp_123", "assigned_shifts": [{"id": "shift_today"}]},
        raw_payload={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.scalar_queue = [existing]

    conversation = await retell_workflow.persist_payload(
        session,
        {
            "event": "call_ended",
            "call": {
                "call_id": call_id,
                "direction": "inbound",
                "call_status": "ended",
                "agent_id": "agent_inbound_123",
                "from_number": "+15555550100",
                "to_number": "+18002225345",
                "end_timestamp": "2026-04-16T18:10:00Z",
            },
        },
    )

    assert conversation is existing
    assert conversation.event_type == "call_ended"
    assert conversation.status == "ended"
    assert conversation.transcript_text == "user: I can't make it today."
    assert conversation.transcript_items == [{"role": "user", "content": "I can't make it today."}]
    assert conversation.metadata_json["employee_id"] == "emp_123"
    assert conversation.analysis["backfill_processing"]["callout"]["status"] == "pending"


@pytest.mark.asyncio
async def test_process_inbound_conversation_completion_creates_callout_from_transcript(monkeypatch):
    session = FakeSession()
    employee_id = uuid4()
    shift_today = uuid4()
    shift_tomorrow = uuid4()
    conversation = RetellConversation(
        id=uuid4(),
        external_id="call_123",
        conversation_type=RetellConversationType.call,
        event_type="call_ended",
        direction="inbound",
        status="ended",
        agent_id="agent_inbound_123",
        phone_from="+15555550100",
        phone_to="+18002225345",
        conversation_summary="Caller said they cannot make today's shift.",
        transcript_text="user: I need to call out for today.",
        transcript_items=[
            {"role": "agent", "content": "Which shift are you calling about?"},
            {"role": "user", "content": "I need to call out for today."},
        ],
        analysis={},
        metadata_json={
            "employee_id": str(employee_id),
            "caller_phone": "+15555550100",
            "assigned_shifts": [
                {
                    "id": str(shift_today),
                    "role_name": "Barista",
                    "location_name": "Downtown",
                    "starts_at": "2026-04-16T18:00:00+00:00",
                    "timezone": "America/Los_Angeles",
                    "start_time_label": "11:00 AM",
                    "date_label": "Today (Thursday, April 16)",
                    "relative_day_label": "Today",
                    "summary": "Today (Thursday, April 16) from 11:00 AM to 7:00 PM PDT as Barista at Downtown",
                },
                {
                    "id": str(shift_tomorrow),
                    "role_name": "Barista",
                    "location_name": "Downtown",
                    "starts_at": "2026-04-17T18:00:00+00:00",
                    "timezone": "America/Los_Angeles",
                    "start_time_label": "11:00 AM",
                    "date_label": "Tomorrow (Friday, April 17)",
                    "relative_day_label": "Tomorrow",
                    "summary": "Tomorrow (Friday, April 17) from 11:00 AM to 7:00 PM PDT as Barista at Downtown",
                },
            ],
        },
        raw_payload={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    captured: dict[str, object] = {}

    async def fake_create_vacancy(_session, args):
        captured.update(args)
        return {
            "status": "vacancy_created",
            "shift_id": args["shift_id"],
            "coverage_case_id": str(uuid4()),
            "offers": [],
            "used_published_amendment": True,
        }

    monkeypatch.setattr(retell_workflow, "create_vacancy", fake_create_vacancy)

    result = await retell_workflow.process_inbound_conversation_completion(session, conversation)

    assert captured["shift_id"] == str(shift_today)
    assert captured["employee_id"] == str(employee_id)
    assert captured["source"] == "retell_post_call"
    assert result["callout"]["status"] == "vacancy_created"
    assert result["consent"]["status"] == "no_consent_change"
    assert conversation.analysis["backfill_processing"]["callout"]["status"] == "vacancy_created"


@pytest.mark.asyncio
async def test_process_inbound_conversation_completion_detects_cant_make_my_shift_tomorrow(monkeypatch):
    session = FakeSession()
    employee_id = uuid4()
    shift_today = uuid4()
    shift_tomorrow = uuid4()
    shift_saturday = uuid4()
    conversation = RetellConversation(
        id=uuid4(),
        external_id="call_live_shape",
        conversation_type=RetellConversationType.call,
        event_type="transcript_updated",
        direction="inbound",
        status="ongoing",
        agent_id="agent_inbound_123",
        phone_from="+15555550100",
        phone_to="+18002225345",
        conversation_summary=(
            "The user contacted the AI assistant to report they cannot work their only "
            "shift scheduled for tomorrow. The agent confirmed the shift details and "
            "asked for the type of reason, which the user provided as personal."
        ),
        transcript_text=(
            "agent: Are you calling to report that you can't make an upcoming shift?\n"
            "user: Yes. I can't make my shift tomorrow.\n"
            "agent: Which shift tomorrow do you mean?\n"
            "user: That's the only shift that I have tomorrow.\n"
            "agent: Just to confirm, you're unable to work your only shift tomorrow, correct?\n"
            "user: Correct.\n"
            "agent: Do you want to share a broad reason?\n"
            "user: Personal."
        ),
        transcript_items=[
            {"role": "user", "content": "Yes. I can't make my shift tomorrow."},
            {"role": "user", "content": "That's the only shift that I have tomorrow."},
            {"role": "user", "content": "Correct."},
            {"role": "user", "content": "Personal."},
        ],
        analysis={},
        metadata_json={
            "employee_id": str(employee_id),
            "caller_phone": "+15555550100",
            "assigned_shifts": [
                {
                    "id": str(shift_today),
                    "role_name": "General Manager",
                    "location_name": "Pasadena",
                    "starts_at": "2026-04-16T21:00:00+00:00",
                    "timezone": "America/Los_Angeles",
                    "start_time_label": "2:00 PM",
                    "date_label": "Today (Thursday, April 16)",
                    "relative_day_label": "Today",
                    "summary": "Today (Thursday, April 16) from 2:00 PM to 6:00 PM PDT as General Manager at Pasadena",
                },
                {
                    "id": str(shift_tomorrow),
                    "role_name": "General Manager",
                    "location_name": "Pasadena",
                    "starts_at": "2026-04-17T21:00:00+00:00",
                    "timezone": "America/Los_Angeles",
                    "start_time_label": "2:00 PM",
                    "date_label": "Tomorrow (Friday, April 17)",
                    "relative_day_label": "Tomorrow",
                    "summary": "Tomorrow (Friday, April 17) from 2:00 PM to 6:00 PM PDT as General Manager at Pasadena",
                },
                {
                    "id": str(shift_saturday),
                    "role_name": "General Manager",
                    "location_name": "Pasadena",
                    "starts_at": "2026-04-18T21:00:00+00:00",
                    "timezone": "America/Los_Angeles",
                    "start_time_label": "2:00 PM",
                    "date_label": "Saturday, April 18",
                    "relative_day_label": "",
                    "summary": "Saturday, April 18 from 2:00 PM to 6:00 PM PDT as General Manager at Pasadena",
                },
            ],
        },
        raw_payload={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    captured: dict[str, object] = {}

    async def fake_create_vacancy(_session, args):
        captured.update(args)
        return {
            "status": "vacancy_created",
            "shift_id": args["shift_id"],
            "coverage_case_id": str(uuid4()),
            "offers": [],
            "used_published_amendment": True,
        }

    monkeypatch.setattr(retell_workflow, "create_vacancy", fake_create_vacancy)

    result = await retell_workflow.process_inbound_conversation_completion(session, conversation)

    assert captured["shift_id"] == str(shift_tomorrow)
    assert captured["employee_id"] == str(employee_id)
    assert captured["source"] == "retell_post_call"
    assert result["callout"]["status"] == "vacancy_created"
    assert result["callout"]["resolution"] == "transcript_shift_match"


@pytest.mark.asyncio
async def test_process_inbound_conversation_completion_uses_high_confidence_retell_callout_intent(monkeypatch):
    session = FakeSession()
    employee_id = uuid4()
    shift_tomorrow = uuid4()
    conversation = RetellConversation(
        id=uuid4(),
        external_id="call_retell_high_confidence",
        conversation_type=RetellConversationType.call,
        event_type="call_analyzed",
        direction="inbound",
        status="ended",
        agent_id="agent_inbound_123",
        phone_from="+15555550100",
        phone_to="+18002225345",
        conversation_summary="Caller confirmed they cannot work their only shift tomorrow.",
        transcript_text="user: Correct. Personal.",
        transcript_items=[
            {"role": "user", "content": "That's the only shift that I have tomorrow."},
            {"role": "user", "content": "Correct."},
        ],
        analysis={
            "custom_analysis_data": {
                "call_intent": "callout",
                "call_intent_confidence": "high",
            }
        },
        metadata_json={
            "employee_id": str(employee_id),
            "caller_phone": "+15555550100",
            "assigned_shifts": [
                {
                    "id": str(shift_tomorrow),
                    "role_name": "General Manager",
                    "location_name": "Pasadena",
                    "starts_at": "2026-04-17T21:00:00+00:00",
                    "timezone": "America/Los_Angeles",
                    "start_time_label": "2:00 PM",
                    "date_label": "Tomorrow (Friday, April 17)",
                    "relative_day_label": "Tomorrow",
                    "summary": "Tomorrow (Friday, April 17) from 2:00 PM to 6:00 PM PDT as General Manager at Pasadena",
                },
            ],
        },
        raw_payload={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    captured: dict[str, object] = {}

    async def fake_create_vacancy(_session, args):
        captured.update(args)
        return {
            "status": "vacancy_created",
            "shift_id": args["shift_id"],
            "coverage_case_id": str(uuid4()),
            "offers": [],
            "used_published_amendment": True,
            "reason_code": args["reason_code"],
        }

    monkeypatch.setattr(retell_workflow, "create_vacancy", fake_create_vacancy)

    result = await retell_workflow.process_inbound_conversation_completion(session, conversation)

    assert captured["shift_id"] == str(shift_tomorrow)
    assert captured["reason_code"] == "callout"
    assert result["callout"]["status"] == "vacancy_created"
    assert result["callout"]["intent"] == "callout"
    assert result["callout"]["confidence"] == "high"
    assert conversation.analysis["backfill_processing"]["intent"]["intent"] == "callout"


@pytest.mark.asyncio
async def test_process_inbound_conversation_completion_holds_medium_confidence_retell_callout_for_review():
    session = FakeSession()
    employee_id = uuid4()
    conversation = RetellConversation(
        id=uuid4(),
        external_id="call_retell_medium_confidence",
        conversation_type=RetellConversationType.call,
        event_type="call_analyzed",
        direction="inbound",
        status="ended",
        agent_id="agent_inbound_123",
        phone_from="+15555550100",
        phone_to="+18002225345",
        transcript_text="user: I can't make my shift tomorrow.",
        transcript_items=[
            {"role": "user", "content": "I can't make my shift tomorrow."},
        ],
        analysis={
            "custom_analysis_data": {
                "call_intent": "callout",
                "call_intent_confidence": "medium",
            }
        },
        metadata_json={
            "employee_id": str(employee_id),
            "caller_phone": "+15555550100",
            "assigned_shifts": [
                {
                    "id": str(uuid4()),
                    "role_name": "General Manager",
                    "location_name": "Pasadena",
                    "starts_at": "2026-04-17T21:00:00+00:00",
                    "timezone": "America/Los_Angeles",
                    "start_time_label": "2:00 PM",
                    "date_label": "Tomorrow (Friday, April 17)",
                    "relative_day_label": "Tomorrow",
                    "summary": "Tomorrow (Friday, April 17) from 2:00 PM to 6:00 PM PDT as General Manager at Pasadena",
                },
            ],
        },
        raw_payload={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    result = await retell_workflow.process_inbound_conversation_completion(session, conversation)

    assert result["callout"]["status"] == "retell_intent_requires_secondary_review"
    assert result["callout"]["intent"] == "callout"
    assert result["callout"]["confidence"] == "medium"
    assert conversation.analysis["backfill_processing"]["intent"]["confidence"] == "medium"


@pytest.mark.asyncio
async def test_process_inbound_conversation_completion_uses_openai_to_confirm_medium_confidence_retell_callout(monkeypatch):
    session = FakeSession()
    employee_id = uuid4()
    shift_tomorrow = uuid4()
    conversation = RetellConversation(
        id=uuid4(),
        external_id="call_retell_medium_confidence_openai_agrees",
        conversation_type=RetellConversationType.call,
        event_type="call_analyzed",
        direction="inbound",
        status="ended",
        agent_id="agent_inbound_123",
        phone_from="+15555550100",
        phone_to="+18002225345",
        conversation_summary="Caller confirmed they cannot work their only shift tomorrow.",
        transcript_text="user: I can't make my shift tomorrow.",
        transcript_items=[
            {"role": "user", "content": "I can't make my shift tomorrow."},
        ],
        analysis={
            "custom_analysis_data": {
                "call_intent": "callout",
                "call_intent_confidence": "medium",
            }
        },
        metadata_json={
            "employee_id": str(employee_id),
            "caller_phone": "+15555550100",
            "assigned_shift_schedule_summary": "1. Tomorrow (Friday, April 17) from 2:00 PM to 6:00 PM PDT as General Manager at Pasadena",
            "assigned_shifts": [
                {
                    "id": str(shift_tomorrow),
                    "role_name": "General Manager",
                    "location_name": "Pasadena",
                    "starts_at": "2026-04-17T21:00:00+00:00",
                    "timezone": "America/Los_Angeles",
                    "start_time_label": "2:00 PM",
                    "date_label": "Tomorrow (Friday, April 17)",
                    "relative_day_label": "Tomorrow",
                    "summary": "Tomorrow (Friday, April 17) from 2:00 PM to 6:00 PM PDT as General Manager at Pasadena",
                },
            ],
        },
        raw_payload={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        retell_workflow.llm_gateway,
        "provider_is_configured",
        lambda provider: provider == retell_workflow.llm_gateway.LlmProvider.OPENAI,
    )

    async def fake_generate(_session, *, request):
        assert request.model == "gpt-5-mini"
        return retell_workflow.llm_gateway.LlmGenerationResult(
            provider=retell_workflow.llm_gateway.LlmProvider.OPENAI,
            model="gpt-5-mini",
            tool_calls=[
                retell_workflow.llm_gateway.LlmToolCall(
                    tool_call_id="tool_1",
                    name="resolve_inbound_intent",
                    arguments={
                        "intent": "callout",
                        "confidence": "high",
                        "reasoning": "The worker clearly said they cannot make tomorrow's shift.",
                    },
                )
            ],
        )

    async def fake_create_vacancy(_session, args):
        captured.update(args)
        return {
            "status": "vacancy_created",
            "shift_id": args["shift_id"],
            "coverage_case_id": str(uuid4()),
            "offers": [],
            "used_published_amendment": True,
            "reason_code": args["reason_code"],
        }

    monkeypatch.setattr(retell_workflow.llm_gateway, "generate", fake_generate)
    monkeypatch.setattr(retell_workflow, "create_vacancy", fake_create_vacancy)

    result = await retell_workflow.process_inbound_conversation_completion(session, conversation)

    assert captured["shift_id"] == str(shift_tomorrow)
    assert result["callout"]["status"] == "vacancy_created"
    assert result["callout"]["intent"] == "callout"
    assert result["callout"]["confidence"] == "medium"
    assert result["callout"]["source"] == "retell_non_high_confidence_openai_confirmation"
    assert result["callout"]["secondary_intent"]["intent"] == "callout"


@pytest.mark.asyncio
async def test_process_inbound_conversation_completion_uses_openai_to_confirm_low_confidence_retell_callout(monkeypatch):
    session = FakeSession()
    employee_id = uuid4()
    shift_tomorrow = uuid4()
    conversation = RetellConversation(
        id=uuid4(),
        external_id="call_retell_low_confidence_openai_agrees",
        conversation_type=RetellConversationType.call,
        event_type="call_analyzed",
        direction="inbound",
        status="ended",
        agent_id="agent_inbound_123",
        phone_from="+15555550100",
        phone_to="+18002225345",
        conversation_summary="Caller said they cannot work their only shift tomorrow.",
        transcript_text="user: I can't make my shift tomorrow.",
        transcript_items=[
            {"role": "user", "content": "I can't make my shift tomorrow."},
        ],
        analysis={
            "custom_analysis_data": {
                "call_intent": "callout",
                "call_intent_confidence": "low",
            }
        },
        metadata_json={
            "employee_id": str(employee_id),
            "caller_phone": "+15555550100",
            "assigned_shift_schedule_summary": "1. Tomorrow (Friday, April 17) from 2:00 PM to 6:00 PM PDT as General Manager at Pasadena",
            "assigned_shifts": [
                {
                    "id": str(shift_tomorrow),
                    "role_name": "General Manager",
                    "location_name": "Pasadena",
                    "starts_at": "2026-04-17T21:00:00+00:00",
                    "timezone": "America/Los_Angeles",
                    "start_time_label": "2:00 PM",
                    "date_label": "Tomorrow (Friday, April 17)",
                    "relative_day_label": "Tomorrow",
                    "summary": "Tomorrow (Friday, April 17) from 2:00 PM to 6:00 PM PDT as General Manager at Pasadena",
                },
            ],
        },
        raw_payload={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        retell_workflow.llm_gateway,
        "provider_is_configured",
        lambda provider: provider == retell_workflow.llm_gateway.LlmProvider.OPENAI,
    )

    async def fake_generate(_session, *, request):
        assert request.provider == retell_workflow.llm_gateway.LlmProvider.OPENAI
        assert request.purpose == "intent_resolution"
        return retell_workflow.llm_gateway.LlmGenerationResult(
            provider=retell_workflow.llm_gateway.LlmProvider.OPENAI,
            model="gpt-test",
            tool_calls=[
                retell_workflow.llm_gateway.LlmToolCall(
                    tool_call_id="tool_1",
                    name="resolve_inbound_intent",
                    arguments={
                        "intent": "callout",
                        "confidence": "medium",
                        "reasoning": "The caller explicitly said they cannot make the shift tomorrow.",
                    },
                )
            ],
        )

    async def fake_create_vacancy(_session, args):
        captured.update(args)
        return {
            "status": "vacancy_created",
            "shift_id": args["shift_id"],
            "coverage_case_id": str(uuid4()),
            "offers": [],
            "used_published_amendment": True,
            "reason_code": args["reason_code"],
        }

    monkeypatch.setattr(retell_workflow.llm_gateway, "generate", fake_generate)
    monkeypatch.setattr(retell_workflow, "create_vacancy", fake_create_vacancy)

    result = await retell_workflow.process_inbound_conversation_completion(session, conversation)

    assert captured["shift_id"] == str(shift_tomorrow)
    assert captured["reason_code"] == "callout"
    assert result["callout"]["status"] == "vacancy_created"
    assert result["callout"]["intent"] == "callout"
    assert result["callout"]["confidence"] == "low"
    assert result["callout"]["source"] == "retell_non_high_confidence_openai_confirmation"
    assert result["callout"]["secondary_intent"]["intent"] == "callout"
    assert conversation.analysis["backfill_processing"]["secondary_intent"]["intent"] == "callout"


@pytest.mark.asyncio
async def test_process_inbound_conversation_completion_holds_when_low_confidence_retell_and_openai_disagree(monkeypatch):
    session = FakeSession()
    employee_id = uuid4()
    conversation = RetellConversation(
        id=uuid4(),
        external_id="call_retell_low_confidence_openai_disagrees",
        conversation_type=RetellConversationType.call,
        event_type="call_analyzed",
        direction="inbound",
        status="ended",
        agent_id="agent_inbound_123",
        phone_from="+15555550100",
        phone_to="+18002225345",
        transcript_text="user: What shifts do I have this week?",
        transcript_items=[
            {"role": "user", "content": "What shifts do I have this week?"},
        ],
        analysis={
            "custom_analysis_data": {
                "call_intent": "callout",
                "call_intent_confidence": "low",
            }
        },
        metadata_json={
            "employee_id": str(employee_id),
            "caller_phone": "+15555550100",
            "assigned_shifts": [],
        },
        raw_payload={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    monkeypatch.setattr(
        retell_workflow.llm_gateway,
        "provider_is_configured",
        lambda provider: provider == retell_workflow.llm_gateway.LlmProvider.OPENAI,
    )

    async def fake_generate(_session, *, request):
        return retell_workflow.llm_gateway.LlmGenerationResult(
            provider=retell_workflow.llm_gateway.LlmProvider.OPENAI,
            model="gpt-test",
            tool_calls=[
                retell_workflow.llm_gateway.LlmToolCall(
                    tool_call_id="tool_1",
                    name="resolve_inbound_intent",
                    arguments={
                        "intent": "schedule_question",
                        "confidence": "high",
                        "reasoning": "The caller asked about upcoming shifts.",
                    },
                )
            ],
        )

    monkeypatch.setattr(retell_workflow.llm_gateway, "generate", fake_generate)

    result = await retell_workflow.process_inbound_conversation_completion(session, conversation)

    assert result["callout"]["status"] == "retell_openai_intent_disagreement"
    assert result["callout"]["intent"] == "callout"
    assert result["callout"]["confidence"] == "low"
    assert result["callout"]["secondary_intent"]["intent"] == "schedule_question"
    assert conversation.analysis["backfill_processing"]["secondary_intent"]["intent"] == "schedule_question"


@pytest.mark.asyncio
async def test_process_inbound_conversation_completion_records_non_callout_retell_intent():
    session = FakeSession()
    employee_id = uuid4()
    conversation = RetellConversation(
        id=uuid4(),
        external_id="call_retell_schedule_question",
        conversation_type=RetellConversationType.call,
        event_type="call_analyzed",
        direction="inbound",
        status="ended",
        agent_id="agent_inbound_123",
        phone_from="+15555550100",
        phone_to="+18002225345",
        transcript_text="user: What shifts do I have this week?",
        transcript_items=[
            {"role": "user", "content": "What shifts do I have this week?"},
        ],
        analysis={
            "custom_analysis_data": {
                "call_intent": "schedule_question",
                "call_intent_confidence": "high",
            }
        },
        metadata_json={
            "employee_id": str(employee_id),
            "caller_phone": "+15555550100",
            "assigned_shifts": [],
        },
        raw_payload={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    result = await retell_workflow.process_inbound_conversation_completion(session, conversation)

    assert result["callout"]["status"] == "retell_intent_non_callout"
    assert result["callout"]["intent"] == "schedule_question"
    assert result["callout"]["confidence"] == "high"


@pytest.mark.asyncio
async def test_process_inbound_conversation_completion_records_sms_opt_out(monkeypatch):
    session = FakeSession()
    employee_id = uuid4()
    conversation = RetellConversation(
        id=uuid4(),
        external_id="call_456",
        conversation_type=RetellConversationType.call,
        event_type="call_ended",
        direction="inbound",
        status="ended",
        agent_id="agent_inbound_123",
        phone_from="+15555550100",
        phone_to="+18002225345",
        transcript_items=[
            {"role": "user", "content": "Please stop texting me about shifts."},
        ],
        analysis={},
        metadata_json={
            "employee_id": str(employee_id),
            "caller_phone": "+15555550100",
            "assigned_shifts": [],
        },
        raw_payload={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    async def fake_log_consent(_session, args):
        assert args["employee_id"] == str(employee_id)
        assert args["phone"] == "+15555550100"
        assert args["granted"] is False
        return {"status": "consent_revoked", "phone": args["phone"], "changed": True}

    monkeypatch.setattr(retell_workflow, "log_consent", fake_log_consent)

    result = await retell_workflow.process_inbound_conversation_completion(session, conversation)

    assert result["consent"]["status"] == "consent_revoked"
    assert result["callout"]["status"] == "no_callout_detected"


@pytest.mark.asyncio
async def test_process_outbound_conversation_completion_accepts_high_confidence_retell_intent(monkeypatch):
    session = FakeSession()
    employee_id = uuid4()
    offer_id = uuid4()
    shift_id = uuid4()
    captured: dict[str, object] = {}
    conversation = RetellConversation(
        id=uuid4(),
        external_id="call_outbound_accept_high",
        conversation_type=RetellConversationType.call,
        event_type="call_analyzed",
        direction="outbound",
        status="ended",
        agent_id="agent_outbound_123",
        phone_from="+18002225345",
        phone_to="+15555550199",
        conversation_summary="Worker confirmed they can take the offered shift.",
        transcript_text="user: Yes, I can take it.",
        transcript_items=[
            {"role": "user", "content": "Yes, I can take it."},
        ],
        analysis={
            "custom_analysis_data": {
                "outbound_intent": "accept_shift",
                "outbound_intent_confidence": "high",
            }
        },
        metadata_json={
            "employee_id": str(employee_id),
            "offer_id": str(offer_id),
            "shift_id": str(shift_id),
            "location_name": "Pasadena",
            "role_name": "General Manager",
            "shift_starts_at": "2026-04-17T21:00:00+00:00",
            "shift_ends_at": "2026-04-18T01:00:00+00:00",
        },
        raw_payload={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    async def fake_respond_to_offer(_session, *, args, accepted):
        captured.update(args)
        captured["accepted"] = accepted
        return {
            "status": "accepted",
            "offer_id": args["offer_id"],
            "shift_id": args["shift_id"],
            "assignment_id": str(uuid4()),
        }

    monkeypatch.setattr(retell_workflow, "_respond_to_offer", fake_respond_to_offer)

    result = await retell_workflow.process_outbound_conversation_completion(session, conversation)

    assert captured["accepted"] is True
    assert captured["offer_id"] == str(offer_id)
    assert captured["employee_id"] == str(employee_id)
    assert result["consent"]["status"] == "no_consent_change"
    assert result["offer_response"]["status"] == "accepted"
    assert result["offer_response"]["intent"] == "accept_shift"
    assert result["offer_response"]["confidence"] == "high"
    assert conversation.analysis["backfill_processing"]["intent"]["intent"] == "accept_shift"


@pytest.mark.asyncio
async def test_process_outbound_conversation_completion_uses_openai_to_confirm_medium_confidence_accept(monkeypatch):
    session = FakeSession()
    employee_id = uuid4()
    offer_id = uuid4()
    shift_id = uuid4()
    captured: dict[str, object] = {}
    conversation = RetellConversation(
        id=uuid4(),
        external_id="call_outbound_accept_medium",
        conversation_type=RetellConversationType.call,
        event_type="call_analyzed",
        direction="outbound",
        status="ended",
        agent_id="agent_outbound_123",
        phone_from="+18002225345",
        phone_to="+15555550199",
        conversation_summary="Worker sounded willing to take the offered shift.",
        transcript_text="user: Yes, that works for me.",
        transcript_items=[
            {"role": "user", "content": "Yes, that works for me."},
        ],
        analysis={
            "custom_analysis_data": {
                "outbound_intent": "accept_shift",
                "outbound_intent_confidence": "medium",
            }
        },
        metadata_json={
            "employee_id": str(employee_id),
            "offer_id": str(offer_id),
            "shift_id": str(shift_id),
            "location_name": "Pasadena",
            "role_name": "General Manager",
            "shift_starts_at": "2026-04-17T21:00:00+00:00",
            "shift_ends_at": "2026-04-18T01:00:00+00:00",
        },
        raw_payload={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    monkeypatch.setattr(
        retell_workflow.llm_gateway,
        "provider_is_configured",
        lambda provider: provider == retell_workflow.llm_gateway.LlmProvider.OPENAI,
    )

    async def fake_generate(_session, *, request):
        assert request.model == "gpt-5-mini"
        return retell_workflow.llm_gateway.LlmGenerationResult(
            provider=retell_workflow.llm_gateway.LlmProvider.OPENAI,
            model="gpt-5-mini",
            tool_calls=[
                retell_workflow.llm_gateway.LlmToolCall(
                    tool_call_id="tool_1",
                    name="resolve_outbound_intent",
                    arguments={
                        "intent": "accept_shift",
                        "confidence": "high",
                        "reasoning": "The worker clearly agreed to take the shift.",
                    },
                )
            ],
        )

    async def fake_respond_to_offer(_session, *, args, accepted):
        captured.update(args)
        captured["accepted"] = accepted
        return {
            "status": "accepted",
            "offer_id": args["offer_id"],
            "shift_id": args["shift_id"],
            "assignment_id": str(uuid4()),
        }

    monkeypatch.setattr(retell_workflow.llm_gateway, "generate", fake_generate)
    monkeypatch.setattr(retell_workflow, "_respond_to_offer", fake_respond_to_offer)

    result = await retell_workflow.process_outbound_conversation_completion(session, conversation)

    assert captured["accepted"] is True
    assert captured["offer_id"] == str(offer_id)
    assert result["offer_response"]["status"] == "accepted"
    assert result["offer_response"]["intent"] == "accept_shift"
    assert result["offer_response"]["confidence"] == "medium"
    assert result["offer_response"]["source"] == "retell_non_high_confidence_openai_confirmation"
    assert result["offer_response"]["secondary_intent"]["intent"] == "accept_shift"


@pytest.mark.asyncio
async def test_process_outbound_conversation_completion_holds_when_retell_and_openai_disagree(monkeypatch):
    session = FakeSession()
    employee_id = uuid4()
    conversation = RetellConversation(
        id=uuid4(),
        external_id="call_outbound_disagreement",
        conversation_type=RetellConversationType.call,
        event_type="call_analyzed",
        direction="outbound",
        status="ended",
        agent_id="agent_outbound_123",
        phone_from="+18002225345",
        phone_to="+15555550199",
        transcript_text="user: I don't think I can do that one.",
        transcript_items=[
            {"role": "user", "content": "I don't think I can do that one."},
        ],
        analysis={
            "custom_analysis_data": {
                "outbound_intent": "accept_shift",
                "outbound_intent_confidence": "low",
            }
        },
        metadata_json={
            "employee_id": str(employee_id),
            "offer_id": str(uuid4()),
            "shift_id": str(uuid4()),
        },
        raw_payload={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    monkeypatch.setattr(
        retell_workflow.llm_gateway,
        "provider_is_configured",
        lambda provider: provider == retell_workflow.llm_gateway.LlmProvider.OPENAI,
    )

    async def fake_generate(_session, *, request):
        return retell_workflow.llm_gateway.LlmGenerationResult(
            provider=retell_workflow.llm_gateway.LlmProvider.OPENAI,
            model="gpt-5-mini",
            tool_calls=[
                retell_workflow.llm_gateway.LlmToolCall(
                    tool_call_id="tool_1",
                    name="resolve_outbound_intent",
                    arguments={
                        "intent": "decline_shift",
                        "confidence": "high",
                        "reasoning": "The worker declined the offered shift.",
                    },
                )
            ],
        )

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("_respond_to_offer should not be called on disagreement")

    monkeypatch.setattr(retell_workflow.llm_gateway, "generate", fake_generate)
    monkeypatch.setattr(retell_workflow, "_respond_to_offer", fail_if_called)

    result = await retell_workflow.process_outbound_conversation_completion(session, conversation)

    assert result["offer_response"]["status"] == "retell_openai_intent_disagreement"
    assert result["offer_response"]["intent"] == "accept_shift"
    assert result["offer_response"]["confidence"] == "low"
    assert result["offer_response"]["secondary_intent"]["intent"] == "decline_shift"


@pytest.mark.asyncio
async def test_process_outbound_conversation_completion_records_opt_out_and_declines_offer(monkeypatch):
    session = FakeSession()
    employee_id = uuid4()
    offer_id = uuid4()
    shift_id = uuid4()
    consent_calls: list[dict[str, object]] = []
    response_calls: list[dict[str, object]] = []
    conversation = RetellConversation(
        id=uuid4(),
        external_id="call_outbound_opt_out",
        conversation_type=RetellConversationType.call,
        event_type="call_analyzed",
        direction="outbound",
        status="ended",
        agent_id="agent_outbound_123",
        phone_from="+18002225345",
        phone_to="+15555550199",
        transcript_text="user: Please stop calling me about these shifts.",
        transcript_items=[
            {"role": "user", "content": "Please stop calling me about these shifts."},
        ],
        analysis={
            "custom_analysis_data": {
                "outbound_intent": "opt_out",
                "outbound_intent_confidence": "high",
            }
        },
        metadata_json={
            "employee_id": str(employee_id),
            "offer_id": str(offer_id),
            "shift_id": str(shift_id),
        },
        raw_payload={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    async def fake_log_consent(_session, args):
        consent_calls.append(dict(args))
        return {"status": "consent_revoked", "phone": args["phone"], "changed": True}

    async def fake_respond_to_offer(_session, *, args, accepted):
        response_calls.append({**args, "accepted": accepted})
        return {
            "status": "declined",
            "offer_id": args["offer_id"],
            "shift_id": args["shift_id"],
            "assignment_id": None,
        }

    monkeypatch.setattr(retell_workflow, "log_consent", fake_log_consent)
    monkeypatch.setattr(retell_workflow, "_respond_to_offer", fake_respond_to_offer)

    result = await retell_workflow.process_outbound_conversation_completion(session, conversation)

    assert consent_calls[0]["employee_id"] == str(employee_id)
    assert consent_calls[0]["phone"] == "+15555550199"
    assert consent_calls[0]["granted"] is False
    assert consent_calls[0]["channel"] == "outbound_call"
    assert response_calls[0]["accepted"] is False
    assert response_calls[0]["offer_id"] == str(offer_id)
    assert result["consent"]["status"] == "consent_revoked"
    assert result["offer_response"]["status"] == "declined"
    assert result["offer_response"]["intent"] == "opt_out"
    assert result["offer_response"]["opt_out_applied"] is True
