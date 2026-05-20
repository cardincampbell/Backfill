from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.business import Location
from app.models.common import ShiftStatus
from app.models.scheduling import Shift
from app.models.workforce import Employee
from app.services import labor_rules


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        class _ScalarResult:
            def __init__(self, values):
                self._values = values

            def all(self):
                return list(self._values)

        return _ScalarResult(self._values)

    def all(self):
        return list(self._values)


class FakeSession:
    def __init__(self):
        self.execute_queue: list[list[object]] = []

    async def execute(self, _query):
        return _ExecuteResult(self.execute_queue.pop(0) if self.execute_queue else [])

    async def get(self, *_args, **_kwargs):
        return None


def _profile(
    *,
    code: str,
    jurisdiction_code: str,
    overtime_mode: str,
    daily: float | None = None,
    weekly: float | None = 40.0,
    dt: float | None = None,
    consecutive: float | None = None,
    rules_json: dict[str, object] | None = None,
) -> labor_rules.LaborRuleProfileSnapshot:
    return labor_rules.LaborRuleProfileSnapshot(
        profile_id=uuid4(),
        code=code,
        jurisdiction_code=jurisdiction_code,
        display_name=code.replace("_", " ").title(),
        overtime_mode=overtime_mode,
        daily_ot_threshold_hours=daily,
        weekly_ot_threshold_hours=weekly,
        double_time_threshold_hours=dt,
        consecutive_hours_threshold_hours=consecutive,
        industry_profile_code=None,
        rules_json=rules_json or {"workweek_start_day_local": "monday", "workweek_start_time_local": "00:00"},
        effective_start_date=None,
        effective_end_date=None,
        source_urls=(),
        source_version="seed",
        source_hash="seed",
        version_id=uuid4(),
        version_no=1,
        payload_hash="sha256:test",
        payload_json={},
    )


def _shift(*, starts_at: datetime, ends_at: datetime) -> Shift:
    shift = Shift(
        id=uuid4(),
        business_id=uuid4(),
        location_id=uuid4(),
        role_id=uuid4(),
        timezone="America/Los_Angeles",
        starts_at=starts_at,
        ends_at=ends_at,
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
    )
    shift.location = Location(
        id=shift.location_id,
        business_id=shift.business_id,
        name="Downtown",
        display_name="Downtown",
        slug="downtown",
        region="CA",
        country_code="US",
        timezone="America/Los_Angeles",
        settings={},
    )
    return shift


def _interval(start_at: datetime, end_at: datetime) -> labor_rules.CountedInterval:
    return labor_rules.CountedInterval(
        start_at=start_at,
        end_at=end_at,
        shift_id=uuid4(),
        assignment_status="completed",
    )


def test_resolve_jurisdiction_code_uses_country_and_region():
    location = Location(
        id=uuid4(),
        business_id=uuid4(),
        name="Store",
        display_name="Store",
        slug="store",
        region="ca",
        country_code="us",
        timezone="America/Los_Angeles",
        settings={},
    )

    assert labor_rules.resolve_jurisdiction_code(location) == "US-CA"


def test_evaluate_overtime_projection_weekly_only_applies_weekly_threshold():
    profile = _profile(
        code="us_flsa_general",
        jurisdiction_code="US",
        overtime_mode="weekly_only",
        weekly=40.0,
    )
    now = datetime(2026, 4, 17, 18, 0, tzinfo=timezone.utc)
    shift = _shift(
        starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 19, 0, 0, tzinfo=timezone.utc),
    )
    projection = labor_rules.evaluate_overtime_projection(
        profile,
        candidate_shift=shift,
        counted_intervals=(
            _interval(datetime(2026, 4, 14, 16, 0, tzinfo=timezone.utc), datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 15, 16, 0, tzinfo=timezone.utc), datetime(2026, 4, 16, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 16, 16, 0, tzinfo=timezone.utc), datetime(2026, 4, 17, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 17, 4, 0, tzinfo=timezone.utc), datetime(2026, 4, 17, 13, 0, tzinfo=timezone.utc)),
        ),
        reference_time=now,
    )

    assert projection["status"] == "elevated"
    assert projection["projected_ot_hours"] == 4.0
    assert projection["projected_dt_hours"] == 0.0
    assert projection["reason_codes"] == ["weekly_ot_triggered"]


def test_evaluate_overtime_projection_california_daily_and_double_time():
    profile = _profile(
        code="us_ca_general_nonexempt",
        jurisdiction_code="US-CA",
        overtime_mode="daily_8_plus_weekly_plus_7th_day",
        daily=8.0,
        weekly=40.0,
        dt=12.0,
    )
    now = datetime(2026, 4, 17, 18, 0, tzinfo=timezone.utc)
    shift = _shift(
        starts_at=datetime(2026, 4, 17, 19, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 18, 3, 0, tzinfo=timezone.utc),
    )
    projection = labor_rules.evaluate_overtime_projection(
        profile,
        candidate_shift=shift,
        counted_intervals=(
            _interval(datetime(2026, 4, 17, 13, 0, tzinfo=timezone.utc), datetime(2026, 4, 17, 19, 0, tzinfo=timezone.utc)),
        ),
        reference_time=now,
    )

    assert projection["status"] == "high"
    assert projection["projected_ot_hours"] == 4.0
    assert projection["projected_dt_hours"] == 2.0
    assert "daily_ot_triggered" in projection["reason_codes"]
    assert "double_time_triggered" in projection["reason_codes"]


def test_max_consecutive_work_days_defaults_for_day_of_rest_ruleset():
    profile = _profile(
        code="us_ca_general_nonexempt",
        jurisdiction_code="US-CA",
        overtime_mode="daily_8_plus_weekly_plus_7th_day",
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "day_of_rest_ruleset": "ca_v1",
        },
    )

    assert labor_rules.max_consecutive_work_days(profile) == 6


def test_max_consecutive_work_days_prefers_explicit_profile_override():
    profile = _profile(
        code="custom_profile",
        jurisdiction_code="US-CA",
        overtime_mode="weekly_only",
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "max_consecutive_work_days": 4,
        },
    )

    assert labor_rules.max_consecutive_work_days(profile) == 4


def test_effective_max_consecutive_work_days_prefers_stricter_policy_override():
    profile = _profile(
        code="custom_profile",
        jurisdiction_code="US-CA",
        overtime_mode="weekly_only",
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
        },
    )

    assert (
        labor_rules.effective_max_consecutive_work_days(
            profile,
            compliance_settings={"max_consecutive_work_days": 6},
        )
        == 6
    )


def test_required_rest_days_per_workweek_defaults_when_enabled():
    profile = _profile(
        code="custom_profile",
        jurisdiction_code="US-CA",
        overtime_mode="weekly_only",
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "day_of_rest_workweek_required": True,
        },
    )

    assert labor_rules.required_rest_days_per_workweek(profile) == 1


def test_required_rest_days_per_workweek_prefers_explicit_profile_override():
    profile = _profile(
        code="custom_profile",
        jurisdiction_code="US-CA",
        overtime_mode="weekly_only",
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "required_rest_days_per_workweek": 2,
        },
    )

    assert labor_rules.required_rest_days_per_workweek(profile) == 2


def test_california_seed_profile_defaults_enable_break_and_rest_day_rules():
    profile = _profile(
        code="us_ca_general_nonexempt",
        jurisdiction_code="US-CA",
        overtime_mode="daily_8_plus_weekly_plus_7th_day",
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "meal_break_ruleset": "ca_v1",
            "rest_break_ruleset": "ca_v1",
            "day_of_rest_ruleset": "ca_v1",
            "day_of_rest_workweek_required": True,
        },
    )

    assert labor_rules.max_consecutive_work_days(profile) == 6
    assert labor_rules.required_rest_days_per_workweek(profile) == 1


@pytest.mark.asyncio
async def test_build_hours_snapshots_deduplicates_overlaps_and_clips_in_progress():
    employee = Employee(id=uuid4(), business_id=uuid4(), full_name="Worker")
    now = datetime(2026, 4, 17, 18, 0, tzinfo=timezone.utc)
    shift = _shift(
        starts_at=datetime(2026, 4, 17, 20, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 18, 0, 0, tzinfo=timezone.utc),
    )
    profile = _profile(
        code="us_ca_general_nonexempt",
        jurisdiction_code="US-CA",
        overtime_mode="daily_8_plus_weekly_plus_7th_day",
        daily=8.0,
        weekly=40.0,
        dt=12.0,
    )
    session = FakeSession()
    session.execute_queue = [
        [
            (
                employee.id,
                uuid4(),
                "assigned",
                datetime(2026, 4, 17, 10, 0, tzinfo=timezone.utc),
                datetime(2026, 4, 17, 20, 0, tzinfo=timezone.utc),
                "in_progress",
            ),
            (
                employee.id,
                uuid4(),
                "completed",
                datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
                datetime(2026, 4, 17, 16, 0, tzinfo=timezone.utc),
                "completed",
            ),
        ]
    ]

    snapshots = await labor_rules.build_hours_snapshots(
        session,
        employees=[employee],
        shift=shift,
        profile=profile,
        now=now,
    )

    snapshot = snapshots[employee.id]
    assert snapshot.gross_hours_by_window["workday"] == 8.0
    assert snapshot.gross_hours_by_window["workweek"] == 8.0


@pytest.mark.asyncio
async def test_runtime_resolved_profile_prefers_seeded_hospitality_profile_for_matching_location(monkeypatch):
    location = Location(
        id=uuid4(),
        business_id=uuid4(),
        name="Hotel",
        display_name="Hotel",
        slug="hotel",
        region="NY",
        country_code="US",
        timezone="America/New_York",
        settings={"labor_industry_profile_code": "hospitality"},
    )
    generic = _profile(
        code="us_flsa_general",
        jurisdiction_code="US",
        overtime_mode="weekly_only",
    )
    hospitality = _profile(
        code="us_ny_hospitality_nonexempt",
        jurisdiction_code="US-NY",
        overtime_mode="weekly_only",
        rules_json={
            "workweek_start_day_local": "sunday",
            "workweek_start_time_local": "00:00",
            "spread_of_hours_ruleset": "ny_v1",
            "day_of_rest_workweek_required": True,
        },
    )
    object.__setattr__(hospitality, "industry_profile_code", "hospitality")

    async def fake_existing(*args, **kwargs):
        return None

    async def fake_profiles(*args, **kwargs):
        return [generic, hospitality]

    monkeypatch.setattr(labor_rules, "load_authoritative_location_resolution", fake_existing)
    monkeypatch.setattr(labor_rules, "active_profiles_for_jurisdiction", fake_profiles)

    resolved = await labor_rules.runtime_resolved_profile(
        None,  # type: ignore[arg-type]
        location=location,
    )

    assert resolved is not None
    assert resolved.code == "us_ny_hospitality_nonexempt"
