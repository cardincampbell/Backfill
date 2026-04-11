from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.common import AuditActorType


class PlatformEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "platform_events"
    __table_args__ = (
        Index("ix_platform_events_business_id_occurred_at", "business_id", "occurred_at"),
        Index("ix_platform_events_location_id_occurred_at", "location_id", "occurred_at"),
        Index("ix_platform_events_event_type_occurred_at", "event_type", "occurred_at"),
        Index("ix_platform_events_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_platform_events_trace_id", "trace_id"),
        Index("ix_platform_events_created_at_id", "created_at", "id"),
    )

    business_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("businesses.id", ondelete="SET NULL"))
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    compatibility_event_name: Mapped[Optional[str]] = mapped_column(String(120))
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column()
    actor_type: Mapped[AuditActorType] = mapped_column(
        Enum(AuditActorType, name="platform_event_actor_type"),
        nullable=False,
    )
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_membership_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("memberships.id", ondelete="SET NULL"))
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(String(1024))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
