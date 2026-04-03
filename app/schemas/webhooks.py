from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


class WebhookSubscriptionCreate(BaseSchema):
    endpoint_url: str
    description: Optional[str] = None
    subscribed_events: list[str] = Field(default_factory=list)


class WebhookSubscriptionUpdate(BaseSchema):
    endpoint_url: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    subscribed_events: Optional[list[str]] = None


class WebhookSubscriptionRead(BaseSchema):
    id: UUID
    business_id: UUID
    created_by_user_id: Optional[UUID]
    endpoint_url: str
    description: Optional[str]
    status: str
    subscribed_events: list[str]
    secret_hint: str
    last_delivery_at: Optional[datetime]
    failure_count: int
    subscription_metadata: dict
    created_at: datetime
    updated_at: datetime


class WebhookSubscriptionCreateResponse(BaseSchema):
    subscription: WebhookSubscriptionRead
    signing_secret: str


class WebhookSecretRotateResponse(BaseSchema):
    subscription: WebhookSubscriptionRead
    signing_secret: str


class WebhookDeliveryRead(BaseSchema):
    id: UUID
    subscription_id: UUID
    business_id: UUID
    audit_log_id: Optional[UUID]
    outbox_event_id: Optional[UUID]
    event_name: str
    target_type: str
    target_id: Optional[UUID]
    endpoint_url: str
    status: str
    attempt_count: int
    next_attempt_at: Optional[datetime]
    last_attempted_at: Optional[datetime]
    delivered_at: Optional[datetime]
    response_status_code: Optional[int]
    response_body_preview: Optional[str]
    error_message: Optional[str]
    request_payload: dict
    request_headers: dict
    signature_header: Optional[str]
    created_at: datetime
    updated_at: datetime


class WebhookEventCatalogResponse(BaseSchema):
    events: list[str] = Field(default_factory=list)
