from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from app_v2.schemas.common import BaseSchema


class LocationSettingsRead(BaseSchema):
    location_id: UUID
    coverage_requires_manager_approval: bool = False
    late_arrival_policy: Literal["wait", "manager_action", "start_coverage"] = "wait"
    missed_check_in_policy: Literal["manager_action", "start_coverage"] = "manager_action"
    agency_supply_approved: bool = False
    writeback_enabled: bool = False
    timezone: Optional[str] = None
    scheduling_platform: Optional[str] = "backfill_native"
    integration_status: Optional[str] = None
    backfill_shifts_enabled: bool = False
    backfill_shifts_launch_state: str = "off"
    backfill_shifts_beta_eligible: bool = False


class LocationSettingsUpdate(BaseSchema):
    coverage_requires_manager_approval: bool | None = None
    late_arrival_policy: Literal["wait", "manager_action", "start_coverage"] | None = None
    missed_check_in_policy: Literal["manager_action", "start_coverage"] | None = None
    agency_supply_approved: bool | None = None
    writeback_enabled: bool | None = None
    timezone: str | None = None
    scheduling_platform: str | None = None
    integration_status: str | None = None
    backfill_shifts_enabled: bool | None = None
    backfill_shifts_launch_state: str | None = None
    backfill_shifts_beta_eligible: bool | None = None
