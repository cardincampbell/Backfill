from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import coverage_runtime, provider_callbacks, runtime_projections


def _normalized_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _coverage_failed_count(coverage_result: dict[str, Any]) -> int:
    reconcile = coverage_result.get("reconcile") if isinstance(coverage_result.get("reconcile"), dict) else {}
    queued_cases = coverage_result.get("queued_cases") if isinstance(coverage_result.get("queued_cases"), dict) else {}
    delivery = coverage_result.get("delivery") if isinstance(coverage_result.get("delivery"), dict) else {}
    return (
        _normalized_int(reconcile.get("failed_count"))
        + _normalized_int(queued_cases.get("failed_count"))
        + _normalized_int(delivery.get("failed_count"))
    )


def _offer_expiry_result(coverage_result: dict[str, Any]) -> dict[str, Any]:
    return coverage_result.get("offer_expiry") if isinstance(coverage_result.get("offer_expiry"), dict) else {}


async def process_runtime_tick(
    session: AsyncSession,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    callback_result = await provider_callbacks.process_callback_batch(session, limit=limit)
    projection_health = await runtime_projections.monitor_runtime_projection_freshness(
        session,
        business_limit=limit,
    )
    coverage_blocked = projection_health.get("status") == "blocked"
    coverage_result = await coverage_runtime.process_coverage_runtime_batch(
        session,
        limit=limit,
        allow_queued_dispatch=not coverage_blocked,
        queue_block_reason=projection_health.get("blocked_reason") if coverage_blocked else None,
    )
    if coverage_blocked:
        coverage_result = {
            "status": "blocked",
            "reason": projection_health.get("blocked_reason") or "runtime_projections_too_stale",
            **coverage_result,
        }

    processed_case_ids = coverage_result.get("processed_case_ids", []) if isinstance(coverage_result, dict) else []
    delivery = coverage_result.get("delivery") if isinstance(coverage_result.get("delivery"), dict) else {}
    reconcile = coverage_result.get("reconcile") if isinstance(coverage_result.get("reconcile"), dict) else {}
    queued_cases = coverage_result.get("queued_cases") if isinstance(coverage_result.get("queued_cases"), dict) else {}
    offer_expiry = _offer_expiry_result(coverage_result)

    summary = {
        "callback_claimed_count": _normalized_int(callback_result.get("claimed_count")),
        "callback_processed_count": _normalized_int(callback_result.get("processed_count")),
        "callback_failed_count": _normalized_int(callback_result.get("failed_count")),
        "callback_dead_lettered_count": _normalized_int(callback_result.get("dead_lettered_count")),
        "coverage_claimed_case_count": (
            _normalized_int(reconcile.get("claimed_count")) + _normalized_int(queued_cases.get("claimed_count"))
        ),
        "coverage_processed_case_count": len(processed_case_ids),
        "offer_expiry_expired_count": _normalized_int(offer_expiry.get("expired_count")),
        "offer_expiry_advanced_offer_count": len(offer_expiry.get("advanced_offer_ids", []) or []),
        "offer_expiry_exhausted_case_count": len(offer_expiry.get("exhausted_case_ids", []) or []),
        "delivery_claimed_count": _normalized_int(delivery.get("claimed_count")),
        "projection_monitored_business_count": _normalized_int(projection_health.get("monitored_business_count")),
        "projection_blocked_business_count": _normalized_int(projection_health.get("blocked_business_count")),
        "projection_stale_employee_count": _normalized_int(projection_health.get("stale_employee_count")),
        "projection_missing_employee_count": _normalized_int(projection_health.get("missing_employee_count")),
        "total_failed_count": _normalized_int(callback_result.get("failed_count"))
        + _coverage_failed_count(coverage_result),
    }

    did_work = any(
        value > 0
        for value in (
            summary["callback_claimed_count"],
            summary["coverage_claimed_case_count"],
            summary["offer_expiry_expired_count"],
            summary["offer_expiry_advanced_offer_count"],
            summary["offer_expiry_exhausted_case_count"],
            summary["delivery_claimed_count"],
        )
    )

    return {
        "status": "blocked" if coverage_blocked else ("processed" if did_work else "idle"),
        "summary": summary,
        "callbacks": callback_result,
        "runtime_projections": projection_health,
        "coverage_runtime": coverage_result,
    }
