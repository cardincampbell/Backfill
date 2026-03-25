"""
Scheduling integration orchestration.

This layer owns adapter selection, roster/schedule sync, and best-effort
write-back when a Backfill fill should be reflected into the source scheduler.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import aiosqlite

from app.config import settings
from app.db import queries
from app.integrations.deputy import DeputyAdapter
from app.integrations.homebase import HomebaseAdapter
from app.integrations.native_lite import NativeLiteAdapter
from app.integrations.seven_shifts import SevenShiftsAdapter
from app.integrations.when_i_work import WhenIWorkAdapter


def integration_mode_for_restaurant(restaurant: dict | None) -> str:
    if not restaurant:
        return "native"
    value = restaurant.get("scheduling_platform") or "backfill_native"
    if value in {"wheniwork", "homebase", "7shifts", "deputy"}:
        if writeback_is_enabled(restaurant) and scheduler_supports_writeback(value):
            return "companion_writeback"
        return "companion"
    return "native"


def scheduler_supports_writeback(platform: str | None) -> bool:
    value = platform or "backfill_native"
    return value in {"7shifts", "deputy"}


def writeback_is_enabled(restaurant: dict | None) -> bool:
    if not restaurant:
        return False
    return bool(restaurant.get("writeback_enabled")) and scheduler_supports_writeback(
        restaurant.get("scheduling_platform")
    )


async def get_integration_health(db: aiosqlite.Connection, restaurant_id: int) -> dict:
    restaurant = await queries.get_restaurant(db, restaurant_id)
    if restaurant is None:
        raise ValueError(f"Restaurant {restaurant_id} not found")

    platform = restaurant.get("scheduling_platform") or "backfill_native"
    platform_id = restaurant.get("scheduling_platform_id")
    mode = integration_mode_for_restaurant(restaurant)
    writeback_supported = scheduler_supports_writeback(platform)
    writeback_enabled = writeback_is_enabled(restaurant)

    if platform == "backfill_native":
        return {
            "restaurant_id": restaurant_id,
            "platform": platform,
            "mode": mode,
            "writable": False,
            "writeback_supported": False,
            "writeback_enabled": False,
            "writeback_subscription_tier": restaurant.get("writeback_subscription_tier") or "core",
            "status": restaurant.get("integration_status") or "native_lite",
            "integration_state": restaurant.get("integration_state") or "healthy",
            "reason": None,
        }

    try:
        _adapter_for_restaurant(db, restaurant)
        status = restaurant.get("integration_status") or "ready_to_sync"
        reason = None
    except RuntimeError as exc:
        status = "credentials_missing"
        reason = str(exc)

    return {
        "restaurant_id": restaurant_id,
        "platform": platform,
        "mode": mode,
        "writable": writeback_enabled,
        "writeback_supported": writeback_supported,
        "writeback_enabled": writeback_enabled,
        "writeback_subscription_tier": restaurant.get("writeback_subscription_tier") or "core",
        "platform_id_present": bool(platform_id),
        "status": status,
        "integration_state": restaurant.get("integration_state") or "healthy",
        "reason": reason,
        "last_roster_sync_at": restaurant.get("last_roster_sync_at"),
        "last_roster_sync_status": restaurant.get("last_roster_sync_status"),
        "last_schedule_sync_at": restaurant.get("last_schedule_sync_at"),
        "last_schedule_sync_status": restaurant.get("last_schedule_sync_status"),
        "last_sync_error": restaurant.get("last_sync_error"),
        "last_event_sync_at": restaurant.get("last_event_sync_at"),
        "last_rolling_sync_at": restaurant.get("last_rolling_sync_at"),
        "last_daily_sync_at": restaurant.get("last_daily_sync_at"),
        "last_writeback_at": restaurant.get("last_writeback_at"),
    }


async def connect_and_sync_restaurant(db: aiosqlite.Connection, restaurant_id: int) -> dict:
    health = await get_integration_health(db, restaurant_id)
    if health["platform"] == "backfill_native":
        await queries.update_restaurant(
            db,
            restaurant_id,
            {"integration_status": "native_lite", "integration_state": "healthy", "last_sync_error": None},
        )
        return {
            "restaurant_id": restaurant_id,
            "platform": health["platform"],
            "mode": health["mode"],
            "status": "native_lite",
            "roster_sync": None,
            "schedule_sync": None,
        }

    if health["status"] == "credentials_missing":
        await queries.update_restaurant(
            db,
            restaurant_id,
            {"integration_status": "credentials_missing", "integration_state": "degraded", "last_sync_error": health["reason"]},
        )
        return {
            "restaurant_id": restaurant_id,
            "platform": health["platform"],
            "mode": health["mode"],
            "status": "credentials_missing",
            "roster_sync": None,
            "schedule_sync": None,
            "error": health["reason"],
        }

    roster_result = await sync_roster(db, restaurant_id)
    schedule_result = await sync_schedule(
        db,
        restaurant_id,
        start_date=date.today(),
        end_date=date.today() + timedelta(days=14),
    )
    return {
        "restaurant_id": restaurant_id,
        "platform": health["platform"],
        "mode": health["mode"],
        "status": "connected",
        "roster_sync": roster_result,
        "schedule_sync": schedule_result,
    }


def _clean_phone(phone: str | None) -> str:
    return (phone or "").strip()


def _stringify(value: object | None) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _adapter_for_restaurant(db: aiosqlite.Connection, restaurant: dict):
    platform = restaurant.get("scheduling_platform") or "backfill_native"
    platform_id = restaurant.get("scheduling_platform_id") or ""

    if platform == "7shifts":
        if not (settings.sevenshifts_client_id and settings.sevenshifts_client_secret and platform_id):
            raise RuntimeError("7shifts integration requires client credentials and restaurant.scheduling_platform_id")
        return SevenShiftsAdapter(
            client_id=settings.sevenshifts_client_id,
            client_secret=settings.sevenshifts_client_secret,
            company_id=platform_id,
        )
    if platform == "deputy":
        if not (settings.deputy_client_id and settings.deputy_client_secret and platform_id):
            raise RuntimeError("Deputy integration requires client credentials and restaurant.scheduling_platform_id")
        return DeputyAdapter(
            client_id=settings.deputy_client_id,
            client_secret=settings.deputy_client_secret,
            install_url=platform_id,
        )
    if platform == "wheniwork":
        if not (settings.wheniwork_developer_key and platform_id):
            raise RuntimeError("When I Work integration requires WHENIWORK_DEVELOPER_KEY and restaurant.scheduling_platform_id")
        return WhenIWorkAdapter(
            api_token=settings.wheniwork_developer_key,
            account_id=platform_id,
        )
    if platform == "homebase":
        if not settings.homebase_api_key:
            raise RuntimeError("Homebase integration requires HOMEBASE_API_KEY")
        return HomebaseAdapter(api_key=settings.homebase_api_key)
    return NativeLiteAdapter(db)


async def sync_roster(db: aiosqlite.Connection, restaurant_id: int) -> dict:
    restaurant = await queries.get_restaurant(db, restaurant_id)
    if restaurant is None:
        raise ValueError(f"Restaurant {restaurant_id} not found")

    try:
        adapter = _adapter_for_restaurant(db, restaurant)
    except RuntimeError as exc:
        await queries.update_restaurant(
            db,
            restaurant_id,
            {
                "integration_status": "credentials_missing",
                "integration_state": "degraded",
                "last_roster_sync_status": "failed",
                "last_sync_error": str(exc),
            },
        )
        raise
    platform = restaurant.get("scheduling_platform") or "backfill_native"
    try:
        workers = await adapter.sync_roster(restaurant_id)
    except Exception as exc:
        await queries.update_restaurant(
            db,
            restaurant_id,
            {
                "integration_status": "sync_failed",
                "integration_state": "degraded",
                "last_roster_sync_status": "failed",
                "last_sync_error": str(exc),
            },
        )
        raise

    created = 0
    updated = 0
    skipped = 0

    for worker in workers:
        source_id = _stringify(worker.get("source_id"))
        phone = _clean_phone(worker.get("phone"))
        existing = None
        if source_id:
            existing = await queries.get_worker_by_source_id(db, source_id, restaurant_id=restaurant_id)
        if existing is None and phone:
            phone_match = await queries.get_worker_by_phone(db, phone)
            if phone_match and phone_match.get("restaurant_id") == restaurant_id:
                existing = phone_match

        payload = {
            "name": worker.get("name") or "Unknown Worker",
            "phone": phone,
            "email": worker.get("email"),
            "source": "scheduling_sync",
            "source_id": source_id,
            "roles": worker.get("roles") or [],
            "certifications": worker.get("certifications") or [],
            "restaurant_id": restaurant_id,
            "worker_type": worker.get("worker_type", "internal"),
            "preferred_channel": worker.get("preferred_channel", "sms"),
            "sms_consent_status": worker.get("sms_consent_status", "pending"),
            "voice_consent_status": worker.get("voice_consent_status", "pending"),
        }
        if existing and not payload["phone"]:
            payload.pop("phone")

        if existing:
            payload.pop("sms_consent_status", None)
            payload.pop("voice_consent_status", None)
            await queries.update_worker(db, existing["id"], payload)
            updated += 1
            continue

        if not phone:
            skipped += 1
            continue

        await queries.insert_worker(db, payload)
        created += 1

    await queries.update_restaurant(
        db,
        restaurant_id,
        {
            "integration_status": "connected",
            "integration_state": "healthy",
            "last_roster_sync_at": datetime.utcnow().isoformat(),
            "last_roster_sync_status": "ok",
            "last_sync_error": None,
        },
    )

    return {
        "status": "ok",
        "restaurant_id": restaurant_id,
        "platform": platform,
        "created": created,
        "updated": updated,
        "skipped": skipped,
    }


async def sync_schedule(
    db: aiosqlite.Connection,
    restaurant_id: int,
    start_date: date,
    end_date: date,
) -> dict:
    restaurant = await queries.get_restaurant(db, restaurant_id)
    if restaurant is None:
        raise ValueError(f"Restaurant {restaurant_id} not found")

    try:
        adapter = _adapter_for_restaurant(db, restaurant)
    except RuntimeError as exc:
        await queries.update_restaurant(
            db,
            restaurant_id,
            {
                "integration_status": "credentials_missing",
                "integration_state": "degraded",
                "last_schedule_sync_status": "failed",
                "last_sync_error": str(exc),
            },
        )
        raise
    source = restaurant.get("scheduling_platform") or "backfill_native"
    try:
        shifts = await adapter.sync_schedule(restaurant_id, (start_date, end_date))
    except Exception as exc:
        await queries.update_restaurant(
            db,
            restaurant_id,
            {
                "integration_status": "sync_failed",
                "integration_state": "degraded",
                "last_schedule_sync_status": "failed",
                "last_sync_error": str(exc),
            },
        )
        raise

    created = 0
    updated = 0
    skipped = 0

    for shift in shifts:
        platform_shift_id = _stringify(shift.get("scheduling_platform_id"))
        existing = None
        if platform_shift_id:
            existing = await queries.get_shift_by_platform_id(db, source, platform_shift_id)

        payload = {
            "restaurant_id": restaurant_id,
            "scheduling_platform_id": platform_shift_id,
            "role": shift.get("role") or "unknown",
            "date": shift.get("date"),
            "start_time": shift.get("start_time"),
            "end_time": shift.get("end_time"),
            "pay_rate": float(shift.get("pay_rate") or 0),
            "requirements": shift.get("requirements") or [],
            "status": shift.get("status", "scheduled"),
            "source_platform": source,
        }

        required_fields = [payload["date"], payload["start_time"], payload["end_time"]]
        if not all(required_fields):
            skipped += 1
            continue

        if existing:
            payload["status"] = existing.get("status", payload["status"])
            await queries.update_shift(db, existing["id"], payload)
            updated += 1
            continue

        await queries.insert_shift(db, payload)
        created += 1

    await queries.update_restaurant(
        db,
        restaurant_id,
        {
            "integration_status": "connected",
            "integration_state": "healthy",
            "last_schedule_sync_at": datetime.utcnow().isoformat(),
            "last_schedule_sync_status": "ok",
            "last_sync_error": None,
        },
    )

    return {
        "status": "ok",
        "restaurant_id": restaurant_id,
        "platform": source,
        "created": created,
        "updated": updated,
        "skipped": skipped,
    }


async def push_fill_update(db: aiosqlite.Connection, shift_id: int) -> dict:
    shift = await queries.get_shift(db, shift_id)
    if shift is None:
        raise ValueError(f"Shift {shift_id} not found")
    if not shift.get("filled_by"):
        return {"status": "skipped", "reason": "shift_not_filled"}

    restaurant = await queries.get_restaurant(db, shift["restaurant_id"])
    if restaurant is None:
        return {"status": "skipped", "reason": "restaurant_not_found"}

    platform = restaurant.get("scheduling_platform") or "backfill_native"
    if platform in {"backfill_native", "homebase"}:
        return {"status": "skipped", "reason": f"{platform}_does_not_require_write_back"}
    if not scheduler_supports_writeback(platform):
        return {"status": "skipped", "reason": f"{platform}_write_back_not_supported"}
    if not writeback_is_enabled(restaurant):
        return {"status": "skipped", "reason": "writeback_disabled_for_restaurant"}
    if not shift.get("scheduling_platform_id"):
        return {"status": "skipped", "reason": "missing_external_shift_id"}

    worker = await queries.get_worker(db, int(shift["filled_by"]))
    if worker is None:
        return {"status": "skipped", "reason": "worker_not_found"}
    if not worker.get("source_id"):
        return {"status": "skipped", "reason": "missing_external_worker_id"}

    adapter = _adapter_for_restaurant(db, restaurant)
    await adapter.push_fill(shift, worker)
    return {"status": "ok", "platform": platform, "shift_id": shift_id}
