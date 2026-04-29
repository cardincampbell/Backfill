from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.common import (
    ComplianceOverrideArtifactStatus,
    ComplianceOverrideArtifactType,
    CoverageAttemptStatus,
    ShiftStatus,
)
from app.models.business import Location
from app.models.compliance import ComplianceOverrideArtifact
from app.models.scheduling import Shift
from app.models.workforce import Employee
from app.schemas.coverage import CoverageCandidatePreview
from app.services import labor_rules, runtime_projections


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)

    def scalars(self):
        values = self._values

        class _ScalarResult:
            def __init__(self, scalar_values):
                self._scalar_values = scalar_values

            def all(self):
                normalized = []
                for value in self._scalar_values:
                    if isinstance(value, tuple):
                        normalized.append(value[0])
                    else:
                        normalized.append(value)
                return normalized

        return _ScalarResult(values)


class FakeProjectionSession:
    def __init__(self):
        self.execute_queue: list[list[object]] = []

    async def execute(self, _query):
        values = self.execute_queue.pop(0) if self.execute_queue else []
        return _ExecuteResult(values)


def _make_profile(*, code: str = "us_ca_general_nonexempt") -> labor_rules.LaborRuleProfileSnapshot:
    return labor_rules.LaborRuleProfileSnapshot(
        profile_id=uuid4(),
        code=code,
        jurisdiction_code="US-CA",
        display_name="California General Nonexempt",
        overtime_mode="daily_8_plus_weekly_plus_7th_day",
        daily_ot_threshold_hours=8.0,
        weekly_ot_threshold_hours=40.0,
        double_time_threshold_hours=12.0,
        consecutive_hours_threshold_hours=None,
        industry_profile_code=None,
        rules_json={"workweek_start_day_local": "monday", "workweek_start_time_local": "00:00"},
        effective_start_date=None,
        effective_end_date=None,
        source_urls=(),
        source_version="seed_v1",
        source_hash="seed",
        version_id=uuid4(),
        version_no=1,
        payload_hash="sha256:test",
        payload_json={},
    )


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
            scoring_factors={
                "score_snapshot": {"status": "fresh"},
                "policy_version": "coverage_policy_v1",
                "snapshot_generated_at": "2026-04-17T12:00:00+00:00",
                "inputs_version": "runtime_projection_inputs_v1",
                "compliance": {"status": "warning"},
            },
            availability_snapshot={},
        ),
        CoverageCandidatePreview(
            employee_id=uuid4(),
            employee_name="Refreshed",
            phone_e164="+15555550101",
            primary_location_id=uuid4(),
            rank=2,
            score=80.0,
            scoring_factors={"score_snapshot": {"status": "refreshed"}, "compliance": {"status": "block"}},
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
    assert metadata["compliance"]["resolved"] == 2
    assert metadata["compliance"]["warning"] == 1
    assert metadata["compliance"]["blocked"] == 1
    assert metadata["policy"]["policy_version"] == "coverage_policy_v1"
    assert metadata["policy"]["inputs_version"] == "runtime_projection_inputs_v1"


@pytest.mark.asyncio
async def test_monitor_runtime_projection_freshness_blocks_when_stale_ratio_is_too_high():
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    session = FakeProjectionSession()
    session.execute_queue = [
        [(business_id,)],
        [
            (business_id, {"updated_at": (now - timedelta(minutes=2)).isoformat()}),
            (business_id, {"updated_at": (now - timedelta(minutes=45)).isoformat()}),
            (business_id, {}),
            (business_id, {"updated_at": (now - timedelta(minutes=50)).isoformat()}),
            (business_id, {}),
        ],
    ]

    result = await runtime_projections.monitor_runtime_projection_freshness(
        session,
        now=now,
        business_limit=10,
    )

    assert result["status"] == "blocked"
    assert result["blocked_reason"] == "runtime_projections_too_stale"
    assert result["blocked_business_count"] == 1
    assert result["blocked_business_ids"] == [str(business_id)]
    assert result["fresh_employee_count"] == 1
    assert result["stale_employee_count"] == 2
    assert result["missing_employee_count"] == 2


@pytest.mark.asyncio
async def test_monitor_runtime_projection_freshness_uses_scalar_business_ids():
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    session = FakeProjectionSession()
    session.execute_queue = [
        [(business_id,)],
        [
            (business_id, {"updated_at": (now - timedelta(minutes=2)).isoformat()}),
        ],
    ]

    result = await runtime_projections.monitor_runtime_projection_freshness(
        session,
        now=now,
        business_limit=10,
    )

    assert result["status"] == "ready"
    assert result["monitored_business_count"] == 1
    assert result["fresh_employee_count"] == 1


@pytest.mark.asyncio
async def test_build_outreach_guardrail_snapshots_marks_hard_cooldown_and_burden():
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    employee = Employee(
        id=uuid4(),
        business_id=business_id,
        full_name="Contacted Recently",
    )
    shift = Shift(
        id=uuid4(),
        business_id=business_id,
        location_id=uuid4(),
        role_id=uuid4(),
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
    )
    session = FakeProjectionSession()
    session.execute_queue = [
        [
            (
                employee.id,
                now - timedelta(seconds=30),
                CoverageAttemptStatus.delivered,
            ),
            (
                employee.id,
                now - timedelta(hours=12),
                CoverageAttemptStatus.accepted,
            ),
        ],
        [
            (
                employee.id,
                now - timedelta(days=1),
                now + timedelta(hours=3),
            )
        ],
    ]

    snapshots = await runtime_projections.build_outreach_guardrail_snapshots(
        session,
        [employee],
        shift=shift,
        now=now,
    )

    guardrails = snapshots[employee.id]
    assert guardrails["contact_cooldown"]["status"] == "hard_cooldown"
    assert guardrails["contact_cooldown"]["multiplier"] == 0.0
    assert guardrails["recent_burden"]["recent_attempt_count"] == 2
    assert guardrails["recent_burden"]["recent_accept_count"] == 1
    assert guardrails["hard_excluded"] is True


def test_contact_cooldown_snapshot_uses_configured_hard_window(monkeypatch):
    now = datetime.now(timezone.utc)
    last_contact_at = now - timedelta(minutes=2)

    monkeypatch.setattr(
        runtime_projections,
        "_contact_cooldown_hard_window",
        lambda: timedelta(minutes=3),
    )
    monkeypatch.setattr(
        runtime_projections,
        "_contact_cooldown_soft_window",
        lambda: timedelta(hours=2),
    )

    snapshot = runtime_projections._contact_cooldown_snapshot(
        last_contact_at=last_contact_at,
        now=now,
    )

    assert snapshot["status"] == "hard_cooldown"
    assert snapshot["multiplier"] == 0.0


@pytest.mark.asyncio
async def test_build_outreach_guardrail_snapshots_downranks_for_overtime_risk(monkeypatch):
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    employee = Employee(
        id=uuid4(),
        business_id=business_id,
        full_name="Heavy Load",
    )
    shift = Shift(
        id=uuid4(),
        business_id=business_id,
        location_id=uuid4(),
        role_id=uuid4(),
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
    )
    shift.location = Location(
        id=shift.location_id,
        business_id=business_id,
        name="Downtown",
        display_name="Downtown",
        slug="downtown",
        region="CA",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
    )
    session = FakeProjectionSession()
    session.execute_queue = [
        [],
        [
            (employee.id, now - timedelta(days=2), now - timedelta(days=2) + timedelta(hours=18)),
            (employee.id, now - timedelta(days=1), now - timedelta(days=1) + timedelta(hours=16)),
        ],
        [
            (
                employee.id,
                uuid4(),
                "completed",
                now - timedelta(days=2),
                now - timedelta(days=2) + timedelta(hours=18),
                "completed",
            ),
            (
                employee.id,
                uuid4(),
                "completed",
                now - timedelta(days=1),
                now - timedelta(days=1) + timedelta(hours=16),
                "completed",
            ),
        ],
    ]
    async def fake_profile_loader(*args, **kwargs):
        return _make_profile()

    monkeypatch.setattr(runtime_projections, "_load_labor_rule_profile_for_shift", fake_profile_loader)
    monkeypatch.setattr(labor_rules, "settings", SimpleNamespace(labor_rules_mode="primary"))

    snapshots = await runtime_projections.build_outreach_guardrail_snapshots(
        session,
        [employee],
        shift=shift,
        now=now,
    )

    guardrails = snapshots[employee.id]
    assert guardrails["contact_cooldown"]["status"] == "clear"
    assert guardrails["overtime_risk"]["status"] == "high"
    assert guardrails["overtime_risk"]["multiplier"] < 1.0
    assert guardrails["overtime_projection"]["profile_code"] == "us_ca_general_nonexempt"
    assert guardrails["overall_multiplier"] < 1.0


@pytest.mark.asyncio
async def test_build_outreach_guardrail_snapshots_blocks_minimum_rest_violation(monkeypatch):
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    employee = Employee(
        id=uuid4(),
        business_id=business_id,
        full_name="Clopening Risk",
    )
    shift = Shift(
        id=uuid4(),
        business_id=business_id,
        location_id=uuid4(),
        role_id=uuid4(),
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=8),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
    )
    shift.location = Location(
        id=shift.location_id,
        business_id=business_id,
        name="Downtown",
        display_name="Downtown",
        slug="downtown",
        region="NY",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
    )
    session = FakeProjectionSession()
    session.execute_queue = [
        [],
        [],
        [
            (
                employee.id,
                uuid4(),
                "completed",
                now - timedelta(hours=6),
                now + timedelta(hours=1),
                "completed",
            ),
        ],
    ]

    profile = _make_profile(code="us_nyc_fast_food")
    profile = labor_rules.LaborRuleProfileSnapshot(
        profile_id=profile.profile_id,
        code=profile.code,
        jurisdiction_code=profile.jurisdiction_code,
        display_name=profile.display_name,
        overtime_mode=profile.overtime_mode,
        daily_ot_threshold_hours=profile.daily_ot_threshold_hours,
        weekly_ot_threshold_hours=profile.weekly_ot_threshold_hours,
        double_time_threshold_hours=profile.double_time_threshold_hours,
        consecutive_hours_threshold_hours=profile.consecutive_hours_threshold_hours,
        industry_profile_code=profile.industry_profile_code,
        rules_json={
            **profile.rules_json,
            "minimum_rest_hours": 11,
            "written_consent_allowed": True,
            "clopening_premium_cents": 10000,
            "rest_window_rule_code": "clopening_restricted",
        },
        effective_start_date=profile.effective_start_date,
        effective_end_date=profile.effective_end_date,
        source_urls=profile.source_urls,
        source_version=profile.source_version,
        source_hash=profile.source_hash,
        version_id=profile.version_id,
        version_no=profile.version_no,
        payload_hash=profile.payload_hash,
        payload_json=profile.payload_json,
    )

    async def fake_profile_loader(*_args, **_kwargs):
        return profile

    monkeypatch.setattr(runtime_projections, "_load_labor_rule_profile_for_shift", fake_profile_loader)

    snapshots = await runtime_projections.build_outreach_guardrail_snapshots(
        session,
        [employee],
        shift=shift,
        now=now,
    )

    guardrails = snapshots[employee.id]
    assert guardrails["hard_excluded"] is True
    assert guardrails["overall_multiplier"] == 0.0
    assert guardrails["compliance"]["status"] == "block"
    assert guardrails["compliance"]["blocking_rule_codes"] == ["clopening_restricted"]


@pytest.mark.asyncio
async def test_build_outreach_guardrail_snapshots_applies_written_consent_override(monkeypatch):
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    employee = Employee(
        id=uuid4(),
        business_id=business_id,
        full_name="Clopening Override",
    )
    shift = Shift(
        id=uuid4(),
        business_id=business_id,
        location_id=uuid4(),
        role_id=uuid4(),
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=8),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
    )
    shift.location = Location(
        id=shift.location_id,
        business_id=business_id,
        name="Downtown",
        display_name="Downtown",
        slug="downtown",
        region="NY",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
    )
    session = FakeProjectionSession()
    session.execute_queue = [
        [],
        [],
        [
            (
                employee.id,
                uuid4(),
                "completed",
                now - timedelta(hours=6),
                now + timedelta(hours=1),
                "completed",
            ),
        ],
    ]

    profile = _make_profile(code="us_nyc_fast_food")
    profile = labor_rules.LaborRuleProfileSnapshot(
        profile_id=profile.profile_id,
        code=profile.code,
        jurisdiction_code=profile.jurisdiction_code,
        display_name=profile.display_name,
        overtime_mode=profile.overtime_mode,
        daily_ot_threshold_hours=profile.daily_ot_threshold_hours,
        weekly_ot_threshold_hours=profile.weekly_ot_threshold_hours,
        double_time_threshold_hours=profile.double_time_threshold_hours,
        consecutive_hours_threshold_hours=profile.consecutive_hours_threshold_hours,
        industry_profile_code=profile.industry_profile_code,
        rules_json={
            **profile.rules_json,
            "minimum_rest_hours": 11,
            "written_consent_allowed": True,
            "clopening_premium_cents": 10000,
            "rest_window_rule_code": "clopening_restricted",
        },
        effective_start_date=profile.effective_start_date,
        effective_end_date=profile.effective_end_date,
        source_urls=profile.source_urls,
        source_version=profile.source_version,
        source_hash=profile.source_hash,
        version_id=profile.version_id,
        version_no=profile.version_no,
        payload_hash=profile.payload_hash,
        payload_json=profile.payload_json,
    )
    artifact = ComplianceOverrideArtifact(
        id=uuid4(),
        business_id=business_id,
        location_id=shift.location_id,
        shift_id=shift.id,
        employee_id=employee.id,
        rule_code="clopening_restricted",
        artifact_type=ComplianceOverrideArtifactType.written_consent,
        status=ComplianceOverrideArtifactStatus.approved,
        engine_version="deterministic_compliance_engine_v1",
        approved_at=now,
        expires_at=now + timedelta(hours=12),
        note="Written consent collected.",
        reason_codes=["minimum_rest_window_violation"],
        artifact_payload={},
    )

    async def fake_profile_loader(*_args, **_kwargs):
        return profile

    async def fake_active_artifacts(*_args, **_kwargs):
        return {employee.id: [artifact]}

    monkeypatch.setattr(runtime_projections, "_load_labor_rule_profile_for_shift", fake_profile_loader)
    monkeypatch.setattr(
        runtime_projections.compliance_overrides,
        "active_artifacts_for_shift_employees",
        fake_active_artifacts,
    )

    snapshots = await runtime_projections.build_outreach_guardrail_snapshots(
        session,
        [employee],
        shift=shift,
        now=now,
    )

    guardrails = snapshots[employee.id]
    assert guardrails["hard_excluded"] is False
    assert guardrails["overall_multiplier"] > 0.0
    assert guardrails["compliance"]["status"] == "warning"
    assert guardrails["compliance"]["override_applied"] is True
    assert guardrails["compliance"]["override_artifact_id"] == str(artifact.id)


@pytest.mark.asyncio
async def test_build_outreach_guardrail_snapshots_ignores_failed_attempts_for_cooldown():
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    employee = Employee(
        id=uuid4(),
        business_id=business_id,
        full_name="System Failure Target",
    )
    shift = Shift(
        id=uuid4(),
        business_id=business_id,
        location_id=uuid4(),
        role_id=uuid4(),
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=6),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
    )
    session = FakeProjectionSession()
    session.execute_queue = [
        [
            (
                employee.id,
                now - timedelta(minutes=5),
                CoverageAttemptStatus.failed,
            ),
            (
                employee.id,
                now - timedelta(hours=12),
                CoverageAttemptStatus.accepted,
            ),
        ],
        [],
    ]

    snapshots = await runtime_projections.build_outreach_guardrail_snapshots(
        session,
        [employee],
        shift=shift,
        now=now,
    )

    guardrails = snapshots[employee.id]
    assert guardrails["contact_cooldown"]["status"] == "clear"
    assert guardrails["contact_cooldown"]["multiplier"] == 1.0
    assert guardrails["recent_burden"]["recent_attempt_count"] == 1
    assert guardrails["recent_burden"]["recent_accept_count"] == 1
    assert guardrails["hard_excluded"] is False
