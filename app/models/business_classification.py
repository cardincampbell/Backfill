from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BusinessDerivationRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "business_derivation_runs"
    __table_args__ = (
        Index("ix_business_derivation_runs_business_id_created_at", "business_id", "created_at"),
        Index("ix_business_derivation_runs_business_id_applied", "business_id", "applied"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    llm_generation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("llm_generations.id", ondelete="SET NULL")
    )
    mode: Mapped[str] = mapped_column(String(32), nullable=False, server_default="shadow")
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False, server_default="classify")
    provider: Mapped[Optional[str]] = mapped_column(String(64))
    model: Mapped[Optional[str]] = mapped_column(String(255))
    vertical_code: Mapped[str] = mapped_column(String(80), nullable=False)
    subvertical_code: Mapped[Optional[str]] = mapped_column(String(120))
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    fallback_reason: Mapped[Optional[str]] = mapped_column(Text)
    evidence_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    reason_codes: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        default=list,
    )
    baseline_role_codes: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        default=list,
    )
    selected_role_codes: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        default=list,
    )
    applied_role_codes: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        default=list,
    )
    run_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    gap_suggestions: Mapped[list["BusinessDerivationGapSuggestion"]] = relationship(
        back_populates="derivation_run",
        cascade="all, delete-orphan",
    )


class BusinessDerivationGapSuggestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "business_derivation_gap_suggestions"
    __table_args__ = (
        Index(
            "ix_business_derivation_gap_suggestions_business_id_status",
            "business_id",
            "status",
        ),
        Index(
            "ix_business_derivation_gap_suggestions_run_id",
            "derivation_run_id",
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    derivation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business_derivation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    suggestion_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    vertical_code: Mapped[Optional[str]] = mapped_column(String(80))
    subvertical_code: Mapped[Optional[str]] = mapped_column(String(120))
    proposed_code: Mapped[Optional[str]] = mapped_column(String(120))
    proposed_display_name: Mapped[Optional[str]] = mapped_column(String(255))
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    reason: Mapped[Optional[str]] = mapped_column(Text)
    suggestion_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    derivation_run: Mapped["BusinessDerivationRun"] = relationship(back_populates="gap_suggestions")
