from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta

from app.models.scheduling import Shift
from app.services import compliance_engine, compliance_shift_facts, labor_rules

COMPLIANCE_BREAK_PLAN_VERSION = "deterministic_break_plan_v1"


def plan_shift_segments(
    profile: labor_rules.LaborRuleProfileSnapshot | None,
    *,
    shift: Shift,
    business_settings: Mapping[str, object] | None = None,
    location_settings: Mapping[str, object] | None = None,
) -> list[dict[str, object]] | None:
    if profile is None:
        return None

    meal_rule = compliance_engine._meal_break_rule(
        profile,
        business_settings=business_settings,
        location_settings=location_settings,
    )
    rest_rule = compliance_engine._paid_rest_break_rule(profile)
    if meal_rule is None and rest_rule is None:
        return None

    planned_breaks: list[dict[str, object]] = []
    if meal_rule is not None:
        planned_breaks.extend(_plan_meal_breaks(shift=shift, meal_rule=meal_rule))

    provisional_shift = _synthetic_shift_with_breaks(shift, planned_breaks)
    provisional_facts = compliance_shift_facts.build_shift_structure_facts(provisional_shift)

    if rest_rule is not None:
        planned_breaks.extend(
            _plan_rest_breaks(
                shift=shift,
                existing_breaks=planned_breaks,
                required_break_count=_required_paid_rest_break_count(
                    int(provisional_facts.get("net_active_work_minutes") or 0)
                ),
                min_break_minutes=int(rest_rule.get("min_break_minutes") or 10),
            )
        )

    planned_breaks.sort(key=lambda item: (str(item["starts_at"]), str(item["break_type"])))
    return [
        {
            "sequence_no": 1,
            "segment_type": "work",
            "starts_at": shift.starts_at.isoformat(),
            "ends_at": shift.ends_at.isoformat(),
            "segment_metadata": {
                "planned_by": COMPLIANCE_BREAK_PLAN_VERSION,
            },
            "breaks": [
                {
                    "sequence_no": index,
                    "break_type": item["break_type"],
                    "is_paid": item["is_paid"],
                    "starts_at": item["starts_at"].isoformat(),
                    "ends_at": item["ends_at"].isoformat(),
                    "notes": item["notes"],
                    "break_metadata": {
                        "planned_by": COMPLIANCE_BREAK_PLAN_VERSION,
                    },
                }
                for index, item in enumerate(planned_breaks, start=1)
            ],
        }
    ]


def _plan_meal_breaks(
    *,
    shift: Shift,
    meal_rule: Mapping[str, object],
) -> list[dict[str, object]]:
    planned: list[dict[str, object]] = []
    scheduled_span_minutes = _duration_minutes(shift.starts_at, shift.ends_at)
    first_trigger_minutes = int(meal_rule.get("first_trigger_minutes") or 300)
    first_min_break_minutes = int(meal_rule.get("first_min_break_minutes") or 30)
    if scheduled_span_minutes > first_trigger_minutes:
        planned.append(
            _planned_break(
                shift=shift,
                break_type="meal",
                is_paid=False,
                duration_minutes=first_min_break_minutes,
                start_offset_minutes=max(120, int(meal_rule.get("first_deadline_minutes") or 300) - 60),
                notes="planned_first_meal_break",
            )
        )

    second_trigger_minutes = int(meal_rule.get("second_trigger_minutes") or 600)
    second_min_break_minutes = int(meal_rule.get("second_min_break_minutes") or 30)
    if scheduled_span_minutes > second_trigger_minutes:
        planned.append(
            _planned_break(
                shift=shift,
                break_type="meal",
                is_paid=False,
                duration_minutes=second_min_break_minutes,
                start_offset_minutes=max(360, int(meal_rule.get("second_deadline_minutes") or 600) - 60),
                notes="planned_second_meal_break",
            )
        )

    return planned


def _plan_rest_breaks(
    *,
    shift: Shift,
    existing_breaks: list[dict[str, object]],
    required_break_count: int,
    min_break_minutes: int,
) -> list[dict[str, object]]:
    if required_break_count <= 0:
        return []

    intervals = _work_intervals(shift=shift, existing_breaks=existing_breaks)
    if not intervals:
        return []

    assignments = [0 for _ in intervals]
    for _ in range(required_break_count):
        target_index = max(
            range(len(intervals)),
            key=lambda index: _duration_minutes(intervals[index][0], intervals[index][1]) / (assignments[index] + 1),
        )
        assignments[target_index] += 1

    planned: list[dict[str, object]] = []
    for interval_index, assigned_count in enumerate(assignments):
        if assigned_count <= 0:
            continue
        interval_start, interval_end = intervals[interval_index]
        interval_duration = _duration_minutes(interval_start, interval_end)
        for item_index in range(assigned_count):
            midpoint_ratio = (item_index + 1) / (assigned_count + 1)
            midpoint_minutes = round(interval_duration * midpoint_ratio)
            start_offset = _duration_minutes(shift.starts_at, interval_start) + max(
                0,
                midpoint_minutes - (min_break_minutes // 2),
            )
            planned.append(
                _planned_break(
                    shift=shift,
                    break_type="rest",
                    is_paid=True,
                    duration_minutes=min_break_minutes,
                    start_offset_minutes=start_offset,
                    interval_end=interval_end,
                    notes="planned_rest_break",
                )
            )
    return planned


def _work_intervals(
    *,
    shift: Shift,
    existing_breaks: list[dict[str, object]],
) -> list[tuple[datetime, datetime]]:
    sorted_breaks = sorted(existing_breaks, key=lambda item: item["starts_at"])
    intervals: list[tuple[datetime, datetime]] = []
    cursor = shift.starts_at
    for item in sorted_breaks:
        if item["starts_at"] > cursor:
            intervals.append((cursor, item["starts_at"]))
        cursor = max(cursor, item["ends_at"])
    if cursor < shift.ends_at:
        intervals.append((cursor, shift.ends_at))
    return intervals


def _planned_break(
    *,
    shift: Shift,
    break_type: str,
    is_paid: bool,
    duration_minutes: int,
    start_offset_minutes: int,
    notes: str,
    interval_end: datetime | None = None,
) -> dict[str, object]:
    start_at = shift.starts_at + timedelta(minutes=max(0, start_offset_minutes))
    end_limit = interval_end or shift.ends_at
    if start_at + timedelta(minutes=duration_minutes) > end_limit:
        start_at = end_limit - timedelta(minutes=duration_minutes)
    start_at = max(shift.starts_at, start_at)
    end_at = min(shift.ends_at, start_at + timedelta(minutes=duration_minutes))
    return {
        "break_type": break_type,
        "is_paid": is_paid,
        "starts_at": start_at,
        "ends_at": end_at,
        "notes": notes,
    }


def _synthetic_shift_with_breaks(shift: Shift, breaks: list[dict[str, object]]) -> Shift:
    synthetic = Shift(
        id=shift.id,
        business_id=shift.business_id,
        location_id=shift.location_id,
        role_id=shift.role_id,
        timezone=shift.timezone,
        starts_at=shift.starts_at,
        ends_at=shift.ends_at,
        seats_requested=int(shift.seats_requested or 1),
        seats_filled=int(shift.seats_filled or 0),
    )
    synthetic.location = getattr(shift, "location", None)
    synthetic.segments = [
        _synthetic_segment_for_breaks(
            shift=synthetic,
            breaks=breaks,
        )
    ]
    return synthetic


def _synthetic_segment_for_breaks(
    *,
    shift: Shift,
    breaks: list[dict[str, object]],
):
    from app.models.scheduling import ShiftBreak, ShiftSegment

    segment = ShiftSegment(
        shift_id=shift.id,
        sequence_no=1,
        segment_type="work",
        starts_at=shift.starts_at,
        ends_at=shift.ends_at,
        segment_metadata={},
    )
    segment.breaks = [
        ShiftBreak(
            shift_id=shift.id,
            shift_segment_id=segment.id,
            sequence_no=index,
            break_type=item["break_type"],
            is_paid=item["is_paid"],
            starts_at=item["starts_at"],
            ends_at=item["ends_at"],
            notes=item["notes"],
            break_metadata={},
        )
        for index, item in enumerate(sorted(breaks, key=lambda row: row["starts_at"]), start=1)
    ]
    return segment


def _required_paid_rest_break_count(net_active_work_minutes: int) -> int:
    if net_active_work_minutes < 210:
        return 0
    full_blocks = net_active_work_minutes // 240
    remainder = net_active_work_minutes % 240
    return full_blocks + (1 if remainder > 120 else 0)


def _duration_minutes(start_at: datetime, end_at: datetime) -> int:
    return max(0, int(round((end_at - start_at).total_seconds() / 60.0)))
