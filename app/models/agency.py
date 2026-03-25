from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class AgencyRequestStatus(str, Enum):
    sent = "sent"
    acknowledged = "acknowledged"
    declined = "declined"
    candidate_pending = "candidate_pending"
    filled = "filled"
    expired = "expired"


class AgencyPartner(BaseModel):
    id: Optional[int] = None
    name: str
    coverage_areas: list[str] = Field(default_factory=list)
    roles_supported: list[str] = Field(default_factory=list)
    certifications_supported: list[str] = Field(default_factory=list)
    contact_channel: str = "email"   # "email" | "sms" | "api" | "portal"
    contact_info: Optional[str] = None
    avg_response_time_minutes: Optional[int] = None
    acceptance_rate: Optional[float] = None
    fill_rate: Optional[float] = None
    billing_model: str = "referral_fee"  # "referral_fee" | "restaurant_fee" | "both"
    sla_tier: str = "standard"           # "standard" | "priority"
    active: bool = True

    model_config = ConfigDict(from_attributes=True)


class AgencyRequest(BaseModel):
    id: Optional[int] = None
    shift_id: int
    cascade_id: int
    agency_partner_id: int
    status: AgencyRequestStatus = AgencyRequestStatus.sent
    request_timestamp: Optional[datetime] = None
    response_deadline: Optional[datetime] = None
    confirmed_worker_name: Optional[str] = None
    confirmed_worker_eta: Optional[str] = None
    agency_reference_id: Optional[str] = None
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
