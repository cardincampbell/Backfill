from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.common import AssignmentStatus
from app.models.scheduling import ShiftAssignment
from app.services import shift_assignments


def _assignment(
    status: AssignmentStatus,
    *,
    sequence_no: int,
    created_at: datetime,
    accepted_at: datetime | None = None,
) -> ShiftAssignment:
    return ShiftAssignment(
        id=uuid4(),
        shift_id=uuid4(),
        employee_id=uuid4(),
        assigned_via="coverage_offer",
        status=status,
        sequence_no=sequence_no,
        accepted_at=accepted_at,
        created_at=created_at,
        updated_at=created_at,
        assignment_metadata={},
    )


def test_current_assignment_prefers_accepted_assignment_over_newer_assigned_state():
    now = datetime.now(timezone.utc)
    accepted = _assignment(
        AssignmentStatus.accepted,
        sequence_no=1,
        created_at=now,
        accepted_at=now + timedelta(minutes=5),
    )
    newer_assigned = _assignment(
        AssignmentStatus.assigned,
        sequence_no=2,
        created_at=now + timedelta(minutes=10),
    )

    result = shift_assignments.current_assignment([accepted, newer_assigned])

    assert result is accepted


def test_current_assignment_ignores_removed_states():
    now = datetime.now(timezone.utc)
    cancelled = _assignment(
        AssignmentStatus.cancelled,
        sequence_no=3,
        created_at=now + timedelta(minutes=15),
    )
    declined = _assignment(
        AssignmentStatus.declined,
        sequence_no=2,
        created_at=now + timedelta(minutes=10),
    )
    assigned = _assignment(
        AssignmentStatus.assigned,
        sequence_no=1,
        created_at=now,
    )

    result = shift_assignments.current_assignment([cancelled, declined, assigned])

    assert result is assigned
