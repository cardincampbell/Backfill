from __future__ import annotations

from app.models.common import ShiftLifecycleStatus, ShiftStaffingStatus, ShiftStatus
from app.models.scheduling import Shift


def test_shift_status_setter_maps_legacy_open_status_to_split_axes():
    shift = Shift(status=ShiftStatus.open)

    assert shift.lifecycle_status == ShiftLifecycleStatus.scheduled
    assert shift.staffing_status == ShiftStaffingStatus.open
    assert shift.status == ShiftStatus.open


def test_shift_status_getter_prefers_terminal_lifecycle_status_over_staffing_summary():
    shift = Shift(
        lifecycle_status=ShiftLifecycleStatus.cancelled,
        staffing_status=ShiftStaffingStatus.covered,
    )

    assert shift.status == ShiftStatus.cancelled
