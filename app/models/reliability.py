from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ReliabilityEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "reliability_events"
    __table_args__ = (
        Index("ix_reliability_events_business_id_occurred_at", "business_id", "occurred_at"),
        Index("ix_reliability_events_employee_id_occurred_at", "employee_id", "occurred_at"),
        Index("ix_reliability_events_event_type_occurred_at", "event_type", "occurred_at"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
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
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    event_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    business: Mapped["Business"] = relationship()
    employee: Mapped["Employee"] = relationship()
    shift: Mapped[Optional["Shift"]] = relationship()
    location: Mapped[Optional["Location"]] = relationship()
    role: Mapped[Optional["Role"]] = relationship()


class ReliabilitySnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reliability_snapshots"
    __table_args__ = (
        Index("ix_reliability_snapshots_business_id_snapshot_at", "business_id", "snapshot_at"),
        Index("ix_reliability_snapshots_employee_id_snapshot_at", "employee_id", "snapshot_at"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, server_default="0")
    attendance_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, server_default="0.7000")
    punctuality_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, server_default="0.7000")
    commitment_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, server_default="0.7000")
    response_behavior_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, server_default="0.7000")
    coverage_reliability_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, server_default="0.7000")
    overall_reliability_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, server_default="0.7000")
    snapshot_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="v1")
    payload_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    snapshot_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    employee: Mapped["Employee"] = relationship()
    business: Mapped["Business"] = relationship()


from app.models.business import Business, Location, Role  # noqa: E402
from app.models.scheduling import Shift  # noqa: E402
from app.models.workforce import Employee  # noqa: E402
