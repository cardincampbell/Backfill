"""
Retell webhook handler.
"""
from __future__ import annotations

from typing import Optional, Type

from fastapi import APIRouter, Depends, HTTPException, Request
import aiosqlite
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.db.database import get_db
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
