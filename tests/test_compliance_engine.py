from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from app.models.business import Location
from app.models.common import ShiftBreakType, ShiftSegmentType, ShiftStatus
from app.models.scheduling import Shift, ShiftBreak, ShiftSegment
from app.services import compliance_engine, labor_rules


def _profile(*, rules_json: dict[str, object] | None = None) -> labor_rules.LaborRuleProfileSnapshot:
    return labor_rules.LaborRuleProfileSnapshot(
        profile_id=uuid4(),
        code="us_test_profile",
        jurisdiction_code="US-CA",
        display_name="Test Profile",
        overtime_mode="daily_8_plus_weekly_plus_7th_day",
        daily_ot_threshold_hours=8.0,
        weekly_ot_threshold_hours=40.0,
        double_time_threshold_hours=12.0,
        consecutive_hours_threshold_hours=None,
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
    shift.segments = []
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


def _apply_segments(shift: Shift, segments: list[dict[str, object]]) -> Shift:
    shift.segments = []
    for segment_index, segment_payload in enumerate(segments, start=1):
        segment = ShiftSegment(
            shift_id=shift.id,
            sequence_no=segment_index,
            segment_type=ShiftSegmentType.work,
            starts_at=segment_payload["starts_at"],
            ends_at=segment_payload["ends_at"],
            segment_metadata={},
        )
        segment.breaks = []
        for break_index, break_payload in enumerate(segment_payload.get("breaks") or [], start=1):
            segment.breaks.append(
                ShiftBreak(
                    shift_id=shift.id,
                    shift_segment_id=segment.id,
                    sequence_no=break_index,
                    break_type=break_payload["break_type"],
                    is_paid=break_payload["is_paid"],
                    starts_at=break_payload["starts_at"],
                    ends_at=break_payload["ends_at"],
                    notes=None,
                    break_metadata={},
                )
            )
        shift.segments.append(segment)
    return shift


def _interval(start_at: datetime, end_at: datetime) -> labor_rules.CountedInterval:
    return labor_rules.CountedInterval(
        start_at=start_at,
        end_at=end_at,
        shift_id=uuid4(),
        assignment_status="completed",
    )


def test_evaluate_shift_assignment_compliance_marks_overtime_as_warning_not_block():
    profile = _profile()
    shift = _shift(
        starts_at=datetime(2026, 4, 17, 19, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 18, 3, 0, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(
            _interval(datetime(2026, 4, 17, 13, 0, tzinfo=timezone.utc), datetime(2026, 4, 17, 19, 0, tzinfo=timezone.utc)),
        ),
        reference_time=datetime(2026, 4, 17, 18, 0, tzinfo=timezone.utc),
    )

    assert evaluation["status"] == "warning"
    assert evaluation["would_block"] is False
    assert evaluation["premium_rule_codes"] == ["overtime_projection"]
    assert evaluation["premium_total_cents"] == 0
    assert evaluation["premium_components"][0]["premium_type"] == "cost_multiplier"
    assert evaluation["shift_facts"]["scheduled_span_minutes"] == 480
    assert evaluation["shift_facts"]["net_payable_minutes"] == 480


def test_evaluate_shift_assignment_compliance_blocks_minimum_rest_window_violations():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "minimum_rest_hours": 11,
            "written_consent_allowed": True,
            "clopening_premium_cents": 10000,
            "rest_window_rule_code": "clopening_restricted",
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 18, 22, 0, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(
            _interval(datetime(2026, 4, 18, 5, 0, tzinfo=timezone.utc), datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc)),
        ),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert evaluation["status"] == "block"
    assert evaluation["would_block"] is True
    assert evaluation["blocking_rule_codes"] == ["clopening_restricted"]
    assert compliance_engine.coverage_multiplier_for_evaluation(evaluation) == 0.0
    assert evaluation["shift_facts"]["scheduled_span_minutes"] == 360
    assert evaluation["shift_facts"]["split_shift_detected"] is False


def test_evaluate_shift_assignment_compliance_blocks_missing_first_meal_for_structured_shift():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "meal_break_ruleset": "ca_v1",
            "meal_break_premium_cents": 2200,
        }
    )
    shift = _apply_segments(
        _shift(
            starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 18, 22, 30, tzinfo=timezone.utc),
        ),
        [
            {
                "starts_at": datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 4, 18, 22, 30, tzinfo=timezone.utc),
                "breaks": [],
            }
        ],
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert evaluation["status"] == "block"
    assert evaluation["would_block"] is True
    assert evaluation["blocking_rule_codes"] == ["meal_break_first_window"]
    assert evaluation["premium_total_cents"] == 2200
    assert evaluation["premium_components"][0]["rule_code"] == "meal_break_first_window"
    assert evaluation["premium_components"][0]["premium_cents"] == 2200


def test_evaluate_shift_assignment_compliance_accepts_structured_first_meal_break():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "meal_break_ruleset": "ca_v1",
        }
    )
    shift = _apply_segments(
        _shift(
            starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 18, 22, 30, tzinfo=timezone.utc),
        ),
        [
            {
                "starts_at": datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 4, 18, 22, 30, tzinfo=timezone.utc),
                "breaks": [
                    {
                        "break_type": ShiftBreakType.meal,
                        "is_paid": False,
                        "starts_at": datetime(2026, 4, 18, 20, 30, tzinfo=timezone.utc),
                        "ends_at": datetime(2026, 4, 18, 21, 0, tzinfo=timezone.utc),
                    }
                ],
            }
        ],
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert "meal_break_first_window" not in evaluation["blocking_rule_codes"]
    assert "meal_break_first_window" not in evaluation["warning_rule_codes"]


def test_evaluate_shift_assignment_compliance_warns_when_unstructured_meal_plan_is_missing():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "meal_break_ruleset": "ca_v1",
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 18, 22, 30, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert evaluation["status"] == "warning"
    assert evaluation["would_block"] is False
    assert "meal_break_first_window" in evaluation["warning_rule_codes"]


def test_evaluate_shift_assignment_compliance_blocks_missing_midday_meal_for_new_york_structured_shift():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "sunday",
            "workweek_start_time_local": "00:00",
            "meal_break_ruleset": "ny_non_factory_v1",
        }
    )
    shift = _apply_segments(
        _shift(
            starts_at=datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 5, 1, 21, 30, tzinfo=timezone.utc),
        ),
        [
            {
                "starts_at": datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 5, 1, 21, 30, tzinfo=timezone.utc),
                "breaks": [],
            }
        ],
    )
    shift.timezone = "America/New_York"
    shift.location.timezone = "America/New_York"

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
    )

    assert evaluation["blocking_rule_codes"] == ["meal_break_midday_window"]
    assert evaluation["status"] == "block"


def test_evaluate_shift_assignment_compliance_blocks_missing_evening_meal_for_new_york_long_day_shift():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "sunday",
            "workweek_start_time_local": "00:00",
            "meal_break_ruleset": "ny_non_factory_v1",
        }
    )
    shift = _apply_segments(
        _shift(
            starts_at=datetime(2026, 5, 1, 14, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 5, 2, 0, 0, tzinfo=timezone.utc),
        ),
        [
            {
                "starts_at": datetime(2026, 5, 1, 14, 0, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 5, 2, 0, 0, tzinfo=timezone.utc),
                "breaks": [
                    {
                        "break_type": ShiftBreakType.meal,
                        "is_paid": False,
                        "starts_at": datetime(2026, 5, 1, 16, 30, tzinfo=timezone.utc),
                        "ends_at": datetime(2026, 5, 1, 17, 0, tzinfo=timezone.utc),
                    }
                ],
            }
        ],
    )
    shift.timezone = "America/New_York"
    shift.location.timezone = "America/New_York"

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
    )

    assert "meal_break_evening_window" in evaluation["blocking_rule_codes"]


def test_evaluate_shift_assignment_compliance_accepts_midshift_meal_for_new_york_evening_shift():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "sunday",
            "workweek_start_time_local": "00:00",
            "meal_break_ruleset": "ny_non_factory_v1",
        }
    )
    shift = _apply_segments(
        _shift(
            starts_at=datetime(2026, 5, 2, 21, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 5, 3, 4, 30, tzinfo=timezone.utc),
        ),
        [
            {
                "starts_at": datetime(2026, 5, 2, 21, 0, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 5, 3, 4, 30, tzinfo=timezone.utc),
                "breaks": [
                    {
                        "break_type": ShiftBreakType.meal,
                        "is_paid": False,
                        "starts_at": datetime(2026, 5, 3, 0, 15, tzinfo=timezone.utc),
                        "ends_at": datetime(2026, 5, 3, 1, 0, tzinfo=timezone.utc),
                    }
                ],
            }
        ],
    )
    shift.timezone = "America/New_York"
    shift.location.timezone = "America/New_York"

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 5, 2, 18, 0, tzinfo=timezone.utc),
    )

    assert "meal_break_midshift_window" not in evaluation["blocking_rule_codes"]
    assert "meal_break_midshift_window" not in evaluation["warning_rule_codes"]


def test_evaluate_shift_assignment_compliance_uses_metadata_break_plan_when_rows_are_missing():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "meal_break_ruleset": "ca_v1",
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 18, 22, 30, tzinfo=timezone.utc),
    )
    shift.shift_metadata = {
        "planned_segments": [
            {
                "sequence_no": 1,
                "segment_type": "work",
                "starts_at": shift.starts_at.isoformat(),
                "ends_at": shift.ends_at.isoformat(),
                "segment_metadata": {"planned_by": "test"},
                "breaks": [
                    {
                        "sequence_no": 1,
                        "break_type": ShiftBreakType.meal.value,
                        "is_paid": False,
                        "starts_at": datetime(2026, 4, 18, 20, 30, tzinfo=timezone.utc).isoformat(),
                        "ends_at": datetime(2026, 4, 18, 21, 0, tzinfo=timezone.utc).isoformat(),
                        "notes": "planned_first_meal_break",
                        "break_metadata": {"planned_by": "test"},
                    }
                ],
            }
        ]
    }

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert "meal_break_first_window" not in evaluation["warning_rule_codes"]
    assert "meal_break_first_window" not in evaluation["blocking_rule_codes"]
    assert evaluation["shift_facts"]["structure_source"] == "metadata"


def test_evaluate_shift_assignment_compliance_warns_when_rest_break_quota_is_missing():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "rest_break_ruleset": "ca_v1",
        }
    )
    shift = _apply_segments(
        _shift(
            starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 18, 22, 30, tzinfo=timezone.utc),
        ),
        [
            {
                "starts_at": datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 4, 18, 22, 30, tzinfo=timezone.utc),
                "breaks": [],
            }
        ],
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert evaluation["status"] == "warning"
    assert evaluation["would_block"] is False
    assert "paid_rest_break_quota" in evaluation["warning_rule_codes"]
    assert evaluation["unresolved_premium_rule_codes"] == ["paid_rest_break_quota"]


def test_evaluate_shift_assignment_compliance_accepts_rest_break_quota_when_present():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "rest_break_ruleset": "ca_v1",
        }
    )
    shift = _apply_segments(
        _shift(
            starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 18, 22, 30, tzinfo=timezone.utc),
        ),
        [
            {
                "starts_at": datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 4, 18, 22, 30, tzinfo=timezone.utc),
                "breaks": [
                    {
                        "break_type": ShiftBreakType.rest,
                        "is_paid": True,
                        "starts_at": datetime(2026, 4, 18, 18, 0, tzinfo=timezone.utc),
                        "ends_at": datetime(2026, 4, 18, 18, 10, tzinfo=timezone.utc),
                    },
                    {
                        "break_type": ShiftBreakType.rest,
                        "is_paid": True,
                        "starts_at": datetime(2026, 4, 18, 21, 0, tzinfo=timezone.utc),
                        "ends_at": datetime(2026, 4, 18, 21, 10, tzinfo=timezone.utc),
                    },
                ],
            }
        ],
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert "paid_rest_break_quota" not in evaluation["warning_rule_codes"]


def test_evaluate_shift_assignment_compliance_summarizes_split_shift_premium_when_configured():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "split_shift_ruleset": "ca_v1",
            "split_shift_premium_cents": 1900,
        }
    )
    shift = _apply_segments(
        _shift(
            starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 19, 1, 0, tzinfo=timezone.utc),
        ),
        [
            {
                "starts_at": datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 4, 18, 20, 0, tzinfo=timezone.utc),
                "breaks": [],
            },
            {
                "starts_at": datetime(2026, 4, 18, 21, 0, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 4, 19, 1, 0, tzinfo=timezone.utc),
                "breaks": [],
            },
        ],
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert evaluation["status"] == "warning"
    assert "split_shift_premium" in evaluation["warning_rule_codes"]
    assert evaluation["premium_total_cents"] == 1900
    assert any(component["rule_code"] == "split_shift_premium" for component in evaluation["premium_components"])


def test_evaluate_shift_assignment_compliance_flags_unresolved_split_shift_premium_without_fixed_amount():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "split_shift_ruleset": "ca_v1",
        }
    )
    shift = _apply_segments(
        _shift(
            starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 19, 1, 0, tzinfo=timezone.utc),
        ),
        [
            {
                "starts_at": datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 4, 18, 20, 0, tzinfo=timezone.utc),
                "breaks": [],
            },
            {
                "starts_at": datetime(2026, 4, 18, 21, 0, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 4, 19, 1, 0, tzinfo=timezone.utc),
                "breaks": [],
            },
        ],
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert evaluation["premium_total_cents"] == 0
    assert evaluation["unresolved_premium_rule_codes"] == ["split_shift_premium"]


def test_evaluate_shift_assignment_compliance_summarizes_spread_of_hours_premium_when_configured():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "spread_of_hours_ruleset": "ny_v1",
            "minimum_wage_cents": 1650,
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 18, 14, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 19, 1, 30, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert evaluation["status"] == "warning"
    assert "spread_of_hours_premium" in evaluation["warning_rule_codes"]
    assert evaluation["premium_total_cents"] == 1650
    component = next(
        item for item in evaluation["premium_components"] if item["rule_code"] == "spread_of_hours_premium"
    )
    assert component["premium_type"] == "fixed_cents"
    assert component["premium_cents"] == 1650


def test_evaluate_shift_assignment_compliance_flags_unresolved_spread_of_hours_premium_without_wage_floor():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "spread_of_hours_ruleset": "ny_v1",
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 18, 14, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 19, 1, 30, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert evaluation["premium_total_cents"] == 0
    assert evaluation["unresolved_premium_rule_codes"] == ["spread_of_hours_premium"]


def test_evaluate_shift_assignment_compliance_blocks_seven_consecutive_workdays_when_day_of_rest_rule_is_enabled():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "day_of_rest_ruleset": "ca_v1",
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 20, 17, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 21, 1, 0, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(
            _interval(datetime(2026, 4, 14, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 15, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 16, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 16, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 17, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 17, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 18, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 18, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 19, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 19, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 20, 1, 0, tzinfo=timezone.utc)),
        ),
        reference_time=datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
    )

    assert evaluation["status"] == "block"
    assert evaluation["blocking_rule_codes"] == ["day_of_rest_in_seven"]
    rule_result = next(
        item for item in evaluation["rule_results"] if item["rule_code"] == "day_of_rest_in_seven"
    )
    assert "seven_consecutive_workdays_projected" in rule_result["reason_codes"]
    assert rule_result["projected_consecutive_work_days"] == 7
    assert rule_result["streak_start_date"] == "2026-04-14"
    assert rule_result["streak_end_date"] == "2026-04-20"


def test_evaluate_shift_assignment_compliance_allows_candidate_when_rest_day_breaks_streak():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "day_of_rest_ruleset": "ca_v1",
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 20, 17, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 21, 1, 0, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(
            _interval(datetime(2026, 4, 14, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 15, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 16, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 16, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 17, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 18, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 19, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 19, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 20, 1, 0, tzinfo=timezone.utc)),
        ),
        reference_time=datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
    )

    assert "day_of_rest_in_seven" not in evaluation["blocking_rule_codes"]
    rule_result = next(
        item for item in evaluation["rule_results"] if item["rule_code"] == "day_of_rest_in_seven"
    )
    assert rule_result["status"] == "clear"
    assert rule_result["projected_consecutive_work_days"] == 3


def test_evaluate_shift_assignment_compliance_blocks_missing_workweek_rest_day_when_rule_is_enabled():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "day_of_rest_workweek_required": True,
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 19, 17, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 20, 1, 0, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(
            _interval(datetime(2026, 4, 13, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 14, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 14, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 15, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 16, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 16, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 17, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 17, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 18, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 18, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 19, 1, 0, tzinfo=timezone.utc)),
        ),
        reference_time=datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc),
    )

    assert evaluation["status"] == "block"
    assert "day_of_rest_workweek" in evaluation["blocking_rule_codes"]
    rule_result = next(
        item for item in evaluation["rule_results"] if item["rule_code"] == "day_of_rest_workweek"
    )
    assert "workweek_rest_day_missing" in rule_result["reason_codes"]
    assert "seven_workdays_in_workweek_projected" in rule_result["reason_codes"]
    assert rule_result["projected_workdays_in_workweek"] == 7
    assert rule_result["required_rest_days_per_workweek"] == 1


def test_evaluate_shift_assignment_compliance_clears_workweek_rest_day_rule_when_day_off_exists():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "day_of_rest_workweek_required": True,
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 19, 17, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 20, 1, 0, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(
            _interval(datetime(2026, 4, 13, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 14, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 14, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 15, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 16, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 16, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 17, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 17, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 18, 1, 0, tzinfo=timezone.utc)),
        ),
        reference_time=datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc),
    )

    assert "day_of_rest_workweek" not in evaluation["blocking_rule_codes"]
    rule_result = next(
        item for item in evaluation["rule_results"] if item["rule_code"] == "day_of_rest_workweek"
    )
    assert rule_result["status"] == "clear"
    assert rule_result["projected_workdays_in_workweek"] == 6


def test_evaluate_shift_assignment_compliance_applies_stricter_rest_policy_and_disables_consent():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "minimum_rest_hours": 10,
            "written_consent_allowed": True,
            "rest_window_rule_code": "clopening_restricted",
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 18, 22, 0, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(
            _interval(datetime(2026, 4, 18, 0, 0, tzinfo=timezone.utc), datetime(2026, 4, 18, 5, 0, tzinfo=timezone.utc)),
        ),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        business_settings={"compliance": {"minimum_rest_hours": 12, "written_consent_allowed": False}},
    )

    assert evaluation["status"] == "block"
    assert evaluation["blocking_rule_codes"] == ["clopening_restricted"]
    rule_result = next(
        result for result in evaluation["rule_results"] if result["rule_code"] == "clopening_restricted"
    )
    assert rule_result["minimum_rest_hours"] == 12.0
    assert rule_result["artifact_type_allowed"] is None
    assert "written_consent_required" not in rule_result["reason_codes"]


def test_evaluate_shift_assignment_compliance_disables_meal_waiver_when_policy_requires():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "meal_break_ruleset": "ca_v1",
        }
    )
    shift = _apply_segments(
        _shift(
            starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 18, 21, 30, tzinfo=timezone.utc),
        ),
        [
            {
                "starts_at": datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 4, 18, 21, 30, tzinfo=timezone.utc),
                "breaks": [],
            }
        ],
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        business_settings={"compliance": {"first_meal_waiver_allowed": False}},
    )

    assert evaluation["status"] == "block"
    assert evaluation["blocking_rule_codes"] == ["meal_break_first_window"]
    meal_result = next(
        result for result in evaluation["rule_results"] if result["rule_code"] == "meal_break_first_window"
    )
    assert meal_result["artifact_type_allowed"] is None
    assert "waiver_disabled_by_policy" in meal_result["reason_codes"]


def test_evaluate_shift_assignment_compliance_blocks_unstructured_break_plan_when_policy_requires():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "meal_break_ruleset": "ca_v1",
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 18, 22, 30, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        business_settings={"compliance": {"require_structured_break_plans": True}},
    )

    assert evaluation["status"] == "block"
    assert "customer_policy_structured_break_plan" in evaluation["blocking_rule_codes"]


def test_evaluate_shift_assignment_compliance_blocks_daily_minutes_when_policy_requires():
    profile = _profile()
    shift = _shift(
        starts_at=datetime(2026, 4, 17, 19, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 18, 3, 0, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 17, 18, 0, tzinfo=timezone.utc),
        business_settings={"compliance": {"max_daily_minutes": 420}},
    )

    assert evaluation["status"] == "block"
    assert "customer_policy_max_daily_work_minutes" in evaluation["blocking_rule_codes"]


def test_evaluate_shift_assignment_compliance_blocks_consecutive_workdays_when_policy_requires():
    profile = _profile()
    shift = _shift(
        starts_at=datetime(2026, 4, 20, 17, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 21, 1, 0, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(
            _interval(datetime(2026, 4, 14, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 15, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 16, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 16, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 17, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 17, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 18, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 18, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 19, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 19, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 20, 1, 0, tzinfo=timezone.utc)),
        ),
        reference_time=datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
        business_settings={"compliance": {"max_consecutive_work_days": 6}},
    )

    assert evaluation["status"] == "block"
    assert "customer_policy_max_consecutive_work_days" in evaluation["blocking_rule_codes"]
    rule_result = next(
        item
        for item in evaluation["rule_results"]
        if item["rule_code"] == "customer_policy_max_consecutive_work_days"
    )
    assert "max_consecutive_work_days_exceeded_by_policy" in rule_result["reason_codes"]
    assert "seven_consecutive_workdays_projected" in rule_result["reason_codes"]
    assert rule_result["configured_days"] == 6
    assert rule_result["projected_consecutive_work_days"] == 7


def test_evaluate_shift_assignment_compliance_blocks_workweek_rest_day_when_policy_requires():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 19, 17, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 20, 1, 0, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(
            _interval(datetime(2026, 4, 13, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 14, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 14, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 15, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 16, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 16, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 17, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 17, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 18, 1, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 18, 17, 0, tzinfo=timezone.utc), datetime(2026, 4, 19, 1, 0, tzinfo=timezone.utc)),
        ),
        reference_time=datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc),
        business_settings={"compliance": {"required_rest_days_per_workweek": 1}},
    )

    assert evaluation["status"] == "block"
    assert "customer_policy_required_rest_days_per_workweek" in evaluation["blocking_rule_codes"]
    rule_result = next(
        item
        for item in evaluation["rule_results"]
        if item["rule_code"] == "customer_policy_required_rest_days_per_workweek"
    )
    assert "workweek_rest_day_missing_by_policy" in rule_result["reason_codes"]
    assert "seven_workdays_in_workweek_projected" in rule_result["reason_codes"]
    assert rule_result["required_rest_days_per_workweek"] == 1
    assert rule_result["projected_workdays_in_workweek"] == 7


def test_evaluate_shift_assignment_compliance_blocks_unresolved_premium_when_policy_requires():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "rest_break_ruleset": "ca_v1",
        }
    )
    shift = _apply_segments(
        _shift(
            starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 18, 22, 30, tzinfo=timezone.utc),
        ),
        [
            {
                "starts_at": datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 4, 18, 22, 30, tzinfo=timezone.utc),
                "breaks": [],
            }
        ],
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        business_settings={"compliance": {"block_unresolved_premiums": True}},
    )

    assert evaluation["status"] == "block"
    assert "customer_policy_unresolved_premium" in evaluation["blocking_rule_codes"]
    assert evaluation["unresolved_premium_rule_codes"] == ["paid_rest_break_quota"]


def test_evaluate_shift_assignment_compliance_resolves_meal_premium_from_employee_hourly_rate():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "meal_break_ruleset": "ca_v1",
        }
    )
    shift = _apply_segments(
        _shift(
            starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 18, 22, 30, tzinfo=timezone.utc),
        ),
        [
            {
                "starts_at": datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 4, 18, 22, 30, tzinfo=timezone.utc),
                "breaks": [],
            }
        ],
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        employee_base_hourly_rate_cents=2250,
    )

    assert evaluation["premium_total_cents"] == 2250
    assert evaluation["unresolved_premium_rule_codes"] == []
    component = next(
        item for item in evaluation["premium_components"] if item["rule_code"] == "meal_break_first_window"
    )
    assert component["premium_type"] == "fixed_cents"
    assert component["premium_cents"] == 2250


def test_evaluate_shift_assignment_compliance_resolves_rest_premium_from_employee_hourly_rate():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "rest_break_ruleset": "ca_v1",
        }
    )
    shift = _apply_segments(
        _shift(
            starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 18, 22, 30, tzinfo=timezone.utc),
        ),
        [
            {
                "starts_at": datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 4, 18, 22, 30, tzinfo=timezone.utc),
                "breaks": [],
            }
        ],
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        employee_base_hourly_rate_cents=1850,
    )

    assert evaluation["premium_total_cents"] == 1850
    assert evaluation["unresolved_premium_rule_codes"] == []
    component = next(
        item for item in evaluation["premium_components"] if item["rule_code"] == "paid_rest_break_quota"
    )
    assert component["premium_type"] == "fixed_cents"
    assert component["premium_cents"] == 1850


def test_evaluate_shift_assignment_compliance_blocks_minor_without_work_permit():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "minor_work_permit_required": True,
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 18, 20, 0, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        employee_date_of_birth=date(2010, 5, 1),
    )

    assert evaluation["status"] == "block"
    assert evaluation["blocking_rule_codes"] == ["minor_work_permit_required"]
    rule_result = next(
        result for result in evaluation["rule_results"] if result["rule_code"] == "minor_work_permit_required"
    )
    assert "work_permit_missing" in rule_result["reason_codes"]


def test_evaluate_shift_assignment_compliance_blocks_minor_daily_limit_and_time_window():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "minor_daily_max_minutes": 300,
            "minor_earliest_start_local_time": "07:00",
            "minor_latest_end_local_time": "19:00",
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 18, 13, 30, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 19, 2, 30, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        employee_date_of_birth=date(2010, 5, 1),
    )

    assert evaluation["status"] == "block"
    assert "minor_daily_hours_limit" in evaluation["blocking_rule_codes"]
    assert "minor_time_window_restricted" in evaluation["blocking_rule_codes"]
    time_window_result = next(
        result for result in evaluation["rule_results"] if result["rule_code"] == "minor_time_window_restricted"
    )
    assert "minor_shift_starts_too_early" in time_window_result["reason_codes"]
    assert "minor_shift_ends_too_late" in time_window_result["reason_codes"]


def test_evaluate_shift_assignment_compliance_accepts_minor_when_rules_are_satisfied():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "minor_work_permit_required": True,
            "minor_daily_max_minutes": 300,
            "minor_earliest_start_local_time": "07:00",
            "minor_latest_end_local_time": "19:00",
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 18, 20, 30, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        employee_date_of_birth=date(2010, 5, 1),
        employee_work_permit_number="WP-12345",
        employee_work_permit_expires_on=date(2026, 8, 31),
    )

    assert evaluation["status"] == "clear"
    assert evaluation["blocking_rule_codes"] == []
    assert "minor_work_permit_required" not in evaluation["warning_rule_codes"]


def test_evaluate_shift_assignment_compliance_blocks_when_work_permit_is_not_yet_effective():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "minor_work_permit_required": True,
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 18, 20, 0, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        employee_date_of_birth=date(2010, 5, 1),
        employee_work_permit_number="WP-12345",
        employee_work_permit_effective_start_on=date(2026, 5, 1),
        employee_work_permit_expires_on=date(2026, 8, 31),
    )

    assert "minor_work_permit_required" in evaluation["blocking_rule_codes"]
    rule_result = next(
        item for item in evaluation["rule_results"] if item["rule_code"] == "minor_work_permit_required"
    )
    assert "work_permit_not_yet_effective" in rule_result["reason_codes"]


def test_evaluate_shift_assignment_compliance_blocks_on_active_work_permit_specific_limits():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "minor_work_permit_required": True,
            "minor_daily_max_minutes": 480,
            "minor_latest_end_local_time": "21:00",
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 18, 23, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 19, 3, 30, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(
            _interval(datetime(2026, 4, 14, 16, 0, tzinfo=timezone.utc), datetime(2026, 4, 14, 19, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 15, 16, 0, tzinfo=timezone.utc), datetime(2026, 4, 15, 19, 0, tzinfo=timezone.utc)),
        ),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        employee_date_of_birth=date(2010, 5, 1),
        employee_work_permit_number="WP-12345",
        employee_work_permit_effective_start_on=date(2026, 4, 1),
        employee_work_permit_expires_on=date(2026, 8, 31),
        employee_work_permit_max_daily_minutes=180,
        employee_work_permit_max_weekly_minutes=1080,
        employee_work_permit_latest_end_local_time="19:00",
    )

    assert "minor_work_permit_daily_hours_limit" in evaluation["blocking_rule_codes"]
    assert "minor_work_permit_time_window" in evaluation["blocking_rule_codes"]
    daily_result = next(
        item for item in evaluation["rule_results"] if item["rule_code"] == "minor_work_permit_daily_hours_limit"
    )
    assert daily_result["daily_max_minutes"] == 180
    time_result = next(
        item for item in evaluation["rule_results"] if item["rule_code"] == "minor_work_permit_time_window"
    )
    assert "work_permit_shift_ends_too_late" in time_result["reason_codes"]


def test_evaluate_shift_assignment_compliance_applies_school_day_specific_active_work_permit_profile():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "minor_work_permit_required": True,
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 16, 23, 30, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 17, 3, 30, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(
            _interval(datetime(2026, 4, 14, 16, 0, tzinfo=timezone.utc), datetime(2026, 4, 14, 21, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 15, 16, 0, tzinfo=timezone.utc), datetime(2026, 4, 15, 21, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 16, 16, 0, tzinfo=timezone.utc), datetime(2026, 4, 16, 21, 0, tzinfo=timezone.utc)),
        ),
        reference_time=datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc),
        employee_date_of_birth=date(2010, 5, 1),
        employee_minor_school_status="in_session",
        employee_work_permit_number="WP-12345",
        employee_work_permit_effective_start_on=date(2026, 4, 1),
        employee_work_permit_expires_on=date(2026, 8, 31),
        employee_work_permit_max_daily_minutes=300,
        employee_work_permit_max_weekly_minutes=1800,
        employee_work_permit_rule_profile={
            "allowed_weekdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
            "daily_max_minutes_school_day": 180,
            "weekly_max_minutes_school_week": 1080,
            "latest_end_local_time_school_day": "19:00",
        },
        business_settings={
            "compliance": {
                "school_day_weekdays": [
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                ],
            }
        },
    )

    assert "minor_work_permit_daily_hours_limit" in evaluation["blocking_rule_codes"]
    assert "minor_work_permit_weekly_hours_limit" in evaluation["blocking_rule_codes"]
    assert "minor_work_permit_time_window" in evaluation["blocking_rule_codes"]
    weekday_result = next(
        item for item in evaluation["rule_results"] if item["rule_code"] == "minor_work_permit_weekday_restriction"
    )
    assert weekday_result["status"] == "clear"
    assert "work_permit_weekday_allowed" in weekday_result["reason_codes"]
    daily_result = next(
        item for item in evaluation["rule_results"] if item["rule_code"] == "minor_work_permit_daily_hours_limit"
    )
    assert daily_result["daily_max_minutes"] == 180
    assert daily_result["minor_school_day"] is True
    weekly_result = next(
        item for item in evaluation["rule_results"] if item["rule_code"] == "minor_work_permit_weekly_hours_limit"
    )
    assert weekly_result["weekly_max_minutes"] == 1080
    assert weekly_result["minor_school_week"] is True
    time_result = next(
        item for item in evaluation["rule_results"] if item["rule_code"] == "minor_work_permit_time_window"
    )
    assert time_result["latest_end_local_time"] == "19:00:00"


def test_evaluate_shift_assignment_compliance_blocks_on_active_work_permit_weekday_restriction():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "minor_work_permit_required": True,
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 18, 18, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 18, 22, 0, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        employee_date_of_birth=date(2010, 5, 1),
        employee_minor_school_status="in_session",
        employee_work_permit_number="WP-12345",
        employee_work_permit_effective_start_on=date(2026, 4, 1),
        employee_work_permit_expires_on=date(2026, 8, 31),
        employee_work_permit_rule_profile={
            "allowed_weekdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        },
        business_settings={
            "compliance": {
                "school_day_weekdays": [
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                ],
            }
        },
    )

    assert "minor_work_permit_weekday_restriction" in evaluation["blocking_rule_codes"]
    weekday_result = next(
        item for item in evaluation["rule_results"] if item["rule_code"] == "minor_work_permit_weekday_restriction"
    )
    assert "work_permit_weekday_not_allowed" in weekday_result["reason_codes"]
    assert weekday_result["shift_weekday"] == "saturday"


def test_evaluate_shift_assignment_compliance_allows_template_permit_on_day_preceding_non_school_day():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "minor_work_permit_required": True,
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 18, 0, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 18, 7, 15, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
        employee_date_of_birth=date(2009, 5, 1),
        employee_minor_school_status="in_session",
        employee_work_permit_number="WP-CA-16-17",
        employee_work_permit_effective_start_on=date(2026, 4, 1),
        employee_work_permit_expires_on=date(2026, 8, 31),
        employee_work_permit_rule_profile={
            "template_code": "ca_16_17_school_required_v1",
        },
        business_settings={
            "compliance": {
                "school_day_weekdays": [
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                ],
            }
        },
    )

    assert "minor_work_permit_daily_hours_limit" not in evaluation["blocking_rule_codes"]
    assert "minor_work_permit_time_window" not in evaluation["blocking_rule_codes"]
    daily_result = next(
        item for item in evaluation["rule_results"] if item["rule_code"] == "minor_work_permit_daily_hours_limit"
    )
    assert daily_result["status"] == "clear"
    assert daily_result["daily_max_minutes"] == 480
    assert daily_result["minor_precedes_non_school_day"] is True
    time_result = next(
        item for item in evaluation["rule_results"] if item["rule_code"] == "minor_work_permit_time_window"
    )
    assert time_result["status"] == "clear"
    assert time_result["latest_end_local_time"] == "00:30:00"


def test_evaluate_shift_assignment_compliance_blocks_template_permit_on_regular_school_night():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "minor_work_permit_required": True,
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 17, 0, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 17, 7, 15, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc),
        employee_date_of_birth=date(2009, 5, 1),
        employee_minor_school_status="in_session",
        employee_work_permit_number="WP-CA-16-17",
        employee_work_permit_effective_start_on=date(2026, 4, 1),
        employee_work_permit_expires_on=date(2026, 8, 31),
        employee_work_permit_rule_profile={
            "template_code": "ca_16_17_school_required_v1",
        },
        business_settings={
            "compliance": {
                "school_day_weekdays": [
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                ],
            }
        },
    )

    assert "minor_work_permit_daily_hours_limit" in evaluation["blocking_rule_codes"]
    assert "minor_work_permit_time_window" in evaluation["blocking_rule_codes"]
    daily_result = next(
        item for item in evaluation["rule_results"] if item["rule_code"] == "minor_work_permit_daily_hours_limit"
    )
    assert daily_result["daily_max_minutes"] == 240
    assert daily_result["minor_precedes_non_school_day"] is False
    time_result = next(
        item for item in evaluation["rule_results"] if item["rule_code"] == "minor_work_permit_time_window"
    )
    assert "work_permit_shift_ends_too_late" in time_result["reason_codes"]


def test_evaluate_shift_assignment_compliance_applies_in_session_youth_limits():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "minor_daily_max_minutes_in_session": 180,
            "minor_weekly_max_minutes_in_session": 1080,
            "minor_latest_end_local_time_in_session": "19:00",
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 18, 23, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 19, 3, 0, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(
            _interval(datetime(2026, 4, 14, 16, 0, tzinfo=timezone.utc), datetime(2026, 4, 14, 19, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 15, 16, 0, tzinfo=timezone.utc), datetime(2026, 4, 15, 19, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 16, 16, 0, tzinfo=timezone.utc), datetime(2026, 4, 17, 1, 0, tzinfo=timezone.utc)),
        ),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        employee_date_of_birth=date(2011, 5, 1),
        employee_minor_school_status="in_session",
    )

    assert evaluation["status"] == "block"
    assert "minor_daily_hours_limit" in evaluation["blocking_rule_codes"]
    assert "minor_weekly_hours_limit" in evaluation["blocking_rule_codes"]
    assert "minor_time_window_restricted" in evaluation["blocking_rule_codes"]


def test_evaluate_shift_assignment_compliance_relaxes_youth_limits_on_summer_break():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "minor_daily_max_minutes_in_session": 180,
            "minor_weekly_max_minutes_in_session": 1080,
            "minor_latest_end_local_time_in_session": "19:00",
            "minor_daily_max_minutes_summer_break": 480,
            "minor_weekly_max_minutes_summer_break": 2400,
            "minor_latest_end_local_time_summer_break": "21:00",
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 7, 18, 20, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 7, 19, 3, 30, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc),
        employee_date_of_birth=date(2011, 5, 1),
        employee_minor_school_status="summer_break",
    )

    minor_rule_results = {
        item["rule_code"]: item
        for item in evaluation["rule_results"]
        if str(item.get("rule_code", "")).startswith("minor_")
    }

    assert "minor_daily_hours_limit" not in evaluation["blocking_rule_codes"]
    assert "minor_weekly_hours_limit" not in evaluation["blocking_rule_codes"]
    assert "minor_time_window_restricted" not in evaluation["blocking_rule_codes"]
    assert minor_rule_results["minor_daily_hours_limit"]["status"] == "clear"
    assert minor_rule_results["minor_weekly_hours_limit"]["status"] == "clear"
    assert minor_rule_results["minor_time_window_restricted"]["status"] == "clear"


def test_evaluate_shift_assignment_compliance_applies_school_day_overrides_for_in_session_minors():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "minor_daily_max_minutes_in_session": 300,
            "minor_daily_max_minutes_school_day": 180,
            "minor_latest_end_local_time_in_session": "21:00",
            "minor_latest_end_local_time_school_day": "19:00",
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 13, 23, 30, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 14, 3, 30, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc),
        employee_date_of_birth=date(2011, 5, 1),
        employee_minor_school_status="in_session",
        business_settings={
            "compliance": {
                "school_day_weekdays": [
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                ],
            }
        },
    )

    assert "minor_daily_hours_limit" in evaluation["blocking_rule_codes"]
    assert "minor_time_window_restricted" in evaluation["blocking_rule_codes"]
    daily_result = next(
        item for item in evaluation["rule_results"] if item["rule_code"] == "minor_daily_hours_limit"
    )
    assert daily_result["minor_school_day"] is True
    assert daily_result["daily_max_minutes"] == 180


def test_evaluate_shift_assignment_compliance_applies_non_school_day_overrides_for_in_session_minors():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "minor_daily_max_minutes_in_session": 180,
            "minor_daily_max_minutes_non_school_day": 480,
            "minor_latest_end_local_time_in_session": "19:00",
            "minor_latest_end_local_time_non_school_day": "21:00",
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 18, 23, 30, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 19, 3, 30, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        employee_date_of_birth=date(2011, 5, 1),
        employee_minor_school_status="in_session",
        business_settings={
            "compliance": {
                "school_day_weekdays": [
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                ],
            }
        },
    )

    minor_rule_results = {
        item["rule_code"]: item
        for item in evaluation["rule_results"]
        if str(item.get("rule_code", "")).startswith("minor_")
    }
    assert "minor_daily_hours_limit" not in evaluation["blocking_rule_codes"]
    assert "minor_time_window_restricted" not in evaluation["blocking_rule_codes"]
    assert minor_rule_results["minor_daily_hours_limit"]["status"] == "clear"
    assert minor_rule_results["minor_daily_hours_limit"]["minor_school_day"] is False
    assert minor_rule_results["minor_time_window_restricted"]["status"] == "clear"


def test_evaluate_shift_assignment_compliance_applies_non_school_week_limit_when_calendar_closes_school_days():
    profile = _profile(
        rules_json={
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "minor_weekly_max_minutes_in_session": 1080,
            "minor_weekly_max_minutes_non_school_week": 2400,
        }
    )
    shift = _shift(
        starts_at=datetime(2026, 4, 18, 23, 30, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 19, 3, 30, tzinfo=timezone.utc),
    )

    evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=(
            _interval(datetime(2026, 4, 14, 16, 0, tzinfo=timezone.utc), datetime(2026, 4, 14, 22, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 15, 16, 0, tzinfo=timezone.utc), datetime(2026, 4, 15, 22, 0, tzinfo=timezone.utc)),
            _interval(datetime(2026, 4, 16, 16, 0, tzinfo=timezone.utc), datetime(2026, 4, 16, 22, 0, tzinfo=timezone.utc)),
        ),
        reference_time=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
        employee_date_of_birth=date(2011, 5, 1),
        employee_minor_school_status="in_session",
        business_settings={
            "compliance": {
                "school_day_weekdays": [
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                ],
                "non_school_dates": [
                    "2026-04-13",
                    "2026-04-14",
                    "2026-04-15",
                    "2026-04-16",
                    "2026-04-17",
                ],
            }
        },
    )

    weekly_result = next(
        item for item in evaluation["rule_results"] if item["rule_code"] == "minor_weekly_hours_limit"
    )
    assert weekly_result["status"] == "clear"
    assert weekly_result["minor_school_week"] is False
    assert weekly_result["weekly_max_minutes"] == 2400
