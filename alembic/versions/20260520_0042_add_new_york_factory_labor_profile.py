"""add new york factory labor profile

Revision ID: 20260520_0042
Revises: 20260501_0041
Create Date: 2026-05-20 11:20:00.000000
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260520_0042"
down_revision = "20260501_0041"
branch_labels = None
depends_on = None


def _uuid(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"backfill:labor-rules:{name}")


def _definition() -> dict[str, object]:
    return {
        "id": _uuid("profile:us_ny_factory_nonexempt"),
        "code": "us_ny_factory_nonexempt",
        "jurisdiction_code": "US-NY",
        "display_name": "New York Factory Nonexempt",
        "overtime_mode": "weekly_only",
        "daily_ot_threshold_hours": None,
        "weekly_ot_threshold_hours": 40.0,
        "double_time_threshold_hours": None,
        "consecutive_hours_threshold_hours": None,
        "industry_profile_code": "manufacturing",
        "rules_json": {
            "workweek_start_day_local": "sunday",
            "workweek_start_time_local": "00:00",
            "meal_break_ruleset": "ny_factory_v1",
            "day_of_rest_workweek_required": True,
        },
        "effective_start_date": date(2026, 1, 1),
        "effective_end_date": None,
        "source_urls": [
            "https://dol.ny.gov/system/files/documents/2021/03/meal-and-rest-periods-frequently-asked-questions.pdf",
            "https://dol.ny.gov/LS443-doc",
            "https://dol.ny.gov/day-rest-and-meal-periods",
        ],
        "source_version": "seed_v1_ny_factory_compliance_pack",
    }


def _profile_payload(definition: dict[str, object]) -> dict[str, object]:
    return {
        "profile_id": str(definition["id"]),
        "code": definition["code"],
        "jurisdiction_code": definition["jurisdiction_code"],
        "display_name": definition["display_name"],
        "overtime_mode": definition["overtime_mode"],
        "daily_ot_threshold_hours": definition["daily_ot_threshold_hours"],
        "weekly_ot_threshold_hours": definition["weekly_ot_threshold_hours"],
        "double_time_threshold_hours": definition["double_time_threshold_hours"],
        "consecutive_hours_threshold_hours": definition["consecutive_hours_threshold_hours"],
        "industry_profile_code": definition["industry_profile_code"],
        "rules_json": definition["rules_json"],
        "effective_start_date": (
            definition["effective_start_date"].isoformat()
            if definition["effective_start_date"]
            else None
        ),
        "effective_end_date": (
            definition["effective_end_date"].isoformat()
            if definition["effective_end_date"]
            else None
        ),
        "source_urls": definition["source_urls"],
        "source_version": definition["source_version"],
        "source_hash": None,
    }


def _payload_hash(payload: dict[str, object]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"


def _profile_table() -> sa.Table:
    return sa.table(
        "labor_rule_profiles",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String()),
        sa.column("jurisdiction_code", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("overtime_mode", sa.String()),
        sa.column("daily_ot_threshold_hours", sa.Numeric()),
        sa.column("weekly_ot_threshold_hours", sa.Numeric()),
        sa.column("double_time_threshold_hours", sa.Numeric()),
        sa.column("consecutive_hours_threshold_hours", sa.Numeric()),
        sa.column("industry_profile_code", sa.String()),
        sa.column("rules_json", postgresql.JSONB()),
        sa.column("effective_start_date", sa.Date()),
        sa.column("effective_end_date", sa.Date()),
        sa.column("source_urls", postgresql.JSONB()),
        sa.column("source_version", sa.String()),
        sa.column("source_hash", sa.String()),
    )


def _version_table() -> sa.Table:
    return sa.table(
        "labor_rule_profile_versions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("labor_rule_profile_id", postgresql.UUID(as_uuid=True)),
        sa.column("version_no", sa.Integer()),
        sa.column("payload_json", postgresql.JSONB()),
        sa.column("payload_hash", sa.String()),
        sa.column("change_summary", sa.Text()),
        sa.column("created_by", sa.String()),
    )


def upgrade() -> None:
    definition = _definition()
    payload = _profile_payload(definition)
    payload_hash = _payload_hash(payload)

    profile_table = _profile_table()
    version_table = _version_table()

    bind = op.get_bind()
    existing_profile_id = bind.execute(
        sa.select(profile_table.c.id).where(profile_table.c.code == str(definition["code"]))
    ).scalar_one_or_none()

    if existing_profile_id is None:
        op.execute(
            profile_table.insert().values(
                id=definition["id"],
                code=definition["code"],
                jurisdiction_code=definition["jurisdiction_code"],
                display_name=definition["display_name"],
                overtime_mode=definition["overtime_mode"],
                daily_ot_threshold_hours=definition["daily_ot_threshold_hours"],
                weekly_ot_threshold_hours=definition["weekly_ot_threshold_hours"],
                double_time_threshold_hours=definition["double_time_threshold_hours"],
                consecutive_hours_threshold_hours=definition["consecutive_hours_threshold_hours"],
                industry_profile_code=definition["industry_profile_code"],
                rules_json=definition["rules_json"],
                effective_start_date=definition["effective_start_date"],
                effective_end_date=definition["effective_end_date"],
                source_urls=definition["source_urls"],
                source_version=definition["source_version"],
                source_hash=payload_hash,
            )
        )
        profile_id = definition["id"]
    else:
        op.execute(
            profile_table.update()
            .where(profile_table.c.id == existing_profile_id)
            .values(
                jurisdiction_code=definition["jurisdiction_code"],
                display_name=definition["display_name"],
                overtime_mode=definition["overtime_mode"],
                daily_ot_threshold_hours=definition["daily_ot_threshold_hours"],
                weekly_ot_threshold_hours=definition["weekly_ot_threshold_hours"],
                double_time_threshold_hours=definition["double_time_threshold_hours"],
                consecutive_hours_threshold_hours=definition["consecutive_hours_threshold_hours"],
                industry_profile_code=definition["industry_profile_code"],
                rules_json=definition["rules_json"],
                effective_start_date=definition["effective_start_date"],
                effective_end_date=definition["effective_end_date"],
                source_urls=definition["source_urls"],
                source_version=definition["source_version"],
                source_hash=payload_hash,
            )
        )
        profile_id = existing_profile_id

    version_id = _uuid("version:us_ny_factory_nonexempt:1")
    existing_version_id = bind.execute(
        sa.select(version_table.c.id).where(version_table.c.id == version_id)
    ).scalar_one_or_none()
    if existing_version_id is None:
        op.execute(
            version_table.insert().values(
                id=version_id,
                labor_rule_profile_id=profile_id,
                version_no=1,
                payload_json=payload,
                payload_hash=payload_hash,
                change_summary="Seed New York factory meal-period and rest-day profile",
                created_by="system_seed",
            )
        )


def downgrade() -> None:
    profile_table = _profile_table()
    version_table = _version_table()

    op.execute(
        version_table.delete().where(
            version_table.c.id == _uuid("version:us_ny_factory_nonexempt:1")
        )
    )
    op.execute(
        profile_table.delete().where(
            profile_table.c.code == "us_ny_factory_nonexempt"
        )
    )
