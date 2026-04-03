from __future__ import annotations

from enum import Enum


class MembershipRole(str, Enum):
    owner = "owner"
    admin = "admin"
    manager = "manager"
    viewer = "viewer"


class MembershipStatus(str, Enum):
    pending = "pending"
    active = "active"
    suspended = "suspended"
    revoked = "revoked"


class InviteStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    expired = "expired"
    revoked = "revoked"


class ChallengeChannel(str, Enum):
    sms = "sms"


class ChallengePurpose(str, Enum):
    sign_in = "sign_in"
    sign_up = "sign_up"
    invite_acceptance = "invite_acceptance"
    step_up_billing = "step_up_billing"
    step_up_export = "step_up_export"
    step_up_phone_change = "step_up_phone_change"


class ChallengeStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    expired = "expired"
    cancelled = "cancelled"
    failed = "failed"


class SessionRiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class EmployeeStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    archived = "archived"


class ShiftStatus(str, Enum):
    draft = "draft"
    scheduled = "scheduled"
    open = "open"
    filling = "filling"
    covered = "covered"
    no_fill = "no_fill"
    cancelled = "cancelled"
    completed = "completed"


class AssignmentStatus(str, Enum):
    proposed = "proposed"
    assigned = "assigned"
    accepted = "accepted"
    declined = "declined"
    cancelled = "cancelled"
    replaced = "replaced"
    no_show = "no_show"
    completed = "completed"


class CoverageCaseStatus(str, Enum):
    queued = "queued"
    running = "running"
    filled = "filled"
    exhausted = "exhausted"
    cancelled = "cancelled"
    failed = "failed"


class CoverageRunStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class CoverageOperatingMode(str, Enum):
    standard_queue = "standard_queue"
    compressed_queue = "compressed_queue"
    blast = "blast"


class CandidateSource(str, Enum):
    phase_1 = "phase_1"
    phase_2 = "phase_2"
    manager_override = "manager_override"


class CoverageAttemptStatus(str, Enum):
    pending = "pending"
    delivered = "delivered"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"
    cancelled = "cancelled"
    failed = "failed"


class OfferStatus(str, Enum):
    pending = "pending"
    delivered = "delivered"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"
    cancelled = "cancelled"
    failed = "failed"


class OfferResponseChannel(str, Enum):
    sms = "sms"
    voice = "voice"
    web = "web"


class OutboxChannel(str, Enum):
    sms = "sms"
    email = "email"
    voice = "voice"
    webhook = "webhook"


class OutboxStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    sent = "sent"
    failed = "failed"
    cancelled = "cancelled"


class AuditActorType(str, Enum):
    system = "system"
    user = "user"
    service = "service"


class WebhookSubscriptionStatus(str, Enum):
    active = "active"
    paused = "paused"


class WebhookDeliveryStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class SchedulerProvider(str, Enum):
    backfill_native = "backfill_native"
    seven_shifts = "7shifts"
    deputy = "deputy"
    when_i_work = "wheniwork"
    homebase = "homebase"


class SchedulerConnectionStatus(str, Enum):
    pending = "pending"
    active = "active"
    degraded = "degraded"
    disabled = "disabled"


class SchedulerSyncEventStatus(str, Enum):
    received = "received"
    queued = "queued"
    processed = "processed"
    retrying = "retrying"
    failed = "failed"


class SchedulerSyncJobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class SchedulerSyncRunStatus(str, Enum):
    completed = "completed"
    retrying = "retrying"
    failed = "failed"


class RetellConversationType(str, Enum):
    call = "call"
    chat = "chat"
