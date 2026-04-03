from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from app.schemas.common import BaseSchema


class AuditLogRead(BaseSchema):
    id: UUID
    business_id: Optional[UUID]
    location_id: Optional[UUID]
    actor_type: str
    actor_user_id: Optional[UUID]
    actor_membership_id: Optional[UUID]
    event_name: str
    target_type: str
    target_id: Optional[UUID]
    ip_address: Optional[str]
    user_agent: Optional[str]
    payload: dict
    occurred_at: datetime
