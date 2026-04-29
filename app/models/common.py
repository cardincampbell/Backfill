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


class ShiftLifecycleStatus(str, Enum):
    draft = "draft"
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class ShiftStaffingStatus(str, Enum):
    open = "open"
    filling = "filling"
    covered = "covered"
    no_fill = "no_fill"


class ShiftStatus(str, Enum):
    draft = "draft"
    scheduled = "scheduled"
    open = "open"
    filling = "filling"
    covered = "covered"
    no_fill = "no_fill"
    cancelled = "cancelled"
    completed = "completed"


class ShiftSegmentType(str, Enum):
    work = "work"


class ShiftBreakType(str, Enum):
    meal = "meal"
    rest = "rest"
    other = "other"


class AssignmentStatus(str, Enum):
    proposed = "proposed"
    assigned = "assigned"
    accepted = "accepted"
    declined = "declined"
    cancelled = "cancelled"
    replaced = "replaced"
    no_show = "no_show"
    completed = "completed"


class ComplianceOverrideArtifactType(str, Enum):
    written_consent = "written_consent"
    meal_waiver = "meal_waiver"
    manager_override = "manager_override"


class ComplianceOverrideArtifactStatus(str, Enum):
    approved = "approved"
    revoked = "revoked"
    expired = "expired"


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


class ScheduleRunType(str, Enum):
    draft_generate = "draft_generate"
    replay = "replay"
    shadow_compare = "shadow_compare"
    publish_candidate = "publish_candidate"


class ScheduleRunStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ScheduleApplyStatus(str, Enum):
    queued = "queued"
    applied = "applied"
    stale_rejected = "stale_rejected"
    failed = "failed"
    no_op = "no_op"


class ReliabilityCoachingCaseStatus(str, Enum):
    open = "open"
    suppressed = "suppressed"
    escalated = "escalated"
    closed = "closed"


class ReliabilityCoachingDeliveryStatus(str, Enum):
    pending = "pending"
    queued = "queued"
    in_flight = "in_flight"
    delivered = "delivered"
    cooldown_blocked = "cooldown_blocked"
    exhausted = "exhausted"


class ReliabilityCoachingAttemptStatus(str, Enum):
    queued = "queued"
    in_flight = "in_flight"
    completed = "completed"
    no_answer = "no_answer"
    failed = "failed"
    cancelled = "cancelled"


class LaborForecastRunStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class DemandFeatureSnapshotStatus(str, Enum):
    building = "building"
    completed = "completed"
    failed = "failed"


class BucketAlignmentMode(str, Enum):
    local_operating_time = "local_operating_time"


class DstHandlingMode(str, Enum):
    skip_missing_repeat_distinct = "skip_missing_repeat_distinct"


_STAFFING_TO_COMPATIBILITY_SHIFT_STATUS = {
    ShiftStaffingStatus.open: ShiftStatus.open,
    ShiftStaffingStatus.filling: ShiftStatus.filling,
    ShiftStaffingStatus.covered: ShiftStatus.covered,
    ShiftStaffingStatus.no_fill: ShiftStatus.no_fill,
}


def compatibility_shift_status(
    lifecycle_status: ShiftLifecycleStatus | str,
    staffing_status: ShiftStaffingStatus | str,
) -> ShiftStatus:
    lifecycle = (
        lifecycle_status
        if isinstance(lifecycle_status, ShiftLifecycleStatus)
        else ShiftLifecycleStatus(str(lifecycle_status))
    )
    staffing = (
        staffing_status
        if isinstance(staffing_status, ShiftStaffingStatus)
        else ShiftStaffingStatus(str(staffing_status))
    )

    if lifecycle == ShiftLifecycleStatus.draft:
        return ShiftStatus.draft
    if lifecycle == ShiftLifecycleStatus.cancelled:
        return ShiftStatus.cancelled
    if lifecycle == ShiftLifecycleStatus.completed:
        return ShiftStatus.completed
    return _STAFFING_TO_COMPATIBILITY_SHIFT_STATUS[staffing]


def shift_axes_from_compatibility_status(
    status: ShiftStatus | str,
) -> tuple[ShiftLifecycleStatus, ShiftStaffingStatus]:
    normalized = status if isinstance(status, ShiftStatus) else ShiftStatus(str(status))
    if normalized == ShiftStatus.draft:
        return ShiftLifecycleStatus.draft, ShiftStaffingStatus.open
    if normalized == ShiftStatus.scheduled:
        return ShiftLifecycleStatus.scheduled, ShiftStaffingStatus.open
    if normalized == ShiftStatus.open:
        return ShiftLifecycleStatus.scheduled, ShiftStaffingStatus.open
    if normalized == ShiftStatus.filling:
        return ShiftLifecycleStatus.scheduled, ShiftStaffingStatus.filling
    if normalized == ShiftStatus.covered:
        return ShiftLifecycleStatus.scheduled, ShiftStaffingStatus.covered
    if normalized == ShiftStatus.no_fill:
        return ShiftLifecycleStatus.scheduled, ShiftStaffingStatus.no_fill
    if normalized == ShiftStatus.cancelled:
        return ShiftLifecycleStatus.cancelled, ShiftStaffingStatus.open
    return ShiftLifecycleStatus.completed, ShiftStaffingStatus.covered
