from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import aiosqlite

from app.db import queries


def _conversation_type_from_event(event: str) -> str:
    return "chat" if event.startswith("chat_") else "call"


def _conversation_payload(body: dict, conversation_type: str) -> dict[str, Any]:
    candidates = (
        body.get(conversation_type),
        body.get(f"{conversation_type}_detail"),
        body.get("conversation"),
        body.get("data"),
        body,
    )
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return {}


def _pick_value(*mappings: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        for key in keys:
            value = mapping.get(key)
            if value not in (None, ""):
                return value
    return None


def _coerce_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _transcript_text_from_items(items: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        speaker = item.get("speaker") or item.get("role") or item.get("sender")
        text = item.get("text") or item.get("message") or item.get("content")
        if not text:
            continue
        lines.append(f"{speaker}: {text}" if speaker else str(text))
    return "\n".join(lines)


def _extract_transcript_items(body: dict, payload: dict) -> list[dict[str, Any]]:
    candidate = _pick_value(
        payload,
        body,
        keys=(
            "transcript_items",
            "transcript_object",
            "messages",
            "message_history",
            "utterances",
            "conversation",
        ),
    )
    if isinstance(candidate, list):
        return [item for item in candidate if isinstance(item, dict)]
    if isinstance(candidate, dict):
        return [candidate]
    return []


def _extract_transcript_text(body: dict, payload: dict, items: list[dict[str, Any]]) -> Optional[str]:
    transcript = _pick_value(payload, body, keys=("transcript_text", "transcript"))
    if isinstance(transcript, str) and transcript.strip():
        return transcript
    derived = _transcript_text_from_items(items)
    return derived or None


def _extract_analysis(body: dict, payload: dict, conversation_type: str) -> dict[str, Any]:
    candidate = _pick_value(
        payload,
        body,
        keys=(f"{conversation_type}_analysis", "analysis"),
    )
    return candidate if isinstance(candidate, dict) else {}


def _extract_conversation_summary(
    body: dict,
    payload: dict,
    analysis: dict[str, Any],
    conversation_type: str,
) -> Optional[str]:
    summary = _pick_value(
        analysis,
        payload,
        body,
        keys=(f"{conversation_type}_summary", "summary", "conversation_summary", "call_summary", "chat_summary"),
    )
    return summary.strip() if isinstance(summary, str) and summary.strip() else None


def _normalize_timestamp(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        if value > 1_000_000_000_000:
            value = value / 1000.0
        return datetime.utcfromtimestamp(value).isoformat()
    return None


async def _sync_outreach_summary(
    db: aiosqlite.Connection,
    cascade_id: Optional[int],
    worker_id: Optional[int],
    summary: Optional[str],
) -> None:
    if not summary or cascade_id is None or worker_id is None:
        return
    attempts = await queries.list_outreach_attempts(db, cascade_id=cascade_id)
    for attempt in attempts:
        if int(attempt["worker_id"]) != worker_id:
            continue
        await queries.update_outreach_attempt(
            db,
            int(attempt["id"]),
            conversation_summary=summary,
        )
        return


async def persist_retell_payload(
    db: aiosqlite.Connection,
    body: dict,
) -> Optional[int]:
    event = body.get("event") or ""
    conversation_type = _conversation_type_from_event(event)
    payload = _conversation_payload(body, conversation_type)
    external_id = _pick_value(payload, body, keys=(f"{conversation_type}_id", "id"))
    if not isinstance(external_id, str) or not external_id.strip():
        return None

    metadata_value = _pick_value(payload, body, keys=("metadata",))
    metadata = metadata_value if isinstance(metadata_value, dict) else {}
    transcript_items = _extract_transcript_items(body, payload)
    transcript_text = _extract_transcript_text(body, payload, transcript_items)
    analysis = _extract_analysis(body, payload, conversation_type)
    summary = _extract_conversation_summary(body, payload, analysis, conversation_type)

    started_at = _normalize_timestamp(
        _pick_value(payload, body, keys=("started_at", "start_timestamp", "start_time"))
    )
    ended_at = _normalize_timestamp(
        _pick_value(payload, body, keys=("ended_at", "end_timestamp", "end_time"))
    )
    if event.endswith("_started") and started_at is None:
        started_at = datetime.utcnow().isoformat()
    if event.endswith("_ended") and ended_at is None:
        ended_at = datetime.utcnow().isoformat()

    cascade_id = _coerce_int(metadata.get("cascade_id") or body.get("cascade_id"))
    shift_id = _coerce_int(metadata.get("shift_id") or body.get("shift_id"))
    worker_id = _coerce_int(metadata.get("worker_id") or body.get("worker_id"))
    location_id = _coerce_int(metadata.get("location_id") or body.get("location_id"))

    conversation_id = await queries.upsert_retell_conversation(
        db,
        {
            "external_id": external_id.strip(),
            "conversation_type": conversation_type,
            "event_type": event,
            "direction": _pick_value(payload, body, keys=("direction",)),
            "status": _pick_value(payload, body, keys=("status", f"{conversation_type}_status", "call_status", "chat_status")),
            "agent_id": _pick_value(payload, body, keys=("agent_id", "override_agent_id")),
            "location_id": location_id,
            "shift_id": shift_id,
            "cascade_id": cascade_id,
            "worker_id": worker_id,
            "phone_from": _pick_value(payload, body, keys=("from_number", "from")),
            "phone_to": _pick_value(payload, body, keys=("to_number", "to")),
            "disconnection_reason": _pick_value(payload, body, keys=("disconnection_reason", "disconnect_reason")),
            "conversation_summary": summary,
            "transcript_text": transcript_text,
            "transcript_items": transcript_items,
            "analysis": analysis,
            "metadata": metadata,
            "raw_payload": body,
            "started_at": started_at,
            "ended_at": ended_at,
        },
    )
    await _sync_outreach_summary(db, cascade_id, worker_id, summary)
    return conversation_id


async def get_persisted_conversation(
    db: aiosqlite.Connection,
    conversation_id: int,
) -> Optional[dict]:
    return await queries.get_retell_conversation(db, conversation_id)
