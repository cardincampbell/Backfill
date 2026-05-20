"""update california general compliance pack

Revision ID: 20260429_0040
Revises: 20260428_0039
Create Date: 2026-04-29 11:10:00.000000
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260429_0040"
down_revision = "20260428_0039"
branch_labels = None
depends_on = None


def _uuid(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"backfill:labor-rules:{name}")


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


def _old_definition() -> dict[str, object]:
    return {
        "id": _uuid("profile:us_ca_general_nonexempt"),
        "code": "us_ca_general_nonexempt",
        "jurisdiction_code": "US-CA",
        "display_name": "California General Nonexempt",
        "overtime_mode": "daily_8_plus_weekly_plus_7th_day",
        "daily_ot_threshold_hours": 8.0,
        "weekly_ot_threshold_hours": 40.0,
        "double_time_threshold_hours": 12.0,
        "consecutive_hours_threshold_hours": None,
        "industry_profile_code": None,
        "rules_json": {
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
        },
        "effective_start_date": date(2026, 1, 1),
        "effective_end_date": None,
        "source_urls": [
            "https://www.dir.ca.gov/dlse/faq_overtime.htm",
        ],
        "source_version": "seed_v1",
    }


def _new_definition() -> dict[str, object]:
    return {
        "id": _uuid("profile:us_ca_general_nonexempt"),
        "code": "us_ca_general_nonexempt",
        "jurisdiction_code": "US-CA",
        "display_name": "California General Nonexempt",
        "overtime_mode": "daily_8_plus_weekly_plus_7th_day",
        "daily_ot_threshold_hours": 8.0,
        "weekly_ot_threshold_hours": 40.0,
        "double_time_threshold_hours": 12.0,
        "consecutive_hours_threshold_hours": None,
        "industry_profile_code": None,
        "rules_json": {
            "workweek_start_day_local": "monday",
            "workweek_start_time_local": "00:00",
            "meal_break_ruleset": "ca_v1",
            "rest_break_ruleset": "ca_v1",
            "day_of_rest_ruleset": "ca_v1",
            "day_of_rest_workweek_required": True,
        },
        "effective_start_date": date(2026, 1, 1),
        "effective_end_date": None,
        "source_urls": [
            "https://www.dir.ca.gov/dlse/faq_overtime.htm",
            "https://www.dir.ca.gov/dlse/FAQ_MealPeriods.html",
            "https://dir.ca.gov/dlse/faq_restperiods.htm",
            "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=LAB&sectionNum=551",
            "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=LAB&sectionNum=552",
            "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=LAB&sectionNum=556",
        ],
        "source_version": "seed_v2_ca_general_compliance_pack",
    }


def _profile_table() -> sa.Table:
    return sa.table(
        "labor_rule_profiles",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String()),
        sa.column("rules_json", postgresql.JSONB()),
        sa.column("source_urls", postgresql.JSONB()),
        sa.column("source_version", sa.String()),
        sa.column("source_hash", sa.String()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
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


def _resolution_table() -> sa.Table:
    return sa.table(
        "location_labor_rule_resolutions",
        sa.column("resolved_profile_code", sa.String()),
        sa.column("resolved_profile_version_id", postgresql.UUID(as_uuid=True)),
        sa.column("resolved_profile_payload_hash", sa.String()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )


def _apply_profile_update(
    *,
    definition: dict[str, object],
    version_id: uuid.UUID,
    version_no: int,
    change_summary: str,
    delete_version_id: uuid.UUID | None = None,
    insert_version: bool = True,
) -> None:
    profile_table = _profile_table()
    version_table = _version_table()
    resolution_table = _resolution_table()

    payload = _profile_payload(definition)
    payload_hash = _payload_hash(payload)

    op.execute(
        profile_table.update()
        .where(profile_table.c.id == definition["id"])
        .values(
            rules_json=definition["rules_json"],
            source_urls=definition["source_urls"],
            source_version=definition["source_version"],
            source_hash=payload_hash,
            updated_at=sa.text("CURRENT_TIMESTAMP"),
        )
    )

    if delete_version_id is not None:
        op.execute(version_table.delete().where(version_table.c.id == delete_version_id))

    if insert_version:
        op.execute(
            version_table.insert().values(
                id=version_id,
                labor_rule_profile_id=definition["id"],
                version_no=version_no,
                payload_json=payload,
                payload_hash=payload_hash,
                change_summary=change_summary,
                created_by="system_seed",
            )
        )

    op.execute(
        resolution_table.update()
        .where(resolution_table.c.resolved_profile_code == str(definition["code"]))
        .values(
            resolved_profile_version_id=version_id,
            resolved_profile_payload_hash=payload_hash,
            updated_at=sa.text("CURRENT_TIMESTAMP"),
        )
    )


def upgrade() -> None:
    _apply_profile_update(
        definition=_new_definition(),
        version_id=_uuid("version:us_ca_general_nonexempt:2"),
        version_no=2,
        change_summary="Seed California meal, rest, and day-of-rest compliance pack",
    )


def downgrade() -> None:
    _apply_profile_update(
        definition=_old_definition(),
        version_id=_uuid("version:us_ca_general_nonexempt:1"),
        version_no=1,
        change_summary="Initial seeded labor rule profile",
        delete_version_id=_uuid("version:us_ca_general_nonexempt:2"),
        insert_version=False,
    )
