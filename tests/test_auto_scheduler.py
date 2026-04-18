from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.models.common import ScheduleApplyStatus, ScheduleRunStatus
from app.services import auto_scheduler


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


def test_resolve_schedule_policy_payload_uses_business_defaults():
    payload = auto_scheduler.resolve_schedule_policy_payload(
        business_settings={
            "week_start_day": "sunday",
            "coverage": {
                "same_day_second_shift_allowed": False,
                "cross_location_shift_coverage_allowed": True,
            },
        },
        location_settings={},
    )

    assert payload.week_start_day == "sunday"
    assert payload.publish_mode == "draft_only"
    assert payload.same_day_second_shift_allowed is False
    assert payload.cross_location_shift_coverage_allowed is True
    assert payload.hard_constraints["manual_drafts_locked"] is True


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


def test_evaluate_schedule_run_apply_requires_completed_run():
    result = auto_scheduler.evaluate_schedule_run_apply(
        schedule_run_status=ScheduleRunStatus.running,
        target_snapshot_hash="sha256:unchanged",
        current_snapshot_hash="sha256:unchanged",
    )

    assert result.can_apply is False
    assert result.status == ScheduleApplyStatus.failed
    assert result.reason_code == "schedule_run_not_completed"
