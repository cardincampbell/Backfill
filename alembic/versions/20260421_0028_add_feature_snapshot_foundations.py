"""add feature snapshot foundations

Revision ID: 20260421_0028
Revises: 20260420_0027
Create Date: 2026-04-21 10:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260421_0028"
down_revision = "20260420_0027"
branch_labels = None
depends_on = None


bucket_alignment_mode_enum = postgresql.ENUM(
    "local_operating_time",
    name="bucket_alignment_mode",
)
demand_feature_snapshot_status_enum = postgresql.ENUM(
    "building",
    "completed",
    "failed",
    name="demand_feature_snapshot_status",
)
dst_handling_mode_enum = postgresql.ENUM(
    "skip_missing_repeat_distinct",
    name="dst_handling_mode",
)


def upgrade() -> None:
    bind = op.get_bind()
    bucket_alignment_mode_enum.create(bind, checkfirst=True)
    demand_feature_snapshot_status_enum.create(bind, checkfirst=True)
    dst_handling_mode_enum.create(bind, checkfirst=True)

    op.create_table(
        "weather_forecast_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("forecast_generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_valid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("temperature_f", sa.Numeric(10, 4), nullable=True),
        sa.Column("precipitation_probability", sa.Integer(), nullable=True),
        sa.Column("precipitation_inches", sa.Numeric(10, 4), nullable=True),
        sa.Column("wind_speed_mph", sa.Numeric(10, 4), nullable=True),
        sa.Column("weather_code", sa.Integer(), nullable=True),
        sa.Column("severity_flag", sa.String(length=16), nullable=False, server_default=sa.text("'none'")),
        sa.Column(
            "source_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_weather_forecast_snapshots"),
    )
    op.create_index(
        "ix_weather_forecast_snapshots_location_bucket_start",
        "weather_forecast_snapshots",
        ["location_id", "bucket_start"],
        unique=False,
    )
    op.create_index(
        "ix_weather_forecast_snapshots_location_generated_at",
        "weather_forecast_snapshots",
        ["location_id", "forecast_generated_at"],
        unique=False,
    )
    op.create_index(
        "ix_weather_forecast_snapshots_location_valid_at",
        "weather_forecast_snapshots",
        ["location_id", "forecast_valid_at"],
        unique=False,
    )

    op.create_table(
        "demand_feature_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("planning_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("planning_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone_name", sa.String(length=64), nullable=False),
        sa.Column("bucket_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "bucket_alignment_mode",
            postgresql.ENUM(
                "local_operating_time",
                name="bucket_alignment_mode",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'local_operating_time'"),
        ),
        sa.Column(
            "dst_handling_mode",
            postgresql.ENUM(
                "skip_missing_repeat_distinct",
                name="dst_handling_mode",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'skip_missing_repeat_distinct'"),
        ),
        sa.Column("snapshot_hash", sa.String(length=255), nullable=False),
        sa.Column("feature_schema_version", sa.String(length=64), nullable=False, server_default=sa.text("'v1'")),
        sa.Column(
            "snapshot_status",
            postgresql.ENUM(
                "building",
                "completed",
                "failed",
                name="demand_feature_snapshot_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'building'"),
        ),
        sa.Column("operating_hours_version", sa.String(length=64), nullable=True),
        sa.Column(
            "source_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_demand_feature_snapshots"),
        sa.UniqueConstraint("snapshot_hash", name="uq_demand_feature_snapshots_snapshot_hash"),
    )
    op.create_index(
        "ix_demand_feature_snapshots_location_created_at",
        "demand_feature_snapshots",
        ["location_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_demand_feature_snapshots_hash_created_at",
        "demand_feature_snapshots",
        ["snapshot_hash", "created_at"],
        unique=False,
    )

    op.create_table(
        "demand_feature_snapshot_points",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("demand_feature_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "feature_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("feature_vector_version", sa.String(length=64), nullable=False, server_default=sa.text("'v1'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["demand_feature_snapshot_id"], ["demand_feature_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_demand_feature_snapshot_points"),
        sa.UniqueConstraint(
            "demand_feature_snapshot_id",
            "location_id",
            "role_id",
            "bucket_start",
            "bucket_end",
            name="uq_demand_feature_snapshot_points_snapshot_location_role_bucket",
        ),
    )
    op.create_index(
        "ix_demand_feature_snapshot_points_snapshot_bucket_start",
        "demand_feature_snapshot_points",
        ["demand_feature_snapshot_id", "bucket_start"],
        unique=False,
    )
    op.create_index(
        "ix_demand_feature_snapshot_points_location_role_bucket_start",
        "demand_feature_snapshot_points",
        ["location_id", "role_id", "bucket_start"],
        unique=False,
    )

    op.add_column(
        "labor_forecast_runs",
        sa.Column("demand_feature_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_labor_forecast_runs_demand_feature_snapshot_id",
        "labor_forecast_runs",
        "demand_feature_snapshots",
        ["demand_feature_snapshot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_labor_forecast_runs_snapshot_id_created_at",
        "labor_forecast_runs",
        ["demand_feature_snapshot_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_labor_forecast_runs_snapshot_id_created_at",
        table_name="labor_forecast_runs",
    )
    op.drop_constraint(
        "fk_labor_forecast_runs_demand_feature_snapshot_id",
        "labor_forecast_runs",
        type_="foreignkey",
    )
    op.drop_column("labor_forecast_runs", "demand_feature_snapshot_id")

    op.drop_index(
        "ix_demand_feature_snapshot_points_location_role_bucket_start",
        table_name="demand_feature_snapshot_points",
    )
    op.drop_index(
        "ix_demand_feature_snapshot_points_snapshot_bucket_start",
        table_name="demand_feature_snapshot_points",
    )
    op.drop_table("demand_feature_snapshot_points")

    op.drop_index(
        "ix_demand_feature_snapshots_hash_created_at",
        table_name="demand_feature_snapshots",
    )
    op.drop_index(
        "ix_demand_feature_snapshots_location_created_at",
        table_name="demand_feature_snapshots",
    )
    op.drop_table("demand_feature_snapshots")

    op.drop_index(
        "ix_weather_forecast_snapshots_location_valid_at",
        table_name="weather_forecast_snapshots",
    )
    op.drop_index(
        "ix_weather_forecast_snapshots_location_generated_at",
        table_name="weather_forecast_snapshots",
    )
    op.drop_index(
        "ix_weather_forecast_snapshots_location_bucket_start",
        table_name="weather_forecast_snapshots",
    )
    op.drop_table("weather_forecast_snapshots")

    dst_handling_mode_enum.drop(op.get_bind(), checkfirst=True)
    demand_feature_snapshot_status_enum.drop(op.get_bind(), checkfirst=True)
    bucket_alignment_mode_enum.drop(op.get_bind(), checkfirst=True)
