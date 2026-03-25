"""
Retell webhook handler.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
import aiosqlite

from app.db.database import get_db
from app.services import caller_lookup, consent as consent_svc, shift_manager, cascade as cascade_svc
from app.services import notifications as notifications_svc
from app.models.audit import AuditAction
from app.services import audit as audit_svc

router = APIRouter(prefix="/webhooks", tags=["retell-webhooks"])


@router.post("/retell")
async def retell_webhook(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    body = await request.json()
    event = body.get("event")

    # ── call lifecycle events ─────────────────────────────────────────────────
    if event == "call_started":
        return {"status": "ok"}

    if event == "call_ended":
        return {"status": "ok"}

    if event == "call_analyzed":
        return {"status": "ok"}

    # ── function calls from the agent ─────────────────────────────────────────
    if event == "function_call":
        name = body.get("name")
        args = body.get("args", {})
        return await _dispatch(db, name, args)

    return {"status": "ignored", "event": event}


# ── function call dispatcher ──────────────────────────────────────────────────

async def _dispatch(db: aiosqlite.Connection, name: str, args: dict) -> dict:
    handlers = {
        "lookup_caller":   _lookup_caller,
        "log_consent":     _log_consent,
        "create_vacancy":  _create_vacancy,
        "confirm_fill":    _confirm_fill,
        "get_open_shifts": _get_open_shifts,
        "get_shift_status": _get_shift_status,
        "create_open_shift": _create_open_shift,
    }
    handler = handlers.get(name)
    if handler is None:
        raise HTTPException(status_code=400, detail=f"Unknown function call: {name!r}")
    return await handler(db, args)


async def _lookup_caller(db: aiosqlite.Connection, args: dict) -> dict:
    phone = args.get("phone", "").strip()
    if not phone:
        return {"found": False, "caller_type": "unknown", "record": None}
    return await caller_lookup.lookup(db, phone)


async def _log_consent(db: aiosqlite.Connection, args: dict) -> dict:
    worker_id = int(args["worker_id"])
    granted = bool(args.get("granted", True))
    channel = args.get("channel", "inbound_call")

    if granted:
        await consent_svc.grant(db, worker_id, channel=channel)
        return {"status": "consent_granted", "worker_id": worker_id}
    else:
        await consent_svc.revoke(db, worker_id, channel="voice")
        return {"status": "consent_revoked", "worker_id": worker_id}


async def _create_vacancy(db: aiosqlite.Connection, args: dict) -> dict:
    shift_id = int(args["shift_id"])
    worker_id = int(args["worker_id"])
    cascade = await shift_manager.create_vacancy(
        db,
        shift_id=shift_id,
        called_out_by_worker_id=worker_id,
        actor=f"worker:{worker_id}",
    )
    # Immediately kick off the first outreach
    result = await cascade_svc.advance(db, cascade["id"])
    return {
        "status": "vacancy_created",
        "cascade_id": cascade["id"],
        "first_outreach": result,
    }


async def _confirm_fill(db: aiosqlite.Connection, args: dict) -> dict:
    cascade_id = int(args["cascade_id"])
    worker_id = int(args["worker_id"])
    accepted = bool(args.get("accepted", False))
    summary = args.get("conversation_summary", "")

    await cascade_svc.record_response(
        db,
        cascade_id=cascade_id,
        worker_id=worker_id,
        accepted=accepted,
        summary=summary,
    )

    if accepted:
        await notifications_svc.fire_manager_notification(db, cascade_id, worker_id, filled=True)
        return {"status": "shift_filled", "worker_id": worker_id}
    else:
        return {"status": "declined", "worker_id": worker_id}


async def _get_open_shifts(db: aiosqlite.Connection, args: dict) -> dict:
    restaurant_id = args.get("restaurant_id")
    query = "SELECT * FROM shifts WHERE status='vacant'"
    params: list = []
    if restaurant_id:
        query += " AND restaurant_id=?"
        params.append(int(restaurant_id))
    query += " ORDER BY date ASC LIMIT 10"
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return {"shifts": [dict(r) for r in rows]}


async def _get_shift_status(db: aiosqlite.Connection, args: dict) -> dict:
    from app.db.queries import get_shift_status

    shift_id = args.get("shift_id")
    if shift_id is None:
        raise HTTPException(status_code=400, detail="shift_id is required")
    payload = await get_shift_status(db, int(shift_id))
    if payload is None:
        raise HTTPException(status_code=404, detail="Shift not found")
    return payload


async def _create_open_shift(db: aiosqlite.Connection, args: dict) -> dict:
    from app.db.queries import insert_shift, get_shift

    required = ["restaurant_id", "role", "date", "start_time", "end_time", "pay_rate"]
    missing = [key for key in required if key not in args]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing fields: {', '.join(missing)}")

    shift_id = await insert_shift(
        db,
        {
            "restaurant_id": int(args["restaurant_id"]),
            "role": args["role"],
            "date": args["date"],
            "start_time": args["start_time"],
            "end_time": args["end_time"],
            "pay_rate": float(args["pay_rate"]),
            "requirements": args.get("requirements", []),
            "status": "vacant",
            "source_platform": "backfill_native",
        },
    )
    cascade = await shift_manager.create_vacancy(
        db,
        shift_id=shift_id,
        called_out_by_worker_id=None,
        actor=f"manager:{args['restaurant_id']}",
    )
    result = await cascade_svc.advance(db, cascade["id"])
    return {
        "shift": await get_shift(db, shift_id),
        "cascade_id": cascade["id"],
        "first_outreach": result,
    }


