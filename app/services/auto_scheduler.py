from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.auto_scheduler import (
    ScheduleRun,
    ScheduleRunApply,
    ScheduleRunAssignment,
    ScheduleRunExplanation,
    ScheduleRunInput,
    ScheduleRunMetric,
    ScheduleRunProposedShift,
    ScheduleRunRejection,
)
from app.models.business import Business, Location
from app.models.common import (
    AssignmentStatus,
    EmployeeStatus,
    ScheduleApplyStatus,
    ScheduleRunStatus,
    ScheduleRunType,
    ShiftLifecycleStatus,
    ShiftStaffingStatus,
)
from app.models.scheduling import Shift, ShiftAssignment
from app.models.workforce import Employee, EmployeeLocation, EmployeeRole
from app.schemas.auto_scheduler import (
    GeneratedDemandPayload,
    ProposedShiftPayload,
    SchedulePolicyPayload,
    ScheduleRunInputContract,
)
from app.services import auto_scheduler_optimizer, shift_assignments
from app.services.schedule_weeks import effective_week_start_day

_DEFAULT_SAME_DAY_SECOND_SHIFT_ALLOWED = True
_DEFAULT_CROSS_LOCATION_SHIFT_COVERAGE_ALLOWED = False
_DEFAULT_LABOR_RULE_MODE = "soft_penalty"
_DEFAULT_FAIRNESS_MODE = "balanced_hours"
_DEFAULT_MAX_SOLVER_RUNTIME_SECONDS = 30
_USABLE_LOCATION_ACCESS_LEVELS = {"approved", "trusted"}
_COUNTED_ASSIGNMENT_STATUSES = {
    AssignmentStatus.proposed,
    AssignmentStatus.assigned,
    AssignmentStatus.accepted,
    AssignmentStatus.completed,
}
_AUTO_SCHEDULER_DEMAND_SOURCE_SYSTEM = "auto_scheduler_demand"


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
    coverage_settings = _mapping_value(business_settings, "coverage")
    auto_scheduler_settings = _mapping_value(business_settings, "auto_scheduler")

    return SchedulePolicyPayload(
        week_start_day=effective_week_start_day(
            business_settings=business_settings,
            location_settings=location_settings,
        ),
        publish_mode="draft_only",
        labor_rule_mode=_scheduler_choice(
            auto_scheduler_settings.get("labor_rule_mode"),
            allowed={"soft_penalty", "hard_block"},
            default=_DEFAULT_LABOR_RULE_MODE,
        ),
        fairness_mode=_scheduler_choice(
            auto_scheduler_settings.get("fairness_mode"),
            allowed={"balanced_hours"},
            default=_DEFAULT_FAIRNESS_MODE,
        ),
        same_day_second_shift_allowed=_bool_setting(
            coverage_settings.get("same_day_second_shift_allowed"),
            default=_DEFAULT_SAME_DAY_SECOND_SHIFT_ALLOWED,
        ),
        cross_location_shift_coverage_allowed=_bool_setting(
            coverage_settings.get("cross_location_shift_coverage_allowed"),
            default=_DEFAULT_CROSS_LOCATION_SHIFT_COVERAGE_ALLOWED,
        ),
        max_solver_runtime_seconds=_int_setting(
            auto_scheduler_settings.get("max_solver_runtime_seconds"),
            default=_DEFAULT_MAX_SOLVER_RUNTIME_SECONDS,
            minimum=1,
        ),
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


def build_schedule_run_inputs_from_loaded_scope(
    *,
    business_id: UUID,
    planning_window_start: datetime,
    planning_window_end: datetime,
    reliability_payload,
    shifts: Sequence[Shift],
    employees: Sequence[Employee],
    business_settings: Mapping[str, object] | None,
    location_id: UUID | None = None,
    location_settings: Mapping[str, object] | None = None,
    labor_payload: Mapping[str, object] | None = None,
    generated_demand_payload: Mapping[str, object] | GeneratedDemandPayload | None = None,
    source_metadata: Mapping[str, object] | None = None,
) -> tuple[ScheduleRunInputContract, str]:
    location_scope = [
        shift.location_id
        for shift in shifts
        if shift.location_id is not None and (location_id is None or shift.location_id == location_id)
    ]
    fixed_shift_rows = _shift_rows_for_optimizer(shifts=shifts, location_id=location_id)
    generated_demand = _normalized_generated_demand_payload(
        generated_demand_payload,
        location_id=location_id,
    )
    generated_shift_rows = _generated_shift_rows_for_optimizer(generated_demand)
    shift_rows = sorted(
        [*fixed_shift_rows, *generated_shift_rows],
        key=lambda row: (str(row.get("starts_at") or ""), str(row.get("shift_id") or "")),
    )
    draft_assignment_rows = _draft_assignment_rows(shifts=shifts, location_id=location_id)
    employee_role_rows = _employee_role_eligibility_rows(employees)
    employee_location_rows = _employee_location_eligibility_rows(employees)
    availability_exception_rows = _availability_exception_rows(employees)
    policy_payload = resolve_schedule_policy_payload(
        business_settings=business_settings,
        location_settings=location_settings,
    )
    eligible_employee_ids_by_shift = _eligible_employee_ids_by_shift(
        shifts=shift_rows,
        employees=employees,
    )
    employee_rows = _employee_rows_for_optimizer(employees)
    scope_payload = {
        "business_id": str(business_id),
        "location_id": str(location_id) if location_id is not None else None,
        "location_scope": [str(value) for value in sorted(set(location_scope), key=str)],
        "planning_window_start": planning_window_start.isoformat(),
        "planning_window_end": planning_window_end.isoformat(),
        "policy_version": "v1",
    }
    input_snapshot_hash = build_authoring_snapshot_hash(
        shifts=shift_rows,
        draft_assignments=draft_assignment_rows,
        employee_role_eligibility=employee_role_rows,
        employee_location_eligibility=employee_location_rows,
        availability_exceptions=availability_exception_rows,
        scope_payload=scope_payload,
    )
    inputs = ScheduleRunInputContract(
        shift_payload={"shifts": shift_rows},
        fixed_shift_payload={"shifts": fixed_shift_rows},
        generated_demand_payload=generated_demand,
        employee_payload={"employees": employee_rows},
        availability_payload={"eligible_employee_ids_by_shift": eligible_employee_ids_by_shift},
        policy_payload=policy_payload,
        labor_payload=dict(labor_payload or {}),
        reliability_payload=reliability_payload,
        reliability_snapshot_generated_at=reliability_payload.generated_at,
        reliability_snapshot_hash=reliability_payload.snapshot_hash,
        reliability_snapshot_version=reliability_payload.snapshot_version,
        source_metadata={
            "authoring_snapshot_hash": input_snapshot_hash,
            "shift_count": len(shift_rows),
            "fixed_shift_count": len(fixed_shift_rows),
            "generated_shift_count": len(generated_shift_rows),
            "employee_count": len(employee_rows),
            **dict(source_metadata or {}),
        },
    )
    return inputs, input_snapshot_hash


async def create_schedule_run(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None,
    planning_window_start: datetime,
    planning_window_end: datetime,
    inputs: ScheduleRunInputContract,
    input_snapshot_hash: str,
    run_type: ScheduleRunType = ScheduleRunType.draft_generate,
    optimizer_engine: str = "ortools_cp_sat_v1",
    objective_version: str = "v1",
    constraints_version: str = "v1",
    policy_version: str = "v1",
    input_snapshot_version: str = "v1",
    run_metadata: Mapping[str, object] | None = None,
) -> ScheduleRun:
    schedule_run = ScheduleRun(
        business_id=business_id,
        location_id=location_id,
        planning_window_start=planning_window_start,
        planning_window_end=planning_window_end,
        run_type=run_type,
        status=ScheduleRunStatus.queued,
        optimizer_engine=optimizer_engine,
        objective_version=objective_version,
        constraints_version=constraints_version,
        policy_version=policy_version,
        input_snapshot_version=input_snapshot_version,
        input_snapshot_hash=input_snapshot_hash,
        run_metadata=dict(run_metadata or {}),
    )
    session.add(schedule_run)
    await session.flush()

    schedule_run_input = ScheduleRunInput(
        schedule_run_id=schedule_run.id,
        shift_payload=inputs.shift_payload,
        fixed_shift_payload=inputs.fixed_shift_payload,
        generated_demand_payload=inputs.generated_demand_payload.model_dump(),
        employee_payload=inputs.employee_payload,
        availability_payload=inputs.availability_payload,
        policy_payload=inputs.policy_payload.model_dump(),
        labor_payload=inputs.labor_payload,
        reliability_payload=inputs.reliability_payload.model_dump(),
        reliability_snapshot_generated_at=inputs.reliability_snapshot_generated_at,
        reliability_snapshot_hash=inputs.reliability_snapshot_hash,
        reliability_snapshot_version=inputs.reliability_snapshot_version,
        source_metadata=inputs.source_metadata,
    )
    session.add(schedule_run_input)
    schedule_run.inputs = schedule_run_input
    schedule_run.proposed_shifts[:] = _proposed_shift_models_for_run(
        schedule_run,
        inputs.generated_demand_payload,
    )
    for proposed_shift in schedule_run.proposed_shifts:
        session.add(proposed_shift)
    await session.flush()
    return schedule_run


async def create_and_execute_schedule_run_for_scope(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None,
    planning_window_start: datetime,
    planning_window_end: datetime,
    source_metadata: Mapping[str, object] | None = None,
    optimizer: Callable[[ScheduleRunInputContract], Mapping[str, object]] | None = None,
) -> ScheduleRun:
    business = await _load_scope_business(session, business_id)
    if business is None:
        raise LookupError("business_not_found")

    location = await _load_scope_location(session, location_id) if location_id is not None else None
    if location_id is not None and location is None:
        raise LookupError("location_not_found")
    if location is not None and location.business_id != business_id:
        raise LookupError("location_not_found")

    generated_at = datetime.now(timezone.utc)
    shifts = await _load_scope_shifts(
        session,
        business_id=business_id,
        location_id=location_id,
        planning_window_start=planning_window_start,
        planning_window_end=planning_window_end,
    )
    employees = await _load_scope_employees(
        session,
        business_id=business_id,
        shifts=shifts,
    )
    reliability_payload = await _build_scope_reliability_payload(
        session,
        business_id=business_id,
        employee_ids=[employee.id for employee in employees],
        generated_at=generated_at,
    )
    labor_payload = await _build_scope_labor_payload(
        session,
        shifts=shifts,
        employees=employees,
        reference_time=generated_at,
    )
    inputs, input_snapshot_hash = build_schedule_run_inputs_from_loaded_scope(
        business_id=business_id,
        planning_window_start=planning_window_start,
        planning_window_end=planning_window_end,
        reliability_payload=reliability_payload,
        shifts=shifts,
        employees=employees,
        business_settings=business.settings if isinstance(business.settings, Mapping) else {},
        location_id=location_id,
        location_settings=location.settings if location is not None and isinstance(location.settings, Mapping) else {},
        labor_payload=labor_payload,
        source_metadata={
            "source": "auto_scheduler_scope_loader_v1",
            "generated_at": generated_at.isoformat(),
            **dict(source_metadata or {}),
        },
    )
    schedule_run = await create_schedule_run(
        session,
        business_id=business_id,
        location_id=location_id,
        planning_window_start=planning_window_start,
        planning_window_end=planning_window_end,
        inputs=inputs,
        input_snapshot_hash=input_snapshot_hash,
        run_metadata={
            "scope_shift_count": len(shifts),
            "scope_employee_count": len(employees),
            "source": "auto_scheduler_scope_loader_v1",
        },
    )
    return await execute_schedule_run(
        session,
        schedule_run.id,
        optimizer=optimizer,
    )


async def current_scope_snapshot_hash(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None,
    planning_window_start: datetime,
    planning_window_end: datetime,
) -> str:
    shifts = await _load_scope_shifts(
        session,
        business_id=business_id,
        location_id=location_id,
        planning_window_start=planning_window_start,
        planning_window_end=planning_window_end,
    )
    employees = await _load_scope_employees(
        session,
        business_id=business_id,
        shifts=shifts,
    )
    return build_authoring_snapshot_hash(
        shifts=_shift_rows_for_optimizer(shifts=shifts, location_id=location_id),
        draft_assignments=_draft_assignment_rows(shifts=shifts, location_id=location_id),
        employee_role_eligibility=_employee_role_eligibility_rows(employees),
        employee_location_eligibility=_employee_location_eligibility_rows(employees),
        availability_exceptions=_availability_exception_rows(employees),
        scope_payload=_scope_payload_for_hash(
            business_id=business_id,
            location_id=location_id,
            planning_window_start=planning_window_start,
            planning_window_end=planning_window_end,
            shifts=shifts,
        ),
    )


async def apply_schedule_run_from_live_scope(
    session: AsyncSession,
    schedule_run_id: UUID,
) -> ScheduleRunApply:
    schedule_run = await load_schedule_run(session, schedule_run_id)
    if schedule_run is None:
        raise LookupError("schedule_run_not_found")

    current_snapshot_hash = await current_scope_snapshot_hash(
        session,
        business_id=schedule_run.business_id,
        location_id=schedule_run.location_id,
        planning_window_start=schedule_run.planning_window_start,
        planning_window_end=schedule_run.planning_window_end,
    )
    return await apply_schedule_run_to_draft(
        session,
        schedule_run_id,
        current_snapshot_hash=current_snapshot_hash,
    )


def schedule_run_input_contract(schedule_run: ScheduleRun) -> ScheduleRunInputContract:
    run_inputs = schedule_run.inputs
    if run_inputs is None:
        raise ValueError("schedule_run_missing_inputs")

    return ScheduleRunInputContract.model_validate(
        {
            "shift_payload": run_inputs.shift_payload or {},
            "fixed_shift_payload": run_inputs.fixed_shift_payload or {},
            "generated_demand_payload": run_inputs.generated_demand_payload or {},
            "employee_payload": run_inputs.employee_payload or {},
            "availability_payload": run_inputs.availability_payload or {},
            "policy_payload": run_inputs.policy_payload or {},
            "labor_payload": run_inputs.labor_payload or {},
            "reliability_payload": run_inputs.reliability_payload or {},
            "reliability_snapshot_generated_at": run_inputs.reliability_snapshot_generated_at,
            "reliability_snapshot_hash": run_inputs.reliability_snapshot_hash,
            "reliability_snapshot_version": run_inputs.reliability_snapshot_version,
            "source_metadata": run_inputs.source_metadata or {},
        }
    )


async def execute_schedule_run(
    session: AsyncSession,
    schedule_run_id: UUID,
    *,
    optimizer: Callable[[ScheduleRunInputContract], Mapping[str, object]] | None = None,
) -> ScheduleRun:
    schedule_run = await load_schedule_run(session, schedule_run_id)
    if schedule_run is None:
        raise LookupError("schedule_run_not_found")

    if schedule_run.status == ScheduleRunStatus.completed:
        return schedule_run
    if schedule_run.status == ScheduleRunStatus.cancelled:
        raise ValueError("schedule_run_cancelled")

    optimizer_callable = optimizer or auto_scheduler_optimizer.optimize_schedule_inputs
    inputs = schedule_run_input_contract(schedule_run)

    await record_schedule_run_result(
        session,
        schedule_run,
        status=ScheduleRunStatus.running,
        started_at=datetime.now(timezone.utc),
    )

    try:
        result = dict(optimizer_callable(inputs))
    except Exception as exc:
        await record_schedule_run_result(
            session,
            schedule_run,
            status=ScheduleRunStatus.failed,
            run_metadata={
                "last_error_type": exc.__class__.__name__,
                "last_error_message": str(exc),
            },
            completed_at=datetime.now(timezone.utc),
        )
        raise

    await record_schedule_run_result(
        session,
        schedule_run,
        status=ScheduleRunStatus.completed,
        assignments=_sequence_mapping(result.get("assignments")),
        rejections=_sequence_mapping(result.get("rejections")),
        explanation=_mapping(result.get("explanation")),
        metrics=_mapping(result.get("metrics")),
        run_metadata={
            "optimizer_engine": schedule_run.optimizer_engine,
            "objective_version": schedule_run.objective_version,
            "constraints_version": schedule_run.constraints_version,
            "policy_version": schedule_run.policy_version,
        },
        completed_at=datetime.now(timezone.utc),
    )
    return schedule_run


async def load_schedule_run(
    session: AsyncSession,
    schedule_run_id: UUID,
) -> ScheduleRun | None:
    return await session.get(
        ScheduleRun,
        schedule_run_id,
        populate_existing=True,
        options=(
            selectinload(ScheduleRun.inputs),
            selectinload(ScheduleRun.proposed_shifts),
            selectinload(ScheduleRun.assignments),
            selectinload(ScheduleRun.rejections),
            selectinload(ScheduleRun.explanation),
            selectinload(ScheduleRun.metrics),
            selectinload(ScheduleRun.applies),
            selectinload(ScheduleRun.replay_runs),
        ),
    )


async def list_schedule_runs(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None = None,
    limit: int = 25,
    status: ScheduleRunStatus | str | None = None,
) -> list[ScheduleRun]:
    stmt = (
        select(ScheduleRun)
        .where(ScheduleRun.business_id == business_id)
        .order_by(ScheduleRun.created_at.desc(), ScheduleRun.id.desc())
        .limit(max(1, min(limit, 100)))
    )
    if location_id is not None:
        stmt = stmt.where(ScheduleRun.location_id == location_id)
    if status is not None:
        normalized_status = (
            status if isinstance(status, ScheduleRunStatus) else ScheduleRunStatus(str(status))
        )
        stmt = stmt.where(ScheduleRun.status == normalized_status)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def latest_schedule_run_for_scope(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None,
    planning_window_start: datetime,
    planning_window_end: datetime,
) -> ScheduleRun | None:
    stmt = (
        select(ScheduleRun.id)
        .where(
            ScheduleRun.business_id == business_id,
            ScheduleRun.planning_window_start == planning_window_start,
            ScheduleRun.planning_window_end == planning_window_end,
        )
        .order_by(ScheduleRun.created_at.desc(), ScheduleRun.id.desc())
        .limit(1)
    )
    if location_id is None:
        stmt = stmt.where(ScheduleRun.location_id.is_(None))
    else:
        stmt = stmt.where(ScheduleRun.location_id == location_id)
    result = await session.execute(stmt)
    schedule_run_id = result.scalar_one_or_none()
    if schedule_run_id is None:
        return None
    return await load_schedule_run(session, schedule_run_id)


async def get_schedule_run_detail(
    session: AsyncSession,
    schedule_run_id: UUID,
) -> ScheduleRun | None:
    return await load_schedule_run(session, schedule_run_id)


async def record_schedule_run_result(
    session: AsyncSession,
    schedule_run: ScheduleRun,
    *,
    status: ScheduleRunStatus | None = None,
    assignments: Sequence[Mapping[str, object]] | None = None,
    rejections: Sequence[Mapping[str, object]] | None = None,
    explanation: Mapping[str, object] | None = None,
    metrics: Mapping[str, object] | None = None,
    run_metadata: Mapping[str, object] | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> ScheduleRun:
    proposed_shifts_by_optimizer_id = {
        proposed_shift.optimizer_shift_id: proposed_shift
        for proposed_shift in (schedule_run.proposed_shifts or [])
    }
    if run_metadata:
        schedule_run.run_metadata = {
            **(schedule_run.run_metadata or {}),
            **dict(run_metadata),
        }
    if started_at is not None:
        schedule_run.started_at = started_at

    if assignments is not None:
        schedule_run.assignments[:] = []
        for item in assignments:
            proposed_shift = _proposed_shift_for_result_item(
                proposed_shifts_by_optimizer_id,
                item,
            )
            row = ScheduleRunAssignment(
                schedule_run_id=schedule_run.id,
                shift_id=None if proposed_shift is not None else item.get("shift_id"),
                proposed_shift_id=proposed_shift.id if proposed_shift is not None else item.get("proposed_shift_id"),
                employee_id=item.get("employee_id"),
                decision_score=Decimal(str(item.get("decision_score", "0"))),
                decision_rank=int(item.get("decision_rank", 0)),
                assignment_payload=_result_payload_with_demand_metadata(
                    dict(item.get("assignment_payload") or {}),
                    proposed_shift=proposed_shift,
                ),
            )
            session.add(row)
            schedule_run.assignments.append(row)

    if rejections is not None:
        schedule_run.rejections[:] = []
        for item in rejections:
            proposed_shift = _proposed_shift_for_result_item(
                proposed_shifts_by_optimizer_id,
                item,
            )
            row = ScheduleRunRejection(
                schedule_run_id=schedule_run.id,
                shift_id=None if proposed_shift is not None else item.get("shift_id"),
                proposed_shift_id=proposed_shift.id if proposed_shift is not None else item.get("proposed_shift_id"),
                employee_id=item.get("employee_id"),
                candidate_rank=int(item.get("candidate_rank", 0)),
                rejection_reason_codes=list(item.get("rejection_reason_codes") or []),
                score_payload=_result_payload_with_demand_metadata(
                    dict(item.get("score_payload") or {}),
                    proposed_shift=proposed_shift,
                ),
                constraint_failure_payload=dict(item.get("constraint_failure_payload") or {}),
            )
            session.add(row)
            schedule_run.rejections.append(row)

    if explanation is not None:
        current = schedule_run.explanation
        payload = dict(explanation)
        if current is None:
            current = ScheduleRunExplanation(
                schedule_run_id=schedule_run.id,
                summary_payload=dict(payload.get("summary_payload") or {}),
                fairness_payload=dict(payload.get("fairness_payload") or {}),
                overtime_payload=dict(payload.get("overtime_payload") or {}),
                coverage_payload=dict(payload.get("coverage_payload") or {}),
                unassigned_shift_payload=dict(payload.get("unassigned_shift_payload") or {}),
            )
            session.add(current)
            schedule_run.explanation = current
        else:
            current.summary_payload = dict(payload.get("summary_payload") or {})
            current.fairness_payload = dict(payload.get("fairness_payload") or {})
            current.overtime_payload = dict(payload.get("overtime_payload") or {})
            current.coverage_payload = dict(payload.get("coverage_payload") or {})
            current.unassigned_shift_payload = dict(payload.get("unassigned_shift_payload") or {})

    if metrics is not None:
        current_metric = schedule_run.metrics
        payload = dict(metrics)
        if current_metric is None:
            current_metric = ScheduleRunMetric(
                schedule_run_id=schedule_run.id,
                shift_count=int(payload.get("shift_count", 0)),
                assigned_shift_count=int(payload.get("assigned_shift_count", 0)),
                unassigned_shift_count=int(payload.get("unassigned_shift_count", 0)),
                candidate_considered_count=int(payload.get("candidate_considered_count", 0)),
                overtime_assignment_count=int(payload.get("overtime_assignment_count", 0)),
                fairness_spread_metrics=dict(payload.get("fairness_spread_metrics") or {}),
                solver_runtime_ms=int(payload.get("solver_runtime_ms", 0)),
                objective_value=_optional_decimal(payload.get("objective_value")),
            )
            session.add(current_metric)
            schedule_run.metrics = current_metric
        else:
            current_metric.shift_count = int(payload.get("shift_count", 0))
            current_metric.assigned_shift_count = int(payload.get("assigned_shift_count", 0))
            current_metric.unassigned_shift_count = int(payload.get("unassigned_shift_count", 0))
            current_metric.candidate_considered_count = int(payload.get("candidate_considered_count", 0))
            current_metric.overtime_assignment_count = int(payload.get("overtime_assignment_count", 0))
            current_metric.fairness_spread_metrics = dict(payload.get("fairness_spread_metrics") or {})
            current_metric.solver_runtime_ms = int(payload.get("solver_runtime_ms", 0))
            current_metric.objective_value = _optional_decimal(payload.get("objective_value"))

    if status is not None:
        schedule_run.status = status
        if status == ScheduleRunStatus.running and schedule_run.started_at is None:
            schedule_run.started_at = datetime.now(timezone.utc)
        if status in {ScheduleRunStatus.completed, ScheduleRunStatus.failed, ScheduleRunStatus.cancelled}:
            schedule_run.completed_at = completed_at or datetime.now(timezone.utc)

    await session.flush()
    return schedule_run


async def apply_schedule_run_to_draft(
    session: AsyncSession,
    schedule_run_id: UUID,
    *,
    current_snapshot_hash: str,
    apply_metadata: Mapping[str, object] | None = None,
) -> ScheduleRunApply:
    schedule_run = await load_schedule_run(session, schedule_run_id)
    if schedule_run is None:
        raise LookupError("schedule_run_not_found")

    existing_successful_apply = _existing_successful_apply(schedule_run)
    precheck = evaluate_schedule_run_apply(
        schedule_run_status=schedule_run.status,
        target_snapshot_hash=schedule_run.input_snapshot_hash,
        current_snapshot_hash=current_snapshot_hash,
        existing_successful_apply=existing_successful_apply,
    )
    if precheck.status == ScheduleApplyStatus.no_op and existing_successful_apply is not None:
        return existing_successful_apply

    if not schedule_run.assignments and not schedule_run.proposed_shifts:
        apply_record = ScheduleRunApply(
            schedule_run_id=schedule_run.id,
            business_id=schedule_run.business_id,
            location_id=schedule_run.location_id,
            planning_window_start=schedule_run.planning_window_start,
            planning_window_end=schedule_run.planning_window_end,
            status=ScheduleApplyStatus.no_op,
            target_snapshot_hash=schedule_run.input_snapshot_hash,
            current_snapshot_hash=current_snapshot_hash,
            stale_reason="no_schedule_run_assignments",
            apply_metadata=dict(apply_metadata or {}),
        )
        session.add(apply_record)
        await session.flush()
        return apply_record

    apply_record = ScheduleRunApply(
        schedule_run_id=schedule_run.id,
        business_id=schedule_run.business_id,
        location_id=schedule_run.location_id,
        planning_window_start=schedule_run.planning_window_start,
        planning_window_end=schedule_run.planning_window_end,
        status=precheck.status,
        target_snapshot_hash=schedule_run.input_snapshot_hash,
        current_snapshot_hash=current_snapshot_hash,
        stale_reason=precheck.stale_reason,
        apply_metadata=dict(apply_metadata or {}),
        applied_at=None,
    )
    session.add(apply_record)

    if not precheck.can_apply:
        await session.flush()
        return apply_record

    materialized_shifts = await _materialize_schedule_run_proposed_shifts(
        session,
        schedule_run=schedule_run,
        apply_record=apply_record,
    )
    applied_assignment_count = 0
    reused_assignment_count = 0
    replaced_assignment_count = 0
    for run_assignment in sorted(
        schedule_run.assignments,
        key=lambda item: (int(item.decision_rank or 0), item.created_at or datetime.min.replace(tzinfo=timezone.utc)),
    ):
        outcome = await _apply_schedule_run_assignment(
            session,
            schedule_run=schedule_run,
            apply_record=apply_record,
            run_assignment=run_assignment,
            materialized_shifts_by_proposed_id=materialized_shifts,
        )
        if outcome == "created":
            applied_assignment_count += 1
        elif outcome == "reused":
            reused_assignment_count += 1
        elif outcome == "replaced":
            replaced_assignment_count += 1

    post_apply_snapshot_hash = await current_scope_snapshot_hash(
        session,
        business_id=schedule_run.business_id,
        location_id=schedule_run.location_id,
        planning_window_start=schedule_run.planning_window_start,
        planning_window_end=schedule_run.planning_window_end,
    )
    apply_record.status = ScheduleApplyStatus.applied
    apply_record.applied_at = datetime.now(timezone.utc)
    apply_record.apply_metadata = {
        **(apply_record.apply_metadata or {}),
        "materialized_shift_count": len(materialized_shifts),
        "applied_assignment_count": applied_assignment_count,
        "reused_assignment_count": reused_assignment_count,
        "replaced_assignment_count": replaced_assignment_count,
        "post_apply_snapshot_hash": post_apply_snapshot_hash,
    }
    await session.flush()
    return apply_record


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
        existing_post_apply_hash = str(
            (
                getattr(existing_successful_apply, "apply_metadata", {}) or {}
            ).get("post_apply_snapshot_hash")
            or ""
        )
        existing_status = getattr(existing_successful_apply, "status", None)
        if (
            str(existing_status) == ScheduleApplyStatus.applied.value
            and existing_target == target_snapshot_hash
            and current_snapshot_hash in {existing_current, existing_post_apply_hash}
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


async def _materialize_schedule_run_proposed_shifts(
    session: AsyncSession,
    *,
    schedule_run: ScheduleRun,
    apply_record: ScheduleRunApply,
) -> dict[UUID, Shift]:
    materialized: dict[UUID, Shift] = {}
    for proposed_shift in sorted(
        schedule_run.proposed_shifts or [],
        key=lambda item: (item.starts_at, item.demand_key),
    ):
        if proposed_shift.applied_shift_id is not None:
            existing_shift = await _load_shift_for_apply(
                session,
                schedule_run.business_id,
                proposed_shift.applied_shift_id,
            )
            if existing_shift is not None:
                materialized[proposed_shift.id] = existing_shift
                continue

        if proposed_shift.location_id is None or proposed_shift.role_id is None:
            raise ValueError("proposed_shift_missing_links")

        created_shift = Shift(
            business_id=schedule_run.business_id,
            location_id=proposed_shift.location_id,
            role_id=proposed_shift.role_id,
            source_system=_AUTO_SCHEDULER_DEMAND_SOURCE_SYSTEM,
            source_shift_id=f"{schedule_run.id}:{proposed_shift.demand_key}",
            timezone=proposed_shift.timezone,
            starts_at=proposed_shift.starts_at,
            ends_at=proposed_shift.ends_at,
            lifecycle_status=ShiftLifecycleStatus.draft,
            staffing_status=ShiftStaffingStatus.open,
            seats_requested=proposed_shift.headcount,
            seats_filled=0,
            requires_manager_approval=proposed_shift.requires_manager_approval,
            premium_cents=proposed_shift.premium_cents,
            shift_metadata={
                "created_via": "auto_scheduler_demand",
                "schedule_run_id": str(schedule_run.id),
                "schedule_run_apply_id": str(apply_record.id),
                "schedule_run_proposed_shift_id": str(proposed_shift.id),
                "demand_key": proposed_shift.demand_key,
                "source_type": proposed_shift.source_type,
                "generation_version": proposed_shift.generation_version,
                **dict(proposed_shift.generation_payload or {}),
            },
        )
        session.add(created_shift)
        await session.flush()
        proposed_shift.applied_shift_id = created_shift.id
        materialized[proposed_shift.id] = created_shift
    return materialized


async def _apply_schedule_run_assignment(
    session: AsyncSession,
    *,
    schedule_run: ScheduleRun,
    apply_record: ScheduleRunApply,
    run_assignment: ScheduleRunAssignment,
    materialized_shifts_by_proposed_id: Mapping[UUID, Shift],
) -> str:
    if run_assignment.employee_id is None:
        raise ValueError("schedule_run_assignment_missing_links")

    if run_assignment.proposed_shift_id is not None:
        shift = materialized_shifts_by_proposed_id.get(run_assignment.proposed_shift_id)
        if shift is None:
            raise LookupError("schedule_run_proposed_shift_not_materialized")
    else:
        if run_assignment.shift_id is None:
            raise ValueError("schedule_run_assignment_missing_links")
        shift = await _load_shift_for_apply(session, schedule_run.business_id, run_assignment.shift_id)
        if shift is None:
            raise LookupError("schedule_run_shift_not_found")
        if shift.lifecycle_status != ShiftLifecycleStatus.draft:
            raise ValueError("schedule_run_apply_requires_draft_shift")

    employee = await _load_employee_for_apply(session, schedule_run.business_id, run_assignment.employee_id)
    if employee is None:
        raise LookupError("schedule_run_employee_not_found")
    _validate_employee_eligibility(employee, shift)

    current_assignment = shift_assignments.current_assignment(shift.assignments or [])
    if current_assignment is not None and current_assignment.assigned_via != "auto_scheduler":
        if current_assignment.employee_id == employee.id:
            return "reused"
        raise ValueError("manual_draft_assignment_locked")

    if current_assignment is not None and current_assignment.assigned_via == "auto_scheduler":
        if current_assignment.employee_id == employee.id:
            current_assignment.assignment_metadata = {
                **(current_assignment.assignment_metadata or {}),
                "schedule_run_id": str(schedule_run.id),
                "schedule_run_apply_id": str(apply_record.id),
                "decision_score": str(run_assignment.decision_score),
                "decision_rank": int(run_assignment.decision_rank or 0),
            }
            return "reused"
        current_assignment.status = AssignmentStatus.replaced
        current_assignment.assignment_metadata = {
            **(current_assignment.assignment_metadata or {}),
            "replaced_at": datetime.now(timezone.utc).isoformat(),
            "replaced_via": "auto_scheduler",
            "replaced_by_schedule_run_id": str(schedule_run.id),
            "replaced_by_schedule_run_apply_id": str(apply_record.id),
        }
        outcome = "replaced"
    else:
        outcome = "created"

    next_sequence_no = _next_assignment_sequence_no(shift)
    assignment = ShiftAssignment(
        shift_id=shift.id,
        employee_id=employee.id,
        assigned_via="auto_scheduler",
        status=AssignmentStatus.proposed,
        sequence_no=next_sequence_no,
        assignment_metadata={
            "employee_name": employee.full_name,
            "schedule_run_id": str(schedule_run.id),
            "schedule_run_apply_id": str(apply_record.id),
            "decision_score": str(run_assignment.decision_score),
            "decision_rank": int(run_assignment.decision_rank or 0),
        },
    )
    assignment.employee = employee
    session.add(assignment)
    shift.assignments.append(assignment)
    _recompute_draft_shift_state(shift)
    return outcome


async def _load_shift_for_apply(
    session: AsyncSession,
    business_id: UUID,
    shift_id: UUID,
) -> Shift | None:
    shift = await session.get(
        Shift,
        shift_id,
        populate_existing=True,
        options=(
            selectinload(Shift.assignments).selectinload(ShiftAssignment.employee),
            selectinload(Shift.role),
            selectinload(Shift.location),
        ),
    )
    if shift is None or shift.business_id != business_id:
        return None
    return shift


async def _load_employee_for_apply(
    session: AsyncSession,
    business_id: UUID,
    employee_id: UUID,
) -> Employee | None:
    employee = await session.get(
        Employee,
        employee_id,
        populate_existing=True,
        options=(
            selectinload(Employee.employee_roles).selectinload(EmployeeRole.role),
            selectinload(Employee.employee_locations).selectinload(EmployeeLocation.location),
        ),
    )
    if employee is None or employee.business_id != business_id:
        return None
    return employee


def _validate_employee_eligibility(employee: Employee, shift: Shift) -> None:
    if employee.status != EmployeeStatus.active:
        raise ValueError("employee_not_active")
    if shift.role_id not in {record.role_id for record in (employee.employee_roles or [])}:
        raise ValueError("employee_missing_shift_role")
    employee_location = next(
        (
            record
            for record in (employee.employee_locations or [])
            if record.location_id == shift.location_id
        ),
        None,
    )
    if employee_location is None:
        raise ValueError("employee_missing_location_eligibility")
    if employee_location.access_level not in _USABLE_LOCATION_ACCESS_LEVELS:
        raise ValueError("employee_location_not_usable")


def _recompute_draft_shift_state(shift: Shift) -> None:
    current_assignment = shift_assignments.current_assignment(shift.assignments or [])
    shift.seats_filled = 1 if current_assignment is not None else 0
    shift.staffing_status = (
        ShiftStaffingStatus.covered
        if current_assignment is not None
        else ShiftStaffingStatus.open
    )


def _next_assignment_sequence_no(shift: Shift) -> int:
    existing = [int(assignment.sequence_no or 0) for assignment in (shift.assignments or [])]
    return (max(existing) if existing else 0) + 1


def _existing_successful_apply(schedule_run: ScheduleRun) -> ScheduleRunApply | None:
    successful = [
        apply_record
        for apply_record in (schedule_run.applies or [])
        if apply_record.status == ScheduleApplyStatus.applied
    ]
    if not successful:
        return None
    return max(successful, key=lambda item: item.created_at or datetime.min.replace(tzinfo=timezone.utc))


def _normalized_generated_demand_payload(
    generated_demand_payload: Mapping[str, object] | GeneratedDemandPayload | None,
    *,
    location_id: UUID | None,
) -> GeneratedDemandPayload:
    if isinstance(generated_demand_payload, GeneratedDemandPayload):
        payload = generated_demand_payload
    elif generated_demand_payload is None:
        payload = GeneratedDemandPayload()
    else:
        payload = GeneratedDemandPayload.model_validate(generated_demand_payload)

    if location_id is None:
        return payload

    return GeneratedDemandPayload(
        proposed_shifts=[
            proposed_shift
            for proposed_shift in payload.proposed_shifts
            if proposed_shift.location_id == location_id
        ],
        metadata=dict(payload.metadata or {}),
    )


def _proposed_shift_models_for_run(
    schedule_run: ScheduleRun,
    generated_demand_payload: GeneratedDemandPayload,
) -> list[ScheduleRunProposedShift]:
    models: list[ScheduleRunProposedShift] = []
    for proposed_shift in generated_demand_payload.proposed_shifts:
        models.append(
            ScheduleRunProposedShift(
                schedule_run_id=schedule_run.id,
                location_id=proposed_shift.location_id,
                role_id=proposed_shift.role_id,
                demand_key=proposed_shift.demand_key,
                optimizer_shift_id=_optimizer_shift_id_for_demand_key(proposed_shift.demand_key),
                source_type=proposed_shift.source_type,
                generation_version=proposed_shift.generation_version,
                timezone=proposed_shift.timezone,
                starts_at=proposed_shift.starts_at,
                ends_at=proposed_shift.ends_at,
                headcount=proposed_shift.headcount,
                premium_cents=proposed_shift.premium_cents,
                requires_manager_approval=proposed_shift.requires_manager_approval,
                generation_payload=dict(proposed_shift.generation_payload or {}),
            )
        )
    return models


def _proposed_shift_for_result_item(
    proposed_shifts_by_optimizer_id: Mapping[str, ScheduleRunProposedShift],
    item: Mapping[str, object],
) -> ScheduleRunProposedShift | None:
    proposed_shift_id = item.get("proposed_shift_id")
    if proposed_shift_id is not None:
        for proposed_shift in proposed_shifts_by_optimizer_id.values():
            if str(proposed_shift.id) == str(proposed_shift_id):
                return proposed_shift
    shift_id = item.get("shift_id")
    if shift_id is None:
        return None
    return proposed_shifts_by_optimizer_id.get(str(shift_id))


def _result_payload_with_demand_metadata(
    payload: dict[str, object],
    *,
    proposed_shift: ScheduleRunProposedShift | None,
) -> dict[str, object]:
    if proposed_shift is None:
        return payload
    return {
        **payload,
        "demand_key": proposed_shift.demand_key,
        "source_type": proposed_shift.source_type,
        "proposed_shift_id": str(proposed_shift.id),
        "optimizer_shift_id": proposed_shift.optimizer_shift_id,
    }


def _mapping_value(
    payload: Mapping[str, object] | None,
    key: str,
) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        return {}
    value = payload.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def _scheduler_choice(value: object, *, allowed: set[str], default: str) -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in allowed:
            return normalized
    return default


def _bool_setting(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _int_setting(value: object, *, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= minimum else default


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence_mapping(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


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


def _optimizer_shift_id_for_demand_key(demand_key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"auto_scheduler_demand:{demand_key}"))


def _shift_rows_for_optimizer(
    *,
    shifts: Sequence[Shift],
    location_id: UUID | None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for shift in shifts:
        if shift.lifecycle_status != ShiftLifecycleStatus.draft:
            continue
        if location_id is not None and shift.location_id != location_id:
            continue
        current_assignment = shift_assignments.current_assignment(shift.assignments or [])
        if current_assignment is not None and current_assignment.assigned_via != "auto_scheduler":
            continue
        rows.append(
            {
                "shift_id": str(shift.id),
                "location_id": str(shift.location_id),
                "role_id": str(shift.role_id),
                "starts_at": shift.starts_at.isoformat(),
                "ends_at": shift.ends_at.isoformat(),
                "timezone": shift.timezone,
                "headcount": int(shift.seats_requested or 1),
                "premium_cents": int(shift.premium_cents or 0),
                "requires_manager_approval": bool(shift.requires_manager_approval),
            }
        )
    rows.sort(key=lambda row: (row["starts_at"], row["shift_id"]))
    return rows


def _generated_shift_rows_for_optimizer(
    generated_demand_payload: GeneratedDemandPayload,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for proposed_shift in generated_demand_payload.proposed_shifts:
        rows.append(
            {
                "shift_id": _optimizer_shift_id_for_demand_key(proposed_shift.demand_key),
                "location_id": str(proposed_shift.location_id),
                "role_id": str(proposed_shift.role_id),
                "starts_at": proposed_shift.starts_at.isoformat(),
                "ends_at": proposed_shift.ends_at.isoformat(),
                "timezone": proposed_shift.timezone,
                "headcount": proposed_shift.headcount,
                "premium_cents": proposed_shift.premium_cents,
                "requires_manager_approval": proposed_shift.requires_manager_approval,
                "demand_key": proposed_shift.demand_key,
                "source_type": proposed_shift.source_type,
            }
        )
    rows.sort(key=lambda row: (row["starts_at"], row["shift_id"]))
    return rows


def _draft_assignment_rows(
    *,
    shifts: Sequence[Shift],
    location_id: UUID | None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for shift in shifts:
        if location_id is not None and shift.location_id != location_id:
            continue
        if shift.lifecycle_status != ShiftLifecycleStatus.draft:
            continue
        for assignment in shift.assignments or []:
            if assignment.status in {AssignmentStatus.cancelled, AssignmentStatus.replaced, AssignmentStatus.declined}:
                continue
            rows.append(
                {
                    "assignment_id": str(assignment.id),
                    "shift_id": str(shift.id),
                    "employee_id": str(assignment.employee_id) if assignment.employee_id is not None else None,
                    "assigned_via": assignment.assigned_via,
                    "status": assignment.status.value,
                    "sequence_no": int(assignment.sequence_no or 0),
                }
            )
    return sorted(rows, key=lambda row: (row["shift_id"], row["sequence_no"], row["assignment_id"]))


def _employee_rows_for_optimizer(employees: Sequence[Employee]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for employee in employees:
        if employee.status != EmployeeStatus.active:
            continue
        rows.append(
            {
                "employee_id": str(employee.id),
                "role_ids": [str(role.role_id) for role in employee.employee_roles or []],
                "location_ids": [
                    str(location.location_id)
                    for location in employee.employee_locations or []
                    if location.access_level in _USABLE_LOCATION_ACCESS_LEVELS
                ],
                "assigned_hours": round(_employee_assigned_hours(employee), 4),
                "target_hours": round(_employee_target_hours(employee), 4),
            }
        )
    return sorted(rows, key=lambda row: row["employee_id"])


def _employee_role_eligibility_rows(employees: Sequence[Employee]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for employee in employees:
        for employee_role in employee.employee_roles or []:
            rows.append(
                {
                    "employee_id": str(employee.id),
                    "role_id": str(employee_role.role_id),
                    "is_primary": bool(employee_role.is_primary),
                }
            )
    return sorted(rows, key=lambda row: (row["employee_id"], row["role_id"]))


def _employee_location_eligibility_rows(employees: Sequence[Employee]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for employee in employees:
        for employee_location in employee.employee_locations or []:
            rows.append(
                {
                    "employee_id": str(employee.id),
                    "location_id": str(employee_location.location_id),
                    "access_level": employee_location.access_level,
                    "can_cover_last_minute": bool(employee_location.can_cover_last_minute),
                    "travel_radius_miles": employee_location.travel_radius_miles,
                }
            )
    return sorted(rows, key=lambda row: (row["employee_id"], row["location_id"]))


def _availability_exception_rows(employees: Sequence[Employee]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for employee in employees:
        for exception in employee.availability_exceptions or []:
            rows.append(
                {
                    "employee_id": str(employee.id),
                    "availability_exception_id": str(exception.id),
                    "starts_at": exception.starts_at.isoformat(),
                    "ends_at": exception.ends_at.isoformat(),
                    "exception_type": exception.exception_type,
                }
            )
    return sorted(rows, key=lambda row: (row["employee_id"], row["starts_at"], row["availability_exception_id"]))


def _eligible_employee_ids_by_shift(
    *,
    shifts: Sequence[Mapping[str, object]],
    employees: Sequence[Employee],
) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    employee_index = [employee for employee in employees if employee.status == EmployeeStatus.active]
    for shift_row in shifts:
        shift_id = str(shift_row["shift_id"])
        eligible_ids: list[str] = []
        for employee in employee_index:
            if not _employee_can_cover_shift(employee, shift_row):
                continue
            eligible_ids.append(str(employee.id))
        mapping[shift_id] = sorted(eligible_ids)
    return mapping


def _employee_can_cover_shift(employee: Employee, shift_row: Mapping[str, object]) -> bool:
    role_id = str(shift_row["role_id"])
    location_id = str(shift_row["location_id"])
    starts_at = datetime.fromisoformat(str(shift_row["starts_at"]))
    ends_at = datetime.fromisoformat(str(shift_row["ends_at"]))
    timezone_name = str(shift_row.get("timezone") or "UTC")

    if role_id not in {str(record.role_id) for record in employee.employee_roles or []}:
        return False
    employee_location = next(
        (
            record
            for record in employee.employee_locations or []
            if str(record.location_id) == location_id
        ),
        None,
    )
    if employee_location is None or employee_location.access_level not in _USABLE_LOCATION_ACCESS_LEVELS:
        return False
    return _employee_is_available_for_shift(
        employee,
        starts_at=starts_at,
        ends_at=ends_at,
        timezone_name=timezone_name,
    )


def _employee_is_available_for_shift(
    employee: Employee,
    *,
    starts_at: datetime,
    ends_at: datetime,
    timezone_name: str,
) -> bool:
    timezone = ZoneInfo(timezone_name)
    starts_local = starts_at.astimezone(timezone)
    ends_local = ends_at.astimezone(timezone)

    for exception in employee.availability_exceptions or []:
        overlaps = exception.starts_at < ends_at and exception.ends_at > starts_at
        if not overlaps:
            continue
        if exception.exception_type in {"unavailable", "blocked", "time_off"}:
            return False
        if exception.exception_type in {"available", "override_available"}:
            return True

    day_of_week = starts_local.weekday()
    for rule in employee.availability_rules or []:
        if rule.day_of_week != day_of_week:
            continue
        if rule.valid_from and starts_local.date() < rule.valid_from:
            continue
        if rule.valid_until and starts_local.date() > rule.valid_until:
            continue
        if rule.availability_type != "available":
            continue
        if _time_range_covers_shift(starts_local, ends_local, rule.start_local_time, rule.end_local_time):
            return True
    return False


def _time_range_covers_shift(starts_at_local: datetime, ends_at_local: datetime, rule_start, rule_end) -> bool:
    shift_start = starts_at_local.timetz().replace(tzinfo=None)
    shift_end = ends_at_local.timetz().replace(tzinfo=None)
    if rule_start <= rule_end:
        return rule_start <= shift_start and rule_end >= shift_end
    return shift_start >= rule_start or shift_end <= rule_end


def _employee_assigned_hours(employee: Employee) -> float:
    total = 0.0
    for assignment in employee.assignments or []:
        if assignment.status not in _COUNTED_ASSIGNMENT_STATUSES:
            continue
        shift = getattr(assignment, "shift", None)
        if shift is None or shift.starts_at is None or shift.ends_at is None:
            continue
        total += max((shift.ends_at - shift.starts_at).total_seconds() / 3600.0, 0.0)
    return total


def _employee_target_hours(employee: Employee) -> float:
    metadata = employee.employee_metadata if isinstance(employee.employee_metadata, Mapping) else {}
    target_hours = metadata.get("target_hours")
    try:
        return float(target_hours)
    except (TypeError, ValueError):
        return 0.0


def _scope_payload_for_hash(
    *,
    business_id: UUID,
    location_id: UUID | None,
    planning_window_start: datetime,
    planning_window_end: datetime,
    shifts: Sequence[Shift],
) -> dict[str, object]:
    location_scope = [
        shift.location_id
        for shift in shifts
        if shift.location_id is not None and (location_id is None or shift.location_id == location_id)
    ]
    return {
        "business_id": str(business_id),
        "location_id": str(location_id) if location_id is not None else None,
        "location_scope": [str(value) for value in sorted(set(location_scope), key=str)],
        "planning_window_start": planning_window_start.isoformat(),
        "planning_window_end": planning_window_end.isoformat(),
        "policy_version": "v1",
    }


async def _load_scope_business(session: AsyncSession, business_id: UUID) -> Business | None:
    return await session.get(Business, business_id)


async def _load_scope_location(session: AsyncSession, location_id: UUID) -> Location | None:
    return await session.get(Location, location_id)


async def _load_scope_shifts(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID | None,
    planning_window_start: datetime,
    planning_window_end: datetime,
) -> list[Shift]:
    stmt = (
        select(Shift)
        .where(
            Shift.business_id == business_id,
            Shift.lifecycle_status == ShiftLifecycleStatus.draft,
            Shift.starts_at >= planning_window_start,
            Shift.starts_at < planning_window_end,
        )
        .options(
            selectinload(Shift.assignments).selectinload(ShiftAssignment.employee),
            selectinload(Shift.role),
            selectinload(Shift.location),
        )
        .order_by(Shift.starts_at.asc(), Shift.id.asc())
    )
    if location_id is not None:
        stmt = stmt.where(Shift.location_id == location_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _load_scope_employees(
    session: AsyncSession,
    *,
    business_id: UUID,
    shifts: Sequence[Shift],
) -> list[Employee]:
    if not shifts:
        return []

    role_ids = sorted({shift.role_id for shift in shifts if shift.role_id is not None}, key=str)
    location_ids = sorted({shift.location_id for shift in shifts if shift.location_id is not None}, key=str)
    stmt = (
        select(Employee)
        .join(Employee.employee_roles)
        .join(Employee.employee_locations)
        .where(
            Employee.business_id == business_id,
            Employee.status == EmployeeStatus.active,
            EmployeeRole.role_id.in_(role_ids),
            EmployeeLocation.location_id.in_(location_ids),
            EmployeeLocation.access_level.in_(tuple(sorted(_USABLE_LOCATION_ACCESS_LEVELS))),
        )
        .options(
            selectinload(Employee.employee_roles).selectinload(EmployeeRole.role),
            selectinload(Employee.employee_locations).selectinload(EmployeeLocation.location),
            selectinload(Employee.availability_rules),
            selectinload(Employee.availability_exceptions),
            selectinload(Employee.assignments).selectinload(ShiftAssignment.shift),
        )
        .order_by(Employee.created_at.asc(), Employee.id.asc())
        .distinct()
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _build_scope_reliability_payload(
    session: AsyncSession,
    *,
    business_id: UUID,
    employee_ids: Sequence[UUID],
    generated_at: datetime,
):
    from app.services import reliability_engine

    if employee_ids:
        return await reliability_engine.build_pinned_reliability_snapshot_payload(
            session,
            business_id=business_id,
            employee_ids=employee_ids,
            generated_at=generated_at,
        )
    return reliability_engine.build_reliability_snapshot_payload(
        employee_snapshots=[],
        generated_at=generated_at,
        metadata={
            "business_id": str(business_id),
            "employee_count": 0,
        },
    )


async def _build_scope_labor_payload(
    session: AsyncSession,
    *,
    shifts: Sequence[Shift],
    employees: Sequence[Employee],
    reference_time: datetime,
) -> dict[str, object]:
    from app.services import labor_rules

    employee_rows: dict[str, dict[str, object]] = {
        str(employee.id): {
            "status": "unresolved",
            "source": "pending_per_shift_labor_projection",
        }
        for employee in employees
    }
    shift_rows: dict[str, dict[str, dict[str, object]]] = {}
    if not shifts or not employees:
        return {
            "employees": employee_rows,
            "employees_by_shift": shift_rows,
        }

    worst_projection_by_employee: dict[str, dict[str, object]] = {}
    for shift in shifts:
        profile = await labor_rules.runtime_resolved_profile(
            session,
            location=shift.location,
            business=None,
            as_of=reference_time,
        )
        if profile is None:
            shift_projections = {
                str(employee.id): labor_rules.evaluate_overtime_projection(
                    None,
                    candidate_shift=shift,
                    counted_intervals=(),
                    reference_time=reference_time,
                )
                for employee in employees
            }
        else:
            snapshots = await labor_rules.build_hours_snapshots(
                session,
                employees=employees,
                shift=shift,
                profile=profile,
                now=reference_time,
            )
            shift_projections = {}
            for employee in employees:
                snapshot = snapshots.get(employee.id)
                shift_projections[str(employee.id)] = labor_rules.evaluate_overtime_projection(
                    profile,
                    candidate_shift=shift,
                    counted_intervals=snapshot.counted_intervals if snapshot is not None else (),
                    reference_time=reference_time,
                )

        shift_rows[str(shift.id)] = shift_projections
        for employee_id, projection in shift_projections.items():
            existing = worst_projection_by_employee.get(employee_id)
            if existing is None or _labor_projection_rank(projection) > _labor_projection_rank(existing):
                worst_projection_by_employee[employee_id] = projection

    for employee_id, projection in worst_projection_by_employee.items():
        employee_rows[employee_id] = projection

    return {
        "employees": employee_rows,
        "employees_by_shift": shift_rows,
    }


def _labor_projection_rank(projection: Mapping[str, object]) -> tuple[int, float, float]:
    status = str(projection.get("status") or "").strip().lower()
    status_rank = {
        "high": 4,
        "elevated": 3,
        "watch": 2,
        "clear": 1,
        "unresolved": 0,
    }.get(status, 0)
    return (
        status_rank,
        float(projection.get("projected_dt_hours") or 0.0),
        float(projection.get("projected_ot_hours") or 0.0),
    )
