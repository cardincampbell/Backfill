from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app_v2.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app_v2.models.common import (
    RetellConversationType,
    SchedulerConnectionStatus,
    SchedulerProvider,
    SchedulerSyncEventStatus,
    SchedulerSyncJobStatus,
    SchedulerSyncRunStatus,
)


class SchedulerConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scheduler_connections"
    __table_args__ = (
        UniqueConstraint("location_id", name="uq_scheduler_connections_location_id"),
        Index("ix_scheduler_connections_business_id_provider", "business_id", "provider"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[SchedulerProvider] = mapped_column(
        Enum(SchedulerProvider, name="scheduler_provider"),
        nullable=False,
        server_default=SchedulerProvider.backfill_native.value,
    )
    provider_location_ref: Mapped[Optional[str]] = mapped_column(String(255))
    install_url: Mapped[Optional[str]] = mapped_column(String(512))
    status: Mapped[SchedulerConnectionStatus] = mapped_column(
        Enum(SchedulerConnectionStatus, name="scheduler_connection_status"),
        nullable=False,
        server_default=SchedulerConnectionStatus.pending.value,
    )
    writeback_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    credentials: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(255))
    secret_hint: Mapped[Optional[str]] = mapped_column(String(64))
    connection_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    last_roster_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_roster_sync_status: Mapped[Optional[str]] = mapped_column(String(32))
    last_schedule_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_schedule_sync_status: Mapped[Optional[str]] = mapped_column(String(32))
    last_event_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_rolling_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_daily_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_writeback_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_sync_error: Mapped[Optional[str]] = mapped_column(Text)

    business: Mapped["Business"] = relationship()
    location: Mapped["Location"] = relationship()
    events: Mapped[list["SchedulerEvent"]] = relationship(back_populates="connection")
    jobs: Mapped[list["SchedulerSyncJob"]] = relationship(back_populates="connection")


class SchedulerEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scheduler_events"
    __table_args__ = (
        UniqueConstraint("provider", "source_event_id", name="uq_scheduler_events_provider_source_event_id"),
        Index("ix_scheduler_events_connection_id_received_at", "connection_id", "received_at"),
    )

    connection_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("scheduler_connections.id", ondelete="SET NULL"))
    business_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("businesses.id", ondelete="SET NULL"))
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
    provider: Mapped[SchedulerProvider] = mapped_column(
        Enum(SchedulerProvider, name="scheduler_event_provider"),
        nullable=False,
    )
    source_event_id: Mapped[Optional[str]] = mapped_column(String(255))
    event_type: Mapped[Optional[str]] = mapped_column(String(120))
    event_scope: Mapped[Optional[str]] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[SchedulerSyncEventStatus] = mapped_column(
        Enum(SchedulerSyncEventStatus, name="scheduler_sync_event_status"),
        nullable=False,
        server_default=SchedulerSyncEventStatus.received.value,
    )
    error: Mapped[Optional[str]] = mapped_column(Text)

    connection: Mapped[Optional["SchedulerConnection"]] = relationship(back_populates="events")
    jobs: Mapped[list["SchedulerSyncJob"]] = relationship(back_populates="scheduler_event")


class SchedulerSyncJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scheduler_sync_jobs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_scheduler_sync_jobs_idempotency_key"),
        Index("ix_scheduler_sync_jobs_status_next_run_at", "status", "next_run_at"),
        Index("ix_scheduler_sync_jobs_connection_id_status", "connection_id", "status"),
    )

    connection_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("scheduler_connections.id", ondelete="SET NULL"))
    scheduler_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("scheduler_events.id", ondelete="SET NULL"))
    business_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("businesses.id", ondelete="SET NULL"))
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
    provider: Mapped[SchedulerProvider] = mapped_column(
        Enum(SchedulerProvider, name="scheduler_sync_job_provider"),
        nullable=False,
    )
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50")
    scope: Mapped[Optional[str]] = mapped_column(String(64))
    scope_ref: Mapped[Optional[str]] = mapped_column(String(255))
    window_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[SchedulerSyncJobStatus] = mapped_column(
        Enum(SchedulerSyncJobStatus, name="scheduler_sync_job_status"),
        nullable=False,
        server_default=SchedulerSyncJobStatus.queued.value,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255))

    connection: Mapped[Optional["SchedulerConnection"]] = relationship(back_populates="jobs")
    scheduler_event: Mapped[Optional["SchedulerEvent"]] = relationship(back_populates="jobs")
    runs: Mapped[list["SchedulerSyncRun"]] = relationship(back_populates="sync_job", cascade="all, delete-orphan")


class SchedulerSyncRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scheduler_sync_runs"
    __table_args__ = (
        Index("ix_scheduler_sync_runs_sync_job_id_started_at", "sync_job_id", "started_at"),
    )

    sync_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scheduler_sync_jobs.id", ondelete="CASCADE"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[SchedulerSyncRunStatus] = mapped_column(
        Enum(SchedulerSyncRunStatus, name="scheduler_sync_run_status"),
        nullable=False,
    )
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    error: Mapped[Optional[str]] = mapped_column(Text)

    sync_job: Mapped["SchedulerSyncJob"] = relationship(back_populates="runs")


class RetellConversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "retell_conversations"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_retell_conversations_external_id"),
        Index("ix_retell_conversations_shift_id_created_at", "shift_id", "created_at"),
        Index("ix_retell_conversations_offer_id_created_at", "coverage_offer_id", "created_at"),
    )

    business_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("businesses.id", ondelete="SET NULL"))
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
    coverage_case_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("coverage_cases.id", ondelete="SET NULL"))
    coverage_offer_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("coverage_offers.id", ondelete="SET NULL"))
    shift_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("shifts.id", ondelete="SET NULL"))
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    conversation_type: Mapped[RetellConversationType] = mapped_column(
        Enum(RetellConversationType, name="retell_conversation_type"),
        nullable=False,
    )
    event_type: Mapped[Optional[str]] = mapped_column(String(120))
    direction: Mapped[Optional[str]] = mapped_column(String(32))
    status: Mapped[Optional[str]] = mapped_column(String(64))
    agent_id: Mapped[Optional[str]] = mapped_column(String(255))
    phone_from: Mapped[Optional[str]] = mapped_column(String(24))
    phone_to: Mapped[Optional[str]] = mapped_column(String(24))
    disconnection_reason: Mapped[Optional[str]] = mapped_column(String(255))
    conversation_summary: Mapped[Optional[str]] = mapped_column(Text)
    transcript_text: Mapped[Optional[str]] = mapped_column(Text)
    transcript_items: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    analysis: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


from app_v2.models.business import Business, Location  # noqa: E402
from app_v2.models.coverage import CoverageCase, CoverageOffer  # noqa: E402
from app_v2.models.scheduling import Shift  # noqa: E402
from app_v2.models.workforce import Employee  # noqa: E402
