from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from app.models.common import ShiftBreakType
from app.models.scheduling import Shift, ShiftBreak, ShiftSegment

_SHIFT_STRUCTURE_METADATA_KEYS = ("compliance_segments", "planned_segments")


def build_shift_structure_facts(shift: Shift) -> dict[str, object]:
    segments, structure_source = _normalized_segments_for_shift(shift)
    has_structured_segments = structure_source in {"explicit", "metadata"}

    scheduled_span_minutes = _duration_minutes(shift.starts_at, shift.ends_at)
    scheduled_segment_minutes = 0
    paid_break_minutes = 0
    unpaid_break_minutes = 0
    meal_break_minutes = 0
    rest_break_minutes = 0
    other_break_minutes = 0
    meal_break_count = 0
    rest_break_count = 0
    other_break_count = 0
    longest_continuous_work_minutes = 0
    inter_segment_gap_minutes = 0
    longest_inter_segment_gap_minutes = 0
    split_shift_gap_count = 0

    previous_segment: ShiftSegment | None = None
    for segment in segments:
        scheduled_segment_minutes += _duration_minutes(segment.starts_at, segment.ends_at)

        if previous_segment is not None and segment.starts_at > previous_segment.ends_at:
            gap_minutes = _duration_minutes(previous_segment.ends_at, segment.starts_at)
            inter_segment_gap_minutes += gap_minutes
            longest_inter_segment_gap_minutes = max(longest_inter_segment_gap_minutes, gap_minutes)
            split_shift_gap_count += 1
        previous_segment = segment

        breaks = sorted(
            list(segment.breaks or []),
            key=lambda shift_break: (
                int(shift_break.sequence_no or 0),
                shift_break.starts_at,
                shift_break.ends_at,
            ),
        )

        cursor = segment.starts_at
        for shift_break in breaks:
            longest_continuous_work_minutes = max(
                longest_continuous_work_minutes,
                _duration_minutes(cursor, shift_break.starts_at),
            )

            break_minutes = _duration_minutes(shift_break.starts_at, shift_break.ends_at)
            if shift_break.is_paid:
                paid_break_minutes += break_minutes
            else:
                unpaid_break_minutes += break_minutes

            break_type = ShiftBreakType(shift_break.break_type)
            if break_type is ShiftBreakType.meal:
                meal_break_minutes += break_minutes
                meal_break_count += 1
            elif break_type is ShiftBreakType.rest:
                rest_break_minutes += break_minutes
                rest_break_count += 1
            else:
                other_break_minutes += break_minutes
                other_break_count += 1
            cursor = shift_break.ends_at

        longest_continuous_work_minutes = max(
            longest_continuous_work_minutes,
            _duration_minutes(cursor, segment.ends_at),
        )

    total_break_minutes = paid_break_minutes + unpaid_break_minutes
    net_active_work_minutes = max(0, scheduled_segment_minutes - total_break_minutes)
    net_payable_minutes = max(0, scheduled_segment_minutes - unpaid_break_minutes)

    return {
        "has_structured_segments": has_structured_segments,
        "structure_source": structure_source,
        "segment_count": len(segments),
        "break_count": meal_break_count + rest_break_count + other_break_count,
        "meal_break_count": meal_break_count,
        "rest_break_count": rest_break_count,
        "other_break_count": other_break_count,
        "scheduled_span_minutes": scheduled_span_minutes,
        "scheduled_segment_minutes": scheduled_segment_minutes,
        "inter_segment_gap_minutes": inter_segment_gap_minutes,
        "split_shift_detected": split_shift_gap_count > 0,
        "split_shift_gap_count": split_shift_gap_count,
        "longest_inter_segment_gap_minutes": longest_inter_segment_gap_minutes,
        "paid_break_minutes": paid_break_minutes,
        "unpaid_break_minutes": unpaid_break_minutes,
        "total_break_minutes": total_break_minutes,
        "meal_break_minutes": meal_break_minutes,
        "rest_break_minutes": rest_break_minutes,
        "other_break_minutes": other_break_minutes,
        "net_active_work_minutes": net_active_work_minutes,
        "net_payable_minutes": net_payable_minutes,
        "longest_continuous_work_minutes": longest_continuous_work_minutes,
    }


def list_break_facts(shift: Shift) -> list[dict[str, object]]:
    segments, _structure_source = _normalized_segments_for_shift(shift)
    break_facts: list[dict[str, object]] = []

    for segment in segments:
        for shift_break in sorted(
            list(segment.breaks or []),
            key=lambda current_break: (
                int(current_break.sequence_no or 0),
                current_break.starts_at,
                current_break.ends_at,
            ),
        ):
            break_facts.append(
                {
                    "segment_sequence_no": int(segment.sequence_no or 0),
                    "break_sequence_no": int(shift_break.sequence_no or 0),
                    "break_type": ShiftBreakType(shift_break.break_type).value,
                    "is_paid": bool(shift_break.is_paid),
                    "starts_at": shift_break.starts_at,
                    "ends_at": shift_break.ends_at,
                    "duration_minutes": _duration_minutes(shift_break.starts_at, shift_break.ends_at),
                    "start_offset_minutes": _duration_minutes(shift.starts_at, shift_break.starts_at),
                    "end_offset_minutes": _duration_minutes(shift.starts_at, shift_break.ends_at),
                }
            )
    return break_facts


def _normalized_segments_for_shift(shift: Shift) -> tuple[list[ShiftSegment], str]:
    explicit_segments = _sorted_segments(shift.segments or [])
    if explicit_segments:
        return explicit_segments, "explicit"

    metadata_segments = _metadata_segments_for_shift(shift)
    if metadata_segments:
        return metadata_segments, "metadata"

    return [_synthetic_segment_for_shift(shift)], "synthetic"


def _metadata_segments_for_shift(shift: Shift) -> list[ShiftSegment]:
    shift_metadata = shift.shift_metadata if isinstance(shift.shift_metadata, Mapping) else {}
    for key in _SHIFT_STRUCTURE_METADATA_KEYS:
        raw_segments = shift_metadata.get(key)
        if not isinstance(raw_segments, list):
            continue
        segments = _segments_from_metadata_payload(shift, raw_segments)
        if segments:
            return segments
    return []


def _segments_from_metadata_payload(shift: Shift, raw_segments: list[object]) -> list[ShiftSegment]:
    segments: list[ShiftSegment] = []
    for segment_index, raw_segment in enumerate(raw_segments, start=1):
        if not isinstance(raw_segment, Mapping):
            return []
        starts_at = _datetime_from_metadata(raw_segment.get("starts_at"))
        ends_at = _datetime_from_metadata(raw_segment.get("ends_at"))
        if starts_at is None or ends_at is None or ends_at <= starts_at:
            return []

        segment = ShiftSegment(
            shift_id=shift.id,
            sequence_no=int(raw_segment.get("sequence_no") or segment_index),
            segment_type="work",
            starts_at=starts_at,
            ends_at=ends_at,
            segment_metadata=dict(raw_segment.get("segment_metadata") or {}),
        )
        segment.breaks = []
        raw_breaks = raw_segment.get("breaks")
        if raw_breaks is not None and not isinstance(raw_breaks, list):
            return []

        for break_index, raw_break in enumerate(raw_breaks or [], start=1):
            if not isinstance(raw_break, Mapping):
                return []
            break_type = str(raw_break.get("break_type") or "").strip().lower() or ShiftBreakType.other.value
            if break_type not in {member.value for member in ShiftBreakType}:
                return []
            break_starts_at = _datetime_from_metadata(raw_break.get("starts_at"))
            break_ends_at = _datetime_from_metadata(raw_break.get("ends_at"))
            if break_starts_at is None or break_ends_at is None or break_ends_at <= break_starts_at:
                return []
            segment.breaks.append(
                ShiftBreak(
                    shift_id=shift.id,
                    shift_segment_id=segment.id,
                    sequence_no=int(raw_break.get("sequence_no") or break_index),
                    break_type=break_type,
                    is_paid=bool(raw_break.get("is_paid")),
                    starts_at=break_starts_at,
                    ends_at=break_ends_at,
                    notes=str(raw_break.get("notes") or "") or None,
                    break_metadata=dict(raw_break.get("break_metadata") or {}),
                )
            )
        segments.append(segment)

    normalized_segments = _sorted_segments(segments)
    if not _metadata_segments_are_valid(shift, normalized_segments):
        return []
    return normalized_segments


def _metadata_segments_are_valid(shift: Shift, segments: list[ShiftSegment]) -> bool:
    if not segments:
        return False
    if segments[0].starts_at != shift.starts_at or segments[-1].ends_at != shift.ends_at:
        return False

    previous_segment_end: datetime | None = None
    for segment in segments:
        if segment.starts_at < shift.starts_at or segment.ends_at > shift.ends_at:
            return False
        if previous_segment_end is not None and segment.starts_at < previous_segment_end:
            return False
        previous_segment_end = segment.ends_at

        previous_break_end: datetime | None = None
        segment_duration_minutes = _duration_minutes(segment.starts_at, segment.ends_at)
        total_break_minutes = 0
        for shift_break in sorted(
            segment.breaks or [],
            key=lambda current_break: (
                int(current_break.sequence_no or 0),
                current_break.starts_at,
                current_break.ends_at,
            ),
        ):
            if shift_break.starts_at < segment.starts_at or shift_break.ends_at > segment.ends_at:
                return False
            if previous_break_end is not None and shift_break.starts_at < previous_break_end:
                return False
            previous_break_end = shift_break.ends_at
            total_break_minutes += _duration_minutes(shift_break.starts_at, shift_break.ends_at)
        if total_break_minutes >= segment_duration_minutes:
            return False
    return True


def _sorted_segments(segments: list[ShiftSegment]) -> list[ShiftSegment]:
    return sorted(
        list(segments or []),
        key=lambda segment: (
            int(segment.sequence_no or 0),
            segment.starts_at,
            segment.ends_at,
        ),
    )


def _synthetic_segment_for_shift(shift: Shift) -> ShiftSegment:
    segment = ShiftSegment(
        shift_id=shift.id,
        sequence_no=1,
        segment_type="work",
        starts_at=shift.starts_at,
        ends_at=shift.ends_at,
        segment_metadata={},
    )
    segment.breaks = []
    return segment


def _datetime_from_metadata(value: object | None) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _duration_minutes(start_at, end_at) -> int:
    return max(0, int(round((end_at - start_at).total_seconds() / 60.0)))
