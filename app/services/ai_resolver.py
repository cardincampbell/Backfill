from __future__ import annotations

from datetime import date, timedelta
import re
from typing import Any, Optional

import aiosqlite

from app.db import queries
from app.services import ai_extraction
from app.services import backfill_shifts as backfill_shifts_svc
from app.services import roster as roster_svc


_SCHEDULE_REQUIRED_ACTIONS = {
    "get_schedule_summary",
    "get_unfilled_shifts",
    "get_coverage_status",
    "get_publish_readiness",
    "explain_schedule_issues",
    "publish_schedule",
    "create_open_shift",
    "edit_shift",
    "delete_shift",
    "assign_shift",
    "clear_shift_assignment",
    "open_shift",
    "cancel_open_shift_offer",
    "close_open_shift",
    "reopen_open_shift",
    "reopen_and_offer_open_shift",
}


async def resolve_entities(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    action_type: str,
    channel: str = "web",
    text: str = "",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = dict(context or {})
    location = await queries.get_location(db, location_id)
    if location is None:
        raise ValueError("Location not found")

    extraction = None
    if action_type == "create_open_shift":
        extraction = await ai_extraction.extract_open_shift_creation(
            text=text,
            channel=channel,
            context=context,
        )
        extracted_fields = dict(extraction.fields or {})
        if extracted_fields.get("date") and not context.get("week_start_date"):
            context["target_date"] = extracted_fields["date"]
        context["create_shift_payload"] = extracted_fields
    elif action_type == "edit_shift":
        extraction = await ai_extraction.extract_shift_edit(
            text=text,
            channel=channel,
            context=context,
        )
        context["shift_patch"] = dict(extraction.fields or {})

    schedule = None
    if action_type in _SCHEDULE_REQUIRED_ACTIONS:
        schedule = await _resolve_schedule(
            db,
            location_id=location_id,
            context=context,
            allow_latest_fallback=not bool(context.get("target_date")),
        )

    entities: list[dict[str, Any]] = [
        {
            "entity_type": "location",
            "entity_id": int(location["id"]),
            "raw_reference": location.get("name") or str(location["id"]),
            "normalized_reference": location.get("name") or str(location["id"]),
            "confidence_score": 1.0,
            "resolution_status": "matched",
            "candidate_payload_json": [],
        }
    ]
    if schedule is not None:
        entities.append(
            {
                "entity_type": "schedule",
                "entity_id": int(schedule["id"]),
                "raw_reference": context.get("week_start_date") or schedule.get("week_start_date") or str(schedule["id"]),
                "normalized_reference": schedule.get("week_start_date") or str(schedule["id"]),
                "confidence_score": 0.98,
                "resolution_status": "matched",
                "candidate_payload_json": [],
            }
        )

    action_params = {
        "location_id": int(location["id"]),
        "schedule_id": int(schedule["id"]) if schedule is not None else None,
        "week_start_date": str(schedule["week_start_date"]) if schedule and schedule.get("week_start_date") else context.get("week_start_date"),
    }
    clarification = None

    if action_type in {"approve_fill", "decline_fill"}:
        pending_fill = await _resolve_pending_fill(
            db,
            location_id=location_id,
            action_type=action_type,
            text=text,
            context=context,
        )
        if pending_fill.get("entity"):
            entities.append(pending_fill["entity"])
        if pending_fill.get("action_params"):
            action_params.update(pending_fill["action_params"])
        clarification = pending_fill.get("clarification")
    elif action_type == "open_shift":
        open_shift = await _resolve_open_shift_lifecycle_action(
            db,
            location_id=location_id,
            text=text,
            context=context,
            week_start_date=str(action_params.get("week_start_date") or ""),
            action_type="open_shift",
            required_action="start_coverage",
            prompt="I found {count} open shifts that can start coverage. Which one should I open?",
        )
        if open_shift.get("entity"):
            entities.append(open_shift["entity"])
        if open_shift.get("action_params"):
            action_params.update(open_shift["action_params"])
        clarification = open_shift.get("clarification")
    elif action_type == "cancel_open_shift_offer":
        open_shift = await _resolve_open_shift_lifecycle_action(
            db,
            location_id=location_id,
            text=text,
            context=context,
            week_start_date=str(action_params.get("week_start_date") or ""),
            action_type="cancel_open_shift_offer",
            required_action="cancel_offer",
            prompt="I found {count} open-shift offers that can be cancelled. Which one should I cancel?",
        )
        if open_shift.get("entity"):
            entities.append(open_shift["entity"])
        if open_shift.get("action_params"):
            action_params.update(open_shift["action_params"])
        clarification = open_shift.get("clarification")
    elif action_type == "close_open_shift":
        open_shift = await _resolve_open_shift_lifecycle_action(
            db,
            location_id=location_id,
            text=text,
            context=context,
            week_start_date=str(action_params.get("week_start_date") or ""),
            action_type="close_open_shift",
            required_action="close_shift",
            prompt="I found {count} open shifts that can be closed. Which one should I close?",
        )
        if open_shift.get("entity"):
            entities.append(open_shift["entity"])
        if open_shift.get("action_params"):
            action_params.update(open_shift["action_params"])
        clarification = open_shift.get("clarification")
    elif action_type == "reopen_open_shift":
        closed_shift = await _resolve_closed_open_shift_lifecycle_action(
            db,
            location_id=location_id,
            text=text,
            context=context,
            week_start_date=str(action_params.get("week_start_date") or ""),
            action_type="reopen_open_shift",
            required_action="reopen_shift",
            prompt="I found {count} closed open shifts that can be reopened. Which one should I reopen?",
        )
        if closed_shift.get("entity"):
            entities.append(closed_shift["entity"])
        if closed_shift.get("action_params"):
            action_params.update(closed_shift["action_params"])
        clarification = closed_shift.get("clarification")
    elif action_type == "reopen_and_offer_open_shift":
        closed_shift = await _resolve_closed_open_shift_lifecycle_action(
            db,
            location_id=location_id,
            text=text,
            context=context,
            week_start_date=str(action_params.get("week_start_date") or ""),
            action_type="reopen_and_offer_open_shift",
            required_action="reopen_and_offer",
            prompt="I found {count} closed open shifts that can be reopened and offered. Which one should I send out?",
        )
        if closed_shift.get("entity"):
            entities.append(closed_shift["entity"])
        if closed_shift.get("action_params"):
            action_params.update(closed_shift["action_params"])
        clarification = closed_shift.get("clarification")
    elif action_type == "create_open_shift":
        shift_payload = dict(context.get("create_shift_payload") or {})
        if shift_payload:
            action_params["create_shift_payload"] = shift_payload
            if shift_payload.get("date") and not action_params.get("week_start_date"):
                action_params["week_start_date"] = _week_start_for_date(str(shift_payload["date"]))
        if schedule is not None:
            action_params["schedule_id"] = int(schedule["id"])
    elif action_type == "edit_shift":
        edit_resolution = await _resolve_shift_edit_action(
            db,
            location_id=location_id,
            text=text,
            context=context,
            week_start_date=str(action_params.get("week_start_date") or ""),
            action_type="edit_shift",
        )
        if edit_resolution.get("entity"):
            entities.append(edit_resolution["entity"])
        if edit_resolution.get("action_params"):
            action_params.update(edit_resolution["action_params"])
        clarification = edit_resolution.get("clarification")
    elif action_type == "delete_shift":
        delete_resolution = await _resolve_delete_shift_action(
            db,
            location_id=location_id,
            text=text,
            context=context,
            week_start_date=str(action_params.get("week_start_date") or ""),
            action_type="delete_shift",
        )
        if delete_resolution.get("entity"):
            entities.append(delete_resolution["entity"])
        if delete_resolution.get("action_params"):
            action_params.update(delete_resolution["action_params"])
        clarification = delete_resolution.get("clarification")
    elif action_type == "assign_shift":
        assignment_resolution = await _resolve_shift_assignment_action(
            db,
            location_id=location_id,
            text=text,
            context=context,
            week_start_date=str(action_params.get("week_start_date") or ""),
            action_type="assign_shift",
        )
        if assignment_resolution.get("entities"):
            entities.extend(list(assignment_resolution.get("entities") or []))
        if assignment_resolution.get("action_params"):
            action_params.update(assignment_resolution["action_params"])
        clarification = assignment_resolution.get("clarification")
    elif action_type == "clear_shift_assignment":
        clear_resolution = await _resolve_clear_assignment_action(
            db,
            location_id=location_id,
            text=text,
            context=context,
            week_start_date=str(action_params.get("week_start_date") or ""),
            action_type="clear_shift_assignment",
        )
        if clear_resolution.get("entity"):
            entities.append(clear_resolution["entity"])
        if clear_resolution.get("action_params"):
            action_params.update(clear_resolution["action_params"])
        clarification = clear_resolution.get("clarification")

    return {
        "location": location,
        "schedule": schedule,
        "week_start_date": str(schedule["week_start_date"]) if schedule and schedule.get("week_start_date") else context.get("week_start_date"),
        "entities": entities,
        "action_params": action_params,
        "clarification": clarification,
        "needs_clarification": clarification is not None,
        "extraction": {
            "fields": dict(extraction.fields or {}),
            "runtime": dict(extraction.runtime or {}),
        }
        if extraction is not None
        else None,
    }


async def _resolve_schedule(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    context: dict[str, Any],
    allow_latest_fallback: bool = True,
) -> Optional[dict]:
    explicit_schedule_id = context.get("schedule_id") or context.get("draft_schedule_id")
    if explicit_schedule_id is not None:
        try:
            schedule = await queries.get_schedule(db, int(explicit_schedule_id))
        except (TypeError, ValueError):
            schedule = None
        if schedule is not None and int(schedule["location_id"]) == location_id:
            return schedule

    week_start_date = context.get("week_start_date")
    if isinstance(week_start_date, str) and week_start_date.strip():
        schedule = await queries.get_schedule_by_location_week(
            db,
            location_id=location_id,
            week_start_date=week_start_date.strip(),
        )
        if schedule is not None:
            return schedule

    target_date = context.get("target_date")
    if isinstance(target_date, str) and target_date.strip():
        week_start_date = _week_start_for_date(target_date.strip())
        schedule = await queries.get_schedule_by_location_week(
            db,
            location_id=location_id,
            week_start_date=week_start_date,
        )
        if schedule is not None:
            return schedule
        if not allow_latest_fallback:
            return None

    if not allow_latest_fallback:
        return None
    return await queries.get_latest_schedule_for_location(db, location_id)


async def _resolve_pending_fill(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    action_type: str,
    text: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    queue = await backfill_shifts_svc.get_manager_action_queue(
        db,
        location_id=location_id,
        week_start=context.get("week_start_date"),
    )
    candidates = [item for item in queue.get("actions") or [] if item.get("action_type") == "approve_fill"]
    resolved = _resolve_candidate(
        candidates,
        text=text,
        context=context,
        id_keys=("cascade_id", "shift_id"),
    )
    matched = resolved.get("matched")
    if matched is not None:
        return {
            "entity": {
                "entity_type": "cascade",
                "entity_id": int(matched["cascade_id"]),
                "raw_reference": matched.get("worker_name") or str(matched["cascade_id"]),
                "normalized_reference": str(matched["cascade_id"]),
                "confidence_score": 0.96,
                "resolution_status": "matched",
                "candidate_payload_json": [],
            },
            "action_params": {
                "cascade_id": int(matched["cascade_id"]),
                "shift_id": int(matched["shift_id"]),
            },
        }
    ambiguous = resolved.get("ambiguous") or []
    if ambiguous:
        prompt_action = "approve" if action_type == "approve_fill" else "decline"
        return {
            "clarification": {
                "prompt": f"I found {len(ambiguous)} pending fill approvals. Which one should I {prompt_action}?",
                "candidates": [_build_fill_candidate(item, action_type=action_type) for item in ambiguous],
            }
        }
    return {}


async def _resolve_open_shift_lifecycle_action(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    text: str,
    context: dict[str, Any],
    week_start_date: str,
    action_type: str,
    required_action: str,
    prompt: str,
) -> dict[str, Any]:
    queue = await backfill_shifts_svc.get_schedule_exception_queue(
        db,
        location_id=location_id,
        week_start=week_start_date or context.get("week_start_date"),
        action_required_only=False,
    )
    candidates = [
        item
        for item in queue.get("items") or []
        if required_action in set(item.get("available_actions") or []) and item.get("vacancy_kind") == "open_shift"
    ]
    resolved = _resolve_candidate(
        candidates,
        text=text,
        context=context,
        id_keys=("shift_id",),
    )
    matched = resolved.get("matched")
    if matched is not None:
        return {
            "entity": {
                "entity_type": "shift",
                "entity_id": int(matched["shift_id"]),
                "raw_reference": f"{matched.get('role') or 'shift'} {matched.get('date') or ''}".strip(),
                "normalized_reference": str(matched["shift_id"]),
                "confidence_score": 0.95,
                "resolution_status": "matched",
                "candidate_payload_json": [],
            },
            "action_params": {
                "shift_id": int(matched["shift_id"]),
            },
        }
    ambiguous = resolved.get("ambiguous") or []
    if ambiguous:
        return {
            "clarification": {
                "prompt": prompt.format(count=len(ambiguous)),
                "candidates": [_build_open_shift_candidate(item, action_type=action_type) for item in ambiguous],
            }
        }
    return {}


async def _resolve_closed_open_shift_lifecycle_action(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    text: str,
    context: dict[str, Any],
    week_start_date: str,
    action_type: str,
    required_action: str,
    prompt: str,
) -> dict[str, Any]:
    schedule_view = await backfill_shifts_svc.get_schedule_view(
        db,
        location_id=location_id,
        week_start=week_start_date or context.get("week_start_date"),
    )
    candidates = [
        item
        for item in schedule_view.get("shifts") or []
        if required_action in set(item.get("available_actions") or [])
    ]
    resolved = _resolve_candidate(
        candidates,
        text=text,
        context=context,
        id_keys=("shift_id", "id"),
    )
    matched = resolved.get("matched")
    if matched is not None:
        shift_id = int(matched.get("shift_id") or matched.get("id"))
        return {
            "entity": {
                "entity_type": "shift",
                "entity_id": shift_id,
                "raw_reference": f"{matched.get('role') or 'shift'} {matched.get('date') or ''}".strip(),
                "normalized_reference": str(shift_id),
                "confidence_score": 0.95,
                "resolution_status": "matched",
                "candidate_payload_json": [],
            },
            "action_params": {
                "shift_id": shift_id,
            },
        }
    ambiguous = resolved.get("ambiguous") or []
    if ambiguous:
        return {
            "clarification": {
                "prompt": prompt.format(count=len(ambiguous)),
                "candidates": [_build_closed_open_shift_candidate(item, action_type=action_type) for item in ambiguous],
            }
        }
    return {}


async def _resolve_shift_assignment_action(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    text: str,
    context: dict[str, Any],
    week_start_date: str,
    action_type: str,
) -> dict[str, Any]:
    worker_resolution = await _resolve_location_worker(
        db,
        location_id=location_id,
        text=text,
        context=context,
    )
    resolved_worker = worker_resolution.get("matched")
    worker_entity = None
    if resolved_worker is not None:
        worker_entity = {
            "entity_type": "worker",
            "entity_id": int(resolved_worker["id"]),
            "raw_reference": resolved_worker.get("name") or str(resolved_worker["id"]),
            "normalized_reference": str(resolved_worker["id"]),
            "confidence_score": 0.95,
            "resolution_status": "matched",
            "candidate_payload_json": [],
        }

    schedule_view = await backfill_shifts_svc.get_schedule_view(
        db,
        location_id=location_id,
        week_start=week_start_date or context.get("week_start_date"),
    )
    shift_candidates = [
        _shift_candidate_payload(shift)
        for shift in schedule_view.get("shifts") or []
        if (shift.get("assignment") or {}).get("assignment_status") != "closed"
        and str((shift.get("coverage") or {}).get("status") or "") != "active"
    ]
    resolved_shift = _resolve_candidate(
        shift_candidates,
        text=text,
        context=context,
        id_keys=("shift_id", "id"),
    )
    matched_shift = resolved_shift.get("matched")
    if matched_shift is None:
        ambiguous_shifts = resolved_shift.get("ambiguous") or []
        if ambiguous_shifts:
            return {
                "entities": [worker_entity] if worker_entity else [],
                "clarification": {
                    "prompt": "I found multiple shifts that could be reassigned. Which one should I update?",
                    "candidates": [
                        _build_assignment_shift_candidate(
                            shift,
                            action_type=action_type,
                            worker_id=int(resolved_worker["id"]) if resolved_worker is not None else None,
                        )
                        for shift in ambiguous_shifts
                    ],
                },
            }
        return {"entities": [worker_entity] if worker_entity else []}

    matched_shift_id = int(matched_shift.get("shift_id") or matched_shift.get("id"))
    shift_entity = {
        "entity_type": "shift",
        "entity_id": matched_shift_id,
        "raw_reference": f"{matched_shift.get('role') or 'shift'} {matched_shift.get('date') or ''}".strip(),
        "normalized_reference": str(matched_shift_id),
        "confidence_score": 0.95,
        "resolution_status": "matched",
        "candidate_payload_json": [],
    }
    if resolved_worker is not None:
        return {
            "entities": [entity for entity in (shift_entity, worker_entity) if entity is not None],
            "action_params": {
                "shift_id": matched_shift_id,
                "worker_id": int(resolved_worker["id"]),
            },
        }

    eligible = await roster_svc.list_eligible_workers(
        db,
        location_id=location_id,
        role=str(matched_shift.get("role") or ""),
    )
    eligible_candidates = list(eligible.get("workers") or [])
    resolved_worker = _resolve_candidate(
        [
            {
                "id": int(worker["id"]),
                "worker_name": worker.get("name"),
                "role": matched_shift.get("role"),
            }
            for worker in eligible_candidates
        ],
        text=text,
        context=context,
        id_keys=("worker_id", "id"),
    )
    matched_worker = resolved_worker.get("matched")
    if matched_worker is not None:
        worker_id = int(matched_worker.get("worker_id") or matched_worker.get("id"))
        worker_row = next(
            (worker for worker in eligible_candidates if int(worker["id"]) == worker_id),
            None,
        )
        worker_entity = {
            "entity_type": "worker",
            "entity_id": worker_id,
            "raw_reference": (worker_row or {}).get("name") or str(worker_id),
            "normalized_reference": str(worker_id),
            "confidence_score": 0.94,
            "resolution_status": "matched",
            "candidate_payload_json": [],
        }
        return {
            "entities": [shift_entity, worker_entity],
            "action_params": {
                "shift_id": matched_shift_id,
                "worker_id": worker_id,
            },
        }

    ambiguous_workers = resolved_worker.get("ambiguous") or []
    if ambiguous_workers or eligible_candidates:
        candidates = ambiguous_workers or [
            {"id": int(worker["id"]), "worker_name": worker.get("name"), "role": matched_shift.get("role")}
            for worker in eligible_candidates
        ]
        return {
            "entities": [shift_entity],
            "clarification": {
                "prompt": "Which worker should I assign to that shift?",
                "candidates": [
                    _build_worker_assignment_candidate(
                        item,
                        shift_id=matched_shift_id,
                        action_type=action_type,
                    )
                    for item in candidates
                ],
            },
        }
    return {"entities": [shift_entity]}


async def _resolve_shift_edit_action(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    text: str,
    context: dict[str, Any],
    week_start_date: str,
    action_type: str,
) -> dict[str, Any]:
    schedule_view = await backfill_shifts_svc.get_schedule_view(
        db,
        location_id=location_id,
        week_start=week_start_date or context.get("week_start_date"),
    )
    shift_candidates = [
        _shift_candidate_payload(shift)
        for shift in schedule_view.get("shifts") or []
        if str((shift.get("coverage") or {}).get("status") or "") != "active"
    ]
    resolved_shift = _resolve_candidate(
        shift_candidates,
        text=text,
        context=context,
        id_keys=("shift_id", "id"),
    )
    matched_shift = resolved_shift.get("matched")
    shift_patch = dict(context.get("shift_patch") or {})
    if matched_shift is not None:
        shift_id = int(matched_shift.get("shift_id") or matched_shift.get("id"))
        return {
            "entity": {
                "entity_type": "shift",
                "entity_id": shift_id,
                "raw_reference": f"{matched_shift.get('role') or 'shift'} {matched_shift.get('date') or ''}".strip(),
                "normalized_reference": str(shift_id),
                "confidence_score": 0.95,
                "resolution_status": "matched",
                "candidate_payload_json": [],
            },
            "action_params": {
                "shift_id": shift_id,
                "shift_patch": shift_patch,
            },
        }
    ambiguous = resolved_shift.get("ambiguous") or []
    if ambiguous:
        return {
            "clarification": {
                "prompt": "I found multiple shifts that could be edited. Which one should I update?",
                "candidates": [
                    _build_shift_edit_candidate(shift, action_type=action_type, shift_patch=shift_patch)
                    for shift in ambiguous
                ],
            }
        }
    return {"action_params": {"shift_patch": shift_patch}}


async def _resolve_delete_shift_action(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    text: str,
    context: dict[str, Any],
    week_start_date: str,
    action_type: str,
) -> dict[str, Any]:
    schedule_view = await backfill_shifts_svc.get_schedule_view(
        db,
        location_id=location_id,
        week_start=week_start_date or context.get("week_start_date"),
    )
    shift_candidates = [
        _shift_candidate_payload(shift)
        for shift in schedule_view.get("shifts") or []
        if str((shift.get("coverage") or {}).get("status") or "") != "active"
    ]
    resolved_shift = _resolve_candidate(
        shift_candidates,
        text=text,
        context=context,
        id_keys=("shift_id", "id"),
    )
    matched_shift = resolved_shift.get("matched")
    if matched_shift is not None:
        shift_id = int(matched_shift.get("shift_id") or matched_shift.get("id"))
        return {
            "entity": {
                "entity_type": "shift",
                "entity_id": shift_id,
                "raw_reference": f"{matched_shift.get('role') or 'shift'} {matched_shift.get('date') or ''}".strip(),
                "normalized_reference": str(shift_id),
                "confidence_score": 0.95,
                "resolution_status": "matched",
                "candidate_payload_json": [],
            },
            "action_params": {
                "shift_id": shift_id,
            },
        }
    ambiguous = resolved_shift.get("ambiguous") or []
    if ambiguous:
        return {
            "clarification": {
                "prompt": "I found multiple shifts that could be deleted. Which one should I remove?",
                "candidates": [
                    _build_delete_shift_candidate(shift, action_type=action_type)
                    for shift in ambiguous
                ],
            }
        }
    return {}


async def _resolve_clear_assignment_action(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    text: str,
    context: dict[str, Any],
    week_start_date: str,
    action_type: str,
) -> dict[str, Any]:
    schedule_view = await backfill_shifts_svc.get_schedule_view(
        db,
        location_id=location_id,
        week_start=week_start_date or context.get("week_start_date"),
    )
    shift_candidates = [
        _shift_candidate_payload(shift)
        for shift in schedule_view.get("shifts") or []
        if (shift.get("assignment") or {}).get("worker_id") is not None
        and (shift.get("assignment") or {}).get("assignment_status") in {"assigned", "claimed", "confirmed"}
        and str((shift.get("coverage") or {}).get("status") or "") != "active"
    ]
    resolved_shift = _resolve_candidate(
        shift_candidates,
        text=text,
        context=context,
        id_keys=("shift_id", "id"),
    )
    matched_shift = resolved_shift.get("matched")
    if matched_shift is not None:
        shift_id = int(matched_shift.get("shift_id") or matched_shift.get("id"))
        return {
            "entity": {
                "entity_type": "shift",
                "entity_id": shift_id,
                "raw_reference": f"{matched_shift.get('role') or 'shift'} {matched_shift.get('date') or ''}".strip(),
                "normalized_reference": str(shift_id),
                "confidence_score": 0.95,
                "resolution_status": "matched",
                "candidate_payload_json": [],
            },
            "action_params": {
                "shift_id": shift_id,
            },
        }
    ambiguous = resolved_shift.get("ambiguous") or []
    if ambiguous:
        return {
            "clarification": {
                "prompt": "I found multiple assigned shifts that could be cleared. Which one should I open back up?",
                "candidates": [
                    _build_assignment_shift_candidate(shift, action_type=action_type)
                    for shift in ambiguous
                ],
            }
        }
    return {}


async def _resolve_location_worker(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    text: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    roster = await roster_svc.list_roster_for_location(db, location_id=location_id, include_inactive=False)
    candidates = [
        {
            "id": int(worker["id"]),
            "worker_name": worker.get("name"),
            "role": " ".join(worker.get("roles") or []),
        }
        for worker in roster.get("workers") or []
        if worker.get("is_active_at_location")
    ]
    explicit_worker_id = context.get("worker_id")
    if explicit_worker_id is not None:
        try:
            target_id = int(explicit_worker_id)
        except (TypeError, ValueError):
            return {}
        for candidate in candidates:
            if int(candidate["id"]) == target_id:
                return {"matched": candidate}
        return {}
    return _resolve_candidate(
        candidates,
        text=text,
        context=context,
        id_keys=("worker_id", "id"),
    )


def _resolve_candidate(
    candidates: list[dict[str, Any]],
    *,
    text: str,
    context: dict[str, Any],
    id_keys: tuple[str, ...],
) -> dict[str, Any]:
    for key in id_keys:
        raw_value = context.get(key)
        if raw_value is None:
            continue
        try:
            target_value = int(raw_value)
        except (TypeError, ValueError):
            continue
        for candidate in candidates:
            try:
                if int(candidate.get(key) or 0) == target_value:
                    return {"matched": candidate}
            except (TypeError, ValueError):
                continue

    if len(candidates) == 1:
        return {"matched": candidates[0]}

    matched_by_text = _match_candidates_by_text(candidates, text=text)
    if len(matched_by_text) == 1:
        return {"matched": matched_by_text[0]}
    if len(matched_by_text) > 1:
        return {"ambiguous": matched_by_text}
    if len(candidates) > 1:
        return {"ambiguous": candidates}
    return {}


def _match_candidates_by_text(candidates: list[dict[str, Any]], *, text: str) -> list[dict[str, Any]]:
    normalized_text = _normalize_text(text)
    if not normalized_text:
        return []

    scored: list[tuple[int, dict[str, Any]]] = []
    for candidate in candidates:
        score = _candidate_match_score(candidate, normalized_text=normalized_text)
        if score > 0:
            scored.append((score, candidate))
    if not scored:
        return []

    best_score = max(score for score, _ in scored)
    return [candidate for score, candidate in scored if score == best_score]


def _candidate_match_score(candidate: dict[str, Any], *, normalized_text: str) -> int:
    score = 0
    shift_id = candidate.get("shift_id")
    cascade_id = candidate.get("cascade_id")
    if shift_id is not None and _text_mentions_id(normalized_text, int(shift_id), label="shift"):
        score += 100
    if cascade_id is not None and _text_mentions_id(normalized_text, int(cascade_id), label="cascade"):
        score += 100

    for value in (
        candidate.get("worker_name"),
        candidate.get("role"),
        candidate.get("date"),
    ):
        normalized_value = _normalize_text(value)
        if normalized_value and normalized_value in normalized_text:
            score += 25
        for token in normalized_value.split():
            if len(token) >= 3 and token in normalized_text.split():
                score += 8

    time_text = str(candidate.get("start_time") or "")
    if time_text:
        compact_time = time_text[:5]
        if compact_time and compact_time in normalized_text:
            score += 10
    return score


def _text_mentions_id(normalized_text: str, identifier: int, *, label: str) -> bool:
    text_tokens = normalized_text.split()
    raw_id = str(identifier)
    return raw_id in text_tokens or f"{label} {raw_id}" in normalized_text or f"#{raw_id}" in normalized_text


def _normalize_text(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    normalized = re.sub(r"[_/:-]+", " ", raw)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _build_fill_candidate(item: dict[str, Any], *, action_type: str) -> dict[str, Any]:
    shift_id = int(item["shift_id"])
    cascade_id = int(item["cascade_id"])
    label = f"{item.get('worker_name') or 'Worker'} · {item.get('role') or 'shift'} · {item.get('date')} {str(item.get('start_time') or '')[:5]}".strip()
    return {
        "option_key": f"cascade:{cascade_id}",
        "label": label,
        "worker_name": item.get("worker_name"),
        "role": item.get("role"),
        "date": item.get("date"),
        "start_time": item.get("start_time"),
        "shift_id": shift_id,
        "cascade_id": cascade_id,
        "proposed_action": {
            "action_type": action_type,
            "params": {
                "cascade_id": cascade_id,
                "shift_id": shift_id,
            },
        },
    }


def _build_open_shift_candidate(item: dict[str, Any], *, action_type: str = "open_shift") -> dict[str, Any]:
    shift_id = int(item["shift_id"])
    label = f"{item.get('role') or 'Shift'} · {item.get('date')} {str(item.get('start_time') or '')[:5]}".strip()
    return {
        "option_key": f"shift:{shift_id}",
        "label": label,
        "role": item.get("role"),
        "date": item.get("date"),
        "start_time": item.get("start_time"),
        "shift_id": shift_id,
        "code": item.get("code"),
        "proposed_action": {
            "action_type": action_type,
            "params": {
                "shift_id": shift_id,
            },
        },
    }


def _build_closed_open_shift_candidate(item: dict[str, Any], *, action_type: str) -> dict[str, Any]:
    shift_id = int(item.get("shift_id") or item.get("id"))
    label = f"{item.get('role') or 'Shift'} · {item.get('date')} {str(item.get('start_time') or '')[:5]}".strip()
    return {
        "option_key": f"shift:{shift_id}",
        "label": label,
        "role": item.get("role"),
        "date": item.get("date"),
        "start_time": item.get("start_time"),
        "shift_id": shift_id,
        "proposed_action": {
            "action_type": action_type,
            "params": {
                "shift_id": shift_id,
            },
        },
    }


def _build_assignment_shift_candidate(
    item: dict[str, Any],
    *,
    action_type: str,
    worker_id: int | None = None,
) -> dict[str, Any]:
    shift_id = int(item.get("shift_id") or item.get("id"))
    assignment = item.get("assignment") or {}
    label = f"{item.get('role') or 'Shift'} · {item.get('date')} {str(item.get('start_time') or '')[:5]}".strip()
    if assignment.get("worker_name"):
        label += f" · {assignment.get('worker_name')}"
    params: dict[str, Any] = {"shift_id": shift_id}
    if worker_id is not None:
        params["worker_id"] = worker_id
    return {
        "option_key": f"shift:{shift_id}",
        "label": label,
        "role": item.get("role"),
        "date": item.get("date"),
        "start_time": item.get("start_time"),
        "shift_id": shift_id,
        "proposed_action": {
            "action_type": action_type,
            "params": params,
        },
    }


def _build_shift_edit_candidate(
    item: dict[str, Any],
    *,
    action_type: str,
    shift_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    shift_id = int(item.get("shift_id") or item.get("id"))
    assignment = item.get("assignment") or {}
    label = f"{item.get('role') or 'Shift'} · {item.get('date')} {str(item.get('start_time') or '')[:5]}".strip()
    if assignment.get("worker_name"):
        label += f" · {assignment.get('worker_name')}"
    return {
        "option_key": f"shift:{shift_id}",
        "label": label,
        "role": item.get("role"),
        "date": item.get("date"),
        "start_time": item.get("start_time"),
        "shift_id": shift_id,
        "proposed_action": {
            "action_type": action_type,
            "params": {
                "shift_id": shift_id,
                "shift_patch": dict(shift_patch or {}),
            },
        },
    }


def _build_delete_shift_candidate(
    item: dict[str, Any],
    *,
    action_type: str,
) -> dict[str, Any]:
    shift_id = int(item.get("shift_id") or item.get("id"))
    assignment = item.get("assignment") or {}
    label = f"{item.get('role') or 'Shift'} · {item.get('date')} {str(item.get('start_time') or '')[:5]}".strip()
    if assignment.get("worker_name"):
        label += f" · {assignment.get('worker_name')}"
    return {
        "option_key": f"shift:{shift_id}",
        "label": label,
        "role": item.get("role"),
        "date": item.get("date"),
        "start_time": item.get("start_time"),
        "shift_id": shift_id,
        "proposed_action": {
            "action_type": action_type,
            "params": {
                "shift_id": shift_id,
            },
        },
    }


def _build_worker_assignment_candidate(
    item: dict[str, Any],
    *,
    shift_id: int,
    action_type: str,
) -> dict[str, Any]:
    worker_id = int(item.get("worker_id") or item.get("id"))
    worker_name = item.get("worker_name") or "Worker"
    return {
        "option_key": f"worker:{worker_id}",
        "label": str(worker_name),
        "worker_name": worker_name,
        "worker_id": worker_id,
        "proposed_action": {
            "action_type": action_type,
            "params": {
                "shift_id": shift_id,
                "worker_id": worker_id,
            },
        },
    }


def _shift_candidate_payload(shift: dict[str, Any]) -> dict[str, Any]:
    payload = dict(shift)
    assignment = shift.get("assignment") or {}
    if assignment.get("worker_name") and not payload.get("worker_name"):
        payload["worker_name"] = assignment.get("worker_name")
    return payload


def _week_start_for_date(value: str) -> str | None:
    try:
        target = date.fromisoformat(value)
    except ValueError:
        return None
    return (target - timedelta(days=target.weekday())).isoformat()
