from __future__ import annotations

from datetime import datetime, timedelta

import aiosqlite

from app.config import settings
from app.db import queries
from app.services import retell, retell_ingest

STATE_KEY_LAST_RECONCILE_AT = "retell_last_successful_reconcile_at"
STATE_KEY_LAST_WEBHOOK_SUCCESS_AT = "retell_last_successful_webhook_at"
STATE_KEY_LAST_WEBHOOK_FAILURE_AT = "retell_last_failed_webhook_at"
STATE_KEY_LAST_WEBHOOK_FAILURE_EVENT = "retell_last_failed_webhook_event"
STATE_KEY_LAST_WEBHOOK_FAILURE_ERROR = "retell_last_failed_webhook_error"


def _conversation_timestamp(payload: dict) -> datetime | None:
    for key in ("start_timestamp", "end_timestamp", "started_at", "ended_at"):
        value = payload.get(key)
        if isinstance(value, (int, float)):
            if value > 1_000_000_000_000:
                value = value / 1000.0
            return datetime.utcfromtimestamp(value)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                continue
    return None


def _coerce_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _shift_start_datetime(shift: dict) -> datetime | None:
    shift_date = shift.get("date")
    shift_start = shift.get("start_time")
    if not shift_date or not shift_start:
        return None
    try:
        return datetime.fromisoformat(f"{shift_date}T{shift_start}")
    except ValueError:
        return None


async def _urgent_shift_ids(db: aiosqlite.Connection, *, now: datetime) -> set[int]:
    urgent_ids: set[int] = set()
    window_end = now + timedelta(hours=settings.retell_reconcile_urgent_window_hours)

    for shift in await queries.list_shifts(db, status="vacant"):
        shift_start = _shift_start_datetime(shift)
        if shift_start is None:
            continue
        if shift_start <= window_end:
            urgent_ids.add(int(shift["id"]))
    return urgent_ids


async def _targeted_repair(
    db: aiosqlite.Connection,
    *,
    now: datetime,
    shift_ids: set[int] | None,
    seen_external_ids: set[str] | None = None,
) -> dict[str, int | list[str]]:
    if shift_ids is not None and not shift_ids:
        return {"calls": 0, "chats": 0, "call_ids": [], "chat_ids": []}

    since = (now - timedelta(minutes=settings.retell_reconcile_targeted_lookback_minutes)).isoformat()
    entries = await queries.list_recent_outreach_audit_entries(
        db,
        since=since,
        shift_ids=shift_ids,
    )

    call_ids: list[str] = []
    chat_ids: list[str] = []
    seen: set[str] = set(seen_external_ids or set())

    for entry in entries:
        details = entry.get("details") or {}
        entry_timestamp = _coerce_timestamp(entry.get("timestamp"))
        if entry_timestamp and entry_timestamp > now - timedelta(minutes=settings.retell_reconcile_drift_grace_minutes):
            continue
        call_id = details.get("call_id")
        chat_id = details.get("chat_id")
        if not chat_id:
            message_sid = details.get("message_sid")
            if isinstance(message_sid, str) and message_sid.startswith("chat_"):
                chat_id = message_sid

        if isinstance(call_id, str) and call_id and call_id not in seen:
            existing = await queries.get_retell_conversation_by_external_id(db, call_id)
            if existing is None or not (existing.get("transcript_text") or existing.get("analysis")):
                call_ids.append(call_id)
                seen.add(call_id)

        if isinstance(chat_id, str) and chat_id and chat_id not in seen:
            existing = await queries.get_retell_conversation_by_external_id(db, chat_id)
            if existing is None or not (existing.get("transcript_text") or existing.get("analysis")):
                chat_ids.append(chat_id)
                seen.add(chat_id)

    synced_calls = 0
    synced_chats = 0
    for call_id in call_ids:
        await sync_call_by_id(db, call_id)
        synced_calls += 1
    for chat_id in chat_ids:
        await sync_chat_by_id(db, chat_id)
        synced_chats += 1

    return {
        "calls": synced_calls,
        "chats": synced_chats,
        "call_ids": call_ids,
        "chat_ids": chat_ids,
    }


async def mark_webhook_success(db: aiosqlite.Connection, *, event: str) -> None:
    now = datetime.utcnow().isoformat()
    await queries.set_app_state(db, STATE_KEY_LAST_WEBHOOK_SUCCESS_AT, now)
    await queries.set_app_state(db, STATE_KEY_LAST_WEBHOOK_FAILURE_ERROR, "")
    await queries.set_app_state(db, STATE_KEY_LAST_WEBHOOK_FAILURE_EVENT, "")


async def mark_webhook_failure(db: aiosqlite.Connection, *, event: str, error: str) -> None:
    now = datetime.utcnow().isoformat()
    await queries.set_app_state(db, STATE_KEY_LAST_WEBHOOK_FAILURE_AT, now)
    await queries.set_app_state(db, STATE_KEY_LAST_WEBHOOK_FAILURE_EVENT, event or "unknown")
    await queries.set_app_state(db, STATE_KEY_LAST_WEBHOOK_FAILURE_ERROR, error[:500])


async def _webhook_repair_mode(db: aiosqlite.Connection, *, now: datetime) -> dict:
    last_success = _coerce_timestamp(await queries.get_app_state(db, STATE_KEY_LAST_WEBHOOK_SUCCESS_AT))
    last_failure = _coerce_timestamp(await queries.get_app_state(db, STATE_KEY_LAST_WEBHOOK_FAILURE_AT))
    stale = last_success is None or last_success < now - timedelta(minutes=settings.retell_webhook_stale_minutes)
    recent_failure = last_failure is not None and (
        last_success is None or last_failure >= last_success
    )
    return {
        "stale": stale,
        "recent_failure": recent_failure,
        "repair_mode": stale or recent_failure,
    }


async def _incremental_cutoff(
    db: aiosqlite.Connection,
    *,
    now: datetime,
    requested_lookback_minutes: int,
) -> datetime:
    baseline = now - timedelta(minutes=max(1, requested_lookback_minutes))
    last_reconcile = _coerce_timestamp(await queries.get_app_state(db, STATE_KEY_LAST_RECONCILE_AT))
    if last_reconcile is None:
        return baseline
    overlap_cutoff = last_reconcile - timedelta(minutes=settings.retell_reconcile_overlap_minutes)
    return max(baseline, overlap_cutoff)


async def sync_call_by_id(db: aiosqlite.Connection, call_id: str) -> dict:
    call = await retell.get_call(call_id)
    conversation_id = await retell_ingest.persist_retell_payload(
        db,
        {"event": "call_reconciled", "call": call},
    )
    return {"status": "ok", "call_id": call_id, "conversation_id": conversation_id}


async def sync_chat_by_id(db: aiosqlite.Connection, chat_id: str) -> dict:
    chat = await retell.get_chat(chat_id)
    conversation_id = await retell_ingest.persist_retell_payload(
        db,
        {"event": "chat_reconciled", "chat": chat},
    )
    return {"status": "ok", "chat_id": chat_id, "conversation_id": conversation_id}


async def sync_recent_activity(
    db: aiosqlite.Connection,
    *,
    lookback_minutes: int | None = None,
    limit: int = 50,
) -> dict:
    now = datetime.utcnow()
    effective_lookback = lookback_minutes or settings.retell_reconcile_default_lookback_minutes
    webhook_mode = await _webhook_repair_mode(db, now=now)
    if webhook_mode["repair_mode"]:
        effective_lookback = max(
            effective_lookback,
            settings.retell_reconcile_failure_lookback_minutes,
        )
    cutoff = await _incremental_cutoff(
        db,
        now=now,
        requested_lookback_minutes=effective_lookback,
    )
    urgent_shift_ids = await _urgent_shift_ids(db, now=now)
    targeted = await _targeted_repair(db, now=now, shift_ids=urgent_shift_ids)
    repair_boost = {"calls": 0, "chats": 0}
    if webhook_mode["repair_mode"]:
        repair_boost = await _targeted_repair(
            db,
            now=now,
            shift_ids=None,
            seen_external_ids=set(targeted["call_ids"]) | set(targeted["chat_ids"]),
        )
    synced_calls = 0
    synced_chats = 0

    for call in await retell.list_calls(limit=limit):
        stamp = _conversation_timestamp(call)
        if stamp is not None and stamp < cutoff:
            continue
        await retell_ingest.persist_retell_payload(db, {"event": "call_reconciled", "call": call})
        synced_calls += 1

    for chat in await retell.list_chats(limit=limit):
        stamp = _conversation_timestamp(chat)
        if stamp is not None and stamp < cutoff:
            continue
        await retell_ingest.persist_retell_payload(db, {"event": "chat_reconciled", "chat": chat})
        synced_chats += 1

    await queries.set_app_state(db, STATE_KEY_LAST_RECONCILE_AT, now.isoformat())

    return {
        "status": "ok",
        "lookback_minutes": effective_lookback,
        "incremental_cutoff": cutoff.isoformat(),
        "urgent_shift_count": len(urgent_shift_ids),
        "webhook_repair_mode": webhook_mode["repair_mode"],
        "webhook_stale": webhook_mode["stale"],
        "recent_webhook_failure": webhook_mode["recent_failure"],
        "calls_synced": synced_calls + targeted["calls"] + repair_boost["calls"],
        "chats_synced": synced_chats + targeted["chats"] + repair_boost["chats"],
        "targeted_calls_synced": targeted["calls"],
        "targeted_chats_synced": targeted["chats"],
        "repair_mode_calls_synced": repair_boost["calls"],
        "repair_mode_chats_synced": repair_boost["chats"],
    }
