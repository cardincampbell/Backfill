"""split shift status into lifecycle and staffing axes

Revision ID: 20260412_0015
Revises: 20260410_0014
Create Date: 2026-04-12 10:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.reflection import Inspector


revision = "20260412_0015"
down_revision = "20260410_0014"
branch_labels = None
depends_on = None


def _table_names(inspector: Inspector) -> set[str]:
    return set(inspector.get_table_names())


def _index_names(inspector: Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "shifts" not in _table_names(inspector):
        return

    lifecycle_enum = postgresql.ENUM(
        "draft",
        "scheduled",
        "in_progress",
        "completed",
        "cancelled",
        name="shift_lifecycle_status",
    )
    staffing_enum = postgresql.ENUM(
        "open",
        "filling",
        "covered",
        "no_fill",
        name="shift_staffing_status",
    )
    legacy_enum = postgresql.ENUM(
        "draft",
        "scheduled",
        "open",
        "filling",
        "covered",
        "no_fill",
        "cancelled",
        "completed",
        name="shift_status",
    )

    lifecycle_enum.create(bind, checkfirst=True)
    staffing_enum.create(bind, checkfirst=True)

    column_names = {column["name"] for column in inspector.get_columns("shifts")}
    if "lifecycle_status" not in column_names:
        op.add_column(
            "shifts",
            sa.Column(
                "lifecycle_status",
                lifecycle_enum,
                nullable=True,
                server_default=sa.text("'draft'"),
            ),
        )
    if "staffing_status" not in column_names:
        op.add_column(
            "shifts",
            sa.Column(
                "staffing_status",
                staffing_enum,
                nullable=True,
                server_default=sa.text("'open'"),
            ),
        )

    op.execute(
        """
        UPDATE shifts
        SET lifecycle_status = CASE
            WHEN status = 'draft' THEN 'draft'::shift_lifecycle_status
            WHEN status = 'cancelled' THEN 'cancelled'::shift_lifecycle_status
            WHEN status = 'completed' THEN 'completed'::shift_lifecycle_status
            ELSE 'scheduled'::shift_lifecycle_status
        END,
        staffing_status = CASE
            WHEN status = 'no_fill' THEN 'no_fill'::shift_staffing_status
            WHEN status = 'covered' THEN 'covered'::shift_staffing_status
            WHEN status = 'filling' THEN 'filling'::shift_staffing_status
            WHEN COALESCE(seats_filled, 0) >= GREATEST(1, COALESCE(seats_requested, 1))
                AND COALESCE(seats_filled, 0) > 0
                THEN 'covered'::shift_staffing_status
            WHEN COALESCE(seats_filled, 0) > 0 THEN 'filling'::shift_staffing_status
            ELSE 'open'::shift_staffing_status
        END
        """
    )

    op.alter_column("shifts", "lifecycle_status", nullable=False, server_default=sa.text("'draft'"))
    op.alter_column("shifts", "staffing_status", nullable=False, server_default=sa.text("'open'"))

    inspector = sa.inspect(bind)
    index_names = _index_names(inspector, "shifts")
    if "ix_shifts_status_starts_at" in index_names:
        op.drop_index("ix_shifts_status_starts_at", table_name="shifts")
    if "ix_shifts_lifecycle_status_starts_at" not in index_names:
        op.create_index(
            "ix_shifts_lifecycle_status_starts_at",
            "shifts",
            ["lifecycle_status", "starts_at"],
            unique=False,
        )
    if "ix_shifts_staffing_status_starts_at" not in index_names:
        op.create_index(
            "ix_shifts_staffing_status_starts_at",
            "shifts",
            ["staffing_status", "starts_at"],
            unique=False,
        )

    inspector = sa.inspect(bind)
    column_names = {column["name"] for column in inspector.get_columns("shifts")}
    if "status" in column_names:
        op.drop_column("shifts", "status")
    legacy_enum.drop(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "shifts" not in _table_names(inspector):
        return

    lifecycle_enum = postgresql.ENUM(
        "draft",
        "scheduled",
        "in_progress",
        "completed",
        "cancelled",
        name="shift_lifecycle_status",
    )
    staffing_enum = postgresql.ENUM(
        "open",
        "filling",
        "covered",
        "no_fill",
        name="shift_staffing_status",
    )
    legacy_enum = postgresql.ENUM(
        "draft",
        "scheduled",
        "open",
        "filling",
        "covered",
        "no_fill",
        "cancelled",
        "completed",
        name="shift_status",
    )

    legacy_enum.create(bind, checkfirst=True)

    column_names = {column["name"] for column in inspector.get_columns("shifts")}
    if "status" not in column_names:
        op.add_column(
            "shifts",
            sa.Column(
                "status",
                legacy_enum,
                nullable=True,
                server_default=sa.text("'draft'"),
            ),
        )

    op.execute(
        """
        UPDATE shifts
        SET status = CASE
            WHEN lifecycle_status = 'draft' THEN 'draft'::shift_status
            WHEN lifecycle_status = 'cancelled' THEN 'cancelled'::shift_status
            WHEN lifecycle_status = 'completed' THEN 'completed'::shift_status
            WHEN staffing_status = 'no_fill' THEN 'no_fill'::shift_status
            WHEN staffing_status = 'covered' THEN 'covered'::shift_status
            WHEN staffing_status = 'filling' THEN 'filling'::shift_status
            ELSE 'open'::shift_status
        END
        """
    )

    op.alter_column("shifts", "status", nullable=False, server_default=sa.text("'draft'"))

    inspector = sa.inspect(bind)
    index_names = _index_names(inspector, "shifts")
    if "ix_shifts_lifecycle_status_starts_at" in index_names:
        op.drop_index("ix_shifts_lifecycle_status_starts_at", table_name="shifts")
    if "ix_shifts_staffing_status_starts_at" in index_names:
        op.drop_index("ix_shifts_staffing_status_starts_at", table_name="shifts")
    if "ix_shifts_status_starts_at" not in index_names:
        op.create_index("ix_shifts_status_starts_at", "shifts", ["status", "starts_at"], unique=False)

    inspector = sa.inspect(bind)
    column_names = {column["name"] for column in inspector.get_columns("shifts")}
    if "lifecycle_status" in column_names:
        op.drop_column("shifts", "lifecycle_status")
    if "staffing_status" in column_names:
        op.drop_column("shifts", "staffing_status")

    staffing_enum.drop(bind, checkfirst=True)
    lifecycle_enum.drop(bind, checkfirst=True)
