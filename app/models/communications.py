from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CommunicationSuppression(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "communication_suppressions"
    __table_args__ = (
        Index(
            "uq_communication_suppressions_active_destination",
            "channel",
            "destination",
            "scope",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "ix_communication_suppressions_destination",
            "channel",
            "destination",
        ),
        Index(
            "ix_communication_suppressions_revoked_at",
            "revoked_at",
        ),
    )

    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    destination: Mapped[str] = mapped_column(String(320), nullable=False)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, server_default="global")
    source: Mapped[Optional[str]] = mapped_column(String(64))
    reason_code: Mapped[Optional[str]] = mapped_column(String(64))
    suppressed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    suppression_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
