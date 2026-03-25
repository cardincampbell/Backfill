from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class AuditAction(str, Enum):
    vacancy_created = "vacancy_created"
    outreach_sent = "outreach_sent"
    outreach_response = "outreach_response"
    shift_filled = "shift_filled"
    shift_unfilled = "shift_unfilled"
    cascade_started = "cascade_started"
    cascade_exhausted = "cascade_exhausted"
    tier_escalated = "tier_escalated"
    consent_granted = "consent_granted"
    consent_revoked = "consent_revoked"
    opt_out_received = "opt_out_received"
    agency_request_sent = "agency_request_sent"
    agency_request_confirmed = "agency_request_confirmed"
    agency_request_declined = "agency_request_declined"
    manager_notified = "manager_notified"
    worker_created = "worker_created"
    restaurant_created = "restaurant_created"
    caller_lookup = "caller_lookup"


class AuditLog(BaseModel):
    id: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    actor: str = Field(description="'system' | worker_id | manager_id | agency_id")
    action: AuditAction
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    details: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)
