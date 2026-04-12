from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

from app.models.common import AssignmentStatus
from app.models.scheduling import ShiftAssignment

_REMOVED_ASSIGNMENT_STATUSES = {
    AssignmentStatus.cancelled,
    AssignmentStatus.declined,
    AssignmentStatus.replaced,
    AssignmentStatus.no_show,
}

_ASSIGNMENT_PRIORITY = {
    AssignmentStatus.accepted: 3,
    AssignmentStatus.completed: 3,
    AssignmentStatus.assigned: 2,
    AssignmentStatus.proposed: 1,
}


def is_current_owner_candidate(assignment: ShiftAssignment) -> bool:
    return assignment.status not in _REMOVED_ASSIGNMENT_STATUSES


def _assignment_sort_key(assignment: ShiftAssignment) -> tuple[int, datetime, int, datetime]:
    priority = _ASSIGNMENT_PRIORITY.get(assignment.status, 0)
    accepted_at = assignment.accepted_at or datetime.min.replace(tzinfo=timezone.utc)
    sequence_no = int(assignment.sequence_no or 0)
    created_at = assignment.created_at or datetime.min.replace(tzinfo=timezone.utc)
    return priority, accepted_at, sequence_no, created_at


def current_assignment(assignments: Iterable[ShiftAssignment] | None) -> ShiftAssignment | None:
    eligible = [assignment for assignment in (assignments or []) if is_current_owner_candidate(assignment)]
    if not eligible:
        return None
    return max(eligible, key=_assignment_sort_key)


def latest_assignment(assignments: Iterable[ShiftAssignment] | None) -> ShiftAssignment | None:
    all_assignments = list(assignments or [])
    if not all_assignments:
        return None
    return max(all_assignments, key=_assignment_sort_key)
