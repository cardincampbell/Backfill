from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integrations import ProviderCallbackLog


def _normalized_mapping(mapping: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        return {}
    return {
        str(key): value if isinstance(value, (dict, list, str, int, float, bool)) or value is None else str(value)
        for key, value in mapping.items()
    }


def _stable_payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def dedupe_key_for_callback(
    *,
    provider: str,
    provider_event_id: str | None,
    payload: dict[str, Any] | None,
) -> str:
    normalized_provider = provider.strip().lower()
    normalized_event_id = str(provider_event_id or "").strip()
    if normalized_event_id:
        return f"{normalized_provider}:{normalized_event_id}"
    return f"{normalized_provider}:{_stable_payload_hash(_normalized_mapping(payload))}"


async def record_raw_callback(
    session: AsyncSession,
    *,
    provider: str,
    route_key: str,
    headers: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    event_type: str | None = None,
    provider_event_id: str | None = None,
) -> tuple[ProviderCallbackLog, bool]:
    dedupe_key = dedupe_key_for_callback(
        provider=provider,
        provider_event_id=provider_event_id,
        payload=payload,
    )
    existing = await session.scalar(
        select(ProviderCallbackLog).where(
            ProviderCallbackLog.provider == provider.strip().lower(),
            ProviderCallbackLog.dedupe_key == dedupe_key,
        )
    )
    if existing is not None:
        return existing, False

    entry = ProviderCallbackLog(
        provider=provider.strip().lower(),
        route_key=route_key.strip(),
        event_type=(str(event_type).strip() if event_type is not None else None) or None,
        provider_event_id=(str(provider_event_id).strip() if provider_event_id is not None else None) or None,
        dedupe_key=dedupe_key,
        status="received",
        headers=_normalized_mapping(headers),
        payload=_normalized_mapping(payload),
    )
    session.add(entry)
    await session.flush()
    return entry, True


async def mark_processed(
    session: AsyncSession,
    entry: ProviderCallbackLog,
    *,
    result_payload: dict[str, Any] | None = None,
) -> ProviderCallbackLog:
    entry.status = "processed"
    entry.processed_at = datetime.now(timezone.utc)
    entry.result_payload = _normalized_mapping(result_payload)
    entry.error_message = None
    await session.flush()
    return entry


async def mark_failed(
    session: AsyncSession,
    entry: ProviderCallbackLog,
    *,
    error_message: str,
    result_payload: dict[str, Any] | None = None,
) -> ProviderCallbackLog:
    entry.status = "failed"
    entry.processed_at = datetime.now(timezone.utc)
    entry.error_message = error_message.strip() or "callback_processing_failed"
    entry.result_payload = _normalized_mapping(result_payload)
    await session.flush()
    return entry
