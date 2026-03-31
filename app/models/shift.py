from __future__ import annotations

from datetime import date, time
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class ShiftStatus(str, Enum):
    scheduled = "scheduled"
    vacant = "vacant"
    filling = "filling"
    filled = "filled"
    unfilled = "unfilled"


class FillTier(str, Enum):
    tier1_internal = "tier1_internal"
    tier2_alumni = "tier2_alumni"
    tier3_agency = "tier3_agency"


class SourcePlatform(str, Enum):
    seven_shifts = "7shifts"
    deputy = "deputy"
    when_i_work = "wheniwork"
    homebase = "homebase"
    backfill_native = "backfill_native"
    inbound_call = "inbound_call"


class ShiftCreate(BaseModel):
    location_id: Optional[int] = None
    schedule_id: Optional[int] = None
    scheduling_platform_id: Optional[str] = None
    role: str
    date: date
    start_time: time
    end_time: time
    pay_rate: float = Field(gt=0, description="Hourly pay rate in USD")
    requirements: list[str] = Field(default_factory=list)
    status: ShiftStatus = ShiftStatus.scheduled
    source_platform: SourcePlatform = SourcePlatform.backfill_native
    shift_label: Optional[str] = None
    notes: Optional[str] = None
    published_state: Optional[str] = None
    spans_midnight: bool = False


class Shift(ShiftCreate):
    id: int
    called_out_by: Optional[int] = Field(None, description="worker_id of the worker who called out")
    filled_by: Optional[int] = Field(None, description="worker_id of the worker who filled it")
    fill_tier: Optional[FillTier] = None
    escalated_from_worker_id: Optional[int] = None
    reminder_sent_at: Optional[str] = None
    confirmation_requested_at: Optional[str] = None
    worker_confirmed_at: Optional[str] = None
    worker_declined_at: Optional[str] = None
    confirmation_escalated_at: Optional[str] = None
    check_in_requested_at: Optional[str] = None
    checked_in_at: Optional[str] = None
    late_reported_at: Optional[str] = None
    late_eta_minutes: Optional[int] = None
    check_in_escalated_at: Optional[str] = None
    attendance_action_state: Optional[str] = None
    attendance_action_updated_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
