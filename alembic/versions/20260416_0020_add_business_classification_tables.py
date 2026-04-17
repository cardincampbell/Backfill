"""add business classification tables

Revision ID: 20260416_0020
Revises: 20260414_0019
Create Date: 2026-04-16 12:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260416_0020"
down_revision = "20260414_0019"
branch_labels = None
depends_on = None


def _subvertical_rows() -> list[dict[str, object]]:
    return [
        {"code": "full_service_restaurant", "business_vertical_code": "restaurant", "display_name": "Full Service Restaurant"},
        {"code": "takeout_restaurant", "business_vertical_code": "restaurant", "display_name": "Takeout Restaurant"},
        {"code": "delivery_restaurant", "business_vertical_code": "restaurant", "display_name": "Delivery Restaurant"},
        {"code": "cafe", "business_vertical_code": "cafe", "display_name": "Cafe"},
        {"code": "coffee_shop", "business_vertical_code": "cafe", "display_name": "Coffee Shop"},
        {"code": "bakery", "business_vertical_code": "bakery", "display_name": "Bakery"},
        {"code": "bar", "business_vertical_code": "bar", "display_name": "Bar"},
        {"code": "pub", "business_vertical_code": "bar", "display_name": "Pub"},
        {"code": "wine_bar", "business_vertical_code": "bar", "display_name": "Wine Bar"},
        {"code": "nightlife", "business_vertical_code": "bar", "display_name": "Nightlife"},
        {"code": "grocery", "business_vertical_code": "retail", "display_name": "Grocery"},
        {"code": "convenience", "business_vertical_code": "retail", "display_name": "Convenience"},
        {"code": "department_store", "business_vertical_code": "retail", "display_name": "Department Store"},
        {"code": "shopping_center", "business_vertical_code": "retail", "display_name": "Shopping Center"},
        {"code": "apparel", "business_vertical_code": "retail", "display_name": "Apparel"},
        {"code": "specialty_retail", "business_vertical_code": "retail", "display_name": "Specialty Retail"},
        {"code": "hair_salon", "business_vertical_code": "beauty", "display_name": "Hair Salon"},
        {"code": "beauty_salon", "business_vertical_code": "beauty", "display_name": "Beauty Salon"},
        {"code": "barber_shop", "business_vertical_code": "beauty", "display_name": "Barber Shop"},
        {"code": "nail_salon", "business_vertical_code": "beauty", "display_name": "Nail Salon"},
        {"code": "spa", "business_vertical_code": "beauty", "display_name": "Spa"},
        {"code": "gym", "business_vertical_code": "fitness", "display_name": "Gym"},
        {"code": "fitness_center", "business_vertical_code": "fitness", "display_name": "Fitness Center"},
        {"code": "yoga_studio", "business_vertical_code": "fitness", "display_name": "Yoga Studio"},
        {"code": "pilates_studio", "business_vertical_code": "fitness", "display_name": "Pilates Studio"},
        {"code": "dentistry", "business_vertical_code": "dental_clinic", "display_name": "Dentistry"},
        {"code": "orthodontics", "business_vertical_code": "dental_clinic", "display_name": "Orthodontics"},
        {"code": "doctor_office", "business_vertical_code": "medical_clinic", "display_name": "Doctor Office"},
        {"code": "hospital", "business_vertical_code": "medical_clinic", "display_name": "Hospital"},
        {"code": "medical_lab", "business_vertical_code": "medical_clinic", "display_name": "Medical Lab"},
        {"code": "urgent_care", "business_vertical_code": "medical_clinic", "display_name": "Urgent Care"},
        {"code": "pharmacy", "business_vertical_code": "medical_clinic", "display_name": "Pharmacy"},
        {"code": "electrical", "business_vertical_code": "home_services", "display_name": "Electrical"},
        {"code": "plumbing", "business_vertical_code": "home_services", "display_name": "Plumbing"},
        {"code": "roofing", "business_vertical_code": "home_services", "display_name": "Roofing"},
        {"code": "hvac", "business_vertical_code": "home_services", "display_name": "HVAC"},
        {"code": "contracting", "business_vertical_code": "home_services", "display_name": "Contracting"},
        {"code": "locksmith", "business_vertical_code": "home_services", "display_name": "Locksmith"},
        {"code": "moving", "business_vertical_code": "home_services", "display_name": "Moving"},
        {"code": "painting", "business_vertical_code": "home_services", "display_name": "Painting"},
        {"code": "warehouse", "business_vertical_code": "warehouse", "display_name": "Warehouse"},
        {"code": "storage", "business_vertical_code": "warehouse", "display_name": "Storage"},
        {"code": "lodging", "business_vertical_code": "hotel", "display_name": "Lodging"},
        {"code": "hotel", "business_vertical_code": "hotel", "display_name": "Hotel"},
        {"code": "motel", "business_vertical_code": "hotel", "display_name": "Motel"},
        {"code": "resort", "business_vertical_code": "hotel", "display_name": "Resort"},
        {"code": "legal", "business_vertical_code": "professional_office", "display_name": "Legal"},
        {"code": "accounting", "business_vertical_code": "professional_office", "display_name": "Accounting"},
        {"code": "insurance", "business_vertical_code": "professional_office", "display_name": "Insurance"},
        {"code": "real_estate", "business_vertical_code": "professional_office", "display_name": "Real Estate"},
        {"code": "finance", "business_vertical_code": "professional_office", "display_name": "Finance"},
        {"code": "office", "business_vertical_code": "professional_office", "display_name": "Office"},
    ]


def upgrade() -> None:
    op.create_table(
        "business_subverticals",
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("business_vertical_code", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["business_vertical_code"], ["business_verticals.code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_index(
        "ix_business_subverticals_vertical_active",
        "business_subverticals",
        ["business_vertical_code", "is_active"],
        unique=False,
    )

    subvertical_table = sa.table(
        "business_subverticals",
        sa.column("code", sa.String()),
        sa.column("business_vertical_code", sa.String()),
        sa.column("display_name", sa.String()),
    )
    op.bulk_insert(subvertical_table, _subvertical_rows())

    op.create_foreign_key(
        "fk_business_vertical_type_mappings_subvertical_code",
        "business_vertical_type_mappings",
        "business_subverticals",
        ["subvertical_code"],
        ["code"],
        ondelete="SET NULL",
    )

    op.create_table(
        "business_derivation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("llm_generation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="shadow"),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False, server_default="classify"),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("vertical_code", sa.String(length=80), nullable=False),
        sa.Column("subvertical_code", sa.String(length=120), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column("evidence_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("baseline_role_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("selected_role_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("applied_role_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["llm_generation_id"], ["llm_generations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_business_derivation_runs_business_id_created_at",
        "business_derivation_runs",
        ["business_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_business_derivation_runs_business_id_applied",
        "business_derivation_runs",
        ["business_id", "applied"],
        unique=False,
    )

    op.create_table(
        "business_derivation_gap_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("derivation_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("suggestion_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("vertical_code", sa.String(length=80), nullable=True),
        sa.Column("subvertical_code", sa.String(length=120), nullable=True),
        sa.Column("proposed_code", sa.String(length=120), nullable=True),
        sa.Column("proposed_display_name", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("suggestion_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["derivation_run_id"], ["business_derivation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_business_derivation_gap_suggestions_business_id_status",
        "business_derivation_gap_suggestions",
        ["business_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_business_derivation_gap_suggestions_run_id",
        "business_derivation_gap_suggestions",
        ["derivation_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_business_derivation_gap_suggestions_run_id", table_name="business_derivation_gap_suggestions")
    op.drop_index("ix_business_derivation_gap_suggestions_business_id_status", table_name="business_derivation_gap_suggestions")
    op.drop_table("business_derivation_gap_suggestions")

    op.drop_index("ix_business_derivation_runs_business_id_applied", table_name="business_derivation_runs")
    op.drop_index("ix_business_derivation_runs_business_id_created_at", table_name="business_derivation_runs")
    op.drop_table("business_derivation_runs")

    op.drop_constraint(
        "fk_business_vertical_type_mappings_subvertical_code",
        "business_vertical_type_mappings",
        type_="foreignkey",
    )
    op.drop_index("ix_business_subverticals_vertical_active", table_name="business_subverticals")
    op.drop_table("business_subverticals")
