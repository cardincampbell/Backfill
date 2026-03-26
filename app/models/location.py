from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SchedulingPlatform(str, Enum):
    seven_shifts = "7shifts"
    deputy = "deputy"
    when_i_work = "wheniwork"
    homebase = "homebase"
    backfill_native = "backfill_native"


class BusinessVertical(str, Enum):
    restaurant = "restaurant"
    healthcare = "healthcare"
    warehouse = "warehouse"
    retail = "retail"
    hospitality = "hospitality"
    other = "other"


class LocationCreate(BaseModel):
    name: str
    vertical: BusinessVertical = BusinessVertical.restaurant
    address: Optional[str] = None
    manager_name: Optional[str] = None
    manager_phone: Optional[str] = Field(None, description="E.164 format")
    manager_email: Optional[str] = None
    scheduling_platform: SchedulingPlatform = Field(
        default=SchedulingPlatform.backfill_native,
        description="'7shifts' | 'deputy' | 'wheniwork' | 'homebase' | 'backfill_native'",
    )
    scheduling_platform_id: Optional[str] = None
    integration_status: Optional[str] = None
    last_roster_sync_at: Optional[str] = None
    last_roster_sync_status: Optional[str] = None
    last_schedule_sync_at: Optional[str] = None
    last_schedule_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    integration_state: Optional[str] = None
    last_event_sync_at: Optional[str] = None
    last_rolling_sync_at: Optional[str] = None
    last_daily_sync_at: Optional[str] = None
    last_writeback_at: Optional[str] = None
    writeback_enabled: bool = False
    writeback_subscription_tier: str = "core"
    onboarding_info: Optional[str] = Field(
        None, description="Site notes, arrival instructions, dress code, who to report to, etc."
    )
    agency_supply_approved: bool = False
    preferred_agency_partners: list[int] = Field(default_factory=list)


class Location(LocationCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "BusinessVertical",
    "SchedulingPlatform",
    "LocationCreate",
    "Location",
]
