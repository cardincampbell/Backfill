"""add compliance override artifacts

Revision ID: 20260422_0032
Revises: 20260422_0031
Create Date: 2026-04-22 13:05:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260422_0032"
down_revision = "20260422_0031"
branch_labels = None
depends_on = None


artifact_type_enum = postgresql.ENUM(
    "written_consent",
    "manager_override",
    name="compliance_override_artifact_type",
    create_type=False,
)
artifact_status_enum = postgresql.ENUM(
    "approved",
    "revoked",
    "expired",
    name="compliance_override_artifact_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    artifact_type_enum.create(bind, checkfirst=True)
    artifact_status_enum.create(bind, checkfirst=True)
    op.create_table(
        "compliance_override_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shift_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("labor_rule_profile_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rule_code", sa.String(length=120), nullable=False),
        sa.Column("artifact_type", artifact_type_enum, nullable=False, server_default="written_consent"),
        sa.Column("status", artifact_status_enum, nullable=False, server_default="approved"),
        sa.Column("engine_version", sa.String(length=64), nullable=False),
        sa.Column("profile_payload_hash", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "reason_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "artifact_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assignment_id"], ["shift_assignments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["labor_rule_profile_version_id"],
            ["labor_rule_profile_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shift_id"], ["shifts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_override_artifacts_shift_employee_status",
        "compliance_override_artifacts",
        ["shift_id", "employee_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_override_artifacts_employee_rule_code",
        "compliance_override_artifacts",
        ["employee_id", "rule_code"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index(
        "ix_compliance_override_artifacts_employee_rule_code",
        table_name="compliance_override_artifacts",
    )
    op.drop_index(
        "ix_compliance_override_artifacts_shift_employee_status",
        table_name="compliance_override_artifacts",
    )
    op.drop_table("compliance_override_artifacts")
    artifact_status_enum.drop(bind, checkfirst=True)
    artifact_type_enum.drop(bind, checkfirst=True)
