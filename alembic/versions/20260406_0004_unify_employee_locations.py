"""unify employee locations

Revision ID: 20260406_0004
Revises: 20260402_0003
Create Date: 2026-04-06 13:30:00.000000
"""
from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection
from sqlalchemy.engine.reflection import Inspector


revision = "20260406_0004"
down_revision = "20260402_0003"
branch_labels = None
depends_on = None


def _table_exists(inspector: Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_names(inspector: Inspector, table_name: str) -> set[str]:
    if not _table_exists(inspector, table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(inspector: Inspector, table_name: str) -> set[str]:
    if not _table_exists(inspector, table_name):
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _foreign_keys_for_column(
    inspector: Inspector,
    table_name: str,
    column_name: str,
) -> list[str]:
    if not _table_exists(inspector, table_name):
        return []
    names: list[str] = []
    for foreign_key in inspector.get_foreign_keys(table_name):
        constrained_columns = foreign_key.get("constrained_columns") or []
        if column_name in constrained_columns and foreign_key.get("name"):
            names.append(str(foreign_key["name"]))
    return names


def _create_employee_locations_table() -> None:
    op.create_table(
        "employee_locations",
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("access_level", sa.String(length=32), nullable=False, server_default="approved"),
        sa.Column("location_source", sa.String(length=64), nullable=True),
        sa.Column("can_cover_last_minute", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("can_blast", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("travel_radius_miles", sa.Integer(), nullable=True),
        sa.Column("location_metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_employee_locations"),
        sa.UniqueConstraint(
            "employee_id",
            "location_id",
            name="uq_employee_locations_employee_id_location_id",
        ),
    )


def _ensure_employee_locations_index(inspector: Inspector) -> None:
    if "uq_employee_locations_employee_id_primary" in _index_names(inspector, "employee_locations"):
        return
    op.create_index(
        "uq_employee_locations_employee_id_primary",
        "employee_locations",
        ["employee_id"],
        unique=True,
        postgresql_where=sa.text("is_primary = true"),
    )


def _reflect_table(bind: Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=bind)


def _insert_employee_location(
    bind: Connection,
    employee_locations: sa.Table,
    *,
    employee_id: uuid.UUID,
    location_id: uuid.UUID,
    is_primary: bool,
    access_level: str = "approved",
    location_source: str | None = None,
    can_cover_last_minute: bool = True,
    can_blast: bool = True,
    travel_radius_miles: int | None = None,
    location_metadata: dict | None = None,
) -> None:
    bind.execute(
        employee_locations.insert().values(
            id=uuid.uuid4(),
            employee_id=employee_id,
            location_id=location_id,
            is_primary=is_primary,
            access_level=access_level,
            location_source=location_source,
            can_cover_last_minute=can_cover_last_minute,
            can_blast=can_blast,
            travel_radius_miles=travel_radius_miles,
            location_metadata=location_metadata or {},
        )
    )


def _backfill_legacy_clearances(bind: Connection, inspector: Inspector) -> None:
    if not _table_exists(inspector, "employee_location_clearances"):
        return

    legacy_clearances = _reflect_table(bind, "employee_location_clearances")
    employee_locations = _reflect_table(bind, "employee_locations")
    existing_pairs = {
        (row.employee_id, row.location_id)
        for row in bind.execute(
            sa.select(employee_locations.c.employee_id, employee_locations.c.location_id)
        )
    }

    for row in bind.execute(sa.select(legacy_clearances)):
        pair = (row.employee_id, row.location_id)
        if pair in existing_pairs:
            continue
        _insert_employee_location(
            bind,
            employee_locations,
            employee_id=row.employee_id,
            location_id=row.location_id,
            is_primary=False,
            access_level=row.access_level,
            location_source=row.clearance_source,
            can_cover_last_minute=row.can_cover_last_minute,
            can_blast=row.can_blast,
            travel_radius_miles=row.travel_radius_miles,
            location_metadata=row.clearance_metadata or {},
        )
        existing_pairs.add(pair)

    op.drop_table("employee_location_clearances")


def _backfill_primary_locations(bind: Connection, inspector: Inspector) -> None:
    if "home_location_id" not in _column_names(inspector, "employees"):
        return

    employees = _reflect_table(bind, "employees")
    employee_locations = _reflect_table(bind, "employee_locations")
    existing_pairs = {
        (row.employee_id, row.location_id)
        for row in bind.execute(
            sa.select(employee_locations.c.employee_id, employee_locations.c.location_id)
        )
    }

    primary_rows = bind.execute(
        sa.select(employees.c.id, employees.c.home_location_id).where(
            employees.c.home_location_id.is_not(None)
        )
    )
    for row in primary_rows:
        pair = (row.id, row.home_location_id)
        if pair not in existing_pairs:
            _insert_employee_location(
                bind,
                employee_locations,
                employee_id=row.id,
                location_id=row.home_location_id,
                is_primary=True,
                location_source="employee_primary_location_migration",
            )
            existing_pairs.add(pair)
            continue

        bind.execute(
            employee_locations.update()
            .where(
                employee_locations.c.employee_id == row.id,
                employee_locations.c.location_id == row.home_location_id,
            )
            .values(is_primary=True)
        )

    bind.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY employee_id
                        ORDER BY
                            CASE WHEN is_primary THEN 0 ELSE 1 END,
                            created_at ASC,
                            id ASC
                    ) AS row_rank
                FROM employee_locations
            )
            UPDATE employee_locations
            SET is_primary = ranked.row_rank = 1
            FROM ranked
            WHERE employee_locations.id = ranked.id
            """
        )
    )

    refreshed_inspector = sa.inspect(bind)
    for foreign_key_name in _foreign_keys_for_column(
        refreshed_inspector,
        "employees",
        "home_location_id",
    ):
        op.drop_constraint(foreign_key_name, "employees", type_="foreignkey")

    for index_name in _index_names(refreshed_inspector, "employees"):
        if "home_location_id" in index_name:
            op.drop_index(index_name, table_name="employees")

    op.drop_column("employees", "home_location_id")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "employee_locations"):
        _create_employee_locations_table()
        inspector = sa.inspect(bind)

    _backfill_legacy_clearances(bind, inspector)
    inspector = sa.inspect(bind)
    _backfill_primary_locations(bind, inspector)
    inspector = sa.inspect(bind)
    _ensure_employee_locations_index(inspector)


def _create_legacy_clearances_table(inspector: Inspector) -> None:
    if _table_exists(inspector, "employee_location_clearances"):
        return
    op.create_table(
        "employee_location_clearances",
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("access_level", sa.String(length=32), nullable=False, server_default="approved"),
        sa.Column("clearance_source", sa.String(length=64), nullable=True),
        sa.Column("can_cover_last_minute", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("can_blast", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("travel_radius_miles", sa.Integer(), nullable=True),
        sa.Column("clearance_metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_employee_location_clearances"),
        sa.UniqueConstraint(
            "employee_id",
            "location_id",
            name="uq_employee_location_clearances_employee_id_location_id",
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "employee_locations"):
        return

    if "home_location_id" not in _column_names(inspector, "employees"):
        op.add_column("employees", sa.Column("home_location_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            "fk_employees_home_location_id_locations",
            "employees",
            "locations",
            ["home_location_id"],
            ["id"],
            ondelete="SET NULL",
        )

    inspector = sa.inspect(bind)
    _create_legacy_clearances_table(inspector)

    employee_locations = _reflect_table(bind, "employee_locations")
    legacy_clearances = _reflect_table(bind, "employee_location_clearances")
    employees = _reflect_table(bind, "employees")

    rows = list(bind.execute(sa.select(employee_locations)))
    for row in rows:
        if row.is_primary:
            bind.execute(
                employees.update()
                .where(employees.c.id == row.employee_id)
                .values(home_location_id=row.location_id)
            )
            continue

        bind.execute(
            legacy_clearances.insert().values(
                id=uuid.uuid4(),
                employee_id=row.employee_id,
                location_id=row.location_id,
                access_level=row.access_level,
                clearance_source=row.location_source,
                can_cover_last_minute=row.can_cover_last_minute,
                can_blast=row.can_blast,
                travel_radius_miles=row.travel_radius_miles,
                clearance_metadata=row.location_metadata or {},
            )
        )

    refreshed_inspector = sa.inspect(bind)
    if "uq_employee_locations_employee_id_primary" in _index_names(
        refreshed_inspector,
        "employee_locations",
    ):
        op.drop_index("uq_employee_locations_employee_id_primary", table_name="employee_locations")
    op.drop_table("employee_locations")
