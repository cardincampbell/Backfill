from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class ConsentStatus(str, Enum):
    granted = "granted"
    revoked = "revoked"
    pending = "pending"


class WorkerType(str, Enum):
    internal = "internal"
    alumni = "alumni"


class WorkerSource(str, Enum):
    scheduling_sync = "scheduling_sync"
    inbound_call = "inbound_call"
    csv_import = "csv_import"
    agency_fill = "agency_fill"


class WorkerCreate(BaseModel):
    name: str
    phone: str = Field(description="E.164 format, e.g. +15551234567")
    email: Optional[str] = None
    source_id: Optional[str] = None
    worker_type: WorkerType = WorkerType.internal
    preferred_channel: str = Field(default="sms", description="'sms' | 'voice' | 'both'")
    roles: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    priority_rank: int = Field(default=1, ge=1, description="Lower = higher priority")
    restaurant_id: Optional[int] = None
    restaurant_assignments: list[dict] = Field(default_factory=list)
    restaurants_worked: list[int] = Field(default_factory=list)
    source: WorkerSource = WorkerSource.csv_import

    # Consent — collected and logged from day one (TCPA / FCC 2024)
    sms_consent_status: ConsentStatus = ConsentStatus.pending
    voice_consent_status: ConsentStatus = ConsentStatus.pending
    consent_text_version: Optional[str] = None
    consent_timestamp: Optional[datetime] = None
    consent_channel: Optional[str] = Field(
        None,
        description="'inbound_call' | 'inbound_sms' | 'web' | 'csv_import'",
    )
    opt_out_timestamp: Optional[datetime] = None
    opt_out_channel: Optional[str] = Field(
        None,
        description="'sms_reply' | 'voice' | 'web' | 'manual'",
    )


class Worker(WorkerCreate):
    id: int

    # Behavioral scores (populated over time)
    response_rate: Optional[float] = None
    acceptance_rate: Optional[float] = None
    show_up_rate: Optional[float] = None
    rating: Optional[float] = None
    total_shifts_filled: int = 0

    model_config = ConfigDict(from_attributes=True)
