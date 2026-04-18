from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import hashlib
import json
from uuid import UUID

from app.models.common import ScheduleApplyStatus, ScheduleRunStatus
from app.schemas.auto_scheduler import SchedulePolicyPayload
from app.services.schedule_weeks import effective_week_start_day

_DEFAULT_SAME_DAY_SECOND_SHIFT_ALLOWED = True
_DEFAULT_CROSS_LOCATION_SHIFT_COVERAGE_ALLOWED = False


@dataclass(frozen=True)
class ScheduleRunApplyPrecheckResult:
    status: ScheduleApplyStatus
    can_apply: bool
    reason_code: str
    stale_reason: str | None = None
    existing_apply_id: UUID | None = None


def stable_payload_json(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def stable_payload_hash(payload: Mapping[str, object]) -> str:
    return f"sha256:{hashlib.sha256(stable_payload_json(payload).encode('utf-8')).hexdigest()}"


def resolve_schedule_policy_payload(
    *,
    business_settings: Mapping[str, object] | None,
    location_settings: Mapping[str, object] | None = None,
    objective_weights: Mapping[str, object] | None = None,
    hard_constraints: Mapping[str, object] | None = None,
    metadata: Mapping[str, object] | None = None,
) -> SchedulePolicyPayload:
    coverage_settings = (
        business_settings.get("coverage")
        if isinstance(business_settings, Mapping)
        else None
    )
    coverage = dict(coverage_settings) if isinstance(coverage_settings, Mapping) else {}

    return SchedulePolicyPayload(
        week_start_day=effective_week_start_day(
            business_settings=business_settings,
            location_settings=location_settings,
        ),
        publish_mode="draft_only",
        labor_rule_mode="soft_penalty",
        fairness_mode="balanced_hours",
        same_day_second_shift_allowed=_bool_setting(
            coverage.get("same_day_second_shift_allowed"),
            default=_DEFAULT_SAME_DAY_SECOND_SHIFT_ALLOWED,
        ),
        cross_location_shift_coverage_allowed=_bool_setting(
            coverage.get("cross_location_shift_coverage_allowed"),
            default=_DEFAULT_CROSS_LOCATION_SHIFT_COVERAGE_ALLOWED,
        ),
        max_solver_runtime_seconds=30,
        objective_weights=dict(
            objective_weights
            or {
                "coverage_completeness": 1.0,
                "reliability": 1.0,
                "fairness": 1.0,
                "labor_pressure": 1.0,
            }
        ),
        hard_constraints=dict(
            hard_constraints
            or {
                "publish_mode": "draft_only",
                "manual_drafts_locked": True,
                "stale_apply_rejected": True,
            }
        ),
        metadata=dict(metadata or {}),
    )


def build_authoring_snapshot_payload(
    *,
    shifts: Iterable[Mapping[str, object]],
    draft_assignments: Iterable[Mapping[str, object]],
    employee_role_eligibility: Iterable[Mapping[str, object]],
    employee_location_eligibility: Iterable[Mapping[str, object]],
    availability_exceptions: Iterable[Mapping[str, object]],
    scope_payload: Mapping[str, object],
) -> dict[str, object]:
    return {
        "shifts": _sorted_rows(
            shifts,
            ("shift_id", "id"),
        ),
        "draft_assignments": _sorted_rows(
            draft_assignments,
            ("assignment_id", "id"),
        ),
        "employee_role_eligibility": _sorted_rows(
            employee_role_eligibility,
            ("employee_id", "role_id", "id"),
        ),
        "employee_location_eligibility": _sorted_rows(
            employee_location_eligibility,
            ("employee_id", "location_id", "id"),
        ),
        "availability_exceptions": _sorted_rows(
            availability_exceptions,
            ("employee_id", "availability_exception_id", "id"),
        ),
        "scope": _normalized_row(scope_payload),
    }


def build_authoring_snapshot_hash(
    *,
    shifts: Iterable[Mapping[str, object]],
    draft_assignments: Iterable[Mapping[str, object]],
    employee_role_eligibility: Iterable[Mapping[str, object]],
    employee_location_eligibility: Iterable[Mapping[str, object]],
    availability_exceptions: Iterable[Mapping[str, object]],
    scope_payload: Mapping[str, object],
) -> str:
    payload = build_authoring_snapshot_payload(
        shifts=shifts,
        draft_assignments=draft_assignments,
        employee_role_eligibility=employee_role_eligibility,
        employee_location_eligibility=employee_location_eligibility,
        availability_exceptions=availability_exceptions,
        scope_payload=scope_payload,
    )
    return stable_payload_hash(payload)


def evaluate_schedule_run_apply(
    *,
    schedule_run_status: ScheduleRunStatus | str,
    target_snapshot_hash: str,
    current_snapshot_hash: str,
    existing_successful_apply: object | None = None,
) -> ScheduleRunApplyPrecheckResult:
    if existing_successful_apply is not None:
        existing_target = str(getattr(existing_successful_apply, "target_snapshot_hash", "") or "")
        existing_current = str(getattr(existing_successful_apply, "current_snapshot_hash", "") or "")
        existing_status = getattr(existing_successful_apply, "status", None)
        if (
            str(existing_status) == ScheduleApplyStatus.applied.value
            and existing_target == target_snapshot_hash
            and existing_current == current_snapshot_hash
        ):
            return ScheduleRunApplyPrecheckResult(
                status=ScheduleApplyStatus.no_op,
                can_apply=False,
                reason_code="existing_successful_apply",
                existing_apply_id=getattr(existing_successful_apply, "id", None),
            )

    normalized_status = (
        schedule_run_status
        if isinstance(schedule_run_status, ScheduleRunStatus)
        else ScheduleRunStatus(str(schedule_run_status))
    )
    if normalized_status != ScheduleRunStatus.completed:
        return ScheduleRunApplyPrecheckResult(
            status=ScheduleApplyStatus.failed,
            can_apply=False,
            reason_code="schedule_run_not_completed",
        )

    if target_snapshot_hash != current_snapshot_hash:
        return ScheduleRunApplyPrecheckResult(
            status=ScheduleApplyStatus.stale_rejected,
            can_apply=False,
            reason_code="authoring_snapshot_changed",
            stale_reason="input_snapshot_hash_mismatch",
        )

    return ScheduleRunApplyPrecheckResult(
        status=ScheduleApplyStatus.applied,
        can_apply=True,
        reason_code="ready_to_apply",
    )


def _bool_setting(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _normalized_row(row: Mapping[str, object]) -> dict[str, object]:
    return {str(key): row[key] for key in sorted(row.keys(), key=str)}


def _sorted_rows(
    rows: Iterable[Mapping[str, object]],
    order_keys: tuple[str, ...],
) -> list[dict[str, object]]:
    normalized = [_normalized_row(row) for row in rows]
    return sorted(normalized, key=lambda item: _row_sort_key(item, order_keys))


def _row_sort_key(row: Mapping[str, object], order_keys: tuple[str, ...]) -> tuple[object, ...]:
    ordered_values = tuple(_sortable_value(row.get(key)) for key in order_keys)
    return ordered_values + (stable_payload_json(row),)


def _sortable_value(value: object) -> tuple[int, str]:
    if value is None:
        return (1, "")
    return (0, str(value))
