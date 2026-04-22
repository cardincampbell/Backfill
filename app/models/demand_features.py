from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.common import BucketAlignmentMode, DemandFeatureSnapshotStatus, DstHandlingMode

if TYPE_CHECKING:
    from app.models.business import Business, Location, Role
    from app.models.labor_forecasting import LaborForecastRun


class PosSalesFact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pos_sales_facts"
    __table_args__ = (
        Index(
            "ix_pos_sales_facts_location_bucket_start",
            "location_id",
            "bucket_start",
        ),
        Index(
            "ix_pos_sales_facts_location_observed_at",
            "location_id",
            "observed_at",
        ),
        Index(
            "ix_pos_sales_facts_provider_location_bucket_start",
            "provider",
            "provider_location_id",
            "bucket_start",
        ),
        UniqueConstraint("provider", "dedupe_key", name="uq_pos_sales_facts_provider_dedupe_key"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_account_id: Mapped[Optional[str]] = mapped_column(String(255))
    provider_location_id: Mapped[str] = mapped_column(String(255), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bucket_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    gross_sales_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    net_sales_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    order_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    guest_count: Mapped[Optional[int]] = mapped_column(Integer)
    refund_count: Mapped[Optional[int]] = mapped_column(Integer)
    source_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)

    business: Mapped["Business"] = relationship()
    location: Mapped[Optional["Location"]] = relationship()


class AttendanceHistoryFact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "attendance_history_facts"
    __table_args__ = (
        Index(
            "ix_attendance_history_facts_location_role_starts_at",
            "location_id",
            "role_id",
            "starts_at",
        ),
        Index(
            "ix_attendance_history_facts_employee_starts_at",
            "employee_id",
            "starts_at",
        ),
        UniqueConstraint("source_system", "dedupe_key", name="uq_attendance_history_facts_source_system_dedupe_key"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    role_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL")
    )
    shift_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("shifts.id", ondelete="SET NULL")
    )
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False, server_default="backfill_native")
    source_assignment_id: Mapped[Optional[str]] = mapped_column(String(255))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_hours: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, server_default="0")
    worked_hours: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, server_default="0")
    attendance_status: Mapped[str] = mapped_column(String(32), nullable=False)
    late_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    left_early_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    source_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)

    business: Mapped["Business"] = relationship()
    location: Mapped[Optional["Location"]] = relationship()
    role: Mapped[Optional["Role"]] = relationship()


class CalloutHistoryFact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "callout_history_facts"
    __table_args__ = (
        Index(
            "ix_callout_history_facts_location_role_occurred_at",
            "location_id",
            "role_id",
            "occurred_at",
        ),
        Index(
            "ix_callout_history_facts_location_role_shift_starts_at",
            "location_id",
            "role_id",
            "shift_starts_at",
        ),
        UniqueConstraint("source_system", "dedupe_key", name="uq_callout_history_facts_source_system_dedupe_key"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    role_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL")
    )
    shift_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("shifts.id", ondelete="SET NULL")
    )
    source_system: Mapped[str] = mapped_column(String(64), nullable=False, server_default="backfill_native")
    source_case_id: Mapped[Optional[str]] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    shift_starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    shift_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notice_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    reason_code: Mapped[Optional[str]] = mapped_column(String(80))
    filled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    fill_latency_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    source_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)

    business: Mapped["Business"] = relationship()
    location: Mapped[Optional["Location"]] = relationship()
    role: Mapped[Optional["Role"]] = relationship()


class WeatherForecastSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "weather_forecast_snapshots"
    __table_args__ = (
        Index(
            "ix_weather_forecast_snapshots_location_bucket_start",
            "location_id",
            "bucket_start",
        ),
        Index(
            "ix_weather_forecast_snapshots_location_generated_at",
            "location_id",
            "forecast_generated_at",
        ),
        Index(
            "ix_weather_forecast_snapshots_location_valid_at",
            "location_id",
            "forecast_valid_at",
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    forecast_generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forecast_valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bucket_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    temperature_f: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    precipitation_probability: Mapped[Optional[int]] = mapped_column(Integer)
    precipitation_inches: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    wind_speed_mph: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    weather_code: Mapped[Optional[int]] = mapped_column(Integer)
    severity_flag: Mapped[str] = mapped_column(String(16), nullable=False, server_default="none")
    source_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    business: Mapped["Business"] = relationship()
    location: Mapped[Optional["Location"]] = relationship()


class DemandFeatureSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "demand_feature_snapshots"
    __table_args__ = (
        Index(
            "ix_demand_feature_snapshots_location_created_at",
            "location_id",
            "created_at",
        ),
        Index(
            "ix_demand_feature_snapshots_hash_created_at",
            "snapshot_hash",
            "created_at",
        ),
        UniqueConstraint("snapshot_hash", name="uq_demand_feature_snapshots_snapshot_hash"),
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
    timezone_name: Mapped[str] = mapped_column(String(64), nullable=False)
    bucket_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    bucket_alignment_mode: Mapped[BucketAlignmentMode] = mapped_column(
        Enum(BucketAlignmentMode, name="bucket_alignment_mode"),
        nullable=False,
        server_default=BucketAlignmentMode.local_operating_time.value,
    )
    dst_handling_mode: Mapped[DstHandlingMode] = mapped_column(
        Enum(DstHandlingMode, name="dst_handling_mode"),
        nullable=False,
        server_default=DstHandlingMode.skip_missing_repeat_distinct.value,
    )
    snapshot_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="v1")
    snapshot_status: Mapped[DemandFeatureSnapshotStatus] = mapped_column(
        Enum(DemandFeatureSnapshotStatus, name="demand_feature_snapshot_status"),
        nullable=False,
        server_default=DemandFeatureSnapshotStatus.building.value,
    )
    operating_hours_version: Mapped[Optional[str]] = mapped_column(String(64))
    source_summary: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    business: Mapped["Business"] = relationship()
    location: Mapped[Optional["Location"]] = relationship()
    points: Mapped[List["DemandFeatureSnapshotPoint"]] = relationship(
        back_populates="demand_feature_snapshot",
        cascade="all, delete-orphan",
    )
    labor_forecast_runs: Mapped[List["LaborForecastRun"]] = relationship(
        back_populates="demand_feature_snapshot",
    )


class DemandFeatureSnapshotPoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "demand_feature_snapshot_points"
    __table_args__ = (
        Index(
            "ix_demand_feature_snapshot_points_snapshot_bucket_start",
            "demand_feature_snapshot_id",
            "bucket_start",
        ),
        Index(
            "ix_demand_feature_snapshot_points_location_role_bucket_start",
            "location_id",
            "role_id",
            "bucket_start",
        ),
        UniqueConstraint(
            "demand_feature_snapshot_id",
            "location_id",
            "role_id",
            "bucket_start",
            "bucket_end",
            name="uq_demand_feature_snapshot_points_snapshot_location_role_bucket",
        ),
    )

    demand_feature_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("demand_feature_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    role_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL")
    )
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bucket_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    feature_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    feature_vector_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="v1")

    demand_feature_snapshot: Mapped["DemandFeatureSnapshot"] = relationship(back_populates="points")
    location: Mapped[Optional["Location"]] = relationship()
    role: Mapped[Optional["Role"]] = relationship()


from app.models.business import Business, Location, Role  # noqa: E402
from app.models.labor_forecasting import LaborForecastRun  # noqa: E402
