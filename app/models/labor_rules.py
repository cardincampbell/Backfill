from __future__ import annotations

from datetime import date, datetime
import uuid
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LaborIndustryProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "labor_industry_profiles"
    __table_args__ = (
        UniqueConstraint("code", name="uq_labor_industry_profiles_code"),
        Index(
            "ix_labor_industry_profiles_jurisdiction_active",
            "jurisdiction_code",
            "is_active",
        ),
    )

    code: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    jurisdiction_code: Mapped[Optional[str]] = mapped_column(String(24))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )


class LaborRuleProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "labor_rule_profiles"
    __table_args__ = (
        UniqueConstraint("code", name="uq_labor_rule_profiles_code"),
        Index(
            "ix_labor_rule_profiles_jurisdiction_active",
            "jurisdiction_code",
            "is_active",
        ),
    )

    code: Mapped[str] = mapped_column(String(120), nullable=False)
    jurisdiction_code: Mapped[str] = mapped_column(String(24), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    overtime_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    daily_ot_threshold_hours: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))
    weekly_ot_threshold_hours: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))
    double_time_threshold_hours: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))
    consecutive_hours_threshold_hours: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))
    industry_profile_code: Mapped[Optional[str]] = mapped_column(
        String(120),
        ForeignKey("labor_industry_profiles.code", ondelete="SET NULL"),
    )
    rules_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    effective_start_date: Mapped[Optional[date]] = mapped_column(Date)
    effective_end_date: Mapped[Optional[date]] = mapped_column(Date)
    source_urls: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        default=list,
    )
    source_version: Mapped[Optional[str]] = mapped_column(String(255))
    source_hash: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    industry_profile: Mapped[Optional["LaborIndustryProfile"]] = relationship()
    versions: Mapped[list["LaborRuleProfileVersion"]] = relationship(
        back_populates="labor_rule_profile",
        cascade="all, delete-orphan",
    )


class LaborRuleProfileVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "labor_rule_profile_versions"
    __table_args__ = (
        UniqueConstraint(
            "labor_rule_profile_id",
            "version_no",
            name="uq_labor_rule_profile_versions_profile_id_version_no",
        ),
        Index(
            "ix_labor_rule_profile_versions_profile_id_version_no",
            "labor_rule_profile_id",
            "version_no",
        ),
        UniqueConstraint("payload_hash", name="uq_labor_rule_profile_versions_payload_hash"),
    )

    labor_rule_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("labor_rule_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    payload_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    change_summary: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(120))

    labor_rule_profile: Mapped["LaborRuleProfile"] = relationship(back_populates="versions")


class LaborRuleSourceDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "labor_rule_source_documents"
    __table_args__ = (
        Index(
            "ix_labor_rule_source_documents_jurisdiction_active",
            "jurisdiction_code",
            "is_active",
        ),
    )

    jurisdiction_code: Mapped[str] = mapped_column(String(24), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    http_etag: Mapped[Optional[str]] = mapped_column(String(255))
    http_last_modified: Mapped[Optional[str]] = mapped_column(String(255))
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    normalized_text: Mapped[Optional[str]] = mapped_column(Text)
    content_hash: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class LaborRuleUpdateProposal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "labor_rule_update_proposals"
    __table_args__ = (
        Index(
            "ix_labor_rule_update_proposals_jurisdiction_status",
            "jurisdiction_code",
            "proposal_status",
        ),
    )

    jurisdiction_code: Mapped[str] = mapped_column(String(24), nullable=False)
    proposal_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    proposal_type: Mapped[str] = mapped_column(String(64), nullable=False, server_default="profile_update")
    current_profile_codes: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        default=list,
    )
    proposed_profiles_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    reason_summary: Mapped[Optional[str]] = mapped_column(Text)
    citations_json: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        default=list,
    )
    llm_provider: Mapped[Optional[str]] = mapped_column(String(64))
    llm_model: Mapped[Optional[str]] = mapped_column(String(255))
    llm_generation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("llm_generations.id", ondelete="SET NULL")
    )
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(120))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class LocationLaborRuleResolution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "location_labor_rule_resolutions"
    __table_args__ = (
        UniqueConstraint("location_id", name="uq_location_labor_rule_resolutions_location_id"),
        Index(
            "ix_location_labor_rule_resolutions_jurisdiction_source",
            "jurisdiction_code",
            "resolution_source",
        ),
    )

    location_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    jurisdiction_code: Mapped[str] = mapped_column(String(24), nullable=False)
    resolved_profile_code: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("labor_rule_profiles.code", ondelete="RESTRICT"),
        nullable=False,
    )
    resolved_profile_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("labor_rule_profile_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    resolved_profile_payload_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    resolution_source: Mapped[str] = mapped_column(String(32), nullable=False)
    resolution_confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    manual_override_profile_code: Mapped[Optional[str]] = mapped_column(
        String(120),
        ForeignKey("labor_rule_profiles.code", ondelete="SET NULL"),
    )
    resolution_context_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    llm_generation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("llm_generations.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class LaborRuleResolutionRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "labor_rule_resolution_runs"
    __table_args__ = (
        Index(
            "ix_labor_rule_resolution_runs_location_id_created_at",
            "location_id",
            "created_at",
        ),
    )

    location_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    jurisdiction_code: Mapped[str] = mapped_column(String(24), nullable=False)
    candidate_profile_codes: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        default=list,
    )
    selected_profile_code: Mapped[Optional[str]] = mapped_column(
        String(120),
        ForeignKey("labor_rule_profiles.code", ondelete="SET NULL"),
    )
    selected_profile_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("labor_rule_profile_versions.id", ondelete="SET NULL")
    )
    selected_profile_payload_hash: Mapped[Optional[str]] = mapped_column(String(255))
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    reason_codes: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        default=list,
    )
    input_snapshot_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    llm_generation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("llm_generations.id", ondelete="SET NULL")
    )


from app.models.ai import LlmGeneration  # noqa: E402,F401
from app.models.business import Location  # noqa: E402,F401
