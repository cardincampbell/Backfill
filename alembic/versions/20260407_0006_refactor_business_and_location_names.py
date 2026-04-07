"""refactor business and location names

Revision ID: 20260407_0006
Revises: 20260406_0005
Create Date: 2026-04-07 09:30:00.000000
"""
from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "20260407_0006"
down_revision = "20260406_0005"
branch_labels = None
depends_on = None


def _column_names(inspector: Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _slugify(value: str | None) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return normalized or "item"


def _next_unique_slug(base: str, seen: set[str]) -> str:
    slug = base
    suffix = 2
    while slug in seen:
        slug = f"{base}-{suffix}"
        suffix += 1
    seen.add(slug)
    return slug


def _backfill_business_slugs(bind) -> None:
    rows = (
        bind.execute(
            sa.text(
                """
                SELECT id, display_name, name
                FROM businesses
                ORDER BY created_at, id
                """
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        return

    bind.execute(sa.text("UPDATE businesses SET slug = CONCAT('tmp-', id::text)"))

    seen: set[str] = set()
    for row in rows:
        slug = _next_unique_slug(_slugify(row["display_name"] or row["name"]), seen)
        bind.execute(
            sa.text("UPDATE businesses SET slug = :slug WHERE id = :id"),
            {"id": row["id"], "slug": slug},
        )


def _backfill_location_slugs(bind) -> None:
    rows = (
        bind.execute(
            sa.text(
                """
                SELECT id, business_id, display_name, name
                FROM locations
                ORDER BY business_id, created_at, id
                """
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        return

    bind.execute(sa.text("UPDATE locations SET slug = CONCAT('tmp-', id::text)"))

    seen_by_business: dict[object, set[str]] = {}
    for row in rows:
        business_seen = seen_by_business.setdefault(row["business_id"], set())
        slug = _next_unique_slug(_slugify(row["display_name"] or row["name"]), business_seen)
        bind.execute(
            sa.text("UPDATE locations SET slug = :slug WHERE id = :id"),
            {"id": row["id"], "slug": slug},
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    business_columns = _column_names(inspector, "businesses")
    location_columns = _column_names(inspector, "locations")

    if "legal_name" in business_columns and "name" not in business_columns:
        op.alter_column(
            "businesses",
            "legal_name",
            new_column_name="name",
            existing_type=sa.String(length=255),
        )
        business_columns.remove("legal_name")
        business_columns.add("name")

    if "brand_name" in business_columns and "display_name" not in business_columns:
        op.alter_column(
            "businesses",
            "brand_name",
            new_column_name="display_name",
            existing_type=sa.String(length=255),
            existing_nullable=True,
        )
        business_columns.remove("brand_name")
        business_columns.add("display_name")

    if "display_name" not in business_columns:
        op.add_column("businesses", sa.Column("display_name", sa.String(length=255), nullable=True))

    bind.execute(
        sa.text(
            """
            UPDATE businesses
            SET display_name = COALESCE(NULLIF(display_name, ''), NULLIF(name, ''), 'Business')
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE businesses
            SET settings = CASE
                WHEN settings ? 'brand_name_source' THEN
                    jsonb_set(
                        settings - 'brand_name_source',
                        '{display_name_source}',
                        settings->'brand_name_source',
                        true
                    )
                ELSE settings
            END
            """
        )
    )
    op.alter_column(
        "businesses",
        "display_name",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    if "display_name" not in location_columns:
        op.add_column("locations", sa.Column("display_name", sa.String(length=255), nullable=True))

    bind.execute(
        sa.text(
            """
            UPDATE locations
            SET display_name = COALESCE(
                NULLIF(settings->'derived_identity'->>'location_label', ''),
                NULLIF(settings->'derived_identity'->>'suggested_location_name', ''),
                NULLIF(name, ''),
                'Location'
            )
            """
        )
    )
    op.alter_column(
        "locations",
        "display_name",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    _backfill_business_slugs(bind)
    _backfill_location_slugs(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    business_columns = _column_names(inspector, "businesses")
    location_columns = _column_names(inspector, "locations")

    if "display_name" in business_columns and "brand_name" not in business_columns:
        bind.execute(
            sa.text(
                """
                UPDATE businesses
                SET settings = CASE
                    WHEN settings ? 'display_name_source' THEN
                        jsonb_set(
                            settings - 'display_name_source',
                            '{brand_name_source}',
                            settings->'display_name_source',
                            true
                        )
                    ELSE settings
                END
                """
            )
        )
        op.alter_column(
            "businesses",
            "display_name",
            new_column_name="brand_name",
            existing_type=sa.String(length=255),
            existing_nullable=False,
            nullable=True,
        )

    if "name" in business_columns and "legal_name" not in business_columns:
        op.alter_column(
            "businesses",
            "name",
            new_column_name="legal_name",
            existing_type=sa.String(length=255),
        )

    if "display_name" in location_columns:
        op.drop_column("locations", "display_name")
