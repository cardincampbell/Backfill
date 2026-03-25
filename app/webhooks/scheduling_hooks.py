"""
Webhook receivers for scheduling platforms.

These handlers translate external scheduler events into the same vacancy flow
used by native Backfill operations.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
import aiosqlite

from app.config import settings
from app.db.database import get_db
from app.db import queries
from app.services import cascade as cascade_svc
from app.services import shift_manager
from app.services import sync_engine

router = APIRouter(prefix="/webhooks/scheduling", tags=["scheduling-webhooks"])


def _nested(data: dict[str, Any], *path: str) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first_present(data: dict[str, Any], paths: list[tuple[str, ...]]) -> Any:
    for path in paths:
        value = _nested(data, *path)
        if value not in (None, ""):
            return value
    return None


def _valid_signature(secret: str, payload: bytes, signature: str) -> bool:
    if not secret:
        return True
    if not signature:
        return False
    signature = signature.strip()
    if signature.lower().startswith("sha256="):
        signature = signature.split("=", 1)[1]
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    candidates = {
        digest.hex(),
        base64.b64encode(digest).decode("utf-8"),
    }
    return any(hmac.compare_digest(signature, candidate) for candidate in candidates)


async def _resolve_local_shift(
    db: aiosqlite.Connection,
    platform: str,
    body: dict[str, Any],
) -> Optional[dict]:
    shift_id = _first_present(body, [("shift_id",), ("shift", "id"), ("data", "shift_id"), ("data", "id"), ("resource", "id")])
    if shift_id is not None:
        shift_id_text = str(shift_id)
        shift = await queries.get_shift_by_platform_id(db, platform, shift_id_text)
        if shift is not None:
            return shift
        if shift_id_text.isdigit():
            shift = await queries.get_shift(db, int(shift_id_text))
            if shift is not None:
                return shift
    return None


async def _resolve_worker_id(
    db: aiosqlite.Connection,
    restaurant_id: int,
    body: dict[str, Any],
) -> Optional[int]:
    local_worker_id = _first_present(body, [("worker_id",), ("employee_id",), ("user_id",), ("data", "worker_id"), ("data", "employee_id"), ("data", "user_id")])
    if local_worker_id is not None:
        worker_text = str(local_worker_id)
        worker = await queries.get_worker_by_source_id(db, worker_text, restaurant_id=restaurant_id)
        if worker is not None:
            return int(worker["id"])
        if worker_text.isdigit():
            worker = await queries.get_worker(db, int(worker_text))
            if worker is not None:
                return int(worker["id"])
    return None


async def _create_vacancy_from_webhook(
    db: aiosqlite.Connection,
    platform: str,
    body: dict[str, Any],
) -> dict:
    shift = await _resolve_local_shift(db, platform, body)
    if shift is None:
        return {"status": "queued_for_reconcile", "platform": platform}
    caller_id = await _resolve_worker_id(db, shift["restaurant_id"], body)
    cascade = await shift_manager.create_vacancy(
        db,
        shift_id=int(shift["id"]),
        called_out_by_worker_id=caller_id,
        actor=f"{platform}:webhook",
    )
    result = await cascade_svc.advance(db, cascade["id"])
    return {
        "status": "vacancy_created",
        "platform": platform,
        "shift_id": shift["id"],
        "cascade_id": cascade["id"],
        "result": result,
    }


def _source_event_id(platform: str, body: dict[str, Any]) -> Optional[str]:
    raw_id = _first_present(
        body,
        [
            ("event_id",),
            ("id",),
            ("data", "event_id"),
            ("resource", "id"),
            ("meta", "id"),
        ],
    )
    event_type = str(body.get("type") or body.get("event") or body.get("topic") or body.get("resource") or "")
    if raw_id not in (None, ""):
        return f"{platform}:{event_type}:{raw_id}"
    return None


async def _queue_platform_event(
    db: aiosqlite.Connection,
    platform: str,
    body: dict[str, Any],
    *,
    event_type: Optional[str],
    event_scope: str,
    scope_ref: Optional[str] = None,
    process_now: bool = False,
) -> dict:
    shift = await _resolve_local_shift(db, platform, body)
    restaurant_id = int(shift["restaurant_id"]) if shift else None
    queued = await sync_engine.enqueue_event_reconcile(
        db,
        platform=platform,
        payload=body,
        restaurant_id=restaurant_id,
        event_type=event_type,
        event_scope=event_scope,
        scope_ref=scope_ref,
        source_event_id=_source_event_id(platform, body),
    )
    response = {
        "status": "queued",
        "platform": platform,
        "event": event_type,
        "job_id": queued["job"]["id"] if queued.get("job") else None,
        "integration_event_id": queued["event"]["id"] if queued.get("event") else None,
    }
    if process_now and queued.get("job"):
        response["processed"] = await sync_engine.process_sync_job(db, int(queued["job"]["id"]))
    return response


@router.post("/seven_shifts")
async def seven_shifts_webhook(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    raw_body = await request.body()
    if not _valid_signature(
        settings.sevenshifts_webhook_secret,
        raw_body,
        request.headers.get("X-7shifts-Signature", "") or request.headers.get("X-SevenShifts-Signature", ""),
    ):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    body = await request.json()
    event_type = body.get("type") or body.get("event")
    if event_type in {"shift.deleted", "shift.unassigned", "punch.callout"}:
        queued = await _queue_platform_event(
            db,
            "7shifts",
            body,
            event_type=event_type,
            event_scope="shift",
            scope_ref=str(_first_present(body, [("shift_id",), ("shift", "id"), ("data", "shift_id"), ("data", "id")]) or ""),
            process_now=True,
        )
        vacancy = await _create_vacancy_from_webhook(db, "7shifts", body)
        return {**queued, **vacancy}
    if event_type == "schedule.published":
        return await _queue_platform_event(
            db,
            "7shifts",
            body,
            event_type=event_type,
            event_scope="schedule",
            process_now=True,
        )
    return await _queue_platform_event(
        db,
        "7shifts",
        body,
        event_type=event_type,
        event_scope="unknown",
    )


@router.post("/deputy")
async def deputy_webhook(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    raw_body = await request.body()
    if not _valid_signature(
        settings.deputy_webhook_secret,
        raw_body,
        request.headers.get("X-Deputy-Signature", ""),
    ):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    body = await request.json()
    topic = str(body.get("topic") or body.get("resource") or "")
    event = str(body.get("event") or body.get("action") or "")
    status = str(_first_present(body, [("data", "status"), ("data", "state"), ("status",)]) or "").lower()
    if topic.lower() == "roster" and (event.lower() == "delete" or status in {"deleted", "cancelled", "unassigned", "open"}):
        queued = await _queue_platform_event(
            db,
            "deputy",
            body,
            event_type=f"{topic}.{event}",
            event_scope="shift",
            scope_ref=str(_first_present(body, [("resource", "id"), ("data", "shift_id"), ("data", "id")]) or ""),
            process_now=True,
        )
        vacancy = await _create_vacancy_from_webhook(db, "deputy", body)
        return {**queued, **vacancy}
    return await _queue_platform_event(
        db,
        "deputy",
        body,
        event_type=f"{topic}.{event}",
        event_scope="schedule",
    )


@router.post("/wheniwork")
async def when_i_work_webhook(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    raw_body = await request.body()
    if not _valid_signature(
        settings.wheniwork_webhook_secret,
        raw_body,
        request.headers.get("X-WhenIWork-Signature", ""),
    ):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    body = await request.json()
    event_type = str(body.get("event") or body.get("type") or "")
    if event_type in {"shift.deleted", "shift.unassigned", "open_shift.created", "punch.callout"}:
        queued = await _queue_platform_event(
            db,
            "wheniwork",
            body,
            event_type=event_type,
            event_scope="shift",
            scope_ref=str(_first_present(body, [("shift_id",), ("data", "shift_id"), ("data", "id")]) or ""),
            process_now=True,
        )
        vacancy = await _create_vacancy_from_webhook(db, "wheniwork", body)
        return {**queued, **vacancy}
    return await _queue_platform_event(
        db,
        "wheniwork",
        body,
        event_type=event_type,
        event_scope="schedule",
    )
