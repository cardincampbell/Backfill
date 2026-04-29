from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.models.common import ShiftBreakType, ShiftSegmentType, ShiftStatus
from app.models.scheduling import Shift, ShiftBreak, ShiftSegment
from app.services import compliance_shift_facts


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
    return shift


def test_build_shift_structure_facts_infers_single_segment_when_none_are_defined():
    shift = _shift(
        starts_at=datetime(2026, 4, 21, 16, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 21, 23, 0, tzinfo=timezone.utc),
    )

    facts = compliance_shift_facts.build_shift_structure_facts(shift)

    assert facts["has_structured_segments"] is False
    assert facts["structure_source"] == "synthetic"
    assert facts["segment_count"] == 1
    assert facts["scheduled_span_minutes"] == 420
    assert facts["scheduled_segment_minutes"] == 420
    assert facts["inter_segment_gap_minutes"] == 0
    assert facts["total_break_minutes"] == 0
    assert facts["net_active_work_minutes"] == 420
    assert facts["net_payable_minutes"] == 420
    assert facts["split_shift_detected"] is False


def test_build_shift_structure_facts_summarizes_breaks_and_split_gaps():
    shift = _shift(
        starts_at=datetime(2026, 4, 21, 16, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 22, 1, 0, tzinfo=timezone.utc),
    )
    first_segment = ShiftSegment(
        shift_id=shift.id,
        sequence_no=1,
        segment_type=ShiftSegmentType.work,
        starts_at=datetime(2026, 4, 21, 16, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 21, 20, 0, tzinfo=timezone.utc),
        segment_metadata={},
    )
    first_segment.breaks = [
        ShiftBreak(
            shift_id=shift.id,
            shift_segment_id=first_segment.id,
            sequence_no=1,
            break_type=ShiftBreakType.rest,
            is_paid=True,
            starts_at=datetime(2026, 4, 21, 18, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 21, 18, 10, tzinfo=timezone.utc),
            notes=None,
            break_metadata={},
        )
    ]
    second_segment = ShiftSegment(
        shift_id=shift.id,
        sequence_no=2,
        segment_type=ShiftSegmentType.work,
        starts_at=datetime(2026, 4, 21, 21, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 22, 1, 0, tzinfo=timezone.utc),
        segment_metadata={},
    )
    second_segment.breaks = [
        ShiftBreak(
            shift_id=shift.id,
            shift_segment_id=second_segment.id,
            sequence_no=1,
            break_type=ShiftBreakType.meal,
            is_paid=False,
            starts_at=datetime(2026, 4, 21, 23, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 4, 21, 23, 30, tzinfo=timezone.utc),
            notes=None,
            break_metadata={},
        )
    ]
    shift.segments = [first_segment, second_segment]

    facts = compliance_shift_facts.build_shift_structure_facts(shift)

    assert facts["has_structured_segments"] is True
    assert facts["structure_source"] == "explicit"
    assert facts["segment_count"] == 2
    assert facts["break_count"] == 2
    assert facts["meal_break_count"] == 1
    assert facts["rest_break_count"] == 1
    assert facts["scheduled_span_minutes"] == 540
    assert facts["scheduled_segment_minutes"] == 480
    assert facts["inter_segment_gap_minutes"] == 60
    assert facts["split_shift_detected"] is True
    assert facts["split_shift_gap_count"] == 1
    assert facts["longest_inter_segment_gap_minutes"] == 60
    assert facts["paid_break_minutes"] == 10
    assert facts["unpaid_break_minutes"] == 30
    assert facts["total_break_minutes"] == 40
    assert facts["net_active_work_minutes"] == 440
    assert facts["net_payable_minutes"] == 450
    assert facts["longest_continuous_work_minutes"] == 120


def test_build_shift_structure_facts_reads_metadata_segments_when_rows_are_missing():
    shift = _shift(
        starts_at=datetime(2026, 4, 21, 16, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 21, 23, 0, tzinfo=timezone.utc),
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
                        "break_type": "meal",
                        "is_paid": False,
                        "starts_at": datetime(2026, 4, 21, 20, 0, tzinfo=timezone.utc).isoformat(),
                        "ends_at": datetime(2026, 4, 21, 20, 30, tzinfo=timezone.utc).isoformat(),
                        "notes": "meal",
                        "break_metadata": {"planned_by": "test"},
                    }
                ],
            }
        ]
    }

    facts = compliance_shift_facts.build_shift_structure_facts(shift)
    break_facts = compliance_shift_facts.list_break_facts(shift)

    assert facts["has_structured_segments"] is True
    assert facts["structure_source"] == "metadata"
    assert facts["segment_count"] == 1
    assert facts["meal_break_count"] == 1
    assert facts["unpaid_break_minutes"] == 30
    assert facts["net_payable_minutes"] == 390
    assert len(break_facts) == 1
    assert break_facts[0]["break_type"] == "meal"
