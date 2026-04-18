from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


class ReliabilityComponentPayload(BaseSchema):
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    sample_size: int = Field(ge=0)
    metrics: dict = Field(default_factory=dict)


class ReliabilityEmployeeSnapshotPayload(BaseSchema):
    employee_id: UUID
    overall_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    sample_size: int = Field(ge=0)
    attendance: ReliabilityComponentPayload
    punctuality: ReliabilityComponentPayload
    commitment: ReliabilityComponentPayload
    response_behavior: ReliabilityComponentPayload
    coverage_reliability: ReliabilityComponentPayload
    metadata: dict = Field(default_factory=dict)


class ReliabilitySnapshotPayload(BaseSchema):
    generated_at: datetime
    snapshot_hash: str
    snapshot_version: str
    employees: list[ReliabilityEmployeeSnapshotPayload] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class SchedulePolicyPayload(BaseSchema):
    week_start_day: Literal[
        "sunday",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
    ] = "monday"
    publish_mode: Literal["draft_only"] = "draft_only"
    labor_rule_mode: Literal["soft_penalty", "hard_block"] = "soft_penalty"
    fairness_mode: Literal["balanced_hours"] = "balanced_hours"
    same_day_second_shift_allowed: bool = True
    cross_location_shift_coverage_allowed: bool = False
    max_solver_runtime_seconds: int = Field(default=30, ge=1)
    objective_weights: dict = Field(default_factory=dict)
    hard_constraints: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class ScheduleRunInputContract(BaseSchema):
    shift_payload: dict = Field(default_factory=dict)
    employee_payload: dict = Field(default_factory=dict)
    availability_payload: dict = Field(default_factory=dict)
    policy_payload: SchedulePolicyPayload
    labor_payload: dict = Field(default_factory=dict)
    reliability_payload: ReliabilitySnapshotPayload
    reliability_snapshot_generated_at: datetime
    reliability_snapshot_hash: str
    reliability_snapshot_version: str
    source_metadata: dict = Field(default_factory=dict)


class ScheduleRunGenerateRequest(BaseSchema):
    business_id: UUID
    location_id: Optional[UUID] = None
    planning_window_start: datetime
    planning_window_end: datetime
    source_metadata: dict = Field(default_factory=dict)


class ScheduleRunRead(BaseSchema):
    id: UUID
    business_id: UUID
    location_id: Optional[UUID] = None
    planning_window_start: datetime
    planning_window_end: datetime
    run_type: str
    status: str
    optimizer_engine: str
    objective_version: str
    constraints_version: str
    policy_version: str
    input_snapshot_version: str
    input_snapshot_hash: str
    run_metadata: dict
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ScheduleRunInputRead(BaseSchema):
    shift_payload: dict
    employee_payload: dict
    availability_payload: dict
    policy_payload: dict
    labor_payload: dict
    reliability_payload: dict
    reliability_snapshot_generated_at: Optional[datetime] = None
    reliability_snapshot_hash: Optional[str] = None
    reliability_snapshot_version: Optional[str] = None
    source_metadata: dict


class ScheduleRunAssignmentRead(BaseSchema):
    id: UUID
    shift_id: Optional[UUID] = None
    employee_id: Optional[UUID] = None
    decision_score: float
    decision_rank: int
    assignment_payload: dict
    created_at: datetime
    updated_at: datetime


class ScheduleRunRejectionRead(BaseSchema):
    id: UUID
    shift_id: Optional[UUID] = None
    employee_id: Optional[UUID] = None
    candidate_rank: int
    rejection_reason_codes: list = Field(default_factory=list)
    score_payload: dict = Field(default_factory=dict)
    constraint_failure_payload: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ScheduleRunExplanationRead(BaseSchema):
    summary_payload: dict = Field(default_factory=dict)
    fairness_payload: dict = Field(default_factory=dict)
    overtime_payload: dict = Field(default_factory=dict)
    coverage_payload: dict = Field(default_factory=dict)
    unassigned_shift_payload: dict = Field(default_factory=dict)


class ScheduleRunMetricRead(BaseSchema):
    shift_count: int
    assigned_shift_count: int
    unassigned_shift_count: int
    candidate_considered_count: int
    overtime_assignment_count: int
    fairness_spread_metrics: dict = Field(default_factory=dict)
    solver_runtime_ms: int
    objective_value: Optional[float] = None


class ScheduleRunDetailRead(ScheduleRunRead):
    inputs: Optional[ScheduleRunInputRead] = None
    assignments: list[ScheduleRunAssignmentRead] = Field(default_factory=list)
    rejections: list[ScheduleRunRejectionRead] = Field(default_factory=list)
    explanation: Optional[ScheduleRunExplanationRead] = None
    metrics: Optional[ScheduleRunMetricRead] = None
    applies: list["ScheduleRunApplyRead"] = Field(default_factory=list)
    replay_run_ids: list[UUID] = Field(default_factory=list)


class ScheduleRunApplyRead(BaseSchema):
    id: UUID
    schedule_run_id: UUID
    business_id: UUID
    location_id: Optional[UUID] = None
    planning_window_start: datetime
    planning_window_end: datetime
    status: str
    target_snapshot_hash: str
    current_snapshot_hash: str
    stale_reason: Optional[str] = None
    apply_metadata: dict
    applied_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
