from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.common import ComplianceOverrideArtifactStatus, ComplianceOverrideArtifactType


class ComplianceOverrideArtifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compliance_override_artifacts"
    __table_args__ = (
        Index(
            "ix_compliance_override_artifacts_shift_employee_status",
            "shift_id",
            "employee_id",
            "status",
        ),
        Index(
            "ix_compliance_override_artifacts_employee_rule_code",
            "employee_id",
            "rule_code",
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    shift_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shifts.id", ondelete="CASCADE"),
        nullable=False,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    assignment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("shift_assignments.id", ondelete="SET NULL")
    )
    labor_rule_profile_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("labor_rule_profile_versions.id", ondelete="SET NULL")
    )
    approved_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    rule_code: Mapped[str] = mapped_column(String(120), nullable=False)
    artifact_type: Mapped[ComplianceOverrideArtifactType] = mapped_column(
        Enum(ComplianceOverrideArtifactType, name="compliance_override_artifact_type"),
        nullable=False,
        server_default=ComplianceOverrideArtifactType.written_consent.value,
    )
    status: Mapped[ComplianceOverrideArtifactStatus] = mapped_column(
        Enum(ComplianceOverrideArtifactStatus, name="compliance_override_artifact_status"),
        nullable=False,
        server_default=ComplianceOverrideArtifactStatus.approved.value,
    )
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_payload_hash: Mapped[Optional[str]] = mapped_column(String(255))
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    note: Mapped[Optional[str]] = mapped_column(Text)
    reason_codes: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        default=list,
    )
    artifact_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    business: Mapped["Business"] = relationship()
    location: Mapped["Location"] = relationship()
    shift: Mapped["Shift"] = relationship()
    employee: Mapped["Employee"] = relationship()
    assignment: Mapped[Optional["ShiftAssignment"]] = relationship()
    labor_rule_profile_version: Mapped[Optional["LaborRuleProfileVersion"]] = relationship()
    approved_by_user: Mapped[Optional["User"]] = relationship()


class CompliancePolicyVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compliance_policy_versions"
    __table_args__ = (
        Index(
            "ix_compliance_policy_versions_business_scope_effective",
            "business_id",
            "policy_scope",
            "effective_at",
        ),
        Index(
            "ix_compliance_policy_versions_location_effective",
            "location_id",
            "effective_at",
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"),
    )
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    replaces_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("compliance_policy_versions.id", ondelete="SET NULL")
    )
    policy_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    settings_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    superseded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    note: Mapped[Optional[str]] = mapped_column(Text)

    business: Mapped["Business"] = relationship()
    location: Mapped[Optional["Location"]] = relationship()
    created_by_user: Mapped[Optional["User"]] = relationship()
    replaces_version: Mapped[Optional["CompliancePolicyVersion"]] = relationship(
        remote_side="CompliancePolicyVersion.id"
    )


from app.models.business import Business, Location  # noqa: E402
from app.models.identity import User  # noqa: E402
from app.models.labor_rules import LaborRuleProfileVersion  # noqa: E402
from app.models.scheduling import Shift, ShiftAssignment  # noqa: E402
from app.models.workforce import Employee  # noqa: E402
