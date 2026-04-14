from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from html import escape
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.business import Business, Location, LocationRole, Role
from app.models.common import (
    AssignmentStatus,
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
from app.models.scheduling import Shift, ShiftAssignment
from app.models.workforce import Employee, EmployeeLocation, EmployeeRole
from app.schemas.scheduling import (
    PublishedShiftAmendmentRead,
    PublishedShiftAmendmentWrite,
    ScheduleWeekPublishRead,
    ScheduleWeekPublishWrite,
    ShiftAssignmentMutationResponse,
    ShiftAssignmentRead,
    ShiftAssignmentWrite,
    ShiftCreate,
    ShiftUpdate,
)
from app.services import (
    communication_suppressions,
    delivery,
    employee_schedule_links as employee_schedule_link_service,
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
    )


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
    metadata["schedule_break"] = False
    metadata["reason_code"] = None
    metadata["action"] = None
    metadata["note"] = None
    metadata["source"] = None
    metadata["old_employee_id"] = None
    metadata["new_employee_id"] = None
    metadata["amended_at"] = None
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

    for employee_id, employee_shifts in shifts_by_employee.items():
        employee = employees_by_id[employee_id]
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
        for channel in normalized_channels:
            if channel == "sms" and (
                not employee.phone_e164 or not _employee_allows_publish_notification(employee, "sms")
            ):
                continue
            if channel == "email" and (
                not employee.email or not _employee_allows_publish_notification(employee, "email")
            ):
                continue
            if await _employee_is_globally_suppressed(session, employee=employee, channel=channel):
                continue
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

    return enqueued_assignment_count, len(shifts_by_employee)


async def list_shifts(
    session: AsyncSession,
    business_id: UUID,
    *,
    location_id: UUID | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
) -> list[Shift]:
    stmt = select(Shift).where(Shift.business_id == business_id)
    if location_id is not None:
        stmt = stmt.where(Shift.location_id == location_id)
    if starts_at is not None:
        stmt = stmt.where(Shift.ends_at >= starts_at)
    if ends_at is not None:
        stmt = stmt.where(Shift.starts_at <= ends_at)
    result = await session.execute(stmt.order_by(Shift.starts_at.asc()))
    return list(result.scalars().all())


async def get_shift(session: AsyncSession, business_id: UUID, shift_id: UUID) -> Shift:
    shift = await session.get(Shift, shift_id)
    if shift is None or shift.business_id != business_id:
        raise LookupError("shift_not_found")
    return shift


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
            selectinload(Shift.assignments),
            selectinload(Shift.coverage_cases),
        ),
    )
    if shift is None or shift.business_id != business_id:
        raise LookupError("shift_not_found")

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

    _recompute_shift_ownership_state(shift)
    if changed and shift.lifecycle_status == ShiftLifecycleStatus.scheduled:
        shift.lifecycle_status = ShiftLifecycleStatus.draft

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


async def publish_schedule_week(
    session: AsyncSession,
    business_id: UUID,
    location_id: UUID,
    week_start_date: date,
    payload: ScheduleWeekPublishWrite,
) -> ScheduleWeekPublishResult:
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
    current_publishable_shift_ids = [shift.id for shift in draft_shifts]

    if payload.expected_shift_ids is not None:
        expected_shift_ids = sorted(str(shift_id) for shift_id in payload.expected_shift_ids)
        actual_shift_ids = sorted(str(shift_id) for shift_id in current_publishable_shift_ids)
        if expected_shift_ids != actual_shift_ids:
            raise ScheduleWeekPublishConflictError(
                week_start_date=window.week_start,
                publishable_shift_ids=current_publishable_shift_ids,
                draft_shift_count=len(draft_shifts),
                already_scheduled_shift_count=len(already_scheduled_shifts),
            )

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
            week_start_date=window.week_start,
            week_end_date=window.week_end,
            shifts=draft_shifts,
            notify_channels=payload.notify_channels,
            note=payload.note,
        )
    )

    await session.flush()
    return ScheduleWeekPublishResult(
        business_id=business_id,
        location_id=location_id,
        week_start_date=window.week_start,
        week_end_date=window.week_end,
        published_shifts=draft_shifts,
        already_scheduled_shifts=already_scheduled_shifts,
        notification_enqueued_assignment_count=notification_enqueued_assignment_count,
        notification_enqueued_employee_count=notification_enqueued_employee_count,
    )


async def apply_published_shift_amendment(
    session: AsyncSession,
    business_id: UUID,
    shift_id: UUID,
    payload: PublishedShiftAmendmentWrite,
    *,
    assigned_by_user_id: UUID | None = None,
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
    now = datetime.now(timezone.utc)
    week_start_date, week_end_date = await _shift_week_window(
        session,
        business_id=business_id,
        shift=shift,
    )

    if payload.action == "cancel_shift":
        if payload.reason_code != "cancelled":
            raise ValueError("published_shift_cancel_requires_cancelled_reason")
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
            old_employee_id=current.employee_id if current is not None else None,
            new_employee_id=None,
        )
        await session.flush()
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

    if current is None:
        raise ValueError("published_shift_requires_current_assignment")

    if payload.action == "unassign_shift":
        if payload.reason_code not in {"callout", "no_show"}:
            raise ValueError("published_shift_unassign_requires_operational_reason")
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

    if payload.reason_code not in {"callout", "no_show"}:
        raise ValueError("published_shift_reassign_requires_operational_reason")
    employee = await _load_employee_for_assignment(session, business_id, payload.target_employee_id)
    _validate_employee_eligibility(employee, shift)
    if current.employee_id == employee.id:
        raise ValueError("published_shift_reassignment_requires_different_employee")

    cancelled_cases, cancelled_offers = await _cancel_active_automation(
        session,
        shift,
        reason="published_shift_reassigned",
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
    next_sequence_no = _next_assignment_sequence_no(shift)
    assignment = ShiftAssignment(
        shift_id=shift.id,
        employee_id=employee.id,
        assigned_by_user_id=assigned_by_user_id,
        replaced_assignment_id=current.id,
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
        old_employee_id=current.employee_id,
        new_employee_id=employee.id,
    )
    await session.flush()
    return PublishedShiftAmendmentResult(
        shift=shift,
        action=payload.action,
        reason_code=payload.reason_code,
        source=payload.source,
        previous_assignment=current,
        current_assignment=assignment,
        cancelled_cases=cancelled_cases,
        cancelled_offers=cancelled_offers,
        week_start_date=week_start_date,
        week_end_date=week_end_date,
    )


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
        },
    )
    assignment.employee = employee
    session.add(assignment)
    shift.assignments.append(assignment)
    _recompute_shift_ownership_state(shift)
    if shift.lifecycle_status == ShiftLifecycleStatus.scheduled:
        shift.lifecycle_status = ShiftLifecycleStatus.draft
    await session.flush()
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
