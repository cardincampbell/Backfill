from __future__ import annotations

from typing import Any, Optional

import aiosqlite

from app.db import queries
from app.services import backfill_shifts as backfill_shifts_svc
from app.services import cascade as cascade_svc
from app.services import ai_renderers


async def execute_action(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    action_type: str,
    location_id: int,
    schedule_id: int | None = None,
    week_start_date: str | None = None,
    shift_id: int | None = None,
    worker_id: int | None = None,
    cascade_id: int | None = None,
    create_shift_payload: dict[str, Any] | None = None,
    shift_patch: dict[str, Any] | None = None,
    actor: str = "system",
    confirmed: bool = False,
) -> dict[str, Any]:
    if action_type == "get_schedule_summary":
        return await _execute_get_schedule_summary(
            db,
            action_request_id=action_request_id,
            location_id=location_id,
            week_start_date=week_start_date,
        )
    if action_type == "get_unfilled_shifts":
        return await _execute_get_unfilled_shifts(
            db,
            action_request_id=action_request_id,
            location_id=location_id,
            week_start_date=week_start_date,
        )
    if action_type == "get_coverage_status":
        return await _execute_get_coverage_status(
            db,
            action_request_id=action_request_id,
            location_id=location_id,
            week_start_date=week_start_date,
        )
    if action_type == "get_publish_readiness":
        return await _execute_get_publish_readiness(
            db,
            action_request_id=action_request_id,
            schedule_id=schedule_id,
        )
    if action_type == "explain_schedule_issues":
        return await _execute_explain_schedule_issues(
            db,
            action_request_id=action_request_id,
            schedule_id=schedule_id,
        )
    if action_type == "publish_schedule":
        return await _execute_publish_schedule(
            db,
            action_request_id=action_request_id,
            schedule_id=schedule_id,
            actor=actor,
            confirmed=confirmed,
        )
    if action_type == "create_open_shift":
        return await _execute_create_open_shift(
            db,
            action_request_id=action_request_id,
            schedule_id=schedule_id,
            create_shift_payload=create_shift_payload,
            actor=actor,
            confirmed=confirmed,
        )
    if action_type == "edit_shift":
        return await _execute_edit_shift(
            db,
            action_request_id=action_request_id,
            shift_id=shift_id,
            shift_patch=shift_patch,
            actor=actor,
            confirmed=confirmed,
        )
    if action_type == "delete_shift":
        return await _execute_delete_shift(
            db,
            action_request_id=action_request_id,
            shift_id=shift_id,
            actor=actor,
            confirmed=confirmed,
        )
    if action_type == "assign_shift":
        return await _execute_assign_shift(
            db,
            action_request_id=action_request_id,
            shift_id=shift_id,
            worker_id=worker_id,
            actor=actor,
            confirmed=confirmed,
        )
    if action_type == "clear_shift_assignment":
        return await _execute_clear_shift_assignment(
            db,
            action_request_id=action_request_id,
            shift_id=shift_id,
            actor=actor,
            confirmed=confirmed,
        )
    if action_type == "approve_fill":
        return await _execute_approve_fill(
            db,
            action_request_id=action_request_id,
            cascade_id=cascade_id,
            shift_id=shift_id,
            confirmed=confirmed,
        )
    if action_type == "decline_fill":
        return await _execute_decline_fill(
            db,
            action_request_id=action_request_id,
            cascade_id=cascade_id,
            shift_id=shift_id,
            confirmed=confirmed,
        )
    if action_type == "open_shift":
        return await _execute_open_shift(
            db,
            action_request_id=action_request_id,
            shift_id=shift_id,
            actor=actor,
            confirmed=confirmed,
        )
    if action_type == "cancel_open_shift_offer":
        return await _execute_cancel_open_shift_offer(
            db,
            action_request_id=action_request_id,
            shift_id=shift_id,
            actor=actor,
            confirmed=confirmed,
        )
    if action_type == "close_open_shift":
        return await _execute_close_open_shift(
            db,
            action_request_id=action_request_id,
            shift_id=shift_id,
            actor=actor,
            confirmed=confirmed,
        )
    if action_type == "reopen_open_shift":
        return await _execute_reopen_open_shift(
            db,
            action_request_id=action_request_id,
            shift_id=shift_id,
            actor=actor,
            confirmed=confirmed,
        )
    if action_type == "reopen_and_offer_open_shift":
        return await _execute_reopen_and_offer_open_shift(
            db,
            action_request_id=action_request_id,
            shift_id=shift_id,
            actor=actor,
            confirmed=confirmed,
        )
    return ai_renderers.build_error_response(
        action_request_id=action_request_id,
        summary=f"The action {action_type!r} is not implemented yet.",
    )


async def _execute_get_schedule_summary(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    location_id: int,
    week_start_date: str | None,
) -> dict[str, Any]:
    schedule_view = await backfill_shifts_svc.get_schedule_view(
        db,
        location_id=location_id,
        week_start=week_start_date,
    )
    schedule = schedule_view.get("schedule")
    summary = dict(schedule_view.get("summary") or {})
    if schedule is None:
        return ai_renderers.build_completed_response(
            action_request_id=action_request_id,
            summary="No schedule exists yet for this location.",
            risk_class="green",
            ui_payload={
                "kind": "simple_result",
                "data": {
                    "title": "No schedule yet",
                    "body": "Create, import, or generate a schedule to begin.",
                    "metrics": summary,
                },
            },
        )

    headline = (
        f"Week of {schedule.get('week_start_date')} has "
        f"{int(summary.get('filled_shifts') or 0)} filled shifts, "
        f"{int(summary.get('open_shifts') or 0)} open shifts, and "
        f"{int(summary.get('action_required_count') or 0)} items needing attention."
    )
    return ai_renderers.build_completed_response(
        action_request_id=action_request_id,
        summary=headline,
        risk_class="green",
        ui_payload={
            "kind": "simple_result",
            "data": {
                "title": f"Schedule summary · {schedule.get('week_start_date')}",
                "body": headline,
                "metrics": {
                    "filled_shifts": int(summary.get("filled_shifts") or 0),
                    "open_shifts": int(summary.get("open_shifts") or 0),
                    "action_required_count": int(summary.get("action_required_count") or 0),
                    "warning_count": int(summary.get("warning_count") or 0),
                },
            },
        },
    )


async def _execute_get_unfilled_shifts(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    location_id: int,
    week_start_date: str | None,
) -> dict[str, Any]:
    queue = await backfill_shifts_svc.get_schedule_exception_queue(
        db,
        location_id=location_id,
        week_start=week_start_date,
        action_required_only=True,
    )
    summary = dict(queue.get("summary") or {})
    total = int(summary.get("total") or 0)
    message = (
        "I found no open or action-required schedule exceptions."
        if total == 0
        else f"I found {total} schedule exception{'s' if total != 1 else ''} that still need attention."
    )
    return ai_renderers.build_completed_response(
        action_request_id=action_request_id,
        summary=message,
        risk_class="green",
        ui_payload={"kind": "schedule_exceptions", "data": queue},
    )


async def _execute_get_coverage_status(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    location_id: int,
    week_start_date: str | None,
) -> dict[str, Any]:
    coverage = await backfill_shifts_svc.get_coverage_view(
        db,
        location_id=location_id,
        week_start=week_start_date,
    )
    shifts = list(coverage.get("at_risk_shifts") or [])
    active = sum(1 for shift in shifts if str(shift.get("coverage_status") or "") not in {"unfilled", "unassigned"})
    summary = (
        "No active coverage workflows are running right now."
        if not shifts
        else f"There are {len(shifts)} at-risk shift{'s' if len(shifts) != 1 else ''} and {active} active coverage workflow{'s' if active != 1 else ''}."
    )
    return ai_renderers.build_completed_response(
        action_request_id=action_request_id,
        summary=summary,
        risk_class="green",
        ui_payload={"kind": "coverage_summary", "data": coverage},
    )


async def _execute_get_publish_readiness(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    schedule_id: int | None,
) -> dict[str, Any]:
    if schedule_id is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find a schedule to review for publishing.",
        )
    review = await backfill_shifts_svc.get_schedule_review(db, schedule_id=schedule_id)
    readiness = dict(review.get("publish_readiness") or {})
    return ai_renderers.build_completed_response(
        action_request_id=action_request_id,
        summary=str(readiness.get("status_message") or "Schedule review is ready."),
        risk_class="green",
        ui_payload={"kind": "schedule_review", "data": review},
    )


async def _execute_explain_schedule_issues(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    schedule_id: int | None,
) -> dict[str, Any]:
    if schedule_id is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find a schedule to review.",
        )
    review = await backfill_shifts_svc.get_schedule_review(db, schedule_id=schedule_id)
    review_summary = dict(review.get("review_summary") or {})
    return ai_renderers.build_completed_response(
        action_request_id=action_request_id,
        summary=str(review_summary.get("headline") or "Here is the schedule review."),
        risk_class="green",
        ui_payload={"kind": "schedule_review", "data": review},
    )


async def _execute_publish_schedule(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    schedule_id: int | None,
    actor: str,
    confirmed: bool,
) -> dict[str, Any]:
    if schedule_id is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find a current schedule draft to publish.",
        )

    if not confirmed:
        message_preview = await backfill_shifts_svc.get_schedule_message_preview(
            db,
            schedule_id=schedule_id,
        )
        preview = await backfill_shifts_svc.get_schedule_publish_preview(
            db,
            schedule_id=schedule_id,
        )
        schedule = preview.get("schedule") or {}
        publish_preview = dict(preview.get("publish_preview") or {})
        review_link = publish_preview.get("review_link") or (message_preview.get("message_preview") or {}).get("review_link")
        ui_payload = {
            "kind": "publish_preview",
            "data": {
                "schedule_id": schedule_id,
                "message_preview": {
                    "message_body": ((message_preview.get("message_preview") or {}).get("publish_success") or "")
                    or ((message_preview.get("message_preview") or {}).get("draft_ready") or "")
                    or ((message_preview.get("message_preview") or {}).get("publish_blocked") or ""),
                    "review_link": review_link,
                    "publish_mode": (message_preview.get("message_preview") or {}).get("publish_mode"),
                    "worker_update_count": (message_preview.get("message_preview") or {}).get("worker_update_count"),
                },
                "delivery_estimate": publish_preview.get("delivery_estimate") or {},
                "worker_message_previews": publish_preview.get("worker_message_previews") or [],
            },
        }
        affected_entities = [
            {
                "type": "schedule",
                "id": schedule_id,
                "label": f"Schedule week of {schedule.get('week_start_date') or 'current week'}",
            }
        ]
        return ai_renderers.build_confirmation_response(
            action_request_id=action_request_id,
            summary=f"I can publish the schedule for the week of {schedule.get('week_start_date') or 'this week'}.",
            risk_class="yellow",
            confirmation_prompt="Publish the current schedule now?",
            affected_entities=affected_entities,
            ui_payload=ui_payload,
        )

    published = await backfill_shifts_svc.publish_schedule(
        db,
        schedule_id=schedule_id,
        actor=actor,
    )
    delivery_summary = dict(published.get("delivery_summary") or {})
    summary = (
        f"Published the schedule. {int(delivery_summary.get('sms_sent') or 0)} worker text"
        f"{'' if int(delivery_summary.get('sms_sent') or 0) == 1 else 's'} sent"
    )
    if int(delivery_summary.get("not_enrolled") or 0):
        summary += f", {int(delivery_summary.get('not_enrolled') or 0)} worker{'s' if int(delivery_summary.get('not_enrolled') or 0) != 1 else ''} still not enrolled"
    summary += "."
    return ai_renderers.build_completed_response(
        action_request_id=action_request_id,
        summary=summary,
        risk_class="yellow",
        ui_payload={
            "kind": "simple_result",
            "data": {
                "title": "Schedule published",
                "body": summary,
                "metrics": {
                    "sms_sent": int(delivery_summary.get("sms_sent") or 0),
                    "not_enrolled": int(delivery_summary.get("not_enrolled") or 0),
                    "sms_failed": int(delivery_summary.get("sms_failed") or 0),
                },
            },
        },
    )


async def _execute_create_open_shift(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    schedule_id: int | None,
    create_shift_payload: dict[str, Any] | None,
    actor: str,
    confirmed: bool,
) -> dict[str, Any]:
    if schedule_id is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find a schedule week for that shift. Specify the schedule week or date more clearly.",
        )

    payload = dict(create_shift_payload or {})
    missing_fields = [
        field_name
        for field_name in ("role", "date", "start_time", "end_time")
        if not payload.get(field_name)
    ]
    if missing_fields:
        human_fields = ", ".join(field_name.replace("_", " ") for field_name in missing_fields)
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary=f"I need the {human_fields} before I can create that open shift.",
        )

    schedule = await queries.get_schedule(db, schedule_id)
    if schedule is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find the target schedule for that open shift.",
        )
    shift_date = str(payload["date"])
    if schedule.get("week_start_date") and schedule.get("week_end_date"):
        if not (str(schedule["week_start_date"]) <= shift_date <= str(schedule["week_end_date"])):
            return ai_renderers.build_error_response(
                action_request_id=action_request_id,
                summary=(
                    f"The requested date {shift_date} falls outside the schedule week of "
                    f"{schedule.get('week_start_date')} to {schedule.get('week_end_date')}."
                ),
            )

    role_label = str(payload["role"] or "shift").replace("_", " ")
    start_label = str(payload["start_time"])[:5]
    end_label = str(payload["end_time"])[:5]
    start_offer = bool(payload.get("start_open_shift_offer"))
    if not confirmed:
        summary = f"I can create an open {role_label} shift on {shift_date} from {start_label} to {end_label}."
        if start_offer:
            summary = (
                f"I can create an open {role_label} shift on {shift_date} from {start_label} to {end_label} "
                "and start offering it right away."
            )
        return ai_renderers.build_confirmation_response(
            action_request_id=action_request_id,
            summary=summary,
            risk_class="yellow",
            confirmation_prompt="Create this open shift now?",
            affected_entities=[
                {
                    "type": "schedule",
                    "id": schedule_id,
                    "label": f"Schedule week of {schedule.get('week_start_date') or 'current week'}",
                }
            ],
            ui_payload={
                "kind": "create_shift_preview",
                "data": {
                    "schedule_id": schedule_id,
                    "week_start_date": schedule.get("week_start_date"),
                    "shift": {
                        "role": payload["role"],
                        "date": shift_date,
                        "start_time": payload["start_time"],
                        "end_time": payload["end_time"],
                        "spans_midnight": payload.get("spans_midnight"),
                        "start_open_shift_offer": start_offer,
                        "shift_label": payload.get("shift_label"),
                        "notes": payload.get("notes"),
                        "pay_rate": payload.get("pay_rate"),
                        "requirements": list(payload.get("requirements") or []),
                    },
                },
            },
        )

    try:
        result = await backfill_shifts_svc.create_schedule_shift(
            db,
            schedule_id=schedule_id,
            shift_payload={
                "role": payload["role"],
                "date": shift_date,
                "start_time": payload["start_time"],
                "end_time": payload["end_time"],
                "spans_midnight": payload.get("spans_midnight"),
                "start_open_shift_offer": start_offer,
                "shift_label": payload.get("shift_label"),
                "notes": payload.get("notes"),
                "pay_rate": payload.get("pay_rate") or 0.0,
                "requirements": list(payload.get("requirements") or []),
                "worker_id": None,
                "assignment_status": "open",
            },
            actor=actor,
        )
    except ValueError as exc:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary=str(exc),
        )

    offer_result = result.get("offer_result")
    summary = f"Created the open {role_label} shift on {shift_date} from {start_label} to {end_label}."
    if offer_result:
        summary = (
            f"Created the open {role_label} shift on {shift_date} from {start_label} to {end_label} "
            "and started offering it."
        )
    return ai_renderers.build_completed_response(
        action_request_id=action_request_id,
        summary=summary,
        risk_class="green",
        ui_payload={
            "kind": "create_shift_result",
            "data": {
                "schedule_id": schedule_id,
                "shift": result.get("shift"),
                "assignment": result.get("assignment"),
                "coverage": result.get("coverage"),
                "available_actions": result.get("available_actions"),
                "offer_result": offer_result,
            },
        },
    )


async def _execute_edit_shift(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    shift_id: int | None,
    shift_patch: dict[str, Any] | None,
    actor: str,
    confirmed: bool,
) -> dict[str, Any]:
    if shift_id is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find the shift to edit.",
        )
    patch = {
        key: value
        for key, value in dict(shift_patch or {}).items()
        if value not in (None, [], {})
    }
    if not patch:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not tell what to change on that shift.",
        )
    shift = await queries.get_shift(db, int(shift_id))
    if shift is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find that shift.",
        )

    role = str(shift.get("role") or "shift")
    shift_date = str(shift.get("date") or "")
    start_time = str(shift.get("start_time") or "")[:5]
    change_summary = _summarize_shift_patch(patch)
    preview_summary = f"I can update the {role} shift on {shift_date} at {start_time} and change {change_summary}."
    if not confirmed:
        return ai_renderers.build_confirmation_response(
            action_request_id=action_request_id,
            summary=preview_summary,
            risk_class="yellow",
            confirmation_prompt="Apply these shift edits now?",
            affected_entities=[
                {"type": "shift", "id": int(shift_id), "label": f"{role} · {shift_date} {start_time}"},
            ],
            ui_payload={
                "kind": "shift_edit_preview",
                "data": {
                    "shift_id": int(shift_id),
                    "patch": patch,
                    "summary": change_summary,
                },
            },
        )

    try:
        outcome = await backfill_shifts_svc.amend_schedule_shift_details(
            db,
            shift_id=int(shift_id),
            patch=patch,
            actor=actor,
        )
    except ValueError as exc:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary=str(exc),
        )

    updated_shift = dict(outcome.get("shift") or {})
    result_summary = (
        f"Updated the {str(updated_shift.get('role') or role)} shift on "
        f"{updated_shift.get('date') or shift_date} at {str(updated_shift.get('start_time') or shift.get('start_time') or '')[:5]}."
    )
    return ai_renderers.build_completed_response(
        action_request_id=action_request_id,
        summary=result_summary,
        risk_class="yellow",
        ui_payload={
            "kind": "shift_edit_result",
            "data": {
                "shift_id": int(shift_id),
                "updated_fields": list(outcome.get("updated_fields") or []),
                "shift": outcome.get("shift"),
                "assignment": outcome.get("assignment"),
                "coverage": outcome.get("coverage"),
                "available_actions": outcome.get("available_actions"),
            },
        },
    )


async def _execute_delete_shift(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    shift_id: int | None,
    actor: str,
    confirmed: bool,
) -> dict[str, Any]:
    if shift_id is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find the shift to delete.",
        )
    shift = await queries.get_shift(db, int(shift_id))
    if shift is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find that shift.",
        )

    role = str(shift.get("role") or "shift")
    shift_date = str(shift.get("date") or "")
    start_time = str(shift.get("start_time") or "")[:5]
    summary = f"I can delete the {role} shift on {shift_date} at {start_time}."
    if not confirmed:
        return ai_renderers.build_confirmation_response(
            action_request_id=action_request_id,
            summary=summary,
            risk_class="yellow",
            confirmation_prompt="Delete this shift now?",
            affected_entities=[
                {"type": "shift", "id": int(shift_id), "label": f"{role} · {shift_date} {start_time}"},
            ],
            ui_payload={
                "kind": "simple_result",
                "data": {
                    "title": "Delete shift",
                    "body": summary,
                },
            },
        )

    try:
        outcome = await backfill_shifts_svc.delete_schedule_shift(
            db,
            shift_id=int(shift_id),
            actor=actor,
        )
    except ValueError as exc:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary=str(exc),
        )

    return ai_renderers.build_completed_response(
        action_request_id=action_request_id,
        summary=f"Deleted the {role} shift on {shift_date} at {start_time}.",
        risk_class="yellow",
        ui_payload={
            "kind": "simple_result",
            "data": {
                "title": "Shift deleted",
                "body": f"Deleted the {role} shift on {shift_date} at {start_time}.",
                "metrics": {
                    "shift_id": int(shift_id),
                    "deleted": bool(outcome.get("deleted")),
                },
            },
        },
    )


async def _execute_assign_shift(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    shift_id: int | None,
    worker_id: int | None,
    actor: str,
    confirmed: bool,
) -> dict[str, Any]:
    if shift_id is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find the shift to assign.",
        )
    if worker_id is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not identify which worker should take that shift.",
        )
    shift = await queries.get_shift(db, int(shift_id))
    worker = await queries.get_worker(db, int(worker_id))
    if shift is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find that shift.",
        )
    if worker is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find that worker.",
        )
    assignment = await queries.get_shift_assignment_with_worker(db, int(shift_id))
    current_worker_name = assignment.get("worker_name") if assignment else None
    role = str(shift.get("role") or "shift")
    shift_date = str(shift.get("date") or "")
    start_time = str(shift.get("start_time") or "")[:5]
    worker_name = str(worker.get("name") or "the selected worker")
    if not confirmed:
        summary = f"I can assign {worker_name} to the {role} shift on {shift_date} at {start_time}."
        if current_worker_name and current_worker_name != worker_name:
            summary = f"I can reassign the {role} shift on {shift_date} at {start_time} from {current_worker_name} to {worker_name}."
        return ai_renderers.build_confirmation_response(
            action_request_id=action_request_id,
            summary=summary,
            risk_class="yellow",
            confirmation_prompt="Update this shift assignment now?",
            affected_entities=[
                {"type": "shift", "id": int(shift_id), "label": f"{role} · {shift_date} {start_time}"},
                {"type": "worker", "id": int(worker_id), "label": worker_name},
            ],
            ui_payload={
                "kind": "simple_result",
                "data": {
                    "title": "Shift assignment",
                    "body": summary,
                },
            },
        )
    try:
        outcome = await backfill_shifts_svc.amend_shift_assignment(
            db,
            shift_id=int(shift_id),
            worker_id=int(worker_id),
            assignment_status="assigned",
            notes=None,
            actor=actor,
        )
    except ValueError as exc:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary=str(exc),
        )
    summary = f"Assigned {worker_name} to the {role} shift on {shift_date} at {start_time}."
    if current_worker_name and current_worker_name != worker_name:
        summary = f"Reassigned the {role} shift on {shift_date} at {start_time} from {current_worker_name} to {worker_name}."
    return ai_renderers.build_completed_response(
        action_request_id=action_request_id,
        summary=summary,
        risk_class="yellow",
        ui_payload={
            "kind": "simple_result",
            "data": {
                "title": "Shift assigned",
                "body": summary,
                "metrics": {
                    "shift_id": int(shift_id),
                    "worker_id": int(worker_id),
                },
            },
        },
    )


async def _execute_clear_shift_assignment(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    shift_id: int | None,
    actor: str,
    confirmed: bool,
) -> dict[str, Any]:
    if shift_id is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find the shift assignment to clear.",
        )
    shift = await queries.get_shift(db, int(shift_id))
    if shift is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find that shift.",
        )
    assignment = await queries.get_shift_assignment_with_worker(db, int(shift_id))
    if assignment is None or assignment.get("worker_id") is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="That shift does not currently have an assigned worker to clear.",
        )
    role = str(shift.get("role") or "shift")
    shift_date = str(shift.get("date") or "")
    start_time = str(shift.get("start_time") or "")[:5]
    worker_name = str(assignment.get("worker_name") or "the current worker")
    summary = f"I can remove {worker_name} from the {role} shift on {shift_date} at {start_time} and reopen it."
    if not confirmed:
        return ai_renderers.build_confirmation_response(
            action_request_id=action_request_id,
            summary=summary,
            risk_class="yellow",
            confirmation_prompt="Clear this shift assignment now?",
            affected_entities=[
                {"type": "shift", "id": int(shift_id), "label": f"{role} · {shift_date} {start_time}"},
                {"type": "worker", "id": int(assignment.get("worker_id")), "label": worker_name},
            ],
            ui_payload={
                "kind": "simple_result",
                "data": {
                    "title": "Clear shift assignment",
                    "body": summary,
                },
            },
        )
    try:
        await backfill_shifts_svc.amend_shift_assignment(
            db,
            shift_id=int(shift_id),
            worker_id=None,
            assignment_status="open",
            notes=None,
            actor=actor,
        )
    except ValueError as exc:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary=str(exc),
        )
    return ai_renderers.build_completed_response(
        action_request_id=action_request_id,
        summary=summary.replace("I can remove", "Removed").replace(" and reopen it", "."),
        risk_class="yellow",
        ui_payload={
            "kind": "simple_result",
            "data": {
                "title": "Shift assignment cleared",
                "body": f"Removed {worker_name} from the {role} shift on {shift_date} at {start_time}.",
                "metrics": {
                    "shift_id": int(shift_id),
                },
            },
        },
    )


def _summarize_shift_patch(patch: dict[str, Any]) -> str:
    changes: list[str] = []
    if "role" in patch:
        changes.append(f"the role to {str(patch['role']).replace('_', ' ')}")
    if "date" in patch:
        changes.append(f"the date to {patch['date']}")
    if "start_time" in patch and "end_time" in patch:
        changes.append(f"the time to {str(patch['start_time'])[:5]} to {str(patch['end_time'])[:5]}")
    else:
        if "start_time" in patch:
            changes.append(f"the start time to {str(patch['start_time'])[:5]}")
        if "end_time" in patch:
            changes.append(f"the end time to {str(patch['end_time'])[:5]}")
    if "shift_label" in patch:
        changes.append("the shift label")
    if "notes" in patch:
        changes.append("the notes")
    if "pay_rate" in patch:
        changes.append(f"the pay rate to {patch['pay_rate']}")
    if "requirements" in patch:
        changes.append("the requirements")
    if not changes:
        return "the requested details"
    if len(changes) == 1:
        return changes[0]
    if len(changes) == 2:
        return f"{changes[0]} and {changes[1]}"
    return ", ".join(changes[:-1]) + f", and {changes[-1]}"


async def _execute_approve_fill(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    cascade_id: int | None,
    shift_id: int | None,
    confirmed: bool,
) -> dict[str, Any]:
    context = await _load_pending_fill_context(
        db,
        cascade_id=cascade_id,
        shift_id=shift_id,
    )
    if context is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find a pending fill approval to approve.",
        )

    worker_name = context["worker_name"]
    role = context["role"]
    shift_date = context["date"]
    start_time = context["start_time"]
    if not confirmed:
        return ai_renderers.build_confirmation_response(
            action_request_id=action_request_id,
            summary=f"I can approve {worker_name} for {role} on {shift_date} at {start_time}.",
            risk_class="yellow",
            confirmation_prompt=f"Approve {worker_name} to cover this shift?",
            affected_entities=[
                {"type": "worker", "id": context["worker_id"], "label": worker_name},
                {"type": "shift", "id": context["shift_id"], "label": f"{role} · {shift_date} {start_time}"},
            ],
            ui_payload={
                "kind": "simple_result",
                "data": {
                    "title": "Pending fill approval",
                    "body": f"{worker_name} is waiting for approval to cover {role} on {shift_date} at {start_time}.",
                },
            },
        )

    outcome = await cascade_svc.approve_pending_claim(
        db,
        int(context["cascade_id"]),
        summary="Approved from AI web action",
    )
    if outcome.get("status") == "confirmed":
        summary = f"Approved {worker_name} for {role} on {shift_date} at {start_time}."
    else:
        summary = "That fill approval is no longer pending."
    return ai_renderers.build_completed_response(
        action_request_id=action_request_id,
        summary=summary,
        risk_class="yellow",
        ui_payload={
            "kind": "simple_result",
            "data": {
                "title": "Fill approved",
                "body": summary,
                "metrics": {
                    "cascade_id": int(context["cascade_id"]),
                    "shift_id": int(context["shift_id"]),
                    "worker_id": int(context["worker_id"]),
                },
            },
        },
    )


async def _execute_decline_fill(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    cascade_id: int | None,
    shift_id: int | None,
    confirmed: bool,
) -> dict[str, Any]:
    context = await _load_pending_fill_context(
        db,
        cascade_id=cascade_id,
        shift_id=shift_id,
    )
    if context is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find a pending fill approval to decline.",
        )

    worker_name = context["worker_name"]
    role = context["role"]
    shift_date = context["date"]
    start_time = context["start_time"]
    if not confirmed:
        return ai_renderers.build_confirmation_response(
            action_request_id=action_request_id,
            summary=f"I can decline {worker_name}'s claim for {role} on {shift_date} at {start_time}.",
            risk_class="yellow",
            confirmation_prompt=f"Decline {worker_name} and keep looking for coverage?",
            affected_entities=[
                {"type": "worker", "id": context["worker_id"], "label": worker_name},
                {"type": "shift", "id": context["shift_id"], "label": f"{role} · {shift_date} {start_time}"},
            ],
            ui_payload={
                "kind": "simple_result",
                "data": {
                    "title": "Pending fill decline",
                    "body": f"Backfill will keep looking if you decline {worker_name}.",
                },
            },
        )

    outcome = await cascade_svc.decline_pending_claim(
        db,
        int(context["cascade_id"]),
        summary="Declined from AI web action",
    )
    summary = f"Declined {worker_name} for {role} on {shift_date} at {start_time}. Backfill will keep looking."
    if outcome.get("status") == "confirmed":
        summary = f"{worker_name} is already confirmed for {role} on {shift_date} at {start_time}."
    return ai_renderers.build_completed_response(
        action_request_id=action_request_id,
        summary=summary,
        risk_class="yellow",
        ui_payload={
            "kind": "simple_result",
            "data": {
                "title": "Fill declined",
                "body": summary,
                "metrics": {
                    "cascade_id": int(context["cascade_id"]),
                    "shift_id": int(context["shift_id"]),
                    "worker_id": int(context["worker_id"]),
                },
            },
        },
    )


async def _execute_open_shift(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    shift_id: int | None,
    actor: str,
    confirmed: bool,
) -> dict[str, Any]:
    if shift_id is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find an open shift to offer right now.",
        )
    shift = await queries.get_shift(db, int(shift_id))
    if shift is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find that shift.",
        )

    role = str(shift.get("role") or "shift")
    shift_date = str(shift.get("date") or "")
    start_time = str(shift.get("start_time") or "")[:5]
    if not confirmed:
        return ai_renderers.build_confirmation_response(
            action_request_id=action_request_id,
            summary=f"I can start coverage for the open {role} shift on {shift_date} at {start_time}.",
            risk_class="yellow",
            confirmation_prompt="Start outreach for this open shift now?",
            affected_entities=[
                {"type": "shift", "id": int(shift_id), "label": f"{role} · {shift_date} {start_time}"},
            ],
            ui_payload={
                "kind": "simple_result",
                "data": {
                    "title": "Open shift outreach",
                    "body": f"Backfill will begin offering the {role} shift on {shift_date} at {start_time}.",
                },
            },
        )

    outcome = await backfill_shifts_svc.start_coverage_for_open_shift(
        db,
        shift_id=int(shift_id),
        actor=actor,
    )
    if outcome.get("status") == "coverage_active":
        summary = f"Coverage is already running for the open {role} shift on {shift_date} at {start_time}."
    else:
        summary = f"Started coverage for the open {role} shift on {shift_date} at {start_time}."
    return ai_renderers.build_completed_response(
        action_request_id=action_request_id,
        summary=summary,
        risk_class="yellow",
        ui_payload={
            "kind": "simple_result",
            "data": {
                "title": "Open shift outreach started",
                "body": summary,
                "metrics": {
                    "shift_id": int(shift_id),
                    "cascade_id": outcome.get("cascade_id"),
                },
            },
        },
    )


async def _execute_cancel_open_shift_offer(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    shift_id: int | None,
    actor: str,
    confirmed: bool,
) -> dict[str, Any]:
    if shift_id is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find an active open-shift offer to cancel.",
        )
    shift = await queries.get_shift(db, int(shift_id))
    if shift is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find that shift.",
        )
    role = str(shift.get("role") or "shift")
    shift_date = str(shift.get("date") or "")
    start_time = str(shift.get("start_time") or "")[:5]
    if not confirmed:
        return ai_renderers.build_confirmation_response(
            action_request_id=action_request_id,
            summary=f"I can cancel the active offer for the open {role} shift on {shift_date} at {start_time}.",
            risk_class="yellow",
            confirmation_prompt="Cancel outreach for this open shift now?",
            affected_entities=[
                {"type": "shift", "id": int(shift_id), "label": f"{role} · {shift_date} {start_time}"},
            ],
            ui_payload={
                "kind": "simple_result",
                "data": {
                    "title": "Cancel open-shift offer",
                    "body": f"Backfill will stop offering the {role} shift on {shift_date} at {start_time}.",
                },
            },
        )
    try:
        outcome = await backfill_shifts_svc.cancel_open_shift_offer(
            db,
            shift_id=int(shift_id),
            actor=actor,
        )
    except ValueError as exc:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary=str(exc),
        )
    if outcome.get("status") == "offer_not_active":
        summary = f"There is no active offer running for the open {role} shift on {shift_date} at {start_time}."
    else:
        summary = f"Cancelled the active offer for the open {role} shift on {shift_date} at {start_time}."
    return ai_renderers.build_completed_response(
        action_request_id=action_request_id,
        summary=summary,
        risk_class="yellow",
        ui_payload={
            "kind": "simple_result",
            "data": {
                "title": "Open-shift offer cancelled",
                "body": summary,
                "metrics": {
                    "shift_id": int(shift_id),
                    "cascade_id": outcome.get("cascade_id"),
                },
            },
        },
    )


async def _execute_close_open_shift(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    shift_id: int | None,
    actor: str,
    confirmed: bool,
) -> dict[str, Any]:
    if shift_id is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find an open shift to close.",
        )
    shift = await queries.get_shift(db, int(shift_id))
    if shift is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find that shift.",
        )
    role = str(shift.get("role") or "shift")
    shift_date = str(shift.get("date") or "")
    start_time = str(shift.get("start_time") or "")[:5]
    if not confirmed:
        return ai_renderers.build_confirmation_response(
            action_request_id=action_request_id,
            summary=f"I can close the open {role} shift on {shift_date} at {start_time}.",
            risk_class="yellow",
            confirmation_prompt="Close this open shift now?",
            affected_entities=[
                {"type": "shift", "id": int(shift_id), "label": f"{role} · {shift_date} {start_time}"},
            ],
            ui_payload={
                "kind": "simple_result",
                "data": {
                    "title": "Close open shift",
                    "body": f"Backfill will stop treating the {role} shift on {shift_date} at {start_time} as open.",
                },
            },
        )
    try:
        outcome = await backfill_shifts_svc.close_open_shift(
            db,
            shift_id=int(shift_id),
            actor=actor,
        )
    except ValueError as exc:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary=str(exc),
        )
    if outcome.get("idempotent"):
        summary = f"The open {role} shift on {shift_date} at {start_time} is already closed."
    else:
        summary = f"Closed the open {role} shift on {shift_date} at {start_time}."
    return ai_renderers.build_completed_response(
        action_request_id=action_request_id,
        summary=summary,
        risk_class="yellow",
        ui_payload={
            "kind": "simple_result",
            "data": {
                "title": "Open shift closed",
                "body": summary,
                "metrics": {
                    "shift_id": int(shift_id),
                    "cascade_cancelled": bool(outcome.get("cascade_cancelled")),
                },
            },
        },
    )


async def _execute_reopen_open_shift(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    shift_id: int | None,
    actor: str,
    confirmed: bool,
) -> dict[str, Any]:
    return await _execute_reopen_shift_variant(
        db,
        action_request_id=action_request_id,
        shift_id=shift_id,
        actor=actor,
        confirmed=confirmed,
        start_open_shift_offer=False,
    )


async def _execute_reopen_and_offer_open_shift(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    shift_id: int | None,
    actor: str,
    confirmed: bool,
) -> dict[str, Any]:
    return await _execute_reopen_shift_variant(
        db,
        action_request_id=action_request_id,
        shift_id=shift_id,
        actor=actor,
        confirmed=confirmed,
        start_open_shift_offer=True,
    )


async def _execute_reopen_shift_variant(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
    shift_id: int | None,
    actor: str,
    confirmed: bool,
    start_open_shift_offer: bool,
) -> dict[str, Any]:
    if shift_id is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find a closed open shift to reopen.",
        )
    shift = await queries.get_shift(db, int(shift_id))
    if shift is None:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary="I could not find that shift.",
        )
    role = str(shift.get("role") or "shift")
    shift_date = str(shift.get("date") or "")
    start_time = str(shift.get("start_time") or "")[:5]
    if not confirmed:
        summary = f"I can reopen the closed {role} shift on {shift_date} at {start_time}."
        prompt = "Reopen this shift now?"
        title = "Reopen open shift"
        body = f"Backfill will reopen the {role} shift on {shift_date} at {start_time}."
        if start_open_shift_offer:
            summary = f"I can reopen the closed {role} shift on {shift_date} at {start_time} and start offering it right away."
            prompt = "Reopen and offer this shift now?"
            title = "Reopen and offer shift"
            body = f"Backfill will reopen the {role} shift on {shift_date} at {start_time} and immediately start offering it."
        return ai_renderers.build_confirmation_response(
            action_request_id=action_request_id,
            summary=summary,
            risk_class="yellow",
            confirmation_prompt=prompt,
            affected_entities=[
                {"type": "shift", "id": int(shift_id), "label": f"{role} · {shift_date} {start_time}"},
            ],
            ui_payload={
                "kind": "simple_result",
                "data": {
                    "title": title,
                    "body": body,
                },
            },
        )
    try:
        outcome = await backfill_shifts_svc.reopen_open_shift(
            db,
            shift_id=int(shift_id),
            start_open_shift_offer=start_open_shift_offer,
            actor=actor,
        )
    except ValueError as exc:
        return ai_renderers.build_error_response(
            action_request_id=action_request_id,
            summary=str(exc),
        )

    summary = f"Reopened the closed {role} shift on {shift_date} at {start_time}."
    if start_open_shift_offer:
        summary = f"Reopened the closed {role} shift on {shift_date} at {start_time} and started offering it."
    return ai_renderers.build_completed_response(
        action_request_id=action_request_id,
        summary=summary,
        risk_class="yellow",
        ui_payload={
            "kind": "simple_result",
            "data": {
                "title": "Open shift reopened",
                "body": summary,
                "metrics": {
                    "shift_id": int(shift_id),
                    "reopened": bool(outcome.get("reopened")),
                    "cascade_id": outcome.get("cascade_id"),
                },
            },
        },
    )


async def _load_pending_fill_context(
    db: aiosqlite.Connection,
    *,
    cascade_id: int | None,
    shift_id: int | None,
) -> dict[str, Any] | None:
    cascade = None
    if cascade_id is not None:
        cascade = await cascade_svc.get_cascade(db, int(cascade_id))
    elif shift_id is not None:
        cascade = await queries.get_active_cascade_for_shift(db, int(shift_id))
    if cascade is None:
        return None

    resolved_shift_id = int(cascade["shift_id"])
    shift = await queries.get_shift(db, resolved_shift_id)
    if shift is None:
        return None

    worker_id = cascade.get("pending_claim_worker_id") or cascade.get("confirmed_worker_id")
    if worker_id is None:
        return None
    worker = await queries.get_worker(db, int(worker_id))
    if worker is None:
        return None

    return {
        "cascade_id": int(cascade["id"]),
        "shift_id": resolved_shift_id,
        "worker_id": int(worker["id"]),
        "worker_name": worker.get("name") or "Worker",
        "role": shift.get("role") or "shift",
        "date": shift.get("date") or "",
        "start_time": str(shift.get("start_time") or "")[:5],
    }
