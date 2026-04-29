from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, VersionedMixin
from app.models.common import (
    AssignmentStatus,
    ShiftBreakType,
    ShiftLifecycleStatus,
    ShiftSegmentType,
    ShiftStaffingStatus,
    ShiftStatus,
    compatibility_shift_status,
    shift_axes_from_compatibility_status,
)


class Shift(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shifts"
    __table_args__ = (
        UniqueConstraint("source_system", "source_shift_id", name="uq_shifts_source_system_source_shift_id"),
        Index("ix_shifts_location_id_starts_at", "location_id", "starts_at"),
        Index("ix_shifts_lifecycle_status_starts_at", "lifecycle_status", "starts_at"),
        Index("ix_shifts_staffing_status_starts_at", "staffing_status", "starts_at"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False, server_default="backfill_native")
    source_shift_id: Mapped[Optional[str]] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lifecycle_status: Mapped[ShiftLifecycleStatus] = mapped_column(
        Enum(ShiftLifecycleStatus, name="shift_lifecycle_status"),
        nullable=False,
        server_default=ShiftLifecycleStatus.draft.value,
    )
    staffing_status: Mapped[ShiftStaffingStatus] = mapped_column(
        Enum(ShiftStaffingStatus, name="shift_staffing_status"),
        nullable=False,
        server_default=ShiftStaffingStatus.open.value,
    )
    seats_requested: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    seats_filled: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    requires_manager_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    premium_cents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    notes: Mapped[Optional[str]] = mapped_column(Text)
    shift_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    business: Mapped["Business"] = relationship()
    location: Mapped["Location"] = relationship(back_populates="shifts")
    role: Mapped["Role"] = relationship(back_populates="shifts")
    segments: Mapped[list["ShiftSegment"]] = relationship(
        back_populates="shift",
        cascade="all, delete-orphan",
        order_by="ShiftSegment.sequence_no.asc()",
    )
    assignments: Mapped[list["ShiftAssignment"]] = relationship(back_populates="shift", cascade="all, delete-orphan")
    coverage_cases: Mapped[list["CoverageCase"]] = relationship(back_populates="shift", cascade="all, delete-orphan")

    @property
    def status(self) -> ShiftStatus:
        return compatibility_shift_status(self.lifecycle_status, self.staffing_status)

    @status.setter
    def status(self, value: ShiftStatus | str) -> None:
        lifecycle_status, staffing_status = shift_axes_from_compatibility_status(value)
        self.lifecycle_status = lifecycle_status
        self.staffing_status = staffing_status


class ShiftAssignment(UUIDPrimaryKeyMixin, TimestampMixin, VersionedMixin, Base):
    __tablename__ = "shift_assignments"
    __table_args__ = (
        UniqueConstraint("shift_id", "sequence_no", name="uq_shift_assignments_shift_id_sequence_no"),
        Index("ix_shift_assignments_employee_id_status", "employee_id", "status"),
    )

    shift_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False)
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    assigned_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    replaced_assignment_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("shift_assignments.id", ondelete="SET NULL"))
    assigned_via: Mapped[str] = mapped_column(String(64), nullable=False, server_default="manual")
    status: Mapped[AssignmentStatus] = mapped_column(
        Enum(AssignmentStatus, name="assignment_status"),
        nullable=False,
        server_default=AssignmentStatus.proposed.value,
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    declined_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    checked_in_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    checked_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    assignment_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    shift: Mapped["Shift"] = relationship(back_populates="assignments")
    employee: Mapped[Optional["Employee"]] = relationship(back_populates="assignments")
    assigned_by_user: Mapped[Optional["User"]] = relationship()
    replaced_assignment: Mapped[Optional["ShiftAssignment"]] = relationship(remote_side="ShiftAssignment.id")


class ShiftSegment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shift_segments"
    __table_args__ = (
        UniqueConstraint("shift_id", "sequence_no", name="uq_shift_segments_shift_id_sequence_no"),
        Index("ix_shift_segments_shift_id_starts_at", "shift_id", "starts_at"),
    )

    shift_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    segment_type: Mapped[ShiftSegmentType] = mapped_column(
        Enum(ShiftSegmentType, name="shift_segment_type"),
        nullable=False,
        server_default=ShiftSegmentType.work.value,
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    segment_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    shift: Mapped["Shift"] = relationship(back_populates="segments")
    breaks: Mapped[list["ShiftBreak"]] = relationship(
        back_populates="segment",
        cascade="all, delete-orphan",
        order_by="ShiftBreak.sequence_no.asc()",
    )


class ShiftBreak(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shift_breaks"
    __table_args__ = (
        UniqueConstraint("shift_segment_id", "sequence_no", name="uq_shift_breaks_segment_sequence_no"),
        Index("ix_shift_breaks_shift_id_starts_at", "shift_id", "starts_at"),
    )

    shift_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False)
    shift_segment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shift_segments.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    break_type: Mapped[ShiftBreakType] = mapped_column(
        Enum(ShiftBreakType, name="shift_break_type"),
        nullable=False,
        server_default=ShiftBreakType.meal.value,
    )
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    break_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    segment: Mapped["ShiftSegment"] = relationship(back_populates="breaks")


from app.models.business import Business, Location, Role  # noqa: E402
from app.models.coverage import CoverageCase  # noqa: E402
from app.models.identity import User  # noqa: E402
from app.models.workforce import Employee  # noqa: E402
