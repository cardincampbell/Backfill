from __future__ import annotations

from enum import Enum
from typing import Any, Optional

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
    organization_id: Optional[int] = None
    organization_name: Optional[str] = None
    vertical: BusinessVertical = BusinessVertical.restaurant
    address: Optional[str] = None
    place_inferred_vertical: Optional[BusinessVertical] = None
    place_provider: Optional[str] = None
    place_id: Optional[str] = None
    place_resource_name: Optional[str] = None
    place_display_name: Optional[str] = None
    place_brand_name: Optional[str] = None
    place_location_label: Optional[str] = None
    place_formatted_address: Optional[str] = None
    place_primary_type: Optional[str] = None
    place_primary_type_display_name: Optional[str] = None
    place_business_status: Optional[str] = None
    place_latitude: Optional[float] = None
    place_longitude: Optional[float] = None
    place_google_maps_uri: Optional[str] = None
    place_website_uri: Optional[str] = None
    place_national_phone_number: Optional[str] = None
    place_international_phone_number: Optional[str] = None
    place_utc_offset_minutes: Optional[int] = None
    place_rating: Optional[float] = None
    place_user_rating_count: Optional[int] = None
    place_city: Optional[str] = None
    place_state_region: Optional[str] = None
    place_postal_code: Optional[str] = None
    place_country_code: Optional[str] = None
    place_neighborhood: Optional[str] = None
    place_sublocality: Optional[str] = None
    place_types: list[str] = Field(default_factory=list)
    place_address_components: list[dict[str, Any]] = Field(default_factory=list)
    place_regular_opening_hours: dict[str, Any] = Field(default_factory=dict)
    place_plus_code: dict[str, Any] = Field(default_factory=dict)
    place_metadata: dict[str, Any] = Field(default_factory=dict)
    employee_count: Optional[int] = Field(default=None, ge=1)
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
    last_manager_digest_sent_at: Optional[str] = None
    writeback_enabled: bool = False
    writeback_subscription_tier: str = "core"
    backfill_shifts_enabled: bool = True
    backfill_shifts_launch_state: str = Field(
        default="enabled",
        description="'disabled' | 'pilot' | 'enabled'",
    )
    backfill_shifts_beta_eligible: bool = False
    coverage_requires_manager_approval: bool = False
    late_arrival_policy: str = Field(
        default="wait",
        description="'wait' | 'manager_action' | 'start_coverage'",
    )
    missed_check_in_policy: str = Field(
        default="start_coverage",
        description="'manager_action' | 'start_coverage'",
    )
    timezone: Optional[str] = None
    operating_mode: Optional[str] = Field(
        default=None,
        description="'integration' | 'backfill_shifts'",
    )
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
