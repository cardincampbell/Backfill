from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import BaseSchema


class AttendanceHistoryFactPayload(BaseSchema):
    business_id: UUID
    location_id: UUID | None = None
    role_id: UUID | None = None
    shift_id: UUID | None = None
    employee_id: UUID | None = None
    source_system: str = "backfill_native"
    source_assignment_id: str | None = None
    starts_at: datetime
    ends_at: datetime
    scheduled_hours: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    worked_hours: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    attendance_status: str
    late_minutes: int | None = Field(default=None, ge=0)
    left_early_minutes: int | None = Field(default=None, ge=0)
    source_payload: dict = Field(default_factory=dict)
    dedupe_key: str | None = None

    @model_validator(mode="after")
    def validate_window(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("attendance_history_window_invalid")
        return self


class CalloutHistoryFactPayload(BaseSchema):
    business_id: UUID
    location_id: UUID | None = None
    role_id: UUID | None = None
    shift_id: UUID | None = None
    source_system: str = "backfill_native"
    source_case_id: str | None = None
    occurred_at: datetime
    shift_starts_at: datetime | None = None
    shift_ends_at: datetime | None = None
    notice_minutes: int | None = Field(default=None, ge=0)
    reason_code: str | None = None
    filled: bool = False
    fill_latency_minutes: int | None = Field(default=None, ge=0)
    source_payload: dict = Field(default_factory=dict)
    dedupe_key: str | None = None

    @model_validator(mode="after")
    def validate_window(self):
        if self.shift_starts_at is not None and self.shift_ends_at is not None and self.shift_ends_at <= self.shift_starts_at:
            raise ValueError("callout_history_window_invalid")
        return self
