from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LlmGeneration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "llm_generations"
    __table_args__ = (
        Index("ix_llm_generations_business_id_started_at", "business_id", "started_at"),
        Index("ix_llm_generations_location_id_started_at", "location_id", "started_at"),
        Index("ix_llm_generations_provider_model_started_at", "provider", "model", "started_at"),
        Index("ix_llm_generations_trace_id", "trace_id"),
    )

    business_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("businesses.id", ondelete="SET NULL"))
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False, server_default="general")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(120))
    trace_id: Mapped[Optional[str]] = mapped_column(String(64))
    provider_generation_id: Mapped[Optional[str]] = mapped_column(String(255))
    finish_reason: Mapped[Optional[str]] = mapped_column(String(64))
    output_text: Mapped[Optional[str]] = mapped_column(Text)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    estimated_cost_micros: Mapped[Optional[int]] = mapped_column(BigInteger)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    request_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    response_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    tool_calls: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        default=list,
    )
    generation_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
