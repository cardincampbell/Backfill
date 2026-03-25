from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict


class CascadeStatus(str, Enum):
    active = "active"
    completed = "completed"
    exhausted = "exhausted"


class OutreachChannel(str, Enum):
    sms = "sms"
    voice = "voice"


class OutreachStatus(str, Enum):
    pending = "pending"
    sent = "sent"
    delivered = "delivered"
    responded = "responded"
    timed_out = "timed_out"


class OutreachOutcome(str, Enum):
    accepted = "accepted"
    declined = "declined"
    no_response = "no_response"
    negotiating = "negotiating"


class Cascade(BaseModel):
    id: int
    shift_id: int
    status: CascadeStatus = CascadeStatus.active
    current_tier: int = 1
    current_position: int = 0
    manager_approved_tier3: bool = False

    model_config = ConfigDict(from_attributes=True)


class OutreachAttempt(BaseModel):
    id: Optional[int] = None
    cascade_id: int
    worker_id: int
    tier: int
    channel: OutreachChannel = OutreachChannel.sms
    status: OutreachStatus = OutreachStatus.pending
    outcome: Optional[OutreachOutcome] = None
    sent_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
    conversation_summary: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
