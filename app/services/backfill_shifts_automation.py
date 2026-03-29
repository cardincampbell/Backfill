from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import aiosqlite

from app.db import queries
from app.models.audit import AuditAction
from app.services import audit as audit_svc
from app.services import backfill_shifts as core
from app.services import cascade as cascade_svc
from app.services import notifications as notifications_svc
from app.services import outreach as outreach_svc
from app.services import shift_manager


async def send_shift_confirmation_requests(
    db: aiosqlite.Connection,
    *,
    within_minutes: int = 120,
    location_id: Optional[int] = None,
    actor: str = "system",
) -> dict:
    shifts = await queries.list_shifts_needing_confirmation_request(
        db,
        within_minutes=within_minutes,
        location_id=location_id,
    )
    sent_shift_ids: list[int] = []
    skipped_shift_ids: list[int] = []
    failed_shift_ids: list[int] = []
    for shift in shifts:
        if not shift.get("assigned_worker_id") or not shift.get("assigned_worker_phone"):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        location = await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None
        if location is not None and not core._uses_backfill_shifts(location):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        now_iso = datetime.utcnow().isoformat()
        try:
            message_sid = notifications_svc.notify_worker_shift_confirmation_request(
                str(shift["assigned_worker_phone"]),
                worker_name=str(shift.get("assigned_worker_name") or "there"),
                location_name=str(shift.get("location_name") or "your location"),
                role=str(shift["role"]),
                shift_date=str(shift["date"]),
                start_time=str(shift["start_time"]),
            )
        except Exception as exc:
            failed_shift_ids.append(int(shift["id"]))
            await audit_svc.append(
                db,
                AuditAction.shift_confirmation_requested,
                actor=actor,
                entity_type="shift",
                entity_id=int(shift["id"]),
                details={
                    "worker_id": int(shift["assigned_worker_id"]),
                    "status": "failed",
                    "error": str(exc),
                },
            )
            continue
        if not message_sid:
            failed_shift_ids.append(int(shift["id"]))
            await audit_svc.append(
                db,
                AuditAction.shift_confirmation_requested,
                actor=actor,
                entity_type="shift",
                entity_id=int(shift["id"]),
                details={
                    "worker_id": int(shift["assigned_worker_id"]),
                    "status": "failed",
                    "error": "delivery_unavailable",
                },
            )
            continue

        await queries.update_shift(
            db,
            int(shift["id"]),
            {
                "confirmation_requested_at": now_iso,
                "worker_confirmed_at": None,
                "worker_declined_at": None,
            },
        )
        sent_shift_ids.append(int(shift["id"]))
        await audit_svc.append(
            db,
            AuditAction.shift_confirmation_requested,
            actor=actor,
            entity_type="shift",
            entity_id=int(shift["id"]),
            details={
                "worker_id": int(shift["assigned_worker_id"]),
                "status": "sent",
                "message_sid": message_sid,
            },
        )

    return {
        "within_minutes": within_minutes,
        "sent_count": len(sent_shift_ids),
        "sent_shift_ids": sent_shift_ids,
        "skipped_shift_ids": skipped_shift_ids,
        "failed_shift_ids": failed_shift_ids,
    }


async def send_shift_check_in_requests(
    db: aiosqlite.Connection,
    *,
    within_minutes: int = 15,
    location_id: Optional[int] = None,
    actor: str = "system",
) -> dict:
    shifts = await queries.list_shifts_needing_check_in_request(
        db,
        within_minutes=within_minutes,
        location_id=location_id,
    )
    sent_shift_ids: list[int] = []
    skipped_shift_ids: list[int] = []
    failed_shift_ids: list[int] = []
    for shift in shifts:
        if not shift.get("assigned_worker_id") or not shift.get("assigned_worker_phone"):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        location = await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None
        if location is not None and not core._uses_backfill_shifts(location):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        now_iso = datetime.utcnow().isoformat()
        try:
            message_sid = notifications_svc.notify_worker_shift_check_in_request(
                str(shift["assigned_worker_phone"]),
                worker_name=str(shift.get("assigned_worker_name") or "there"),
                location_name=str(shift.get("location_name") or "your location"),
                role=str(shift["role"]),
                shift_date=str(shift["date"]),
                start_time=str(shift["start_time"]),
            )
        except Exception as exc:
            failed_shift_ids.append(int(shift["id"]))
            await audit_svc.append(
                db,
                AuditAction.shift_check_in_requested,
                actor=actor,
                entity_type="shift",
                entity_id=int(shift["id"]),
                details={
                    "worker_id": int(shift["assigned_worker_id"]),
                    "status": "failed",
                    "error": str(exc),
                },
            )
            continue
        if not message_sid:
            failed_shift_ids.append(int(shift["id"]))
            await audit_svc.append(
                db,
                AuditAction.shift_check_in_requested,
                actor=actor,
                entity_type="shift",
                entity_id=int(shift["id"]),
                details={
                    "worker_id": int(shift["assigned_worker_id"]),
                    "status": "failed",
                    "error": "delivery_unavailable",
                },
            )
            continue

        await queries.update_shift(
            db,
            int(shift["id"]),
            {
                "check_in_requested_at": now_iso,
                "checked_in_at": None,
                "late_reported_at": None,
                "late_eta_minutes": None,
                "check_in_escalated_at": None,
                "attendance_action_state": None,
                "attendance_action_updated_at": now_iso,
            },
        )
        sent_shift_ids.append(int(shift["id"]))
        await audit_svc.append(
            db,
            AuditAction.shift_check_in_requested,
            actor=actor,
            entity_type="shift",
            entity_id=int(shift["id"]),
            details={
                "worker_id": int(shift["assigned_worker_id"]),
                "status": "sent",
                "message_sid": message_sid,
            },
        )

    return {
        "within_minutes": within_minutes,
        "sent_count": len(sent_shift_ids),
        "sent_shift_ids": sent_shift_ids,
        "skipped_shift_ids": skipped_shift_ids,
        "failed_shift_ids": failed_shift_ids,
    }


def _should_escalate_missed_check_in(
    shift: dict,
    *,
    grace_minutes: int,
    now: datetime,
) -> bool:
    if shift.get("checked_in_at") or shift.get("check_in_escalated_at"):
        return False
    shift_start = core._shift_start_datetime(shift)
    if shift_start is None:
        return False
    if shift.get("late_reported_at") and shift.get("late_eta_minutes") is not None:
        return now >= shift_start + timedelta(minutes=int(shift["late_eta_minutes"]))
    return now >= shift_start + timedelta(minutes=grace_minutes)


async def escalate_missed_check_ins(
    db: aiosqlite.Connection,
    *,
    grace_minutes: int = 10,
    location_id: Optional[int] = None,
    actor: str = "system",
) -> dict:
    now = datetime.utcnow()
    shifts = await queries.list_shifts_missing_check_in(
        db,
        location_id=location_id,
    )
    escalated_shift_ids: list[int] = []
    skipped_shift_ids: list[int] = []
    for shift in shifts:
        if not _should_escalate_missed_check_in(shift, grace_minutes=grace_minutes, now=now):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        if not shift.get("assigned_worker_id"):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        location = await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None
        if location is not None and not core._uses_backfill_shifts(location):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        worker = await queries.get_worker(db, int(shift["assigned_worker_id"]))
        if worker is None:
            skipped_shift_ids.append(int(shift["id"]))
            continue

        escalated_at = datetime.utcnow().isoformat()
        await queries.update_shift(
            db,
            int(shift["id"]),
            {
                "check_in_escalated_at": escalated_at,
                "escalated_from_worker_id": int(worker["id"]),
                "attendance_action_state": None,
                "attendance_action_updated_at": escalated_at,
            },
        )
        await audit_svc.append(
            db,
            AuditAction.shift_check_in_escalated,
            actor=actor,
            entity_type="shift",
            entity_id=int(shift["id"]),
            details={
                "worker_id": int(worker["id"]),
                "reason": "missed_check_in_after_start",
                "grace_minutes": grace_minutes,
            },
        )
        refreshed_shift = await queries.get_shift(db, int(shift["id"]))
        missed_policy = (location or {}).get("missed_check_in_policy") or "start_coverage"
        if location is not None and refreshed_shift is not None and missed_policy == "manager_action":
            await notifications_svc.queue_manager_missed_check_in_action_required_notification(
                db,
                location_id=int(location["id"]),
                shift_id=int(refreshed_shift["id"]),
                worker_id=int(worker["id"]),
            )
            escalated_shift_ids.append(int(shift["id"]))
            continue

        await core._start_coverage_for_attendance_issue(
            db,
            shift=refreshed_shift or shift,
            worker=worker,
            location=location or {},
            issue_type="missed_check_in",
            actor=actor,
            notify_manager=location is not None and refreshed_shift is not None,
        )
        escalated_shift_ids.append(int(shift["id"]))

    return {
        "grace_minutes": grace_minutes,
        "escalated_count": len(escalated_shift_ids),
        "escalated_shift_ids": escalated_shift_ids,
        "skipped_shift_ids": skipped_shift_ids,
    }


async def escalate_unconfirmed_shifts(
    db: aiosqlite.Connection,
    *,
    within_minutes: int = 15,
    location_id: Optional[int] = None,
    actor: str = "system",
) -> dict:
    shifts = await queries.list_unconfirmed_shifts_for_escalation(
        db,
        within_minutes=within_minutes,
        location_id=location_id,
    )
    escalated_shift_ids: list[int] = []
    skipped_shift_ids: list[int] = []
    for shift in shifts:
        if not shift.get("assigned_worker_id"):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        location = await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None
        if location is not None and not core._uses_backfill_shifts(location):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        worker = await queries.get_worker(db, int(shift["assigned_worker_id"]))
        if worker is None:
            skipped_shift_ids.append(int(shift["id"]))
            continue

        escalated_at = datetime.utcnow().isoformat()
        await queries.update_shift(
            db,
            int(shift["id"]),
            {
                "confirmation_escalated_at": escalated_at,
                "escalated_from_worker_id": int(worker["id"]),
            },
        )
        await audit_svc.append(
            db,
            AuditAction.shift_confirmation_escalated,
            actor=actor,
            entity_type="shift",
            entity_id=int(shift["id"]),
            details={
                "worker_id": int(worker["id"]),
                "reason": "unconfirmed_close_to_start",
            },
        )
        cascade = await shift_manager.create_vacancy(
            db,
            shift_id=int(shift["id"]),
            called_out_by_worker_id=None,
            actor=actor,
        )
        await cascade_svc.advance(db, int(cascade["id"]))
        refreshed_shift = await queries.get_shift(db, int(shift["id"]))
        if location is not None and refreshed_shift is not None:
            await notifications_svc.queue_manager_unconfirmed_shift_escalated_notification(
                db,
                location_id=int(location["id"]),
                shift_id=int(refreshed_shift["id"]),
                worker_id=int(worker["id"]),
                cascade_id=int(cascade["id"]),
            )
        escalated_shift_ids.append(int(shift["id"]))

    return {
        "within_minutes": within_minutes,
        "escalated_count": len(escalated_shift_ids),
        "escalated_shift_ids": escalated_shift_ids,
        "skipped_shift_ids": skipped_shift_ids,
    }


async def send_shift_reminders(
    db: aiosqlite.Connection,
    *,
    within_minutes: int = 30,
    location_id: Optional[int] = None,
    actor: str = "system",
) -> dict:
    from app.services.messaging import send_sms

    shifts = await queries.list_filled_shifts_needing_reminder(
        db,
        within_minutes=within_minutes,
        location_id=location_id,
    )
    sent_shift_ids: list[int] = []
    skipped_shift_ids: list[int] = []
    for shift in shifts:
        worker_id = shift.get("reminder_worker_id") or shift.get("filled_by")
        if not worker_id:
            skipped_shift_ids.append(int(shift["id"]))
            continue
        worker = await queries.get_worker(db, int(worker_id))
        if worker is None or not worker.get("phone"):
            skipped_shift_ids.append(int(shift["id"]))
            continue
        if worker.get("sms_consent_status") != "granted":
            skipped_shift_ids.append(int(shift["id"]))
            continue
        location = await queries.get_location(db, int(shift["location_id"])) if shift.get("location_id") else None
        message_sid = send_sms(
            worker["phone"],
            outreach_svc.build_reminder_sms(worker, shift, location),
        )
        await queries.mark_reminder_sent(db, int(shift["id"]))
        await audit_svc.append(
            db,
            AuditAction.outreach_sent,
            actor=actor,
            entity_type="shift",
            entity_id=int(shift["id"]),
            details={
                "event": "shift_reminder_sent",
                "channel": "sms_reminder",
                "worker_id": int(worker_id),
                "message_sid": message_sid,
            },
        )
        sent_shift_ids.append(int(shift["id"]))
    return {
        "location_id": location_id,
        "within_minutes": within_minutes,
        "reminders_sent": len(sent_shift_ids),
        "shift_ids": sent_shift_ids,
        "skipped_shift_ids": skipped_shift_ids,
    }


async def send_manager_digest(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    lookahead_hours: int = 24,
    include_empty: bool = True,
    actor: str = "system",
) -> dict:
    location = await queries.get_location(db, location_id)
    if location is None:
        raise ValueError("Location not found")
    if not location.get("manager_phone"):
        raise ValueError("Location manager phone is missing")

    now = datetime.utcnow()
    window_end = now + timedelta(hours=lookahead_hours)
    shifts = await queries.list_shifts(db, location_id=location_id)

    upcoming: list[tuple[dict, dict | None, dict | None]] = []
    for shift in shifts:
        assignment = await queries.get_shift_assignment_with_worker(db, int(shift["id"]))
        cascade = await queries.get_active_cascade_for_shift(db, int(shift["id"]))
        if not core._should_include_in_manager_digest(
            shift,
            assignment=assignment,
            cascade=cascade,
            now=now,
            window_end=window_end,
        ):
            continue
        upcoming.append((shift, assignment, cascade))

    scheduled_shifts = len(upcoming)
    open_shifts = 0
    active_coverage = 0
    attendance_issues = 0
    late_arrivals = 0
    late_arrivals_awaiting_decision = 0
    missed_check_ins = 0
    missed_check_ins_awaiting_decision = 0
    missed_check_ins_escalated = 0
    pending_fill_approvals = 0
    pending_agency_approvals = 0
    pending_attendance_reviews = 0

    for shift, assignment, cascade in upcoming:
        assignment_payload = core._serialize_assignment_payload(assignment, shift=shift)
        attendance_payload = core._serialize_attendance_payload(shift, assignment)
        attendance_summary = core._summarize_attendance_exception(
            attendance_payload,
            late_policy=(location.get("late_arrival_policy") or "wait"),
            missed_policy=(location.get("missed_check_in_policy") or "start_coverage"),
        )
        is_open = (
            shift.get("status") in {"vacant", "filling", "unfilled"}
            or assignment_payload.get("worker_id") is None
        )
        if is_open:
            open_shifts += 1
        attendance_issues += attendance_summary["attendance_issues"]
        late_arrivals += attendance_summary["late_arrivals"]
        late_arrivals_awaiting_decision += attendance_summary["late_arrivals_awaiting_decision"]
        missed_check_ins += attendance_summary["missed_check_ins"]
        missed_check_ins_awaiting_decision += attendance_summary["missed_check_ins_awaiting_decision"]
        missed_check_ins_escalated += attendance_summary["missed_check_ins_escalated"]
        pending_attendance_reviews += (
            attendance_summary["late_arrivals_awaiting_decision"]
            + attendance_summary["missed_check_ins_awaiting_decision"]
        )
        if cascade is not None:
            active_coverage += 1
            if cascade.get("pending_claim_worker_id") is not None:
                pending_fill_approvals += 1
            elif int(cascade.get("current_tier") or 1) >= 3 and not cascade.get("manager_approved_tier3"):
                pending_agency_approvals += 1

    pending_actions = pending_fill_approvals + pending_agency_approvals + pending_attendance_reviews
    if not include_empty and scheduled_shifts <= 0 and pending_actions <= 0 and active_coverage <= 0 and open_shifts <= 0:
        return {
            "location_id": location_id,
            "lookahead_hours": lookahead_hours,
            "status": "skipped_no_activity",
            "summary": {
                "scheduled_shifts": scheduled_shifts,
                "open_shifts": open_shifts,
                "active_coverage": active_coverage,
                "attendance_issues": attendance_issues,
                "late_arrivals": late_arrivals,
                "late_arrivals_awaiting_decision": late_arrivals_awaiting_decision,
                "missed_check_ins": missed_check_ins,
                "missed_check_ins_awaiting_decision": missed_check_ins_awaiting_decision,
                "missed_check_ins_escalated": missed_check_ins_escalated,
                "pending_actions": pending_actions,
                "pending_fill_approvals": pending_fill_approvals,
                "pending_agency_approvals": pending_agency_approvals,
                "pending_attendance_reviews": pending_attendance_reviews,
            },
            "review_link": None,
            "message_sid": None,
        }
    relevant_day = (
        min((core._shift_start_datetime(shift) or now for shift, _, _ in upcoming), default=now).date()
    )
    review_tab = "coverage" if pending_actions or open_shifts or active_coverage else "schedule"
    review_link = notifications_svc.build_manager_dashboard_link(
        location_id,
        tab=review_tab,
        week_start=core._week_start_for(relevant_day).isoformat(),
    )
    message_sid = notifications_svc.notify_manager_operational_digest(
        location["manager_phone"],
        location_name=location.get("name") or "your location",
        lookahead_hours=lookahead_hours,
        scheduled_shifts=scheduled_shifts,
        open_shifts=open_shifts,
        active_coverage=active_coverage,
        attendance_issues=attendance_issues,
        late_arrivals=late_arrivals,
        late_arrivals_awaiting_decision=late_arrivals_awaiting_decision,
        missed_check_ins=missed_check_ins,
        missed_check_ins_awaiting_decision=missed_check_ins_awaiting_decision,
        missed_check_ins_escalated=missed_check_ins_escalated,
        pending_actions=pending_actions,
        review_link=review_link,
    )
    summary = {
        "scheduled_shifts": scheduled_shifts,
        "open_shifts": open_shifts,
        "active_coverage": active_coverage,
        "attendance_issues": attendance_issues,
        "late_arrivals": late_arrivals,
        "late_arrivals_awaiting_decision": late_arrivals_awaiting_decision,
        "missed_check_ins": missed_check_ins,
        "missed_check_ins_awaiting_decision": missed_check_ins_awaiting_decision,
        "missed_check_ins_escalated": missed_check_ins_escalated,
        "pending_actions": pending_actions,
        "pending_fill_approvals": pending_fill_approvals,
        "pending_agency_approvals": pending_agency_approvals,
        "pending_attendance_reviews": pending_attendance_reviews,
    }
    await audit_svc.append(
        db,
        AuditAction.manager_notified,
        actor=actor,
        entity_type="location",
        entity_id=location_id,
        details={
            "event": "manager_operational_digest",
            "lookahead_hours": lookahead_hours,
            "summary": summary,
            "review_link": review_link,
            "message_sid": message_sid,
        },
    )
    await queries.update_location(
        db,
        location_id,
        {"last_manager_digest_sent_at": datetime.utcnow().isoformat()},
    )
    return {
        "location_id": location_id,
        "lookahead_hours": lookahead_hours,
        "status": "sent",
        "summary": summary,
        "review_link": review_link,
        "message_sid": message_sid,
    }


async def send_due_manager_digests(
    db: aiosqlite.Connection,
    *,
    lookahead_hours: int = 24,
    cooldown_hours: int = 12,
    location_id: Optional[int] = None,
    include_empty: bool = False,
    actor: str = "system",
) -> dict:
    if location_id is not None:
        target = await queries.get_location(db, location_id)
        if target is None:
            raise ValueError("Location not found")
        locations = [target]
    else:
        locations = await queries.list_locations(db)

    now = datetime.utcnow()
    sent: list[int] = []
    skipped_recent: list[int] = []
    skipped_no_activity: list[int] = []
    skipped_ineligible: list[int] = []

    for location in locations:
        current_location_id = int(location["id"])
        if not core._uses_backfill_shifts(location) or not location.get("manager_phone"):
            skipped_ineligible.append(current_location_id)
            continue
        last_digest_at = location.get("last_manager_digest_sent_at")
        if cooldown_hours > 0 and last_digest_at:
            try:
                last_sent = datetime.fromisoformat(str(last_digest_at))
                if now - last_sent < timedelta(hours=cooldown_hours):
                    skipped_recent.append(current_location_id)
                    continue
            except ValueError:
                pass

        result = await send_manager_digest(
            db,
            location_id=current_location_id,
            lookahead_hours=lookahead_hours,
            include_empty=include_empty,
            actor=actor,
        )
        if result.get("status") == "skipped_no_activity":
            skipped_no_activity.append(current_location_id)
            continue
        sent.append(current_location_id)

    return {
        "lookahead_hours": lookahead_hours,
        "cooldown_hours": cooldown_hours,
        "sent_count": len(sent),
        "sent_location_ids": sent,
        "skipped_recent_location_ids": skipped_recent,
        "skipped_no_activity_location_ids": skipped_no_activity,
        "skipped_ineligible_location_ids": skipped_ineligible,
    }


async def run_due_backfill_shifts_automation(
    db: aiosqlite.Connection,
    *,
    location_id: Optional[int] = None,
    confirmation_within_minutes: int = 120,
    unconfirmed_within_minutes: int = 15,
    check_in_within_minutes: int = 15,
    missed_check_in_grace_minutes: int = 10,
    reminder_within_minutes: int = 30,
    digest_lookahead_hours: int = 24,
    digest_cooldown_hours: int = 12,
    include_empty_digests: bool = False,
    run_confirmations: bool = True,
    run_unconfirmed_escalations: bool = True,
    run_check_ins: bool = True,
    run_missed_check_in_escalations: bool = True,
    run_reminders: bool = True,
    run_manager_digests: bool = True,
    actor: str = "system",
) -> dict:
    ran_at = datetime.utcnow().isoformat()
    steps: dict[str, dict] = {}

    async def _run_step(name: str, enabled: bool, func, **kwargs) -> None:
        if not enabled:
            steps[name] = {"status": "skipped"}
            return
        try:
            steps[name] = {
                "status": "completed",
                "result": await func(db, actor=actor, location_id=location_id, **kwargs),
            }
        except Exception as exc:
            steps[name] = {
                "status": "failed",
                "error": str(exc),
            }

    await _run_step(
        "unconfirmed_escalations",
        run_unconfirmed_escalations,
        escalate_unconfirmed_shifts,
        within_minutes=unconfirmed_within_minutes,
    )
    await _run_step(
        "missed_check_in_escalations",
        run_missed_check_in_escalations,
        escalate_missed_check_ins,
        grace_minutes=missed_check_in_grace_minutes,
    )
    await _run_step(
        "confirmation_requests",
        run_confirmations,
        send_shift_confirmation_requests,
        within_minutes=confirmation_within_minutes,
    )
    await _run_step(
        "check_in_requests",
        run_check_ins,
        send_shift_check_in_requests,
        within_minutes=check_in_within_minutes,
    )
    await _run_step(
        "shift_reminders",
        run_reminders,
        send_shift_reminders,
        within_minutes=reminder_within_minutes,
    )

    if run_manager_digests:
        try:
            steps["manager_digests"] = {
                "status": "completed",
                "result": await send_due_manager_digests(
                    db,
                    lookahead_hours=digest_lookahead_hours,
                    cooldown_hours=digest_cooldown_hours,
                    location_id=location_id,
                    include_empty=include_empty_digests,
                    actor=actor,
                ),
            }
        except Exception as exc:
            steps["manager_digests"] = {
                "status": "failed",
                "error": str(exc),
            }
    else:
        steps["manager_digests"] = {"status": "skipped"}

    return {
        "ran_at": ran_at,
        "location_id": location_id,
        "steps": steps,
        "summary": {
            "completed_steps": sum(1 for step in steps.values() if step.get("status") == "completed"),
            "failed_steps": sum(1 for step in steps.values() if step.get("status") == "failed"),
            "skipped_steps": sum(1 for step in steps.values() if step.get("status") == "skipped"),
        },
    }
