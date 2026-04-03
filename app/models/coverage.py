from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.common import (
    AuditActorType,
    CandidateSource,
    CoverageAttemptStatus,
    CoverageCaseStatus,
    CoverageRunStatus,
    OfferResponseChannel,
    OfferStatus,
    OutboxChannel,
    OutboxStatus,
)


class CoverageCase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "coverage_cases"
    __table_args__ = (
        Index("ix_coverage_cases_shift_id_status", "shift_id", "status"),
        Index("ix_coverage_cases_location_id_status", "location_id", "status"),
    )

    shift_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[CoverageCaseStatus] = mapped_column(
        Enum(CoverageCaseStatus, name="coverage_case_status"),
        nullable=False,
        server_default=CoverageCaseStatus.queued.value,
    )
    phase_target: Mapped[str] = mapped_column(String(32), nullable=False, server_default="phase_1")
    reason_code: Mapped[Optional[str]] = mapped_column(String(80))
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    requires_manager_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    triggered_by: Mapped[Optional[str]] = mapped_column(String(64))
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    case_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    shift: Mapped["Shift"] = relationship(back_populates="coverage_cases")
    runs: Mapped[list["CoverageCaseRun"]] = relationship(back_populates="coverage_case", cascade="all, delete-orphan")
    offers: Mapped[list["CoverageOffer"]] = relationship(back_populates="coverage_case", cascade="all, delete-orphan")


class CoverageCaseRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "coverage_case_runs"
    __table_args__ = (
        UniqueConstraint("coverage_case_id", "phase_no", name="uq_coverage_case_runs_case_id_phase_no"),
    )

    coverage_case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coverage_cases.id", ondelete="CASCADE"), nullable=False)
    phase_no: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[CoverageRunStatus] = mapped_column(
        Enum(CoverageRunStatus, name="coverage_run_status"),
        nullable=False,
        server_default=CoverageRunStatus.queued.value,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    run_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    coverage_case: Mapped["CoverageCase"] = relationship(back_populates="runs")
    candidates: Mapped[list["CoverageCandidate"]] = relationship(back_populates="coverage_case_run", cascade="all, delete-orphan")
    offers: Mapped[list["CoverageOffer"]] = relationship(back_populates="coverage_case_run")


class CoverageCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "coverage_candidates"
    __table_args__ = (
        UniqueConstraint("coverage_case_run_id", "employee_id", name="uq_coverage_candidates_run_id_employee_id"),
        Index("ix_coverage_candidates_employee_id_rank", "employee_id", "rank"),
    )

    coverage_case_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coverage_case_runs.id", ondelete="CASCADE"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[CandidateSource] = mapped_column(
        Enum(CandidateSource, name="candidate_source"),
        nullable=False,
        server_default=CandidateSource.phase_1.value,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    qualification_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="qualified")
    exclusion_reasons: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    scoring_factors: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    availability_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    candidate_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    coverage_case_run: Mapped["CoverageCaseRun"] = relationship(back_populates="candidates")
    employee: Mapped["Employee"] = relationship()
    offers: Mapped[list["CoverageOffer"]] = relationship(back_populates="coverage_candidate")


class CoverageOffer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "coverage_offers"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_coverage_offers_idempotency_key"),
        Index("ix_coverage_offers_employee_id_status", "employee_id", "status"),
    )

    coverage_case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coverage_cases.id", ondelete="CASCADE"), nullable=False)
    coverage_case_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("coverage_case_runs.id", ondelete="SET NULL"))
    coverage_candidate_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("coverage_candidates.id", ondelete="SET NULL"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[OutboxChannel] = mapped_column(
        Enum(OutboxChannel, name="coverage_offer_channel"),
        nullable=False,
    )
    status: Mapped[OfferStatus] = mapped_column(
        Enum(OfferStatus, name="coverage_offer_status"),
        nullable=False,
        server_default=OfferStatus.pending.value,
    )
    delivery_provider: Mapped[Optional[str]] = mapped_column(String(64))
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    declined_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    offer_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    coverage_case: Mapped["CoverageCase"] = relationship(back_populates="offers")
    coverage_case_run: Mapped[Optional["CoverageCaseRun"]] = relationship(back_populates="offers")
    coverage_candidate: Mapped[Optional["CoverageCandidate"]] = relationship(back_populates="offers")
    responses: Mapped[list["CoverageOfferResponse"]] = relationship(back_populates="coverage_offer", cascade="all, delete-orphan")
    attempts: Mapped[list["CoverageContactAttempt"]] = relationship(back_populates="coverage_offer", cascade="all, delete-orphan")


class CoverageOfferResponse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "coverage_offer_responses"
    __table_args__ = (
        Index("ix_coverage_offer_responses_offer_id_responded_at", "coverage_offer_id", "responded_at"),
    )

    coverage_offer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coverage_offers.id", ondelete="CASCADE"), nullable=False)
    response_channel: Mapped[OfferResponseChannel] = mapped_column(
        Enum(OfferResponseChannel, name="coverage_offer_response_channel"),
        nullable=False,
    )
    response_code: Mapped[Optional[str]] = mapped_column(String(64))
    response_text: Mapped[Optional[str]] = mapped_column(Text)
    response_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    coverage_offer: Mapped["CoverageOffer"] = relationship(back_populates="responses")


class CoverageContactAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "coverage_contact_attempts"
    __table_args__ = (
        Index("ix_coverage_contact_attempts_employee_id_requested_at", "employee_id", "requested_at"),
        Index("ix_coverage_contact_attempts_offer_id", "coverage_offer_id"),
    )

    coverage_offer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coverage_offers.id", ondelete="CASCADE"), nullable=False)
    coverage_case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coverage_cases.id", ondelete="CASCADE"), nullable=False)
    coverage_case_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("coverage_case_runs.id", ondelete="SET NULL"))
    outbox_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("outbox_events.id", ondelete="SET NULL"))
    shift_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[OutboxChannel] = mapped_column(
        Enum(OutboxChannel, name="coverage_attempt_channel"),
        nullable=False,
    )
    status: Mapped[CoverageAttemptStatus] = mapped_column(
        Enum(CoverageAttemptStatus, name="coverage_attempt_status"),
        nullable=False,
        server_default=CoverageAttemptStatus.pending.value,
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    delivery_provider: Mapped[Optional[str]] = mapped_column(String(64))
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(255))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    response_time_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    attempt_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    coverage_offer: Mapped["CoverageOffer"] = relationship(back_populates="attempts")
    coverage_case: Mapped["CoverageCase"] = relationship()
    coverage_case_run: Mapped[Optional["CoverageCaseRun"]] = relationship()
    outbox_event: Mapped[Optional["OutboxEvent"]] = relationship()
    shift: Mapped["Shift"] = relationship()
    location: Mapped["Location"] = relationship()
    employee: Mapped["Employee"] = relationship()


class OutboxEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_events_status_available_at", "status", "available_at"),
    )

    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    topic: Mapped[str] = mapped_column(String(120), nullable=False)
    channel: Mapped[OutboxChannel] = mapped_column(
        Enum(OutboxChannel, name="outbox_channel"),
        nullable=False,
    )
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus, name="outbox_status"),
        nullable=False,
        server_default=OutboxStatus.pending.value,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    available_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    result_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(Text)


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_business_id_occurred_at", "business_id", "occurred_at"),
        Index("ix_audit_logs_location_id_occurred_at", "location_id", "occurred_at"),
    )

    business_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("businesses.id", ondelete="SET NULL"))
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
    actor_type: Mapped[AuditActorType] = mapped_column(
        Enum(AuditActorType, name="audit_actor_type"),
        nullable=False,
    )
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_membership_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("memberships.id", ondelete="SET NULL"))
    event_name: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[Optional[uuid.UUID]] = mapped_column()
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(String(1024))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))


from app.models.business import Location, Role  # noqa: E402
from app.models.identity import Membership, User  # noqa: E402
from app.models.scheduling import Shift  # noqa: E402
from app.models.workforce import Employee  # noqa: E402
