from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from html import escape
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.business import Business, Location, LocationRole, Role
from app.models.compliance import ComplianceOverrideArtifact
from app.models.common import (
    AuditActorType,
    AssignmentStatus,
    ComplianceOverrideArtifactStatus,
    ComplianceOverrideArtifactType,
    CoverageAttemptStatus,
    CoverageCaseStatus,
    CoverageRunStatus,
    EmployeeStatus,
    OfferStatus,
    OutboxChannel,
    OutboxStatus,
    ShiftLifecycleStatus,
    ShiftStaffingStatus,
)
from app.models.coverage import CoverageCase, CoverageContactAttempt, CoverageOffer, OutboxEvent
from app.models.scheduling import Shift, ShiftAssignment, ShiftBreak, ShiftSegment
from app.models.workforce import Employee, EmployeeLocation, EmployeeRole
from app.schemas.compliance import ShiftComplianceOverrideCreate
from app.schemas.scheduling import (
    PublishedShiftAmendmentRead,
    PublishedShiftAmendmentWrite,
    ScheduleWeekPublishRead,
    ScheduleWeekPublishWrite,
    ShiftAssignmentMutationResponse,
    ShiftAssignmentRead,
    ShiftAssignmentWrite,
    ShiftBreakWrite,
    ShiftCreate,
    ShiftSegmentWrite,
    ShiftUpdate,
)
from app.services import (
    compliance_decisions,
    compliance_engine,
    compliance_source_references,
    compliance_overrides,
    communication_suppressions,
    delivery,
    employee_schedule_links as employee_schedule_link_service,
    forecast_history,
    labor_rules,
    settings as settings_service,
    shift_assignments,
    worker_runtime,
    workforce,
)
from app.services.schedule_weeks import effective_week_start_day, schedule_week_window

_ACTIVE_CASE_STATUSES = {CoverageCaseStatus.queued, CoverageCaseStatus.running}
_ACTIVE_OFFER_STATUSES = {OfferStatus.pending, OfferStatus.delivered}
_ACTIVE_RUN_STATUSES = {CoverageRunStatus.queued, CoverageRunStatus.running}
_USABLE_LOCATION_ACCESS_LEVELS = {"approved", "trusted"}
_LIVE_SHIFT_LIFECYCLE_STATUSES = {
    ShiftLifecycleStatus.scheduled,
    ShiftLifecycleStatus.in_progress,
}
_PUBLISHED_AMENDMENT_METADATA_KEY = "published_amendment"
_SHIFT_HISTORICAL_ARTIFACTS_KEY = "historical_artifacts"


class ShiftAssignmentConflictError(Exception):
    def __init__(self, current_assignment: ShiftAssignment | None):
        super().__init__("stale_assignment_conflict")
        self.current_assignment = current_assignment


class ScheduleWeekPublishConflictError(Exception):
    def __init__(
        self,
        *,
        week_start_date: date,
        publishable_shift_ids: list[UUID],
        draft_shift_count: int,
        already_scheduled_shift_count: int,
    ):
        super().__init__("stale_publish_conflict")
        self.week_start_date = week_start_date
        self.publishable_shift_ids = publishable_shift_ids
        self.draft_shift_count = draft_shift_count
        self.already_scheduled_shift_count = already_scheduled_shift_count


class ScheduleWeekPublishComplianceError(Exception):
    def __init__(
        self,
        *,
        summary: dict[str, object],
        review_items: list[dict[str, object]],
    ):
        super().__init__("publish_compliance_blocked")
        self.summary = summary
        self.review_items = review_items


class ScheduleWeekPublishFuturePolicyConflictError(Exception):
    def __init__(
        self,
        *,
        summary: dict[str, object],
        policy_reviews: list[dict[str, object]],
    ):
        super().__init__("publish_future_policy_conflict")
        self.summary = summary
        self.policy_reviews = policy_reviews


class ShiftAssignmentComplianceError(Exception):
    def __init__(
        self,
        *,
        summary: dict[str, object],
        review_items: list[dict[str, object]],
    ):
        super().__init__("assignment_compliance_blocked")
        self.code = "assignment_compliance_blocked"
        self.summary = summary
        self.review_items = review_items


class PublishedShiftAmendmentComplianceError(Exception):
    def __init__(
        self,
        *,
        summary: dict[str, object],
        review_items: list[dict[str, object]],
    ):
        super().__init__("published_amendment_compliance_blocked")
        self.code = "published_amendment_compliance_blocked"
        self.summary = summary
        self.review_items = review_items


@dataclass
class ShiftAssignmentMutationResult:
    shift: Shift
    action: str
    source: str
    previous_assignment: ShiftAssignment | None
    current_assignment: ShiftAssignment | None
    cancelled_cases: list[CoverageCase]
    cancelled_offers: list[CoverageOffer]
    no_op: bool = False


@dataclass
class ScheduleWeekPublishResult:
    business_id: UUID
    location_id: UUID
    week_start_date: date
    week_end_date: date
    published_shifts: list[Shift]
    already_scheduled_shifts: list[Shift]
    notification_enqueued_assignment_count: int
    notification_enqueued_employee_count: int
    compliance_summary: dict[str, object] = field(default_factory=dict)
    compliance_review_items: list[dict[str, object]] = field(default_factory=list)


@dataclass
class ScheduleWeekPublishContext:
    business: Business
    location: Location
    week_start_date: date
    week_end_date: date
    shifts: list[Shift]
    draft_shifts: list[Shift]
    already_scheduled_shifts: list[Shift]
    current_publishable_shift_ids: list[UUID]


@dataclass
class PublishedShiftAmendmentResult:
    shift: Shift
    action: str
    reason_code: str
    source: str
    previous_assignment: ShiftAssignment | None
    current_assignment: ShiftAssignment | None
    cancelled_cases: list[CoverageCase]
    cancelled_offers: list[CoverageOffer]
    week_start_date: date
    week_end_date: date


async def _sync_assignment_history_facts(
    session: AsyncSession,
    *,
    shift: Shift,
    assignments: list[ShiftAssignment | None],
) -> None:
    for assignment in assignments:
        if assignment is None:
            continue
        await forecast_history.sync_attendance_history_fact_for_assignment(
            session,
            shift=shift,
            assignment=assignment,
        )


def _assignment_employee_name(assignment: ShiftAssignment | None) -> str | None:
    if assignment is None:
        return None
    metadata = getattr(assignment, "assignment_metadata", None) or {}
    if isinstance(metadata, dict):
        raw_name = metadata.get("employee_name")
        if isinstance(raw_name, str):
            name = raw_name.strip()
            if name:
                return name
    employee = getattr(assignment, "__dict__", {}).get("employee")
    if employee is not None:
        raw_name = getattr(employee, "full_name", None)
        if isinstance(raw_name, str):
            name = raw_name.strip()
            if name:
                return name
    raw_name = getattr(assignment, "employee_name", None)
    if isinstance(raw_name, str):
        name = raw_name.strip()
        if name:
            return name
    return None


def _assignment_read(assignment: ShiftAssignment | None) -> ShiftAssignmentRead | None:
    if assignment is None:
        return None
    return ShiftAssignmentRead(
        assignment_id=assignment.id,
        employee_id=assignment.employee_id,
        employee_name=_assignment_employee_name(assignment),
        status=assignment.status.value if hasattr(assignment.status, "value") else str(assignment.status),
        assigned_via=assignment.assigned_via,
        accepted_at=assignment.accepted_at,
    )


def build_shift_assignment_response(
    result: ShiftAssignmentMutationResult,
) -> ShiftAssignmentMutationResponse:
    return ShiftAssignmentMutationResponse(
        shift_id=result.shift.id,
        lifecycle_status=(
            result.shift.lifecycle_status.value
            if hasattr(result.shift.lifecycle_status, "value")
            else str(result.shift.lifecycle_status)
        ),
        staffing_status=(
            result.shift.staffing_status.value
            if hasattr(result.shift.staffing_status, "value")
            else str(result.shift.staffing_status)
        ),
        status=result.shift.status.value if hasattr(result.shift.status, "value") else str(result.shift.status),
        current_assignment=_assignment_read(result.current_assignment),
    )


def build_schedule_week_publish_response(
    result: ScheduleWeekPublishResult,
) -> ScheduleWeekPublishRead:
    return ScheduleWeekPublishRead(
        business_id=result.business_id,
        location_id=result.location_id,
        week_start_date=result.week_start_date,
        week_end_date=result.week_end_date,
        publish_mode="draft_only_net_new",
        published_shift_count=len(result.published_shifts),
        already_scheduled_shift_count=len(result.already_scheduled_shifts),
        notification_enqueued_assignment_count=result.notification_enqueued_assignment_count,
        notification_enqueued_employee_count=result.notification_enqueued_employee_count,
        published_shift_ids=[shift.id for shift in result.published_shifts],
        already_scheduled_shift_ids=[shift.id for shift in result.already_scheduled_shifts],
        compliance_summary=result.compliance_summary,
        compliance_review_items=result.compliance_review_items,
    )


def _build_compliance_review_item(
    *,
    assignment_id: UUID | None,
    shift_id: UUID,
    employee_id: UUID,
    evaluation: Mapping[str, object],
) -> dict[str, object]:
    issues = _schedule_week_publish_review_issues(evaluation)
    return {
        "assignment_id": assignment_id,
        "shift_id": shift_id,
        "employee_id": employee_id,
        "status": str(evaluation.get("status") or "").strip().lower() or "clear",
        "blocking_rule_codes": sorted(
            {
                str(rule_code or "").strip()
                for rule_code in evaluation.get("blocking_rule_codes") or []
                if str(rule_code or "").strip()
            }
        ),
        "warning_rule_codes": sorted(
            {
                str(rule_code or "").strip()
                for rule_code in evaluation.get("warning_rule_codes") or []
                if str(rule_code or "").strip()
            }
        ),
        "premium_total_cents": _publish_review_int_setting(
            evaluation.get("premium_total_cents"),
            default=0,
            minimum=0,
        ),
        "unresolved_premium_rule_codes": sorted(
            {
                str(rule_code or "").strip()
                for rule_code in evaluation.get("unresolved_premium_rule_codes") or []
                if str(rule_code or "").strip()
            }
        ),
        "override_applied": bool(evaluation.get("override_applied")),
        "override_artifact_id": str(evaluation.get("override_artifact_id") or "").strip() or None,
        "override_eligible_artifact_types": sorted(
            {
                str(issue.get("artifact_type_allowed") or "").strip()
                for issue in issues
                if str(issue.get("artifact_type_allowed") or "").strip()
                and not bool(issue.get("override_applied"))
            }
        ),
        "policy_version_id": evaluation.get("policy_version_id"),
        "policy_hash": str(evaluation.get("policy_hash") or "").strip() or None,
        "policy_effective_at": evaluation.get("policy_effective_at"),
        "policy_scope": str(evaluation.get("policy_scope") or "").strip() or None,
        "issues": issues,
    }


def _summarize_compliance_review_items(
    review_items: list[dict[str, object]],
) -> dict[str, object]:
    summary: dict[str, object] = {
        "selected_assignment_count": len(review_items),
        "clear_assignment_count": 0,
        "warning_assignment_count": 0,
        "blocked_assignment_count": 0,
        "override_applied_count": 0,
        "override_eligible_warning_count": 0,
        "premium_total_cents": 0,
        "unresolved_premium_rule_count": 0,
        "unresolved_premium_rule_codes": [],
        "warning_rule_codes": [],
        "override_eligible_artifact_types": [],
        "warning_shift_ids": [],
        "blocked_shift_ids": [],
        "override_eligible_shift_ids": [],
    }
    warning_rule_codes: set[str] = set()
    unresolved_premium_rule_codes: set[str] = set()
    override_eligible_artifact_types: set[str] = set()
    warning_shift_ids: set[str] = set()
    blocked_shift_ids: set[str] = set()
    override_eligible_shift_ids: set[str] = set()
    override_artifact_ids: set[str] = set()

    for raw_item in review_items:
        item = _publish_review_mapping(raw_item)
        if not item:
            continue
        shift_key = str(item.get("shift_id") or "").strip()
        status = str(item.get("status") or "").strip().lower() or "clear"
        if status == "block":
            summary["blocked_assignment_count"] += 1
            if shift_key:
                blocked_shift_ids.add(shift_key)
        elif status == "warning":
            summary["warning_assignment_count"] += 1
            if shift_key:
                warning_shift_ids.add(shift_key)
        else:
            summary["clear_assignment_count"] += 1

        summary["premium_total_cents"] += _publish_review_int_setting(
            item.get("premium_total_cents"),
            default=0,
            minimum=0,
        )

        for rule_code in item.get("warning_rule_codes") or []:
            normalized = str(rule_code or "").strip()
            if normalized:
                warning_rule_codes.add(normalized)
        for rule_code in item.get("unresolved_premium_rule_codes") or []:
            normalized = str(rule_code or "").strip()
            if normalized:
                unresolved_premium_rule_codes.add(normalized)

        override_artifact_id = str(item.get("override_artifact_id") or "").strip()
        if bool(item.get("override_applied")) and override_artifact_id:
            override_artifact_ids.add(override_artifact_id)

        for issue in item.get("issues") or []:
            issue_payload = _publish_review_mapping(issue)
            if not issue_payload:
                continue
            artifact_type = str(issue_payload.get("artifact_type_allowed") or "").strip()
            if not artifact_type or bool(issue_payload.get("override_applied")):
                continue
            override_eligible_artifact_types.add(artifact_type)
            if shift_key:
                override_eligible_shift_ids.add(shift_key)
            summary["override_eligible_warning_count"] += 1

    summary["override_applied_count"] = len(override_artifact_ids)
    summary["unresolved_premium_rule_count"] = len(unresolved_premium_rule_codes)
    summary["unresolved_premium_rule_codes"] = sorted(unresolved_premium_rule_codes)
    summary["warning_rule_codes"] = sorted(warning_rule_codes)
    summary["override_eligible_artifact_types"] = sorted(override_eligible_artifact_types)
    summary["warning_shift_ids"] = sorted(warning_shift_ids)
    summary["blocked_shift_ids"] = sorted(blocked_shift_ids)
    summary["override_eligible_shift_ids"] = sorted(override_eligible_shift_ids)
    return summary


def _single_assignment_compliance_review(
    *,
    assignment_id: UUID | None,
    shift: Shift,
    employee: Employee,
    evaluation: Mapping[str, object],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    review_item = _build_compliance_review_item(
        assignment_id=assignment_id,
        shift_id=shift.id,
        employee_id=employee.id,
        evaluation=evaluation,
    )
    review_items = [review_item]
    summary = _summarize_compliance_review_items(review_items)
    return summary, review_items


async def schedule_week_publish_compliance_review(
    session: AsyncSession,
    *,
    shifts: list[Shift],
    reference_time: datetime,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    summary: dict[str, object] = {
        "selected_assignment_count": 0,
        "clear_assignment_count": 0,
        "warning_assignment_count": 0,
        "blocked_assignment_count": 0,
        "override_applied_count": 0,
        "override_eligible_warning_count": 0,
        "premium_total_cents": 0,
        "unresolved_premium_rule_count": 0,
        "unresolved_premium_rule_codes": [],
        "warning_rule_codes": [],
        "override_eligible_artifact_types": [],
        "warning_shift_ids": [],
        "blocked_shift_ids": [],
        "override_eligible_shift_ids": [],
    }
    review_items: list[dict[str, object]] = []
    warning_rule_codes: set[str] = set()
    unresolved_premium_rule_codes: set[str] = set()
    override_eligible_artifact_types: set[str] = set()
    warning_shift_ids: set[str] = set()
    blocked_shift_ids: set[str] = set()
    override_eligible_shift_ids: set[str] = set()
    override_artifact_ids: set[str] = set()

    for shift in shifts:
        current_assignment = shift_assignments.current_assignment(shift.assignments or [])
        if current_assignment is None or current_assignment.employee_id is None:
            continue
        employee = current_assignment.employee
        if employee is None:
            employee = await session.get(Employee, current_assignment.employee_id)
        if employee is None:
            continue

        _base_evaluation, evaluation, _override_artifact = await _resolve_assignment_compliance(
            session,
            shift=shift,
            employee=employee,
            reference_time=reference_time,
        )
        review_item = _build_compliance_review_item(
            assignment_id=current_assignment.id,
            shift_id=shift.id,
            employee_id=employee.id,
            evaluation=evaluation,
        )
        review_items.append(review_item)

        status = str(review_item.get("status") or "").strip().lower() or "clear"
        shift_key = str(shift.id)
        summary["selected_assignment_count"] += 1
        if status == "block":
            summary["blocked_assignment_count"] += 1
            blocked_shift_ids.add(shift_key)
        elif status == "warning":
            summary["warning_assignment_count"] += 1
            warning_shift_ids.add(shift_key)
        elif status == "clear":
            summary["clear_assignment_count"] += 1

        summary["premium_total_cents"] += _publish_review_int_setting(
            review_item.get("premium_total_cents"),
            default=0,
            minimum=0,
        )

        for rule_code in review_item.get("warning_rule_codes") or []:
            normalized = str(rule_code or "").strip()
            if normalized:
                warning_rule_codes.add(normalized)
        for rule_code in review_item.get("unresolved_premium_rule_codes") or []:
            normalized = str(rule_code or "").strip()
            if normalized:
                unresolved_premium_rule_codes.add(normalized)

        override_artifact_id = str(review_item.get("override_artifact_id") or "").strip()
        if bool(review_item.get("override_applied")) and override_artifact_id:
            override_artifact_ids.add(override_artifact_id)

        for issue in review_item.get("issues") or []:
            issue_payload = _publish_review_mapping(issue)
            if not issue_payload:
                continue
            artifact_type = str(issue_payload.get("artifact_type_allowed") or "").strip()
            if not artifact_type or bool(issue_payload.get("override_applied")):
                continue
            override_eligible_artifact_types.add(artifact_type)
            override_eligible_shift_ids.add(shift_key)
            summary["override_eligible_warning_count"] += 1

    review_items.sort(
        key=lambda item: (
            _schedule_week_publish_status_rank(str(item.get("status") or "")),
            str(item.get("shift_id") or ""),
            str(item.get("employee_id") or ""),
        )
    )
    summary["override_applied_count"] = len(override_artifact_ids)
    summary["unresolved_premium_rule_count"] = len(unresolved_premium_rule_codes)
    summary["unresolved_premium_rule_codes"] = sorted(unresolved_premium_rule_codes)
    summary["warning_rule_codes"] = sorted(warning_rule_codes)
    summary["override_eligible_artifact_types"] = sorted(override_eligible_artifact_types)
    summary["warning_shift_ids"] = sorted(warning_shift_ids)
    summary["blocked_shift_ids"] = sorted(blocked_shift_ids)
    summary["override_eligible_shift_ids"] = sorted(override_eligible_shift_ids)
    return summary, review_items


def _future_policy_effective_at(value: object) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value
        return value.replace(tzinfo=timezone.utc)
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is not None:
        return parsed
    return parsed.replace(tzinfo=timezone.utc)


def _review_item_has_publish_signal(review_item: Mapping[str, object]) -> bool:
    status = str(review_item.get("status") or "").strip().lower()
    if status in {"block", "warning", "unresolved"}:
        return True
    if _publish_review_int_setting(
        review_item.get("premium_total_cents"),
        default=0,
        minimum=0,
    ) > 0:
        return True
    if review_item.get("unresolved_premium_rule_codes"):
        return True
    if review_item.get("issues"):
        return True
    return False


async def schedule_week_publish_future_policy_review(
    session: AsyncSession,
    *,
    shifts: list[Shift],
    publish_reference_time: datetime,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    policy_reviews_by_key: dict[
        tuple[str, str, str, str],
        dict[str, object],
    ] = {}

    for shift in shifts:
        current_assignment = shift_assignments.current_assignment(shift.assignments or [])
        if current_assignment is None or current_assignment.employee_id is None:
            continue
        employee = current_assignment.employee
        if employee is None:
            employee = await session.get(Employee, current_assignment.employee_id)
        if employee is None:
            continue

        evaluation_reference_time = shift.starts_at
        _base_evaluation, evaluation, _override_artifact = await _resolve_assignment_compliance(
            session,
            shift=shift,
            employee=employee,
            reference_time=evaluation_reference_time,
        )
        policy_effective_at = _future_policy_effective_at(evaluation.get("policy_effective_at"))
        if policy_effective_at is None or policy_effective_at <= publish_reference_time:
            continue

        review_item = _build_compliance_review_item(
            assignment_id=current_assignment.id,
            shift_id=shift.id,
            employee_id=employee.id,
            evaluation=evaluation,
        )
        if not _review_item_has_publish_signal(review_item):
            continue

        policy_version_id = str(evaluation.get("policy_version_id") or "").strip()
        policy_hash = str(evaluation.get("policy_hash") or "").strip()
        policy_scope = str(evaluation.get("policy_scope") or "").strip().lower() or "location"
        key = (
            policy_version_id,
            policy_hash,
            policy_effective_at.isoformat(),
            policy_scope,
        )
        bucket = policy_reviews_by_key.setdefault(
            key,
            {
                "policy_version_id": evaluation.get("policy_version_id"),
                "policy_hash": policy_hash or None,
                "policy_effective_at": policy_effective_at,
                "policy_scope": policy_scope,
                "review_items": [],
            },
        )
        bucket["review_items"].append(review_item)

    policy_reviews: list[dict[str, object]] = []
    flattened_review_items: list[dict[str, object]] = []
    for bucket in sorted(
        policy_reviews_by_key.values(),
        key=lambda item: (
            _future_policy_effective_at(item.get("policy_effective_at")) or publish_reference_time,
            str(item.get("policy_scope") or ""),
            str(item.get("policy_hash") or ""),
        ),
    ):
        review_items = list(bucket.get("review_items") or [])
        review_items.sort(
            key=lambda item: (
                _schedule_week_publish_status_rank(str(item.get("status") or "")),
                str(item.get("shift_id") or ""),
                str(item.get("employee_id") or ""),
            )
        )
        summary = _summarize_compliance_review_items(review_items)
        policy_reviews.append(
            {
                "policy_version_id": bucket.get("policy_version_id"),
                "policy_hash": bucket.get("policy_hash"),
                "policy_effective_at": bucket.get("policy_effective_at"),
                "policy_scope": bucket.get("policy_scope"),
                "summary": summary,
                "review_items": review_items,
            }
        )
        flattened_review_items.extend(review_items)

    summary = _summarize_compliance_review_items(flattened_review_items)
    return summary, policy_reviews


def _schedule_week_publish_review_issues(
    evaluation: Mapping[str, object],
) -> list[dict[str, object]]:
    evaluation_rule_source_references = compliance_source_references.rule_source_references_from_evaluation(
        evaluation
    )
    issues: list[dict[str, object]] = []
    for raw_result in evaluation.get("rule_results") or []:
        result = _publish_review_mapping(raw_result)
        if not result:
            continue
        status = str(result.get("status") or "").strip().lower() or "clear"
        premium_required = bool(result.get("premium_required"))
        override_artifact_id = str(result.get("override_artifact_id") or "").strip() or None
        if status == "clear" and not premium_required and override_artifact_id is None:
            continue
        premium_type = str(result.get("premium_type") or "").strip() or None
        artifact_type_allowed = str(result.get("artifact_type_allowed") or "").strip() or None
        if artifact_type_allowed is None and bool(result.get("written_consent_allowed")):
            artifact_type_allowed = ComplianceOverrideArtifactType.written_consent.value
        if (
            artifact_type_allowed is None
            and bool(result.get("waiver_possible"))
            and "meal" in str(result.get("rule_code") or "").strip().lower()
        ):
            artifact_type_allowed = ComplianceOverrideArtifactType.meal_waiver.value
        rule_code = str(result.get("rule_code") or "").strip() or "compliance_rule"
        issues.append(
            {
                "rule_code": rule_code,
                "status": status,
                "reason_codes": list(result.get("reason_codes") or []),
                "premium_required": premium_required,
                "premium_type": premium_type,
                "premium_cents": _publish_review_int_setting(
                    result.get("premium_cents"),
                    default=0,
                    minimum=0,
                ),
                "unresolved_premium": premium_type == "wage_dependent_unresolved",
                "would_block": bool(result.get("would_block")),
                "artifact_type_allowed": artifact_type_allowed,
                "override_applied": override_artifact_id is not None,
                "override_artifact_id": override_artifact_id,
                "rule_source_references": compliance_source_references.filter_rule_source_references(
                    evaluation_rule_source_references,
                    rule_codes=[rule_code],
                ),
            }
        )
    if not issues and str(evaluation.get("status") or "").strip().lower() == "unresolved":
        fallback_rule_code = "compliance_profile_unresolved"
        issues.append(
            {
                "rule_code": fallback_rule_code,
                "status": "warning",
                "reason_codes": ["labor_rule_profile_unresolved"],
                "premium_required": False,
                "premium_type": None,
                "premium_cents": 0,
                "unresolved_premium": False,
                "would_block": False,
                "artifact_type_allowed": None,
                "override_applied": False,
                "override_artifact_id": None,
                "rule_source_references": compliance_source_references.build_rule_source_references(
                    rule_codes=[fallback_rule_code],
                    profile_code=evaluation.get("profile_code"),
                    profile_display_name=evaluation.get("profile_display_name"),
                    profile_version_id=evaluation.get("profile_version_id"),
                    profile_source_version=evaluation.get("profile_source_version"),
                    profile_source_hash=evaluation.get("profile_source_hash"),
                    profile_source_urls=evaluation.get("profile_source_urls"),
                    work_permit_template_code=evaluation.get("work_permit_template_code"),
                    work_permit_template_label=evaluation.get("work_permit_template_label"),
                    work_permit_jurisdiction_code=evaluation.get("work_permit_jurisdiction_code"),
                    work_permit_source_document_title=evaluation.get(
                        "work_permit_source_document_title"
                    ),
                    work_permit_source_urls=evaluation.get("work_permit_source_urls"),
                    work_permit_source_version=evaluation.get("work_permit_source_version"),
                    work_permit_source_hash=evaluation.get("work_permit_source_hash"),
                    work_permit_payload_hash=evaluation.get("work_permit_payload_hash"),
                    policy_version_id=evaluation.get("policy_version_id"),
                    policy_hash=evaluation.get("policy_hash"),
                    policy_effective_at=evaluation.get("policy_effective_at"),
                    policy_scope=evaluation.get("policy_scope"),
                ),
            }
        )
    issues.sort(
        key=lambda issue: (
            _schedule_week_publish_status_rank(str(issue.get("status") or "")),
            str(issue.get("rule_code") or ""),
        )
    )
    return issues


def _schedule_week_publish_status_rank(status: str) -> int:
    normalized = status.strip().lower()
    return {
        "block": 0,
        "warning": 1,
        "unresolved": 2,
        "clear": 3,
    }.get(normalized, 4)


def _publish_review_mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _publish_review_int_setting(value: object, *, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return parsed if parsed >= minimum else minimum


def _compliance_metadata_for_assignment(
    evaluation: dict[str, object],
    *,
    override_artifact: ComplianceOverrideArtifact | None,
) -> dict[str, object]:
    return {
        "status": str(evaluation.get("status") or "unresolved"),
        "blocking_rule_codes": list(evaluation.get("blocking_rule_codes") or []),
        "warning_rule_codes": list(evaluation.get("warning_rule_codes") or []),
        "premium_rule_codes": list(evaluation.get("premium_rule_codes") or []),
        "premium_total_cents": _publish_review_int_setting(
            evaluation.get("premium_total_cents"),
            default=0,
            minimum=0,
        ),
        "premium_components": list(evaluation.get("premium_components") or []),
        "unresolved_premium_rule_codes": list(evaluation.get("unresolved_premium_rule_codes") or []),
        "override_applied": bool(evaluation.get("override_applied")),
        "override_artifact_id": str(override_artifact.id) if override_artifact is not None else None,
        "profile_code": evaluation.get("profile_code"),
        "profile_version_id": evaluation.get("profile_version_id"),
        "profile_payload_hash": evaluation.get("profile_payload_hash"),
        "policy_version_id": evaluation.get("policy_version_id"),
        "policy_hash": evaluation.get("policy_hash"),
        "policy_effective_at": evaluation.get("policy_effective_at"),
        "policy_scope": evaluation.get("policy_scope"),
        "rule_source_references": compliance_source_references.rule_source_references_from_evaluation(
            evaluation
        ),
    }


async def _resolve_assignment_compliance(
    session: AsyncSession,
    *,
    shift: Shift,
    employee: Employee,
    reference_time: datetime,
) -> tuple[dict[str, object], dict[str, object], ComplianceOverrideArtifact | None]:
    location = shift.location
    if location is None:
        location = await session.get(Location, shift.location_id)
    if location is None:
        raise LookupError("location_not_found")
    business = getattr(location, "business", None)
    if business is None:
        business = await session.get(Business, location.business_id)
    business_settings, location_settings = await settings_service.resolved_compliance_settings_inputs(
        session,
        business=business,
        location=location,
        as_of=reference_time,
    )
    profile = await labor_rules.runtime_resolved_profile(
        session,
        location=location,
        business=business,
        as_of=reference_time,
    )
    if profile is None:
        work_permit_context = workforce.resolve_employee_work_permit_context(
            employee,
            shift_starts_at=shift.starts_at,
            timezone_name=shift.timezone,
        )
        unresolved = compliance_engine.evaluate_shift_assignment_compliance(
            None,
            candidate_shift=shift,
            counted_intervals=(),
            reference_time=reference_time,
            employee_base_hourly_rate_cents=employee.base_hourly_rate_cents,
            employee_date_of_birth=employee.date_of_birth,
            employee_minor_school_status=employee.minor_school_status,
            employee_work_permit_number=work_permit_context.get("permit_number"),
            employee_work_permit_effective_start_on=work_permit_context.get("effective_start_on"),
            employee_work_permit_expires_on=work_permit_context.get("expires_on"),
            employee_work_permit_max_daily_minutes=work_permit_context.get("max_daily_minutes"),
            employee_work_permit_max_weekly_minutes=work_permit_context.get("max_weekly_minutes"),
            employee_work_permit_earliest_start_local_time=work_permit_context.get("earliest_start_local_time"),
            employee_work_permit_latest_end_local_time=work_permit_context.get("latest_end_local_time"),
            employee_work_permit_rule_profile=work_permit_context.get("rule_profile"),
            business_settings=business_settings,
            location_settings=location_settings,
        )
        return unresolved, unresolved, None

    snapshots = await labor_rules.build_hours_snapshots(
        session,
        employees=[employee],
        shift=shift,
        profile=profile,
        compliance_settings=settings_service.merged_compliance_settings_from_inputs(
            business_settings=business_settings,
            location_settings=location_settings,
        ),
        now=reference_time,
    )
    snapshot = snapshots.get(employee.id)
    counted_intervals = snapshot.counted_intervals if snapshot is not None else ()
    overtime_projection = labor_rules.evaluate_overtime_projection(
        profile,
        candidate_shift=shift,
        counted_intervals=counted_intervals,
        reference_time=reference_time,
    )
    work_permit_context = workforce.resolve_employee_work_permit_context(
        employee,
        shift_starts_at=shift.starts_at,
        timezone_name=shift.timezone,
    )
    base_evaluation = compliance_engine.evaluate_shift_assignment_compliance(
        profile,
        candidate_shift=shift,
        counted_intervals=counted_intervals,
        reference_time=reference_time,
        overtime_projection=overtime_projection,
        employee_base_hourly_rate_cents=employee.base_hourly_rate_cents,
        employee_date_of_birth=employee.date_of_birth,
        employee_minor_school_status=employee.minor_school_status,
        employee_work_permit_number=work_permit_context.get("permit_number"),
        employee_work_permit_effective_start_on=work_permit_context.get("effective_start_on"),
        employee_work_permit_expires_on=work_permit_context.get("expires_on"),
        employee_work_permit_max_daily_minutes=work_permit_context.get("max_daily_minutes"),
        employee_work_permit_max_weekly_minutes=work_permit_context.get("max_weekly_minutes"),
        employee_work_permit_earliest_start_local_time=work_permit_context.get("earliest_start_local_time"),
        employee_work_permit_latest_end_local_time=work_permit_context.get("latest_end_local_time"),
        employee_work_permit_rule_profile=work_permit_context.get("rule_profile"),
        business_settings=business_settings,
        location_settings=location_settings,
    )
    artifacts_by_employee = await compliance_overrides.active_artifacts_for_shift_employees(
        session,
        shift_id=shift.id,
        employee_ids=[employee.id],
        reference_time=reference_time,
    )
    override_artifact = compliance_overrides.matching_override_artifact(
        base_evaluation,
        artifacts_by_employee.get(employee.id, []),
        reference_time=reference_time,
    )
    resolved_evaluation = compliance_overrides.apply_override_artifact(base_evaluation, override_artifact)
    return base_evaluation, resolved_evaluation, override_artifact


def build_published_shift_amendment_response(
    result: PublishedShiftAmendmentResult,
) -> PublishedShiftAmendmentRead:
    return PublishedShiftAmendmentRead(
        shift_id=result.shift.id,
        action=result.action,
        reason_code=result.reason_code,
        amended_from_published=_shift_amended_from_published(result.shift),
        schedule_break=_shift_schedule_break(result.shift),
        lifecycle_status=(
            result.shift.lifecycle_status.value
            if hasattr(result.shift.lifecycle_status, "value")
            else str(result.shift.lifecycle_status)
        ),
        staffing_status=(
            result.shift.staffing_status.value
            if hasattr(result.shift.staffing_status, "value")
            else str(result.shift.staffing_status)
        ),
        status=result.shift.status.value if hasattr(result.shift.status, "value") else str(result.shift.status),
        week_publish_state="amended",
        current_assignment=_assignment_read(result.current_assignment),
    )


def _shift_amendment_metadata(shift: Shift) -> dict:
    shift_metadata = shift.shift_metadata if isinstance(shift.shift_metadata, dict) else {}
    raw = shift_metadata.get(_PUBLISHED_AMENDMENT_METADATA_KEY)
    return dict(raw) if isinstance(raw, dict) else {}


def _set_shift_amendment_metadata(shift: Shift, metadata: dict) -> None:
    shift_metadata = dict(shift.shift_metadata or {})
    shift_metadata[_PUBLISHED_AMENDMENT_METADATA_KEY] = metadata
    shift.shift_metadata = shift_metadata


def _shift_amended_from_published(shift: Shift) -> bool:
    return bool(_shift_amendment_metadata(shift).get("amended_from_published"))


def _shift_amendment_reason_code(shift: Shift) -> str | None:
    raw_reason = _shift_amendment_metadata(shift).get("reason_code")
    if isinstance(raw_reason, str) and raw_reason:
        return raw_reason
    return None


def _shift_schedule_break(shift: Shift) -> bool:
    return bool(_shift_amendment_metadata(shift).get("schedule_break"))


def _shift_amended_employee_ids(shift: Shift) -> list[UUID]:
    raw_value = _shift_amendment_metadata(shift).get("amended_employee_ids")
    if not isinstance(raw_value, list):
        return []
    employee_ids: list[UUID] = []
    for raw_id in raw_value:
        try:
            employee_ids.append(raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id)))
        except (TypeError, ValueError):
            continue
    return employee_ids


def _assignment_employee_name(assignment: ShiftAssignment | None) -> str | None:
    if assignment is None:
        return None
    try:
        employee = assignment.employee
    except Exception:
        employee = None
    if employee is not None and employee.full_name:
        return employee.full_name
    metadata = assignment.assignment_metadata or {}
    if isinstance(metadata, dict):
        raw_name = metadata.get("employee_name")
        if isinstance(raw_name, str):
            name = raw_name.strip()
            if name:
                return name
    return None


def _shift_historical_artifacts(shift: Shift) -> list[dict]:
    raw_value = _shift_amendment_metadata(shift).get(_SHIFT_HISTORICAL_ARTIFACTS_KEY)
    if not isinstance(raw_value, list):
        return []
    return [dict(entry) for entry in raw_value if isinstance(entry, dict)]


def _append_shift_historical_artifact(
    shift: Shift,
    *,
    employee_id: UUID | None,
    employee_name: str | None,
    reason_code: str,
) -> None:
    artifacts = _shift_historical_artifacts(shift)
    artifacts.append(
        {
            "artifact_id": str(uuid4()),
            "employee_id": str(employee_id) if employee_id is not None else None,
            "employee_name": employee_name,
            "reason_code": reason_code,
            "starts_at": shift.starts_at.isoformat(),
            "ends_at": shift.ends_at.isoformat(),
            "role_id": str(shift.role_id),
            "role_code": shift.role.code if shift.role is not None else None,
            "role_name": shift.role.name if shift.role is not None else None,
        }
    )
    metadata = {
        **_shift_amendment_metadata(shift),
        _SHIFT_HISTORICAL_ARTIFACTS_KEY: artifacts,
    }
    _set_shift_amendment_metadata(shift, metadata)


def _mark_shift_amended_from_published(
    shift: Shift,
    *,
    action: str,
    reason_code: str | None,
    schedule_break: bool,
    source: str,
    note: str | None,
    amended_at: datetime,
    old_employee_id: UUID | None,
    new_employee_id: UUID | None,
) -> None:
    amended_employee_ids = [
        str(employee_id)
        for employee_id in [old_employee_id, new_employee_id]
        if employee_id is not None
    ]
    metadata = {
        **_shift_amendment_metadata(shift),
        "action": action,
        "reason_code": reason_code,
        "schedule_break": schedule_break,
        "source": source,
        "note": note,
        "amended_at": amended_at.isoformat(),
        "old_employee_id": str(old_employee_id) if old_employee_id is not None else None,
        "new_employee_id": str(new_employee_id) if new_employee_id is not None else None,
        "amended_employee_ids": amended_employee_ids,
        "amended_from_published": True,
    }
    _set_shift_amendment_metadata(shift, metadata)


def _clear_shift_amended_from_published(shift: Shift) -> None:
    metadata = _shift_amendment_metadata(shift)
    if not metadata:
        return
    metadata["amended_from_published"] = False
    metadata["amended_employee_ids"] = []
    _set_shift_amendment_metadata(shift, metadata)


def _normalized_notify_channels(channels: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw_channel in channels:
        channel = str(raw_channel).strip().lower()
        if channel not in {"sms", "email"} or channel in seen:
            continue
        seen.add(channel)
        normalized.append(channel)
    return normalized


def _employee_allows_publish_notification(employee: Employee, channel: str) -> bool:
    preferences = workforce.normalized_employee_notification_preferences(employee.employee_metadata)
    if channel == "email":
        return bool(preferences["schedule_publish_email_enabled"]) and preferences["email_opted_out_at"] is None
    if channel == "sms":
        return bool(preferences["schedule_publish_sms_enabled"]) and preferences["sms_opted_out_at"] is None
    return False


async def _employee_is_globally_suppressed(
    session: AsyncSession,
    *,
    employee: Employee,
    channel: str,
) -> bool:
    destination = employee.email if channel == "email" else employee.phone_e164 if channel == "sms" else None
    return await communication_suppressions.is_destination_suppressed(
        session,
        channel=channel,
        destination=destination,
    )


def _format_shift_notification_line(shift: Shift) -> str:
    timezone_name = shift.timezone or "UTC"
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = timezone.utc
    starts_local = shift.starts_at.astimezone(tz)
    ends_local = shift.ends_at.astimezone(tz)
    role_name = getattr(getattr(shift, "role", None), "name", None) or "Shift"
    date_label = starts_local.strftime("%a %b %d").replace(" 0", " ")
    start_label = starts_local.strftime("%I:%M%p").lstrip("0")
    end_label = ends_local.strftime("%I:%M%p").lstrip("0")
    return f"{date_label} {start_label}-{end_label} · {role_name}"


def _schedule_publish_week_label(week_start_date: date, week_end_date: date) -> str:
    return (
        f"{week_start_date.strftime('%b %d').replace(' 0', ' ')}"
        f" – {week_end_date.strftime('%b %d, %Y').replace(' 0', ' ')}"
    )


def _build_schedule_publish_email_html(
    *,
    business_name: str,
    location_name: str,
    employee_name: str,
    week_label: str,
    shift_lines: list[str],
    schedule_url: str,
    note: str | None,
    unsubscribe_url: str | None = None,
) -> str:
    headline = escape(f"Your schedule for {week_label} is live")
    intro = escape(
        f"{business_name} published your schedule for {location_name} for the week of {week_label}."
    )
    summary = escape(
        f"You have {len(shift_lines)} scheduled shift{'s' if len(shift_lines) != 1 else ''}."
    )
    greeting = escape(f"Hi {employee_name},")
    schedule_url_html = escape(schedule_url)
    note_html = (
        f"""
          <tr>
            <td style="padding:18px 0 0 0;">
              <div style="padding:16px 18px;border-radius:14px;background:#EEF2FF;border:1px solid #D9E0FF;">
                <div style="font-size:12px;font-weight:700;letter-spacing:0.02em;text-transform:uppercase;color:#635BFF;padding:0 0 8px 0;">Manager note</div>
                <div style="font-size:15px;line-height:1.6;color:#334155;">{escape(note)}</div>
              </div>
            </td>
          </tr>
        """.strip()
        if note
        else ""
    )
    shift_items = "".join(
        f"""
          <tr>
            <td style="padding:0 0 10px 0;">
              <div style="padding:14px 16px;border-radius:14px;background:#F8FAFC;border:1px solid #E2E8F0;font-size:15px;line-height:1.5;color:#0A2540;">
                {escape(line)}
              </div>
            </td>
          </tr>
        """.strip()
        for line in shift_lines
    )
    unsubscribe_html = (
        f' To stop Backfill schedule emails, <a href="{escape(unsubscribe_url)}" '
        'style="color:#635BFF;text-decoration:underline;">unsubscribe</a>.'
        if unsubscribe_url
        else ""
    )
    return f"""
<div style="margin:0;padding:24px 0;background:#ffffff;font-family:Helvetica Neue,Arial,sans-serif;color:#111111;">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:640px;margin:0 auto;padding:0 16px;">
    <tr>
      <td align="left" style="padding:0 0 28px 0;font-size:32px;font-weight:800;letter-spacing:-0.04em;">Backfill</td>
      <td align="right" style="padding:0 0 28px 0;font-size:14px;font-weight:600;color:#666666;white-space:nowrap;">Callouts covered.</td>
    </tr>
    <tr>
      <td colspan="2">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#F3F5F8;border:1px solid #DFE4EA;border-radius:18px;padding:32px;">
          <tr>
            <td style="font-size:44px;line-height:1.02;font-weight:800;letter-spacing:-0.06em;padding:0 0 18px 0;">{headline}</td>
          </tr>
          <tr>
            <td style="font-size:18px;line-height:1.6;color:#3F4C5C;padding:0 0 8px 0;">{greeting}</td>
          </tr>
          <tr>
            <td style="font-size:18px;line-height:1.6;color:#3F4C5C;padding:0 0 10px 0;">{intro}</td>
          </tr>
          <tr>
            <td style="font-size:18px;line-height:1.6;color:#3F4C5C;padding:0 0 24px 0;">{summary}</td>
          </tr>
          <tr>
            <td style="padding:0 0 18px 0;">
              <a href="{schedule_url_html}" style="display:inline-block;padding:16px 30px;background:#111111;color:#ffffff;text-decoration:none;border-radius:14px;font-size:18px;font-weight:700;">View schedule</a>
            </td>
          </tr>
          <tr>
            <td style="padding:0 0 10px 0;font-size:12px;font-weight:700;letter-spacing:0.02em;text-transform:uppercase;color:#635BFF;">This week's shifts</td>
          </tr>
          {shift_items}
          {note_html}
        </table>
      </td>
    </tr>
    <tr>
      <td colspan="2" style="padding:22px 0 0 0;font-size:13px;line-height:1.55;color:#8A8A8A;">
        This secure link always shows the latest published schedule. If you believe this message was sent in error, you can ignore it.{unsubscribe_html}
      </td>
    </tr>
  </table>
</div>
""".strip()


def _schedule_publish_notification_payload(
    *,
    business_id: UUID,
    business_name: str,
    location_id: UUID,
    location_name: str,
    week_start_date: date,
    week_end_date: date,
    employee: Employee,
    shifts: list[Shift],
    note: str | None,
    schedule_url: str,
) -> dict:
    week_label = _schedule_publish_week_label(week_start_date, week_end_date)
    shift_lines = [_format_shift_notification_line(shift) for shift in shifts]
    subject = f"Your Backfill schedule for {week_label} is live"
    intro = f"Your schedule for {location_name} for the week of {week_label} is now live."
    sms_body = (
        f"Backfill: Your {location_name} schedule for {week_label} is live. "
        f"View it here: {schedule_url}"
    )
    unsubscribe_url = (
        communication_suppressions.build_email_unsubscribe_url(email=employee.email)
        if employee.email
        else None
    )
    text_body = "\n".join(
        [
            f"Hi {employee.full_name},",
            "",
            intro,
            "",
            *[f"- {line}" for line in shift_lines],
            "",
            f"View your schedule: {schedule_url}",
            *([f"Unsubscribe from Backfill emails: {unsubscribe_url}"] if unsubscribe_url else []),
            *(["", note] if note else []),
        ]
    )
    html_body = _build_schedule_publish_email_html(
        business_name=business_name,
        location_name=location_name,
        employee_name=employee.full_name,
        week_label=week_label,
        shift_lines=shift_lines,
        schedule_url=schedule_url,
        note=note,
        unsubscribe_url=unsubscribe_url,
    )
    return {
        "business_id": str(business_id),
        "business_name": business_name,
        "location_id": str(location_id),
        "employee_id": str(employee.id),
        "employee_name": employee.full_name,
        "phone_e164": employee.phone_e164,
        "email": employee.email,
        "location_name": location_name,
        "week_start_date": week_start_date.isoformat(),
        "week_end_date": week_end_date.isoformat(),
        "schedule_url": schedule_url,
        "unsubscribe_url": unsubscribe_url,
        "shift_ids": [str(shift.id) for shift in shifts],
        "shift_count": len(shifts),
        "sms_body": sms_body,
        "text_body": text_body,
        "html_body": html_body,
        "subject": subject,
        "email_headers": (
            communication_suppressions.build_email_list_unsubscribe_headers(email=employee.email)
            if employee.email
            else {}
        ),
    }


async def _enqueue_schedule_publish_notifications(
    session: AsyncSession,
    *,
    business_id: UUID,
    business_name: str,
    location_id: UUID,
    location_name: str,
    week_start_date: date,
    week_end_date: date,
    shifts: list[Shift],
    notify_channels: list[str],
    note: str | None,
    candidate_employee_ids: set[UUID] | None = None,
) -> tuple[int, int]:
    normalized_channels = _normalized_notify_channels(notify_channels)
    if not normalized_channels:
        return 0, 0

    shifts_by_employee: dict[UUID, list[Shift]] = {}
    employees_by_id: dict[UUID, Employee] = {}
    enqueued_assignment_count = 0

    for shift in shifts:
        current_assignment = shift_assignments.current_assignment(shift.assignments or [])
        employee = current_assignment.employee if current_assignment is not None else None
        if current_assignment is None or employee is None:
            continue
        available_channels: list[str] = []
        for channel in normalized_channels:
            if channel == "sms" and not employee.phone_e164:
                continue
            if channel == "email" and not employee.email:
                continue
            if not _employee_allows_publish_notification(employee, channel):
                continue
            if await _employee_is_globally_suppressed(session, employee=employee, channel=channel):
                continue
            available_channels.append(channel)
        if not available_channels:
            continue
        shifts_by_employee.setdefault(employee.id, []).append(shift)
        employees_by_id[employee.id] = employee
        enqueued_assignment_count += 1

    if candidate_employee_ids is None:
        notification_employee_ids = set(shifts_by_employee.keys())
    else:
        notification_employee_ids = set(candidate_employee_ids)

    notified_employee_count = 0

    for employee_id in sorted(notification_employee_ids, key=str):
        employee = employees_by_id.get(employee_id)
        if employee is None:
            loaded_employee = await session.get(Employee, employee_id)
            if loaded_employee is None or loaded_employee.business_id != business_id:
                continue
            employee = loaded_employee
        available_channels: list[str] = []
        for channel in normalized_channels:
            if channel == "sms" and not employee.phone_e164:
                continue
            if channel == "email" and not employee.email:
                continue
            if not _employee_allows_publish_notification(employee, channel):
                continue
            if await _employee_is_globally_suppressed(session, employee=employee, channel=channel):
                continue
            available_channels.append(channel)
        if not available_channels:
            continue
        employee_shifts = shifts_by_employee.get(employee_id, [])
        access_link, _ = await employee_schedule_link_service.get_or_create_schedule_access_link(
            session,
            business_id=business_id,
            employee=employee,
        )
        schedule_url = employee_schedule_link_service.build_employee_schedule_link(
            employee_schedule_link_service.build_employee_schedule_token(access_link),
            week_start_date=week_start_date,
            location_id=location_id,
        )
        payload = _schedule_publish_notification_payload(
            business_id=business_id,
            business_name=business_name,
            location_id=location_id,
            location_name=location_name,
            week_start_date=week_start_date,
            week_end_date=week_end_date,
            employee=employee,
            shifts=employee_shifts,
            note=note,
            schedule_url=schedule_url,
        )
        for channel in available_channels:
            session.add(
                OutboxEvent(
                    aggregate_type="schedule_publish",
                    aggregate_id=employee.id,
                    topic=delivery.SCHEDULE_PUBLISH_NOTIFICATION_TOPIC,
                    channel=OutboxChannel(channel),
                    payload=payload,
                    result_payload={},
                )
            )
        notified_employee_count += 1

    return enqueued_assignment_count, notified_employee_count


async def list_shifts(
    session: AsyncSession,
    business_id: UUID,
    *,
    location_id: UUID | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
) -> list[Shift]:
    stmt = (
        select(Shift)
        .options(selectinload(Shift.segments).selectinload(ShiftSegment.breaks))
        .where(Shift.business_id == business_id)
    )
    if location_id is not None:
        stmt = stmt.where(Shift.location_id == location_id)
    if starts_at is not None:
        stmt = stmt.where(Shift.ends_at >= starts_at)
    if ends_at is not None:
        stmt = stmt.where(Shift.starts_at <= ends_at)
    result = await session.execute(stmt.order_by(Shift.starts_at.asc()))
    return list(result.scalars().all())


async def get_shift(session: AsyncSession, business_id: UUID, shift_id: UUID) -> Shift:
    shift = await session.get(
        Shift,
        shift_id,
        options=(
            selectinload(Shift.segments).selectinload(ShiftSegment.breaks),
        ),
    )
    if shift is None or shift.business_id != business_id:
        raise LookupError("shift_not_found")
    return shift


def _serialize_shift_segments(shift: Shift) -> list[dict[str, object]]:
    serialized: list[dict[str, object]] = []
    for segment in shift.segments or []:
        serialized.append(
            {
                "segment_type": (
                    segment.segment_type.value
                    if hasattr(segment.segment_type, "value")
                    else str(segment.segment_type)
                ),
                "starts_at": segment.starts_at.isoformat(),
                "ends_at": segment.ends_at.isoformat(),
                "segment_metadata": dict(segment.segment_metadata or {}),
                "breaks": [
                    {
                        "break_type": (
                            shift_break.break_type.value
                            if hasattr(shift_break.break_type, "value")
                            else str(shift_break.break_type)
                        ),
                        "is_paid": bool(shift_break.is_paid),
                        "starts_at": shift_break.starts_at.isoformat(),
                        "ends_at": shift_break.ends_at.isoformat(),
                        "notes": shift_break.notes,
                        "break_metadata": dict(shift_break.break_metadata or {}),
                    }
                    for shift_break in (segment.breaks or [])
                ],
            }
        )
    return serialized


def _serialize_shift_segment_writes(segments: list[ShiftSegmentWrite]) -> list[dict[str, object]]:
    return [
        {
            "segment_type": segment.segment_type,
            "starts_at": segment.starts_at.isoformat(),
            "ends_at": segment.ends_at.isoformat(),
            "segment_metadata": dict(segment.segment_metadata or {}),
            "breaks": [
                {
                    "break_type": shift_break.break_type,
                    "is_paid": bool(shift_break.is_paid),
                    "starts_at": shift_break.starts_at.isoformat(),
                    "ends_at": shift_break.ends_at.isoformat(),
                    "notes": shift_break.notes,
                    "break_metadata": dict(shift_break.break_metadata or {}),
                }
                for shift_break in (segment.breaks or [])
            ],
        }
        for segment in segments
    ]


def _synchronize_shift_structure_metadata(shift: Shift) -> bool:
    current_metadata = dict(shift.shift_metadata or {})
    next_metadata = dict(current_metadata)
    serialized_segments = _serialize_shift_segments(shift)
    if serialized_segments:
        next_metadata["compliance_segments"] = serialized_segments
    else:
        next_metadata.pop("compliance_segments", None)
    if next_metadata == current_metadata:
        return False
    shift.shift_metadata = next_metadata
    return True


def _validate_shift_segments(
    *,
    shift_starts_at: datetime,
    shift_ends_at: datetime,
    segments: list[ShiftSegmentWrite],
) -> None:
    if not segments:
        return
    if segments[0].starts_at != shift_starts_at or segments[-1].ends_at != shift_ends_at:
        raise ValueError("shift_segments_must_cover_shift_bounds")

    previous_segment_end: datetime | None = None
    for segment in segments:
        if segment.ends_at <= segment.starts_at:
            raise ValueError("shift_segment_end_must_be_after_start")
        if segment.starts_at < shift_starts_at or segment.ends_at > shift_ends_at:
            raise ValueError("shift_segment_outside_shift_window")
        if previous_segment_end is not None and segment.starts_at < previous_segment_end:
            raise ValueError("shift_segments_overlap")
        previous_segment_end = segment.ends_at

        previous_break_end: datetime | None = None
        segment_duration_seconds = (segment.ends_at - segment.starts_at).total_seconds()
        total_break_seconds = 0.0
        for shift_break in segment.breaks or []:
            if shift_break.ends_at <= shift_break.starts_at:
                raise ValueError("shift_break_end_must_be_after_start")
            if shift_break.starts_at < segment.starts_at or shift_break.ends_at > segment.ends_at:
                raise ValueError("shift_break_outside_segment")
            if previous_break_end is not None and shift_break.starts_at < previous_break_end:
                raise ValueError("shift_breaks_overlap")
            previous_break_end = shift_break.ends_at
            total_break_seconds += (shift_break.ends_at - shift_break.starts_at).total_seconds()
        if total_break_seconds >= segment_duration_seconds:
            raise ValueError("shift_breaks_exceed_segment_duration")


def _replace_shift_segments(
    shift: Shift,
    segments: list[ShiftSegmentWrite],
) -> None:
    shift.segments = []
    for segment_index, segment_payload in enumerate(segments, start=1):
        segment = ShiftSegment(
            shift_id=shift.id,
            sequence_no=segment_index,
            segment_type=segment_payload.segment_type,
            starts_at=segment_payload.starts_at,
            ends_at=segment_payload.ends_at,
            segment_metadata=segment_payload.segment_metadata,
        )
        segment.breaks = []
        for break_index, break_payload in enumerate(segment_payload.breaks or [], start=1):
            segment.breaks.append(
                ShiftBreak(
                    shift_id=shift.id,
                    sequence_no=break_index,
                    break_type=break_payload.break_type,
                    is_paid=break_payload.is_paid,
                    starts_at=break_payload.starts_at,
                    ends_at=break_payload.ends_at,
                    notes=break_payload.notes,
                    break_metadata=break_payload.break_metadata,
                )
            )
        shift.segments.append(segment)


async def _shift_week_window(
    session: AsyncSession,
    *,
    business_id: UUID,
    shift: Shift,
) -> tuple[date, date]:
    business = await session.get(Business, business_id)
    if business is None:
        raise LookupError("business_not_found")
    location = shift.location
    if location is None:
        location = await session.get(Location, shift.location_id)
    if location is None or location.business_id != business_id:
        raise LookupError("business_or_location_not_found")
    business_settings = business.settings if isinstance(business.settings, dict) else {}
    location_settings = location.settings if isinstance(location.settings, dict) else {}
    week_window = schedule_week_window(
        location.timezone,
        effective_week_start_day(
            business_settings=business_settings,
            location_settings=location_settings,
        ),
        shift.starts_at.astimezone(ZoneInfo(location.timezone)).date(),
    )
    return week_window.week_start, week_window.week_end


def _is_live_shift(shift: Shift) -> bool:
    return shift.lifecycle_status in _LIVE_SHIFT_LIFECYCLE_STATUSES


async def create_shift(session: AsyncSession, business_id: UUID, payload: ShiftCreate) -> Shift:
    location = await session.get(Location, payload.location_id)
    role = await session.get(Role, payload.role_id)
    if location is None or role is None or location.business_id != business_id or role.business_id != business_id:
        raise LookupError("location_or_role_not_found")
    if payload.ends_at <= payload.starts_at:
        raise ValueError("shift_end_must_be_after_start")
    _validate_shift_segments(
        shift_starts_at=payload.starts_at,
        shift_ends_at=payload.ends_at,
        segments=payload.segments,
    )

    enabled_role = await session.scalar(
        select(LocationRole).where(
            LocationRole.location_id == payload.location_id,
            LocationRole.role_id == payload.role_id,
            LocationRole.is_active.is_(True),
        )
    )
    if enabled_role is None:
        raise ValueError("location_role_not_enabled")

    shift = Shift(
        business_id=business_id,
        location_id=payload.location_id,
        role_id=payload.role_id,
        source_system=payload.source_system,
        source_shift_id=payload.source_shift_id,
        timezone=payload.timezone,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        seats_requested=payload.seats_requested,
        requires_manager_approval=payload.requires_manager_approval,
        premium_cents=payload.premium_cents,
        notes=payload.notes,
        shift_metadata=payload.shift_metadata,
    )
    _replace_shift_segments(shift, payload.segments)
    _synchronize_shift_structure_metadata(shift)
    session.add(shift)
    await session.flush()
    await session.refresh(shift)
    return shift


async def update_shift(
    session: AsyncSession,
    business_id: UUID,
    shift_id: UUID,
    payload: ShiftUpdate,
) -> Shift:
    shift = await session.get(
        Shift,
        shift_id,
        options=(
            selectinload(Shift.segments).selectinload(ShiftSegment.breaks),
            selectinload(Shift.assignments),
            selectinload(Shift.coverage_cases),
        ),
    )
    if shift is None or shift.business_id != business_id:
        raise LookupError("shift_not_found")
    if shift.lifecycle_status == ShiftLifecycleStatus.cancelled:
        raise ValueError("cancelled_shift_update_not_allowed")

    changed = False

    if payload.role_id is not None and payload.role_id != shift.role_id:
        role = await session.get(Role, payload.role_id)
        if role is None or role.business_id != business_id:
            raise LookupError("role_not_found")
        enabled_role = await session.scalar(
            select(LocationRole).where(
                LocationRole.location_id == shift.location_id,
                LocationRole.role_id == payload.role_id,
                LocationRole.is_active.is_(True),
            )
        )
        if enabled_role is None:
            raise ValueError("location_role_not_enabled")
        shift.role_id = payload.role_id
        changed = True

    if payload.timezone is not None and payload.timezone != shift.timezone:
        shift.timezone = payload.timezone
        changed = True
    if payload.starts_at is not None and payload.starts_at != shift.starts_at:
        shift.starts_at = payload.starts_at
        changed = True
    if payload.ends_at is not None and payload.ends_at != shift.ends_at:
        shift.ends_at = payload.ends_at
        changed = True
    if payload.starts_at is not None or payload.ends_at is not None:
        if shift.ends_at <= shift.starts_at:
            raise ValueError("shift_end_must_be_after_start")
    next_segments = payload.segments if payload.segments is not None else None
    if next_segments is not None:
        _validate_shift_segments(
            shift_starts_at=shift.starts_at,
            shift_ends_at=shift.ends_at,
            segments=next_segments,
        )
        if _serialize_shift_segments(shift) != _serialize_shift_segment_writes(next_segments):
            _replace_shift_segments(shift, next_segments)
            changed = True
    if payload.seats_requested is not None and payload.seats_requested != shift.seats_requested:
        if payload.seats_requested < max(1, shift.seats_filled):
            raise ValueError("seats_requested_below_current_fill")
        shift.seats_requested = payload.seats_requested
        changed = True
    if (
        payload.requires_manager_approval is not None
        and payload.requires_manager_approval != shift.requires_manager_approval
    ):
        shift.requires_manager_approval = payload.requires_manager_approval
        changed = True
    if payload.premium_cents is not None and payload.premium_cents != shift.premium_cents:
        shift.premium_cents = payload.premium_cents
        changed = True
    if payload.notes is not None and payload.notes != shift.notes:
        shift.notes = payload.notes
        changed = True
    if payload.shift_metadata is not None and payload.shift_metadata != shift.shift_metadata:
        shift.shift_metadata = payload.shift_metadata
        changed = True
    if _synchronize_shift_structure_metadata(shift):
        changed = True

    _recompute_shift_ownership_state(shift)
    if changed and _is_live_shift(shift):
        current_assignment = shift_assignments.current_assignment(shift.assignments or [])
        current_employee_id = current_assignment.employee_id if current_assignment is not None else None
        _mark_shift_amended_from_published(
            shift,
            action="update_shift",
            reason_code="amendment",
            schedule_break=False,
            source="scheduler_ui",
            note=None,
            amended_at=datetime.now(timezone.utc),
            old_employee_id=current_employee_id,
            new_employee_id=current_employee_id,
        )

    await session.flush()
    await session.refresh(shift)
    return shift


async def delete_shift(
    session: AsyncSession,
    business_id: UUID,
    shift_id: UUID,
) -> Shift:
    shift = await session.get(Shift, shift_id)
    if shift is None or shift.business_id != business_id:
        raise LookupError("shift_not_found")

    if shift.lifecycle_status != ShiftLifecycleStatus.draft:
        raise ValueError("scheduled_shift_delete_requires_republish")

    active_case_count = await session.scalar(
        select(func.count(CoverageCase.id)).where(
            CoverageCase.shift_id == shift_id,
            CoverageCase.status.in_([
                CoverageCaseStatus.queued,
                CoverageCaseStatus.running,
                CoverageCaseStatus.filled,
            ]),
        )
    )
    if int(active_case_count or 0) > 0:
        raise ValueError("shift_has_coverage_history")

    await session.delete(shift)
    await session.flush()
    return shift


async def _load_schedule_week_publish_context(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
    week_start_date: date,
) -> ScheduleWeekPublishContext:
    business = await session.get(Business, business_id)
    location = await session.get(Location, location_id)
    if business is None or location is None or location.business_id != business_id:
        raise LookupError("business_or_location_not_found")

    business_settings = business.settings if isinstance(business.settings, dict) else {}
    location_settings = location.settings if isinstance(location.settings, dict) else {}
    window = schedule_week_window(
        location.timezone,
        effective_week_start_day(
            business_settings=business_settings,
            location_settings=location_settings,
        ),
        week_start_date,
    )

    result = await session.execute(
        select(Shift)
        .options(
            selectinload(Shift.location),
            selectinload(Shift.role),
            selectinload(Shift.assignments).selectinload(ShiftAssignment.employee),
        )
        .where(
            Shift.business_id == business_id,
            Shift.location_id == location_id,
            Shift.ends_at >= window.starts_at,
            Shift.starts_at <= window.ends_at,
        )
        .order_by(Shift.starts_at.asc(), Shift.created_at.asc())
    )
    shifts = list(result.scalars().all())
    draft_shifts = [
        shift for shift in shifts if shift.lifecycle_status == ShiftLifecycleStatus.draft
    ]
    already_scheduled_shifts = [
        shift for shift in shifts if shift.lifecycle_status == ShiftLifecycleStatus.scheduled
    ]
    return ScheduleWeekPublishContext(
        business=business,
        location=location,
        week_start_date=window.week_start,
        week_end_date=window.week_end,
        shifts=shifts,
        draft_shifts=draft_shifts,
        already_scheduled_shifts=already_scheduled_shifts,
        current_publishable_shift_ids=[shift.id for shift in draft_shifts],
    )


async def get_schedule_week_future_policy_review(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
    week_start_date: date,
) -> dict[str, object]:
    context = await _load_schedule_week_publish_context(
        session,
        business_id=business_id,
        location_id=location_id,
        week_start_date=week_start_date,
    )
    reference_time = datetime.now(timezone.utc)
    summary, policy_reviews = await schedule_week_publish_future_policy_review(
        session,
        shifts=context.draft_shifts,
        publish_reference_time=reference_time,
    )
    return {
        "week_start_date": context.week_start_date,
        "week_end_date": context.week_end_date,
        "summary": summary,
        "policy_reviews": policy_reviews,
    }


async def publish_schedule_week(
    session: AsyncSession,
    business_id: UUID,
    location_id: UUID,
    week_start_date: date,
    payload: ScheduleWeekPublishWrite,
) -> ScheduleWeekPublishResult:
    context = await _load_schedule_week_publish_context(
        session,
        business_id=business_id,
        location_id=location_id,
        week_start_date=week_start_date,
    )
    business = context.business
    location = context.location
    window_week_start = context.week_start_date
    window_week_end = context.week_end_date
    shifts = context.shifts
    draft_shifts = context.draft_shifts
    already_scheduled_shifts = context.already_scheduled_shifts
    current_publishable_shift_ids = context.current_publishable_shift_ids

    if payload.expected_shift_ids is not None:
        expected_shift_ids = sorted(str(shift_id) for shift_id in payload.expected_shift_ids)
        actual_shift_ids = sorted(str(shift_id) for shift_id in current_publishable_shift_ids)
        if expected_shift_ids != actual_shift_ids:
            raise ScheduleWeekPublishConflictError(
                week_start_date=window_week_start,
                publishable_shift_ids=current_publishable_shift_ids,
                draft_shift_count=len(draft_shifts),
                already_scheduled_shift_count=len(already_scheduled_shifts),
            )

    reference_time = datetime.now(timezone.utc)
    compliance_summary, compliance_review_items = await schedule_week_publish_compliance_review(
        session,
        shifts=draft_shifts,
        reference_time=reference_time,
    )
    if int(compliance_summary.get("blocked_assignment_count") or 0) > 0:
        raise ScheduleWeekPublishComplianceError(
            summary=compliance_summary,
            review_items=compliance_review_items,
        )
    future_policy_summary, future_policy_reviews = await schedule_week_publish_future_policy_review(
        session,
        shifts=draft_shifts,
        publish_reference_time=reference_time,
    )
    if int(future_policy_summary.get("blocked_assignment_count") or 0) > 0:
        raise ScheduleWeekPublishFuturePolicyConflictError(
            summary=future_policy_summary,
            policy_reviews=future_policy_reviews,
        )

    notification_candidate_employee_ids: set[UUID] = set()
    for shift in shifts:
        if _shift_amended_from_published(shift):
            notification_candidate_employee_ids.update(_shift_amended_employee_ids(shift))
    for shift in draft_shifts:
        current_assignment = shift_assignments.current_assignment(shift.assignments or [])
        if current_assignment is not None and current_assignment.employee_id is not None:
            notification_candidate_employee_ids.add(current_assignment.employee_id)

    for shift in shifts:
        _clear_shift_amended_from_published(shift)

    for shift in draft_shifts:
        shift.lifecycle_status = ShiftLifecycleStatus.scheduled

    notification_enqueued_assignment_count, notification_enqueued_employee_count = (
        await _enqueue_schedule_publish_notifications(
            session,
            business_id=business_id,
            business_name=getattr(business, "display_name", None) or business.name,
            location_id=location_id,
            location_name=getattr(location, "display_name", None) or location.name,
            week_start_date=window_week_start,
            week_end_date=window_week_end,
            shifts=shifts,
            notify_channels=payload.notify_channels,
            note=payload.note,
            candidate_employee_ids=notification_candidate_employee_ids,
        )
    )

    await session.flush()
    return ScheduleWeekPublishResult(
        business_id=business_id,
        location_id=location_id,
        week_start_date=window_week_start,
        week_end_date=window_week_end,
        published_shifts=draft_shifts,
        already_scheduled_shifts=already_scheduled_shifts,
        notification_enqueued_assignment_count=notification_enqueued_assignment_count,
        notification_enqueued_employee_count=notification_enqueued_employee_count,
        compliance_summary=compliance_summary,
        compliance_review_items=compliance_review_items,
    )


async def apply_published_shift_amendment(
    session: AsyncSession,
    business_id: UUID,
    shift_id: UUID,
    payload: PublishedShiftAmendmentWrite,
    *,
    assigned_by_user_id: UUID | None = None,
    cancel_active_automation: bool = True,
) -> PublishedShiftAmendmentResult:
    shift = await _load_shift_for_assignment(session, business_id, shift_id)
    if not _is_live_shift(shift):
        raise ValueError("published_shift_amendment_requires_live_shift")
    if payload.action == "reassign_shift":
        if payload.target_employee_id is None:
            raise ValueError("published_shift_reassignment_requires_target_employee")
    elif payload.target_employee_id is not None:
        raise ValueError("published_shift_amendment_target_employee_must_be_null")

    current = shift_assignments.current_assignment(shift.assignments or [])
    latest_assignment = shift_assignments.latest_assignment(shift.assignments or [])
    now = datetime.now(timezone.utc)
    week_start_date, week_end_date = await _shift_week_window(
        session,
        business_id=business_id,
        shift=shift,
    )

    if payload.action == "cancel_shift":
        if payload.reason_code != "cancelled":
            raise ValueError("published_shift_cancel_requires_cancelled_reason")
        cancelled_cases: list[CoverageCase] = []
        cancelled_offers: list[CoverageOffer] = []
        if cancel_active_automation:
            cancelled_cases, cancelled_offers = await _cancel_active_automation(
                session,
                shift,
                reason="published_shift_cancelled",
            )
        if current is not None:
            current.status = AssignmentStatus.cancelled
            current.cancelled_at = now
            current.assignment_metadata = {
                **(current.assignment_metadata or {}),
                "published_amendment_action": payload.action,
                "published_amendment_reason_code": payload.reason_code,
                "published_amendment_source": payload.source,
                "published_amendment_note": payload.note,
                "published_amendment_at": now.isoformat(),
            }
        shift.seats_filled = 0
        shift.lifecycle_status = ShiftLifecycleStatus.cancelled
        shift.staffing_status = ShiftStaffingStatus.open
        _mark_shift_amended_from_published(
            shift,
            action=payload.action,
            reason_code=payload.reason_code,
            schedule_break=False,
            source=payload.source,
            note=payload.note,
            amended_at=now,
            old_employee_id=(
                current.employee_id
                if current is not None
                else latest_assignment.employee_id if latest_assignment is not None else None
            ),
            new_employee_id=None,
        )
        await session.flush()
        await _sync_assignment_history_facts(
            session,
            shift=shift,
            assignments=[current],
        )
        return PublishedShiftAmendmentResult(
            shift=shift,
            action=payload.action,
            reason_code=payload.reason_code,
            source=payload.source,
            previous_assignment=current if current is not None else latest_assignment,
            current_assignment=None,
            cancelled_cases=cancelled_cases,
            cancelled_offers=cancelled_offers,
            week_start_date=week_start_date,
            week_end_date=week_end_date,
        )

    if current is None and not _shift_schedule_break(shift):
        raise ValueError("published_shift_requires_current_assignment")

    if payload.action == "unassign_shift":
        if payload.reason_code not in {"callout", "no_show"}:
            raise ValueError("published_shift_unassign_requires_operational_reason")
        cancelled_cases: list[CoverageCase] = []
        cancelled_offers: list[CoverageOffer] = []
        if cancel_active_automation:
            cancelled_cases, cancelled_offers = await _cancel_active_automation(
                session,
                shift,
                reason="published_shift_unassigned",
            )
        current.status = (
            AssignmentStatus.no_show
            if payload.reason_code == "no_show"
            else AssignmentStatus.cancelled
        )
        current.cancelled_at = now
        current.assignment_metadata = {
            **(current.assignment_metadata or {}),
            "published_amendment_action": payload.action,
            "published_amendment_reason_code": payload.reason_code,
            "published_amendment_source": payload.source,
            "published_amendment_note": payload.note,
            "published_amendment_at": now.isoformat(),
        }
        _recompute_shift_ownership_state(shift)
        _mark_shift_amended_from_published(
            shift,
            action=payload.action,
            reason_code=payload.reason_code,
            schedule_break=True,
            source=payload.source,
            note=payload.note,
            amended_at=now,
            old_employee_id=current.employee_id,
            new_employee_id=None,
        )
        await session.flush()
        await _sync_assignment_history_facts(
            session,
            shift=shift,
            assignments=[current],
        )
        return PublishedShiftAmendmentResult(
            shift=shift,
            action=payload.action,
            reason_code=payload.reason_code,
            source=payload.source,
            previous_assignment=current,
            current_assignment=None,
            cancelled_cases=cancelled_cases,
            cancelled_offers=cancelled_offers,
            week_start_date=week_start_date,
            week_end_date=week_end_date,
        )

    if payload.reason_code != "reassignment":
        raise ValueError("published_shift_reassign_requires_reassignment_reason")
    employee = await _load_employee_for_assignment(session, business_id, payload.target_employee_id)
    _validate_employee_eligibility(employee, shift)
    if current is not None and current.employee_id == employee.id:
        raise ValueError("published_shift_reassignment_requires_different_employee")
    if current is None and latest_assignment is None:
        raise ValueError("published_shift_requires_current_assignment")
    base_evaluation, resolved_evaluation, override_artifact = await _resolve_assignment_compliance(
        session,
        shift=shift,
        employee=employee,
        reference_time=now,
    )
    if bool(resolved_evaluation.get("would_block")):
        summary, review_items = _single_assignment_compliance_review(
            assignment_id=None,
            shift=shift,
            employee=employee,
            evaluation=resolved_evaluation,
        )
        await compliance_decisions.record_shift_compliance_decision(
            session,
            business_id=business_id,
            shift=shift,
            employee=employee,
            evaluation=resolved_evaluation,
            decision_source=payload.source,
            decision_outcome=(
                "blocked_override_required"
                if compliance_overrides.evaluation_has_overridable_block(base_evaluation)
                else "blocked"
            ),
            actor_type=AuditActorType.user if assigned_by_user_id is not None else AuditActorType.system,
            actor_user_id=assigned_by_user_id,
        )
        raise PublishedShiftAmendmentComplianceError(
            summary=summary,
            review_items=review_items,
        )

    cancelled_cases: list[CoverageCase] = []
    cancelled_offers: list[CoverageOffer] = []
    if cancel_active_automation:
        cancelled_cases, cancelled_offers = await _cancel_active_automation(
            session,
            shift,
            reason="published_shift_reassigned",
        )
    prior_reason_code = _shift_amendment_reason_code(shift)
    previous_assignment = current if current is not None else latest_assignment
    if (
        _shift_schedule_break(shift)
        and previous_assignment is not None
        and prior_reason_code in {"callout", "no_show"}
    ):
        _append_shift_historical_artifact(
            shift,
            employee_id=previous_assignment.employee_id,
            employee_name=_assignment_employee_name(previous_assignment),
            reason_code=prior_reason_code,
        )
    if current is not None:
        current.status = AssignmentStatus.cancelled
        current.cancelled_at = now
        current.assignment_metadata = {
            **(current.assignment_metadata or {}),
            "published_amendment_action": payload.action,
            "published_amendment_reason_code": payload.reason_code,
            "published_amendment_source": payload.source,
            "published_amendment_note": payload.note,
            "published_amendment_at": now.isoformat(),
        }
    next_sequence_no = _next_assignment_sequence_no(shift)
    assignment = ShiftAssignment(
        shift_id=shift.id,
        employee_id=employee.id,
        assigned_by_user_id=assigned_by_user_id,
        replaced_assignment_id=(
            current.id
            if current is not None
            else latest_assignment.id if latest_assignment is not None else None
        ),
        assigned_via=payload.source,
        status=AssignmentStatus.assigned,
        sequence_no=next_sequence_no,
        assignment_metadata={
            "note": payload.note,
            "source": payload.source,
            "employee_name": employee.full_name,
            "published_amendment_action": payload.action,
            "published_amendment_reason_code": payload.reason_code,
            "published_amendment_at": now.isoformat(),
            "compliance_evaluation": _compliance_metadata_for_assignment(
                resolved_evaluation,
                override_artifact=override_artifact,
            ),
        },
    )
    assignment.employee = employee
    session.add(assignment)
    shift.assignments.append(assignment)
    _recompute_shift_ownership_state(shift)
    _mark_shift_amended_from_published(
        shift,
        action=payload.action,
        reason_code=payload.reason_code,
        schedule_break=False,
        source=payload.source,
        note=payload.note,
        amended_at=now,
        old_employee_id=(
            current.employee_id
            if current is not None
            else latest_assignment.employee_id if latest_assignment is not None else None
        ),
        new_employee_id=employee.id,
    )
    await session.flush()
    await compliance_decisions.record_shift_compliance_decision(
        session,
        business_id=business_id,
        shift=shift,
        employee=employee,
        evaluation=resolved_evaluation,
        decision_source=payload.source,
        decision_outcome=payload.action,
        assignment=assignment,
        override_artifact=override_artifact,
        actor_type=AuditActorType.user if assigned_by_user_id is not None else AuditActorType.system,
        actor_user_id=assigned_by_user_id,
    )
    await _sync_assignment_history_facts(
        session,
        shift=shift,
        assignments=[current, assignment],
    )
    return PublishedShiftAmendmentResult(
        shift=shift,
        action=payload.action,
        reason_code=payload.reason_code,
        source=payload.source,
        previous_assignment=current if current is not None else latest_assignment,
        current_assignment=assignment,
        cancelled_cases=cancelled_cases,
        cancelled_offers=cancelled_offers,
        week_start_date=week_start_date,
        week_end_date=week_end_date,
    )


async def create_shift_compliance_override_artifact(
    session: AsyncSession,
    business_id: UUID,
    shift_id: UUID,
    payload: ShiftComplianceOverrideCreate,
    *,
    approved_by_user_id: UUID | None = None,
) -> ComplianceOverrideArtifact:
    shift = await _load_shift_for_assignment(session, business_id, shift_id)
    employee = await _load_employee_for_assignment(session, business_id, payload.employee_id)
    _validate_employee_eligibility(employee, shift)

    reference_time = datetime.now(timezone.utc)
    if payload.expires_at is not None and payload.expires_at <= reference_time:
        raise ValueError("compliance_override_expired")

    base_evaluation, _resolved_evaluation, _existing_artifact = await _resolve_assignment_compliance(
        session,
        shift=shift,
        employee=employee,
        reference_time=reference_time,
    )

    artifact_type = ComplianceOverrideArtifactType(payload.artifact_type)
    eligible_rule_results = compliance_overrides.eligible_rule_results_for_artifact_type(
        base_evaluation,
        artifact_type=artifact_type,
    )
    if not eligible_rule_results:
        raise ValueError("compliance_override_not_allowed")

    requested_rule_code = (payload.rule_code or "").strip() or None
    if requested_rule_code is not None and requested_rule_code not in eligible_rule_results:
        raise ValueError("compliance_override_rule_code_mismatch")
    rule_code = requested_rule_code or sorted(eligible_rule_results)[0]
    matched_rule_result = dict(eligible_rule_results.get(rule_code) or {})
    artifact = ComplianceOverrideArtifact(
        business_id=business_id,
        location_id=shift.location_id,
        shift_id=shift.id,
        employee_id=employee.id,
        labor_rule_profile_version_id=(
            UUID(str(base_evaluation["profile_version_id"]))
            if base_evaluation.get("profile_version_id")
            else None
        ),
        approved_by_user_id=approved_by_user_id,
        rule_code=rule_code,
        artifact_type=artifact_type,
        status=ComplianceOverrideArtifactStatus.approved,
        engine_version=compliance_engine.COMPLIANCE_ENGINE_VERSION,
        profile_payload_hash=(
            str(base_evaluation.get("profile_payload_hash"))
            if base_evaluation.get("profile_payload_hash") is not None
            else None
        ),
        approved_at=reference_time,
        expires_at=payload.expires_at or shift.ends_at,
        note=payload.note,
        reason_codes=list(matched_rule_result.get("reason_codes") or []),
        artifact_payload={
            "evidence": dict(payload.artifact_payload or {}),
            "evaluation_reference_time": base_evaluation.get("evaluation_reference_time"),
            "matched_rule_result": matched_rule_result,
        },
    )
    session.add(artifact)
    await session.flush()
    return artifact


async def set_shift_assignment(
    session: AsyncSession,
    business_id: UUID,
    shift_id: UUID,
    payload: ShiftAssignmentWrite,
    *,
    assigned_by_user_id: UUID | None = None,
) -> ShiftAssignmentMutationResult:
    shift = await _load_shift_for_assignment(session, business_id, shift_id)
    if _is_live_shift(shift):
        raise ValueError("published_shift_assignment_requires_amendment")
    if shift.lifecycle_status != ShiftLifecycleStatus.draft:
        raise ValueError("non_draft_shift_assignment_not_allowed")
    current = shift_assignments.current_assignment(shift.assignments or [])

    if int(shift.seats_requested or 1) != 1:
        raise ValueError("single_seat_only_v1")

    expected_assignment_id = payload.expected_assignment_id
    current_assignment_id = current.id if current is not None else None
    if expected_assignment_id != current_assignment_id:
        raise ShiftAssignmentConflictError(current)

    if payload.employee_id is None:
        if current is None:
            return ShiftAssignmentMutationResult(
                shift=shift,
                action="noop",
                source=payload.source,
                previous_assignment=None,
                current_assignment=None,
                cancelled_cases=[],
                cancelled_offers=[],
                no_op=True,
            )

        cancelled_cases, cancelled_offers = await _cancel_active_automation(
            session,
            shift,
            reason="manual_assignment_override",
        )
        now = datetime.now(timezone.utc)
        current.status = AssignmentStatus.cancelled
        current.cancelled_at = now
        current.assignment_metadata = {
            **(current.assignment_metadata or {}),
            "manual_unassigned_at": now.isoformat(),
            "manual_unassigned_note": payload.note,
            "manual_unassigned_source": payload.source,
        }
        _recompute_shift_ownership_state(shift)
        if shift.lifecycle_status == ShiftLifecycleStatus.scheduled:
            shift.lifecycle_status = ShiftLifecycleStatus.draft
        await session.flush()
        await _sync_assignment_history_facts(
            session,
            shift=shift,
            assignments=[current],
        )
        return ShiftAssignmentMutationResult(
            shift=shift,
            action="unassigned",
            source=payload.source,
            previous_assignment=current,
            current_assignment=None,
            cancelled_cases=cancelled_cases,
            cancelled_offers=cancelled_offers,
        )

    employee = await _load_employee_for_assignment(session, business_id, payload.employee_id)
    _validate_employee_eligibility(employee, shift)

    if current is not None and current.employee_id == employee.id:
        return ShiftAssignmentMutationResult(
            shift=shift,
            action="noop",
            source=payload.source,
            previous_assignment=current,
            current_assignment=current,
            cancelled_cases=[],
            cancelled_offers=[],
            no_op=True,
        )
    now = datetime.now(timezone.utc)
    base_evaluation, resolved_evaluation, override_artifact = await _resolve_assignment_compliance(
        session,
        shift=shift,
        employee=employee,
        reference_time=now,
    )
    if bool(resolved_evaluation.get("would_block")):
        summary, review_items = _single_assignment_compliance_review(
            assignment_id=None,
            shift=shift,
            employee=employee,
            evaluation=resolved_evaluation,
        )
        await compliance_decisions.record_shift_compliance_decision(
            session,
            business_id=business_id,
            shift=shift,
            employee=employee,
            evaluation=resolved_evaluation,
            decision_source=payload.source,
            decision_outcome=(
                "blocked_override_required"
                if compliance_overrides.evaluation_has_overridable_block(base_evaluation)
                else "blocked"
            ),
            actor_type=AuditActorType.user if assigned_by_user_id is not None else AuditActorType.system,
            actor_user_id=assigned_by_user_id,
        )
        raise ShiftAssignmentComplianceError(
            summary=summary,
            review_items=review_items,
        )

    cancelled_cases, cancelled_offers = await _cancel_active_automation(
        session,
        shift,
        reason="manual_assignment_override",
    )
    now = datetime.now(timezone.utc)
    next_sequence_no = _next_assignment_sequence_no(shift)
    previous_assignment = current
    if current is not None:
        current.status = AssignmentStatus.replaced
        current.assignment_metadata = {
            **(current.assignment_metadata or {}),
            "replaced_at": now.isoformat(),
            "replaced_via": payload.source,
            "replacement_note": payload.note,
        }

    assignment = ShiftAssignment(
        shift_id=shift.id,
        employee_id=employee.id,
        assigned_by_user_id=assigned_by_user_id,
        replaced_assignment_id=current.id if current is not None else None,
        assigned_via=payload.source,
        status=AssignmentStatus.assigned,
        sequence_no=next_sequence_no,
        assignment_metadata={
            "note": payload.note,
            "source": payload.source,
            "employee_name": employee.full_name,
            "compliance_evaluation": _compliance_metadata_for_assignment(
                resolved_evaluation,
                override_artifact=override_artifact,
            ),
        },
    )
    assignment.employee = employee
    session.add(assignment)
    shift.assignments.append(assignment)
    _recompute_shift_ownership_state(shift)
    if shift.lifecycle_status == ShiftLifecycleStatus.scheduled:
        shift.lifecycle_status = ShiftLifecycleStatus.draft
    await session.flush()
    await compliance_decisions.record_shift_compliance_decision(
        session,
        business_id=business_id,
        shift=shift,
        employee=employee,
        evaluation=resolved_evaluation,
        decision_source=payload.source,
        decision_outcome="assigned" if current is None else "reassigned",
        assignment=assignment,
        override_artifact=override_artifact,
        actor_type=AuditActorType.user if assigned_by_user_id is not None else AuditActorType.system,
        actor_user_id=assigned_by_user_id,
    )
    await _sync_assignment_history_facts(
        session,
        shift=shift,
        assignments=[current, assignment],
    )
    return ShiftAssignmentMutationResult(
        shift=shift,
        action="assigned" if current is None else "reassigned",
        source=payload.source,
        previous_assignment=previous_assignment,
        current_assignment=assignment,
        cancelled_cases=cancelled_cases,
        cancelled_offers=cancelled_offers,
    )


async def _load_shift_for_assignment(
    session: AsyncSession,
    business_id: UUID,
    shift_id: UUID,
) -> Shift:
    shift = await session.get(
        Shift,
        shift_id,
        populate_existing=True,
        options=(
            selectinload(Shift.location),
            selectinload(Shift.role),
            selectinload(Shift.assignments).selectinload(ShiftAssignment.employee),
            selectinload(Shift.coverage_cases)
            .selectinload(CoverageCase.offers)
            .selectinload(CoverageOffer.attempts)
            .selectinload(CoverageContactAttempt.outbox_event),
            selectinload(Shift.coverage_cases).selectinload(CoverageCase.runs),
        ),
    )
    if shift is None or shift.business_id != business_id:
        raise LookupError("shift_not_found")
    return shift


async def _load_employee_for_assignment(
    session: AsyncSession,
    business_id: UUID,
    employee_id: UUID,
) -> Employee:
    employee = await session.get(
        Employee,
        employee_id,
        populate_existing=True,
        options=(
            selectinload(Employee.employee_roles).selectinload(EmployeeRole.role),
            selectinload(Employee.employee_locations).selectinload(EmployeeLocation.location),
        ),
    )
    if employee is None or employee.business_id != business_id:
        raise LookupError("employee_not_found")
    return employee


def _validate_employee_eligibility(employee: Employee, shift: Shift) -> None:
    if employee.status != EmployeeStatus.active:
        raise ValueError("employee_not_active")
    if shift.role_id not in {assignment.role_id for assignment in (employee.employee_roles or [])}:
        raise ValueError("employee_missing_shift_role")
    employee_location = next(
        (
            record
            for record in (employee.employee_locations or [])
            if record.location_id == shift.location_id
        ),
        None,
    )
    if employee_location is None:
        raise ValueError("employee_missing_location_eligibility")
    if employee_location.access_level not in _USABLE_LOCATION_ACCESS_LEVELS:
        raise ValueError("employee_location_not_usable")


def _next_assignment_sequence_no(shift: Shift) -> int:
    existing = [int(assignment.sequence_no or 0) for assignment in (shift.assignments or [])]
    return (max(existing) if existing else 0) + 1


def _recompute_shift_ownership_state(shift: Shift) -> None:
    current = shift_assignments.current_assignment(shift.assignments or [])
    shift.seats_filled = 1 if current is not None else 0
    if current is not None:
        shift.staffing_status = ShiftStaffingStatus.covered
        return
    has_active_automation = any(
        coverage_case.status in _ACTIVE_CASE_STATUSES
        for coverage_case in (shift.coverage_cases or [])
    )
    shift.staffing_status = (
        ShiftStaffingStatus.filling if has_active_automation else ShiftStaffingStatus.open
    )


async def _cancel_active_automation(
    session: AsyncSession,
    shift: Shift,
    *,
    reason: str,
) -> tuple[list[CoverageCase], list[CoverageOffer]]:
    now = datetime.now(timezone.utc)
    cancelled_cases: list[CoverageCase] = []
    cancelled_offers: list[CoverageOffer] = []

    for coverage_case in shift.coverage_cases or []:
        if coverage_case.status not in _ACTIVE_CASE_STATUSES:
            continue
        case_cancelled_offer_ids: list[str] = []
        for offer in coverage_case.offers or []:
            if offer.status not in _ACTIVE_OFFER_STATUSES:
                continue
            offer.status = OfferStatus.cancelled
            offer.offer_metadata = {
                **(offer.offer_metadata or {}),
                "manual_override_reason": reason,
                "manual_override_cancelled_at": now.isoformat(),
            }
            latest_attempt = _latest_attempt(offer)
            if latest_attempt is not None:
                await delivery.mark_offer_attempt_outcome(
                    session,
                    offer,
                    status=CoverageAttemptStatus.cancelled,
                    occurred_at=now,
                    response_payload={"manual_override_reason": reason},
                )
                if latest_attempt.outbox_event is not None and latest_attempt.outbox_event.status in {
                    OutboxStatus.pending,
                    OutboxStatus.processing,
                }:
                    worker_runtime.mark_outbox_event_cancelled(
                        latest_attempt.outbox_event,
                        now=now,
                        error_message=reason,
                        result_payload={"manual_override_reason": reason},
                    )
            cancelled_offers.append(offer)
            case_cancelled_offer_ids.append(str(offer.id))

        if case_cancelled_offer_ids:
            await _cancel_offer_outbox_events(
                session,
                [UUID(offer_id) for offer_id in case_cancelled_offer_ids],
                now=now,
                reason=reason,
            )

        for run in coverage_case.runs or []:
            if run.status not in _ACTIVE_RUN_STATUSES:
                continue
            run.status = CoverageRunStatus.cancelled
            run.finished_at = now
            run.run_metadata = {
                **(run.run_metadata or {}),
                "cancel_reason": reason,
                "cancelled_at": now.isoformat(),
            }

        coverage_case.status = CoverageCaseStatus.cancelled
        coverage_case.closed_at = now
        coverage_case.case_metadata = {
            **(coverage_case.case_metadata or {}),
            "manual_override_reason": reason,
            "manual_override_cancelled_at": now.isoformat(),
            "manual_override_cancelled_offer_ids": case_cancelled_offer_ids,
        }
        cancelled_cases.append(coverage_case)

    return cancelled_cases, cancelled_offers


async def _cancel_offer_outbox_events(
    session: AsyncSession,
    offer_ids: list[UUID],
    *,
    now: datetime,
    reason: str,
) -> None:
    if not offer_ids:
        return
    result = await session.execute(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_type == "coverage_offer",
            OutboxEvent.aggregate_id.in_(offer_ids),
            OutboxEvent.topic == "coverage.offer.created",
            OutboxEvent.status.in_([OutboxStatus.pending, OutboxStatus.processing]),
        )
    )
    for event in result.scalars().all():
        worker_runtime.mark_outbox_event_cancelled(
            event,
            now=now,
            error_message=reason,
            result_payload={"manual_override_reason": reason},
        )


def _latest_attempt(offer: CoverageOffer) -> CoverageContactAttempt | None:
    attempts = list(getattr(offer, "attempts", []) or [])
    if not attempts:
        return None
    return max(
        attempts,
        key=lambda attempt: (
            int(getattr(attempt, "attempt_no", 0) or 0),
            getattr(attempt, "requested_at", None) or datetime.min.replace(tzinfo=timezone.utc),
        ),
    )
