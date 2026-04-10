from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.workforce import Employee
from app.schemas.coverage import CoverageCandidatePreview
from app.services import runtime_projections


@pytest.mark.asyncio
async def test_refresh_employee_score_snapshots_refreshes_missing_and_stale_profiles(monkeypatch):
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    fresh_employee = Employee(
        id=uuid4(),
        business_id=business_id,
        full_name="Fresh Employee",
        response_profile={"updated_at": (now - timedelta(minutes=5)).isoformat()},
    )
    stale_employee = Employee(
        id=uuid4(),
        business_id=business_id,
        full_name="Stale Employee",
        response_profile={"updated_at": (now - timedelta(minutes=45)).isoformat()},
    )
    missing_employee = Employee(
        id=uuid4(),
        business_id=business_id,
        full_name="Missing Employee",
        response_profile={},
    )

    refreshed_ids: list[object] = []

    async def fake_refresh(_session, employee_id, *, now=None):
        refreshed_ids.append(employee_id)
        target = stale_employee if employee_id == stale_employee.id else missing_employee
        target.response_profile = {"updated_at": (now or datetime.now(timezone.utc)).isoformat()}
        return target

    monkeypatch.setattr(runtime_projections.delivery, "refresh_employee_reliability", fake_refresh)

    states = await runtime_projections.refresh_employee_score_snapshots(
        object(),
        [fresh_employee, stale_employee, missing_employee],
        now=now,
    )

    assert states[fresh_employee.id]["status"] == "fresh"
    assert states[stale_employee.id]["status"] == "refreshed"
    assert states[missing_employee.id]["status"] == "refreshed"
    assert refreshed_ids == [stale_employee.id, missing_employee.id]


def test_build_runtime_projection_metadata_summarizes_candidate_snapshot_statuses():
    candidates = [
        CoverageCandidatePreview(
            employee_id=uuid4(),
            employee_name="Fresh",
            phone_e164="+15555550100",
            primary_location_id=uuid4(),
            rank=1,
            score=90.0,
            scoring_factors={"score_snapshot": {"status": "fresh"}},
            availability_snapshot={},
        ),
        CoverageCandidatePreview(
            employee_id=uuid4(),
            employee_name="Refreshed",
            phone_e164="+15555550101",
            primary_location_id=uuid4(),
            rank=2,
            score=80.0,
            scoring_factors={"score_snapshot": {"status": "refreshed"}},
            availability_snapshot={},
        ),
        CoverageCandidatePreview(
            employee_id=uuid4(),
            employee_name="Unknown",
            phone_e164="+15555550102",
            primary_location_id=uuid4(),
            rank=3,
            score=70.0,
            scoring_factors={},
            availability_snapshot={},
        ),
    ]

    metadata = runtime_projections.build_runtime_projection_metadata(candidates)

    assert metadata["eligibility"]["mode"] == "live_authoring_fallback"
    assert metadata["availability"]["mode"] == "live_authoring_fallback"
    assert metadata["score_snapshots"]["candidate_count"] == 3
    assert metadata["score_snapshots"]["fresh"] == 1
    assert metadata["score_snapshots"]["refreshed"] == 1
    assert metadata["score_snapshots"]["unknown"] == 1
