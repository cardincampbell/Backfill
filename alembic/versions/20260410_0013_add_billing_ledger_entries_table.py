"""add billing ledger entries table

Revision ID: 20260410_0013
Revises: 20260410_0012
Create Date: 2026-04-10 12:20:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.reflection import Inspector


revision = "20260410_0013"
down_revision = "20260410_0012"
branch_labels = None
depends_on = None


def _table_names(inspector: Inspector) -> set[str]:
    return set(inspector.get_table_names())


def _index_names(inspector: Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "billing_ledger_entries" not in _table_names(inspector):
        op.create_table(
            "billing_ledger_entries",
            sa.Column("business_id", sa.UUID(), sa.ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True),
            sa.Column("location_id", sa.UUID(), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
            sa.Column("coverage_case_id", sa.UUID(), sa.ForeignKey("coverage_cases.id", ondelete="SET NULL"), nullable=True),
            sa.Column("shift_id", sa.UUID(), sa.ForeignKey("shifts.id", ondelete="SET NULL"), nullable=True),
            sa.Column("employee_id", sa.UUID(), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
            sa.Column("billing_event_type", sa.String(length=32), nullable=False),
            sa.Column("billing_cycle_start", sa.DateTime(timezone=True), nullable=False),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("cap_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("idempotency_key", sa.String(length=255), nullable=True),
            sa.Column("billing_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_billing_ledger_entries")),
            sa.UniqueConstraint("idempotency_key", name="uq_billing_ledger_entries_idempotency_key"),
        )
        op.create_index(
            "ix_billing_ledger_entries_business_id_occurred_at",
            "billing_ledger_entries",
            ["business_id", "occurred_at"],
            unique=False,
        )
        op.create_index(
            "ix_billing_ledger_entries_location_cycle_occurred_at",
            "billing_ledger_entries",
            ["location_id", "billing_cycle_start", "occurred_at"],
            unique=False,
        )
        op.create_index(
            "ix_billing_ledger_entries_case_id_occurred_at",
            "billing_ledger_entries",
            ["coverage_case_id", "occurred_at"],
            unique=False,
        )
        op.create_index(
            "ix_billing_ledger_entries_event_type_occurred_at",
            "billing_ledger_entries",
            ["billing_event_type", "occurred_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "billing_ledger_entries" in _table_names(inspector):
        index_names = _index_names(inspector, "billing_ledger_entries")
        if "ix_billing_ledger_entries_event_type_occurred_at" in index_names:
            op.drop_index("ix_billing_ledger_entries_event_type_occurred_at", table_name="billing_ledger_entries")
        if "ix_billing_ledger_entries_case_id_occurred_at" in index_names:
            op.drop_index("ix_billing_ledger_entries_case_id_occurred_at", table_name="billing_ledger_entries")
        if "ix_billing_ledger_entries_location_cycle_occurred_at" in index_names:
            op.drop_index("ix_billing_ledger_entries_location_cycle_occurred_at", table_name="billing_ledger_entries")
        if "ix_billing_ledger_entries_business_id_occurred_at" in index_names:
            op.drop_index("ix_billing_ledger_entries_business_id_occurred_at", table_name="billing_ledger_entries")
        op.drop_table("billing_ledger_entries")
