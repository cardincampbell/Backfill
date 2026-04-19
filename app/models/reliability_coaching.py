from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.common import (
    OutboxChannel,
    ReliabilityCoachingAttemptStatus,
    ReliabilityCoachingCaseStatus,
    ReliabilityCoachingDeliveryStatus,
)


class ReliabilityCoachingCase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reliability_coaching_cases"
    __table_args__ = (
        Index("ix_reliability_coaching_cases_business_employee_created_at", "business_id", "employee_id", "created_at"),
        Index("ix_reliability_coaching_cases_status_created_at", "case_status", "created_at"),
        Index(
            "uq_reliability_coaching_cases_active_employee",
            "business_id",
            "employee_id",
            unique=True,
            postgresql_where=text("case_status IN ('open', 'suppressed', 'escalated')"),
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_status: Mapped[ReliabilityCoachingCaseStatus] = mapped_column(
        Enum(ReliabilityCoachingCaseStatus, name="reliability_coaching_case_status"),
        nullable=False,
        server_default=ReliabilityCoachingCaseStatus.open.value,
    )
    delivery_status: Mapped[ReliabilityCoachingDeliveryStatus] = mapped_column(
        Enum(ReliabilityCoachingDeliveryStatus, name="reliability_coaching_delivery_status"),
        nullable=False,
        server_default=ReliabilityCoachingDeliveryStatus.pending.value,
    )
    coaching_style: Mapped[str] = mapped_column(String(32), nullable=False, server_default="supportive")
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="v1")
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="v1")
    trigger_metric: Mapped[str] = mapped_column(String(64), nullable=False, server_default="callout_count_rolling_7d")
    trigger_threshold: Mapped[int] = mapped_column(Integer, nullable=False, server_default="2")
    trigger_window_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="7")
    trigger_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    suppressed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    suppressed_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    suppression_reason_code: Mapped[Optional[str]] = mapped_column(String(64))
    suppression_note: Mapped[Optional[str]] = mapped_column(Text)
    suppression_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    case_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    business: Mapped["Business"] = relationship()
    employee: Mapped["Employee"] = relationship()
    suppressed_by_user: Mapped[Optional["User"]] = relationship()
    triggers: Mapped[list["ReliabilityCoachingTrigger"]] = relationship(
        back_populates="coaching_case",
        cascade="all, delete-orphan",
    )
    attempts: Mapped[list["ReliabilityCoachingAttempt"]] = relationship(
        back_populates="coaching_case",
        cascade="all, delete-orphan",
        order_by="ReliabilityCoachingAttempt.attempt_no.asc()",
    )
    outcomes: Mapped[list["ReliabilityCoachingOutcome"]] = relationship(
        back_populates="coaching_case",
        cascade="all, delete-orphan",
    )


class ReliabilityCoachingTrigger(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reliability_coaching_triggers"
    __table_args__ = (
        UniqueConstraint("reliability_event_id", name="uq_reliability_coaching_triggers_reliability_event_id"),
        Index("ix_reliability_coaching_triggers_case_id_occurred_at", "coaching_case_id", "occurred_at"),
    )

    coaching_case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reliability_coaching_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    reliability_event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reliability_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    shift_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("shifts.id", ondelete="SET NULL"),
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL"),
    )
    role_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"),
    )
    trigger_source: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    qualifying_callout_count: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    coaching_case: Mapped["ReliabilityCoachingCase"] = relationship(back_populates="triggers")
    reliability_event: Mapped["ReliabilityEvent"] = relationship()
    shift: Mapped[Optional["Shift"]] = relationship()
    location: Mapped[Optional["Location"]] = relationship()
    role: Mapped[Optional["Role"]] = relationship()


class ReliabilityCoachingAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reliability_coaching_attempts"
    __table_args__ = (
        Index("ix_reliability_coaching_attempts_case_id_attempt_no", "coaching_case_id", "attempt_no"),
        Index("ix_reliability_coaching_attempts_provider_conversation_id", "provider_conversation_id"),
        UniqueConstraint("outbox_event_id", name="uq_reliability_coaching_attempts_outbox_event_id"),
    )

    coaching_case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reliability_coaching_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    outbox_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("outbox_events.id", ondelete="SET NULL")
    )
    channel: Mapped[OutboxChannel] = mapped_column(
        Enum(OutboxChannel, name="reliability_coaching_channel"),
        nullable=False,
        server_default=OutboxChannel.voice.value,
    )
    status: Mapped[ReliabilityCoachingAttemptStatus] = mapped_column(
        Enum(ReliabilityCoachingAttemptStatus, name="reliability_coaching_attempt_status"),
        nullable=False,
        server_default=ReliabilityCoachingAttemptStatus.queued.value,
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[Optional[str]] = mapped_column(String(64))
    provider_conversation_id: Mapped[Optional[str]] = mapped_column(String(255))
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_eligible_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    prompt_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    attempt_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    coaching_case: Mapped["ReliabilityCoachingCase"] = relationship(back_populates="attempts")
    outbox_event: Mapped[Optional["OutboxEvent"]] = relationship()
    outcome: Mapped[Optional["ReliabilityCoachingOutcome"]] = relationship(
        back_populates="attempt",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ReliabilityCoachingOutcome(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reliability_coaching_outcomes"
    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_reliability_coaching_outcomes_attempt_id"),
        Index("ix_reliability_coaching_outcomes_case_id_recorded_at", "coaching_case_id", "recorded_at"),
    )

    coaching_case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reliability_coaching_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reliability_coaching_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    outcome_code: Mapped[str] = mapped_column(String(64), nullable=False)
    barrier_code: Mapped[Optional[str]] = mapped_column(String(64))
    availability_update_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    manager_followup_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    coaching_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    opt_out: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    coaching_case: Mapped["ReliabilityCoachingCase"] = relationship(back_populates="outcomes")
    attempt: Mapped["ReliabilityCoachingAttempt"] = relationship(back_populates="outcome")


from app.models.business import Business, Location, Role  # noqa: E402
from app.models.coverage import OutboxEvent  # noqa: E402
from app.models.identity import User  # noqa: E402
from app.models.reliability import ReliabilityEvent  # noqa: E402
from app.models.scheduling import Shift  # noqa: E402
from app.models.workforce import Employee  # noqa: E402
