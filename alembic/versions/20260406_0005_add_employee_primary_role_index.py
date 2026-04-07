"""add employee primary role index

Revision ID: 20260406_0005
Revises: 20260406_0004
Create Date: 2026-04-06 16:45:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "20260406_0005"
down_revision = "20260406_0004"
branch_labels = None
depends_on = None


def _index_names(inspector: Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "uq_employee_roles_employee_id_primary" not in _index_names(inspector, "employee_roles"):
        op.create_index(
            "uq_employee_roles_employee_id_primary",
            "employee_roles",
            ["employee_id"],
            unique=True,
            postgresql_where=sa.text("is_primary = true"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "uq_employee_roles_employee_id_primary" in _index_names(inspector, "employee_roles"):
        op.drop_index("uq_employee_roles_employee_id_primary", table_name="employee_roles")
