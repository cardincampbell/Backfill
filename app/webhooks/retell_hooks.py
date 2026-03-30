"""
Retell webhook handler.
"""
from __future__ import annotations

from typing import Optional, Type

from fastapi import APIRouter, Depends, HTTPException, Request
import aiosqlite
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.db.database import get_db
from app.db import queries
from app.services import ai_actions as ai_actions_svc
from app.services import caller_lookup, consent as consent_svc, shift_manager, cascade as cascade_svc
from app.services import notifications as notifications_svc
from app.services import onboarding as onboarding_svc
from app.services import rate_limit
from app.services import retell_ingest
from app.services import retell_reconcile

router = APIRouter(
    prefix="/webhooks",
    tags=["retell-webhooks"],
    dependencies=[Depends(rate_limit.limit_by_request_key("retell_webhook", limit=240, window_seconds=60))],
)


class _FunctionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _LookupCallerArgs(_FunctionArgs):
    phone: str = Field(min_length=1)


class _LogConsentArgs(_FunctionArgs):
    worker_id: int
    granted: bool = True
    channel: str = "inbound_call"


class _CreateVacancyArgs(_FunctionArgs):
    shift_id: int
    worker_id: int


class _ClaimShiftArgs(_FunctionArgs):
    cascade_id: int
    worker_id: int
    conversation_summary: str = ""
    eta_minutes: Optional[int] = Field(default=None, ge=0)


class _DeclineShiftArgs(_FunctionArgs):
    cascade_id: int
    worker_id: int
    conversation_summary: str = ""


class _CancelStandbyArgs(_FunctionArgs):
    cascade_id: int
    worker_id: int
    conversation_summary: str = ""


class _PromoteStandbyArgs(_FunctionArgs):
    cascade_id: int
    worker_id: int
    conversation_summary: str = ""


class _ConfirmFillArgs(_FunctionArgs):
    cascade_id: int
    worker_id: int
    accepted: bool
    conversation_summary: str = ""
    eta_minutes: Optional[int] = Field(default=None, ge=0)


class _GetOpenShiftsArgs(_FunctionArgs):
    location_id: Optional[int] = None


class _GetShiftStatusArgs(_FunctionArgs):
    shift_id: int


class _CreateOpenShiftArgs(_FunctionArgs):
    location_id: int
    role: str = Field(min_length=1)
    date: str = Field(min_length=1)
    start_time: str = Field(min_length=1)
    end_time: str = Field(min_length=1)
    pay_rate: float = Field(gt=0)
    requirements: list[str] = Field(default_factory=list)


class _SendOnboardingLinkArgs(_FunctionArgs):
    phone: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    location_id: int
    platform: Optional[str] = None


class _AiManagerActionArgs(_FunctionArgs):
    phone: str = Field(min_length=1)
    text: str = Field(min_length=1)
    location_id: Optional[int] = None
    schedule_id: Optional[int] = None
    week_start_date: Optional[str] = None
    shift_id: Optional[int] = None
    worker_id: Optional[int] = None
    cascade_id: Optional[int] = None


class _ConfirmAiActionArgs(_FunctionArgs):
    action_request_id: int
    location_id: int


class _ClarifyAiActionArgs(_FunctionArgs):
    action_request_id: int
    location_id: int
    selection: dict = Field(default_factory=dict)


@router.post("/retell")
async def retell_webhook(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    body = await request.json()
    event = body.get("event")
    try:
        # ── call lifecycle events ─────────────────────────────────────────────
        if event in {"call_started", "chat_started"}:
            await retell_ingest.persist_retell_payload(db, body)
            await retell_reconcile.mark_webhook_success(db, event=event or "unknown")
            return {"status": "ok"}

        if event in {"call_ended", "chat_ended"}:
            await retell_ingest.persist_retell_payload(db, body)
            await retell_reconcile.mark_webhook_success(db, event=event or "unknown")
            return {"status": "ok"}

        if event in {"call_analyzed", "chat_analyzed"}:
            conversation_id = await retell_ingest.persist_retell_payload(db, body)
            if event == "call_analyzed" and conversation_id is not None:
                conversation = await retell_ingest.get_persisted_conversation(db, conversation_id)
                if conversation is not None:
                    await onboarding_svc.maybe_send_post_call_signup(db, conversation)
            await retell_reconcile.mark_webhook_success(db, event=event or "unknown")
            return {"status": "ok"}

        # ── function calls from the agent ─────────────────────────────────────
        if event == "function_call":
            name = body.get("name")
            args = body.get("args", {})
            result = await _dispatch(db, name, args)
            await retell_reconcile.mark_webhook_success(db, event=event or "unknown")
            return result

        await retell_reconcile.mark_webhook_success(db, event=event or "unknown")
        return {"status": "ignored", "event": event}
    except Exception as exc:
        await retell_reconcile.mark_webhook_failure(
            db,
            event=str(event or "unknown"),
            error=str(exc),
        )
        raise


# ── function call dispatcher ──────────────────────────────────────────────────

async def _dispatch(db: aiosqlite.Connection, name: str, args: dict) -> dict:
    handlers = {
        "lookup_caller": (_lookup_caller, _LookupCallerArgs),
        "log_consent": (_log_consent, _LogConsentArgs),
        "create_vacancy": (_create_vacancy, _CreateVacancyArgs),
        "claim_shift": (_claim_shift, _ClaimShiftArgs),
        "decline_shift": (_decline_shift, _DeclineShiftArgs),
        "cancel_standby": (_cancel_standby, _CancelStandbyArgs),
        "promote_standby": (_promote_standby, _PromoteStandbyArgs),
        "confirm_fill": (_confirm_fill, _ConfirmFillArgs),
        "get_open_shifts": (_get_open_shifts, _GetOpenShiftsArgs),
        "get_shift_status": (_get_shift_status, _GetShiftStatusArgs),
        "create_open_shift": (_create_open_shift, _CreateOpenShiftArgs),
        "send_onboarding_link": (_send_onboarding_link, _SendOnboardingLinkArgs),
        "ai_manager_action": (_ai_manager_action, _AiManagerActionArgs),
        "confirm_ai_action": (_confirm_ai_action, _ConfirmAiActionArgs),
        "clarify_ai_action": (_clarify_ai_action, _ClarifyAiActionArgs),
    }
    binding = handlers.get(name)
    if binding is None:
        raise HTTPException(status_code=400, detail=f"Unknown function call: {name!r}")
    handler, model = binding
    validated_args = _validate_function_args(name, model, args)
    return await handler(db, validated_args)


def _validate_function_args(name: str, model: Type[_FunctionArgs], args: object) -> _FunctionArgs:
    try:
        return model.model_validate(args)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Invalid args for {name}",
                "errors": exc.errors(),
            },
        ) from exc


async def _lookup_caller(db: aiosqlite.Connection, args: _LookupCallerArgs) -> dict:
    return await caller_lookup.lookup(db, args.phone)


async def _log_consent(db: aiosqlite.Connection, args: _LogConsentArgs) -> dict:
    if args.granted:
        await consent_svc.grant(db, args.worker_id, channel=args.channel)
        return {"status": "consent_granted", "worker_id": args.worker_id}
    else:
        await consent_svc.revoke(db, args.worker_id, channel="voice")
        return {"status": "consent_revoked", "worker_id": args.worker_id}


async def _create_vacancy(db: aiosqlite.Connection, args: _CreateVacancyArgs) -> dict:
    cascade = await shift_manager.create_vacancy(
        db,
        shift_id=args.shift_id,
        called_out_by_worker_id=args.worker_id,
        actor=f"worker:{args.worker_id}",
    )
    # Immediately kick off the first outreach
    result = await cascade_svc.advance(db, cascade["id"])
    return {
        "status": "vacancy_created",
        "cascade_id": cascade["id"],
        "first_outreach": result,
    }


async def _confirm_fill(db: aiosqlite.Connection, args: _ConfirmFillArgs) -> dict:
    if args.accepted:
        result = await cascade_svc.claim_shift(
            db,
            cascade_id=args.cascade_id,
            worker_id=args.worker_id,
            summary=args.conversation_summary,
            eta_minutes=args.eta_minutes,
        )
        if result["status"] == "confirmed":
            await notifications_svc.queue_manager_notification(
                db,
                cascade_id=int(args.cascade_id),
                worker_id=int(args.worker_id),
                filled=True,
            )
            return {"status": "shift_filled", "worker_id": args.worker_id}
        return result

    await cascade_svc.decline_shift(
        db,
        cascade_id=args.cascade_id,
        worker_id=args.worker_id,
        summary=args.conversation_summary,
    )
    return {"status": "declined", "worker_id": args.worker_id}


async def _claim_shift(db: aiosqlite.Connection, args: _ClaimShiftArgs) -> dict:
    result = await cascade_svc.claim_shift(
        db,
        cascade_id=args.cascade_id,
        worker_id=args.worker_id,
        summary=args.conversation_summary,
        eta_minutes=args.eta_minutes,
    )
    if result["status"] == "confirmed":
        await notifications_svc.queue_manager_notification(
            db,
            cascade_id=int(args.cascade_id),
            worker_id=int(args.worker_id),
            filled=True,
        )
    return result


async def _decline_shift(db: aiosqlite.Connection, args: _DeclineShiftArgs) -> dict:
    return await cascade_svc.decline_shift(
        db,
        cascade_id=args.cascade_id,
        worker_id=args.worker_id,
        summary=args.conversation_summary,
    )


async def _cancel_standby(db: aiosqlite.Connection, args: _CancelStandbyArgs) -> dict:
    return await cascade_svc.cancel_standby(
        db,
        cascade_id=args.cascade_id,
        worker_id=args.worker_id,
        summary=args.conversation_summary,
    )


async def _promote_standby(db: aiosqlite.Connection, args: _PromoteStandbyArgs) -> dict:
    result = await cascade_svc.promote_standby(
        db,
        cascade_id=args.cascade_id,
        worker_id=args.worker_id,
        summary=args.conversation_summary,
    )
    if result["status"] == "confirmed":
        await notifications_svc.queue_manager_notification(
            db,
            cascade_id=int(args.cascade_id),
            worker_id=int(args.worker_id),
            filled=True,
        )
    return result


async def _get_open_shifts(db: aiosqlite.Connection, args: _GetOpenShiftsArgs) -> dict:
    query = "SELECT * FROM shifts WHERE status='vacant'"
    params: list = []
    if args.location_id:
        query += " AND location_id=?"
        params.append(args.location_id)
    query += " ORDER BY date ASC LIMIT 10"
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return {"shifts": [dict(r) for r in rows]}


async def _get_shift_status(db: aiosqlite.Connection, args: _GetShiftStatusArgs) -> dict:
    from app.db.queries import get_shift_status

    payload = await get_shift_status(db, args.shift_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    return payload


async def _create_open_shift(db: aiosqlite.Connection, args: _CreateOpenShiftArgs) -> dict:
    from app.db.queries import insert_shift, get_shift

    shift_id = await insert_shift(
        db,
        {
            "location_id": args.location_id,
            "role": args.role,
            "date": args.date,
            "start_time": args.start_time,
            "end_time": args.end_time,
            "pay_rate": args.pay_rate,
            "requirements": args.requirements,
            "status": "vacant",
            "source_platform": "backfill_native",
        },
    )
    cascade = await shift_manager.create_vacancy(
        db,
        shift_id=shift_id,
        called_out_by_worker_id=None,
        actor=f"manager:{args.location_id}",
    )
    result = await cascade_svc.advance(db, cascade["id"])
    return {
        "shift": await get_shift(db, shift_id),
        "cascade_id": cascade["id"],
        "first_outreach": result,
    }


async def _send_onboarding_link(db: aiosqlite.Connection, args: _SendOnboardingLinkArgs) -> dict:
    try:
        return await onboarding_svc.send_onboarding_link(
            db,
            phone=args.phone,
            kind=args.kind,
            location_id=args.location_id,
            platform=args.platform,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _ai_manager_action(db: aiosqlite.Connection, args: _AiManagerActionArgs) -> dict:
    manager_context = await _find_manager_voice_context(
        db,
        phone=args.phone,
        location_id=args.location_id,
    )
    if manager_context is None:
        raise HTTPException(status_code=404, detail="Manager context not found")

    context: dict[str, object] = {}
    if args.schedule_id is not None:
        context["schedule_id"] = int(args.schedule_id)
    if args.week_start_date:
        context["week_start_date"] = args.week_start_date
    if args.shift_id is not None:
        context["shift_id"] = int(args.shift_id)
    if args.worker_id is not None:
        context["worker_id"] = int(args.worker_id)
    if args.cascade_id is not None:
        context["cascade_id"] = int(args.cascade_id)

    response = await ai_actions_svc.handle_manager_voice_action(
        db,
        location=manager_context["location"],
        phone=args.phone,
        text=args.text,
        context=context,
    )
    return _render_retell_ai_response(response)


async def _confirm_ai_action(db: aiosqlite.Connection, args: _ConfirmAiActionArgs) -> dict:
    response = await ai_actions_svc.confirm_action_request_for_location(
        db,
        location_id=int(args.location_id),
        action_request_id=int(args.action_request_id),
        actor=f"manager_voice:{args.location_id}",
    )
    return _render_retell_ai_response(response)


async def _clarify_ai_action(db: aiosqlite.Connection, args: _ClarifyAiActionArgs) -> dict:
    response = await ai_actions_svc.clarify_action_request_for_location(
        db,
        location_id=int(args.location_id),
        action_request_id=int(args.action_request_id),
        selection=dict(args.selection or {}),
        actor=f"manager_voice:{args.location_id}",
    )
    return _render_retell_ai_response(response)


async def _find_manager_voice_context(
    db: aiosqlite.Connection,
    *,
    phone: str,
    location_id: int | None = None,
) -> dict | None:
    if location_id is not None:
        location = await queries.get_location(db, int(location_id))
        if location is None:
            return None
        manager_phone = str(location.get("manager_phone") or "")
        if manager_phone != phone:
            return None
        schedule = await queries.get_latest_schedule_for_location(db, int(location["id"]))
        return {
            "location": location,
            "schedule": schedule,
        }

    locations = await queries.list_locations_by_contact_phone(db, phone)
    if not locations:
        return None

    preferred = [
        location
        for location in locations
        if location.get("operating_mode") == "backfill_shifts"
        or location.get("scheduling_platform") == "backfill_native"
    ]
    candidates = preferred or locations
    best_context = None
    best_score: tuple[int, str, int] | None = None
    for location in candidates:
        schedule = await queries.get_latest_schedule_for_location(db, int(location["id"]))
        score = (
            1 if schedule and schedule.get("lifecycle_state") in {"draft", "amended", "recalled", "published"} else 0,
            str(schedule.get("updated_at") or "") if schedule else "",
            int(location["id"]),
        )
        if best_score is None or score > best_score:
            best_score = score
            best_context = {
                "location": location,
                "schedule": schedule,
            }
    return best_context


def _render_retell_ai_response(response: dict) -> dict:
    mode = str(response.get("mode") or "result")
    payload = {
        "status": str(response.get("status") or "completed"),
        "action_request_id": int(response.get("action_request_id") or 0),
        "mode": mode,
        "summary": str(response.get("summary") or ""),
        "risk_class": response.get("risk_class"),
    }
    if mode == "confirmation":
        payload["confirmation_prompt"] = str((response.get("confirmation") or {}).get("prompt") or response.get("summary") or "")
        payload["affected_entities"] = list((response.get("confirmation") or {}).get("affected_entities") or [])
        payload["next_step"] = "Ask the manager for explicit confirmation, then call confirm_ai_action."
    elif mode == "clarification":
        payload["clarification_prompt"] = str((response.get("clarification") or {}).get("prompt") or response.get("summary") or "")
        payload["options"] = list((response.get("clarification") or {}).get("candidates") or [])
        payload["next_step"] = "Ask the manager to choose one option, then call clarify_ai_action with the selected identifiers."
    elif mode == "redirect":
        payload["redirect"] = dict(response.get("redirect") or {})
    else:
        payload["ui_payload"] = response.get("ui_payload")
    return payload
