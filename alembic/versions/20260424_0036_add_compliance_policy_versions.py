"""add compliance policy versions

Revision ID: 20260424_0036
Revises: 20260424_0035
Create Date: 2026-04-24 22:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260424_0036"
down_revision = "20260424_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "compliance_policy_versions",
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("replaces_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("policy_scope", sa.String(length=32), nullable=False),
        sa.Column("policy_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "settings_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["replaces_version_id"],
            ["compliance_policy_versions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_policy_versions_business_scope_effective",
        "compliance_policy_versions",
        ["business_id", "policy_scope", "effective_at"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_policy_versions_location_effective",
        "compliance_policy_versions",
        ["location_id", "effective_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_compliance_policy_versions_location_effective",
        table_name="compliance_policy_versions",
    )
    op.drop_index(
        "ix_compliance_policy_versions_business_scope_effective",
        table_name="compliance_policy_versions",
    )
    op.drop_table("compliance_policy_versions")
