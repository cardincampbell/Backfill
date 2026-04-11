from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, desc, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class FeedProjection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feed_projections"
    __table_args__ = (
        UniqueConstraint(
            "projection_name",
            "source_event_id",
            name="uq_feed_projections_projection_name_source_event_id",
        ),
        Index(
            "ix_feed_projections_projection_name_business_id_occurred_at_id",
            "projection_name",
            "business_id",
            desc("occurred_at"),
            desc("id"),
        ),
        Index(
            "ix_feed_projections_projection_name_business_location_occurred_at_id",
            "projection_name",
            "business_id",
            "location_id",
            desc("occurred_at"),
            desc("id"),
        ),
        Index(
            "ix_feed_projections_projection_name_event_type_occurred_at_id",
            "projection_name",
            "event_type",
            desc("occurred_at"),
            desc("id"),
        ),
        Index(
            "ix_feed_projections_projection_name_trace_id_occurred_at_id",
            "projection_name",
            "trace_id",
            desc("occurred_at"),
            desc("id"),
        ),
    )

    source_event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    projection_name: Mapped[str] = mapped_column(Text, nullable=False)
    business_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE")
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    compatibility_event_name: Mapped[Optional[str]] = mapped_column(String(120))
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column()
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_membership_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("memberships.id", ondelete="SET NULL")
    )
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(String(1024))
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    event_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    projection_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )


class ProjectionCursor(TimestampMixin, Base):
    __tablename__ = "projection_cursors"
    __table_args__ = (
        CheckConstraint(
            "((last_source_created_at IS NULL AND last_source_event_id IS NULL) "
            "OR (last_source_created_at IS NOT NULL AND last_source_event_id IS NOT NULL))",
            name="checkpoint_pair",
        ),
    )

    projection_name: Mapped[str] = mapped_column(Text, primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    last_source_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_source_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("platform_events.id", ondelete="SET NULL")
    )
    cursor_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'idle'"))
    last_run_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_run_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    cursor_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
