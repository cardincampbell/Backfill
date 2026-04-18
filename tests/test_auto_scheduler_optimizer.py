from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.auto_scheduler import (
    ReliabilityComponentPayload,
    ReliabilityEmployeeSnapshotPayload,
    ReliabilitySnapshotPayload,
    SchedulePolicyPayload,
    ScheduleRunInputContract,
)
from app.services import auto_scheduler_optimizer


def _reliability_component(score: float) -> ReliabilityComponentPayload:
    return ReliabilityComponentPayload(
        score=score,
        confidence=0.8,
        sample_size=10,
        metrics={},
    )


def _employee_snapshot(employee_id, score: float) -> ReliabilityEmployeeSnapshotPayload:
    return ReliabilityEmployeeSnapshotPayload(
        employee_id=employee_id,
        overall_score=score,
        confidence=0.8,
        sample_size=10,
        attendance=_reliability_component(score),
        punctuality=_reliability_component(score),
        commitment=_reliability_component(score),
        response_behavior=_reliability_component(score),
        coverage_reliability=_reliability_component(score),
        metadata={},
    )


def _inputs(
    *,
    policy: SchedulePolicyPayload,
    shifts: list[dict],
    employees: list[dict],
    reliability_scores: dict,
    eligible_by_shift: dict,
    labor_projection: dict | None = None,
) -> ScheduleRunInputContract:
    if isinstance(labor_projection, dict) and (
        "employees" in labor_projection or "employees_by_shift" in labor_projection
    ):
        labor_payload = labor_projection
    else:
        labor_payload = {"employees": labor_projection or {}}
    return ScheduleRunInputContract(
        shift_payload={"shifts": shifts},
        employee_payload={"employees": employees},
        availability_payload={"eligible_employee_ids_by_shift": eligible_by_shift},
        policy_payload=policy,
        labor_payload=labor_payload,
        reliability_payload=ReliabilitySnapshotPayload(
            generated_at=datetime(2026, 4, 18, 18, 0, tzinfo=timezone.utc),
            snapshot_hash="sha256:reliability",
            snapshot_version="v1",
            employees=[
                _employee_snapshot(employee_id, score)
                for employee_id, score in reliability_scores.items()
            ],
            metadata={},
        ),
        reliability_snapshot_generated_at=datetime(2026, 4, 18, 18, 0, tzinfo=timezone.utc),
        reliability_snapshot_hash="sha256:reliability",
        reliability_snapshot_version="v1",
        source_metadata={},
    )


def test_optimizer_assigns_highest_scoring_eligible_employee():
    shift_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    employee_a = uuid4()
    employee_b = uuid4()

    result = auto_scheduler_optimizer.optimize_schedule_inputs(
        _inputs(
            policy=SchedulePolicyPayload(),
            shifts=[
                {
                    "shift_id": str(shift_id),
                    "location_id": str(location_id),
                    "role_id": str(role_id),
                    "starts_at": "2026-04-21T16:00:00+00:00",
                    "ends_at": "2026-04-21T22:00:00+00:00",
                }
            ],
            employees=[
                {
                    "employee_id": str(employee_a),
                    "role_ids": [str(role_id)],
                    "location_ids": [str(location_id)],
                    "assigned_hours": 20,
                    "target_hours": 30,
                },
                {
                    "employee_id": str(employee_b),
                    "role_ids": [str(role_id)],
                    "location_ids": [str(location_id)],
                    "assigned_hours": 20,
                    "target_hours": 30,
                },
            ],
            reliability_scores={
                employee_a: 0.9,
                employee_b: 0.75,
            },
            eligible_by_shift={str(shift_id): [str(employee_a), str(employee_b)]},
        )
    )

    assert len(result["assignments"]) == 1
    assert result["assignments"][0]["employee_id"] == employee_a
    assert result["metrics"]["assigned_shift_count"] == 1
    assert result["rejections"][0]["employee_id"] == employee_b


def test_optimizer_respects_hard_block_labor_rule_mode():
    shift_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    employee_a = uuid4()
    employee_b = uuid4()

    result = auto_scheduler_optimizer.optimize_schedule_inputs(
        _inputs(
            policy=SchedulePolicyPayload(labor_rule_mode="hard_block"),
            shifts=[
                {
                    "shift_id": str(shift_id),
                    "location_id": str(location_id),
                    "role_id": str(role_id),
                    "starts_at": "2026-04-21T16:00:00+00:00",
                    "ends_at": "2026-04-21T22:00:00+00:00",
                }
            ],
            employees=[
                {
                    "employee_id": str(employee_a),
                    "role_ids": [str(role_id)],
                    "location_ids": [str(location_id)],
                },
                {
                    "employee_id": str(employee_b),
                    "role_ids": [str(role_id)],
                    "location_ids": [str(location_id)],
                },
            ],
            reliability_scores={employee_a: 0.92, employee_b: 0.8},
            eligible_by_shift={str(shift_id): [str(employee_a), str(employee_b)]},
            labor_projection={
                str(employee_a): {"would_trigger_overtime": True},
                str(employee_b): {"would_trigger_overtime": False},
            },
        )
    )

    assert result["assignments"][0]["employee_id"] == employee_b
    rejected = next(item for item in result["rejections"] if item["employee_id"] == employee_a)
    assert "labor_rule_hard_block" in rejected["rejection_reason_codes"]


def test_optimizer_uses_fairness_adjustment_to_prefer_under_scheduled_employee():
    shift_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    employee_a = uuid4()
    employee_b = uuid4()

    result = auto_scheduler_optimizer.optimize_schedule_inputs(
        _inputs(
            policy=SchedulePolicyPayload(),
            shifts=[
                {
                    "shift_id": str(shift_id),
                    "location_id": str(location_id),
                    "role_id": str(role_id),
                    "starts_at": "2026-04-21T16:00:00+00:00",
                    "ends_at": "2026-04-21T22:00:00+00:00",
                }
            ],
            employees=[
                {
                    "employee_id": str(employee_a),
                    "role_ids": [str(role_id)],
                    "location_ids": [str(location_id)],
                    "assigned_hours": 36,
                    "target_hours": 40,
                },
                {
                    "employee_id": str(employee_b),
                    "role_ids": [str(role_id)],
                    "location_ids": [str(location_id)],
                    "assigned_hours": 8,
                    "target_hours": 40,
                },
            ],
            reliability_scores={employee_a: 0.82, employee_b: 0.8},
            eligible_by_shift={str(shift_id): [str(employee_a), str(employee_b)]},
        )
    )

    assert result["assignments"][0]["employee_id"] == employee_b
    assert result["explanation"]["fairness_payload"]["max_hours"] >= result["explanation"]["fairness_payload"]["min_hours"]


def test_optimizer_prefers_shift_specific_labor_projection_over_employee_fallback():
    shift_id = uuid4()
    location_id = uuid4()
    role_id = uuid4()
    employee_a = uuid4()
    employee_b = uuid4()

    result = auto_scheduler_optimizer.optimize_schedule_inputs(
        _inputs(
            policy=SchedulePolicyPayload(labor_rule_mode="hard_block"),
            shifts=[
                {
                    "shift_id": str(shift_id),
                    "location_id": str(location_id),
                    "role_id": str(role_id),
                    "starts_at": "2026-04-21T16:00:00+00:00",
                    "ends_at": "2026-04-21T22:00:00+00:00",
                }
            ],
            employees=[
                {
                    "employee_id": str(employee_a),
                    "role_ids": [str(role_id)],
                    "location_ids": [str(location_id)],
                },
                {
                    "employee_id": str(employee_b),
                    "role_ids": [str(role_id)],
                    "location_ids": [str(location_id)],
                },
            ],
            reliability_scores={employee_a: 0.95, employee_b: 0.8},
            eligible_by_shift={str(shift_id): [str(employee_a), str(employee_b)]},
            labor_projection={
                "employees": {
                    str(employee_a): {"would_trigger_overtime": False},
                    str(employee_b): {"would_trigger_overtime": False},
                },
                "employees_by_shift": {
                    str(shift_id): {
                        str(employee_a): {"would_trigger_overtime": True},
                        str(employee_b): {"would_trigger_overtime": False},
                    }
                },
            },
        )
    )

    assert result["assignments"][0]["employee_id"] == employee_b
    rejected = next(item for item in result["rejections"] if item["employee_id"] == employee_a)
    assert "labor_rule_hard_block" in rejected["rejection_reason_codes"]
