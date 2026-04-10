from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from app.schemas.common import BaseSchema


class PlatformEventRead(BaseSchema):
    id: UUID
    business_id: Optional[UUID]
    location_id: Optional[UUID]
    schema_version: int
    event_type: str
    compatibility_event_name: Optional[str]
    entity_type: str
    entity_id: Optional[UUID]
    actor_type: str
    actor_user_id: Optional[UUID]
    actor_membership_id: Optional[UUID]
    trace_id: str
    ip_address: Optional[str]
    user_agent: Optional[str]
    payload: dict
    event_metadata: dict
    error_message: Optional[str]
    occurred_at: datetime
