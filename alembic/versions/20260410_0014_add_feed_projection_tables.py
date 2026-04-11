"""add feed projection tables

Revision ID: 20260410_0014
Revises: 20260410_0013
Create Date: 2026-04-10 20:55:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.reflection import Inspector


revision = "20260410_0014"
down_revision = "20260410_0013"
branch_labels = None
depends_on = None


def _table_names(inspector: Inspector) -> set[str]:
    return set(inspector.get_table_names())


def _index_names(inspector: Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _constraint_names(inspector: Inspector, table_name: str) -> set[str]:
    return {
        constraint["name"]
        for constraint in inspector.get_check_constraints(table_name)
        if constraint.get("name")
    }


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "feed_projections" not in _table_names(inspector):
        op.create_table(
            "feed_projections",
            sa.Column("source_event_id", sa.UUID(), sa.ForeignKey("platform_events.id", ondelete="CASCADE"), nullable=False),
            sa.Column("projection_name", sa.Text(), nullable=False),
            sa.Column("business_id", sa.UUID(), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True),
            sa.Column("location_id", sa.UUID(), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
            sa.Column("schema_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("event_type", sa.String(length=120), nullable=False),
            sa.Column("compatibility_event_name", sa.String(length=120), nullable=True),
            sa.Column("entity_type", sa.String(length=80), nullable=False),
            sa.Column("entity_id", sa.UUID(), nullable=True),
            sa.Column("actor_type", sa.String(length=32), nullable=False),
            sa.Column("actor_user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("actor_membership_id", sa.UUID(), sa.ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True),
            sa.Column("trace_id", sa.String(length=64), nullable=False),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=1024), nullable=True),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("projection_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_feed_projections")),
            sa.UniqueConstraint(
                "projection_name",
                "source_event_id",
                name="uq_feed_projections_projection_name_source_event_id",
            ),
        )

    inspector = sa.inspect(bind)
    if "projection_cursors" not in _table_names(inspector):
        op.create_table(
            "projection_cursors",
            sa.Column("projection_name", sa.Text(), nullable=False),
            sa.Column("schema_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("last_source_created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_source_event_id", sa.UUID(), sa.ForeignKey("platform_events.id", ondelete="SET NULL"), nullable=True),
            sa.Column("cursor_status", sa.String(length=32), nullable=False, server_default=sa.text("'idle'")),
            sa.Column("last_run_started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_run_completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("cursor_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(
                "((last_source_created_at IS NULL AND last_source_event_id IS NULL) "
                "OR (last_source_created_at IS NOT NULL AND last_source_event_id IS NOT NULL))",
                name="ck_projection_cursors_checkpoint_pair",
            ),
            sa.PrimaryKeyConstraint("projection_name", name=op.f("pk_projection_cursors")),
        )

    inspector = sa.inspect(bind)
    feed_index_names = _index_names(inspector, "feed_projections") if "feed_projections" in _table_names(inspector) else set()
    if "ix_feed_projections_projection_name_business_id_occurred_at_id" not in feed_index_names:
        op.execute(
            "CREATE INDEX ix_feed_projections_projection_name_business_id_occurred_at_id "
            "ON feed_projections (projection_name, business_id, occurred_at DESC, id DESC)"
        )
    if "ix_feed_projections_projection_name_business_location_occurred_at_id" not in feed_index_names:
        op.execute(
            "CREATE INDEX ix_feed_projections_projection_name_business_location_occurred_at_id "
            "ON feed_projections (projection_name, business_id, location_id, occurred_at DESC, id DESC)"
        )
    if "ix_feed_projections_projection_name_event_type_occurred_at_id" not in feed_index_names:
        op.execute(
            "CREATE INDEX ix_feed_projections_projection_name_event_type_occurred_at_id "
            "ON feed_projections (projection_name, event_type, occurred_at DESC, id DESC)"
        )
    if "ix_feed_projections_projection_name_trace_id_occurred_at_id" not in feed_index_names:
        op.execute(
            "CREATE INDEX ix_feed_projections_projection_name_trace_id_occurred_at_id "
            "ON feed_projections (projection_name, trace_id, occurred_at DESC, id DESC)"
        )

    inspector = sa.inspect(bind)
    if "platform_events" in _table_names(inspector):
        platform_index_names = _index_names(inspector, "platform_events")
        if "ix_platform_events_created_at_id" not in platform_index_names:
            op.create_index(
                "ix_platform_events_created_at_id",
                "platform_events",
                ["created_at", "id"],
                unique=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "platform_events" in _table_names(inspector):
        platform_index_names = _index_names(inspector, "platform_events")
        if "ix_platform_events_created_at_id" in platform_index_names:
            op.drop_index("ix_platform_events_created_at_id", table_name="platform_events")

    inspector = sa.inspect(bind)
    if "feed_projections" in _table_names(inspector):
        feed_index_names = _index_names(inspector, "feed_projections")
        if "ix_feed_projections_projection_name_trace_id_occurred_at_id" in feed_index_names:
            op.drop_index("ix_feed_projections_projection_name_trace_id_occurred_at_id", table_name="feed_projections")
        if "ix_feed_projections_projection_name_event_type_occurred_at_id" in feed_index_names:
            op.drop_index("ix_feed_projections_projection_name_event_type_occurred_at_id", table_name="feed_projections")
        if "ix_feed_projections_projection_name_business_location_occurred_at_id" in feed_index_names:
            op.drop_index("ix_feed_projections_projection_name_business_location_occurred_at_id", table_name="feed_projections")
        if "ix_feed_projections_projection_name_business_id_occurred_at_id" in feed_index_names:
            op.drop_index("ix_feed_projections_projection_name_business_id_occurred_at_id", table_name="feed_projections")
        op.drop_table("feed_projections")

    inspector = sa.inspect(bind)
    if "projection_cursors" in _table_names(inspector):
        constraint_names = _constraint_names(inspector, "projection_cursors")
        if "ck_projection_cursors_checkpoint_pair" in constraint_names:
            op.drop_constraint("ck_projection_cursors_checkpoint_pair", "projection_cursors", type_="check")
        op.drop_table("projection_cursors")
