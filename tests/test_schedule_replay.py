from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.auto_scheduler import ScheduleRun, ScheduleRunAssignment, ScheduleRunInput
from app.models.common import ScheduleRunStatus, ScheduleRunType
from app.services import schedule_replay


def test_calculate_replay_metrics_summarizes_match_and_override_delta():
    shift_hours = {
        "shift-1": 8.0,
        "shift-2": 6.0,
        "shift-3": 4.0,
    }
    proposed_assignments = [
        {
            "shift_id": "shift-1",
            "employee_id": "emp-a",
            "assignment_payload": {"projected_ot_hours": 1.5},
        },
        {
            "shift_id": "shift-2",
            "employee_id": "emp-b",
            "assignment_payload": {"labor_projection": {"projected_ot_hours": 0.5}},
        },
    ]
    actual_assignments = [
        {"assignment_id": "a1", "shift_id": "shift-1", "employee_id": "emp-a", "status": "completed"},
        {"assignment_id": "a2", "shift_id": "shift-2", "employee_id": "emp-c", "status": "no_show"},
        {"assignment_id": "a3", "shift_id": "shift-3", "employee_id": "emp-d", "status": "assigned"},
    ]

    metrics = schedule_replay.calculate_replay_metrics(
        proposed_assignments=proposed_assignments,
        actual_assignments=actual_assignments,
        shift_duration_hours_by_shift_id=shift_hours,
    )

    assert metrics["assignment_match_rate"] == 0.3333
    assert metrics["matched_assignment_count"] == 1
    assert metrics["attendance_outcomes_on_proposed_assignments"]["completed"] == 1
    assert metrics["attendance_outcomes_on_proposed_assignments"]["reassigned_elsewhere"] == 1
    assert metrics["attendance_outcomes_on_proposed_assignments"]["unfilled"] == 1
    assert metrics["uncovered_shift_count"] == 1
    assert metrics["operator_override_delta"]["override_count"] == 2
    assert metrics["overtime_exposure"]["projected_ot_hours"] == 2.0
    assert metrics["fairness_spread"]["proposed"]["spread_hours"] == 2.0
    assert metrics["fairness_spread"]["actual"]["spread_hours"] == 4.0


def test_build_shift_duration_hours_map_reads_shift_payload_rows():
    duration_map = schedule_replay.build_shift_duration_hours_map(
        {
            "shifts": [
                {
                    "shift_id": "shift-1",
                    "starts_at": "2026-04-18T16:00:00+00:00",
                    "ends_at": "2026-04-19T00:00:00+00:00",
                },
                {
                    "shift_id": "shift-2",
                    "starts_at": "2026-04-19T16:00:00+00:00",
                    "ends_at": "2026-04-19T20:00:00+00:00",
                },
            ]
        }
    )

    assert duration_map == {"shift-1": 8.0, "shift-2": 4.0}


class _FakeSession:
    def __init__(self, schedule_run: ScheduleRun):
        self.schedule_run = schedule_run
        self.added: list[object] = []
        self.flush_count = 0

    def add(self, instance):
        self.added.append(instance)

    async def flush(self):
        self.flush_count += 1


@pytest.mark.asyncio
async def test_create_replay_run_persists_metrics_and_hashes(monkeypatch):
    schedule_run = ScheduleRun(
        id=uuid4(),
        business_id=uuid4(),
        location_id=uuid4(),
        planning_window_start=datetime(2026, 4, 18, 0, 0, tzinfo=timezone.utc),
        planning_window_end=datetime(2026, 4, 25, 0, 0, tzinfo=timezone.utc),
        run_type=ScheduleRunType.draft_generate,
        status=ScheduleRunStatus.completed,
        input_snapshot_hash="sha256:target",
    )
    shift_id = uuid4()
    employee_id = uuid4()
    schedule_run.inputs = ScheduleRunInput(
        schedule_run_id=schedule_run.id,
        shift_payload={
            "shifts": [
                {
                    "shift_id": str(shift_id),
                    "starts_at": "2026-04-18T16:00:00+00:00",
                    "ends_at": "2026-04-19T00:00:00+00:00",
                }
            ]
        },
        fixed_shift_payload={"shifts": []},
        generated_demand_payload={"proposed_shifts": [], "metadata": {}},
    )
    schedule_run.assignments = [
        ScheduleRunAssignment(
            schedule_run_id=schedule_run.id,
            decision_rank=1,
            decision_score=Decimal("95.0"),
            assignment_payload={"projected_ot_hours": 0.5},
        )
    ]
    schedule_run.assignments[0].shift_id = shift_id
    schedule_run.assignments[0].employee_id = employee_id

    session = _FakeSession(schedule_run)

    async def fake_load_schedule_run(_session, schedule_run_id):
        assert schedule_run_id == schedule_run.id
        return schedule_run

    async def fake_actual_payload(*_args, **_kwargs):
        return {
            "generated_at": datetime(2026, 4, 26, 0, 0, tzinfo=timezone.utc).isoformat(),
            "shifts": [
                {
                    "shift_id": str(schedule_run.assignments[0].shift_id),
                    "starts_at": "2026-04-18T16:00:00+00:00",
                    "ends_at": "2026-04-19T00:00:00+00:00",
                }
            ],
            "assignments": [
                {
                    "assignment_id": "actual-1",
                    "shift_id": str(schedule_run.assignments[0].shift_id),
                    "employee_id": str(schedule_run.assignments[0].employee_id),
                    "status": "completed",
                }
            ],
        }

    monkeypatch.setattr(schedule_replay, "_load_schedule_run", fake_load_schedule_run)
    monkeypatch.setattr(schedule_replay, "load_actual_schedule_payload", fake_actual_payload)

    replay_run = await schedule_replay.create_replay_run(
        session,
        schedule_run_id=schedule_run.id,
        replay_metadata={"mode": "shadow"},
    )

    assert replay_run.schedule_run_id == schedule_run.id
    assert replay_run.target_snapshot_hash == "sha256:target"
    assert replay_run.metrics_payload["assignment_match_rate"] == 1.0
    assert replay_run.actual_snapshot_hash.startswith("sha256:")
    assert replay_run.replay_metadata["mode"] == "shadow"
    assert session.added[-1] is replay_run
    assert session.flush_count == 1
