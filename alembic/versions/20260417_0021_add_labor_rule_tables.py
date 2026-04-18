"""add labor rule tables

Revision ID: 20260417_0021
Revises: 20260416_0020
Create Date: 2026-04-17 12:30:00.000000
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260417_0021"
down_revision = "20260416_0020"
branch_labels = None
depends_on = None


def _uuid(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"backfill:labor-rules:{name}")


def _industry_rows() -> list[dict[str, object]]:
    return [
        {
            "id": _uuid("industry:general"),
            "code": "general",
            "display_name": "General",
            "description": "General nonexempt labor profile family.",
            "jurisdiction_code": None,
            "metadata_json": {},
        },
        {
            "id": _uuid("industry:manufacturing"),
            "code": "manufacturing",
            "display_name": "Manufacturing",
            "description": "Manufacturing-specific labor profile family.",
            "jurisdiction_code": None,
            "metadata_json": {},
        },
        {
            "id": _uuid("industry:hospitality"),
            "code": "hospitality",
            "display_name": "Hospitality",
            "description": "Hospitality and lodging labor profile family.",
            "jurisdiction_code": None,
            "metadata_json": {},
        },
        {
            "id": _uuid("industry:healthcare"),
            "code": "healthcare",
            "display_name": "Healthcare",
            "description": "Healthcare and hospital labor profile family.",
            "jurisdiction_code": None,
            "metadata_json": {},
        },
        {
            "id": _uuid("industry:public_works"),
            "code": "public_works",
            "display_name": "Public Works",
            "description": "Public works and prevailing wage labor profile family.",
            "jurisdiction_code": None,
            "metadata_json": {},
        },
    ]


def _profile_definitions() -> list[dict[str, object]]:
    return [
        {
            "id": _uuid("profile:us_flsa_general"),
            "code": "us_flsa_general",
            "jurisdiction_code": "US",
            "display_name": "Federal General Nonexempt",
            "overtime_mode": "weekly_only",
            "daily_ot_threshold_hours": None,
            "weekly_ot_threshold_hours": 40.0,
            "double_time_threshold_hours": None,
            "consecutive_hours_threshold_hours": None,
            "industry_profile_code": None,
            "rules_json": {
                "workweek_start_day_local": "monday",
                "workweek_start_time_local": "00:00",
            },
            "effective_start_date": date(2026, 1, 1),
            "effective_end_date": None,
            "source_urls": [
                "https://www.dol.gov/agencies/whd/overtime",
            ],
            "source_version": "seed_v1",
        },
        {
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
        },
        {
            "id": _uuid("profile:us_ak_general_nonexempt"),
            "code": "us_ak_general_nonexempt",
            "jurisdiction_code": "US-AK",
            "display_name": "Alaska General Nonexempt",
            "overtime_mode": "daily_8_plus_weekly",
            "daily_ot_threshold_hours": 8.0,
            "weekly_ot_threshold_hours": 40.0,
            "double_time_threshold_hours": None,
            "consecutive_hours_threshold_hours": None,
            "industry_profile_code": None,
            "rules_json": {
                "workweek_start_day_local": "monday",
                "workweek_start_time_local": "00:00",
            },
            "effective_start_date": date(2026, 1, 1),
            "effective_end_date": None,
            "source_urls": [
                "https://labor.alaska.gov/lss/whact.htm",
            ],
            "source_version": "seed_v1",
        },
        {
            "id": _uuid("profile:us_co_general_nonexempt"),
            "code": "us_co_general_nonexempt",
            "jurisdiction_code": "US-CO",
            "display_name": "Colorado General Nonexempt",
            "overtime_mode": "daily_12_or_consecutive_plus_weekly",
            "daily_ot_threshold_hours": 12.0,
            "weekly_ot_threshold_hours": 40.0,
            "double_time_threshold_hours": None,
            "consecutive_hours_threshold_hours": 12.0,
            "industry_profile_code": None,
            "rules_json": {
                "workweek_start_day_local": "monday",
                "workweek_start_time_local": "00:00",
            },
            "effective_start_date": date(2026, 1, 1),
            "effective_end_date": None,
            "source_urls": [
                "https://cdle.colorado.gov/wage-and-hour-law/overtime",
            ],
            "source_version": "seed_v1",
        },
        {
            "id": _uuid("profile:us_nv_general_fallback"),
            "code": "us_nv_general_fallback",
            "jurisdiction_code": "US-NV",
            "display_name": "Nevada General Fallback",
            "overtime_mode": "weekly_only",
            "daily_ot_threshold_hours": None,
            "weekly_ot_threshold_hours": 40.0,
            "double_time_threshold_hours": None,
            "consecutive_hours_threshold_hours": None,
            "industry_profile_code": None,
            "rules_json": {
                "workweek_start_day_local": "monday",
                "workweek_start_time_local": "00:00",
                "conditional_rule_pending": True,
            },
            "effective_start_date": date(2026, 1, 1),
            "effective_end_date": None,
            "source_urls": [
                "https://labor.nv.gov/Wages/Overtime/",
            ],
            "source_version": "seed_v1",
        },
        {
            "id": _uuid("profile:us_or_general_fallback"),
            "code": "us_or_general_fallback",
            "jurisdiction_code": "US-OR",
            "display_name": "Oregon General Fallback",
            "overtime_mode": "weekly_only",
            "daily_ot_threshold_hours": None,
            "weekly_ot_threshold_hours": 40.0,
            "double_time_threshold_hours": None,
            "consecutive_hours_threshold_hours": None,
            "industry_profile_code": None,
            "rules_json": {
                "workweek_start_day_local": "monday",
                "workweek_start_time_local": "00:00",
                "specialized_industry_pending": True,
            },
            "effective_start_date": date(2026, 1, 1),
            "effective_end_date": None,
            "source_urls": [
                "https://www.oregon.gov/boli/workers/pages/overtime.aspx",
            ],
            "source_version": "seed_v1",
        },
    ]


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
        "effective_start_date": definition["effective_start_date"].isoformat() if definition["effective_start_date"] else None,
        "effective_end_date": definition["effective_end_date"].isoformat() if definition["effective_end_date"] else None,
        "source_urls": definition["source_urls"],
        "source_version": definition["source_version"],
        "source_hash": None,
    }


def _payload_hash(payload: dict[str, object]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"


def upgrade() -> None:
    op.create_table(
        "labor_industry_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("jurisdiction_code", sa.String(length=24), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_labor_industry_profiles_code"),
    )
    op.create_index(
        "ix_labor_industry_profiles_jurisdiction_active",
        "labor_industry_profiles",
        ["jurisdiction_code", "is_active"],
        unique=False,
    )

    op.create_table(
        "labor_rule_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("jurisdiction_code", sa.String(length=24), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("overtime_mode", sa.String(length=64), nullable=False),
        sa.Column("daily_ot_threshold_hours", sa.Numeric(6, 2), nullable=True),
        sa.Column("weekly_ot_threshold_hours", sa.Numeric(6, 2), nullable=True),
        sa.Column("double_time_threshold_hours", sa.Numeric(6, 2), nullable=True),
        sa.Column("consecutive_hours_threshold_hours", sa.Numeric(6, 2), nullable=True),
        sa.Column("industry_profile_code", sa.String(length=120), nullable=True),
        sa.Column("rules_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("effective_start_date", sa.Date(), nullable=True),
        sa.Column("effective_end_date", sa.Date(), nullable=True),
        sa.Column("source_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_version", sa.String(length=255), nullable=True),
        sa.Column("source_hash", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["industry_profile_code"], ["labor_industry_profiles.code"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_labor_rule_profiles_code"),
    )
    op.create_index(
        "ix_labor_rule_profiles_jurisdiction_active",
        "labor_rule_profiles",
        ["jurisdiction_code", "is_active"],
        unique=False,
    )

    op.create_table(
        "labor_rule_profile_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("labor_rule_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("payload_hash", sa.String(length=255), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["labor_rule_profile_id"], ["labor_rule_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "labor_rule_profile_id",
            "version_no",
            name="uq_labor_rule_profile_versions_profile_id_version_no",
        ),
        sa.UniqueConstraint("payload_hash", name="uq_labor_rule_profile_versions_payload_hash"),
    )
    op.create_index(
        "ix_labor_rule_profile_versions_profile_id_version_no",
        "labor_rule_profile_versions",
        ["labor_rule_profile_id", "version_no"],
        unique=False,
    )

    op.create_table(
        "labor_rule_source_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jurisdiction_code", sa.String(length=24), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("http_etag", sa.String(length=255), nullable=True),
        sa.Column("http_last_modified", sa.String(length=255), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("normalized_text", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_labor_rule_source_documents_jurisdiction_active",
        "labor_rule_source_documents",
        ["jurisdiction_code", "is_active"],
        unique=False,
    )

    op.create_table(
        "labor_rule_update_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jurisdiction_code", sa.String(length=24), nullable=False),
        sa.Column("proposal_status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("proposal_type", sa.String(length=64), nullable=False, server_default="profile_update"),
        sa.Column("current_profile_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("proposed_profiles_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("reason_summary", sa.Text(), nullable=True),
        sa.Column("citations_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("llm_provider", sa.String(length=64), nullable=True),
        sa.Column("llm_model", sa.String(length=255), nullable=True),
        sa.Column("llm_generation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_by", sa.String(length=120), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["llm_generation_id"], ["llm_generations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_labor_rule_update_proposals_jurisdiction_status",
        "labor_rule_update_proposals",
        ["jurisdiction_code", "proposal_status"],
        unique=False,
    )

    op.create_table(
        "location_labor_rule_resolutions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jurisdiction_code", sa.String(length=24), nullable=False),
        sa.Column("resolved_profile_code", sa.String(length=120), nullable=False),
        sa.Column("resolved_profile_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resolved_profile_payload_hash", sa.String(length=255), nullable=False),
        sa.Column("resolution_source", sa.String(length=32), nullable=False),
        sa.Column("resolution_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("manual_override_profile_code", sa.String(length=120), nullable=True),
        sa.Column("resolution_context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("llm_generation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["llm_generation_id"], ["llm_generations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manual_override_profile_code"], ["labor_rule_profiles.code"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_profile_code"], ["labor_rule_profiles.code"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_profile_version_id"], ["labor_rule_profile_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("location_id", name="uq_location_labor_rule_resolutions_location_id"),
    )
    op.create_index(
        "ix_location_labor_rule_resolutions_jurisdiction_source",
        "location_labor_rule_resolutions",
        ["jurisdiction_code", "resolution_source"],
        unique=False,
    )

    op.create_table(
        "labor_rule_resolution_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jurisdiction_code", sa.String(length=24), nullable=False),
        sa.Column("candidate_profile_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("selected_profile_code", sa.String(length=120), nullable=True),
        sa.Column("selected_profile_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("selected_profile_payload_hash", sa.String(length=255), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("input_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("llm_generation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["llm_generation_id"], ["llm_generations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["selected_profile_code"], ["labor_rule_profiles.code"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["selected_profile_version_id"], ["labor_rule_profile_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_labor_rule_resolution_runs_location_id_created_at",
        "labor_rule_resolution_runs",
        ["location_id", "created_at"],
        unique=False,
    )

    industry_table = sa.table(
        "labor_industry_profiles",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("jurisdiction_code", sa.String()),
        sa.column("metadata_json", postgresql.JSONB()),
    )
    op.bulk_insert(industry_table, _industry_rows())

    profile_rows = []
    version_rows = []
    for definition in _profile_definitions():
        payload = _profile_payload(definition)
        payload_hash = _payload_hash(payload)
        definition["source_hash"] = payload_hash
        profile_rows.append(
            {
                "id": definition["id"],
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
                "effective_start_date": definition["effective_start_date"],
                "effective_end_date": definition["effective_end_date"],
                "source_urls": definition["source_urls"],
                "source_version": definition["source_version"],
                "source_hash": payload_hash,
            }
        )
        version_rows.append(
            {
                "id": _uuid(f"version:{definition['code']}:1"),
                "labor_rule_profile_id": definition["id"],
                "version_no": 1,
                "payload_json": payload,
                "payload_hash": payload_hash,
                "change_summary": "Initial seeded labor rule profile",
                "created_by": "system_seed",
            }
        )

    profile_table = sa.table(
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
    version_table = sa.table(
        "labor_rule_profile_versions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("labor_rule_profile_id", postgresql.UUID(as_uuid=True)),
        sa.column("version_no", sa.Integer()),
        sa.column("payload_json", postgresql.JSONB()),
        sa.column("payload_hash", sa.String()),
        sa.column("change_summary", sa.Text()),
        sa.column("created_by", sa.String()),
    )
    op.bulk_insert(profile_table, profile_rows)
    op.bulk_insert(version_table, version_rows)


def downgrade() -> None:
    op.drop_index("ix_labor_rule_resolution_runs_location_id_created_at", table_name="labor_rule_resolution_runs")
    op.drop_table("labor_rule_resolution_runs")

    op.drop_index("ix_location_labor_rule_resolutions_jurisdiction_source", table_name="location_labor_rule_resolutions")
    op.drop_table("location_labor_rule_resolutions")

    op.drop_index("ix_labor_rule_update_proposals_jurisdiction_status", table_name="labor_rule_update_proposals")
    op.drop_table("labor_rule_update_proposals")

    op.drop_index("ix_labor_rule_source_documents_jurisdiction_active", table_name="labor_rule_source_documents")
    op.drop_table("labor_rule_source_documents")

    op.drop_index("ix_labor_rule_profile_versions_profile_id_version_no", table_name="labor_rule_profile_versions")
    op.drop_table("labor_rule_profile_versions")

    op.drop_index("ix_labor_rule_profiles_jurisdiction_active", table_name="labor_rule_profiles")
    op.drop_table("labor_rule_profiles")

    op.drop_index("ix_labor_industry_profiles_jurisdiction_active", table_name="labor_industry_profiles")
    op.drop_table("labor_industry_profiles")
