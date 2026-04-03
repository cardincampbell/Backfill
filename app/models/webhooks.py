from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.common import WebhookDeliveryStatus, WebhookSubscriptionStatus


class WebhookSubscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "webhook_subscriptions"
    __table_args__ = (
        Index("ix_webhook_subscriptions_business_id_status", "business_id", "status"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    endpoint_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[WebhookSubscriptionStatus] = mapped_column(
        Enum(WebhookSubscriptionStatus, name="webhook_subscription_status"),
        nullable=False,
        server_default=WebhookSubscriptionStatus.active.value,
    )
    subscribed_events: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    signing_secret: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_hint: Mapped[str] = mapped_column(String(32), nullable=False)
    last_delivery_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    subscription_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    deliveries: Mapped[list["WebhookDelivery"]] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
    )


class WebhookDelivery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        UniqueConstraint("subscription_id", "audit_log_id", name="uq_webhook_deliveries_subscription_id_audit_log_id"),
        Index("ix_webhook_deliveries_subscription_id_created_at", "subscription_id", "created_at"),
        Index("ix_webhook_deliveries_status_next_attempt_at", "status", "next_attempt_at"),
    )

    subscription_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"), nullable=False)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    audit_log_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("audit_logs.id", ondelete="SET NULL"))
    outbox_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("outbox_events.id", ondelete="SET NULL"))
    event_name: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[Optional[uuid.UUID]] = mapped_column()
    endpoint_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    status: Mapped[WebhookDeliveryStatus] = mapped_column(
        Enum(WebhookDeliveryStatus, name="webhook_delivery_status"),
        nullable=False,
        server_default=WebhookDeliveryStatus.pending.value,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_attempted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    response_status_code: Mapped[Optional[int]] = mapped_column(Integer)
    response_body_preview: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    request_headers: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    signature_header: Mapped[Optional[str]] = mapped_column(String(255))

    subscription: Mapped["WebhookSubscription"] = relationship(back_populates="deliveries")


from app.models.business import Business  # noqa: E402,F401
from app.models.coverage import AuditLog, OutboxEvent  # noqa: E402,F401
from app.models.identity import User  # noqa: E402,F401
