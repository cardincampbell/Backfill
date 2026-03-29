"""
Location notification service.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

import aiosqlite

from app.config import settings
from app.models.audit import AuditAction
from app.services import audit as audit_svc
from app.services import outreach as outreach_svc
from app.services.messaging import send_sms


def notify_shift_filled(
    manager_phone: str,
    worker_name: str,
    role: str,
    date: str,
    start_time: str,
    fill_tier: str,
) -> Optional[str]:
    """Send an SMS to the manager confirming coverage. Returns Twilio SID."""
    tier_label = {
        "tier1_internal": "one of your staff members",
        "tier2_alumni": "a trusted prior worker",
        "tier3_agency": "a partner agency worker",
    }.get(fill_tier, "a worker")

    body = (
        f"✅ Backfill: Your {role} shift on {date} at {start_time} "
        f"has been covered by {worker_name} ({tier_label}). "
        f"Reply STATUS to check coverage anytime."
    )
    return send_sms(manager_phone, body)


def notify_cascade_exhausted(
    manager_phone: str,
    role: str,
    date: str,
    start_time: str,
) -> Optional[str]:
    """Notify manager that no internal coverage was found."""
    body = (
        f"⚠️ Backfill: We couldn't find internal coverage for your "
        f"{role} shift on {date} at {start_time}. "
        f"Reply AGENCY to approve routing to a partner staffing agency, "
        f"or call 1-800-BACKFILL to handle manually."
    )
    return send_sms(manager_phone, body)


def build_manager_dashboard_link(
    location_id: int,
    *,
    tab: str,
    week_start: Optional[str] = None,
    job_id: Optional[int] = None,
    row_number: Optional[int] = None,
    shift_id: Optional[int] = None,
) -> str:
    params: list[tuple[str, str | int]] = [("tab", tab)]
    if week_start:
        params.append(("week_start", week_start))
    if job_id is not None:
        params.append(("job_id", job_id))
    if row_number is not None:
        params.append(("row", row_number))
    if shift_id is not None:
        params.append(("shift_id", shift_id))
    return f"{settings.backfill_web_base_url}/dashboard/locations/{location_id}?{urlencode(params)}"


def _format_week_range(week_start_date: str) -> str:
    week_start = date.fromisoformat(week_start_date)
    week_end = week_start + timedelta(days=6)
    if week_start.month == week_end.month:
        return f"{week_start.strftime('%b')} {week_start.day}-{week_end.day}"
    return f"{week_start.strftime('%b')} {week_start.day}-{week_end.strftime('%b')} {week_end.day}"


def _summarize_review_items(review_items: list[str], *, limit: int = 2) -> str:
    if not review_items:
        return ""
    visible = review_items[:limit]
    summary = ", ".join(visible)
    remaining = len(review_items) - len(visible)
    if remaining > 0:
        summary = f"{summary}, +{remaining} more"
    return summary


def notify_schedule_draft_ready(
    manager_phone: str,
    *,
    location_name: str,
    week_start_date: str,
    filled_shifts: int,
    total_shifts: int,
    review_items: list[str],
    review_link: str,
    first_draft: bool = False,
) -> Optional[str]:
    body = build_schedule_draft_ready_message(
        location_name=location_name,
        week_start_date=week_start_date,
        filled_shifts=filled_shifts,
        total_shifts=total_shifts,
        review_items=review_items,
        review_link=review_link,
        first_draft=first_draft,
    )
    return send_sms(manager_phone, body)


def build_schedule_draft_ready_message(
    *,
    location_name: str,
    week_start_date: str,
    filled_shifts: int,
    total_shifts: int,
    review_items: list[str],
    review_link: str,
    first_draft: bool = False,
) -> str:
    label = "Your first draft" if first_draft else "Your draft"
    week_range = _format_week_range(week_start_date)
    if review_items:
        return (
            f"Backfill: {label} for {week_range} is ready. "
            f"{filled_shifts} of {total_shifts} shifts are assigned. "
            f"{len(review_items)} need review: {_summarize_review_items(review_items)}. "
            f"Reply APPROVE or tap to review: {review_link}"
        )
    return (
        f"Backfill: {label} for {week_range} is ready. "
        f"{filled_shifts} of {total_shifts} shifts are assigned. "
        f"Reply APPROVE to publish or REVIEW to edit: {review_link}"
    )


def notify_schedule_published(
    manager_phone: str,
    *,
    sms_sent: int,
    not_enrolled: int,
    sms_failed: int = 0,
    sms_removed_sent: int = 0,
    week_start_date: Optional[str] = None,
    is_update: bool = False,
    change_highlights: Optional[list[str]] = None,
) -> Optional[str]:
    body = build_schedule_published_message(
        sms_sent=sms_sent,
        not_enrolled=not_enrolled,
        sms_failed=sms_failed,
        sms_removed_sent=sms_removed_sent,
        week_start_date=week_start_date,
        is_update=is_update,
        change_highlights=change_highlights,
    )
    return send_sms(manager_phone, body)


def build_schedule_published_message(
    *,
    sms_sent: int,
    not_enrolled: int,
    sms_failed: int = 0,
    sms_removed_sent: int = 0,
    week_start_date: Optional[str] = None,
    is_update: bool = False,
    change_highlights: Optional[list[str]] = None,
) -> str:
    enrolled_label = "employee received" if sms_sent == 1 else "employees received"
    needs_opt_in_label = "still needs" if not_enrolled == 1 else "still need"
    body = "Backfill: Published. Your team has been notified. "
    if is_update:
        schedule_label = (
            f"for {_format_week_range(week_start_date)}" if week_start_date else "for the latest week"
        )
        body = f"Backfill: Published your schedule updates {schedule_label}. "
        visible_highlights = [
            item for item in (change_highlights or []) if item and not item.startswith("No major changes")
        ][:2]
        if visible_highlights:
            body += f"{'; '.join(visible_highlights)}. "
        update_label = "employee received updated shifts" if sms_sent == 1 else "employees received updated shifts"
        body += f"{sms_sent} {update_label}. "
        if sms_removed_sent:
            removed_label = (
                "employee was told they are no longer scheduled"
                if sms_removed_sent == 1
                else "employees were told they are no longer scheduled"
            )
            body += f"{sms_removed_sent} {removed_label}. "
    else:
        body += f"{sms_sent} {enrolled_label} their schedule. "
    if sms_failed:
        failure_label = "delivery could not be sent" if sms_failed == 1 else "deliveries could not be sent"
        body += f"{sms_failed} {failure_label} right now. "
    body += f"{not_enrolled} {needs_opt_in_label} to opt in to SMS."
    return body


def build_schedule_publish_blocked_message(
    *,
    week_start_date: str,
    blocking_issue_count: int,
    blocked_items: list[str],
    review_link: str,
) -> str:
    visible_items = [item for item in blocked_items if item][:2]
    summary = "; ".join(visible_items)
    extra_count = max(len([item for item in blocked_items if item]) - len(visible_items), 0)
    if extra_count:
        summary = f"{summary}; +{extra_count} more" if summary else f"+{extra_count} more"
    blocker_label = "blocker" if blocking_issue_count == 1 else "blockers"
    return (
        f"Backfill: Your draft for {_format_week_range(week_start_date)} "
        f"is not ready to publish yet. "
        f"{blocking_issue_count} {blocker_label}: {summary}. "
        f"Review: {review_link}"
    )


def notify_manager_operational_digest(
    manager_phone: str,
    *,
    location_name: str,
    lookahead_hours: int,
    scheduled_shifts: int,
    open_shifts: int,
    active_coverage: int,
    pending_actions: int,
    attendance_issues: int = 0,
    late_arrivals: int = 0,
    late_arrivals_awaiting_decision: int = 0,
    missed_check_ins: int = 0,
    missed_check_ins_awaiting_decision: int = 0,
    missed_check_ins_escalated: int = 0,
    review_link: str,
) -> Optional[str]:
    shift_label = "shift" if scheduled_shifts == 1 else "shifts"
    open_label = "open shift" if open_shifts == 1 else "open shifts"
    action_label = "manager action" if pending_actions == 1 else "manager actions"
    coverage_label = "coverage workflow" if active_coverage == 1 else "coverage workflows"
    attendance_label = "attendance issue" if attendance_issues == 1 else "attendance issues"
    if scheduled_shifts <= 0:
        body = (
            f"Backfill: No scheduled shifts at {location_name} in the next {lookahead_hours}h. "
            f"Review: {review_link}"
        )
    elif pending_actions or open_shifts or active_coverage:
        body = (
            f"Backfill: Next {lookahead_hours}h for {location_name}: "
            f"{scheduled_shifts} {shift_label}, {open_shifts} {open_label}, {active_coverage} in {coverage_label}, "
            f"{pending_actions} {action_label} needed. Review: {review_link}"
        )
    else:
        verb = "is" if scheduled_shifts == 1 else "are"
        body = (
            f"Backfill: Next {lookahead_hours}h for {location_name} looks on track. "
            f"{scheduled_shifts} {shift_label} {verb} scheduled and all assigned. Review: {review_link}"
        )
    if attendance_issues > 0 and scheduled_shifts > 0:
        attendance_details: list[str] = []
        late_reported = max(0, int(late_arrivals) - int(late_arrivals_awaiting_decision))
        if late_arrivals_awaiting_decision > 0:
            label = (
                "late awaiting decision"
                if late_arrivals_awaiting_decision == 1
                else "late arrivals awaiting decision"
            )
            attendance_details.append(f"{late_arrivals_awaiting_decision} {label}")
        if late_reported > 0:
            label = "late reported" if late_reported == 1 else "late arrivals reported"
            attendance_details.append(f"{late_reported} {label}")
        if missed_check_ins_awaiting_decision > 0:
            label = (
                "missed check-in awaiting decision"
                if missed_check_ins_awaiting_decision == 1
                else "missed check-ins awaiting decision"
            )
            attendance_details.append(f"{missed_check_ins_awaiting_decision} {label}")
        if missed_check_ins_escalated > 0:
            label = (
                "missed check-in escalated"
                if missed_check_ins_escalated == 1
                else "missed check-ins escalated"
            )
            attendance_details.append(f"{missed_check_ins_escalated} {label}")
        detail_text = ", ".join(attendance_details) if attendance_details else f"{attendance_issues} {attendance_label}"
        body = body.replace(f" Review: {review_link}", f" {detail_text}. Review: {review_link}")
    return send_sms(manager_phone, body)


def notify_manager_callout_received(
    manager_phone: str,
    *,
    worker_name: str,
    location_name: str,
    role: str,
    shift_date: str,
    start_time: str,
    coverage_link: str,
) -> Optional[str]:
    shift_day = date.fromisoformat(shift_date)
    body = (
        f"Backfill: {worker_name} called out for {location_name}'s {role} shift on "
        f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} at "
        f"{_format_shift_clock(start_time)}. Coverage has started. Review: {coverage_link}"
    )
    return send_sms(manager_phone, body)


def notify_worker_shift_confirmation_request(
    worker_phone: str,
    *,
    worker_name: str,
    location_name: str,
    role: str,
    shift_date: str,
    start_time: str,
) -> Optional[str]:
    shift_day = date.fromisoformat(shift_date)
    body = (
        f"Backfill: {worker_name}, please confirm your {role} shift at {location_name} on "
        f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} at "
        f"{_format_shift_clock(start_time)}. Reply YES if you're still coming or NO if you can't make it."
    )
    return send_sms(worker_phone, body)


def notify_worker_shift_confirmed(
    worker_phone: str,
    *,
    location_name: str,
    role: str,
    shift_date: str,
    start_time: str,
) -> Optional[str]:
    shift_day = date.fromisoformat(shift_date)
    body = (
        f"Backfill: Thanks, you're confirmed for {location_name}'s {role} shift on "
        f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} at "
        f"{_format_shift_clock(start_time)}."
    )
    return send_sms(worker_phone, body)


def notify_worker_shift_check_in_request(
    worker_phone: str,
    *,
    worker_name: str,
    location_name: str,
    role: str,
    shift_date: str,
    start_time: str,
) -> Optional[str]:
    shift_day = date.fromisoformat(shift_date)
    body = (
        f"Backfill: {worker_name}, your {role} shift at {location_name} starts "
        f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} at "
        f"{_format_shift_clock(start_time)}. Reply HERE when you arrive or LATE 15 if you're running behind."
    )
    return send_sms(worker_phone, body)


def notify_manager_late_arrival_reported(
    manager_phone: str,
    *,
    worker_name: str,
    location_name: str,
    role: str,
    shift_date: str,
    start_time: str,
    eta_minutes: int,
    review_link: str,
) -> Optional[str]:
    shift_day = date.fromisoformat(shift_date)
    minute_label = "minute" if eta_minutes == 1 else "minutes"
    body = (
        f"Backfill: {worker_name} says they're about {eta_minutes} {minute_label} late for "
        f"{location_name}'s {role} shift on {shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} "
        f"at {_format_shift_clock(start_time)}. Review: {review_link}"
    )
    return send_sms(manager_phone, body)


def notify_manager_late_arrival_coverage_started(
    manager_phone: str,
    *,
    worker_name: str,
    location_name: str,
    role: str,
    shift_date: str,
    start_time: str,
    eta_minutes: int,
    coverage_link: str,
) -> Optional[str]:
    shift_day = date.fromisoformat(shift_date)
    minute_label = "minute" if eta_minutes == 1 else "minutes"
    body = (
        f"Backfill: {worker_name} reported they're about {eta_minutes} {minute_label} late for "
        f"{location_name}'s {role} shift on {shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} "
        f"at {_format_shift_clock(start_time)}. Coverage has started. Review: {coverage_link}"
    )
    return send_sms(manager_phone, body)


def notify_manager_unconfirmed_shift_escalated(
    manager_phone: str,
    *,
    worker_name: str,
    location_name: str,
    role: str,
    shift_date: str,
    start_time: str,
    coverage_link: str,
) -> Optional[str]:
    shift_day = date.fromisoformat(shift_date)
    body = (
        f"Backfill: {worker_name} hasn't confirmed {location_name}'s {role} shift on "
        f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} at "
        f"{_format_shift_clock(start_time)}. Coverage has started. Review: {coverage_link}"
    )
    return send_sms(manager_phone, body)


def notify_manager_missed_check_in_action_required(
    manager_phone: str,
    *,
    worker_name: str,
    location_name: str,
    role: str,
    shift_date: str,
    start_time: str,
    review_link: str,
) -> Optional[str]:
    shift_day = date.fromisoformat(shift_date)
    body = (
        f"Backfill: {worker_name} didn't check in for {location_name}'s {role} shift on "
        f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} at "
        f"{_format_shift_clock(start_time)}. Reply REVIEW or open: {review_link}"
    )
    return send_sms(manager_phone, body)


def notify_manager_missed_check_in_escalated(
    manager_phone: str,
    *,
    worker_name: str,
    location_name: str,
    role: str,
    shift_date: str,
    start_time: str,
    coverage_link: str,
) -> Optional[str]:
    shift_day = date.fromisoformat(shift_date)
    body = (
        f"Backfill: {worker_name} didn't check in for {location_name}'s {role} shift on "
        f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} at "
        f"{_format_shift_clock(start_time)}. Coverage has started. Review: {coverage_link}"
    )
    return send_sms(manager_phone, body)


def notify_manager_claim_approval_requested(
    manager_phone: str,
    *,
    worker_name: str,
    role: str,
    shift_date: str,
    start_time: str,
    coverage_link: str,
    vacancy_kind: str = "callout",
) -> Optional[str]:
    shift_day = date.fromisoformat(shift_date)
    if vacancy_kind == "open_shift":
        body = (
            f"Backfill: {worker_name} wants to claim your open {role} shift on "
            f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} at "
            f"{_format_shift_clock(start_time)}. Reply YES to approve or NO to keep looking. "
            f"Review: {coverage_link}"
        )
    else:
        body = (
            f"Backfill: {worker_name} wants to cover your {role} shift on "
            f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} at "
            f"{_format_shift_clock(start_time)}. Reply YES to approve or NO to keep looking. "
            f"Review: {coverage_link}"
        )
    return send_sms(manager_phone, body)


def notify_worker_claim_pending_approval(
    worker_phone: str,
    *,
    role: str,
    shift_date: str,
    start_time: str,
    vacancy_kind: str = "callout",
) -> Optional[str]:
    shift_day = date.fromisoformat(shift_date)
    if vacancy_kind == "open_shift":
        body = (
            f"Backfill: We got your open shift claim for the {role} shift on "
            f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} at "
            f"{_format_shift_clock(start_time)} and sent it to the manager for approval."
        )
    else:
        body = (
            f"Backfill: We got your claim for the {role} shift on "
            f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} at "
            f"{_format_shift_clock(start_time)} and sent it to the manager for approval."
        )
    return send_sms(worker_phone, body)


def notify_worker_claim_approved(
    worker_phone: str,
    *,
    role: str,
    shift_date: str,
    start_time: str,
    vacancy_kind: str = "callout",
) -> Optional[str]:
    shift_day = date.fromisoformat(shift_date)
    if vacancy_kind == "open_shift":
        body = (
            f"Backfill: You're confirmed for the open {role} shift on "
            f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} at "
            f"{_format_shift_clock(start_time)}."
        )
    else:
        body = (
            f"Backfill: You're confirmed for the {role} shift on "
            f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} at "
            f"{_format_shift_clock(start_time)}."
        )
    return send_sms(worker_phone, body)


def notify_worker_claim_denied(
    worker_phone: str,
    *,
    role: str,
    shift_date: str,
    start_time: str,
    vacancy_kind: str = "callout",
) -> Optional[str]:
    shift_day = date.fromisoformat(shift_date)
    if vacancy_kind == "open_shift":
        body = (
            f"Backfill: The manager passed on your open shift claim for the {role} shift on "
            f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} at "
            f"{_format_shift_clock(start_time)}. We'll keep looking."
        )
    else:
        body = (
            f"Backfill: The manager passed on your claim for the {role} shift on "
            f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} at "
            f"{_format_shift_clock(start_time)}. We'll keep looking for coverage."
        )
    return send_sms(worker_phone, body)


def notify_worker_open_shift_closed(
    worker_phone: str,
    *,
    role: str,
    shift_date: str,
    start_time: str,
) -> Optional[str]:
    shift_day = date.fromisoformat(shift_date)
    body = (
        f"Backfill: The open {role} shift on "
        f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} at "
        f"{_format_shift_clock(start_time)} is no longer available."
    )
    return send_sms(worker_phone, body)


def _format_shift_clock(value: str) -> str:
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return value


def _format_worker_schedule_line(shift: dict) -> str:
    shift_day = date.fromisoformat(str(shift["date"]))
    return (
        f"{shift_day.strftime('%a')} {shift_day.strftime('%b')} {shift_day.day} "
        f"{_format_shift_clock(str(shift['start_time']))}-{_format_shift_clock(str(shift['end_time']))} "
        f"{shift['role']}"
    )


def _summarize_worker_schedule_lines(shifts: list[dict], *, limit: int = 3) -> str:
    ordered = sorted(
        shifts,
        key=lambda shift: (
            str(shift.get("date") or ""),
            str(shift.get("start_time") or ""),
            int(shift.get("id") or 0),
        ),
    )
    lines = [_format_worker_schedule_line(shift) for shift in ordered]
    visible = lines[:limit]
    summary = "; ".join(visible)
    remaining = len(lines) - len(visible)
    if remaining > 0:
        summary = f"{summary}; +{remaining} more"
    return summary


def _summarize_schedule_line_labels(lines: list[str], *, limit: int = 3) -> str:
    ordered = sorted(str(line) for line in lines if line)
    visible = ordered[:limit]
    summary = "; ".join(visible)
    remaining = len(ordered) - len(visible)
    if remaining > 0:
        summary = f"{summary}; +{remaining} more"
    return summary


def build_worker_schedule_published_message(
    *,
    worker_name: str,
    location_name: str,
    week_start_date: str,
    shifts: list[dict],
    is_update: bool = False,
) -> str:
    schedule_label = "updated schedule" if is_update else "schedule"
    return (
        f"Backfill: {worker_name}, your {schedule_label} at {location_name} "
        f"for {_format_week_range(week_start_date)}: "
        f"{_summarize_worker_schedule_lines(shifts)}. "
        "We'll text reminders before your shift. Reply STOP to opt out."
    )


def notify_worker_schedule_published(
    worker_phone: str,
    *,
    worker_name: str,
    location_name: str,
    week_start_date: str,
    shifts: list[dict],
    is_update: bool = False,
) -> Optional[str]:
    body = build_worker_schedule_published_message(
        worker_name=worker_name,
        location_name=location_name,
        week_start_date=week_start_date,
        shifts=shifts,
        is_update=is_update,
    )
    return send_sms(worker_phone, body)


def build_worker_schedule_removed_message(
    *,
    worker_name: str,
    location_name: str,
    week_start_date: str,
    removed_lines: list[str],
) -> str:
    return (
        f"Backfill: {worker_name}, your schedule at {location_name} for "
        f"{_format_week_range(week_start_date)} was updated. You're no longer scheduled for: "
        f"{_summarize_schedule_line_labels(removed_lines)}. "
        "Reply HELP if this looks wrong."
    )


def notify_worker_schedule_removed(
    worker_phone: str,
    *,
    worker_name: str,
    location_name: str,
    week_start_date: str,
    removed_lines: list[str],
) -> Optional[str]:
    body = build_worker_schedule_removed_message(
        worker_name=worker_name,
        location_name=location_name,
        week_start_date=week_start_date,
        removed_lines=removed_lines,
    )
    return send_sms(worker_phone, body)


def build_worker_schedule_added_message(
    *,
    worker_name: str,
    location_name: str,
    week_start_date: str,
    added_lines: list[str],
) -> str:
    return (
        f"Backfill: {worker_name}, you're now scheduled at {location_name} for "
        f"{_format_week_range(week_start_date)}: "
        f"{_summarize_schedule_line_labels(added_lines)}. "
        "We'll text reminders before your shift. Reply HELP if this looks wrong."
    )


def notify_worker_schedule_added(
    worker_phone: str,
    *,
    worker_name: str,
    location_name: str,
    week_start_date: str,
    added_lines: list[str],
) -> Optional[str]:
    body = build_worker_schedule_added_message(
        worker_name=worker_name,
        location_name=location_name,
        week_start_date=week_start_date,
        added_lines=added_lines,
    )
    return send_sms(worker_phone, body)


def build_worker_schedule_changed_message(
    *,
    worker_name: str,
    location_name: str,
    week_start_date: str,
    added_lines: list[str],
    removed_lines: list[str],
    current_lines: list[str],
) -> str:
    body = (
        f"Backfill: {worker_name}, your schedule at {location_name} for "
        f"{_format_week_range(week_start_date)} was updated. "
    )
    if added_lines:
        body += f"Added: {_summarize_schedule_line_labels(added_lines)}. "
    if removed_lines:
        body += f"Removed: {_summarize_schedule_line_labels(removed_lines)}. "
    if current_lines:
        body += f"Current schedule: {_summarize_schedule_line_labels(current_lines)}. "
    body += "Reply HELP if this looks wrong."
    return body


def notify_worker_schedule_changed(
    worker_phone: str,
    *,
    worker_name: str,
    location_name: str,
    week_start_date: str,
    added_lines: list[str],
    removed_lines: list[str],
    current_lines: list[str],
) -> Optional[str]:
    body = build_worker_schedule_changed_message(
        worker_name=worker_name,
        location_name=location_name,
        week_start_date=week_start_date,
        added_lines=added_lines,
        removed_lines=removed_lines,
        current_lines=current_lines,
    )
    return send_sms(worker_phone, body)


def build_worker_enrollment_confirmation_text(
    *,
    location_name: str,
    organization_name: Optional[str] = None,
    week_start_date: Optional[str] = None,
    shifts: Optional[list[dict]] = None,
) -> str:
    business_name = organization_name or location_name
    body = (
        f"Backfill for {business_name}: You're enrolled for schedule updates, "
        f"shift offers, and callout routing for {location_name}. "
    )
    if week_start_date and shifts:
        body += (
            f"Current schedule for {_format_week_range(week_start_date)}: "
            f"{_summarize_worker_schedule_lines(shifts)}. "
        )
    body += "Msg frequency varies. Reply STOP to unsubscribe."
    return body


def build_worker_enrollment_invite_text(
    *,
    location_name: str,
    organization_name: Optional[str] = None,
) -> str:
    business_name = organization_name or location_name
    return (
        f"Backfill for {business_name}: {location_name} is using Backfill for schedules, "
        "callouts, and open shifts. Reply JOIN to enroll. Msg frequency varies. "
        "Reply STOP to opt out."
    )


async def enqueue_notification(
    db: aiosqlite.Connection,
    *,
    notification_type: str,
    payload: dict,
    location_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
    max_attempts: int = 3,
) -> dict:
    if not notification_type:
        raise ValueError("notification_type is required")
    normalized_payload = dict(payload or {})
    if not settings.backfill_ops_worker_enabled:
        result = await process_notification_job(
            db,
            notification_type=notification_type,
            payload=normalized_payload,
        )
        result["delivery_mode"] = "inline"
        return result

    from app.services import ops_queue

    job = await ops_queue.enqueue_job(
        db,
        job_type="send_notification",
        location_id=location_id,
        payload={
            "notification_type": notification_type,
            "payload": normalized_payload,
        },
        max_attempts=max_attempts,
        idempotency_key=idempotency_key,
    )
    return {
        "status": "queued",
        "delivery_mode": "queued",
        "notification_type": notification_type,
        "job_id": int(job["id"]),
    }


async def queue_manager_notification(
    db: aiosqlite.Connection,
    *,
    cascade_id: int,
    worker_id: int,
    filled: bool,
    location_id: Optional[int] = None,
) -> dict:
    return await enqueue_notification(
        db,
        notification_type="manager_notification",
        payload={
            "cascade_id": int(cascade_id),
            "worker_id": int(worker_id),
            "filled": bool(filled),
        },
        location_id=location_id,
        idempotency_key=f"manager_notification:{'filled' if filled else 'exhausted'}:{cascade_id}:{worker_id}",
    )


async def queue_manager_callout_received_notification(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    shift_id: int,
    worker_id: int,
    cascade_id: int,
) -> dict:
    return await enqueue_notification(
        db,
        notification_type="manager_callout_received",
        payload={
            "location_id": int(location_id),
            "shift_id": int(shift_id),
            "worker_id": int(worker_id),
            "cascade_id": int(cascade_id),
        },
        location_id=location_id,
        idempotency_key=f"manager_callout_received:{cascade_id}",
    )


async def queue_manager_unconfirmed_shift_escalated_notification(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    shift_id: int,
    worker_id: int,
    cascade_id: int,
) -> dict:
    return await enqueue_notification(
        db,
        notification_type="manager_unconfirmed_shift_escalated",
        payload={
            "location_id": int(location_id),
            "shift_id": int(shift_id),
            "worker_id": int(worker_id),
            "cascade_id": int(cascade_id),
        },
        location_id=location_id,
        idempotency_key=f"manager_unconfirmed_shift_escalated:{cascade_id}",
    )


async def queue_manager_late_arrival_reported_notification(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    shift_id: int,
    worker_id: int,
    eta_minutes: int,
) -> dict:
    return await enqueue_notification(
        db,
        notification_type="manager_late_arrival_reported",
        payload={
            "location_id": int(location_id),
            "shift_id": int(shift_id),
            "worker_id": int(worker_id),
            "eta_minutes": int(eta_minutes),
        },
        location_id=location_id,
        idempotency_key=f"manager_late_arrival_reported:{shift_id}:{worker_id}:{eta_minutes}",
    )


async def queue_manager_late_arrival_coverage_started_notification(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    shift_id: int,
    worker_id: int,
    eta_minutes: int,
    cascade_id: int,
) -> dict:
    return await enqueue_notification(
        db,
        notification_type="manager_late_arrival_coverage_started",
        payload={
            "location_id": int(location_id),
            "shift_id": int(shift_id),
            "worker_id": int(worker_id),
            "eta_minutes": int(eta_minutes),
            "cascade_id": int(cascade_id),
        },
        location_id=location_id,
        idempotency_key=f"manager_late_arrival_coverage_started:{cascade_id}",
    )


async def queue_manager_missed_check_in_action_required_notification(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    shift_id: int,
    worker_id: int,
) -> dict:
    return await enqueue_notification(
        db,
        notification_type="manager_missed_check_in_action_required",
        payload={
            "location_id": int(location_id),
            "shift_id": int(shift_id),
            "worker_id": int(worker_id),
        },
        location_id=location_id,
        idempotency_key=f"manager_missed_check_in_action_required:{shift_id}:{worker_id}",
    )


async def queue_manager_missed_check_in_escalated_notification(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    shift_id: int,
    worker_id: int,
    cascade_id: int,
) -> dict:
    return await enqueue_notification(
        db,
        notification_type="manager_missed_check_in_escalated",
        payload={
            "location_id": int(location_id),
            "shift_id": int(shift_id),
            "worker_id": int(worker_id),
            "cascade_id": int(cascade_id),
        },
        location_id=location_id,
        idempotency_key=f"manager_missed_check_in_escalated:{cascade_id}",
    )


async def queue_manager_claim_approval_requested_notification(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    shift_id: int,
    worker_id: int,
    cascade_id: int,
) -> dict:
    return await enqueue_notification(
        db,
        notification_type="manager_claim_approval_requested",
        payload={
            "location_id": int(location_id),
            "shift_id": int(shift_id),
            "worker_id": int(worker_id),
            "cascade_id": int(cascade_id),
        },
        location_id=location_id,
        idempotency_key=f"manager_claim_approval_requested:{cascade_id}:{worker_id}",
    )


async def queue_worker_shift_confirmed_notification(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    worker_id: int,
    location_id: Optional[int] = None,
) -> dict:
    return await enqueue_notification(
        db,
        notification_type="worker_shift_confirmed",
        payload={
            "shift_id": int(shift_id),
            "worker_id": int(worker_id),
        },
        location_id=location_id,
        idempotency_key=f"worker_shift_confirmed:{shift_id}:{worker_id}",
    )


async def queue_worker_claim_pending_approval_notification(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    worker_id: int,
    location_id: Optional[int] = None,
) -> dict:
    return await enqueue_notification(
        db,
        notification_type="worker_claim_pending_approval",
        payload={
            "shift_id": int(shift_id),
            "worker_id": int(worker_id),
        },
        location_id=location_id,
        idempotency_key=f"worker_claim_pending_approval:{shift_id}:{worker_id}",
    )


async def queue_worker_claim_approved_notification(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    worker_id: int,
    location_id: Optional[int] = None,
) -> dict:
    return await enqueue_notification(
        db,
        notification_type="worker_claim_approved",
        payload={
            "shift_id": int(shift_id),
            "worker_id": int(worker_id),
        },
        location_id=location_id,
        idempotency_key=f"worker_claim_approved:{shift_id}:{worker_id}",
    )


async def queue_worker_claim_denied_notification(
    db: aiosqlite.Connection,
    *,
    shift_id: int,
    worker_id: int,
    location_id: Optional[int] = None,
) -> dict:
    return await enqueue_notification(
        db,
        notification_type="worker_claim_denied",
        payload={
            "shift_id": int(shift_id),
            "worker_id": int(worker_id),
        },
        location_id=location_id,
        idempotency_key=f"worker_claim_denied:{shift_id}:{worker_id}",
    )


async def process_notification_job(
    db: aiosqlite.Connection,
    *,
    notification_type: str,
    payload: dict,
) -> dict:
    from app.db import queries

    normalized_payload = dict(payload or {})

    if notification_type == "manager_notification":
        worker_id = int(normalized_payload.get("worker_id") or 0)
        await fire_manager_notification(
            db,
            int(normalized_payload["cascade_id"]),
            worker_id,
            bool(normalized_payload.get("filled")),
        )
        return {
            "status": "sent",
            "notification_type": notification_type,
            "cascade_id": int(normalized_payload["cascade_id"]),
            "worker_id": worker_id,
        }

    def _missing_context_result() -> dict:
        return {
            "status": "skipped_missing_context",
            "notification_type": notification_type,
            "payload": normalized_payload,
        }

    location_id = normalized_payload.get("location_id")
    shift_id = normalized_payload.get("shift_id")
    worker_id = normalized_payload.get("worker_id")

    location = await queries.get_location(db, int(location_id)) if location_id is not None else None
    shift = await queries.get_shift(db, int(shift_id)) if shift_id is not None else None
    worker = await queries.get_worker(db, int(worker_id)) if worker_id is not None else None

    if notification_type == "manager_callout_received":
        if not location or not shift or not worker:
            return _missing_context_result()
        message_sid = await fire_manager_callout_received_notification(
            db,
            location=location,
            shift=shift,
            worker=worker,
            cascade_id=int(normalized_payload["cascade_id"]),
        )
        return {"status": "sent" if message_sid else "delivery_unavailable", "notification_type": notification_type, "message_sid": message_sid}

    if notification_type == "manager_unconfirmed_shift_escalated":
        if not location or not shift or not worker:
            return _missing_context_result()
        message_sid = await fire_manager_unconfirmed_shift_escalated_notification(
            db,
            location=location,
            shift=shift,
            worker=worker,
            cascade_id=int(normalized_payload["cascade_id"]),
        )
        return {"status": "sent" if message_sid else "delivery_unavailable", "notification_type": notification_type, "message_sid": message_sid}

    if notification_type == "manager_late_arrival_reported":
        if not location or not shift or not worker:
            return _missing_context_result()
        message_sid = await fire_manager_late_arrival_reported_notification(
            db,
            location=location,
            shift=shift,
            worker=worker,
            eta_minutes=int(normalized_payload["eta_minutes"]),
        )
        return {"status": "sent" if message_sid else "delivery_unavailable", "notification_type": notification_type, "message_sid": message_sid}

    if notification_type == "manager_late_arrival_coverage_started":
        if not location or not shift or not worker:
            return _missing_context_result()
        message_sid = await fire_manager_late_arrival_coverage_started_notification(
            db,
            location=location,
            shift=shift,
            worker=worker,
            eta_minutes=int(normalized_payload["eta_minutes"]),
            cascade_id=int(normalized_payload["cascade_id"]),
        )
        return {"status": "sent" if message_sid else "delivery_unavailable", "notification_type": notification_type, "message_sid": message_sid}

    if notification_type == "manager_missed_check_in_action_required":
        if not location or not shift or not worker:
            return _missing_context_result()
        message_sid = await fire_manager_missed_check_in_action_required_notification(
            db,
            location=location,
            shift=shift,
            worker=worker,
        )
        return {"status": "sent" if message_sid else "delivery_unavailable", "notification_type": notification_type, "message_sid": message_sid}

    if notification_type == "manager_missed_check_in_escalated":
        if not location or not shift or not worker:
            return _missing_context_result()
        message_sid = await fire_manager_missed_check_in_escalated_notification(
            db,
            location=location,
            shift=shift,
            worker=worker,
            cascade_id=int(normalized_payload["cascade_id"]),
        )
        return {"status": "sent" if message_sid else "delivery_unavailable", "notification_type": notification_type, "message_sid": message_sid}

    if notification_type == "manager_claim_approval_requested":
        if not location or not shift or not worker:
            return _missing_context_result()
        message_sid = await fire_manager_claim_approval_requested_notification(
            db,
            location=location,
            shift=shift,
            worker=worker,
            cascade_id=int(normalized_payload["cascade_id"]),
        )
        return {"status": "sent" if message_sid else "delivery_unavailable", "notification_type": notification_type, "message_sid": message_sid}

    if notification_type == "worker_shift_confirmed":
        if not shift or not worker or not worker.get("phone"):
            return _missing_context_result()
        location = location or (await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None)
        message_sid = notify_worker_shift_confirmed(
            str(worker["phone"]),
            location_name=(location or {}).get("name") or "your location",
            role=str(shift.get("role") or "scheduled"),
            shift_date=str(shift["date"]),
            start_time=str(shift["start_time"]),
        )
        return {"status": "sent" if message_sid else "delivery_unavailable", "notification_type": notification_type, "message_sid": message_sid}

    if notification_type == "worker_claim_pending_approval":
        if not shift or not worker or not worker.get("phone"):
            return _missing_context_result()
        message_sid = notify_worker_claim_pending_approval(
            str(worker["phone"]),
            role=str(shift.get("role") or "scheduled"),
            shift_date=str(shift["date"]),
            start_time=str(shift["start_time"]),
            vacancy_kind=outreach_svc.vacancy_kind(shift),
        )
        return {"status": "sent" if message_sid else "delivery_unavailable", "notification_type": notification_type, "message_sid": message_sid}

    if notification_type == "worker_claim_approved":
        if not shift or not worker or not worker.get("phone"):
            return _missing_context_result()
        message_sid = notify_worker_claim_approved(
            str(worker["phone"]),
            role=str(shift.get("role") or "scheduled"),
            shift_date=str(shift["date"]),
            start_time=str(shift["start_time"]),
            vacancy_kind=outreach_svc.vacancy_kind(shift),
        )
        return {"status": "sent" if message_sid else "delivery_unavailable", "notification_type": notification_type, "message_sid": message_sid}

    if notification_type == "worker_claim_denied":
        if not shift or not worker or not worker.get("phone"):
            return _missing_context_result()
        message_sid = notify_worker_claim_denied(
            str(worker["phone"]),
            role=str(shift.get("role") or "scheduled"),
            shift_date=str(shift["date"]),
            start_time=str(shift["start_time"]),
            vacancy_kind=outreach_svc.vacancy_kind(shift),
        )
        return {"status": "sent" if message_sid else "delivery_unavailable", "notification_type": notification_type, "message_sid": message_sid}

    raise ValueError(f"Unsupported notification type {notification_type!r}")


async def fire_schedule_draft_ready_notification(
    db: aiosqlite.Connection,
    *,
    location: dict,
    schedule: dict,
    filled_shifts: int,
    total_shifts: int,
    review_items: list[str],
    review_link: str,
    import_job_id: Optional[int] = None,
    first_draft: bool = False,
) -> Optional[str]:
    manager_phone = location.get("manager_phone")
    if not manager_phone:
        return None
    message_sid = notify_schedule_draft_ready(
        manager_phone,
        location_name=location.get("name") or "your location",
        week_start_date=str(schedule["week_start_date"]),
        filled_shifts=filled_shifts,
        total_shifts=total_shifts,
        review_items=review_items,
        review_link=review_link,
        first_draft=first_draft,
    )
    await audit_svc.append(
        db,
        AuditAction.manager_notified,
        entity_type="schedule",
        entity_id=int(schedule["id"]),
        details={
            "event": "schedule_draft_ready",
            "manager_phone": manager_phone,
            "review_count": len(review_items),
            "review_link": review_link,
            "import_job_id": import_job_id,
            "message_sid": message_sid,
        },
    )
    return message_sid


async def fire_schedule_published_notification(
    db: aiosqlite.Connection,
    *,
    location: dict,
    schedule: dict,
    delivery_summary: dict,
    publish_diff: Optional[dict] = None,
    is_update: bool = False,
) -> Optional[str]:
    manager_phone = location.get("manager_phone")
    if not manager_phone:
        return None
    message_sid = notify_schedule_published(
        manager_phone,
        sms_sent=int(delivery_summary.get("sms_sent", 0) or 0),
        not_enrolled=int(delivery_summary.get("not_enrolled", 0) or 0),
        sms_failed=int(delivery_summary.get("sms_failed", 0) or 0),
        sms_removed_sent=int(delivery_summary.get("sms_removed_sent", 0) or 0),
        week_start_date=str(schedule.get("week_start_date") or ""),
        is_update=is_update,
        change_highlights=list((publish_diff or {}).get("highlights") or []),
    )
    await audit_svc.append(
        db,
        AuditAction.manager_notified,
        entity_type="schedule",
        entity_id=int(schedule["id"]),
        details={
            "event": "schedule_published",
            "manager_phone": manager_phone,
            "delivery_summary": delivery_summary,
            "publish_diff": publish_diff or {},
            "is_update": is_update,
            "message_sid": message_sid,
        },
    )
    return message_sid


async def fire_manager_callout_received_notification(
    db: aiosqlite.Connection,
    *,
    location: dict,
    shift: dict,
    worker: dict,
    cascade_id: int,
) -> Optional[str]:
    manager_phone = location.get("manager_phone")
    if not manager_phone:
        return None
    coverage_link = build_manager_dashboard_link(
        int(location["id"]),
        tab="coverage",
        shift_id=int(shift["id"]),
    )
    message_sid = notify_manager_callout_received(
        manager_phone,
        worker_name=worker.get("name") or "A worker",
        location_name=location.get("name") or "your location",
        role=shift.get("role") or "scheduled",
        shift_date=str(shift["date"]),
        start_time=str(shift["start_time"]),
        coverage_link=coverage_link,
    )
    await audit_svc.append(
        db,
        AuditAction.manager_notified,
        entity_type="shift",
        entity_id=int(shift["id"]),
        details={
            "event": "worker_callout_received",
            "worker_id": int(worker["id"]),
            "cascade_id": cascade_id,
            "manager_phone": manager_phone,
            "coverage_link": coverage_link,
            "message_sid": message_sid,
        },
    )
    return message_sid


async def fire_manager_unconfirmed_shift_escalated_notification(
    db: aiosqlite.Connection,
    *,
    location: dict,
    shift: dict,
    worker: dict,
    cascade_id: int,
) -> Optional[str]:
    manager_phone = location.get("manager_phone")
    if not manager_phone:
        return None
    coverage_link = build_manager_dashboard_link(
        int(location["id"]),
        tab="coverage",
        shift_id=int(shift["id"]),
    )
    message_sid = notify_manager_unconfirmed_shift_escalated(
        manager_phone,
        worker_name=worker.get("name") or "A worker",
        location_name=location.get("name") or "your location",
        role=shift.get("role") or "scheduled",
        shift_date=str(shift["date"]),
        start_time=str(shift["start_time"]),
        coverage_link=coverage_link,
    )
    await audit_svc.append(
        db,
        AuditAction.manager_notified,
        entity_type="shift",
        entity_id=int(shift["id"]),
        details={
            "event": "shift_unconfirmed_escalated",
            "worker_id": int(worker["id"]),
            "cascade_id": cascade_id,
            "manager_phone": manager_phone,
            "coverage_link": coverage_link,
            "message_sid": message_sid,
        },
    )
    return message_sid


async def fire_manager_late_arrival_reported_notification(
    db: aiosqlite.Connection,
    *,
    location: dict,
    shift: dict,
    worker: dict,
    eta_minutes: int,
) -> Optional[str]:
    manager_phone = location.get("manager_phone")
    if not manager_phone:
        return None
    shift_day = date.fromisoformat(str(shift["date"]))
    week_start = shift_day - timedelta(days=shift_day.weekday())
    review_link = build_manager_dashboard_link(
        int(location["id"]),
        tab="schedule",
        week_start=str(week_start),
    )
    message_sid = notify_manager_late_arrival_reported(
        manager_phone,
        worker_name=worker.get("name") or "A worker",
        location_name=location.get("name") or "your location",
        role=shift.get("role") or "scheduled",
        shift_date=str(shift["date"]),
        start_time=str(shift["start_time"]),
        eta_minutes=eta_minutes,
        review_link=review_link,
    )
    await audit_svc.append(
        db,
        AuditAction.manager_notified,
        entity_type="shift",
        entity_id=int(shift["id"]),
        details={
            "event": "worker_late_reported",
            "worker_id": int(worker["id"]),
            "eta_minutes": eta_minutes,
            "manager_phone": manager_phone,
            "review_link": review_link,
            "message_sid": message_sid,
        },
    )
    return message_sid


async def fire_manager_late_arrival_coverage_started_notification(
    db: aiosqlite.Connection,
    *,
    location: dict,
    shift: dict,
    worker: dict,
    eta_minutes: int,
    cascade_id: int,
) -> Optional[str]:
    manager_phone = location.get("manager_phone")
    if not manager_phone:
        return None
    coverage_link = build_manager_dashboard_link(
        int(location["id"]),
        tab="coverage",
        shift_id=int(shift["id"]),
    )
    message_sid = notify_manager_late_arrival_coverage_started(
        manager_phone,
        worker_name=worker.get("name") or "A worker",
        location_name=location.get("name") or "your location",
        role=shift.get("role") or "scheduled",
        shift_date=str(shift["date"]),
        start_time=str(shift["start_time"]),
        eta_minutes=eta_minutes,
        coverage_link=coverage_link,
    )
    await audit_svc.append(
        db,
        AuditAction.manager_notified,
        entity_type="shift",
        entity_id=int(shift["id"]),
        details={
            "event": "late_arrival_coverage_started",
            "worker_id": int(worker["id"]),
            "cascade_id": cascade_id,
            "eta_minutes": eta_minutes,
            "manager_phone": manager_phone,
            "coverage_link": coverage_link,
            "message_sid": message_sid,
        },
    )
    return message_sid


async def fire_manager_missed_check_in_escalated_notification(
    db: aiosqlite.Connection,
    *,
    location: dict,
    shift: dict,
    worker: dict,
    cascade_id: int,
) -> Optional[str]:
    manager_phone = location.get("manager_phone")
    if not manager_phone:
        return None
    coverage_link = build_manager_dashboard_link(
        int(location["id"]),
        tab="coverage",
        shift_id=int(shift["id"]),
    )
    message_sid = notify_manager_missed_check_in_escalated(
        manager_phone,
        worker_name=worker.get("name") or "A worker",
        location_name=location.get("name") or "your location",
        role=shift.get("role") or "scheduled",
        shift_date=str(shift["date"]),
        start_time=str(shift["start_time"]),
        coverage_link=coverage_link,
    )
    await audit_svc.append(
        db,
        AuditAction.manager_notified,
        entity_type="shift",
        entity_id=int(shift["id"]),
        details={
            "event": "shift_missed_check_in_escalated",
            "worker_id": int(worker["id"]),
            "cascade_id": cascade_id,
            "manager_phone": manager_phone,
            "coverage_link": coverage_link,
            "message_sid": message_sid,
        },
    )
    return message_sid


async def fire_manager_missed_check_in_action_required_notification(
    db: aiosqlite.Connection,
    *,
    location: dict,
    shift: dict,
    worker: dict,
) -> Optional[str]:
    manager_phone = location.get("manager_phone")
    if not manager_phone:
        return None
    shift_day = date.fromisoformat(str(shift["date"]))
    review_link = build_manager_dashboard_link(
        int(location["id"]),
        tab="schedule",
        week_start=str(shift_day - timedelta(days=shift_day.weekday())),
    )
    message_sid = notify_manager_missed_check_in_action_required(
        manager_phone,
        worker_name=worker.get("name") or "A worker",
        location_name=location.get("name") or "your location",
        role=shift.get("role") or "scheduled",
        shift_date=str(shift["date"]),
        start_time=str(shift["start_time"]),
        review_link=review_link,
    )
    await audit_svc.append(
        db,
        AuditAction.manager_notified,
        entity_type="shift",
        entity_id=int(shift["id"]),
        details={
            "event": "missed_check_in_action_required",
            "worker_id": int(worker["id"]),
            "manager_phone": manager_phone,
            "review_link": review_link,
            "message_sid": message_sid,
        },
    )
    return message_sid


async def fire_manager_claim_approval_requested_notification(
    db: aiosqlite.Connection,
    *,
    location: dict,
    shift: dict,
    worker: dict,
    cascade_id: int,
) -> Optional[str]:
    manager_phone = location.get("manager_phone")
    if not manager_phone:
        return None
    coverage_link = build_manager_dashboard_link(
        int(location["id"]),
        tab="coverage",
        shift_id=int(shift["id"]),
    )
    message_sid = notify_manager_claim_approval_requested(
        manager_phone,
        worker_name=worker.get("name") or "A worker",
        role=shift.get("role") or "scheduled",
        shift_date=str(shift["date"]),
        start_time=str(shift["start_time"]),
        coverage_link=coverage_link,
        vacancy_kind=outreach_svc.vacancy_kind(shift),
    )
    await audit_svc.append(
        db,
        AuditAction.manager_notified,
        entity_type="shift",
        entity_id=int(shift["id"]),
        details={
            "event": "coverage_claim_approval_requested",
            "worker_id": int(worker["id"]),
            "cascade_id": cascade_id,
            "manager_phone": manager_phone,
            "coverage_link": coverage_link,
            "message_sid": message_sid,
        },
    )
    return message_sid


async def fire_schedule_worker_delivery_notifications(
    db: aiosqlite.Connection,
    *,
    location: dict,
    schedule: dict,
    worker_shift_groups: dict[int, list[dict]],
    actor: str = "system",
    is_update: bool = False,
    worker_impact: Optional[dict] = None,
) -> dict:
    from app.db import queries

    impact_workers = list((worker_impact or {}).get("workers") or [])
    worker_impact_by_id = {
        int(item["worker_id"]): item
        for item in impact_workers
        if item.get("worker_id") is not None
    }
    if is_update and impact_workers:
        changed_worker_ids = {
            int(item["worker_id"])
            for item in impact_workers
            if item.get("worker_id") is not None
            and item.get("status") in {"updated_in_both", "added_to_target"}
        }
        removed_worker_ids = {
            int(item["worker_id"])
            for item in impact_workers
            if item.get("worker_id") is not None
            and item.get("status") == "removed_from_target"
        }
        unchanged_worker_ids = {
            int(item["worker_id"])
            for item in impact_workers
            if item.get("worker_id") is not None
            and item.get("status") == "unchanged"
        }
    else:
        changed_worker_ids = {int(worker_id) for worker_id in worker_shift_groups}
        removed_worker_ids: set[int] = set()
        unchanged_worker_ids: set[int] = set()

    summary = {
        "eligible_workers": len(changed_worker_ids) + len(removed_worker_ids),
        "sms_sent": 0,
        "sms_removed_sent": 0,
        "not_enrolled": 0,
        "sms_failed": 0,
        "changed_worker_count": len(changed_worker_ids),
        "removed_worker_count": len(removed_worker_ids),
        "unchanged_worker_count": len(unchanged_worker_ids),
        "skipped_unchanged_workers": len(unchanged_worker_ids),
    }
    event_name = "schedule_updated" if is_update else "schedule_published"

    for worker_id in sorted(changed_worker_ids):
        shifts = worker_shift_groups.get(worker_id) or []
        shift_ids = [int(shift["id"]) for shift in shifts]
        impact_item = worker_impact_by_id.get(worker_id) or {}
        worker = await queries.get_worker(db, worker_id)
        if worker is None or not worker.get("phone"):
            summary["sms_failed"] += 1
            await audit_svc.append(
                db,
                AuditAction.schedule_delivery_failed,
                actor=actor,
                entity_type="schedule",
                entity_id=int(schedule["id"]),
                details={
                    "worker_id": worker_id,
                    "shift_ids": shift_ids,
                    "channel": "sms",
                    "event": event_name,
                    "error": "worker_missing_or_unreachable",
                },
            )
            continue
        if worker.get("sms_consent_status") != "granted":
            summary["not_enrolled"] += 1
            continue

        try:
            if is_update and impact_item:
                change_type = impact_item.get("change_type")
                if change_type == "new_assignment":
                    message_sid = notify_worker_schedule_added(
                        worker["phone"],
                        worker_name=worker.get("name") or "there",
                        location_name=location.get("name") or "your location",
                        week_start_date=str(schedule["week_start_date"]),
                        added_lines=list(impact_item.get("added_lines") or impact_item.get("target_lines") or []),
                    )
                else:
                    message_sid = notify_worker_schedule_changed(
                        worker["phone"],
                        worker_name=worker.get("name") or "there",
                        location_name=location.get("name") or "your location",
                        week_start_date=str(schedule["week_start_date"]),
                        added_lines=list(impact_item.get("added_lines") or []),
                        removed_lines=list(impact_item.get("removed_lines") or []),
                        current_lines=list(impact_item.get("target_lines") or []),
                    )
            else:
                message_sid = notify_worker_schedule_published(
                    worker["phone"],
                    worker_name=worker.get("name") or "there",
                    location_name=location.get("name") or "your location",
                    week_start_date=str(schedule["week_start_date"]),
                    shifts=shifts,
                    is_update=is_update,
                )
        except Exception as exc:
            summary["sms_failed"] += 1
            await audit_svc.append(
                db,
                AuditAction.schedule_delivery_failed,
                actor=actor,
                entity_type="schedule",
                entity_id=int(schedule["id"]),
                details={
                    "worker_id": worker_id,
                    "shift_ids": shift_ids,
                    "channel": "sms",
                    "event": event_name,
                    "error": str(exc),
                },
            )
            continue

        if message_sid:
            summary["sms_sent"] += 1
            await audit_svc.append(
                db,
                AuditAction.schedule_delivery_sent,
                actor=actor,
                entity_type="schedule",
                entity_id=int(schedule["id"]),
                details={
                    "worker_id": worker_id,
                    "shift_ids": shift_ids,
                    "channel": "sms",
                    "event": event_name,
                    "change_type": impact_item.get("change_type"),
                    "message_sid": message_sid,
                },
            )
        else:
            summary["sms_failed"] += 1
            await audit_svc.append(
                db,
                AuditAction.schedule_delivery_failed,
                actor=actor,
                entity_type="schedule",
                entity_id=int(schedule["id"]),
                details={
                    "worker_id": worker_id,
                    "shift_ids": shift_ids,
                    "channel": "sms",
                    "event": event_name,
                    "error": "delivery_unavailable",
                },
            )

    for worker_id in sorted(removed_worker_ids):
        worker = await queries.get_worker(db, worker_id)
        impact_item = worker_impact_by_id.get(worker_id) or {}
        removed_lines = list(impact_item.get("removed_lines") or [])
        if worker is None or not worker.get("phone"):
            summary["sms_failed"] += 1
            await audit_svc.append(
                db,
                AuditAction.schedule_delivery_failed,
                actor=actor,
                entity_type="schedule",
                entity_id=int(schedule["id"]),
                details={
                    "worker_id": worker_id,
                    "shift_ids": sorted(impact_item.get("basis_shift_ids") or []),
                    "channel": "sms",
                    "event": "schedule_removed",
                    "error": "worker_missing_or_unreachable",
                },
            )
            continue
        if worker.get("sms_consent_status") != "granted":
            summary["not_enrolled"] += 1
            continue
        try:
            message_sid = notify_worker_schedule_removed(
                worker["phone"],
                worker_name=worker.get("name") or "there",
                location_name=location.get("name") or "your location",
                week_start_date=str(schedule["week_start_date"]),
                removed_lines=removed_lines,
            )
        except Exception as exc:
            summary["sms_failed"] += 1
            await audit_svc.append(
                db,
                AuditAction.schedule_delivery_failed,
                actor=actor,
                entity_type="schedule",
                entity_id=int(schedule["id"]),
                details={
                    "worker_id": worker_id,
                    "shift_ids": sorted(impact_item.get("basis_shift_ids") or []),
                    "channel": "sms",
                    "event": "schedule_removed",
                    "error": str(exc),
                },
            )
            continue
        if message_sid:
            summary["sms_removed_sent"] += 1
            await audit_svc.append(
                db,
                AuditAction.schedule_delivery_sent,
                actor=actor,
                entity_type="schedule",
                entity_id=int(schedule["id"]),
                details={
                    "worker_id": worker_id,
                    "shift_ids": sorted(impact_item.get("basis_shift_ids") or []),
                    "channel": "sms",
                    "event": "schedule_removed",
                    "message_sid": message_sid,
                },
            )
        else:
            summary["sms_failed"] += 1
            await audit_svc.append(
                db,
                AuditAction.schedule_delivery_failed,
                actor=actor,
                entity_type="schedule",
                entity_id=int(schedule["id"]),
                details={
                    "worker_id": worker_id,
                    "shift_ids": sorted(impact_item.get("basis_shift_ids") or []),
                    "channel": "sms",
                    "event": "schedule_removed",
                    "error": "delivery_unavailable",
                },
            )

    return summary


async def fire_manager_notification(
    db: aiosqlite.Connection,
    cascade_id: int,
    worker_id: int,
    filled: bool,
) -> None:
    """Shared helper: notify manager of fill or exhaustion. Used by retell_hooks and twilio_hooks."""
    from app.db.queries import get_cascade, get_shift, get_worker, get_location

    cascade = await get_cascade(db, cascade_id)
    if not cascade:
        return
    shift = await get_shift(db, cascade["shift_id"])
    if not shift:
        return
    location = await get_location(db, shift["location_id"])
    if not location or not location.get("manager_phone"):
        return

    if filled:
        worker = await get_worker(db, worker_id)
        notify_shift_filled(
            manager_phone=location["manager_phone"],
            worker_name=worker["name"] if worker else "a worker",
            role=shift["role"],
            date=shift["date"],
            start_time=shift["start_time"],
            fill_tier=shift.get("fill_tier") or "tier1_internal",
        )
    else:
        notify_cascade_exhausted(
            manager_phone=location["manager_phone"],
            role=shift["role"],
            date=shift["date"],
            start_time=shift["start_time"],
        )

    await audit_svc.append(
        db,
        AuditAction.manager_notified,
        entity_type="shift",
        entity_id=shift["id"],
        details={"filled": filled, "manager_phone": location["manager_phone"]},
    )
