"""add shift segments and breaks

Revision ID: 20260423_0033
Revises: 20260422_0032
Create Date: 2026-04-23 09:20:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260423_0033"
down_revision = "20260422_0032"
branch_labels = None
depends_on = None


shift_segment_type_enum = sa.Enum("work", name="shift_segment_type")
shift_break_type_enum = sa.Enum("meal", "rest", "other", name="shift_break_type")


def upgrade() -> None:
    bind = op.get_bind()
    shift_segment_type_enum.create(bind, checkfirst=True)
    shift_break_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "shift_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("shift_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("segment_type", shift_segment_type_enum, nullable=False, server_default="work"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "segment_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.ForeignKeyConstraint(["shift_id"], ["shifts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shift_id", "sequence_no", name="uq_shift_segments_shift_id_sequence_no"),
    )
    op.create_index("ix_shift_segments_shift_id_starts_at", "shift_segments", ["shift_id", "starts_at"], unique=False)

    op.create_table(
        "shift_breaks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("shift_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shift_segment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("break_type", shift_break_type_enum, nullable=False, server_default="meal"),
        sa.Column("is_paid", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "break_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.ForeignKeyConstraint(["shift_id"], ["shifts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shift_segment_id"], ["shift_segments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shift_segment_id", "sequence_no", name="uq_shift_breaks_segment_sequence_no"),
    )
    op.create_index("ix_shift_breaks_shift_id_starts_at", "shift_breaks", ["shift_id", "starts_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_shift_breaks_shift_id_starts_at", table_name="shift_breaks")
    op.drop_table("shift_breaks")
    op.drop_index("ix_shift_segments_shift_id_starts_at", table_name="shift_segments")
    op.drop_table("shift_segments")

    bind = op.get_bind()
    shift_break_type_enum.drop(bind, checkfirst=True)
    shift_segment_type_enum.drop(bind, checkfirst=True)
