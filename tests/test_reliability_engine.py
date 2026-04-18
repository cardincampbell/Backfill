from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.workforce import Employee
from app.schemas.auto_scheduler import ReliabilityEmployeeSnapshotPayload
from app.services import reliability_engine


def test_build_employee_reliability_snapshot_applies_cold_start_shrinkage():
    employee_id = uuid4()
    business_id = uuid4()
    snapshot = reliability_engine.build_employee_reliability_snapshot(
        employee_id=employee_id,
        business_id=business_id,
        snapshot_at=datetime(2026, 4, 18, 18, 0, tzinfo=timezone.utc),
        baseline_score=0.7,
        events=[
            {"event_type": "worked_shift", "event_payload": {"late_minutes": 2}},
            {"event_type": "late_arrival", "event_payload": {"late_minutes": 20}},
            {"event_type": "accepted_offer", "event_payload": {}},
            {"event_type": "accepted_then_cancelled", "event_payload": {}},
            {"event_type": "response_time_recorded", "event_payload": {"response_time_seconds": 300}},
            {"event_type": "no_response_to_offer", "event_payload": {}},
        ],
    )

    assert snapshot.employee_id == employee_id
    assert snapshot.sample_size == 6
    assert 0.0 < snapshot.confidence < 1.0
    assert snapshot.attendance.sample_size == 1
    assert snapshot.attendance.score > 0.7
    assert snapshot.punctuality.sample_size == 2
    assert snapshot.punctuality.score < 0.8
    assert snapshot.commitment.sample_size == 2
    assert 0.0 < snapshot.commitment.score < 0.8
    assert snapshot.response_behavior.sample_size == 2
    assert snapshot.response_behavior.metrics["avg_response_time_seconds"] == 300
    assert snapshot.coverage_reliability.sample_size == 3
    assert 0.0 < snapshot.overall_score < 1.0


def test_build_reliability_snapshot_payload_hash_is_stable():
    generated_at = datetime(2026, 4, 18, 20, 0, tzinfo=timezone.utc)
    snapshot_one = ReliabilityEmployeeSnapshotPayload(
        employee_id=uuid4(),
        overall_score=0.75,
        confidence=0.5,
        sample_size=3,
        attendance={"score": 0.8, "confidence": 0.5, "sample_size": 1, "metrics": {}},
        punctuality={"score": 0.7, "confidence": 0.5, "sample_size": 1, "metrics": {}},
        commitment={"score": 0.7, "confidence": 0.5, "sample_size": 1, "metrics": {}},
        response_behavior={"score": 0.75, "confidence": 0.5, "sample_size": 1, "metrics": {}},
        coverage_reliability={"score": 0.8, "confidence": 0.5, "sample_size": 1, "metrics": {}},
        metadata={},
    )
    snapshot_two = snapshot_one.model_copy(deep=True)

    payload_one = reliability_engine.build_reliability_snapshot_payload(
        employee_snapshots=[snapshot_one, snapshot_two],
        generated_at=generated_at,
        metadata={"business_id": str(uuid4())},
    )
    payload_two = reliability_engine.build_reliability_snapshot_payload(
        employee_snapshots=[snapshot_one, snapshot_two],
        generated_at=generated_at,
        metadata={"business_id": payload_one.metadata["business_id"]},
    )

    assert payload_one.snapshot_hash == payload_two.snapshot_hash
    assert payload_one.snapshot_version == "v1"


class _FakeSession:
    def __init__(self, employee: Employee):
        self.employee = employee
        self.added: list[object] = []
        self.flush_count = 0

    async def get(self, model, employee_id):
        assert model is Employee
        if employee_id == self.employee.id:
            return self.employee
        return None

    def add(self, instance):
        self.added.append(instance)

    async def flush(self):
        self.flush_count += 1


@pytest.mark.asyncio
async def test_refresh_employee_reliability_snapshot_persists_snapshot_and_updates_legacy_fields(monkeypatch):
    employee = Employee(id=uuid4(), business_id=uuid4(), full_name="Jamie")
    session = _FakeSession(employee)
    snapshot_at = datetime(2026, 4, 18, 21, 0, tzinfo=timezone.utc)

    async def fake_baseline(*_args, **_kwargs):
        return 0.7

    async def fake_load_events(*_args, **_kwargs):
        return [
            {"event_type": "worked_shift", "event_payload": {"late_minutes": 0}},
            {"event_type": "response_time_recorded", "event_payload": {"response_time_seconds": 120}},
        ]

    monkeypatch.setattr(reliability_engine, "_business_baseline_score", fake_baseline)
    monkeypatch.setattr(reliability_engine, "_load_employee_reliability_events", fake_load_events)

    snapshot = await reliability_engine.refresh_employee_reliability_snapshot(
        session,
        employee.id,
        snapshot_at=snapshot_at,
    )

    assert snapshot is not None
    assert snapshot.employee_id == employee.id
    assert employee.reliability_score > 0.7
    assert employee.avg_response_time_seconds == 120
    assert employee.response_profile["reliability_snapshot_version"] == "v1"
    assert session.flush_count == 1
    assert session.added[-1] is snapshot


@pytest.mark.asyncio
async def test_build_pinned_reliability_snapshot_payload_uses_refreshed_snapshot_rows(monkeypatch):
    business_id = uuid4()
    employee_id = uuid4()
    generated_at = datetime(2026, 4, 18, 22, 0, tzinfo=timezone.utc)

    class _SnapshotRow:
        def __init__(self, payload):
            self.snapshot_payload = payload

    async def fake_refresh(*_args, **_kwargs):
        return [
            _SnapshotRow(
                ReliabilityEmployeeSnapshotPayload(
                    employee_id=employee_id,
                    overall_score=0.82,
                    confidence=0.6,
                    sample_size=4,
                    attendance={"score": 0.9, "confidence": 0.6, "sample_size": 2, "metrics": {}},
                    punctuality={"score": 0.8, "confidence": 0.6, "sample_size": 1, "metrics": {}},
                    commitment={"score": 0.8, "confidence": 0.6, "sample_size": 1, "metrics": {}},
                    response_behavior={"score": 0.8, "confidence": 0.6, "sample_size": 1, "metrics": {}},
                    coverage_reliability={"score": 0.8, "confidence": 0.6, "sample_size": 1, "metrics": {}},
                    metadata={},
                ).model_dump(mode="json")
            )
        ]

    monkeypatch.setattr(
        reliability_engine,
        "refresh_business_reliability_snapshots",
        fake_refresh,
    )

    payload = await reliability_engine.build_pinned_reliability_snapshot_payload(
        object(),  # session is unused by the monkeypatched refresher
        business_id=business_id,
        employee_ids=[employee_id],
        generated_at=generated_at,
    )

    assert payload.generated_at == generated_at
    assert payload.snapshot_version == "v1"
    assert payload.metadata["business_id"] == str(business_id)
    assert payload.employees[0].employee_id == employee_id
