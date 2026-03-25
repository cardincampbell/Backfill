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
    restaurant_id: Optional[int] = None
    scheduling_platform_id: Optional[str] = None
    role: str
    date: date
    start_time: time
    end_time: time
    pay_rate: float = Field(gt=0, description="Hourly pay rate in USD")
    requirements: list[str] = Field(default_factory=list)
    status: ShiftStatus = ShiftStatus.scheduled
    source_platform: SourcePlatform = SourcePlatform.backfill_native


class Shift(ShiftCreate):
    id: int
    called_out_by: Optional[int] = Field(None, description="worker_id of the worker who called out")
    filled_by: Optional[int] = Field(None, description="worker_id of the worker who filled it")
    fill_tier: Optional[FillTier] = None

    model_config = ConfigDict(from_attributes=True)
