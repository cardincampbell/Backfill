from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
                    rest_rule,
                    scheduled_span_minutes=_duration_minutes(shift.starts_at, shift.ends_at),
                    net_active_work_minutes=int(provisional_facts.get("net_active_work_minutes") or 0),
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
    mode = str(meal_rule.get("mode") or "relative_windowed").strip().lower()
    if mode == "co_windowed":
        return _plan_colorado_meal_breaks(shift=shift, meal_rule=meal_rule)
    if mode == "ny_non_factory_windowed":
        return _plan_new_york_non_factory_meal_breaks(shift=shift, meal_rule=meal_rule)
    if mode == "or_windowed":
        return _plan_oregon_meal_breaks(shift=shift, meal_rule=meal_rule)
    if mode == "wa_windowed":
        return _plan_washington_meal_breaks(shift=shift, meal_rule=meal_rule)
    return _plan_relative_windowed_meal_breaks(shift=shift, meal_rule=meal_rule)


def _plan_relative_windowed_meal_breaks(
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


def _plan_new_york_non_factory_meal_breaks(
    *,
    shift: Shift,
    meal_rule: Mapping[str, object],
) -> list[dict[str, object]]:
    planned: list[dict[str, object]] = []
    scheduled_span_minutes = _duration_minutes(shift.starts_at, shift.ends_at)
    shift_timezone = _shift_timezone(shift)
    shift_local_start = shift.starts_at.astimezone(shift_timezone)
    shift_local_end = shift.ends_at.astimezone(shift_timezone)
    shift_local_date = shift_local_start.date()

    midday_trigger_minutes = int(meal_rule.get("midday_trigger_minutes") or 360)
    midday_window_start = compliance_engine._parse_local_time(
        meal_rule.get("midday_window_start_local")
    ) or datetime.min.time().replace(hour=11)
    midday_window_end = compliance_engine._parse_local_time(
        meal_rule.get("midday_window_end_local")
    ) or datetime.min.time().replace(hour=14)
    midday_min_break_minutes = int(meal_rule.get("midday_min_break_minutes") or 30)
    midday_window_start_at, midday_window_end_at = _local_window_bounds_for_date(
        shift_local_date,
        timezone=shift_timezone,
        window_start_local=midday_window_start,
        window_end_local=midday_window_end,
    )
    if (
        scheduled_span_minutes > midday_trigger_minutes
        and shift.starts_at < midday_window_end_at.astimezone(shift.starts_at.tzinfo)
        and shift.ends_at > midday_window_start_at.astimezone(shift.starts_at.tzinfo)
    ):
        planned_break = _planned_break_in_local_window(
            shift=shift,
            timezone=shift_timezone,
            window_start_at=midday_window_start_at,
            window_end_at=midday_window_end_at,
            duration_minutes=midday_min_break_minutes,
            notes="planned_midday_meal_break",
        )
        if planned_break is not None:
            planned.append(planned_break)

    evening_required_if_starts_before = compliance_engine._parse_local_time(
        meal_rule.get("evening_required_if_starts_before_local")
    ) or datetime.min.time().replace(hour=11)
    evening_required_if_ends_after = compliance_engine._parse_local_time(
        meal_rule.get("evening_required_if_ends_after_local")
    ) or datetime.min.time().replace(hour=19)
    evening_window_start = compliance_engine._parse_local_time(
        meal_rule.get("evening_window_start_local")
    ) or datetime.min.time().replace(hour=17)
    evening_window_end = compliance_engine._parse_local_time(
        meal_rule.get("evening_window_end_local")
    ) or datetime.min.time().replace(hour=19)
    evening_min_break_minutes = int(meal_rule.get("evening_min_break_minutes") or 20)
    evening_window_start_at, evening_window_end_at = _local_window_bounds_for_date(
        shift_local_date,
        timezone=shift_timezone,
        window_start_local=evening_window_start,
        window_end_local=evening_window_end,
    )
    if (
        shift_local_start.timetz().replace(tzinfo=None) < evening_required_if_starts_before
        and shift.ends_at > evening_window_end_at.astimezone(shift.ends_at.tzinfo)
    ):
        planned_break = _planned_break_in_local_window(
            shift=shift,
            timezone=shift_timezone,
            window_start_at=evening_window_start_at,
            window_end_at=evening_window_end_at,
            duration_minutes=evening_min_break_minutes,
            notes="planned_evening_meal_break",
        )
        if planned_break is not None:
            planned.append(planned_break)

    midshift_trigger_minutes = int(meal_rule.get("midshift_trigger_minutes") or 360)
    midshift_start_window = compliance_engine._parse_local_time(
        meal_rule.get("midshift_start_window_local")
    ) or datetime.min.time().replace(hour=13)
    midshift_end_window = compliance_engine._parse_local_time(
        meal_rule.get("midshift_end_window_local")
    ) or datetime.min.time().replace(hour=6)
    midshift_min_break_minutes = int(meal_rule.get("midshift_min_break_minutes") or 45)
    if (
        scheduled_span_minutes > midshift_trigger_minutes
        and compliance_engine._local_time_in_wrapped_window(
            shift_local_start.timetz().replace(tzinfo=None),
            window_start=midshift_start_window,
            window_end=midshift_end_window,
        )
    ):
        planned.append(
            _planned_break(
                shift=shift,
                break_type="meal",
                is_paid=False,
                duration_minutes=midshift_min_break_minutes,
                start_offset_minutes=max(0, (scheduled_span_minutes // 2) - (midshift_min_break_minutes // 2)),
                notes="planned_midshift_meal_break",
            )
        )

    return planned


def _plan_washington_meal_breaks(
    *,
    shift: Shift,
    meal_rule: Mapping[str, object],
) -> list[dict[str, object]]:
    scheduled_span_minutes = _duration_minutes(shift.starts_at, shift.ends_at)
    first_trigger_minutes = int(meal_rule.get("first_trigger_minutes") or 300)
    if scheduled_span_minutes <= first_trigger_minutes:
        return []
    first_min_break_minutes = int(meal_rule.get("first_min_break_minutes") or 30)
    window_start_minutes = int(meal_rule.get("first_window_start_minutes") or 120)
    window_end_minutes = int(meal_rule.get("first_window_end_minutes") or 300)
    normal_workday_minutes = compliance_engine._washington_normal_workday_minutes(
        candidate_shift=shift,
        scheduled_span_minutes=scheduled_span_minutes,
    )
    required_meal_count = compliance_engine._required_washington_meal_break_count(
        scheduled_span_minutes=scheduled_span_minutes,
        normal_workday_minutes=normal_workday_minutes,
        additional_trigger_beyond_normal_minutes=(
            int(meal_rule.get("additional_trigger_beyond_normal_minutes") or 180)
        ),
    )
    planned = [
        _planned_break_within_offset_window(
            shift=shift,
            break_type="meal",
            is_paid=False,
            duration_minutes=first_min_break_minutes,
            window_start_minutes=window_start_minutes,
            window_end_minutes=window_end_minutes,
            notes="planned_first_meal_break",
        )
    ]
    previous_break = planned[0]
    additional_interval_minutes = int(meal_rule.get("additional_interval_minutes") or 300)
    additional_min_break_minutes = int(meal_rule.get("additional_min_break_minutes") or 30)
    overtime_extension_required = scheduled_span_minutes >= (
        normal_workday_minutes + int(meal_rule.get("additional_trigger_beyond_normal_minutes") or 180)
    )
    for meal_index in range(2, required_meal_count + 1):
        previous_break_end_minutes = _duration_minutes(shift.starts_at, previous_break["ends_at"])
        next_window_start_minutes = previous_break_end_minutes
        if meal_index == 2 and overtime_extension_required:
            next_window_start_minutes = max(next_window_start_minutes, normal_workday_minutes)
        next_window_end_minutes = min(
            scheduled_span_minutes,
            previous_break_end_minutes + additional_interval_minutes,
        )
        previous_break = _planned_break_within_offset_window(
            shift=shift,
            break_type="meal",
            is_paid=False,
            duration_minutes=additional_min_break_minutes,
            window_start_minutes=next_window_start_minutes,
            window_end_minutes=next_window_end_minutes,
            notes="planned_additional_meal_break",
        )
        planned.append(previous_break)
    return planned


def _plan_colorado_meal_breaks(
    *,
    shift: Shift,
    meal_rule: Mapping[str, object],
) -> list[dict[str, object]]:
    scheduled_span_minutes = _duration_minutes(shift.starts_at, shift.ends_at)
    first_trigger_minutes = int(meal_rule.get("first_trigger_minutes") or 300)
    if scheduled_span_minutes <= first_trigger_minutes:
        return []

    first_min_break_minutes = int(meal_rule.get("first_min_break_minutes") or 30)
    first_window_start_minutes = int(meal_rule.get("first_window_start_minutes") or 60)
    first_window_end_minutes = max(
        first_window_start_minutes,
        scheduled_span_minutes - int(meal_rule.get("first_window_end_offset_minutes") or 60),
    )
    return [
        _planned_break_within_offset_window(
            shift=shift,
            break_type="meal",
            is_paid=False,
            duration_minutes=first_min_break_minutes,
            window_start_minutes=first_window_start_minutes,
            window_end_minutes=first_window_end_minutes,
            notes="planned_first_meal_break",
        )
    ]


def _plan_oregon_meal_breaks(
    *,
    shift: Shift,
    meal_rule: Mapping[str, object],
) -> list[dict[str, object]]:
    scheduled_span_minutes = _duration_minutes(shift.starts_at, shift.ends_at)
    required_meal_count = compliance_engine._required_oregon_meal_break_count(scheduled_span_minutes)
    if required_meal_count <= 0:
        return []

    first_min_break_minutes = int(meal_rule.get("first_min_break_minutes") or 30)
    if scheduled_span_minutes <= int(meal_rule.get("first_short_shift_max_minutes") or 420):
        first_window_start_minutes = int(meal_rule.get("first_short_window_start_minutes") or 120)
        first_window_end_minutes = int(meal_rule.get("first_short_window_end_minutes") or 300)
    else:
        first_window_start_minutes = int(meal_rule.get("first_long_window_start_minutes") or 180)
        first_window_end_minutes = int(meal_rule.get("first_long_window_end_minutes") or 360)

    planned = [
        _planned_break_within_offset_window(
            shift=shift,
            break_type="meal",
            is_paid=False,
            duration_minutes=first_min_break_minutes,
            window_start_minutes=first_window_start_minutes,
            window_end_minutes=first_window_end_minutes,
            notes="planned_first_meal_break",
        )
    ]
    previous_break = planned[0]
    for _ in range(2, required_meal_count + 1):
        previous_break_end_minutes = _duration_minutes(shift.starts_at, previous_break["ends_at"])
        window_start_minutes = previous_break_end_minutes + 120
        window_end_minutes = scheduled_span_minutes - first_min_break_minutes
        previous_break = _planned_break_within_offset_window(
            shift=shift,
            break_type="meal",
            is_paid=False,
            duration_minutes=first_min_break_minutes,
            window_start_minutes=min(window_start_minutes, window_end_minutes),
            window_end_minutes=max(window_start_minutes, window_end_minutes),
            notes="planned_additional_meal_break",
        )
        planned.append(previous_break)
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


def _planned_break_within_offset_window(
    *,
    shift: Shift,
    break_type: str,
    is_paid: bool,
    duration_minutes: int,
    window_start_minutes: int,
    window_end_minutes: int,
    notes: str,
) -> dict[str, object]:
    latest_start_minutes = max(window_start_minutes, window_end_minutes - duration_minutes)
    available_window_minutes = max(0, latest_start_minutes - window_start_minutes)
    start_offset_minutes = window_start_minutes + (available_window_minutes // 2)
    return _planned_break(
        shift=shift,
        break_type=break_type,
        is_paid=is_paid,
        duration_minutes=duration_minutes,
        start_offset_minutes=start_offset_minutes,
        notes=notes,
    )


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


def _required_paid_rest_break_count(
    rest_rule: Mapping[str, object],
    *,
    scheduled_span_minutes: int,
    net_active_work_minutes: int,
) -> int:
    mode = str(rest_rule.get("mode") or "ca_count_only").strip().lower()
    if mode == "co_timed":
        return _required_colorado_paid_rest_break_count(scheduled_span_minutes)
    if mode == "or_timed":
        return _required_oregon_paid_rest_break_count(scheduled_span_minutes)
    if mode == "wa_timed":
        return _required_washington_paid_rest_break_count(net_active_work_minutes)
    if net_active_work_minutes < 210:
        return 0
    full_blocks = net_active_work_minutes // 240
    remainder = net_active_work_minutes % 240
    return full_blocks + (1 if remainder > 120 else 0)


def _required_washington_paid_rest_break_count(net_active_work_minutes: int) -> int:
    if net_active_work_minutes <= 180:
        return 0
    full_blocks = net_active_work_minutes // 240
    remainder = net_active_work_minutes % 240
    return full_blocks + (1 if remainder > 180 else 0)


def _required_oregon_paid_rest_break_count(scheduled_span_minutes: int) -> int:
    if scheduled_span_minutes <= 120:
        return 0
    full_blocks = scheduled_span_minutes // 240
    remainder = scheduled_span_minutes % 240
    return full_blocks + (1 if remainder > 120 else 0)


def _required_colorado_paid_rest_break_count(scheduled_span_minutes: int) -> int:
    if scheduled_span_minutes <= 120:
        return 0
    full_blocks = scheduled_span_minutes // 240
    remainder = scheduled_span_minutes % 240
    return full_blocks + (1 if remainder > 120 else 0)


def _duration_minutes(start_at: datetime, end_at: datetime) -> int:
    return max(0, int(round((end_at - start_at).total_seconds() / 60.0)))


def _planned_break_in_local_window(
    *,
    shift: Shift,
    timezone: ZoneInfo,
    window_start_at: datetime,
    window_end_at: datetime,
    duration_minutes: int,
    notes: str,
) -> dict[str, object] | None:
    overlap_start = max(shift.starts_at, window_start_at.astimezone(shift.starts_at.tzinfo))
    overlap_end = min(shift.ends_at, window_end_at.astimezone(shift.starts_at.tzinfo))
    if overlap_end <= overlap_start or _duration_minutes(overlap_start, overlap_end) < duration_minutes:
        return None
    target_midpoint = overlap_start + (overlap_end - overlap_start) / 2
    start_at = target_midpoint - timedelta(minutes=duration_minutes / 2)
    if start_at < overlap_start:
        start_at = overlap_start
    if start_at + timedelta(minutes=duration_minutes) > overlap_end:
        start_at = overlap_end - timedelta(minutes=duration_minutes)
    return {
        "break_type": "meal",
        "is_paid": False,
        "starts_at": start_at,
        "ends_at": start_at + timedelta(minutes=duration_minutes),
        "notes": notes,
    }


def _local_window_bounds_for_date(
    shift_local_date,
    *,
    timezone: ZoneInfo,
    window_start_local,
    window_end_local,
):
    start_at = datetime.combine(shift_local_date, window_start_local, tzinfo=timezone)
    end_at = datetime.combine(shift_local_date, window_end_local, tzinfo=timezone)
    if end_at <= start_at:
        end_at += timedelta(days=1)
    return start_at, end_at


def _shift_timezone(shift: Shift) -> ZoneInfo:
    timezone_name = str(getattr(shift, "timezone", "") or "").strip() or "UTC"
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return ZoneInfo("UTC")
