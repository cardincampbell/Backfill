from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class SchedulingPlatform(str, Enum):
    seven_shifts = "7shifts"
    deputy = "deputy"
    when_i_work = "wheniwork"
    homebase = "homebase"
    backfill_native = "backfill_native"


class RestaurantCreate(BaseModel):
    name: str
    address: Optional[str] = None
    manager_name: Optional[str] = None
    manager_phone: Optional[str] = Field(None, description="E.164 format")
    manager_email: Optional[str] = None
    scheduling_platform: SchedulingPlatform = Field(
        default=SchedulingPlatform.backfill_native,
        description="'7shifts' | 'deputy' | 'wheniwork' | 'homebase' | 'backfill_native'",
    )
    scheduling_platform_id: Optional[str] = None
    onboarding_info: Optional[str] = Field(
        None, description="Parking, dress code, who to report to, etc."
    )
    agency_supply_approved: bool = False
    preferred_agency_partners: list[int] = Field(default_factory=list)


class Restaurant(RestaurantCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)
