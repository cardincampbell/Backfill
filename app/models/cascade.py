from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class CascadeStatus(str, Enum):
    active = "active"
    completed = "completed"
    exhausted = "exhausted"


class OutreachMode(str, Enum):
    broadcast = "broadcast"
    cascade = "cascade"


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
    confirmed = "confirmed"
    standby = "standby"
    declined = "declined"
    no_response = "no_response"
    promoted = "promoted"
    standby_expired = "standby_expired"


class Cascade(BaseModel):
    id: int
    shift_id: int
    status: CascadeStatus = CascadeStatus.active
    outreach_mode: OutreachMode = OutreachMode.cascade
    current_tier: int = 1
    current_batch: int = 0
    current_position: int = 0
    confirmed_worker_id: Optional[int] = None
    standby_queue: list[int] = Field(default_factory=list)
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
    standby_position: Optional[int] = None
    promoted_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
    conversation_summary: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
