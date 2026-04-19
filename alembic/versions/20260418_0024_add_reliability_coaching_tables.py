"""add reliability coaching tables

Revision ID: 20260418_0024
Revises: 20260418_0023
Create Date: 2026-04-18 18:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260418_0024"
down_revision = "20260418_0023"
branch_labels = None
depends_on = None


case_status_enum = postgresql.ENUM(
    "open",
    "suppressed",
    "escalated",
    "closed",
    name="reliability_coaching_case_status",
)
delivery_status_enum = postgresql.ENUM(
    "pending",
    "queued",
    "in_flight",
    "delivered",
    "cooldown_blocked",
    "exhausted",
    name="reliability_coaching_delivery_status",
)
attempt_status_enum = postgresql.ENUM(
    "queued",
    "in_flight",
    "completed",
    "no_answer",
    "failed",
    "cancelled",
    name="reliability_coaching_attempt_status",
)
channel_enum = postgresql.ENUM(
    "sms",
    "email",
    "voice",
    "webhook",
    name="reliability_coaching_channel",
)


def upgrade() -> None:
    bind = op.get_bind()
    case_status_enum.create(bind, checkfirst=True)
    delivery_status_enum.create(bind, checkfirst=True)
    attempt_status_enum.create(bind, checkfirst=True)
    channel_enum.create(bind, checkfirst=True)

    op.create_table(
        "reliability_coaching_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "case_status",
            postgresql.ENUM(
                "open",
                "suppressed",
                "escalated",
                "closed",
                name="reliability_coaching_case_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column(
            "delivery_status",
            postgresql.ENUM(
                "pending",
                "queued",
                "in_flight",
                "delivered",
                "cooldown_blocked",
                "exhausted",
                name="reliability_coaching_delivery_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("coaching_style", sa.String(length=32), nullable=False, server_default=sa.text("'supportive'")),
        sa.Column("policy_version", sa.String(length=64), nullable=False, server_default=sa.text("'v1'")),
        sa.Column("prompt_version", sa.String(length=64), nullable=False, server_default=sa.text("'v1'")),
        sa.Column(
            "trigger_metric",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'callout_count_rolling_7d'"),
        ),
        sa.Column("trigger_threshold", sa.Integer(), nullable=False, server_default=sa.text("2")),
        sa.Column("trigger_window_days", sa.Integer(), nullable=False, server_default=sa.text("7")),
        sa.Column("trigger_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suppressed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suppressed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("suppression_reason_code", sa.String(length=64), nullable=True),
        sa.Column("suppression_note", sa.Text(), nullable=True),
        sa.Column("suppression_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("case_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["suppressed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_reliability_coaching_cases"),
    )
    op.create_index(
        "ix_reliability_coaching_cases_business_employee_created_at",
        "reliability_coaching_cases",
        ["business_id", "employee_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_reliability_coaching_cases_status_created_at",
        "reliability_coaching_cases",
        ["case_status", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_reliability_coaching_cases_active_employee",
        "reliability_coaching_cases",
        ["business_id", "employee_id"],
        unique=True,
        postgresql_where=sa.text("case_status IN ('open', 'suppressed', 'escalated')"),
    )

    op.create_table(
        "reliability_coaching_triggers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("coaching_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reliability_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shift_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trigger_source", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("qualifying_callout_count", sa.Integer(), nullable=False),
        sa.Column("trigger_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["coaching_case_id"], ["reliability_coaching_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reliability_event_id"], ["reliability_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shift_id"], ["shifts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_reliability_coaching_triggers"),
        sa.UniqueConstraint("reliability_event_id", name="uq_reliability_coaching_triggers_reliability_event_id"),
    )
    op.create_index(
        "ix_reliability_coaching_triggers_case_id_occurred_at",
        "reliability_coaching_triggers",
        ["coaching_case_id", "occurred_at"],
        unique=False,
    )

    op.create_table(
        "reliability_coaching_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("coaching_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outbox_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "channel",
            postgresql.ENUM(
                "sms",
                "email",
                "voice",
                "webhook",
                name="reliability_coaching_channel",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'voice'"),
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "queued",
                "in_flight",
                "completed",
                "no_answer",
                "failed",
                "cancelled",
                name="reliability_coaching_attempt_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("provider_conversation_id", sa.String(length=255), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_eligible_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prompt_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("attempt_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["coaching_case_id"], ["reliability_coaching_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["outbox_event_id"], ["outbox_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_reliability_coaching_attempts"),
        sa.UniqueConstraint("outbox_event_id", name="uq_reliability_coaching_attempts_outbox_event_id"),
    )
    op.create_index(
        "ix_reliability_coaching_attempts_case_id_attempt_no",
        "reliability_coaching_attempts",
        ["coaching_case_id", "attempt_no"],
        unique=False,
    )
    op.create_index(
        "ix_reliability_coaching_attempts_provider_conversation_id",
        "reliability_coaching_attempts",
        ["provider_conversation_id"],
        unique=False,
    )

    op.create_table(
        "reliability_coaching_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("coaching_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outcome_code", sa.String(length=64), nullable=False),
        sa.Column("barrier_code", sa.String(length=64), nullable=True),
        sa.Column("availability_update_requested", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("manager_followup_requested", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("coaching_acknowledged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("opt_out", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["coaching_case_id"], ["reliability_coaching_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attempt_id"], ["reliability_coaching_attempts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_reliability_coaching_outcomes"),
        sa.UniqueConstraint("attempt_id", name="uq_reliability_coaching_outcomes_attempt_id"),
    )
    op.create_index(
        "ix_reliability_coaching_outcomes_case_id_recorded_at",
        "reliability_coaching_outcomes",
        ["coaching_case_id", "recorded_at"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index("ix_reliability_coaching_outcomes_case_id_recorded_at", table_name="reliability_coaching_outcomes")
    op.drop_table("reliability_coaching_outcomes")

    op.drop_index("ix_reliability_coaching_attempts_provider_conversation_id", table_name="reliability_coaching_attempts")
    op.drop_index("ix_reliability_coaching_attempts_case_id_attempt_no", table_name="reliability_coaching_attempts")
    op.drop_table("reliability_coaching_attempts")

    op.drop_index("ix_reliability_coaching_triggers_case_id_occurred_at", table_name="reliability_coaching_triggers")
    op.drop_table("reliability_coaching_triggers")

    op.drop_index("uq_reliability_coaching_cases_active_employee", table_name="reliability_coaching_cases")
    op.drop_index("ix_reliability_coaching_cases_status_created_at", table_name="reliability_coaching_cases")
    op.drop_index("ix_reliability_coaching_cases_business_employee_created_at", table_name="reliability_coaching_cases")
    op.drop_table("reliability_coaching_cases")

    channel_enum.drop(bind, checkfirst=True)
    attempt_status_enum.drop(bind, checkfirst=True)
    delivery_status_enum.drop(bind, checkfirst=True)
    case_status_enum.drop(bind, checkfirst=True)
