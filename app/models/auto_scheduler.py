from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.common import ScheduleApplyStatus, ScheduleRunStatus, ScheduleRunType

if TYPE_CHECKING:
    from app.models.business import Business, Location, Role
    from app.models.scheduling import Shift
    from app.models.workforce import Employee


class ScheduleRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "schedule_runs"
    __table_args__ = (
        Index("ix_schedule_runs_business_id_created_at", "business_id", "created_at"),
        Index("ix_schedule_runs_location_id_created_at", "location_id", "created_at"),
        Index("ix_schedule_runs_status_created_at", "status", "created_at"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    planning_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    planning_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    run_type: Mapped[ScheduleRunType] = mapped_column(
        Enum(ScheduleRunType, name="schedule_run_type"),
        nullable=False,
        server_default=ScheduleRunType.draft_generate.value,
    )
    status: Mapped[ScheduleRunStatus] = mapped_column(
        Enum(ScheduleRunStatus, name="schedule_run_status"),
        nullable=False,
        server_default=ScheduleRunStatus.queued.value,
    )
    optimizer_engine: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default="ortools_cp_sat_v1",
    )
    objective_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="v1")
    constraints_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="v1")
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="v1")
    input_snapshot_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="v1")
    input_snapshot_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    run_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    business: Mapped["Business"] = relationship()
    location: Mapped[Optional["Location"]] = relationship()
    inputs: Mapped[Optional["ScheduleRunInput"]] = relationship(
        back_populates="schedule_run",
        cascade="all, delete-orphan",
        uselist=False,
    )
    proposed_shifts: Mapped[List["ScheduleRunProposedShift"]] = relationship(
        back_populates="schedule_run",
        cascade="all, delete-orphan",
    )
    assignments: Mapped[List["ScheduleRunAssignment"]] = relationship(
        back_populates="schedule_run",
        cascade="all, delete-orphan",
    )
    rejections: Mapped[List["ScheduleRunRejection"]] = relationship(
        back_populates="schedule_run",
        cascade="all, delete-orphan",
    )
    explanation: Mapped[Optional["ScheduleRunExplanation"]] = relationship(
        back_populates="schedule_run",
        cascade="all, delete-orphan",
        uselist=False,
    )
    metrics: Mapped[Optional["ScheduleRunMetric"]] = relationship(
        back_populates="schedule_run",
        cascade="all, delete-orphan",
        uselist=False,
    )
    applies: Mapped[List["ScheduleRunApply"]] = relationship(
        back_populates="schedule_run",
        cascade="all, delete-orphan",
    )
    replay_runs: Mapped[List["ReplayRun"]] = relationship(
        back_populates="schedule_run",
        cascade="all, delete-orphan",
    )


class ScheduleRunInput(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "schedule_run_inputs"
    __table_args__ = (
        UniqueConstraint("schedule_run_id", name="uq_schedule_run_inputs_schedule_run_id"),
    )

    schedule_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedule_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    shift_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    fixed_shift_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    generated_demand_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    employee_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    availability_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    policy_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    labor_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    reliability_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    reliability_snapshot_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reliability_snapshot_hash: Mapped[Optional[str]] = mapped_column(String(255))
    reliability_snapshot_version: Mapped[Optional[str]] = mapped_column(String(64))
    source_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    schedule_run: Mapped["ScheduleRun"] = relationship(back_populates="inputs")


class ScheduleRunProposedShift(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "schedule_run_proposed_shifts"
    __table_args__ = (
        Index("ix_schedule_run_proposed_shifts_schedule_run_id_starts_at", "schedule_run_id", "starts_at"),
        UniqueConstraint("schedule_run_id", "demand_key", name="uq_schedule_run_proposed_shifts_run_demand_key"),
        UniqueConstraint(
            "schedule_run_id",
            "optimizer_shift_id",
            name="uq_schedule_run_proposed_shifts_run_optimizer_shift_id",
        ),
    )

    schedule_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedule_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    applied_shift_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("shifts.id", ondelete="SET NULL")
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    role_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL")
    )
    demand_key: Mapped[str] = mapped_column(String(255), nullable=False)
    optimizer_shift_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, server_default="historical_pattern")
    generation_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="v1")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    headcount: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    premium_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    requires_manager_approval: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    generation_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    schedule_run: Mapped["ScheduleRun"] = relationship(back_populates="proposed_shifts")
    applied_shift: Mapped[Optional["Shift"]] = relationship()
    location: Mapped[Optional["Location"]] = relationship()
    role: Mapped[Optional["Role"]] = relationship()


class ScheduleRunAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "schedule_run_assignments"
    __table_args__ = (
        Index(
            "ix_schedule_run_assignments_schedule_run_id_decision_rank",
            "schedule_run_id",
            "decision_rank",
        ),
    )

    schedule_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedule_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    shift_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("shifts.id", ondelete="SET NULL")
    )
    proposed_shift_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("schedule_run_proposed_shifts.id", ondelete="SET NULL")
    )
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    decision_score: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    decision_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    assignment_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    schedule_run: Mapped["ScheduleRun"] = relationship(back_populates="assignments")
    shift: Mapped[Optional["Shift"]] = relationship()
    proposed_shift: Mapped[Optional["ScheduleRunProposedShift"]] = relationship()
    employee: Mapped[Optional["Employee"]] = relationship()


class ScheduleRunRejection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "schedule_run_rejections"
    __table_args__ = (
        Index(
            "ix_schedule_run_rejections_schedule_run_id_candidate_rank",
            "schedule_run_id",
            "candidate_rank",
        ),
    )

    schedule_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedule_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    shift_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("shifts.id", ondelete="SET NULL")
    )
    proposed_shift_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("schedule_run_proposed_shifts.id", ondelete="SET NULL")
    )
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    candidate_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    rejection_reason_codes: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        default=list,
    )
    score_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    constraint_failure_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    schedule_run: Mapped["ScheduleRun"] = relationship(back_populates="rejections")
    shift: Mapped[Optional["Shift"]] = relationship()
    proposed_shift: Mapped[Optional["ScheduleRunProposedShift"]] = relationship()
    employee: Mapped[Optional["Employee"]] = relationship()


class ScheduleRunExplanation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "schedule_run_explanations"
    __table_args__ = (
        UniqueConstraint("schedule_run_id", name="uq_schedule_run_explanations_schedule_run_id"),
    )

    schedule_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedule_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    summary_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    fairness_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    overtime_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    coverage_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    unassigned_shift_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    schedule_run: Mapped["ScheduleRun"] = relationship(back_populates="explanation")


class ScheduleRunMetric(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "schedule_run_metrics"
    __table_args__ = (
        UniqueConstraint("schedule_run_id", name="uq_schedule_run_metrics_schedule_run_id"),
    )

    schedule_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedule_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    shift_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    assigned_shift_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unassigned_shift_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    candidate_considered_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    overtime_assignment_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    fairness_spread_metrics: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    solver_runtime_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    objective_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4))

    schedule_run: Mapped["ScheduleRun"] = relationship(back_populates="metrics")


class ScheduleRunApply(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "schedule_run_applies"
    __table_args__ = (
        Index("ix_schedule_run_applies_schedule_run_id_created_at", "schedule_run_id", "created_at"),
        Index("ix_schedule_run_applies_status_created_at", "status", "created_at"),
    )

    schedule_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedule_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    planning_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    planning_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ScheduleApplyStatus] = mapped_column(
        Enum(ScheduleApplyStatus, name="schedule_apply_status"),
        nullable=False,
        server_default=ScheduleApplyStatus.queued.value,
    )
    target_snapshot_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    current_snapshot_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    stale_reason: Mapped[Optional[str]] = mapped_column(Text)
    apply_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    schedule_run: Mapped["ScheduleRun"] = relationship(back_populates="applies")
    business: Mapped["Business"] = relationship()
    location: Mapped[Optional["Location"]] = relationship()


class ReplayRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "replay_runs"
    __table_args__ = (
        Index("ix_replay_runs_schedule_run_id_created_at", "schedule_run_id", "created_at"),
        Index("ix_replay_runs_business_id_created_at", "business_id", "created_at"),
        Index("ix_replay_runs_status_created_at", "status", "created_at"),
    )

    schedule_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedule_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    planning_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    planning_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ScheduleRunStatus] = mapped_column(
        Enum(ScheduleRunStatus, name="schedule_run_status"),
        nullable=False,
        server_default=ScheduleRunStatus.queued.value,
    )
    comparison_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="v1")
    target_snapshot_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    actual_snapshot_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    actual_assignment_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    actual_outcome_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    metrics_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    replay_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    schedule_run: Mapped["ScheduleRun"] = relationship(back_populates="replay_runs")
    business: Mapped["Business"] = relationship()
    location: Mapped[Optional["Location"]] = relationship()
