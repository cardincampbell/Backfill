from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.common import LaborForecastRunStatus

if TYPE_CHECKING:
    from app.models.business import Business, Location, Role
    from app.models.demand_features import DemandFeatureSnapshot


class LaborForecastRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "labor_forecast_runs"
    __table_args__ = (
        Index("ix_labor_forecast_runs_business_id_created_at", "business_id", "created_at"),
        Index(
            "ix_labor_forecast_runs_snapshot_id_created_at",
            "demand_feature_snapshot_id",
            "created_at",
        ),
        Index("ix_labor_forecast_runs_location_id_created_at", "location_id", "created_at"),
        Index("ix_labor_forecast_runs_status_created_at", "status", "created_at"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    demand_feature_snapshot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("demand_feature_snapshots.id", ondelete="SET NULL")
    )
    planning_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    planning_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forecast_model_version: Mapped[str] = mapped_column(String(64), nullable=False, server_default="v1")
    feature_snapshot_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[LaborForecastRunStatus] = mapped_column(
        Enum(LaborForecastRunStatus, name="labor_forecast_run_status"),
        nullable=False,
        server_default=LaborForecastRunStatus.queued.value,
    )
    forecast_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    business: Mapped["Business"] = relationship()
    location: Mapped[Optional["Location"]] = relationship()
    demand_feature_snapshot: Mapped[Optional["DemandFeatureSnapshot"]] = relationship(
        back_populates="labor_forecast_runs"
    )
    points: Mapped[List["LaborForecastPoint"]] = relationship(
        back_populates="labor_forecast_run",
        cascade="all, delete-orphan",
    )


class LaborForecastPoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "labor_forecast_points"
    __table_args__ = (
        Index(
            "ix_labor_forecast_points_run_id_window_start",
            "labor_forecast_run_id",
            "window_start",
        ),
        Index(
            "ix_labor_forecast_points_location_role_window_start",
            "location_id",
            "role_id",
            "window_start",
        ),
        UniqueConstraint(
            "labor_forecast_run_id",
            "location_id",
            "role_id",
            "window_start",
            "window_end",
            name="uq_labor_forecast_points_run_location_role_window",
        ),
    )

    labor_forecast_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("labor_forecast_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    role_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL")
    )
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    predicted_headcount: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    predicted_labor_hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, server_default="0")
    forecast_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    labor_forecast_run: Mapped["LaborForecastRun"] = relationship(back_populates="points")
    location: Mapped[Optional["Location"]] = relationship()
    role: Mapped[Optional["Role"]] = relationship()


from app.models.business import Business, Location, Role  # noqa: E402
from app.models.demand_features import DemandFeatureSnapshot  # noqa: E402
