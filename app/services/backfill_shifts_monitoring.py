from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite

from app.db import queries
from app.models.audit import AuditAction
from app.services import notifications as notifications_svc


def _trim_text(value: object | None) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _latest_audit_timestamp(rows: list[dict], predicate) -> str | None:
    timestamps = [str(row.get("timestamp")) for row in rows if row.get("timestamp") and predicate(row)]
    return max(timestamps) if timestamps else None


def _audit_action_name(value: object | None) -> str:
    text = str(value or "")
    if "." in text:
        return text.rsplit(".", 1)[-1]
    return text


async def _collect_location_audit_rows(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    since: str | None = None,
    per_entity_limit: int = 500,
    final_limit: int | None = None,
    workers: list[dict] | None = None,
    schedules: list[dict] | None = None,
    shifts: list[dict] | None = None,
) -> list[dict]:
    audit_rows_by_id: dict[int, dict] = {}

    async def _collect_entity_audit(entity_type: str, entity_id: int) -> None:
        for row in await queries.list_audit_log(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            limit=per_entity_limit,
        ):
            if row.get("id") is not None:
                audit_rows_by_id[int(row["id"])] = row

    await _collect_entity_audit("location", location_id)
    for worker in workers or await queries.list_workers(db, location_id=location_id):
        await _collect_entity_audit("worker", int(worker["id"]))
    for schedule in schedules or await queries.list_schedules_for_location(db, location_id):
        await _collect_entity_audit("schedule", int(schedule["id"]))
    for shift in shifts or await queries.list_shifts(db, location_id=location_id):
        await _collect_entity_audit("shift", int(shift["id"]))

    rows = list(audit_rows_by_id.values())
    if since is not None:
        rows = [
            row
            for row in rows
            if row.get("timestamp") and str(row["timestamp"]) >= since
        ]
    rows.sort(
        key=lambda row: (str(row.get("timestamp") or ""), int(row.get("id") or 0)),
        reverse=True,
    )
    if final_limit is not None:
        rows = rows[:final_limit]
    return rows


def _activity_category_for(*, action_name: str, event_name: str) -> str:
    if event_name in {"worker_callout_received", "agency_routing_approved"}:
        return "coverage"
    if event_name in {"schedule_draft_ready", "schedule_published", "schedule_updated", "schedule_removed"}:
        return "scheduling"
    if event_name in {"manager_operational_digest", "publish_preview_generated"}:
        return "messaging"

    if action_name in {
        AuditAction.worker_invited.value,
        AuditAction.consent_granted.value,
        AuditAction.consent_revoked.value,
        AuditAction.opt_out_received.value,
        AuditAction.worker_created.value,
        AuditAction.worker_deactivated.value,
        AuditAction.worker_reactivated.value,
        AuditAction.worker_transferred.value,
    }:
        return "roster"
    if action_name in {
        AuditAction.import_job_created.value,
        AuditAction.import_job_committed.value,
    }:
        return "import"
    if action_name in {
        AuditAction.schedule_created.value,
        AuditAction.schedule_template_created.value,
        AuditAction.schedule_template_applied.value,
        AuditAction.schedule_template_updated.value,
        AuditAction.schedule_template_deleted.value,
        AuditAction.schedule_published.value,
        AuditAction.schedule_amended.value,
        AuditAction.schedule_recalled.value,
        AuditAction.schedule_archived.value,
        AuditAction.shift_assignment_updated.value,
        AuditAction.shift_updated.value,
        AuditAction.shift_deleted.value,
        AuditAction.open_shift_offer_cancelled.value,
        AuditAction.open_shift_closed.value,
        AuditAction.open_shift_reopened.value,
    }:
        return "scheduling"
    if action_name in {
        AuditAction.schedule_delivery_sent.value,
        AuditAction.schedule_delivery_failed.value,
        AuditAction.manager_notified.value,
    }:
        return "messaging"
    if action_name in {
        AuditAction.shift_confirmation_requested.value,
        AuditAction.shift_confirmation_received.value,
        AuditAction.shift_confirmation_escalated.value,
        AuditAction.shift_check_in_requested.value,
        AuditAction.shift_check_in_received.value,
        AuditAction.shift_check_in_escalated.value,
        AuditAction.shift_attendance_actioned.value,
    }:
        return "attendance"
    return "coverage"


def _humanize_activity_name(value: str) -> str:
    return value.replace("_", " ").strip().title()


async def _build_location_activity_item(
    db: aiosqlite.Connection,
    row: dict,
    *,
    worker_cache: dict[int, dict],
    shift_cache: dict[int, dict],
    schedule_cache: dict[int, dict],
) -> dict:
    details = dict(row.get("details") or {})
    action_name = _audit_action_name(row.get("action"))
    event_name = str(details.get("event") or "").strip()
    activity_type = event_name or action_name
    category = _activity_category_for(action_name=action_name, event_name=event_name)
    entity_type = str(row.get("entity_type") or "")
    entity_id = int(row["entity_id"]) if row.get("entity_id") is not None else None

    async def _get_worker_name(worker_id: int | None) -> str | None:
        if worker_id is None:
            return None
        if worker_id not in worker_cache:
            worker_cache[worker_id] = await queries.get_worker(db, worker_id) or {}
        return worker_cache[worker_id].get("name") or f"Worker #{worker_id}"

    async def _get_shift(shift_id: int | None) -> dict | None:
        if shift_id is None:
            return None
        if shift_id not in shift_cache:
            shift_cache[shift_id] = await queries.get_shift(db, shift_id) or {}
        return shift_cache[shift_id] or None

    async def _get_schedule(schedule_id: int | None) -> dict | None:
        if schedule_id is None:
            return None
        if schedule_id not in schedule_cache:
            schedule_cache[schedule_id] = await queries.get_schedule(db, schedule_id) or {}
        return schedule_cache[schedule_id] or None

    title = _humanize_activity_name(activity_type)
    summary = None
    review_link = str(
        details.get("review_link")
        or details.get("coverage_link")
        or ""
    ).strip() or None

    if activity_type == AuditAction.worker_invited.value:
        worker_name = await _get_worker_name(entity_id if entity_type == "worker" else details.get("worker_id"))
        title = "Enrollment invite sent"
        summary = f"{worker_name or 'A worker'} was invited to enroll by SMS."
    elif activity_type == AuditAction.consent_granted.value:
        worker_name = await _get_worker_name(entity_id if entity_type == "worker" else details.get("worker_id"))
        title = "Worker enrolled"
        summary = f"{worker_name or 'A worker'} granted Backfill SMS consent."
    elif activity_type == AuditAction.consent_revoked.value:
        worker_name = await _get_worker_name(entity_id if entity_type == "worker" else details.get("worker_id"))
        title = "Worker opted out"
        summary = f"{worker_name or 'A worker'} revoked Backfill outreach consent."
    elif activity_type == AuditAction.schedule_published.value or activity_type == "schedule_published":
        delivery = details.get("delivery_summary") or {}
        title = "Schedule updated" if details.get("is_update") else "Schedule published"
        summary = (
            f"{int(delivery.get('sms_sent', 0) or 0)} schedule texts sent, "
            f"{int(delivery.get('not_enrolled', 0) or 0)} not enrolled."
        )
    elif activity_type == AuditAction.schedule_amended.value:
        title = "Schedule amended"
        summary = "A published schedule was changed and saved as an amendment."
    elif activity_type == "schedule_draft_ready":
        title = "Draft ready"
        summary = f"{int(details.get('review_count', 0) or 0)} review item(s) were flagged for manager review."
    elif activity_type in {"schedule_updated", "schedule_removed"}:
        worker_name = await _get_worker_name(details.get("worker_id"))
        title = "Worker update sent" if activity_type == "schedule_updated" else "Worker removal notice sent"
        summary = f"{worker_name or 'A worker'} received a {activity_type.replace('schedule_', '').replace('_', ' ')} text."
    elif action_name == AuditAction.schedule_delivery_failed.value:
        worker_name = await _get_worker_name(details.get("worker_id"))
        title = "Schedule delivery failed"
        summary = (
            f"{worker_name or 'A worker'} could not be reached"
            if details.get("worker_id")
            else "A schedule message could not be delivered."
        )
    elif activity_type == "worker_callout_received":
        worker_name = await _get_worker_name(details.get("worker_id"))
        title = "Worker callout received"
        summary = f"{worker_name or 'A worker'} called out and coverage was started."
    elif action_name == AuditAction.shift_filled.value:
        worker_name = await _get_worker_name(details.get("filled_by"))
        title = "Shift filled"
        summary = f"{worker_name or 'A worker'} filled a coverage need."
    elif action_name == AuditAction.shift_confirmation_received.value:
        worker_name = await _get_worker_name(details.get("worker_id"))
        outcome = str(details.get("outcome") or "responded")
        title = "Shift confirmed" if outcome == "confirmed" else "Shift declined"
        summary = f"{worker_name or 'A worker'} {outcome.replace('_', ' ')} by SMS."
    elif action_name == AuditAction.shift_check_in_received.value:
        worker_name = await _get_worker_name(details.get("worker_id"))
        outcome = str(details.get("outcome") or "checked_in")
        title = "Worker checked in" if outcome == "checked_in" else "Late arrival reported"
        summary = (
            f"{worker_name or 'A worker'} checked in for their shift."
            if outcome == "checked_in"
            else f"{worker_name or 'A worker'} reported being {int(details.get('eta_minutes') or 0)} minutes late."
        )
    elif action_name == AuditAction.shift_check_in_escalated.value:
        title = "Attendance escalated"
        reason = str(details.get("reason") or "missed_check_in").replace("_", " ")
        summary = f"Coverage escalation triggered for {reason}."
    elif action_name == AuditAction.shift_attendance_actioned.value:
        title = "Attendance decision recorded"
        decision = str(details.get("decision") or "reviewed").replace("_", " ")
        summary = f"Manager chose to {decision}."
    elif activity_type == "manager_operational_digest":
        title = "Manager digest sent"
        digest_summary = details.get("summary") or {}
        summary = (
            f"{int(digest_summary.get('pending_actions', 0) or 0)} pending action(s), "
            f"{int(digest_summary.get('active_coverage', 0) or 0)} active coverage workflow(s)."
        )
    elif action_name == AuditAction.import_job_committed.value:
        title = "Import committed"
        summary = "Imported roster or schedule rows were committed into Backfill Shifts."

    if review_link is None:
        if entity_type == "schedule" and entity_id is not None:
            schedule = await _get_schedule(entity_id)
            if schedule and schedule.get("location_id") and schedule.get("week_start_date"):
                review_link = notifications_svc.build_manager_dashboard_link(
                    int(schedule["location_id"]),
                    tab="schedule",
                    week_start=str(schedule["week_start_date"]),
                )
        elif entity_type == "shift" and entity_id is not None:
            shift = await _get_shift(entity_id)
            if shift and shift.get("location_id"):
                review_link = notifications_svc.build_manager_dashboard_link(
                    int(shift["location_id"]),
                    tab="coverage",
                    shift_id=int(entity_id),
                )

    return {
        "id": int(row["id"]),
        "timestamp": str(row.get("timestamp") or ""),
        "actor": str(row.get("actor") or ""),
        "action": action_name,
        "activity_type": activity_type,
        "category": category,
        "title": title,
        "summary": summary,
        "entity_type": entity_type or None,
        "entity_id": entity_id,
        "review_link": review_link,
        "details": details,
    }


async def get_location_backfill_shifts_metrics(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    days: int = 30,
) -> dict:
    location = await queries.get_location(db, location_id)
    if location is None:
        raise ValueError("Location not found")

    window_end_dt = datetime.utcnow()
    window_start_dt = window_end_dt - timedelta(days=max(int(days), 1))
    window_start = window_start_dt.isoformat()
    window_end = window_end_dt.isoformat()

    workers = await queries.list_workers(db, location_id=location_id)
    schedules = await queries.list_schedules_for_location(db, location_id)
    shifts = await queries.list_shifts(db, location_id=location_id)
    window_audit = await _collect_location_audit_rows(
        db,
        location_id=location_id,
        since=window_start,
        workers=workers,
        schedules=schedules,
        shifts=shifts,
    )

    audit_action_counts = Counter(_audit_action_name(row.get("action")) for row in window_audit)
    audit_event_counts = Counter(
        str((row.get("details") or {}).get("event") or "")
        for row in window_audit
        if (row.get("details") or {}).get("event")
    )

    published_schedule_ids: set[int] = set()
    last_schedule_publish_at: str | None = None
    for schedule in schedules:
        versions = await queries.list_schedule_versions(db, int(schedule["id"]))
        publish_versions = [version for version in versions if version.get("version_type") == "publish_snapshot"]
        if publish_versions:
            published_schedule_ids.add(int(schedule["id"]))
            published_at = max(
                (
                    str(version.get("published_at") or version.get("created_at") or "")
                    for version in publish_versions
                    if version.get("published_at") or version.get("created_at")
                ),
                default="",
            )
            if published_at and (last_schedule_publish_at is None or published_at > last_schedule_publish_at):
                last_schedule_publish_at = published_at

    active_workers = [
        worker for worker in workers if str(worker.get("employment_status") or "active") == "active"
    ]
    enrolled_workers = [
        worker for worker in active_workers if worker.get("sms_consent_status") == "granted"
    ]
    invited_workers = audit_action_counts.get(AuditAction.worker_invited.value, 0)
    consent_granted_events = audit_action_counts.get(AuditAction.consent_granted.value, 0)
    schedule_delivery_sent_count = audit_action_counts.get(AuditAction.schedule_delivery_sent.value, 0)
    schedule_delivery_failed_count = audit_action_counts.get(AuditAction.schedule_delivery_failed.value, 0)
    schedule_delivery_removed_count = audit_event_counts.get("schedule_removed", 0)
    schedule_delivery_update_count = audit_event_counts.get("schedule_updated", 0)
    callout_shift_count = sum(1 for shift in shifts if shift.get("called_out_by") is not None)
    filled_callout_shift_count = sum(
        1
        for shift in shifts
        if shift.get("called_out_by") is not None and shift.get("filled_by") is not None
    )

    active_coverage_count = sum(1 for shift in shifts if shift.get("status") in {"vacant", "filling", "unfilled"})
    current_open_shift_count = sum(
        1
        for shift in shifts
        if shift.get("status") in {"scheduled", "vacant", "filling", "unfilled"} and shift.get("filled_by") is None
    )

    summary = {
        "worker_count": len(active_workers),
        "enrolled_worker_count": len(enrolled_workers),
        "pending_enrollment_count": sum(
            1 for worker in active_workers if worker.get("sms_consent_status") != "granted"
        ),
        "invite_sent_count": invited_workers,
        "consent_granted_event_count": consent_granted_events,
        "schedule_publish_event_count": audit_action_counts.get(AuditAction.schedule_published.value, 0),
        "schedule_amendment_event_count": audit_action_counts.get(AuditAction.schedule_amended.value, 0),
        "published_week_count": len(published_schedule_ids),
        "draft_week_count": sum(1 for schedule in schedules if schedule.get("lifecycle_state") == "draft"),
        "schedule_delivery_sent_count": schedule_delivery_sent_count,
        "schedule_delivery_update_count": schedule_delivery_update_count,
        "schedule_delivery_removed_count": schedule_delivery_removed_count,
        "schedule_delivery_failed_count": schedule_delivery_failed_count,
        "callout_shift_count": callout_shift_count,
        "filled_callout_shift_count": filled_callout_shift_count,
        "fill_event_count": audit_action_counts.get(AuditAction.shift_filled.value, 0),
        "active_coverage_count": active_coverage_count,
        "current_open_shift_count": current_open_shift_count,
        "confirmation_response_count": audit_action_counts.get(
            AuditAction.shift_confirmation_received.value,
            0,
        ),
        "check_in_response_count": audit_action_counts.get(
            AuditAction.shift_check_in_received.value,
            0,
        ),
        "reminder_sent_count": audit_event_counts.get("shift_reminder_sent", 0),
    }

    opt_in_rate = round(len(enrolled_workers) / len(active_workers), 4) if active_workers else None
    invite_conversion_rate = round(consent_granted_events / invited_workers, 4) if invited_workers else None
    callout_fill_rate = round(filled_callout_shift_count / callout_shift_count, 4) if callout_shift_count else None
    delivery_attempt_count = schedule_delivery_sent_count + schedule_delivery_failed_count
    delivery_success_rate = (
        round(schedule_delivery_sent_count / delivery_attempt_count, 4)
        if delivery_attempt_count
        else None
    )

    rates = {
        "opt_in_rate": opt_in_rate,
        "invite_conversion_rate": invite_conversion_rate,
        "callout_fill_rate": callout_fill_rate,
        "delivery_success_rate": delivery_success_rate,
        "first_publish_achieved": len(published_schedule_ids) >= 1,
        "second_publish_achieved": len(published_schedule_ids) >= 2,
    }

    recent_activity = {
        "last_schedule_publish_at": last_schedule_publish_at,
        "last_schedule_amendment_at": _latest_audit_timestamp(
            window_audit,
            lambda row: _audit_action_name(row.get("action")) == AuditAction.schedule_amended.value,
        ),
        "last_invite_sent_at": _latest_audit_timestamp(
            window_audit,
            lambda row: _audit_action_name(row.get("action")) == AuditAction.worker_invited.value,
        ),
        "last_enrollment_at": _latest_audit_timestamp(
            window_audit,
            lambda row: _audit_action_name(row.get("action")) == AuditAction.consent_granted.value,
        ),
        "last_callout_at": _latest_audit_timestamp(
            window_audit,
            lambda row: (row.get("details") or {}).get("event") == "worker_callout_received",
        ),
        "last_fill_at": _latest_audit_timestamp(
            window_audit,
            lambda row: _audit_action_name(row.get("action")) == AuditAction.shift_filled.value,
        ),
    }

    return {
        "location_id": location_id,
        "window_days": days,
        "window_start": window_start,
        "window_end": window_end,
        "launch_controls": {
            "backfill_shifts_enabled": bool(location.get("backfill_shifts_enabled", True)),
            "backfill_shifts_launch_state": location.get("backfill_shifts_launch_state") or "enabled",
            "backfill_shifts_beta_eligible": bool(location.get("backfill_shifts_beta_eligible")),
            "operating_mode": location.get("operating_mode"),
            "scheduling_platform": location.get("scheduling_platform"),
        },
        "summary": summary,
        "rates": rates,
        "recent_activity": recent_activity,
    }


async def get_location_backfill_shifts_activity(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    days: int = 30,
    limit: int = 50,
) -> dict:
    location = await queries.get_location(db, location_id)
    if location is None:
        raise ValueError("Location not found")

    window_end_dt = datetime.utcnow()
    window_start_dt = window_end_dt - timedelta(days=max(int(days), 1))
    window_start = window_start_dt.isoformat()
    window_end = window_end_dt.isoformat()

    rows = await _collect_location_audit_rows(
        db,
        location_id=location_id,
        since=window_start,
        final_limit=max(int(limit), 1),
    )
    worker_cache: dict[int, dict] = {}
    shift_cache: dict[int, dict] = {}
    schedule_cache: dict[int, dict] = {}
    items = [
        await _build_location_activity_item(
            db,
            row,
            worker_cache=worker_cache,
            shift_cache=shift_cache,
            schedule_cache=schedule_cache,
        )
        for row in rows
    ]
    category_counts = Counter(str(item.get("category") or "") for item in items if item.get("category"))
    activity_type_counts = Counter(str(item.get("activity_type") or "") for item in items if item.get("activity_type"))

    return {
        "location_id": location_id,
        "window_days": days,
        "window_start": window_start,
        "window_end": window_end,
        "summary": {
            "total_events": len(items),
            "categories": dict(category_counts),
            "activity_types": dict(activity_type_counts),
        },
        "items": items,
    }


async def get_backfill_shifts_webhook_health(
    db: aiosqlite.Connection,
    *,
    source: str = "twilio_sms",
    days: int = 30,
    limit: int = 50,
) -> dict:
    window_end_dt = datetime.utcnow()
    window_start_dt = window_end_dt - timedelta(days=max(int(days), 1))
    window_start = window_start_dt.isoformat()
    window_end = window_end_dt.isoformat()

    receipts = await queries.list_webhook_receipts(
        db,
        source=source,
        since=window_start,
        limit=max(int(limit), 1),
    )
    duplicate_retry_count = sum(int(receipt.get("duplicate_count") or 0) for receipt in receipts)
    receipts_with_retries = sum(1 for receipt in receipts if int(receipt.get("duplicate_count") or 0) > 0)
    completed_count = sum(1 for receipt in receipts if receipt.get("status") == "completed")
    processing_count = sum(1 for receipt in receipts if receipt.get("status") == "processing")

    recent_receipts = []
    for receipt in receipts:
        payload = dict(receipt.get("request_payload") or {})
        body_preview = _trim_text(payload.get("Body"))
        if body_preview and len(body_preview) > 120:
            body_preview = f"{body_preview[:117]}..."
        recent_receipts.append(
            {
                "id": int(receipt["id"]),
                "source": receipt.get("source"),
                "external_id": receipt.get("external_id"),
                "status": receipt.get("status"),
                "duplicate_count": int(receipt.get("duplicate_count") or 0),
                "from_phone": payload.get("From"),
                "body_preview": body_preview,
                "response_status_code": receipt.get("response_status_code"),
                "created_at": receipt.get("created_at"),
                "last_seen_at": receipt.get("last_seen_at") or receipt.get("updated_at"),
            }
        )

    return {
        "source": source,
        "window_days": days,
        "window_start": window_start,
        "window_end": window_end,
        "summary": {
            "receipt_count": len(receipts),
            "completed_count": completed_count,
            "processing_count": processing_count,
            "receipts_with_retries": receipts_with_retries,
            "duplicate_retry_count": duplicate_retry_count,
        },
        "recent_receipts": recent_receipts,
    }
