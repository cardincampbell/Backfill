from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from statistics import mean
from uuid import UUID

from app.schemas.auto_scheduler import ReliabilityEmployeeSnapshotPayload, ScheduleRunInputContract

_DEFAULT_RELIABILITY_SCORE = 0.7
_DEFAULT_HEADCOUNT = 1
_MAX_REJECTIONS_PER_SHIFT = 3


def optimize_schedule_inputs(
    inputs: ScheduleRunInputContract,
) -> dict[str, object]:
    shifts = _normalized_shift_rows(inputs.shift_payload)
    employees = _normalized_employee_rows(inputs.employee_payload)
    reliability_index = _reliability_index(inputs.reliability_payload.employees)
    eligible_employee_ids_by_shift = _eligible_employee_ids_by_shift(inputs.availability_payload)

    assignments: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    candidate_considered_count = 0
    overtime_assignment_count = 0
    compliance_blocked_candidate_count = 0
    assigned_hours_by_employee = {
        employee_id: _as_float(row.get("assigned_hours"), default=0.0)
        for employee_id, row in employees.items()
    }

    for shift in shifts:
        shift_id = shift["shift_id"]
        headcount = int(shift.get("headcount") or _DEFAULT_HEADCOUNT)
        if headcount != 1:
            raise ValueError("single_seat_only_v1")

        eligible_ids = eligible_employee_ids_by_shift.get(shift_id, set(employees.keys()))
        candidate_rankings: list[tuple[float, dict[str, object], dict[str, object]]] = []
        shift_rejections: list[dict[str, object]] = []
        for employee_id in eligible_ids:
            employee = employees.get(employee_id)
            if employee is None:
                continue
            score_payload = _candidate_score_payload(
                shift=shift,
                employee=employee,
                reliability_snapshot=reliability_index.get(employee_id),
                labor_projection=_labor_projection_for_shift_employee(
                    inputs.labor_payload,
                    shift_id=shift_id,
                    employee_id=employee_id,
                ),
                compliance_evaluation=_compliance_evaluation_for_shift_employee(
                    inputs.compliance_payload,
                    shift_id=shift_id,
                    employee_id=employee_id,
                ),
                policy_labor_rule_mode=inputs.policy_payload.labor_rule_mode,
                policy_compliance_rule_mode=inputs.policy_payload.compliance_rule_mode,
                assigned_hours=assigned_hours_by_employee.get(employee_id, 0.0),
            )
            candidate_considered_count += 1
            if score_payload["qualified"] is False:
                if score_payload["would_violate_compliance"]:
                    compliance_blocked_candidate_count += 1
                shift_rejections.append(
                    {
                        "shift_id": shift_id,
                        "employee_id": employee_id,
                        "candidate_rank": len(shift_rejections) + 1,
                        "rejection_reason_codes": list(score_payload["rejection_reason_codes"]),
                        "score_payload": score_payload,
                        "constraint_failure_payload": {
                            "qualified": False,
                            "reason_codes": list(score_payload["rejection_reason_codes"]),
                        },
                    }
                )
                continue
            candidate_rankings.append((float(score_payload["total_score"]), employee, score_payload))

        candidate_rankings.sort(
            key=lambda item: (
                -item[0],
                -float(item[2]["reliability_score"]),
                str(item[1]["employee_id"]),
            )
        )

        if not candidate_rankings:
            rejections.extend(shift_rejections[:_MAX_REJECTIONS_PER_SHIFT])
            continue

        best_score, best_employee, best_payload = candidate_rankings[0]
        assignments.append(
            {
                "shift_id": shift_id,
                "employee_id": best_employee["employee_id"],
                "decision_score": round(best_score, 4),
                "decision_rank": 1,
                "assignment_payload": {
                    "shift_role_id": shift["role_id"],
                    "shift_location_id": shift["location_id"],
                    "reliability_score": best_payload["reliability_score"],
                    "labor_penalty": best_payload["labor_penalty"],
                    "compliance_penalty": best_payload["compliance_penalty"],
                    "compliance_status": best_payload["compliance_status"],
                    "blocking_rule_codes": best_payload["blocking_rule_codes"],
                    "warning_rule_codes": best_payload["warning_rule_codes"],
                    "fairness_adjustment": best_payload["fairness_adjustment"],
                    "scoring_components": best_payload["scoring_components"],
                },
            }
        )
        shift_hours = _shift_duration_hours(shift)
        assigned_hours_by_employee[best_employee["employee_id"]] = (
            assigned_hours_by_employee.get(best_employee["employee_id"], 0.0) + shift_hours
        )
        if best_payload["would_trigger_overtime"]:
            overtime_assignment_count += 1

        for rejection_rank, (_, employee, payload) in enumerate(
            candidate_rankings[1 : 1 + _MAX_REJECTIONS_PER_SHIFT],
            start=2,
        ):
            rejections.append(
                {
                    "shift_id": shift_id,
                    "employee_id": employee["employee_id"],
                    "candidate_rank": rejection_rank,
                    "rejection_reason_codes": ["lower_ranked_candidate"],
                    "score_payload": payload,
                    "constraint_failure_payload": {},
                }
            )
        remaining_slots = _MAX_REJECTIONS_PER_SHIFT - min(len(candidate_rankings) - 1, _MAX_REJECTIONS_PER_SHIFT)
        if remaining_slots > 0:
            rejections.extend(shift_rejections[:remaining_slots])

    assigned_shift_count = len(assignments)
    shift_count = len(shifts)
    unassigned_shift_ids = [
        shift["shift_id"]
        for shift in shifts
        if shift["shift_id"] not in {assignment["shift_id"] for assignment in assignments}
    ]
    fairness_metrics = _fairness_metrics(assigned_hours_by_employee)

    return {
        "assignments": assignments,
        "rejections": rejections,
        "explanation": {
            "summary_payload": {
                "shift_count": shift_count,
                "assigned_shift_count": assigned_shift_count,
                "unassigned_shift_count": len(unassigned_shift_ids),
                "optimizer_engine": "greedy_v1",
            },
            "fairness_payload": fairness_metrics,
            "overtime_payload": {
                "overtime_assignment_count": overtime_assignment_count,
                "labor_rule_mode": inputs.policy_payload.labor_rule_mode,
            },
            "compliance_payload": {
                "compliance_rule_mode": inputs.policy_payload.compliance_rule_mode,
                "blocked_candidate_count": compliance_blocked_candidate_count,
            },
            "coverage_payload": {
                "assigned_shift_ids": [assignment["shift_id"] for assignment in assignments],
            },
            "unassigned_shift_payload": {
                "shift_ids": unassigned_shift_ids,
            },
        },
        "metrics": {
            "shift_count": shift_count,
            "assigned_shift_count": assigned_shift_count,
            "unassigned_shift_count": len(unassigned_shift_ids),
            "candidate_considered_count": candidate_considered_count,
            "overtime_assignment_count": overtime_assignment_count,
            "fairness_spread_metrics": fairness_metrics,
            "solver_runtime_ms": 0,
            "objective_value": round(sum(float(item["decision_score"]) for item in assignments), 4),
        },
    }


def _normalized_shift_rows(payload: Mapping[str, object]) -> list[dict[str, object]]:
    rows = payload.get("shifts")
    if not isinstance(rows, list):
        return []
    normalized: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        shift_id = _uuid_from_value(row.get("shift_id"))
        location_id = _uuid_from_value(row.get("location_id"))
        role_id = _uuid_from_value(row.get("role_id"))
        starts_at = _datetime_from_value(row.get("starts_at"))
        ends_at = _datetime_from_value(row.get("ends_at"))
        if not all([shift_id, location_id, role_id, starts_at, ends_at]):
            continue
        normalized.append(
            {
                "shift_id": shift_id,
                "location_id": location_id,
                "role_id": role_id,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "headcount": int(row.get("headcount") or _DEFAULT_HEADCOUNT),
            }
        )
    return sorted(normalized, key=lambda row: (row["starts_at"], row["shift_id"]))


def _normalized_employee_rows(payload: Mapping[str, object]) -> dict[UUID, dict[str, object]]:
    rows = payload.get("employees")
    if not isinstance(rows, list):
        return {}
    normalized: dict[UUID, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        employee_id = _uuid_from_value(row.get("employee_id"))
        if employee_id is None:
            continue
        normalized[employee_id] = {
            "employee_id": employee_id,
            "role_ids": {role_id for role_id in _uuid_list(row.get("role_ids"))},
            "location_ids": {location_id for location_id in _uuid_list(row.get("location_ids"))},
            "assigned_hours": _as_float(row.get("assigned_hours"), default=0.0),
            "target_hours": _as_float(row.get("target_hours"), default=0.0),
        }
    return normalized


def _eligible_employee_ids_by_shift(payload: Mapping[str, object]) -> dict[UUID, set[UUID]]:
    mapping = payload.get("eligible_employee_ids_by_shift")
    if not isinstance(mapping, Mapping):
        return {}
    normalized: dict[UUID, set[UUID]] = {}
    for raw_shift_id, raw_employee_ids in mapping.items():
        shift_id = _uuid_from_value(raw_shift_id)
        if shift_id is None or not isinstance(raw_employee_ids, list):
            continue
        normalized[shift_id] = {employee_id for employee_id in _uuid_list(raw_employee_ids)}
    return normalized


def _labor_projection_by_employee(payload: Mapping[str, object]) -> dict[UUID, dict[str, object]]:
    mapping = payload.get("employees")
    if not isinstance(mapping, Mapping):
        return {}
    normalized: dict[UUID, dict[str, object]] = {}
    for raw_employee_id, raw_projection in mapping.items():
        employee_id = _uuid_from_value(raw_employee_id)
        if employee_id is None or not isinstance(raw_projection, Mapping):
            continue
        normalized[employee_id] = dict(raw_projection)
    return normalized


def _labor_projection_for_shift_employee(
    payload: Mapping[str, object],
    *,
    shift_id: UUID,
    employee_id: UUID,
) -> dict[str, object] | None:
    raw_shift_mapping = payload.get("employees_by_shift")
    if isinstance(raw_shift_mapping, Mapping):
        raw_shift_payload = raw_shift_mapping.get(str(shift_id)) or raw_shift_mapping.get(shift_id)
        if isinstance(raw_shift_payload, Mapping):
            raw_projection = raw_shift_payload.get(str(employee_id)) or raw_shift_payload.get(employee_id)
            if isinstance(raw_projection, Mapping):
                return dict(raw_projection)
    return _labor_projection_by_employee(payload).get(employee_id)


def _compliance_evaluation_for_shift_employee(
    payload: Mapping[str, object],
    *,
    shift_id: UUID,
    employee_id: UUID,
) -> dict[str, object] | None:
    raw_shift_mapping = payload.get("employees_by_shift")
    if isinstance(raw_shift_mapping, Mapping):
        raw_shift_payload = raw_shift_mapping.get(str(shift_id)) or raw_shift_mapping.get(shift_id)
        if isinstance(raw_shift_payload, Mapping):
            raw_evaluation = raw_shift_payload.get(str(employee_id)) or raw_shift_payload.get(employee_id)
            if isinstance(raw_evaluation, Mapping):
                return dict(raw_evaluation)
    mapping = payload.get("employees")
    if not isinstance(mapping, Mapping):
        return None
    raw_evaluation = mapping.get(str(employee_id)) or mapping.get(employee_id)
    if isinstance(raw_evaluation, Mapping):
        return dict(raw_evaluation)
    return None


def _reliability_index(
    employee_snapshots: list[ReliabilityEmployeeSnapshotPayload],
) -> dict[UUID, ReliabilityEmployeeSnapshotPayload]:
    return {snapshot.employee_id: snapshot for snapshot in employee_snapshots}


def _candidate_score_payload(
    *,
    shift: Mapping[str, object],
    employee: Mapping[str, object],
    reliability_snapshot: ReliabilityEmployeeSnapshotPayload | None,
    labor_projection: Mapping[str, object] | None,
    compliance_evaluation: Mapping[str, object] | None,
    policy_labor_rule_mode: str,
    policy_compliance_rule_mode: str,
    assigned_hours: float,
) -> dict[str, object]:
    rejection_reason_codes: list[str] = []
    if shift["role_id"] not in employee["role_ids"]:
        rejection_reason_codes.append("employee_missing_shift_role")
    if shift["location_id"] not in employee["location_ids"]:
        rejection_reason_codes.append("employee_missing_location_eligibility")

    reliability_score = (
        float(reliability_snapshot.overall_score)
        if reliability_snapshot is not None
        else _DEFAULT_RELIABILITY_SCORE
    )
    reliability_confidence = (
        float(reliability_snapshot.confidence)
        if reliability_snapshot is not None
        else 0.0
    )
    compliance_status = str((compliance_evaluation or {}).get("status") or "clear").strip().lower()
    blocking_rule_codes = list((compliance_evaluation or {}).get("blocking_rule_codes") or [])
    warning_rule_codes = list((compliance_evaluation or {}).get("warning_rule_codes") or [])
    would_violate_compliance = bool((compliance_evaluation or {}).get("would_block"))
    would_trigger_overtime = bool((labor_projection or {}).get("would_trigger_overtime"))
    if would_trigger_overtime and policy_labor_rule_mode == "hard_block":
        rejection_reason_codes.append("labor_rule_hard_block")
    if would_violate_compliance and policy_compliance_rule_mode == "hard_block":
        rejection_reason_codes.append("compliance_rule_hard_block")
        rejection_reason_codes.extend(blocking_rule_codes)

    qualified = not rejection_reason_codes
    fairness_adjustment = _fairness_adjustment(
        assigned_hours=assigned_hours,
        target_hours=_as_float(employee.get("target_hours"), default=0.0),
    )
    labor_penalty = -20.0 if would_trigger_overtime and policy_labor_rule_mode == "soft_penalty" else 0.0
    compliance_penalty = (
        -15.0
        if (
            warning_rule_codes
            and any(code != "overtime_projection" for code in warning_rule_codes)
            and policy_compliance_rule_mode == "soft_penalty"
        )
        else 0.0
    )
    total_score = (
        (reliability_score * 100.0)
        + (reliability_confidence * 10.0)
        + fairness_adjustment
        + labor_penalty
        + compliance_penalty
    )

    return {
        "qualified": qualified,
        "rejection_reason_codes": rejection_reason_codes,
        "reliability_score": round(reliability_score, 4),
        "reliability_confidence": round(reliability_confidence, 4),
        "fairness_adjustment": round(fairness_adjustment, 4),
        "labor_penalty": round(labor_penalty, 4),
        "compliance_penalty": round(compliance_penalty, 4),
        "compliance_status": compliance_status,
        "blocking_rule_codes": blocking_rule_codes,
        "warning_rule_codes": warning_rule_codes,
        "would_violate_compliance": would_violate_compliance,
        "would_trigger_overtime": would_trigger_overtime,
        "total_score": round(total_score, 4),
        "scoring_components": {
            "reliability": round(reliability_score * 100.0, 4),
            "confidence": round(reliability_confidence * 10.0, 4),
            "fairness": round(fairness_adjustment, 4),
            "labor_penalty": round(labor_penalty, 4),
            "compliance_penalty": round(compliance_penalty, 4),
        },
    }


def _fairness_adjustment(*, assigned_hours: float, target_hours: float) -> float:
    if target_hours <= 0:
        return 0.0
    gap = target_hours - assigned_hours
    if gap >= 0:
        return min(gap, 8.0) * 1.5
    return max(gap, -8.0) * 1.5


def _fairness_metrics(assigned_hours_by_employee: Mapping[UUID, float]) -> dict[str, float]:
    if not assigned_hours_by_employee:
        return {"min_hours": 0.0, "max_hours": 0.0, "avg_hours": 0.0}
    values = list(assigned_hours_by_employee.values())
    return {
        "min_hours": round(min(values), 4),
        "max_hours": round(max(values), 4),
        "avg_hours": round(mean(values), 4),
    }


def _shift_duration_hours(shift: Mapping[str, object]) -> float:
    starts_at = shift["starts_at"]
    ends_at = shift["ends_at"]
    return round((ends_at - starts_at).total_seconds() / 3600.0, 4)


def _uuid_list(values: object) -> list[UUID]:
    if not isinstance(values, list):
        return []
    parsed: list[UUID] = []
    for value in values:
        item = _uuid_from_value(value)
        if item is not None:
            parsed.append(item)
    return parsed


def _uuid_from_value(value: object) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


def _datetime_from_value(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _as_float(value: object, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
