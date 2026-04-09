"""add employee user link

Revision ID: 20260408_0008
Revises: 20260408_0007
Create Date: 2026-04-08 16:35:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "20260408_0008"
down_revision = "20260408_0007"
branch_labels = None
depends_on = None


def _column_names(inspector: Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _unique_constraint_names(inspector: Inspector, table_name: str) -> set[str]:
    return {constraint["name"] for constraint in inspector.get_unique_constraints(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "user_id" not in _column_names(inspector, "employees"):
        op.add_column(
            "employees",
            sa.Column(
                "user_id",
                sa.UUID(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    inspector = sa.inspect(bind)
    if "uq_employees_business_id_user_id" not in _unique_constraint_names(inspector, "employees"):
        op.create_unique_constraint(
            "uq_employees_business_id_user_id",
            "employees",
            ["business_id", "user_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "uq_employees_business_id_user_id" in _unique_constraint_names(inspector, "employees"):
        op.drop_constraint(
            "uq_employees_business_id_user_id",
            "employees",
            type_="unique",
        )

    inspector = sa.inspect(bind)
    if "user_id" in _column_names(inspector, "employees"):
        op.drop_column("employees", "user_id")
