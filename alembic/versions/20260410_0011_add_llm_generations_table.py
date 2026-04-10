"""add llm generations table

Revision ID: 20260410_0011
Revises: 20260410_0010
Create Date: 2026-04-10 11:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.reflection import Inspector


revision = "20260410_0011"
down_revision = "20260410_0010"
branch_labels = None
depends_on = None


def _table_names(inspector: Inspector) -> set[str]:
    return set(inspector.get_table_names())


def _index_names(inspector: Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "llm_generations" not in _table_names(inspector):
        op.create_table(
            "llm_generations",
            sa.Column("business_id", sa.UUID(), sa.ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True),
            sa.Column("location_id", sa.UUID(), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
            sa.Column("provider", sa.String(length=64), nullable=False),
            sa.Column("model", sa.String(length=255), nullable=False),
            sa.Column("purpose", sa.String(length=64), nullable=False, server_default="general"),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("prompt_version", sa.String(length=120), nullable=True),
            sa.Column("trace_id", sa.String(length=64), nullable=True),
            sa.Column("provider_generation_id", sa.String(length=255), nullable=True),
            sa.Column("finish_reason", sa.String(length=64), nullable=True),
            sa.Column("output_text", sa.Text(), nullable=True),
            sa.Column("input_tokens", sa.Integer(), nullable=True),
            sa.Column("output_tokens", sa.Integer(), nullable=True),
            sa.Column("total_tokens", sa.Integer(), nullable=True),
            sa.Column("estimated_cost_micros", sa.BigInteger(), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("tool_calls", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_generations")),
        )
        op.create_index(
            "ix_llm_generations_business_id_started_at",
            "llm_generations",
            ["business_id", "started_at"],
            unique=False,
        )
        op.create_index(
            "ix_llm_generations_location_id_started_at",
            "llm_generations",
            ["location_id", "started_at"],
            unique=False,
        )
        op.create_index(
            "ix_llm_generations_provider_model_started_at",
            "llm_generations",
            ["provider", "model", "started_at"],
            unique=False,
        )
        op.create_index(
            "ix_llm_generations_trace_id",
            "llm_generations",
            ["trace_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "llm_generations" in _table_names(inspector):
        index_names = _index_names(inspector, "llm_generations")
        if "ix_llm_generations_trace_id" in index_names:
            op.drop_index("ix_llm_generations_trace_id", table_name="llm_generations")
        if "ix_llm_generations_provider_model_started_at" in index_names:
            op.drop_index("ix_llm_generations_provider_model_started_at", table_name="llm_generations")
        if "ix_llm_generations_location_id_started_at" in index_names:
            op.drop_index("ix_llm_generations_location_id_started_at", table_name="llm_generations")
        if "ix_llm_generations_business_id_started_at" in index_names:
            op.drop_index("ix_llm_generations_business_id_started_at", table_name="llm_generations")
        op.drop_table("llm_generations")
