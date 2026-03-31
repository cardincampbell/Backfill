from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class AuditAction(str, Enum):
    vacancy_created = "vacancy_created"
    outreach_sent = "outreach_sent"
    outreach_response = "outreach_response"
    shift_filled = "shift_filled"
    shift_unfilled = "shift_unfilled"
    cascade_started = "cascade_started"
    cascade_exhausted = "cascade_exhausted"
    tier_escalated = "tier_escalated"
    consent_granted = "consent_granted"
    consent_revoked = "consent_revoked"
    opt_out_received = "opt_out_received"
    agency_request_sent = "agency_request_sent"
    agency_request_confirmed = "agency_request_confirmed"
    agency_request_declined = "agency_request_declined"
    manager_notified = "manager_notified"
    worker_created = "worker_created"
    location_created = "location_created"
    location_deleted = "location_deleted"
    location_manager_invited = "location_manager_invited"
    location_manager_revoked = "location_manager_revoked"
    auth_verification_requested = "auth_verification_requested"
    auth_verification_succeeded = "auth_verification_succeeded"
    auth_verification_failed = "auth_verification_failed"
    auth_step_up_requested = "auth_step_up_requested"
    auth_step_up_succeeded = "auth_step_up_succeeded"
    auth_step_up_failed = "auth_step_up_failed"
    auth_session_revoked = "auth_session_revoked"
    caller_lookup = "caller_lookup"
    import_job_created = "import_job_created"
    import_job_committed = "import_job_committed"
    schedule_created = "schedule_created"
    schedule_template_created = "schedule_template_created"
    schedule_template_applied = "schedule_template_applied"
    schedule_template_updated = "schedule_template_updated"
    schedule_template_deleted = "schedule_template_deleted"
    schedule_published = "schedule_published"
    schedule_delivery_sent = "schedule_delivery_sent"
    schedule_delivery_failed = "schedule_delivery_failed"
    schedule_amended = "schedule_amended"
    schedule_recalled = "schedule_recalled"
    schedule_archived = "schedule_archived"
    shift_assignment_updated = "shift_assignment_updated"
    shift_deleted = "shift_deleted"
    shift_updated = "shift_updated"
    open_shift_offer_cancelled = "open_shift_offer_cancelled"
    open_shift_closed = "open_shift_closed"
    open_shift_reopened = "open_shift_reopened"
    shift_confirmation_requested = "shift_confirmation_requested"
    shift_confirmation_received = "shift_confirmation_received"
    shift_confirmation_escalated = "shift_confirmation_escalated"
    shift_check_in_requested = "shift_check_in_requested"
    shift_check_in_received = "shift_check_in_received"
    shift_check_in_escalated = "shift_check_in_escalated"
    shift_attendance_actioned = "shift_attendance_actioned"
    worker_deactivated = "worker_deactivated"
    worker_reactivated = "worker_reactivated"
    worker_transferred = "worker_transferred"
    worker_invited = "worker_invited"


class AuditLog(BaseModel):
    id: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    actor: str = Field(description="'system' | worker_id | manager_id | agency_id")
    action: AuditAction
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    details: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)
