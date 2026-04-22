from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.common import AssignmentStatus, CoverageCaseStatus, ShiftLifecycleStatus, ShiftStaffingStatus
from app.models.coverage import CoverageCase
from app.models.demand_features import AttendanceHistoryFact, CalloutHistoryFact
from app.models.scheduling import Shift, ShiftAssignment
from app.services import forecast_history


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalarResult(self._rows)


class _FakeSession:
    def __init__(self):
        self.added: list[object] = []
        self.flush_count = 0
        self.execute_rows: list[object] = []
        self.execute_responses: list[list[object]] = []
        self.execute_count = 0

    def add(self, instance):
        now = datetime.now(timezone.utc)
        if getattr(instance, "id", None) is None:
            instance.id = uuid4()
        if hasattr(instance, "created_at") and getattr(instance, "created_at", None) is None:
            instance.created_at = now
        if hasattr(instance, "updated_at") and getattr(instance, "updated_at", None) is None:
            instance.updated_at = now
        self.added.append(instance)

    async def flush(self):
        self.flush_count += 1

    async def execute(self, _stmt):
        self.execute_count += 1
        if self.execute_responses:
            return _FakeExecuteResult(self.execute_responses.pop(0))
        return _FakeExecuteResult(self.execute_rows)


def _shift(*, starts_at=None, ends_at=None) -> Shift:
    return Shift(
        id=uuid4(),
        business_id=uuid4(),
        location_id=uuid4(),
        role_id=uuid4(),
        timezone="America/Los_Angeles",
        starts_at=starts_at or datetime(2026, 4, 14, 16, 0, tzinfo=timezone.utc),
        ends_at=ends_at or datetime(2026, 4, 14, 20, 0, tzinfo=timezone.utc),
        lifecycle_status=ShiftLifecycleStatus.completed,
        staffing_status=ShiftStaffingStatus.covered,
        seats_requested=1,
        seats_filled=1,
        shift_metadata={},
    )


def _assignment(*, employee_id=None, status=AssignmentStatus.completed) -> ShiftAssignment:
    return ShiftAssignment(
        id=uuid4(),
        shift_id=uuid4(),
        employee_id=employee_id or uuid4(),
        assigned_via="manual",
        status=status,
        sequence_no=1,
        accepted_at=datetime(2026, 4, 14, 15, 0, tzinfo=timezone.utc),
        checked_in_at=datetime(2026, 4, 14, 16, 5, tzinfo=timezone.utc),
        checked_out_at=datetime(2026, 4, 14, 20, 0, tzinfo=timezone.utc),
        assignment_metadata={"late_minutes": 5, "left_early_minutes": 0},
    )


def _coverage_case(*, shift: Shift, status=CoverageCaseStatus.filled) -> CoverageCase:
    return CoverageCase(
        id=uuid4(),
        shift_id=shift.id,
        location_id=shift.location_id,
        role_id=shift.role_id,
        status=status,
        phase_target="phase_1",
        reason_code="callout",
        priority=100,
        requires_manager_approval=False,
        triggered_by="manager",
        opened_at=datetime(2026, 4, 14, 14, 30, tzinfo=timezone.utc),
        closed_at=datetime(2026, 4, 14, 15, 0, tzinfo=timezone.utc),
        case_metadata={},
    )


def test_build_attendance_history_fact_dedupe_key_is_stable():
    shift = _shift()
    assignment = _assignment()
    payload_one = forecast_history.build_attendance_history_fact_payload_from_assignment(
        shift=shift,
        assignment=assignment,
        source_payload={"source_record_id": "assign-123", "nested": {"a": 1, "b": 2}},
    )
    payload_two = forecast_history.build_attendance_history_fact_payload_from_assignment(
        shift=shift,
        assignment=assignment,
        source_payload={"nested": {"b": 2, "a": 1}, "source_record_id": "assign-123"},
    )

    key_one = forecast_history.build_attendance_history_fact_dedupe_key(payload_one)
    key_two = forecast_history.build_attendance_history_fact_dedupe_key(payload_two)

    assert key_one.startswith("sha256:")
    assert key_one == key_two


def test_build_attendance_history_fact_payload_from_assignment():
    shift = _shift()
    assignment = _assignment()

    payload = forecast_history.build_attendance_history_fact_payload_from_assignment(
        shift=shift,
        assignment=assignment,
    )

    assert payload.business_id == shift.business_id
    assert payload.location_id == shift.location_id
    assert payload.role_id == shift.role_id
    assert payload.shift_id == shift.id
    assert payload.employee_id == assignment.employee_id
    assert payload.attendance_status == "completed"
    assert payload.late_minutes == 5
    assert payload.left_early_minutes == 0
    assert payload.scheduled_hours == Decimal("4.0000")
    assert payload.worked_hours == Decimal("3.9167")


@pytest.mark.asyncio
async def test_upsert_attendance_history_fact_persists_new_row():
    session = _FakeSession()
    shift = _shift()
    assignment = _assignment()
    payload = forecast_history.build_attendance_history_fact_payload_from_assignment(shift=shift, assignment=assignment)

    row = await forecast_history.upsert_attendance_history_fact(session, payload)

    assert row.business_id == shift.business_id
    assert row.location_id == shift.location_id
    assert row.role_id == shift.role_id
    assert row.shift_id == shift.id
    assert row.employee_id == assignment.employee_id
    assert row.attendance_status == "completed"
    assert row.dedupe_key.startswith("sha256:")
    assert session.added[-1] is row
    assert session.flush_count == 1
    assert session.execute_count == 1


@pytest.mark.asyncio
async def test_upsert_attendance_history_fact_updates_existing_row():
    session = _FakeSession()
    existing = AttendanceHistoryFact(
        id=uuid4(),
        business_id=uuid4(),
        location_id=uuid4(),
        role_id=uuid4(),
        shift_id=uuid4(),
        employee_id=uuid4(),
        source_system="backfill_native",
        source_assignment_id="assignment-old",
        starts_at=datetime(2026, 4, 14, 16, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 14, 20, 0, tzinfo=timezone.utc),
        scheduled_hours=Decimal("4.0000"),
        worked_hours=Decimal("0.0000"),
        attendance_status="no_show",
        late_minutes=None,
        left_early_minutes=None,
        source_payload={},
        ingested_at=datetime(2026, 4, 14, 21, 0, tzinfo=timezone.utc),
        dedupe_key="sha256:existing",
    )
    session.execute_rows = [existing]
    shift = _shift(starts_at=existing.starts_at, ends_at=existing.ends_at)
    shift.business_id = existing.business_id
    shift.location_id = existing.location_id
    shift.role_id = existing.role_id
    shift.id = existing.shift_id
    assignment = _assignment(employee_id=existing.employee_id)
    assignment.id = uuid4()
    payload = forecast_history.build_attendance_history_fact_payload_from_assignment(
        shift=shift,
        assignment=assignment,
        source_payload={"source_record_id": "same-assignment"},
    )
    payload = payload.model_copy(update={"source_system": existing.source_system, "dedupe_key": existing.dedupe_key})

    row = await forecast_history.upsert_attendance_history_fact(session, payload)

    assert row is existing
    assert row.attendance_status == "completed"
    assert row.worked_hours == Decimal("3.9167")
    assert row.late_minutes == 5
    assert session.added == []
    assert session.flush_count == 1


def test_summarize_attendance_by_local_bucket_builds_role_scoped_means():
    location_id = uuid4()
    role_id = uuid4()
    rows = [
        AttendanceHistoryFact(
            id=uuid4(),
            business_id=uuid4(),
            location_id=location_id,
            role_id=role_id,
            shift_id=uuid4(),
            employee_id=uuid4(),
            source_system="backfill_native",
            source_assignment_id="a1",
            starts_at=datetime(2026, 4, 14, 16, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 14, 18, 0, tzinfo=timezone.utc),
            scheduled_hours=Decimal("2.0000"),
            worked_hours=Decimal("2.0000"),
            attendance_status="completed",
            late_minutes=0,
            left_early_minutes=0,
            source_payload={},
            ingested_at=datetime(2026, 4, 14, 21, 0, tzinfo=timezone.utc),
            dedupe_key="sha256:a1",
        ),
        AttendanceHistoryFact(
            id=uuid4(),
            business_id=uuid4(),
            location_id=location_id,
            role_id=role_id,
            shift_id=uuid4(),
            employee_id=uuid4(),
            source_system="backfill_native",
            source_assignment_id="a2",
            starts_at=datetime(2026, 4, 7, 16, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 7, 18, 0, tzinfo=timezone.utc),
            scheduled_hours=Decimal("2.0000"),
            worked_hours=Decimal("0.0000"),
            attendance_status="no_show",
            late_minutes=None,
            left_early_minutes=None,
            source_payload={},
            ingested_at=datetime(2026, 4, 7, 21, 0, tzinfo=timezone.utc),
            dedupe_key="sha256:a2",
        ),
    ]

    summaries = forecast_history.summarize_attendance_by_local_bucket(
        rows,
        timezone_name="America/Los_Angeles",
        bucket_minutes=60,
        lookback_days=56,
    )

    summary = summaries[(str(location_id), str(role_id), 1, 9, 60)]
    assert summary["attendance_sample_count_56d"] == 2
    assert summary["attendance_completed_rate_56d"] == 0.5
    assert summary["attendance_no_show_rate_56d"] == 0.5
    assert summary["attendance_late_minutes_mean_56d"] == 0.0
    assert summary["attendance_worked_hours_ratio_mean_56d"] == 0.5


def test_build_callout_history_fact_payload_from_case():
    shift = _shift()
    coverage_case = _coverage_case(shift=shift)

    payload = forecast_history.build_callout_history_fact_payload_from_case(
        coverage_case=coverage_case,
        shift=shift,
    )

    assert payload.business_id == shift.business_id
    assert payload.location_id == shift.location_id
    assert payload.role_id == shift.role_id
    assert payload.shift_id == shift.id
    assert payload.reason_code == "callout"
    assert payload.filled is True
    assert payload.notice_minutes == 90
    assert payload.fill_latency_minutes == 30


@pytest.mark.asyncio
async def test_upsert_callout_history_fact_persists_new_row():
    session = _FakeSession()
    shift = _shift()
    coverage_case = _coverage_case(shift=shift)
    payload = forecast_history.build_callout_history_fact_payload_from_case(coverage_case=coverage_case, shift=shift)

    row = await forecast_history.upsert_callout_history_fact(session, payload)

    assert row.business_id == shift.business_id
    assert row.location_id == shift.location_id
    assert row.role_id == shift.role_id
    assert row.shift_id == shift.id
    assert row.filled is True
    assert row.dedupe_key.startswith("sha256:")
    assert session.added[-1] is row
    assert session.flush_count == 1
    assert session.execute_count == 1


def test_summarize_callout_history_by_local_bucket_builds_role_scoped_means():
    location_id = uuid4()
    role_id = uuid4()
    rows = [
        CalloutHistoryFact(
            id=uuid4(),
            business_id=uuid4(),
            location_id=location_id,
            role_id=role_id,
            shift_id=uuid4(),
            source_system="backfill_native",
            source_case_id="case-1",
            occurred_at=datetime(2026, 4, 14, 14, 30, tzinfo=timezone.utc),
            shift_starts_at=datetime(2026, 4, 14, 16, 0, tzinfo=timezone.utc),
            shift_ends_at=datetime(2026, 4, 14, 18, 0, tzinfo=timezone.utc),
            notice_minutes=90,
            reason_code="callout",
            filled=True,
            fill_latency_minutes=30,
            source_payload={},
            ingested_at=datetime(2026, 4, 14, 15, 0, tzinfo=timezone.utc),
            dedupe_key="sha256:c1",
        ),
        CalloutHistoryFact(
            id=uuid4(),
            business_id=uuid4(),
            location_id=location_id,
            role_id=role_id,
            shift_id=uuid4(),
            source_system="backfill_native",
            source_case_id="case-2",
            occurred_at=datetime(2026, 4, 7, 15, 0, tzinfo=timezone.utc),
            shift_starts_at=datetime(2026, 4, 7, 16, 0, tzinfo=timezone.utc),
            shift_ends_at=datetime(2026, 4, 7, 18, 0, tzinfo=timezone.utc),
            notice_minutes=60,
            reason_code="callout",
            filled=False,
            fill_latency_minutes=None,
            source_payload={},
            ingested_at=datetime(2026, 4, 7, 15, 5, tzinfo=timezone.utc),
            dedupe_key="sha256:c2",
        ),
    ]

    summaries = forecast_history.summarize_callout_history_by_local_bucket(
        rows,
        timezone_name="America/Los_Angeles",
        bucket_minutes=60,
        lookback_days=56,
    )

    summary = summaries[(str(location_id), str(role_id), 1, 9, 60)]
    assert summary["callout_sample_count_56d"] == 2
    assert summary["callout_filled_rate_56d"] == 0.5
    assert summary["callout_notice_minutes_mean_56d"] == 75.0
    assert summary["callout_fill_latency_minutes_mean_56d"] == 30.0
