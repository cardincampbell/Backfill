"""create platform events table

Revision ID: 20260410_0010
Revises: 20260409_0009
Create Date: 2026-04-10 10:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.reflection import Inspector


revision = "20260410_0010"
down_revision = "20260409_0009"
branch_labels = None
depends_on = None


def _table_names(inspector: Inspector) -> set[str]:
    return set(inspector.get_table_names())


def _index_names(inspector: Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "platform_event_actor_type" not in {enum["name"] for enum in inspector.get_enums()}:
        platform_event_actor_type = postgresql.ENUM(
            "system",
            "user",
            "service",
            name="platform_event_actor_type",
        )
        platform_event_actor_type.create(bind, checkfirst=True)

    inspector = sa.inspect(bind)
    if "platform_events" not in _table_names(inspector):
        op.create_table(
            "platform_events",
            sa.Column("business_id", sa.UUID(), sa.ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True),
            sa.Column("location_id", sa.UUID(), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
            sa.Column("schema_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("event_type", sa.String(length=120), nullable=False),
            sa.Column("compatibility_event_name", sa.String(length=120), nullable=True),
            sa.Column("entity_type", sa.String(length=80), nullable=False),
            sa.Column("entity_id", sa.UUID(), nullable=True),
            sa.Column(
                "actor_type",
                postgresql.ENUM(
                    "system",
                    "user",
                    "service",
                    name="platform_event_actor_type",
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("actor_user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("actor_membership_id", sa.UUID(), sa.ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True),
            sa.Column("trace_id", sa.String(length=64), nullable=False),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=1024), nullable=True),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_events")),
        )
        op.create_index(
            "ix_platform_events_business_id_occurred_at",
            "platform_events",
            ["business_id", "occurred_at"],
            unique=False,
        )
        op.create_index(
            "ix_platform_events_location_id_occurred_at",
            "platform_events",
            ["location_id", "occurred_at"],
            unique=False,
        )
        op.create_index(
            "ix_platform_events_event_type_occurred_at",
            "platform_events",
            ["event_type", "occurred_at"],
            unique=False,
        )
        op.create_index(
            "ix_platform_events_entity_type_entity_id",
            "platform_events",
            ["entity_type", "entity_id"],
            unique=False,
        )
        op.create_index(
            "ix_platform_events_trace_id",
            "platform_events",
            ["trace_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "platform_events" in _table_names(inspector):
        index_names = _index_names(inspector, "platform_events")
        if "ix_platform_events_trace_id" in index_names:
            op.drop_index("ix_platform_events_trace_id", table_name="platform_events")
        if "ix_platform_events_entity_type_entity_id" in index_names:
            op.drop_index("ix_platform_events_entity_type_entity_id", table_name="platform_events")
        if "ix_platform_events_event_type_occurred_at" in index_names:
            op.drop_index("ix_platform_events_event_type_occurred_at", table_name="platform_events")
        if "ix_platform_events_location_id_occurred_at" in index_names:
            op.drop_index("ix_platform_events_location_id_occurred_at", table_name="platform_events")
        if "ix_platform_events_business_id_occurred_at" in index_names:
            op.drop_index("ix_platform_events_business_id_occurred_at", table_name="platform_events")
        op.drop_table("platform_events")

    inspector = sa.inspect(bind)
    if "platform_event_actor_type" in {enum["name"] for enum in inspector.get_enums()}:
        postgresql.ENUM(name="platform_event_actor_type").drop(bind, checkfirst=True)
