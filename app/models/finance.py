from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CostLedgerEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cost_ledger_entries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_cost_ledger_entries_idempotency_key"),
        Index("ix_cost_ledger_entries_business_id_occurred_at", "business_id", "occurred_at"),
        Index("ix_cost_ledger_entries_location_id_occurred_at", "location_id", "occurred_at"),
        Index("ix_cost_ledger_entries_case_id_occurred_at", "coverage_case_id", "occurred_at"),
        Index("ix_cost_ledger_entries_provider_product_occurred_at", "provider", "product", "occurred_at"),
        Index("ix_cost_ledger_entries_reference_type_reference_id", "reference_type", "reference_id"),
    )

    business_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("businesses.id", ondelete="SET NULL"))
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
    coverage_case_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("coverage_cases.id", ondelete="SET NULL"))
    shift_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("shifts.id", ondelete="SET NULL"))
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    product: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(80), nullable=False)
    reference_id: Mapped[Optional[str]] = mapped_column(String(255))
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255))
    quantity: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False, server_default=text("1"))
    unit_cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cost_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
