from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from uuid import UUID as UUIDType

import pytest

from app.models.auto_scheduler import ScheduleRunAssignment
from app.models.business import Business, Location, Role
from app.models.common import (
    AssignmentStatus,
    ComplianceOverrideArtifactStatus,
    ComplianceOverrideArtifactType,
    EmployeeStatus,
    ScheduleApplyStatus,
    ScheduleRunStatus,
    ShiftBreakType,
    ShiftLifecycleStatus,
    ShiftSegmentType,
    ShiftStaffingStatus,
)
from app.models.compliance import ComplianceOverrideArtifact
from app.models.scheduling import Shift, ShiftAssignment, ShiftBreak, ShiftSegment
from app.models.workforce import Employee, EmployeeLocation, EmployeeRole
from app.models.workforce import EmployeeAvailabilityException, EmployeeAvailabilityRule
from app.schemas.auto_scheduler import (
    GeneratedDemandPayload,
    ProposedShiftPayload,
    ReliabilityComponentPayload,
    ReliabilityEmployeeSnapshotPayload,
    ReliabilitySnapshotPayload,
    SchedulePolicyPayload,
    ScheduleRunInputContract,
)
from app.services import auto_scheduler, labor_rules


class FakeAutoSchedulerSession:
    def __init__(self):
        self.added: list[object] = []
        self.get_map: dict[tuple[type, object], object] = {}

    def add(self, obj):
        now = datetime.now(timezone.utc)
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = now
        if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
            obj.updated_at = now
        if isinstance(obj, Shift):
            for segment in obj.segments or []:
                if getattr(segment, "id", None) is None:
                    segment.id = uuid4()
                if getattr(segment, "created_at", None) is None:
                    segment.created_at = now
                if getattr(segment, "updated_at", None) is None:
                    segment.updated_at = now
                for shift_break in segment.breaks or []:
                    if getattr(shift_break, "id", None) is None:
                        shift_break.id = uuid4()
                    if getattr(shift_break, "created_at", None) is None:
                        shift_break.created_at = now
                    if getattr(shift_break, "updated_at", None) is None:
                        shift_break.updated_at = now
        self.added.append(obj)
        self.get_map[(type(obj), obj.id)] = obj

    async def get(self, model, object_id, **_kwargs):
        return self.get_map.get((model, object_id))

    async def flush(self):
        return None


def _reliability_component(score: float) -> ReliabilityComponentPayload:
    return ReliabilityComponentPayload(
        score=score,
        confidence=0.8,
        sample_size=12,
        metrics={},
    )


def _run_inputs() -> ScheduleRunInputContract:
    employee_id = uuid4()
    return ScheduleRunInputContract(
        shift_payload={"shift_ids": [str(uuid4())]},
        fixed_shift_payload={"shift_ids": []},
        employee_payload={"employee_ids": [str(employee_id)]},
        availability_payload={"employee_ids": [str(employee_id)]},
        policy_payload=SchedulePolicyPayload(),
        labor_payload={"profiles": []},
        reliability_payload=ReliabilitySnapshotPayload(
            generated_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
            snapshot_hash="sha256:reliability",
            snapshot_version="v1",
            employees=[
                ReliabilityEmployeeSnapshotPayload(
                    employee_id=employee_id,
                    overall_score=0.81,
                    confidence=0.8,
                    sample_size=12,
                    attendance=_reliability_component(0.9),
                    punctuality=_reliability_component(0.8),
                    commitment=_reliability_component(0.85),
                    response_behavior=_reliability_component(0.75),
                    coverage_reliability=_reliability_component(0.78),
                    metadata={},
                )
            ],
            metadata={},
        ),
        reliability_snapshot_generated_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
        reliability_snapshot_hash="sha256:reliability",
        reliability_snapshot_version="v1",
        source_metadata={"authoring_snapshot_hash": "sha256:authoring"},
    )


def _generated_demand_payload(*, location_id, role_id, source_run_id=None, source_point_id=None) -> GeneratedDemandPayload:
    return GeneratedDemandPayload(
        proposed_shifts=[
            ProposedShiftPayload(
                demand_key=f"{location_id}:{role_id}:2026-04-22T16:00:00+00:00",
                source_type="historical_pattern",
                generation_version="v1",
                source_run_id=source_run_id,
                source_point_id=source_point_id,
                location_id=location_id,
                role_id=role_id,
                timezone="America/Los_Angeles",
                starts_at=datetime(2026, 4, 22, 16, 0, tzinfo=timezone.utc),
                ends_at=datetime(2026, 4, 22, 22, 0, tzinfo=timezone.utc),
                headcount=1,
                premium_cents=0,
                requires_manager_approval=False,
                generation_payload={"source_week_count": 2},
            )
        ],
        metadata={"source": "historical_pattern_v1"},
    )


def _california_break_profile() -> labor_rules.LaborRuleProfileSnapshot:
    return labor_rules.LaborRuleProfileSnapshot(
        profile_id=uuid4(),
        code="ca_restaurant_core",
        jurisdiction_code="US-CA",
        display_name="California Restaurant Core",
        overtime_mode="daily_8_plus_weekly_plus_7th_day",
        daily_ot_threshold_hours=8.0,
        weekly_ot_threshold_hours=40.0,
        double_time_threshold_hours=12.0,
        consecutive_hours_threshold_hours=None,
        industry_profile_code=None,
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "meal_break_ruleset": "ca_v1",
            "rest_break_ruleset": "ca_v1",
        },
        effective_start_date=None,
        effective_end_date=None,
        source_urls=(),
        source_version="seed",
        source_hash="seed",
        version_id=uuid4(),
        version_no=1,
        payload_hash="sha256:ca_break_rules",
        payload_json={},
    )


def _new_york_hospitality_profile() -> labor_rules.LaborRuleProfileSnapshot:
    return labor_rules.LaborRuleProfileSnapshot(
        profile_id=uuid4(),
        code="us_ny_hospitality_nonexempt",
        jurisdiction_code="US-NY",
        display_name="New York Hospitality Nonexempt",
        overtime_mode="weekly_only",
        daily_ot_threshold_hours=None,
        weekly_ot_threshold_hours=40.0,
        double_time_threshold_hours=None,
        consecutive_hours_threshold_hours=None,
        industry_profile_code="hospitality",
        rules_json={
            "workweek_start_day_local": "sunday",
            "workweek_start_time_local": "00:00",
            "meal_break_ruleset": "ny_non_factory_v1",
            "spread_of_hours_ruleset": "ny_v1",
            "day_of_rest_workweek_required": True,
        },
        effective_start_date=None,
        effective_end_date=None,
        source_urls=(),
        source_version="seed",
        source_hash="seed",
        version_id=uuid4(),
        version_no=1,
        payload_hash="sha256:ny_hospitality_break_rules",
        payload_json={},
    )


def _reliability_payload_for(employee_id) -> ReliabilitySnapshotPayload:
    return ReliabilitySnapshotPayload(
        generated_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
        snapshot_hash="sha256:reliability",
        snapshot_version="v1",
        employees=[
            ReliabilityEmployeeSnapshotPayload(
                employee_id=employee_id,
                overall_score=0.81,
                confidence=0.8,
                sample_size=12,
                attendance=_reliability_component(0.9),
                punctuality=_reliability_component(0.8),
                commitment=_reliability_component(0.85),
                response_behavior=_reliability_component(0.75),
                coverage_reliability=_reliability_component(0.78),
                metadata={},
            )
        ],
        metadata={},
    )


def test_demand_feature_snapshot_points_for_inputs_enrich_weather_sales_and_history():
    location_id = uuid4()
    role_id = uuid4()
    inputs = _run_inputs().model_copy(
        update={
            "generated_demand_payload": _generated_demand_payload(location_id=location_id, role_id=role_id),
            "fixed_shift_payload": {"shifts": []},
        }
    )

    points = auto_scheduler._demand_feature_snapshot_points_for_inputs(
        inputs,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        default_timezone="America/Los_Angeles",
        bucket_minutes=60,
        weather_bucket_features={
            (
                str(location_id),
                datetime(2026, 4, 22, 16, 0, tzinfo=timezone.utc),
                datetime(2026, 4, 22, 17, 0, tzinfo=timezone.utc),
            ): {
                "weather_severity_flag": "monitor",
                "weather_precipitation_probability": 65,
            }
        },
        sales_bucket_features={
            (str(location_id), 2, 9, 60): {
                "pos_sales_sample_count_28d": 4,
                "pos_gross_sales_cents_mean_28d": 42000,
                "pos_order_count_mean_28d": 18.5,
            }
        },
        attendance_bucket_features={
            (str(location_id), str(role_id), 2, 9, 60): {
                "attendance_sample_count_56d": 6,
                "attendance_completed_rate_56d": 0.8333,
                "attendance_no_show_rate_56d": 0.1667,
            }
        },
        callout_bucket_features={
            (str(location_id), str(role_id), 2, 9, 60): {
                "callout_sample_count_56d": 3,
                "callout_filled_rate_56d": 0.6667,
            }
        },
    )

    first_payload = points[0]["feature_payload"]
    assert first_payload["weather_severity_flag"] == "monitor"
    assert first_payload["weather_precipitation_probability"] == 65
    assert first_payload["pos_sales_sample_count_28d"] == 4
    assert first_payload["pos_gross_sales_cents_mean_28d"] == 42000
    assert first_payload["pos_order_count_mean_28d"] == 18.5
    assert first_payload["attendance_sample_count_56d"] == 6
    assert first_payload["attendance_completed_rate_56d"] == 0.8333
    assert first_payload["attendance_no_show_rate_56d"] == 0.1667
    assert first_payload["callout_sample_count_56d"] == 3
    assert first_payload["callout_filled_rate_56d"] == 0.6667


def test_demand_feature_snapshot_points_for_inputs_seeds_historical_signature_buckets():
    location_id = uuid4()
    role_id = uuid4()
    inputs = _run_inputs().model_copy(
        update={
            "generated_demand_payload": GeneratedDemandPayload(),
            "fixed_shift_payload": {"shifts": []},
        }
    )

    points = auto_scheduler._demand_feature_snapshot_points_for_inputs(
        inputs,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        default_timezone="America/Los_Angeles",
        bucket_minutes=60,
        attendance_bucket_features={
            (str(location_id), str(role_id), 2, 9, 60): {
                "attendance_sample_count_56d": 8,
                "attendance_completed_rate_56d": 1.0,
            }
        },
    )

    assert len(points) == 1
    assert points[0]["location_id"] == location_id
    assert points[0]["role_id"] == role_id
    assert points[0]["bucket_start"] == datetime(2026, 4, 22, 16, 0, tzinfo=timezone.utc)
    assert points[0]["feature_payload"]["attendance_sample_count_56d"] == 8
    assert points[0]["feature_payload"]["total_headcount"] == 0


def _make_business() -> Business:
    now = datetime.now(timezone.utc)
    return Business(
        id=uuid4(),
        name="Backfill Cafe",
        display_name="Backfill Cafe",
        slug="backfill-cafe",
        timezone="America/Los_Angeles",
        settings={},
        place_metadata={},
        created_at=now,
        updated_at=now,
    )


def _make_shift(*, business_id, location_id, role_id) -> Shift:
    now = datetime.now(timezone.utc)
    return Shift(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        timezone="America/Los_Angeles",
        starts_at=datetime(2026, 4, 21, 16, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 21, 22, 0, tzinfo=timezone.utc),
        lifecycle_status=ShiftLifecycleStatus.draft,
        staffing_status=ShiftStaffingStatus.open,
        seats_requested=1,
        seats_filled=0,
        shift_metadata={},
        created_at=now,
        updated_at=now,
    )


def _make_location(*, business_id) -> Location:
    now = datetime.now(timezone.utc)
    return Location(
        id=uuid4(),
        business_id=business_id,
        name="Pasadena",
        display_name="Pasadena",
        slug="pasadena",
        locality="Pasadena",
        region="CA",
        country_code="US",
        timezone="America/Los_Angeles",
        google_place_metadata={},
        settings={},
        created_at=now,
        updated_at=now,
    )


def _make_role(*, business_id) -> Role:
    now = datetime.now(timezone.utc)
    return Role(
        id=uuid4(),
        business_id=business_id,
        code="server",
        name="Server",
        coverage_priority=100,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )


def _make_employee(*, business_id, role: Role, location: Location) -> Employee:
    now = datetime.now(timezone.utc)
    employee = Employee(
        id=uuid4(),
        business_id=business_id,
        full_name="Taylor Rivera",
        reliability_score=Decimal("0.810"),
        status=EmployeeStatus.active,
        response_profile={},
        employee_metadata={},
        created_at=now,
        updated_at=now,
    )
    employee_role = EmployeeRole(
        id=uuid4(),
        employee_id=employee.id,
        role_id=role.id,
        role_metadata={},
        created_at=now,
        updated_at=now,
    )
    employee_role.role = role
    employee_location = EmployeeLocation(
        id=uuid4(),
        employee_id=employee.id,
        location_id=location.id,
        access_level="approved",
        location_metadata={},
        created_at=now,
        updated_at=now,
    )
    employee_location.location = location
    employee.employee_roles = [employee_role]
    employee.employee_locations = [employee_location]
    return employee


def test_build_authoring_snapshot_hash_is_stable_across_input_order():
    shift_a = {
        "shift_id": uuid4(),
        "location_id": uuid4(),
        "role_id": uuid4(),
        "starts_at": "2026-04-20T16:00:00+00:00",
        "ends_at": "2026-04-20T22:00:00+00:00",
    }
    shift_b = {
        "shift_id": uuid4(),
        "location_id": uuid4(),
        "role_id": uuid4(),
        "starts_at": "2026-04-21T16:00:00+00:00",
        "ends_at": "2026-04-21T22:00:00+00:00",
    }
    assignment_a = {
        "assignment_id": uuid4(),
        "shift_id": shift_a["shift_id"],
        "employee_id": uuid4(),
        "assigned_via": "manual",
        "status": "proposed",
    }
    assignment_b = {
        "assignment_id": uuid4(),
        "shift_id": shift_b["shift_id"],
        "employee_id": uuid4(),
        "assigned_via": "auto_scheduler",
        "status": "proposed",
    }
    role_eligibility = [
        {"employee_id": assignment_a["employee_id"], "role_id": shift_a["role_id"]},
        {"employee_id": assignment_b["employee_id"], "role_id": shift_b["role_id"]},
    ]
    location_eligibility = [
        {"employee_id": assignment_a["employee_id"], "location_id": shift_a["location_id"]},
        {"employee_id": assignment_b["employee_id"], "location_id": shift_b["location_id"]},
    ]
    availability_exceptions = [
        {"employee_id": assignment_a["employee_id"], "availability_exception_id": uuid4()},
        {"employee_id": assignment_b["employee_id"], "availability_exception_id": uuid4()},
    ]
    scope_payload = {
        "business_id": uuid4(),
        "location_scope": [shift_a["location_id"], shift_b["location_id"]],
        "planning_window_start": "2026-04-20T00:00:00+00:00",
        "planning_window_end": "2026-04-27T00:00:00+00:00",
        "policy_version": "v1",
    }

    hash_one = auto_scheduler.build_authoring_snapshot_hash(
        shifts=[shift_a, shift_b],
        draft_assignments=[assignment_a, assignment_b],
        employee_role_eligibility=role_eligibility,
        employee_location_eligibility=location_eligibility,
        availability_exceptions=availability_exceptions,
        scope_payload=scope_payload,
    )
    hash_two = auto_scheduler.build_authoring_snapshot_hash(
        shifts=[shift_b, shift_a],
        draft_assignments=[assignment_b, assignment_a],
        employee_role_eligibility=list(reversed(role_eligibility)),
        employee_location_eligibility=list(reversed(location_eligibility)),
        availability_exceptions=list(reversed(availability_exceptions)),
        scope_payload=dict(reversed(list(scope_payload.items()))),
    )

    assert hash_one == hash_two


@pytest.mark.asyncio
async def test_current_scope_snapshot_hash_changes_when_compliance_override_artifacts_change(monkeypatch):
    business_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    shift = Shift(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        role_id=role_id,
        source_system="backfill_native",
        timezone="America/Los_Angeles",
        starts_at=datetime(2026, 4, 20, 16, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 20, 22, 0, tzinfo=timezone.utc),
        lifecycle_status=ShiftLifecycleStatus.draft,
        staffing_status=ShiftStaffingStatus.open,
        seats_requested=1,
        seats_filled=0,
        requires_manager_approval=False,
        premium_cents=0,
        notes=None,
        shift_metadata={},
        created_at=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    async def fake_load_scope_shifts(*_args, **_kwargs):
        return [shift]

    async def fake_load_scope_employees(*_args, **_kwargs):
        return []

    async def fake_load_scope_compliance_override_artifacts(*_args, **_kwargs):
        return []

    monkeypatch.setattr(auto_scheduler, "_load_scope_shifts", fake_load_scope_shifts)
    monkeypatch.setattr(auto_scheduler, "_load_scope_employees", fake_load_scope_employees)
    monkeypatch.setattr(
        auto_scheduler,
        "_load_scope_compliance_override_artifacts",
        fake_load_scope_compliance_override_artifacts,
    )

    hash_without_artifact = await auto_scheduler.current_scope_snapshot_hash(
        None,
        business_id=business_id,
        location_id=location_id,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
    )

    artifact = ComplianceOverrideArtifact(
        id=uuid4(),
        business_id=business_id,
        location_id=location_id,
        shift_id=shift.id,
        employee_id=uuid4(),
        rule_code="meal_break_first_window",
        artifact_type=ComplianceOverrideArtifactType.meal_waiver,
        status=ComplianceOverrideArtifactStatus.approved,
        engine_version="deterministic_compliance_engine_v1",
        profile_payload_hash="sha256:profile",
        approved_at=datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc),
        expires_at=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        revoked_at=None,
        reason_codes=["waiver_possible_but_not_modelled"],
        artifact_payload={},
        created_at=datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc),
    )

    async def fake_load_scope_compliance_override_artifacts_with_value(*_args, **_kwargs):
        return [artifact]

    monkeypatch.setattr(
        auto_scheduler,
        "_load_scope_compliance_override_artifacts",
        fake_load_scope_compliance_override_artifacts_with_value,
    )

    hash_with_artifact = await auto_scheduler.current_scope_snapshot_hash(
        None,
        business_id=business_id,
        location_id=location_id,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
    )

    assert hash_without_artifact != hash_with_artifact


def test_resolve_schedule_policy_payload_reads_business_defaults():
    payload = auto_scheduler.resolve_schedule_policy_payload(
        business_settings={
            "week_start_day": "sunday",
            "coverage": {
                "same_day_second_shift_allowed": False,
                "cross_location_shift_coverage_allowed": True,
            },
            "auto_scheduler": {
                "labor_rule_mode": "hard_block",
                "fairness_mode": "balanced_hours",
                "max_solver_runtime_seconds": 45,
            },
        },
        location_settings={},
    )

    assert payload.week_start_day == "sunday"
    assert payload.publish_mode == "draft_only"
    assert payload.same_day_second_shift_allowed is False
    assert payload.cross_location_shift_coverage_allowed is True
    assert payload.labor_rule_mode == "hard_block"
    assert payload.compliance_rule_mode == "hard_block"
    assert payload.fairness_mode == "balanced_hours"
    assert payload.max_solver_runtime_seconds == 45
    assert payload.hard_constraints["manual_drafts_locked"] is True


@pytest.mark.asyncio
async def test_create_schedule_run_persists_input_contract():
    session = FakeAutoSchedulerSession()
    business = _make_business()
    location = _make_location(business_id=business.id)
    session.get_map[(Business, business.id)] = business
    session.get_map[(Location, location.id)] = location

    schedule_run = await auto_scheduler.create_schedule_run(
        session,
        business_id=business.id,
        location_id=location.id,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        inputs=_run_inputs(),
        input_snapshot_hash="sha256:authoring",
    )

    assert schedule_run.business_id == business.id
    assert schedule_run.location_id == location.id
    assert schedule_run.input_snapshot_hash == "sha256:authoring"
    assert schedule_run.inputs is not None
    assert schedule_run.inputs.reliability_snapshot_hash == "sha256:reliability"
    assert schedule_run.inputs.policy_payload["publish_mode"] == "draft_only"
    assert schedule_run.inputs.fixed_shift_payload == {"shift_ids": []}
    assert schedule_run.inputs.generated_demand_payload == {"proposed_shifts": [], "metadata": {}}
    assert schedule_run.proposed_shifts == []


@pytest.mark.asyncio
async def test_record_schedule_run_result_replaces_artifacts():
    session = FakeAutoSchedulerSession()
    schedule_run = await auto_scheduler.create_schedule_run(
        session,
        business_id=uuid4(),
        location_id=None,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        inputs=_run_inputs(),
        input_snapshot_hash="sha256:authoring",
    )

    await auto_scheduler.record_schedule_run_result(
        session,
        schedule_run,
        status=ScheduleRunStatus.completed,
        assignments=[
            {
                "shift_id": uuid4(),
                "employee_id": uuid4(),
                "decision_score": "0.91",
                "decision_rank": 1,
                "assignment_payload": {"source": "optimizer"},
            }
        ],
        explanation={"summary_payload": {"status": "ok"}},
        metrics={"shift_count": 3, "assigned_shift_count": 1, "objective_value": "10.5"},
    )

    assert schedule_run.status == ScheduleRunStatus.completed
    assert schedule_run.completed_at is not None
    assert len(schedule_run.assignments) == 1
    assert schedule_run.assignments[0].decision_score == Decimal("0.91")
    assert schedule_run.explanation is not None
    assert schedule_run.explanation.summary_payload == {"status": "ok"}
    assert schedule_run.metrics is not None
    assert schedule_run.metrics.shift_count == 3
    assert schedule_run.metrics.objective_value == Decimal("10.5")


@pytest.mark.asyncio
async def test_create_schedule_run_persists_generated_demand_contract():
    session = FakeAutoSchedulerSession()
    business = _make_business()
    location = _make_location(business_id=business.id)
    role = _make_role(business_id=business.id)
    inputs = _run_inputs().model_copy(
        update={
            "generated_demand_payload": _generated_demand_payload(location_id=location.id, role_id=role.id),
            "shift_payload": {
                "shifts": [
                    {
                        "shift_id": auto_scheduler._optimizer_shift_id_for_demand_key(
                            f"{location.id}:{role.id}:2026-04-22T16:00:00+00:00"
                        ),
                        "location_id": str(location.id),
                        "role_id": str(role.id),
                        "starts_at": "2026-04-22T16:00:00+00:00",
                        "ends_at": "2026-04-22T22:00:00+00:00",
                        "timezone": "America/Los_Angeles",
                        "headcount": 1,
                    }
                ]
            },
        }
    )

    schedule_run = await auto_scheduler.create_schedule_run(
        session,
        business_id=business.id,
        location_id=location.id,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        inputs=inputs,
        input_snapshot_hash="sha256:authoring",
    )

    assert len(schedule_run.proposed_shifts) == 1
    proposed_shift = schedule_run.proposed_shifts[0]
    assert proposed_shift.demand_key == f"{location.id}:{role.id}:2026-04-22T16:00:00+00:00"
    assert proposed_shift.source_type == "historical_pattern"
    assert proposed_shift.optimizer_shift_id == auto_scheduler._optimizer_shift_id_for_demand_key(
        proposed_shift.demand_key
    )


@pytest.mark.asyncio
async def test_record_schedule_run_result_maps_generated_assignments_to_proposed_shifts():
    session = FakeAutoSchedulerSession()
    business = _make_business()
    location = _make_location(business_id=business.id)
    role = _make_role(business_id=business.id)
    employee_id = uuid4()
    demand_payload = _generated_demand_payload(location_id=location.id, role_id=role.id)
    proposed_shift = demand_payload.proposed_shifts[0]
    optimizer_shift_id = auto_scheduler._optimizer_shift_id_for_demand_key(proposed_shift.demand_key)
    schedule_run = await auto_scheduler.create_schedule_run(
        session,
        business_id=business.id,
        location_id=location.id,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        inputs=_run_inputs().model_copy(
            update={
                "generated_demand_payload": demand_payload,
                "shift_payload": {
                    "shifts": [
                        {
                            "shift_id": optimizer_shift_id,
                            "location_id": str(location.id),
                            "role_id": str(role.id),
                            "starts_at": "2026-04-22T16:00:00+00:00",
                            "ends_at": "2026-04-22T22:00:00+00:00",
                            "timezone": "America/Los_Angeles",
                            "headcount": 1,
                        }
                    ]
                },
            }
        ),
        input_snapshot_hash="sha256:authoring",
    )

    await auto_scheduler.record_schedule_run_result(
        session,
        schedule_run,
        status=ScheduleRunStatus.completed,
        assignments=[
            {
                "shift_id": UUIDType(optimizer_shift_id),
                "employee_id": employee_id,
                "decision_score": "0.88",
                "decision_rank": 1,
                "assignment_payload": {"source": "optimizer"},
            }
        ],
    )

    assert len(schedule_run.assignments) == 1
    assert schedule_run.assignments[0].shift_id is None
    assert schedule_run.assignments[0].proposed_shift_id == schedule_run.proposed_shifts[0].id
    assert schedule_run.assignments[0].assignment_payload["demand_key"] == proposed_shift.demand_key


@pytest.mark.asyncio
async def test_create_schedule_run_persists_generated_shift_forecast_provenance():
    session = FakeAutoSchedulerSession()
    business = _make_business()
    location = _make_location(business_id=business.id)
    role = _make_role(business_id=business.id)
    source_run_id = uuid4()
    source_point_id = uuid4()
    demand_payload = _generated_demand_payload(
        location_id=location.id,
        role_id=role.id,
        source_run_id=source_run_id,
        source_point_id=source_point_id,
    )

    schedule_run = await auto_scheduler.create_schedule_run(
        session,
        business_id=business.id,
        location_id=location.id,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        inputs=_run_inputs().model_copy(
            update={
                "generated_demand_payload": demand_payload,
                "shift_payload": {"shifts": []},
            }
        ),
        input_snapshot_hash="sha256:authoring",
    )

    proposed_shift = schedule_run.proposed_shifts[0]
    assert proposed_shift.source_run_id == source_run_id
    assert proposed_shift.source_point_id == source_point_id


@pytest.mark.asyncio
async def test_schedule_run_input_contract_round_trips_persisted_inputs():
    session = FakeAutoSchedulerSession()
    schedule_run = await auto_scheduler.create_schedule_run(
        session,
        business_id=uuid4(),
        location_id=None,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        inputs=_run_inputs(),
        input_snapshot_hash="sha256:authoring",
    )

    contract = auto_scheduler.schedule_run_input_contract(schedule_run)

    assert contract.reliability_snapshot_hash == "sha256:reliability"
    assert contract.policy_payload.publish_mode == "draft_only"
    assert contract.fixed_shift_payload == {"shift_ids": []}
    assert contract.generated_demand_payload.proposed_shifts == []
    assert contract.source_metadata["authoring_snapshot_hash"] == "sha256:authoring"


@pytest.mark.asyncio
async def test_execute_schedule_run_persists_optimizer_artifacts():
    session = FakeAutoSchedulerSession()
    schedule_run = await auto_scheduler.create_schedule_run(
        session,
        business_id=uuid4(),
        location_id=None,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        inputs=_run_inputs(),
        input_snapshot_hash="sha256:authoring",
    )

    result = await auto_scheduler.execute_schedule_run(
        session,
        schedule_run.id,
        optimizer=lambda _inputs: {
            "assignments": [
                {
                    "shift_id": uuid4(),
                    "employee_id": uuid4(),
                    "decision_score": "0.77",
                    "decision_rank": 1,
                    "assignment_payload": {"source": "test"},
                }
            ],
            "rejections": [
                {
                    "shift_id": uuid4(),
                    "employee_id": uuid4(),
                    "candidate_rank": 2,
                    "rejection_reason_codes": ["lower_ranked_candidate"],
                    "score_payload": {"total_score": 0.5},
                    "constraint_failure_payload": {},
                }
            ],
            "explanation": {"summary_payload": {"assigned_shift_count": 1}},
            "metrics": {"shift_count": 1, "assigned_shift_count": 1, "objective_value": "0.77"},
        },
    )

    assert result.status == ScheduleRunStatus.completed
    assert result.started_at is not None
    assert result.completed_at is not None
    assert len(result.assignments) == 1
    assert result.assignments[0].decision_score == Decimal("0.77")
    assert len(result.rejections) == 1
    assert result.explanation is not None
    assert result.explanation.summary_payload["assigned_shift_count"] == 1
    assert result.metrics is not None
    assert result.metrics.objective_value == Decimal("0.77")
    assert result.run_metadata["optimizer_engine"] == result.optimizer_engine


@pytest.mark.asyncio
async def test_execute_schedule_run_marks_failure_when_optimizer_raises():
    session = FakeAutoSchedulerSession()
    schedule_run = await auto_scheduler.create_schedule_run(
        session,
        business_id=uuid4(),
        location_id=None,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        inputs=_run_inputs(),
        input_snapshot_hash="sha256:authoring",
    )

    with pytest.raises(RuntimeError, match="optimizer_boom"):
        await auto_scheduler.execute_schedule_run(
            session,
            schedule_run.id,
            optimizer=lambda _inputs: (_ for _ in ()).throw(RuntimeError("optimizer_boom")),
        )

    assert schedule_run.status == ScheduleRunStatus.failed
    assert schedule_run.completed_at is not None
    assert schedule_run.run_metadata["last_error_type"] == "RuntimeError"
    assert schedule_run.run_metadata["last_error_message"] == "optimizer_boom"


@pytest.mark.asyncio
async def test_create_and_execute_schedule_run_for_scope_builds_inputs_and_executes(monkeypatch):
    business = _make_business()
    location = _make_location(business_id=business.id)
    role = _make_role(business_id=business.id)
    employee = _make_employee(business_id=business.id, role=role, location=location)
    employee.availability_rules = [
        EmployeeAvailabilityRule(
            id=uuid4(),
            employee_id=employee.id,
            day_of_week=1,
            start_local_time=time(8, 0),
            end_local_time=time(23, 0),
            timezone="America/Los_Angeles",
            availability_type="available",
            priority=0,
            availability_metadata={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]
    employee.assignments = []

    open_shift = _make_shift(business_id=business.id, location_id=location.id, role_id=role.id)
    open_shift.assignments = []

    reliability_payload = _reliability_payload_for(employee.id)
    captured: dict[str, object] = {}
    snapshot_id = uuid4()
    forecast_run_id = uuid4()

    async def fake_load_business(_session, business_id):
        assert business_id == business.id
        return business

    async def fake_load_location(_session, location_id):
        assert location_id == location.id
        return location

    async def fake_load_shifts(_session, **kwargs):
        captured["shift_scope"] = kwargs
        return [open_shift]

    async def fake_load_employees(_session, **kwargs):
        captured["employee_scope"] = kwargs
        return [employee]

    async def fake_build_reliability(_session, **kwargs):
        captured["reliability"] = kwargs
        return reliability_payload

    async def fake_build_labor_payload(_session, *, shifts, employees, reference_time):
        captured["labor"] = {
            "shift_ids": [shift.id for shift in shifts],
            "employee_ids": [employee.id for employee in employees],
            "reference_time": reference_time,
        }
        return {
            "employees": {
                str(employee.id): {
                    "status": "clear",
                    "projected_ot_hours": 0.0,
                }
            },
            "employees_by_shift": {
                str(open_shift.id): {
                    str(employee.id): {
                        "status": "clear",
                        "projected_ot_hours": 0.0,
                    }
                }
            },
        }

    async def fake_build_compliance_payload(
        _session,
        *,
        business_id=None,
        shifts,
        employees,
        reference_time,
        business_settings,
        generated_demand_payload=None,
        generated_locations=None,
    ):
        captured["compliance"] = {
            "shift_ids": [shift.id for shift in shifts],
            "employee_ids": [employee.id for employee in employees],
            "reference_time": reference_time,
            "business_settings": business_settings,
        }
        return {
            "employees": {
                str(employee.id): {
                    "status": "clear",
                    "blocking_rule_codes": [],
                    "warning_rule_codes": [],
                }
            },
            "employees_by_shift": {
                str(open_shift.id): {
                    str(employee.id): {
                        "status": "clear",
                        "blocking_rule_codes": [],
                        "warning_rule_codes": [],
                    }
                }
            },
        }

    async def fake_create_schedule_run(
        _session,
        *,
        business_id,
        location_id,
        planning_window_start,
        planning_window_end,
        inputs,
        input_snapshot_hash,
        run_metadata,
        **_kwargs,
    ):
        captured["create"] = {
            "business_id": business_id,
            "location_id": location_id,
            "planning_window_start": planning_window_start,
            "planning_window_end": planning_window_end,
            "inputs": inputs,
            "input_snapshot_hash": input_snapshot_hash,
            "run_metadata": run_metadata,
        }
        return SimpleNamespace(id=uuid4())

    async def fake_execute_schedule_run(_session, schedule_run_id, *, optimizer=None):
        captured["execute"] = {"schedule_run_id": schedule_run_id, "optimizer": optimizer}
        return SimpleNamespace(id=schedule_run_id, status=ScheduleRunStatus.completed)

    async def fake_create_demand_feature_snapshot_for_inputs(
        _session,
        *,
        business_id,
        location,
        planning_window_start,
        planning_window_end,
        inputs,
    ):
        captured["snapshot"] = {
            "business_id": business_id,
            "location_id": location.id if location is not None else None,
            "planning_window_start": planning_window_start,
            "planning_window_end": planning_window_end,
            "input_shift_count": len(inputs.shift_payload["shifts"]),
        }
        return SimpleNamespace(
            id=snapshot_id,
            snapshot_hash="sha256:demand_features",
            snapshot_status="completed",
        )

    async def fake_create_labor_forecast_run_for_snapshot(
        _session,
        *,
        business_id,
        location,
        planning_window_start,
        planning_window_end,
        demand_feature_snapshot,
    ):
        captured["forecast"] = {
            "business_id": business_id,
            "location_id": location.id if location is not None else None,
            "planning_window_start": planning_window_start,
            "planning_window_end": planning_window_end,
            "demand_feature_snapshot_id": demand_feature_snapshot.id,
            "feature_snapshot_hash": demand_feature_snapshot.snapshot_hash,
        }
        return SimpleNamespace(
            id=forecast_run_id,
            feature_snapshot_hash=demand_feature_snapshot.snapshot_hash,
            forecast_model_version="baseline_bucketed_v1",
            points=[],
        )

    monkeypatch.setattr(auto_scheduler, "_load_scope_business", fake_load_business)
    monkeypatch.setattr(auto_scheduler, "_load_scope_location", fake_load_location)
    monkeypatch.setattr(auto_scheduler, "_load_scope_shifts", fake_load_shifts)
    monkeypatch.setattr(auto_scheduler, "_load_scope_employees", fake_load_employees)
    monkeypatch.setattr(auto_scheduler, "_build_scope_reliability_payload", fake_build_reliability)
    monkeypatch.setattr(auto_scheduler, "_build_scope_labor_payload", fake_build_labor_payload)
    monkeypatch.setattr(auto_scheduler, "_build_scope_compliance_payload", fake_build_compliance_payload)
    monkeypatch.setattr(auto_scheduler, "create_schedule_run", fake_create_schedule_run)
    monkeypatch.setattr(auto_scheduler, "execute_schedule_run", fake_execute_schedule_run)
    monkeypatch.setattr(
        auto_scheduler,
        "_create_demand_feature_snapshot_for_inputs",
        fake_create_demand_feature_snapshot_for_inputs,
    )
    monkeypatch.setattr(
        auto_scheduler,
        "_create_labor_forecast_run_for_snapshot",
        fake_create_labor_forecast_run_for_snapshot,
    )

    result = await auto_scheduler.create_and_execute_schedule_run_for_scope(
        FakeAutoSchedulerSession(),
        business_id=business.id,
        location_id=location.id,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        source_metadata={"source_request_id": "req_123"},
    )

    assert result.status == ScheduleRunStatus.completed
    assert captured["reliability"]["employee_ids"] == [employee.id]
    inputs = captured["create"]["inputs"]
    assert inputs.policy_payload.publish_mode == "draft_only"
    assert inputs.reliability_snapshot_hash == "sha256:reliability"
    assert inputs.shift_payload["shifts"][0]["shift_id"] == str(open_shift.id)
    assert inputs.fixed_shift_payload["shifts"][0]["shift_id"] == str(open_shift.id)
    assert inputs.generated_demand_payload.proposed_shifts == []
    assert inputs.employee_payload["employees"][0]["employee_id"] == str(employee.id)
    assert inputs.labor_payload["employees"][str(employee.id)]["status"] == "clear"
    assert inputs.labor_payload["employees_by_shift"][str(open_shift.id)][str(employee.id)]["status"] == "clear"
    assert inputs.compliance_payload["employees"][str(employee.id)]["status"] == "clear"
    assert inputs.compliance_payload["employees_by_shift"][str(open_shift.id)][str(employee.id)]["status"] == "clear"
    assert inputs.source_metadata["source_request_id"] == "req_123"
    assert inputs.source_metadata["demand_feature_snapshot_id"] == str(snapshot_id)
    assert inputs.source_metadata["demand_feature_snapshot_hash"] == "sha256:demand_features"
    assert inputs.source_metadata["labor_forecast_run_id"] == str(forecast_run_id)
    assert inputs.source_metadata["labor_forecast_source_type"] == "baseline_forecast"
    assert captured["create"]["run_metadata"]["scope_shift_count"] == 1
    assert captured["create"]["run_metadata"]["scope_employee_count"] == 1
    assert captured["create"]["run_metadata"]["demand_feature_snapshot_id"] == str(snapshot_id)
    assert captured["create"]["run_metadata"]["labor_forecast_run_id"] == str(forecast_run_id)
    assert captured["create"]["run_metadata"]["labor_forecast_source_type"] == "baseline_forecast"
    assert captured["forecast"]["demand_feature_snapshot_id"] == snapshot_id


@pytest.mark.asyncio
async def test_create_and_execute_schedule_run_for_scope_threads_forecast_provenance(monkeypatch):
    business = _make_business()
    location = _make_location(business_id=business.id)
    role = _make_role(business_id=business.id)
    employee = _make_employee(business_id=business.id, role=role, location=location)
    employee.availability_rules = []
    employee.assignments = []
    open_shift = _make_shift(business_id=business.id, location_id=location.id, role_id=role.id)
    open_shift.assignments = []
    generated_demand = _generated_demand_payload(location_id=location.id, role_id=role.id)
    forecast_point_id = uuid4()
    captured: dict[str, object] = {}

    async def fake_load_business(_session, business_id):
        assert business_id == business.id
        return business

    async def fake_load_location(_session, location_id):
        assert location_id == location.id
        return location

    async def fake_load_shifts(_session, **_kwargs):
        return [open_shift]

    async def fake_load_employees(_session, **_kwargs):
        return [employee]

    async def fake_build_reliability(_session, **_kwargs):
        return _reliability_payload_for(employee.id)

    async def fake_build_labor_payload(_session, *, shifts, employees, reference_time):
        return {
            "employees": {str(employee.id): {"status": "clear", "projected_ot_hours": 0.0}},
            "employees_by_shift": {},
        }

    async def fake_build_compliance_payload(
        _session,
        *,
        business_id=None,
        shifts,
        employees,
        reference_time,
        business_settings,
        generated_demand_payload=None,
        generated_locations=None,
    ):
        return {
            "employees": {str(employee.id): {"status": "clear", "blocking_rule_codes": [], "warning_rule_codes": []}},
            "employees_by_shift": {},
        }

    async def fake_create_schedule_run(
        _session,
        *,
        inputs,
        run_metadata,
        **_kwargs,
    ):
        captured["create"] = {
            "inputs": inputs,
            "run_metadata": run_metadata,
        }
        return SimpleNamespace(id=uuid4())

    async def fake_execute_schedule_run(_session, schedule_run_id, *, optimizer=None):
        return SimpleNamespace(id=schedule_run_id, status=ScheduleRunStatus.completed)

    async def fake_attach_generated_demand_break_plans_to_inputs(
        _session,
        *,
        business_id,
        inputs,
        reference_time,
        business_settings,
        generated_locations,
    ):
        return inputs, {
            "compliance_break_plan_status": "skipped",
            "compliance_break_planned_shift_count": 0,
        }

    async def fake_create_demand_feature_snapshot_for_inputs(*_args, **_kwargs):
        return SimpleNamespace(
            id=uuid4(),
            snapshot_hash="sha256:demand_features",
            snapshot_status="completed",
        )

    async def fake_create_labor_forecast_run_for_generated_demand(*_args, generated_demand_payload, **_kwargs):
        captured["forecast_generated_demand"] = generated_demand_payload
        return SimpleNamespace(
            id=uuid4(),
            feature_snapshot_hash="sha256:demand_features",
            points=[
                SimpleNamespace(
                    id=forecast_point_id,
                    forecast_payload={"demand_key": generated_demand.proposed_shifts[0].demand_key},
                )
            ],
        )

    monkeypatch.setattr(auto_scheduler, "_load_scope_business", fake_load_business)
    monkeypatch.setattr(auto_scheduler, "_load_scope_location", fake_load_location)
    monkeypatch.setattr(auto_scheduler, "_load_scope_shifts", fake_load_shifts)
    monkeypatch.setattr(auto_scheduler, "_load_scope_employees", fake_load_employees)
    monkeypatch.setattr(auto_scheduler, "_build_scope_reliability_payload", fake_build_reliability)
    monkeypatch.setattr(auto_scheduler, "_build_scope_labor_payload", fake_build_labor_payload)
    monkeypatch.setattr(auto_scheduler, "_build_scope_compliance_payload", fake_build_compliance_payload)
    monkeypatch.setattr(auto_scheduler, "create_schedule_run", fake_create_schedule_run)
    monkeypatch.setattr(auto_scheduler, "execute_schedule_run", fake_execute_schedule_run)
    monkeypatch.setattr(
        auto_scheduler,
        "_attach_generated_demand_break_plans_to_inputs",
        fake_attach_generated_demand_break_plans_to_inputs,
    )
    monkeypatch.setattr(
        auto_scheduler,
        "_create_demand_feature_snapshot_for_inputs",
        fake_create_demand_feature_snapshot_for_inputs,
    )
    monkeypatch.setattr(
        auto_scheduler,
        "_create_labor_forecast_run_for_generated_demand",
        fake_create_labor_forecast_run_for_generated_demand,
    )

    await auto_scheduler.create_and_execute_schedule_run_for_scope(
        FakeAutoSchedulerSession(),
        business_id=business.id,
        location_id=location.id,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        generated_demand_payload=generated_demand,
    )

    proposed_shift = captured["create"]["inputs"].generated_demand_payload.proposed_shifts[0]
    assert proposed_shift.source_run_id is not None
    assert proposed_shift.source_point_id == forecast_point_id
    assert captured["create"]["inputs"].source_metadata["labor_forecast_point_count"] == 1


@pytest.mark.asyncio
async def test_apply_schedule_run_from_live_scope_uses_current_scope_hash(monkeypatch):
    schedule_run = SimpleNamespace(
        id=uuid4(),
        business_id=uuid4(),
        location_id=uuid4(),
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
    )
    apply_record = SimpleNamespace(id=uuid4(), status=ScheduleApplyStatus.applied)
    captured: dict[str, object] = {}

    async def fake_load_schedule_run(_session, schedule_run_id):
        assert schedule_run_id == schedule_run.id
        return schedule_run

    async def fake_current_hash(_session, **kwargs):
        captured["hash_kwargs"] = kwargs
        return "sha256:current"

    async def fake_apply_to_draft(_session, schedule_run_id, *, current_snapshot_hash):
        captured["apply"] = {
            "schedule_run_id": schedule_run_id,
            "current_snapshot_hash": current_snapshot_hash,
        }
        return apply_record

    monkeypatch.setattr(auto_scheduler, "load_schedule_run", fake_load_schedule_run)
    monkeypatch.setattr(auto_scheduler, "current_scope_snapshot_hash", fake_current_hash)
    monkeypatch.setattr(auto_scheduler, "apply_schedule_run_to_draft", fake_apply_to_draft)
    monkeypatch.setattr(
        auto_scheduler,
        "schedule_run_input_contract",
        lambda _schedule_run: SimpleNamespace(
            generated_demand_payload={"proposed_shifts": [{"demand_key": "generated:1"}], "metadata": {}},
        ),
    )

    result = await auto_scheduler.apply_schedule_run_from_live_scope(
        FakeAutoSchedulerSession(),
        schedule_run.id,
    )

    assert result is apply_record
    assert captured["hash_kwargs"]["business_id"] == schedule_run.business_id
    assert captured["hash_kwargs"]["location_id"] == schedule_run.location_id
    assert captured["hash_kwargs"]["generated_demand_payload"] == {
        "proposed_shifts": [{"demand_key": "generated:1"}],
        "metadata": {},
    }
    assert captured["apply"]["current_snapshot_hash"] == "sha256:current"


def test_build_schedule_run_inputs_from_loaded_scope_respects_locked_manual_drafts_and_availability():
    business = _make_business()
    location = _make_location(business_id=business.id)
    role = _make_role(business_id=business.id)
    eligible_employee = _make_employee(business_id=business.id, role=role, location=location)
    blocked_employee = _make_employee(business_id=business.id, role=role, location=location)

    for employee in (eligible_employee, blocked_employee):
        employee.availability_rules = [
            EmployeeAvailabilityRule(
                id=uuid4(),
                employee_id=employee.id,
                day_of_week=1,
                start_local_time=time(8, 0),
                end_local_time=time(23, 0),
                timezone="America/Los_Angeles",
                availability_type="available",
                priority=0,
                availability_metadata={},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        ]

    blocked_employee.availability_exceptions = [
        EmployeeAvailabilityException(
            id=uuid4(),
            employee_id=blocked_employee.id,
            starts_at=datetime(2026, 4, 21, 15, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 21, 23, 0, tzinfo=timezone.utc),
            exception_type="blocked",
            exception_metadata={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]

    hours_shift = _make_shift(business_id=business.id, location_id=location.id, role_id=role.id)
    prior_assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=hours_shift.id,
        employee_id=eligible_employee.id,
        assigned_via="scheduler_ui",
        status=AssignmentStatus.assigned,
        assignment_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    prior_assignment.shift = hours_shift
    eligible_employee.assignments = [prior_assignment]
    blocked_employee.assignments = []

    open_shift = _make_shift(business_id=business.id, location_id=location.id, role_id=role.id)
    open_shift.assignments = []

    locked_shift = _make_shift(business_id=business.id, location_id=location.id, role_id=role.id)
    locked_assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=locked_shift.id,
        employee_id=eligible_employee.id,
        assigned_via="scheduler_ui",
        status=AssignmentStatus.assigned,
        assignment_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    locked_assignment.employee = eligible_employee
    locked_shift.assignments = [locked_assignment]

    inputs, input_hash = auto_scheduler.build_schedule_run_inputs_from_loaded_scope(
        business_id=business.id,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        reliability_payload=_reliability_payload_for(eligible_employee.id),
        shifts=[open_shift, locked_shift],
        employees=[eligible_employee, blocked_employee],
        business_settings={
            "coverage": {
                "same_day_second_shift_allowed": True,
                "cross_location_shift_coverage_allowed": False,
            },
            "auto_scheduler": {
                "labor_rule_mode": "hard_block",
                "fairness_mode": "balanced_hours",
            },
        },
        location_id=location.id,
        location_settings=location.settings,
        labor_payload={"employees": {}},
        compliance_payload={"employees": {}},
    )

    assert inputs.policy_payload.labor_rule_mode == "hard_block"
    assert inputs.policy_payload.compliance_rule_mode == "hard_block"
    assert inputs.source_metadata["authoring_snapshot_hash"] == input_hash
    assert len(inputs.shift_payload["shifts"]) == 1
    assert len(inputs.fixed_shift_payload["shifts"]) == 1
    assert inputs.generated_demand_payload.proposed_shifts == []
    assert inputs.shift_payload["shifts"][0]["shift_id"] == str(open_shift.id)
    assert str(locked_shift.id) not in {
        row["shift_id"] for row in inputs.shift_payload["shifts"]
    }
    draft_assignment_rows = auto_scheduler._draft_assignment_rows(
        shifts=[open_shift, locked_shift],
        location_id=location.id,
    )
    assert str(locked_shift.id) in {row["shift_id"] for row in draft_assignment_rows}
    eligible_by_shift = inputs.availability_payload["eligible_employee_ids_by_shift"][str(open_shift.id)]
    assert eligible_by_shift == [str(eligible_employee.id)]
    employee_row = next(row for row in inputs.employee_payload["employees"] if row["employee_id"] == str(eligible_employee.id))
    assert employee_row["assigned_hours"] == 12.0


def test_build_schedule_run_inputs_from_loaded_scope_merges_generated_demand():
    business = _make_business()
    location = _make_location(business_id=business.id)
    role = _make_role(business_id=business.id)
    employee = _make_employee(business_id=business.id, role=role, location=location)
    employee.availability_rules = []
    employee.assignments = []
    open_shift = _make_shift(business_id=business.id, location_id=location.id, role_id=role.id)
    open_shift.assignments = []

    generated_demand = _generated_demand_payload(location_id=location.id, role_id=role.id)

    inputs, _ = auto_scheduler.build_schedule_run_inputs_from_loaded_scope(
        business_id=business.id,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        reliability_payload=_reliability_payload_for(employee.id),
        shifts=[open_shift],
        employees=[employee],
        business_settings={},
        location_id=location.id,
        location_settings=location.settings,
        labor_payload={"employees": {}},
        generated_demand_payload=generated_demand,
    )

    assert len(inputs.fixed_shift_payload["shifts"]) == 1
    assert len(inputs.generated_demand_payload.proposed_shifts) == 1
    assert len(inputs.shift_payload["shifts"]) == 2
    generated_shift_row = next(
        row for row in inputs.shift_payload["shifts"] if row["shift_id"] != str(open_shift.id)
    )
    assert generated_shift_row["demand_key"] == generated_demand.proposed_shifts[0].demand_key
    assert inputs.source_metadata["fixed_shift_count"] == 1
    assert inputs.source_metadata["generated_shift_count"] == 1


def test_evaluate_schedule_run_apply_rejects_stale_snapshot():
    result = auto_scheduler.evaluate_schedule_run_apply(
        schedule_run_status=ScheduleRunStatus.completed,
        target_snapshot_hash="sha256:expected",
        current_snapshot_hash="sha256:changed",
    )

    assert result.can_apply is False
    assert result.status == ScheduleApplyStatus.stale_rejected
    assert result.reason_code == "authoring_snapshot_changed"
    assert result.stale_reason == "input_snapshot_hash_mismatch"


def test_evaluate_schedule_run_apply_returns_no_op_for_existing_successful_apply():
    apply_id = uuid4()
    result = auto_scheduler.evaluate_schedule_run_apply(
        schedule_run_status=ScheduleRunStatus.completed,
        target_snapshot_hash="sha256:unchanged",
        current_snapshot_hash="sha256:unchanged",
        existing_successful_apply=SimpleNamespace(
            id=apply_id,
            status=ScheduleApplyStatus.applied.value,
            target_snapshot_hash="sha256:unchanged",
            current_snapshot_hash="sha256:unchanged",
        ),
    )

    assert result.can_apply is False
    assert result.status == ScheduleApplyStatus.no_op
    assert result.reason_code == "existing_successful_apply"
    assert result.existing_apply_id == apply_id


def test_evaluate_schedule_run_apply_returns_no_op_for_post_apply_snapshot():
    result = auto_scheduler.evaluate_schedule_run_apply(
        schedule_run_status=ScheduleRunStatus.completed,
        target_snapshot_hash="sha256:unchanged",
        current_snapshot_hash="sha256:post_apply",
        existing_successful_apply=SimpleNamespace(
            id=uuid4(),
            status=ScheduleApplyStatus.applied.value,
            target_snapshot_hash="sha256:unchanged",
            current_snapshot_hash="sha256:pre_apply",
            apply_metadata={"post_apply_snapshot_hash": "sha256:post_apply"},
        ),
    )

    assert result.can_apply is False
    assert result.status == ScheduleApplyStatus.no_op


@pytest.mark.asyncio
async def test_apply_schedule_run_to_draft_creates_proposed_assignment(monkeypatch):
    session = FakeAutoSchedulerSession()
    business = _make_business()
    location = _make_location(business_id=business.id)
    role = _make_role(business_id=business.id)
    employee = _make_employee(business_id=business.id, role=role, location=location)
    shift = _make_shift(business_id=business.id, location_id=location.id, role_id=role.id)
    shift.location = location
    shift.role = role
    shift.assignments = []

    session.get_map[(Business, business.id)] = business
    session.get_map[(Location, location.id)] = location
    session.get_map[(Role, role.id)] = role
    session.get_map[(Employee, employee.id)] = employee
    session.get_map[(Shift, shift.id)] = shift
    monkeypatch.setattr(
        auto_scheduler,
        "current_scope_snapshot_hash",
        AsyncMock(return_value="sha256:post_apply"),
    )

    schedule_run = await auto_scheduler.create_schedule_run(
        session,
        business_id=business.id,
        location_id=location.id,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        inputs=_run_inputs(),
        input_snapshot_hash="sha256:authoring",
    )
    schedule_run.assignments = [
        ScheduleRunAssignment(
            id=uuid4(),
            schedule_run_id=schedule_run.id,
            shift_id=shift.id,
            employee_id=employee.id,
            decision_score=Decimal("0.94"),
            decision_rank=1,
            assignment_payload={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]
    schedule_run.status = ScheduleRunStatus.completed
    session.get_map[(type(schedule_run), schedule_run.id)] = schedule_run

    apply_record = await auto_scheduler.apply_schedule_run_to_draft(
        session,
        schedule_run.id,
        current_snapshot_hash="sha256:authoring",
    )

    assert apply_record.status == ScheduleApplyStatus.applied
    assert apply_record.applied_at is not None
    assert shift.seats_filled == 1
    assert shift.staffing_status == ShiftStaffingStatus.covered
    assert len(shift.assignments) == 1
    assignment = shift.assignments[0]
    assert assignment.status == AssignmentStatus.proposed
    assert assignment.assigned_via == "auto_scheduler"
    assert assignment.assignment_metadata["schedule_run_id"] == str(schedule_run.id)
    assert assignment.assignment_metadata["schedule_run_apply_id"] == str(apply_record.id)
    assert apply_record.apply_metadata["post_apply_snapshot_hash"] == "sha256:post_apply"


@pytest.mark.asyncio
async def test_apply_schedule_run_to_draft_preserves_manual_assignment_for_same_employee(monkeypatch):
    session = FakeAutoSchedulerSession()
    business = _make_business()
    location = _make_location(business_id=business.id)
    role = _make_role(business_id=business.id)
    employee = _make_employee(business_id=business.id, role=role, location=location)
    shift = _make_shift(business_id=business.id, location_id=location.id, role_id=role.id)
    shift.location = location
    shift.role = role
    manual_assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=shift.id,
        employee_id=employee.id,
        assigned_via="scheduler_ui",
        status=AssignmentStatus.assigned,
        assignment_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    manual_assignment.employee = employee
    shift.assignments = [manual_assignment]

    session.get_map[(Employee, employee.id)] = employee
    session.get_map[(Shift, shift.id)] = shift
    monkeypatch.setattr(
        auto_scheduler,
        "current_scope_snapshot_hash",
        AsyncMock(return_value="sha256:post_apply"),
    )

    schedule_run = await auto_scheduler.create_schedule_run(
        session,
        business_id=business.id,
        location_id=location.id,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        inputs=_run_inputs(),
        input_snapshot_hash="sha256:authoring",
    )
    schedule_run.assignments = [
        ScheduleRunAssignment(
            id=uuid4(),
            schedule_run_id=schedule_run.id,
            shift_id=shift.id,
            employee_id=employee.id,
            decision_score=Decimal("0.80"),
            decision_rank=1,
            assignment_payload={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]
    schedule_run.status = ScheduleRunStatus.completed
    session.get_map[(type(schedule_run), schedule_run.id)] = schedule_run

    apply_record = await auto_scheduler.apply_schedule_run_to_draft(
        session,
        schedule_run.id,
        current_snapshot_hash="sha256:authoring",
    )

    assert apply_record.status == ScheduleApplyStatus.applied
    assert len(shift.assignments) == 1
    assert shift.assignments[0].assigned_via == "scheduler_ui"


@pytest.mark.asyncio
async def test_apply_schedule_run_to_draft_blocks_manual_assignment_replacement(monkeypatch):
    session = FakeAutoSchedulerSession()
    business = _make_business()
    location = _make_location(business_id=business.id)
    role = _make_role(business_id=business.id)
    manual_employee = _make_employee(business_id=business.id, role=role, location=location)
    target_employee = _make_employee(business_id=business.id, role=role, location=location)
    shift = _make_shift(business_id=business.id, location_id=location.id, role_id=role.id)
    shift.location = location
    shift.role = role
    manual_assignment = ShiftAssignment(
        id=uuid4(),
        shift_id=shift.id,
        employee_id=manual_employee.id,
        assigned_via="scheduler_ui",
        status=AssignmentStatus.assigned,
        assignment_metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    manual_assignment.employee = manual_employee
    shift.assignments = [manual_assignment]

    session.get_map[(Employee, manual_employee.id)] = manual_employee
    session.get_map[(Employee, target_employee.id)] = target_employee
    session.get_map[(Shift, shift.id)] = shift
    monkeypatch.setattr(
        auto_scheduler,
        "current_scope_snapshot_hash",
        AsyncMock(return_value="sha256:post_apply"),
    )

    schedule_run = await auto_scheduler.create_schedule_run(
        session,
        business_id=business.id,
        location_id=location.id,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        inputs=_run_inputs(),
        input_snapshot_hash="sha256:authoring",
    )
    schedule_run.assignments = [
        ScheduleRunAssignment(
            id=uuid4(),
            schedule_run_id=schedule_run.id,
            shift_id=shift.id,
            employee_id=target_employee.id,
            decision_score=Decimal("0.88"),
            decision_rank=1,
            assignment_payload={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]
    schedule_run.status = ScheduleRunStatus.completed
    session.get_map[(type(schedule_run), schedule_run.id)] = schedule_run

    with pytest.raises(ValueError, match="manual_draft_assignment_locked"):
        await auto_scheduler.apply_schedule_run_to_draft(
            session,
            schedule_run.id,
            current_snapshot_hash="sha256:authoring",
        )


@pytest.mark.asyncio
async def test_apply_schedule_run_to_draft_materializes_generated_shift(monkeypatch):
    session = FakeAutoSchedulerSession()
    business = _make_business()
    location = _make_location(business_id=business.id)
    role = _make_role(business_id=business.id)
    employee = _make_employee(business_id=business.id, role=role, location=location)
    session.get_map[(Employee, employee.id)] = employee
    monkeypatch.setattr(
        auto_scheduler,
        "current_scope_snapshot_hash",
        AsyncMock(return_value="sha256:post_apply"),
    )

    generated_demand = _generated_demand_payload(location_id=location.id, role_id=role.id)
    generated_demand.proposed_shifts[0].generation_payload["planned_segments"] = [
        {
            "sequence_no": 1,
            "segment_type": ShiftSegmentType.work.value,
            "starts_at": generated_demand.proposed_shifts[0].starts_at.isoformat(),
            "ends_at": generated_demand.proposed_shifts[0].ends_at.isoformat(),
            "segment_metadata": {"planned_by": "test"},
            "breaks": [
                {
                    "sequence_no": 1,
                    "break_type": ShiftBreakType.meal.value,
                    "is_paid": False,
                    "starts_at": datetime(2026, 4, 22, 20, 0, tzinfo=timezone.utc).isoformat(),
                    "ends_at": datetime(2026, 4, 22, 20, 30, tzinfo=timezone.utc).isoformat(),
                    "notes": "planned_first_meal_break",
                    "break_metadata": {"planned_by": "test"},
                }
            ],
        }
    ]
    optimizer_shift_id = auto_scheduler._optimizer_shift_id_for_demand_key(
        generated_demand.proposed_shifts[0].demand_key
    )
    schedule_run = await auto_scheduler.create_schedule_run(
        session,
        business_id=business.id,
        location_id=location.id,
        planning_window_start=datetime(2026, 4, 20, 7, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 27, 7, 0, tzinfo=timezone.utc),
        inputs=_run_inputs().model_copy(
            update={
                "generated_demand_payload": generated_demand,
                "shift_payload": {
                    "shifts": [
                        {
                            "shift_id": optimizer_shift_id,
                            "location_id": str(location.id),
                            "role_id": str(role.id),
                            "starts_at": "2026-04-22T16:00:00+00:00",
                            "ends_at": "2026-04-22T22:00:00+00:00",
                            "timezone": "America/Los_Angeles",
                            "headcount": 1,
                        }
                    ]
                },
            }
        ),
        input_snapshot_hash="sha256:authoring",
    )
    proposed_shift = schedule_run.proposed_shifts[0]
    schedule_run.assignments = [
        ScheduleRunAssignment(
            id=uuid4(),
            schedule_run_id=schedule_run.id,
            proposed_shift_id=proposed_shift.id,
            employee_id=employee.id,
            decision_score=Decimal("0.91"),
            decision_rank=1,
            assignment_payload={"demand_key": proposed_shift.demand_key},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]
    schedule_run.status = ScheduleRunStatus.completed
    session.get_map[(type(schedule_run), schedule_run.id)] = schedule_run

    apply_record = await auto_scheduler.apply_schedule_run_to_draft(
        session,
        schedule_run.id,
        current_snapshot_hash="sha256:authoring",
    )

    assert apply_record.status == ScheduleApplyStatus.applied
    assert proposed_shift.applied_shift_id is not None
    created_shift = session.get_map[(Shift, proposed_shift.applied_shift_id)]
    assert created_shift.source_system == "auto_scheduler_demand"
    assert created_shift.shift_metadata["demand_key"] == proposed_shift.demand_key
    assert len(created_shift.segments) == 1
    assert created_shift.segments[0].breaks[0].break_type == ShiftBreakType.meal
    assert len(created_shift.assignments) == 1
    assert created_shift.assignments[0].employee_id == employee.id


@pytest.mark.asyncio
async def test_attach_generated_demand_break_plans_to_inputs_plans_segments(monkeypatch):
    session = FakeAutoSchedulerSession()
    business = _make_business()
    location = _make_location(business_id=business.id)
    role = _make_role(business_id=business.id)
    generated_demand = _generated_demand_payload(location_id=location.id, role_id=role.id)

    async def fake_runtime_resolved_profile(_session, *, location, business=None, as_of=None):
        assert location.id == location.id
        return _california_break_profile()

    monkeypatch.setattr(labor_rules, "runtime_resolved_profile", fake_runtime_resolved_profile)

    inputs, metadata = await auto_scheduler._attach_generated_demand_break_plans_to_inputs(
        session,
        business_id=business.id,
        inputs=_run_inputs().model_copy(update={"generated_demand_payload": generated_demand}),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        business_settings={},
        generated_locations={location.id: location},
    )

    generation_payload = inputs.generated_demand_payload.proposed_shifts[0].generation_payload
    assert metadata["compliance_break_planned_shift_count"] == 1
    assert generation_payload["compliance_break_plan_status"] == "planned"
    assert generation_payload["compliance_break_plan_version"] == "deterministic_break_plan_v1"
    assert len(generation_payload["planned_segments"]) == 1
    assert len(generation_payload["planned_segments"][0]["breaks"]) >= 1


@pytest.mark.asyncio
async def test_attach_generated_demand_break_plans_to_inputs_plans_new_york_windowed_meals(monkeypatch):
    session = FakeAutoSchedulerSession()
    business = _make_business()
    location = _make_location(business_id=business.id)
    location.timezone = "America/New_York"
    location.region = "NY"
    role = _make_role(business_id=business.id)
    generated_demand = _generated_demand_payload(location_id=location.id, role_id=role.id)
    generated_demand.proposed_shifts[0].timezone = "America/New_York"
    generated_demand.proposed_shifts[0].starts_at = datetime(2026, 4, 22, 14, 0, tzinfo=timezone.utc)
    generated_demand.proposed_shifts[0].ends_at = datetime(2026, 4, 23, 0, 0, tzinfo=timezone.utc)
    generated_demand.proposed_shifts[0].demand_key = f"{location.id}:{role.id}:2026-04-22T14:00:00+00:00"

    async def fake_runtime_resolved_profile(_session, *, location, business=None, as_of=None):
        return _new_york_hospitality_profile()

    monkeypatch.setattr(labor_rules, "runtime_resolved_profile", fake_runtime_resolved_profile)

    inputs, metadata = await auto_scheduler._attach_generated_demand_break_plans_to_inputs(
        session,
        business_id=business.id,
        inputs=_run_inputs().model_copy(update={"generated_demand_payload": generated_demand}),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        business_settings={},
        generated_locations={location.id: location},
    )

    generation_payload = inputs.generated_demand_payload.proposed_shifts[0].generation_payload
    notes = [item["notes"] for item in generation_payload["planned_segments"][0]["breaks"]]
    assert metadata["compliance_break_planned_shift_count"] == 1
    assert "planned_midday_meal_break" in notes
    assert "planned_evening_meal_break" in notes


@pytest.mark.asyncio
async def test_build_scope_compliance_payload_includes_generated_shift_rows(monkeypatch):
    session = FakeAutoSchedulerSession()
    business = _make_business()
    location = _make_location(business_id=business.id)
    role = _make_role(business_id=business.id)
    employee = _make_employee(business_id=business.id, role=role, location=location)
    employee.assignments = []
    generated_demand = _generated_demand_payload(location_id=location.id, role_id=role.id)

    async def fake_runtime_resolved_profile(_session, *, location, business=None, as_of=None):
        return _california_break_profile()

    async def fake_build_hours_snapshots(_session, *, employees, shift, profile, now=None):
        return {employee.id: SimpleNamespace(counted_intervals=()) for employee in employees}

    def fake_evaluate_overtime_projection(profile, *, candidate_shift, counted_intervals, reference_time):
        return {
            "status": "clear",
            "projected_regular_hours": 0.0,
            "projected_ot_hours": 0.0,
            "projected_dt_hours": 0.0,
            "projected_cost_multiplier": 1.0,
            "reason_codes": ["no_overtime_triggered"],
        }

    monkeypatch.setattr(labor_rules, "runtime_resolved_profile", fake_runtime_resolved_profile)
    monkeypatch.setattr(labor_rules, "build_hours_snapshots", fake_build_hours_snapshots)
    monkeypatch.setattr(labor_rules, "evaluate_overtime_projection", fake_evaluate_overtime_projection)

    planned_inputs, _metadata = await auto_scheduler._attach_generated_demand_break_plans_to_inputs(
        session,
        business_id=business.id,
        inputs=_run_inputs().model_copy(update={"generated_demand_payload": generated_demand}),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        business_settings={},
        generated_locations={location.id: location},
    )
    payload = await auto_scheduler._build_scope_compliance_payload(
        session,
        business_id=business.id,
        shifts=[],
        employees=[employee],
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        business_settings={},
        generated_demand_payload=planned_inputs.generated_demand_payload,
        generated_locations={location.id: location},
    )

    generated_shift_id = auto_scheduler._optimizer_shift_id_for_demand_key(
        planned_inputs.generated_demand_payload.proposed_shifts[0].demand_key
    )
    evaluation = payload["employees_by_shift"][generated_shift_id][str(employee.id)]
    assert evaluation["status"] == "clear"
    assert evaluation["blocking_rule_codes"] == []


@pytest.mark.asyncio
async def test_build_scope_compliance_payload_applies_override_artifacts_for_persisted_shifts(monkeypatch):
    session = FakeAutoSchedulerSession()
    business = _make_business()
    location = _make_location(business_id=business.id)
    role = _make_role(business_id=business.id)
    employee = _make_employee(business_id=business.id, role=role, location=location)
    employee.assignments = []
    shift = _make_shift(business_id=business.id, location_id=location.id, role_id=role.id)
    shift.location = location
    now = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)
    artifact = ComplianceOverrideArtifact(
        id=uuid4(),
        business_id=business.id,
        location_id=location.id,
        shift_id=shift.id,
        employee_id=employee.id,
        rule_code="clopening_restricted",
        artifact_type=ComplianceOverrideArtifactType.written_consent,
        status=ComplianceOverrideArtifactStatus.approved,
        engine_version=auto_scheduler.compliance_engine.COMPLIANCE_ENGINE_VERSION,
        approved_at=now,
        expires_at=now + timedelta(hours=8),
        reason_codes=["minimum_rest_window_violation"],
        artifact_payload={},
        created_at=now,
        updated_at=now,
    )

    async def fake_runtime_resolved_profile(_session, *, location, business=None, as_of=None):
        return SimpleNamespace(code="ca_restaurant_core")

    async def fake_build_hours_snapshots(_session, *, employees, shift, profile, now=None):
        return {employee.id: SimpleNamespace(counted_intervals=()) for employee in employees}

    def fake_evaluate_overtime_projection(profile, *, candidate_shift, counted_intervals, reference_time):
        return {
            "status": "clear",
            "projected_regular_hours": 0.0,
            "projected_ot_hours": 0.0,
            "projected_dt_hours": 0.0,
            "projected_cost_multiplier": 1.0,
            "reason_codes": ["no_overtime_triggered"],
        }

    def fake_evaluate_shift_assignment_compliance(
        profile,
        *,
        candidate_shift,
        counted_intervals,
        reference_time,
        overtime_projection=None,
        employee_base_hourly_rate_cents=None,
        employee_date_of_birth=None,
        employee_minor_school_status=None,
        employee_work_permit_number=None,
        employee_work_permit_effective_start_on=None,
        employee_work_permit_expires_on=None,
        employee_work_permit_max_daily_minutes=None,
        employee_work_permit_max_weekly_minutes=None,
        employee_work_permit_earliest_start_local_time=None,
        employee_work_permit_latest_end_local_time=None,
        employee_work_permit_rule_profile=None,
        business_settings=None,
        location_settings=None,
    ):
        return {
            "status": "block",
            "blocking_rule_codes": ["clopening_restricted"],
            "warning_rule_codes": [],
            "premium_rule_codes": ["clopening_restricted"],
            "would_block": True,
            "requires_override": True,
            "rule_results": [
                {
                    "rule_code": "clopening_restricted",
                    "status": "block",
                    "reason_codes": ["minimum_rest_window_violation"],
                    "premium_required": True,
                    "would_block": True,
                    "written_consent_allowed": True,
                }
            ],
        }

    async def fake_active_artifacts_for_shift_employees(
        _session,
        *,
        shift_id,
        employee_ids,
        reference_time=None,
    ):
        assert shift_id == shift.id
        assert employee_ids == [employee.id]
        return {employee.id: [artifact]}

    monkeypatch.setattr(labor_rules, "runtime_resolved_profile", fake_runtime_resolved_profile)
    monkeypatch.setattr(labor_rules, "build_hours_snapshots", fake_build_hours_snapshots)
    monkeypatch.setattr(labor_rules, "evaluate_overtime_projection", fake_evaluate_overtime_projection)
    monkeypatch.setattr(
        auto_scheduler.compliance_engine,
        "evaluate_shift_assignment_compliance",
        fake_evaluate_shift_assignment_compliance,
    )
    monkeypatch.setattr(
        auto_scheduler.compliance_overrides,
        "active_artifacts_for_shift_employees",
        fake_active_artifacts_for_shift_employees,
    )

    payload = await auto_scheduler._build_scope_compliance_payload(
        session,
        business_id=business.id,
        shifts=[shift],
        employees=[employee],
        reference_time=now,
        business_settings={},
    )

    evaluation = payload["employees_by_shift"][str(shift.id)][str(employee.id)]
    assert evaluation["status"] == "warning"
    assert evaluation["blocking_rule_codes"] == []
    assert evaluation["warning_rule_codes"] == ["clopening_restricted"]
    assert evaluation["override_applied"] is True
    assert evaluation["override_artifact_id"] == str(artifact.id)
    assert payload["employees"][str(employee.id)]["override_applied"] is True
