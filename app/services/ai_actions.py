from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import aiosqlite

from app.config import settings
from app.db import queries
from app.services import ai_executor, ai_intent, ai_planner, ai_policy, ai_renderers, ai_resolver
from app.services import notifications as notifications_svc
from app.services.auth import AuthPrincipal


def _session_expires_at() -> str:
    return (datetime.utcnow() + timedelta(minutes=settings.backfill_ai_action_session_ttl_minutes)).isoformat()


async def handle_web_action(
    db: aiosqlite.Connection,
    *,
    principal: AuthPrincipal,
    location_id: int,
    text: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = dict(context or {})
    now = datetime.utcnow().isoformat()
    actor_id = int(principal.session_id or 0)
    request_id = await queries.insert_ai_action_request(
        db,
        {
            "channel": "web",
            "actor_type": "manager",
            "actor_id": actor_id,
            "organization_id": principal.organization_id,
            "location_id": location_id,
            "original_text": text,
            "intent_type": "received",
            "status": "received",
            "risk_class": None,
            "requires_confirmation": False,
            "redirect_reason": None,
            "action_plan_json": {},
            "result_summary_json": {},
            "created_at": now,
            "updated_at": now,
        },
    )
    await queries.insert_ai_action_event(
        db,
        {
            "ai_action_request_id": request_id,
            "event_type": "received",
            "payload_json": {"text": text, "context": context},
            "created_at": now,
        },
    )
    await queries.update_ai_action_request(db, request_id, {"status": "resolving"})

    classification = await ai_intent.classify_intent(text=text, channel="web")
    intent = classification.intent
    await queries.update_ai_action_request(
        db,
        request_id,
        {
            "intent_type": intent.get("intent_type"),
            "status": "resolving",
        },
    )
    await queries.insert_ai_action_event(
        db,
        {
            "ai_action_request_id": request_id,
            "event_type": "parsed",
            "payload_json": {
                "intent": intent,
                "runtime": classification.runtime,
            },
            "created_at": datetime.utcnow().isoformat(),
        },
    )

    resolution = await ai_resolver.resolve_entities(
        db,
        location_id=location_id,
        action_type=str((intent.get("action_candidates") or ["get_schedule_summary"])[0]),
        channel="web",
        text=text,
        context=context,
    )
    for entity in resolution.get("entities") or []:
        await queries.insert_ai_action_entity(
            db,
            {
                "ai_action_request_id": request_id,
                "entity_type": entity.get("entity_type"),
                "entity_id": entity.get("entity_id"),
                "raw_reference": entity.get("raw_reference"),
                "normalized_reference": entity.get("normalized_reference"),
                "confidence_score": entity.get("confidence_score"),
                "resolution_status": entity.get("resolution_status"),
                "candidate_payload_json": entity.get("candidate_payload_json") or [],
                "created_at": datetime.utcnow().isoformat(),
            },
        )
    await queries.insert_ai_action_event(
        db,
        {
            "ai_action_request_id": request_id,
            "event_type": "resolved",
            "payload_json": {
                "schedule_id": int(resolution["schedule"]["id"]) if resolution.get("schedule") else None,
                "week_start_date": resolution.get("week_start_date"),
                "extraction": resolution.get("extraction"),
            },
            "created_at": datetime.utcnow().isoformat(),
        },
    )

    plan = await ai_planner.build_action_plan(
        intent=intent,
        resolution=resolution,
        channel="web",
    )
    await queries.update_ai_action_request(
        db,
        request_id,
        {
            "risk_class": plan.get("risk_class"),
            "requires_confirmation": bool(plan.get("requires_confirmation")),
            "redirect_reason": plan.get("redirect_reason"),
            "action_plan_json": plan,
        },
    )
    await queries.insert_ai_action_event(
        db,
        {
            "ai_action_request_id": request_id,
            "event_type": "planned",
            "payload_json": plan,
            "created_at": datetime.utcnow().isoformat(),
        },
    )

    policy = await ai_policy.evaluate_policy(channel="web", action_type=str(plan.get("action_type") or ""))
    if not bool(plan.get("supported")) or not policy.get("allowed"):
        response = ai_renderers.build_redirect_response(
            action_request_id=request_id,
            summary="That action is not enabled in the AI layer yet. Use the structured Backfill UI for now.",
            reason=str(plan.get("redirect_reason") or policy.get("redirect_reason") or "unsupported_action"),
            url=f"/dashboard/locations/{location_id}",
            label="Open location workspace",
        )
        await _persist_response(
            db,
            request_id=request_id,
            status="redirected",
            response=response,
            event_type="redirected",
            runtime=classification.runtime,
        )
        return response

    if bool(plan.get("requires_clarification")):
        clarification = dict(plan.get("clarification") or {})
        indexed_candidates = _options_with_indexes(list(clarification.get("candidates") or []))
        response = ai_renderers.build_clarification_response(
            action_request_id=request_id,
            summary=str(clarification.get("prompt") or "I need one more detail before I can do that."),
            risk_class=str(plan.get("risk_class") or "yellow"),
            clarification_prompt=str(clarification.get("prompt") or "Choose one option."),
            candidates=indexed_candidates,
        )
        await _persist_response(
            db,
            request_id=request_id,
            status="awaiting_clarification",
            response=response,
            event_type="clarification_requested",
            runtime=classification.runtime,
        )
        await queries.insert_action_session(
            db,
            {
                "ai_action_request_id": request_id,
                "channel": "web",
                "actor_type": "manager",
                "actor_id": actor_id,
                "organization_id": principal.organization_id,
                "location_id": location_id,
                "status": "active",
                "pending_prompt_type": "clarification",
                "pending_payload_json": {
                    "action_type": plan.get("action_type"),
                    "risk_class": plan.get("risk_class"),
                    "requires_confirmation": bool(plan.get("requires_confirmation")),
                    "options": indexed_candidates,
                },
                "expires_at": _session_expires_at(),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            },
        )
        return response

    proposed = dict((plan.get("proposed_actions") or [{}])[0] or {})
    params = dict(proposed.get("params") or {})
    actor = f"dashboard_session:{principal.session_id}" if principal.session_id is not None else "dashboard"
    response = await ai_executor.execute_action(
        db,
        action_request_id=request_id,
        action_type=str(plan.get("action_type")),
        location_id=int(params.get("location_id") or location_id),
        schedule_id=params.get("schedule_id"),
        week_start_date=params.get("week_start_date"),
        shift_id=params.get("shift_id"),
        worker_id=params.get("worker_id"),
        cascade_id=params.get("cascade_id"),
        create_shift_payload=dict(params.get("create_shift_payload") or {}),
        shift_patch=dict(params.get("shift_patch") or {}),
        actor=actor,
        confirmed=False,
    )

    next_status = str(response.get("status") or "completed")
    await _persist_response(
        db,
        request_id=request_id,
        status=next_status,
        response=response,
        event_type="completed" if next_status == "completed" else "confirmation_requested" if next_status == "awaiting_confirmation" else next_status,
        runtime=classification.runtime,
    )
    if next_status == "awaiting_confirmation":
        await queries.insert_action_session(
            db,
            {
                "ai_action_request_id": request_id,
                "channel": "web",
                "actor_type": "manager",
                "actor_id": actor_id,
                "organization_id": principal.organization_id,
                "location_id": location_id,
                "status": "active",
                "pending_prompt_type": "confirmation",
                "pending_payload_json": response.get("confirmation") or {},
                "expires_at": _session_expires_at(),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            },
        )
    return response


async def handle_manager_sms_action(
    db: aiosqlite.Connection,
    *,
    location: dict[str, Any],
    phone: str,
    text: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return await _handle_manager_channel_action(
        db,
        location=location,
        phone=phone,
        text=text,
        channel="sms",
        context=context,
    )


async def handle_manager_voice_action(
    db: aiosqlite.Connection,
    *,
    location: dict[str, Any],
    phone: str,
    text: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return await _handle_manager_channel_action(
        db,
        location=location,
        phone=phone,
        text=text,
        channel="voice",
        context=context,
    )


async def _handle_manager_channel_action(
    db: aiosqlite.Connection,
    *,
    location: dict[str, Any],
    phone: str,
    text: str,
    channel: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = dict(context or {})
    now = datetime.utcnow().isoformat()
    location_id = int(location["id"])
    request_id = await queries.insert_ai_action_request(
        db,
        {
            "channel": channel,
            "actor_type": "manager",
            "actor_id": location_id,
            "organization_id": location.get("organization_id"),
            "location_id": location_id,
            "original_text": text,
            "intent_type": "received",
            "status": "received",
            "risk_class": None,
            "requires_confirmation": False,
            "redirect_reason": None,
            "action_plan_json": {},
            "result_summary_json": {},
            "created_at": now,
            "updated_at": now,
        },
    )
    await queries.insert_ai_action_event(
        db,
        {
            "ai_action_request_id": request_id,
            "event_type": "received",
            "payload_json": {"text": text, "context": context, "phone": phone},
            "created_at": now,
        },
    )
    await queries.update_ai_action_request(db, request_id, {"status": "resolving"})

    classification = await ai_intent.classify_intent(text=text, channel=channel)
    intent = classification.intent
    await queries.update_ai_action_request(
        db,
        request_id,
        {
            "intent_type": intent.get("intent_type"),
            "status": "resolving",
        },
    )
    await queries.insert_ai_action_event(
        db,
        {
            "ai_action_request_id": request_id,
            "event_type": "parsed",
            "payload_json": {
                "intent": intent,
                "runtime": classification.runtime,
            },
            "created_at": datetime.utcnow().isoformat(),
        },
    )

    resolution = await ai_resolver.resolve_entities(
        db,
        location_id=location_id,
        action_type=str((intent.get("action_candidates") or ["get_schedule_summary"])[0]),
        channel=channel,
        text=text,
        context=context,
    )
    for entity in resolution.get("entities") or []:
        await queries.insert_ai_action_entity(
            db,
            {
                "ai_action_request_id": request_id,
                "entity_type": entity.get("entity_type"),
                "entity_id": entity.get("entity_id"),
                "raw_reference": entity.get("raw_reference"),
                "normalized_reference": entity.get("normalized_reference"),
                "confidence_score": entity.get("confidence_score"),
                "resolution_status": entity.get("resolution_status"),
                "candidate_payload_json": entity.get("candidate_payload_json") or [],
                "created_at": datetime.utcnow().isoformat(),
            },
        )
    await queries.insert_ai_action_event(
        db,
        {
            "ai_action_request_id": request_id,
            "event_type": "resolved",
            "payload_json": {
                "schedule_id": int(resolution["schedule"]["id"]) if resolution.get("schedule") else None,
                "week_start_date": resolution.get("week_start_date"),
                "extraction": resolution.get("extraction"),
            },
            "created_at": datetime.utcnow().isoformat(),
        },
    )

    plan = await ai_planner.build_action_plan(
        intent=intent,
        resolution=resolution,
        channel=channel,
    )
    await queries.update_ai_action_request(
        db,
        request_id,
        {
            "risk_class": plan.get("risk_class"),
            "requires_confirmation": bool(plan.get("requires_confirmation")),
            "redirect_reason": plan.get("redirect_reason"),
            "action_plan_json": plan,
        },
    )
    await queries.insert_ai_action_event(
        db,
        {
            "ai_action_request_id": request_id,
            "event_type": "planned",
            "payload_json": plan,
            "created_at": datetime.utcnow().isoformat(),
        },
    )

    policy = await ai_policy.evaluate_policy(channel=channel, action_type=str(plan.get("action_type") or ""))
    if not bool(plan.get("supported")) or not policy.get("allowed"):
        response = ai_renderers.build_redirect_response(
            action_request_id=request_id,
            summary=(
                "That action is not enabled by text yet. Open the Backfill dashboard for the full workflow."
                if channel == "sms"
                else "That action is not enabled by voice yet. Open the Backfill dashboard for the full workflow."
            ),
            reason=str(plan.get("redirect_reason") or policy.get("redirect_reason") or "unsupported_action"),
            url=(
                notifications_svc.build_manager_dashboard_link(
                    location_id,
                    tab="schedule",
                    week_start=str((resolution.get("schedule") or {}).get("week_start_date") or ""),
                )
                if resolution.get("schedule")
                else f"/dashboard/locations/{location_id}"
            ),
            label="Open location workspace",
        )
        await _persist_response(
            db,
            request_id=request_id,
            status="redirected",
            response=response,
            event_type="redirected",
            runtime=classification.runtime,
        )
        return response

    if bool(plan.get("requires_clarification")):
        clarification = dict(plan.get("clarification") or {})
        indexed_candidates = _options_with_indexes(list(clarification.get("candidates") or []))
        response = ai_renderers.build_clarification_response(
            action_request_id=request_id,
            summary=str(clarification.get("prompt") or "I need one more detail before I can do that."),
            risk_class=str(plan.get("risk_class") or "yellow"),
            clarification_prompt=str(clarification.get("prompt") or "Choose one option."),
            candidates=indexed_candidates,
        )
        await _persist_response(
            db,
            request_id=request_id,
            status="awaiting_clarification",
            response=response,
            event_type="clarification_requested",
            runtime=classification.runtime,
        )
        await queries.insert_action_session(
            db,
            {
                "ai_action_request_id": request_id,
                "channel": channel,
                "actor_type": "manager",
                "actor_id": location_id,
                "organization_id": location.get("organization_id"),
                "location_id": location_id,
                "status": "active",
                "pending_prompt_type": "clarification",
                "pending_payload_json": {
                    "action_type": plan.get("action_type"),
                    "risk_class": plan.get("risk_class"),
                    "requires_confirmation": bool(plan.get("requires_confirmation")),
                    "options": indexed_candidates,
                },
                "expires_at": _session_expires_at(),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            },
        )
        return response

    proposed = dict((plan.get("proposed_actions") or [{}])[0] or {})
    params = dict(proposed.get("params") or {})
    response = await ai_executor.execute_action(
        db,
        action_request_id=request_id,
        action_type=str(plan.get("action_type")),
        location_id=int(params.get("location_id") or location_id),
        schedule_id=params.get("schedule_id"),
        week_start_date=params.get("week_start_date"),
        shift_id=params.get("shift_id"),
        worker_id=params.get("worker_id"),
        cascade_id=params.get("cascade_id"),
        create_shift_payload=dict(params.get("create_shift_payload") or {}),
        shift_patch=dict(params.get("shift_patch") or {}),
        actor=f"manager_{channel}:{phone}",
        confirmed=False,
    )
    next_status = str(response.get("status") or "completed")
    await _persist_response(
        db,
        request_id=request_id,
        status=next_status,
        response=response,
        event_type="completed" if next_status == "completed" else "confirmation_requested" if next_status == "awaiting_confirmation" else next_status,
        runtime=classification.runtime,
    )
    if next_status == "awaiting_confirmation":
        await queries.insert_action_session(
            db,
            {
                "ai_action_request_id": request_id,
                "channel": channel,
                "actor_type": "manager",
                "actor_id": location_id,
                "organization_id": location.get("organization_id"),
                "location_id": location_id,
                "status": "active",
                "pending_prompt_type": "confirmation",
                "pending_payload_json": response.get("confirmation") or {},
                "expires_at": _session_expires_at(),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            },
        )
    return response


async def get_action_request_detail(
    db: aiosqlite.Connection,
    *,
    principal: AuthPrincipal,
    action_request_id: int,
) -> dict[str, Any]:
    request_row = await queries.get_ai_action_request(db, action_request_id)
    if request_row is None:
        raise ValueError("AI action request not found")
    await _ensure_request_access(principal, request_row)
    session = await queries.get_action_session_by_request_id(db, action_request_id)
    if session is not None and _is_session_expired(session) and request_row.get("status") in {"awaiting_confirmation", "awaiting_clarification", "resolving"}:
        return await _expire_request_session(db, request_row=request_row, session=session)
    stored = dict(request_row.get("result_summary_json") or {})
    if stored:
        return stored
    return {
        "action_request_id": action_request_id,
        "status": request_row.get("status"),
        "mode": "result",
        "summary": str(request_row.get("original_text") or "").strip() or "AI action request",
        "risk_class": request_row.get("risk_class"),
        "requires_confirmation": bool(request_row.get("requires_confirmation")),
        "next_actions": [],
    }


async def confirm_action_request(
    db: aiosqlite.Connection,
    *,
    principal: AuthPrincipal,
    action_request_id: int,
) -> dict[str, Any]:
    request_row = await queries.get_ai_action_request(db, action_request_id)
    if request_row is None:
        raise ValueError("AI action request not found")
    await _ensure_request_access(principal, request_row)
    if request_row.get("status") != "awaiting_confirmation":
        raise ValueError("AI action request is not awaiting confirmation")
    session = await queries.get_action_session_by_request_id(db, action_request_id)
    if session is not None and _is_session_expired(session):
        return await _expire_request_session(db, request_row=request_row, session=session)

    plan = dict(request_row.get("action_plan_json") or {})
    proposed = dict((plan.get("proposed_actions") or [{}])[0] or {})
    params = dict(proposed.get("params") or {})
    actor = f"dashboard_session:{principal.session_id}" if principal.session_id is not None else "dashboard"
    response = await ai_executor.execute_action(
        db,
        action_request_id=action_request_id,
        action_type=str(plan.get("action_type")),
        location_id=int(params.get("location_id") or request_row["location_id"]),
        schedule_id=params.get("schedule_id"),
        week_start_date=params.get("week_start_date"),
        shift_id=params.get("shift_id"),
        worker_id=params.get("worker_id"),
        cascade_id=params.get("cascade_id"),
        create_shift_payload=dict(params.get("create_shift_payload") or {}),
        shift_patch=dict(params.get("shift_patch") or {}),
        actor=actor,
        confirmed=True,
    )
    await _persist_response(
        db,
        request_id=action_request_id,
        status=str(response.get("status") or "completed"),
        response=response,
        event_type="completed",
    )
    session = await queries.get_action_session_by_request_id(db, action_request_id)
    if session is not None:
        await queries.update_action_session(
            db,
            int(session["id"]),
            {"status": "completed", "updated_at": datetime.utcnow().isoformat()},
        )
    return response


async def cancel_action_request(
    db: aiosqlite.Connection,
    *,
    principal: AuthPrincipal,
    action_request_id: int,
) -> dict[str, Any]:
    request_row = await queries.get_ai_action_request(db, action_request_id)
    if request_row is None:
        raise ValueError("AI action request not found")
    await _ensure_request_access(principal, request_row)
    response = ai_renderers.build_cancelled_response(action_request_id=action_request_id)
    await _persist_response(
        db,
        request_id=action_request_id,
        status="cancelled",
        response=response,
        event_type="cancelled",
    )
    session = await queries.get_action_session_by_request_id(db, action_request_id)
    if session is not None:
        await queries.update_action_session(
            db,
            int(session["id"]),
            {"status": "cancelled", "updated_at": datetime.utcnow().isoformat()},
        )
    return response


async def clarify_action_request(
    db: aiosqlite.Connection,
    *,
    principal: AuthPrincipal,
    action_request_id: int,
    selection: dict[str, Any],
) -> dict[str, Any]:
    request_row = await queries.get_ai_action_request(db, action_request_id)
    if request_row is None:
        raise ValueError("AI action request not found")
    await _ensure_request_access(principal, request_row)
    if request_row.get("status") != "awaiting_clarification":
        raise ValueError("AI action request is not awaiting clarification")
    session = await queries.get_action_session_by_request_id(db, action_request_id)
    if session is None or session.get("status") != "active" or session.get("pending_prompt_type") != "clarification":
        raise ValueError("AI action request is not awaiting clarification")
    if _is_session_expired(session):
        return await _expire_request_session(db, request_row=request_row, session=session)

    option = _match_clarification_option(
        list((session.get("pending_payload_json") or {}).get("options") or []),
        selection,
    )
    if option is None:
        raise ValueError("Selected clarification option was not found")

    plan = dict(request_row.get("action_plan_json") or {})
    plan["requires_clarification"] = False
    plan["clarification"] = None
    plan["proposed_actions"] = [dict(option.get("proposed_action") or {})]
    await queries.update_ai_action_request(
        db,
        action_request_id,
        {
            "status": "resolving",
            "action_plan_json": plan,
        },
    )
    await queries.insert_ai_action_event(
        db,
        {
            "ai_action_request_id": action_request_id,
            "event_type": "clarified",
            "payload_json": {"selection": selection, "option": option},
            "created_at": datetime.utcnow().isoformat(),
        },
    )

    proposed = dict((plan.get("proposed_actions") or [{}])[0] or {})
    params = dict(proposed.get("params") or {})
    actor = f"dashboard_session:{principal.session_id}" if principal.session_id is not None else "dashboard"
    response = await ai_executor.execute_action(
        db,
        action_request_id=action_request_id,
        action_type=str(plan.get("action_type")),
        location_id=int(params.get("location_id") or request_row["location_id"]),
        schedule_id=params.get("schedule_id"),
        week_start_date=params.get("week_start_date"),
        shift_id=params.get("shift_id"),
        worker_id=params.get("worker_id"),
        cascade_id=params.get("cascade_id"),
        create_shift_payload=dict(params.get("create_shift_payload") or {}),
        shift_patch=dict(params.get("shift_patch") or {}),
        actor=actor,
        confirmed=False,
    )
    next_status = str(response.get("status") or "completed")
    await _persist_response(
        db,
        request_id=action_request_id,
        status=next_status,
        response=response,
        event_type="completed" if next_status == "completed" else "confirmation_requested" if next_status == "awaiting_confirmation" else next_status,
    )
    if next_status == "awaiting_confirmation":
        await queries.update_action_session(
            db,
            int(session["id"]),
            {
                "pending_prompt_type": "confirmation",
                "pending_payload_json": response.get("confirmation") or {},
                "updated_at": datetime.utcnow().isoformat(),
            },
        )
    else:
        await queries.update_action_session(
            db,
            int(session["id"]),
            {"status": "completed", "updated_at": datetime.utcnow().isoformat()},
        )
    return response


async def confirm_action_request_for_location(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    action_request_id: int,
    actor: str,
) -> dict[str, Any]:
    request_row = await queries.get_ai_action_request(db, action_request_id)
    if request_row is None:
        raise ValueError("AI action request not found")
    if int(request_row["location_id"]) != location_id:
        raise ValueError("Forbidden for this AI action request")
    if request_row.get("status") != "awaiting_confirmation":
        raise ValueError("AI action request is not awaiting confirmation")
    session = await queries.get_action_session_by_request_id(db, action_request_id)
    if session is not None and _is_session_expired(session):
        return await _expire_request_session(db, request_row=request_row, session=session)

    plan = dict(request_row.get("action_plan_json") or {})
    proposed = dict((plan.get("proposed_actions") or [{}])[0] or {})
    params = dict(proposed.get("params") or {})
    response = await ai_executor.execute_action(
        db,
        action_request_id=action_request_id,
        action_type=str(plan.get("action_type")),
        location_id=int(params.get("location_id") or request_row["location_id"]),
        schedule_id=params.get("schedule_id"),
        week_start_date=params.get("week_start_date"),
        shift_id=params.get("shift_id"),
        worker_id=params.get("worker_id"),
        cascade_id=params.get("cascade_id"),
        create_shift_payload=dict(params.get("create_shift_payload") or {}),
        shift_patch=dict(params.get("shift_patch") or {}),
        actor=actor,
        confirmed=True,
    )
    await _persist_response(
        db,
        request_id=action_request_id,
        status=str(response.get("status") or "completed"),
        response=response,
        event_type="completed",
    )
    session = await queries.get_action_session_by_request_id(db, action_request_id)
    if session is not None:
        await queries.update_action_session(
            db,
            int(session["id"]),
            {"status": "completed", "updated_at": datetime.utcnow().isoformat()},
        )
    return response


async def cancel_action_request_for_location(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    action_request_id: int,
) -> dict[str, Any]:
    request_row = await queries.get_ai_action_request(db, action_request_id)
    if request_row is None:
        raise ValueError("AI action request not found")
    if int(request_row["location_id"]) != location_id:
        raise ValueError("Forbidden for this AI action request")
    response = ai_renderers.build_cancelled_response(action_request_id=action_request_id)
    await _persist_response(
        db,
        request_id=action_request_id,
        status="cancelled",
        response=response,
        event_type="cancelled",
    )
    session = await queries.get_action_session_by_request_id(db, action_request_id)
    if session is not None:
        await queries.update_action_session(
            db,
            int(session["id"]),
            {"status": "cancelled", "updated_at": datetime.utcnow().isoformat()},
        )
    return response


async def clarify_action_request_for_location(
    db: aiosqlite.Connection,
    *,
    location_id: int,
    action_request_id: int,
    selection: dict[str, Any],
    actor: str,
) -> dict[str, Any]:
    request_row = await queries.get_ai_action_request(db, action_request_id)
    if request_row is None:
        raise ValueError("AI action request not found")
    if int(request_row["location_id"]) != location_id:
        raise ValueError("Forbidden for this AI action request")
    if request_row.get("status") != "awaiting_clarification":
        raise ValueError("AI action request is not awaiting clarification")
    session = await queries.get_action_session_by_request_id(db, action_request_id)
    if session is None or session.get("status") != "active" or session.get("pending_prompt_type") != "clarification":
        raise ValueError("AI action request is not awaiting clarification")
    if _is_session_expired(session):
        return await _expire_request_session(db, request_row=request_row, session=session)

    option = _match_clarification_option(
        list((session.get("pending_payload_json") or {}).get("options") or []),
        selection,
    )
    if option is None:
        raise ValueError("Selected clarification option was not found")

    plan = dict(request_row.get("action_plan_json") or {})
    plan["requires_clarification"] = False
    plan["clarification"] = None
    plan["proposed_actions"] = [dict(option.get("proposed_action") or {})]
    await queries.update_ai_action_request(
        db,
        action_request_id,
        {
            "status": "resolving",
            "action_plan_json": plan,
        },
    )
    await queries.insert_ai_action_event(
        db,
        {
            "ai_action_request_id": action_request_id,
            "event_type": "clarified",
            "payload_json": {"selection": selection, "option": option},
            "created_at": datetime.utcnow().isoformat(),
        },
    )

    proposed = dict((plan.get("proposed_actions") or [{}])[0] or {})
    params = dict(proposed.get("params") or {})
    response = await ai_executor.execute_action(
        db,
        action_request_id=action_request_id,
        action_type=str(plan.get("action_type")),
        location_id=int(params.get("location_id") or request_row["location_id"]),
        schedule_id=params.get("schedule_id"),
        week_start_date=params.get("week_start_date"),
        shift_id=params.get("shift_id"),
        worker_id=params.get("worker_id"),
        cascade_id=params.get("cascade_id"),
        create_shift_payload=dict(params.get("create_shift_payload") or {}),
        shift_patch=dict(params.get("shift_patch") or {}),
        actor=actor,
        confirmed=False,
    )
    next_status = str(response.get("status") or "completed")
    await _persist_response(
        db,
        request_id=action_request_id,
        status=next_status,
        response=response,
        event_type="completed" if next_status == "completed" else "confirmation_requested" if next_status == "awaiting_confirmation" else next_status,
    )
    if next_status == "awaiting_confirmation":
        await queries.update_action_session(
            db,
            int(session["id"]),
            {
                "pending_prompt_type": "confirmation",
                "pending_payload_json": response.get("confirmation") or {},
                "updated_at": datetime.utcnow().isoformat(),
            },
        )
    else:
        await queries.update_action_session(
            db,
            int(session["id"]),
            {"status": "completed", "updated_at": datetime.utcnow().isoformat()},
        )
    return response


async def list_location_action_history(
    db: aiosqlite.Connection,
    *,
    principal: AuthPrincipal,
    location_id: int,
    status: str | None = None,
    channel: str | None = None,
    fallback_only: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    if not principal.is_internal and location_id not in principal.location_ids and principal.organization_id is None:
        raise ValueError("Forbidden for this location")
    rows = await queries.list_ai_action_requests_for_location(
        db,
        location_id=location_id,
        status=status,
        channel=channel,
        limit=limit,
    )
    items = []
    for row in rows:
        result_summary = dict(row.get("result_summary_json") or {})
        runtime = result_summary.get("runtime")
        if fallback_only and not bool((runtime or {}).get("fallback_used")):
            continue
        items.append(
            {
                "action_request_id": int(row["id"]),
                "channel": row.get("channel"),
                "status": row.get("status"),
                "text": row.get("original_text") or "",
                "summary": result_summary.get("summary") or row.get("original_text") or "AI action",
                "risk_class": row.get("risk_class"),
                "action_type": (row.get("action_plan_json") or {}).get("action_type"),
                "runtime": result_summary.get("runtime"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
        )
    return {"location_id": location_id, "items": items}


async def list_location_action_attention(
    db: aiosqlite.Connection,
    *,
    principal: AuthPrincipal,
    location_id: int,
    include_resolved: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    if not principal.is_internal and location_id not in principal.location_ids and principal.organization_id is None:
        raise ValueError("Forbidden for this location")
    await expire_stale_action_sessions_internal(db, location_id=location_id, limit=max(limit, 100))
    rows = await queries.list_ai_action_requests_for_location(
        db,
        location_id=location_id,
        limit=max(limit * 5, 100),
    )
    items: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    for row in rows:
        session = await queries.get_action_session_by_request_id(db, int(row["id"]))
        item = _build_attention_item(row, session)
        if item is None and not include_resolved:
            continue
        if item is None:
            item = {
                "action_request_id": int(row["id"]),
                "location_id": int(row["location_id"]),
                "channel": row.get("channel"),
                "status": row.get("status"),
                "action_type": (row.get("action_plan_json") or {}).get("action_type"),
                "text": row.get("original_text") or "",
                "summary": (row.get("result_summary_json") or {}).get("summary") or row.get("original_text") or "AI action",
                "risk_class": row.get("risk_class"),
                "attention_reason": None,
                "recovery_actions": [],
                "state_summary": _build_request_state_summary(row, session),
                "runtime": (row.get("result_summary_json") or {}).get("runtime"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
        items.append(item)
        status_key = str(item.get("status") or "unknown")
        status_counts[status_key] = status_counts.get(status_key, 0) + 1
        reason_key = str(item.get("attention_reason") or "resolved")
        reason_counts[reason_key] = reason_counts.get(reason_key, 0) + 1
        if len(items) >= limit:
            break
    return {
        "location_id": location_id,
        "summary": {
            "total": len(items),
            "status_counts": status_counts,
            "reason_counts": reason_counts,
        },
        "items": items,
    }


async def retry_action_request(
    db: aiosqlite.Connection,
    *,
    principal: AuthPrincipal,
    action_request_id: int,
) -> dict[str, Any]:
    request_row = await queries.get_ai_action_request(db, action_request_id)
    if request_row is None:
        raise ValueError("AI action request not found")
    await _ensure_request_access(principal, request_row)
    session = await queries.get_action_session_by_request_id(db, action_request_id)
    if session is not None and not _is_session_expired(session) and request_row.get("status") in {"awaiting_confirmation", "awaiting_clarification", "resolving"}:
        raise ValueError("AI action request is still active")
    if session is not None and _is_session_expired(session):
        await _expire_request_session(db, request_row=request_row, session=session)

    received = await _get_received_action_payload(db, action_request_id)
    text = str(received.get("text") or request_row.get("original_text") or "").strip()
    context = dict(received.get("context") or {})
    context["retry_of_action_request_id"] = action_request_id
    await queries.insert_ai_action_event(
        db,
        {
            "ai_action_request_id": action_request_id,
            "event_type": "retry_requested",
            "payload_json": {
                "retried_at": datetime.utcnow().isoformat(),
                "principal_type": principal.principal_type,
                "session_id": principal.session_id,
            },
            "created_at": datetime.utcnow().isoformat(),
        },
    )
    return await handle_web_action(
        db,
        principal=principal,
        location_id=int(request_row["location_id"]),
        text=text,
        context=context,
    )


async def list_location_active_sessions(
    db: aiosqlite.Connection,
    *,
    principal: AuthPrincipal,
    location_id: int,
    include_expired: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    if not principal.is_internal and location_id not in principal.location_ids and principal.organization_id is None:
        raise ValueError("Forbidden for this location")
    await expire_stale_action_sessions_internal(db, location_id=location_id, limit=max(limit, 100))
    rows = await queries.list_action_sessions(
        db,
        location_id=location_id,
        status=None if include_expired else "active",
        limit=limit,
    )
    items = [_serialize_action_session(row) for row in rows]
    if not include_expired:
        items = [item for item in items if item["status"] == "active" and not item["is_expired"]]
    return {"location_id": location_id, "items": items}


async def retry_action_request_internal(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
) -> dict[str, Any]:
    request_row = await queries.get_ai_action_request(db, action_request_id)
    if request_row is None:
        raise ValueError("AI action request not found")
    session = await queries.get_action_session_by_request_id(db, action_request_id)
    if session is not None and not _is_session_expired(session) and request_row.get("status") in {"awaiting_confirmation", "awaiting_clarification", "resolving"}:
        raise ValueError("AI action request is still active")
    if session is not None and _is_session_expired(session):
        await _expire_request_session(db, request_row=request_row, session=session)

    received = await _get_received_action_payload(db, action_request_id)
    text = str(received.get("text") or request_row.get("original_text") or "").strip()
    if not text:
        raise ValueError("AI action request cannot be retried because the original text is unavailable")
    context = dict(received.get("context") or {})
    context["retry_of_action_request_id"] = action_request_id
    await queries.insert_ai_action_event(
        db,
        {
            "ai_action_request_id": action_request_id,
            "event_type": "retry_requested",
            "payload_json": {
                "retried_at": datetime.utcnow().isoformat(),
                "principal_type": "internal",
            },
            "created_at": datetime.utcnow().isoformat(),
        },
    )

    channel = str(request_row.get("channel") or "web")
    location_id = int(request_row["location_id"])
    if channel == "web":
        return await handle_web_action(
            db,
            principal=AuthPrincipal(
                principal_type="internal",
                organization_id=request_row.get("organization_id"),
                location_ids=[location_id],
            ),
            location_id=location_id,
            text=text,
            context=context,
        )

    location = await queries.get_location(db, location_id)
    if location is None:
        raise ValueError("Location not found")
    phone = str(received.get("phone") or location.get("manager_phone") or "").strip()
    if not phone:
        raise ValueError("AI action request cannot be retried because the manager phone is unavailable")
    return await _handle_manager_channel_action(
        db,
        location=location,
        phone=phone,
        text=text,
        channel=channel,
        context=context,
    )


async def cancel_action_request_internal(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
) -> dict[str, Any]:
    request_row = await queries.get_ai_action_request(db, action_request_id)
    if request_row is None:
        raise ValueError("AI action request not found")
    response = ai_renderers.build_cancelled_response(action_request_id=action_request_id)
    await _persist_response(
        db,
        request_id=action_request_id,
        status="cancelled",
        response=response,
        event_type="cancelled",
    )
    session = await queries.get_action_session_by_request_id(db, action_request_id)
    if session is not None:
        await queries.update_action_session(
            db,
            int(session["id"]),
            {"status": "cancelled", "updated_at": datetime.utcnow().isoformat()},
        )
    return response


async def expire_action_request_internal(
    db: aiosqlite.Connection,
    *,
    action_request_id: int,
) -> dict[str, Any]:
    request_row = await queries.get_ai_action_request(db, action_request_id)
    if request_row is None:
        raise ValueError("AI action request not found")
    session = await queries.get_action_session_by_request_id(db, action_request_id)
    if session is None:
        if str(request_row.get("status") or "") == "expired":
            stored = dict(request_row.get("result_summary_json") or {})
            return stored or ai_renderers.build_expired_response(action_request_id=action_request_id)
        raise ValueError("AI action request does not have an active session")
    if session.get("status") == "expired":
        stored = dict(request_row.get("result_summary_json") or {})
        return stored or ai_renderers.build_expired_response(action_request_id=action_request_id)
    return await _expire_request_session(db, request_row=request_row, session=session)


async def get_action_request_debug_detail(
    db: aiosqlite.Connection,
    *,
    principal: AuthPrincipal,
    action_request_id: int,
) -> dict[str, Any]:
    request_row = await queries.get_ai_action_request(db, action_request_id)
    if request_row is None:
        raise ValueError("AI action request not found")
    await _ensure_request_access(principal, request_row)
    entities = await queries.list_ai_action_entities(db, action_request_id)
    events = await queries.list_ai_action_events(db, action_request_id)
    session = await queries.get_action_session_by_request_id(db, action_request_id)
    received = next((event for event in events if event.get("event_type") == "received"), None)
    return {
        "action_request_id": action_request_id,
        "request": request_row,
        "entities": entities,
        "events": events,
        "session": session,
        "state_summary": _build_request_state_summary(request_row, session),
        "received": (received or {}).get("payload_json") or {},
        "recovery_actions": {
            "retry_supported": _build_request_state_summary(request_row, session)["retryable"],
            "retry_route": f"/api/ai-actions/{action_request_id}/retry",
            "internal_retry_route": f"/api/internal/ai-actions/{action_request_id}/retry",
            "internal_cancel_route": f"/api/internal/ai-actions/{action_request_id}/cancel",
            "internal_expire_route": f"/api/internal/ai-actions/{action_request_id}/expire",
        },
    }


async def get_location_runtime_stats(
    db: aiosqlite.Connection,
    *,
    principal: AuthPrincipal,
    location_id: int,
    days: int = 7,
    channel: str | None = None,
) -> dict[str, Any]:
    if not principal.is_internal and location_id not in principal.location_ids and principal.organization_id is None:
        raise ValueError("Forbidden for this location")
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    rows = await queries.list_ai_action_requests_for_location(
        db,
        location_id=location_id,
        channel=channel,
        created_after=cutoff,
        limit=500,
    )
    feedback_events = await queries.list_ai_action_events_for_request_ids(
        db,
        [int(row["id"]) for row in rows],
        event_type="feedback",
    )
    all_events = await queries.list_ai_action_events_for_request_ids(
        db,
        [int(row["id"]) for row in rows],
    )
    feedback_by_request: dict[int, list[dict[str, Any]]] = {}
    for event in feedback_events:
        feedback_by_request.setdefault(int(event["ai_action_request_id"]), []).append(event)
    status_counts: dict[str, int] = {}
    channel_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    provider_counts: dict[str, int] = {}
    latencies: list[int] = []
    fallback_rows: list[dict[str, Any]] = []
    runtime_rows = 0
    feedback_summary = {
        "total_feedback": 0,
        "helpful_count": 0,
        "unhelpful_count": 0,
        "correct_count": 0,
        "incorrect_count": 0,
    }
    retry_requested_count = sum(1 for event in all_events if event.get("event_type") == "retry_requested")
    for row in rows:
        status = str(row.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        row_channel = str(row.get("channel") or "unknown")
        channel_counts[row_channel] = channel_counts.get(row_channel, 0) + 1
        action_type = str((row.get("action_plan_json") or {}).get("action_type") or "unknown")
        action_counts[action_type] = action_counts.get(action_type, 0) + 1
        runtime = dict((row.get("result_summary_json") or {}).get("runtime") or {})
        provider = str(runtime.get("provider") or "unknown")
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
        if runtime:
            runtime_rows += 1
        latency = runtime.get("latency_ms")
        if latency is not None:
            try:
                latencies.append(int(latency))
            except (TypeError, ValueError):
                pass
        if runtime.get("fallback_used"):
            fallback_rows.append(
                {
                    "action_request_id": int(row["id"]),
                    "action_type": action_type,
                    "channel": row_channel,
                    "status": status,
                    "summary": (row.get("result_summary_json") or {}).get("summary") or row.get("original_text") or "AI action",
                    "runtime": runtime,
                    "created_at": row.get("created_at"),
                }
            )
        for event in feedback_by_request.get(int(row["id"]), []):
            feedback_summary["total_feedback"] += 1
            payload = dict(event.get("payload_json") or {})
            if payload.get("helpful") is True:
                feedback_summary["helpful_count"] += 1
            if payload.get("helpful") is False:
                feedback_summary["unhelpful_count"] += 1
            if payload.get("correct") is True:
                feedback_summary["correct_count"] += 1
            if payload.get("correct") is False:
                feedback_summary["incorrect_count"] += 1
    fallback_count = len(fallback_rows)
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else None
    sorted_latencies = sorted(latencies)
    p95_latency = None
    if sorted_latencies:
        index = max(0, min(len(sorted_latencies) - 1, int(round((len(sorted_latencies) - 1) * 0.95))))
        p95_latency = sorted_latencies[index]
    return {
        "location_id": location_id,
        "days": days,
        "summary": {
            "total_actions": len(rows),
            "runtime_record_count": runtime_rows,
            "fallback_count": fallback_count,
            "fallback_rate": round(fallback_count / len(rows), 4) if rows else 0.0,
            "expired_count": status_counts.get("expired", 0),
            "retry_requested_count": retry_requested_count,
            "avg_latency_ms": avg_latency,
            "p95_latency_ms": p95_latency,
            "last_action_at": rows[0].get("created_at") if rows else None,
            **feedback_summary,
        },
        "status_counts": status_counts,
        "channel_counts": channel_counts,
        "action_counts": action_counts,
        "provider_counts": provider_counts,
        "recent_fallbacks": fallback_rows[:10],
    }


async def get_location_ai_capabilities(
    db: aiosqlite.Connection,
    *,
    principal: AuthPrincipal,
    location_id: int,
) -> dict[str, Any]:
    if not principal.is_internal and location_id not in principal.location_ids and principal.organization_id is None:
        raise ValueError("Forbidden for this location")
    location = await queries.get_location(db, location_id)
    if location is None:
        raise ValueError("Location not found")
    return {
        "location_id": location_id,
        "provider_policy": ai_policy.provider_policy_snapshot(),
        "actions": ai_policy.action_capabilities(),
    }


async def list_ai_action_sessions_internal(
    db: aiosqlite.Connection,
    *,
    location_id: int | None = None,
    organization_id: int | None = None,
    status: str | None = "active",
    channel: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    rows = await queries.list_action_sessions(
        db,
        location_id=location_id,
        organization_id=organization_id,
        status=status,
        channel=channel,
        limit=limit,
    )
    return {"items": [_serialize_action_session(row) for row in rows]}


async def list_ai_action_attention_internal(
    db: aiosqlite.Connection,
    *,
    location_id: int | None = None,
    organization_id: int | None = None,
    include_resolved: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    rows = await queries.list_recent_ai_action_requests(
        db,
        location_id=location_id,
        organization_id=organization_id,
        limit=max(limit * 5, 100),
    )
    items: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    for row in rows:
        session = await queries.get_action_session_by_request_id(db, int(row["id"]))
        item = _build_attention_item(row, session, location_name=row.get("location_name"))
        if item is None and not include_resolved:
            continue
        if item is None:
            item = {
                "action_request_id": int(row["id"]),
                "location_id": int(row["location_id"]),
                "location_name": row.get("location_name"),
                "organization_id": row.get("organization_id"),
                "channel": row.get("channel"),
                "status": row.get("status"),
                "action_type": (row.get("action_plan_json") or {}).get("action_type"),
                "text": row.get("original_text") or "",
                "summary": (row.get("result_summary_json") or {}).get("summary") or row.get("original_text") or "AI action",
                "risk_class": row.get("risk_class"),
                "attention_reason": None,
                "recovery_actions": [],
                "state_summary": _build_request_state_summary(row, session),
                "runtime": (row.get("result_summary_json") or {}).get("runtime"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
        items.append(item)
        status_key = str(item.get("status") or "unknown")
        status_counts[status_key] = status_counts.get(status_key, 0) + 1
        reason_key = str(item.get("attention_reason") or "resolved")
        reason_counts[reason_key] = reason_counts.get(reason_key, 0) + 1
        if len(items) >= limit:
            break
    return {
        "summary": {
            "total": len(items),
            "status_counts": status_counts,
            "reason_counts": reason_counts,
        },
        "items": items,
    }


async def expire_stale_action_sessions_internal(
    db: aiosqlite.Connection,
    *,
    location_id: int | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    rows = await queries.list_action_sessions(
        db,
        location_id=location_id,
        status="active",
        expired_before=datetime.utcnow().isoformat(),
        limit=limit,
    )
    expired_items: list[dict[str, Any]] = []
    for session in rows:
        request_row = await queries.get_ai_action_request(db, int(session["ai_action_request_id"]))
        if request_row is None:
            continue
        response = await _expire_request_session(
            db,
            request_row=request_row,
            session=session,
        )
        expired_items.append(
            {
                "session_id": int(session["id"]),
                "action_request_id": int(request_row["id"]),
                "location_id": int(request_row["location_id"]),
                "status": response.get("status"),
            }
        )
    return {"expired_count": len(expired_items), "items": expired_items}


async def record_action_feedback(
    db: aiosqlite.Connection,
    *,
    principal: AuthPrincipal,
    action_request_id: int,
    feedback: dict[str, Any],
) -> dict[str, Any]:
    request_row = await queries.get_ai_action_request(db, action_request_id)
    if request_row is None:
        raise ValueError("AI action request not found")
    await _ensure_request_access(principal, request_row)
    normalized_feedback = {
        "helpful": feedback.get("helpful"),
        "correct": feedback.get("correct"),
        "notes": (str(feedback.get("notes") or "").strip() or None),
        "submitted_at": datetime.utcnow().isoformat(),
        "submitted_by": {
            "principal_type": principal.principal_type,
            "session_id": principal.session_id,
            "organization_id": principal.organization_id,
            "location_ids": list(principal.location_ids or []),
        },
    }
    await queries.insert_ai_action_event(
        db,
        {
            "ai_action_request_id": action_request_id,
            "event_type": "feedback",
            "payload_json": normalized_feedback,
            "created_at": datetime.utcnow().isoformat(),
        },
    )
    return {
        "action_request_id": action_request_id,
        "feedback_recorded": True,
        "feedback": normalized_feedback,
    }


async def list_recent_ai_actions_internal(
    db: aiosqlite.Connection,
    *,
    location_id: int | None = None,
    organization_id: int | None = None,
    status: str | None = None,
    channel: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    rows = await queries.list_recent_ai_action_requests(
        db,
        location_id=location_id,
        organization_id=organization_id,
        status=status,
        channel=channel,
        limit=limit,
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        result_summary = dict(row.get("result_summary_json") or {})
        items.append(
            {
                "action_request_id": int(row["id"]),
                "location_id": int(row["location_id"]),
                "location_name": row.get("location_name"),
                "organization_id": row.get("organization_id"),
                "channel": row.get("channel"),
                "status": row.get("status"),
                "action_type": (row.get("action_plan_json") or {}).get("action_type"),
                "text": row.get("original_text") or "",
                "summary": result_summary.get("summary") or row.get("original_text") or "AI action",
                "risk_class": row.get("risk_class"),
                "runtime": result_summary.get("runtime"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
        )
    return {"items": items}


async def _get_received_action_payload(
    db: aiosqlite.Connection,
    action_request_id: int,
) -> dict[str, Any]:
    events = await queries.list_ai_action_events(db, action_request_id)
    received = next((event for event in events if event.get("event_type") == "received"), None)
    payload = (received or {}).get("payload_json") or {}
    return dict(payload if isinstance(payload, dict) else {})


async def _expire_request_session(
    db: aiosqlite.Connection,
    *,
    request_row: dict[str, Any],
    session: dict[str, Any],
) -> dict[str, Any]:
    response = ai_renderers.build_expired_response(
        action_request_id=int(request_row["id"]),
    )
    await _persist_response(
        db,
        request_id=int(request_row["id"]),
        status="expired",
        response=response,
        event_type="expired",
    )
    await queries.update_action_session(
        db,
        int(session["id"]),
        {
            "status": "expired",
            "updated_at": datetime.utcnow().isoformat(),
        },
    )
    await queries.update_ai_action_request(
        db,
        int(request_row["id"]),
        {
            "error_code": "session_expired",
            "error_message": "AI action session expired before completion",
            "updated_at": datetime.utcnow().isoformat(),
        },
    )
    return response


def _is_session_expired(session: dict[str, Any] | None) -> bool:
    if not session:
        return False
    expires_at = str(session.get("expires_at") or "").strip()
    if not expires_at:
        return False
    try:
        return datetime.fromisoformat(expires_at) <= datetime.utcnow()
    except ValueError:
        return False


def _serialize_action_session(row: dict[str, Any]) -> dict[str, Any]:
    action_plan = _decode_possible_json(row.get("request_action_plan_json"))
    result_summary = _decode_possible_json(row.get("request_result_summary_json"))
    return {
        "session_id": int(row["id"]),
        "action_request_id": int(row["ai_action_request_id"]),
        "location_id": int(row["location_id"]),
        "channel": row.get("channel"),
        "status": row.get("status"),
        "pending_prompt_type": row.get("pending_prompt_type"),
        "action_type": (action_plan or {}).get("action_type"),
        "text": row.get("request_text") or "",
        "summary": (result_summary or {}).get("summary") or row.get("request_text") or "AI action",
        "expires_at": row.get("expires_at"),
        "is_expired": _is_session_expired(row),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _build_request_state_summary(request_row: dict[str, Any], session: dict[str, Any] | None) -> dict[str, Any]:
    request_status = str(request_row.get("status") or "unknown")
    session_expired = _is_session_expired(session)
    attention_reason = _attention_reason_for_request(request_row, session)
    retryable_statuses = {"failed", "cancelled", "expired", "redirected"}
    return {
        "request_status": request_status,
        "session_status": session.get("status") if session else None,
        "pending_prompt_type": session.get("pending_prompt_type") if session else None,
        "expires_at": session.get("expires_at") if session else None,
        "is_session_expired": session_expired,
        "stalled_resolution": attention_reason == "stalled_resolution",
        "attention_reason": attention_reason,
        "retryable": request_status in retryable_statuses or session_expired or attention_reason == "stalled_resolution",
    }


def _decode_possible_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


async def _persist_response(
    db: aiosqlite.Connection,
    *,
    request_id: int,
    status: str,
    response: dict[str, Any],
    event_type: str,
    runtime: dict[str, Any] | None = None,
) -> None:
    stored_request = await queries.get_ai_action_request(db, request_id)
    stored_response = dict((stored_request or {}).get("result_summary_json") or {})
    persisted_response = dict(response)
    if runtime is not None:
        response["runtime"] = runtime
        persisted_response["runtime"] = runtime
    elif stored_response.get("runtime") is not None:
        response["runtime"] = stored_response.get("runtime")
        persisted_response["runtime"] = stored_response.get("runtime")
    await queries.update_ai_action_request(
        db,
        request_id,
        {
            "status": status,
            "result_summary_json": persisted_response,
            "updated_at": datetime.utcnow().isoformat(),
        },
    )
    await queries.insert_ai_action_event(
        db,
        {
            "ai_action_request_id": request_id,
            "event_type": event_type,
            "payload_json": persisted_response,
            "created_at": datetime.utcnow().isoformat(),
        },
    )


async def _ensure_request_access(principal: AuthPrincipal, request_row: dict) -> None:
    if principal.is_internal:
        return
    request_location_id = int(request_row["location_id"])
    if request_location_id in principal.location_ids:
        return
    if principal.organization_id is not None and principal.organization_id == request_row.get("organization_id"):
        return
    raise ValueError("Forbidden for this AI action request")


def _match_clarification_option(options: list[dict[str, Any]], selection: dict[str, Any]) -> dict[str, Any] | None:
    option_key = selection.get("option_key")
    if option_key is not None:
        for option in options:
            if option.get("option_key") == option_key:
                return option

    option_index = selection.get("option_index")
    if option_index is not None:
        try:
            normalized_index = int(option_index)
        except (TypeError, ValueError):
            normalized_index = None
        if normalized_index is not None:
            for option in options:
                if int(option.get("option_index") or 0) == normalized_index:
                    return option

    for option in options:
        if _selection_matches_option(option, selection):
            return option
    return None


def _selection_matches_option(option: dict[str, Any], selection: dict[str, Any]) -> bool:
    matched = False
    for key in ("shift_id", "cascade_id", "worker_id"):
        if selection.get(key) is None:
            continue
        matched = True
        try:
            if int(selection[key]) != int(option.get(key) or 0):
                return False
        except (TypeError, ValueError):
            return False
    return matched


def _options_with_indexes(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed: list[dict[str, Any]] = []
    for index, option in enumerate(options, start=1):
        enriched = dict(option)
        enriched["option_index"] = index
        indexed.append(enriched)
    return indexed


def _attention_reason_for_request(request_row: dict[str, Any], session: dict[str, Any] | None) -> str | None:
    request_status = str(request_row.get("status") or "unknown")
    if session is not None and _is_session_expired(session):
        return "expired"
    if request_status == "awaiting_confirmation":
        return "pending_confirmation"
    if request_status == "awaiting_clarification":
        return "pending_clarification"
    if request_status == "failed":
        return "failed"
    if request_status == "expired":
        return "expired"
    if request_status == "redirected":
        return "redirected"
    if request_status == "resolving" and _is_request_stalled(request_row):
        return "stalled_resolution"
    return None


def _is_request_stalled(request_row: dict[str, Any]) -> bool:
    updated_at = str(request_row.get("updated_at") or request_row.get("created_at") or "").strip()
    if not updated_at:
        return False
    try:
        updated = datetime.fromisoformat(updated_at)
    except ValueError:
        return False
    return updated <= datetime.utcnow() - timedelta(minutes=settings.backfill_ai_resolving_attention_minutes)


def _recovery_actions_for_request(request_row: dict[str, Any], session: dict[str, Any] | None) -> list[dict[str, Any]]:
    action_request_id = int(request_row["id"])
    attention_reason = _attention_reason_for_request(request_row, session)
    actions: list[dict[str, Any]] = []
    if attention_reason in {"pending_confirmation", "pending_clarification"}:
        actions.append({"type": "open", "label": "Open pending action", "route": f"/api/ai-actions/{action_request_id}"})
    if attention_reason in {"failed", "expired", "redirected", "stalled_resolution"}:
        actions.append({"type": "retry", "label": "Retry", "route": f"/api/ai-actions/{action_request_id}/retry"})
        actions.append({"type": "internal_retry", "label": "Retry internally", "route": f"/api/internal/ai-actions/{action_request_id}/retry"})
    if attention_reason in {"pending_confirmation", "pending_clarification", "stalled_resolution"}:
        actions.append({"type": "internal_cancel", "label": "Cancel", "route": f"/api/internal/ai-actions/{action_request_id}/cancel"})
    if attention_reason in {"pending_confirmation", "pending_clarification", "stalled_resolution"}:
        actions.append({"type": "internal_expire", "label": "Expire", "route": f"/api/internal/ai-actions/{action_request_id}/expire"})
    return actions


def _build_attention_item(
    request_row: dict[str, Any],
    session: dict[str, Any] | None,
    *,
    location_name: str | None = None,
) -> dict[str, Any] | None:
    attention_reason = _attention_reason_for_request(request_row, session)
    if attention_reason is None:
        return None
    result_summary = dict(request_row.get("result_summary_json") or {})
    item = {
        "action_request_id": int(request_row["id"]),
        "location_id": int(request_row["location_id"]),
        "channel": request_row.get("channel"),
        "status": request_row.get("status"),
        "action_type": (request_row.get("action_plan_json") or {}).get("action_type"),
        "text": request_row.get("original_text") or "",
        "summary": result_summary.get("summary") or request_row.get("original_text") or "AI action",
        "risk_class": request_row.get("risk_class"),
        "attention_reason": attention_reason,
        "recovery_actions": _recovery_actions_for_request(request_row, session),
        "state_summary": _build_request_state_summary(request_row, session),
        "runtime": result_summary.get("runtime"),
        "created_at": request_row.get("created_at"),
        "updated_at": request_row.get("updated_at"),
    }
    if location_name is not None:
        item["location_name"] = location_name
    if request_row.get("organization_id") is not None:
        item["organization_id"] = request_row.get("organization_id")
    return item
