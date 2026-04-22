from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.demand_features import PosSalesFact
from app.schemas.pos_sales import PosSalesFactPayload
from app.services.payload_utils import stable_payload_hash, stable_payload_json


def _json_safe_mapping(payload: Mapping[str, object] | None) -> dict[str, object]:
    return json.loads(stable_payload_json(dict(payload or {})))


def build_pos_sales_fact_dedupe_key(
    payload: PosSalesFactPayload | Mapping[str, object],
) -> str:
    normalized = payload if isinstance(payload, PosSalesFactPayload) else PosSalesFactPayload.model_validate(payload)
    source_payload = dict(normalized.source_payload or {})
    identity_ref = (
        source_payload.get("provider_record_id")
        or source_payload.get("source_record_id")
        or source_payload.get("external_id")
    )
    return stable_payload_hash(
        {
            "provider": normalized.provider,
            "provider_account_id": normalized.provider_account_id,
            "provider_location_id": normalized.provider_location_id,
            "bucket_start": normalized.bucket_start.isoformat(),
            "bucket_end": normalized.bucket_end.isoformat(),
            "identity_ref": identity_ref,
        }
    )


def _apply_pos_sales_fact_payload(
    row: PosSalesFact,
    payload: PosSalesFactPayload,
    *,
    dedupe_key: str,
    ingested_at: datetime,
) -> PosSalesFact:
    row.business_id = payload.business_id
    row.location_id = payload.location_id
    row.provider = payload.provider
    row.provider_account_id = payload.provider_account_id
    row.provider_location_id = payload.provider_location_id
    row.observed_at = payload.observed_at
    row.bucket_start = payload.bucket_start
    row.bucket_end = payload.bucket_end
    row.gross_sales_cents = int(payload.gross_sales_cents)
    row.net_sales_cents = int(payload.net_sales_cents)
    row.order_count = int(payload.order_count)
    row.guest_count = int(payload.guest_count) if payload.guest_count is not None else None
    row.refund_count = int(payload.refund_count) if payload.refund_count is not None else None
    row.source_payload = _json_safe_mapping(payload.source_payload)
    row.ingested_at = ingested_at
    row.dedupe_key = dedupe_key
    return row


async def upsert_pos_sales_fact(
    session: AsyncSession,
    payload: PosSalesFactPayload | Mapping[str, object],
) -> PosSalesFact:
    rows = await upsert_pos_sales_facts(session, [payload])
    return rows[0]


async def upsert_pos_sales_facts(
    session: AsyncSession,
    payloads: Sequence[PosSalesFactPayload | Mapping[str, object]],
) -> list[PosSalesFact]:
    ingested_at = datetime.now(timezone.utc)
    normalized_payloads = [
        payload if isinstance(payload, PosSalesFactPayload) else PosSalesFactPayload.model_validate(payload)
        for payload in payloads
    ]
    dedupe_index: dict[tuple[str, str], PosSalesFact] = {}
    persisted: dict[tuple[str, str], PosSalesFact] = {}

    for payload in normalized_payloads:
        dedupe_key = payload.dedupe_key or build_pos_sales_fact_dedupe_key(payload)
        cache_key = (payload.provider, dedupe_key)
        row = dedupe_index.get(cache_key)

        if row is None:
            result = await session.execute(
                select(PosSalesFact).where(
                    PosSalesFact.provider == payload.provider,
                    PosSalesFact.dedupe_key == dedupe_key,
                )
            )
            row = next(iter(result.scalars().all()), None)

        if row is None:
            row = PosSalesFact(
                business_id=payload.business_id,
                location_id=payload.location_id,
                provider=payload.provider,
                provider_account_id=payload.provider_account_id,
                provider_location_id=payload.provider_location_id,
                observed_at=payload.observed_at,
                bucket_start=payload.bucket_start,
                bucket_end=payload.bucket_end,
                gross_sales_cents=0,
                net_sales_cents=0,
                order_count=0,
                guest_count=None,
                refund_count=None,
                source_payload={},
                ingested_at=ingested_at,
                dedupe_key=dedupe_key,
            )
            session.add(row)

        dedupe_index[cache_key] = _apply_pos_sales_fact_payload(
            row,
            payload,
            dedupe_key=dedupe_key,
            ingested_at=ingested_at,
        )
        persisted[cache_key] = row

    await session.flush()
    return list(persisted.values())


async def list_pos_sales_facts(
    session: AsyncSession,
    *,
    business_id,
    location_id=None,
    provider: str | None = None,
    bucket_start: datetime | None = None,
    bucket_end: datetime | None = None,
    limit: int = 500,
) -> list[PosSalesFact]:
    stmt = (
        select(PosSalesFact)
        .where(PosSalesFact.business_id == business_id)
        .order_by(PosSalesFact.bucket_start.asc(), PosSalesFact.id.asc())
        .limit(max(1, min(limit, 5000)))
    )
    if location_id is not None:
        stmt = stmt.where(PosSalesFact.location_id == location_id)
    if provider is not None:
        stmt = stmt.where(PosSalesFact.provider == provider)
    if bucket_start is not None:
        stmt = stmt.where(PosSalesFact.bucket_start >= bucket_start)
    if bucket_end is not None:
        stmt = stmt.where(PosSalesFact.bucket_start < bucket_end)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def summarize_pos_sales_by_local_bucket(
    rows: Sequence[PosSalesFact],
    *,
    timezone_name: str,
    bucket_minutes: int,
) -> dict[tuple[str | None, int, int, int], dict[str, object]]:
    local_zone = ZoneInfo(timezone_name)
    aggregates: dict[tuple[str | None, int, int, int], dict[str, float]] = {}

    for row in rows:
        duration_minutes = int((row.bucket_end - row.bucket_start).total_seconds() // 60)
        if duration_minutes != bucket_minutes:
            continue
        local_bucket_start = row.bucket_start.astimezone(local_zone)
        key = (
            str(row.location_id) if row.location_id is not None else None,
            local_bucket_start.weekday(),
            local_bucket_start.hour,
            duration_minutes,
        )
        bucket = aggregates.setdefault(
            key,
            {
                "sample_count": 0.0,
                "gross_sales_cents_total": 0.0,
                "net_sales_cents_total": 0.0,
                "order_count_total": 0.0,
                "guest_count_total": 0.0,
                "guest_count_samples": 0.0,
                "refund_count_total": 0.0,
                "refund_count_samples": 0.0,
            },
        )
        bucket["sample_count"] += 1.0
        bucket["gross_sales_cents_total"] += float(row.gross_sales_cents)
        bucket["net_sales_cents_total"] += float(row.net_sales_cents)
        bucket["order_count_total"] += float(row.order_count)
        if row.guest_count is not None:
            bucket["guest_count_total"] += float(row.guest_count)
            bucket["guest_count_samples"] += 1.0
        if row.refund_count is not None:
            bucket["refund_count_total"] += float(row.refund_count)
            bucket["refund_count_samples"] += 1.0

    summaries: dict[tuple[str | None, int, int, int], dict[str, object]] = {}
    for key, bucket in aggregates.items():
        sample_count = max(bucket["sample_count"], 1.0)
        guest_samples = max(bucket["guest_count_samples"], 1.0)
        refund_samples = max(bucket["refund_count_samples"], 1.0)
        summaries[key] = {
            "pos_sales_sample_count_28d": int(bucket["sample_count"]),
            "pos_gross_sales_cents_mean_28d": int(round(bucket["gross_sales_cents_total"] / sample_count)),
            "pos_net_sales_cents_mean_28d": int(round(bucket["net_sales_cents_total"] / sample_count)),
            "pos_order_count_mean_28d": round(bucket["order_count_total"] / sample_count, 2),
            "pos_guest_count_mean_28d": (
                round(bucket["guest_count_total"] / guest_samples, 2) if bucket["guest_count_samples"] > 0 else None
            ),
            "pos_refund_count_mean_28d": (
                round(bucket["refund_count_total"] / refund_samples, 2)
                if bucket["refund_count_samples"] > 0
                else None
            ),
        }
    return summaries
