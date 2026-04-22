from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from sqlalchemy import select

from app.models.common import (
    CoverageAttemptStatus,
    CoverageCaseStatus,
    OfferStatus,
    ShiftLifecycleStatus,
    ShiftStaffingStatus,
)
from app.models.coverage import CoverageCase, CoverageOffer
from app.models.scheduling import Shift
from app.schemas.coverage import CoverageExecutionDispatchRequest
from app.services import coverage, coverage_transitions, delivery, forecast_history, outreach as outreach_service, platform_events, worker_runtime

_EVENT_COVERAGE_CAMPAIGN_FILLED = "coverage.campaign.filled"
_EVENT_COVERAGE_CASE_FILLED = "coverage.case.filled"
_EVENT_COVERAGE_CAMPAIGN_CANCELLED = "coverage.campaign.cancelled"
_EVENT_COVERAGE_CASE_CANCELLED = "coverage.case.cancelled"
_EVENT_COVERAGE_CAMPAIGN_EXHAUSTED = "coverage.campaign.exhausted"
_EVENT_COVERAGE_CASE_EXHAUSTED = "coverage.case.exhausted"
_EVENT_COVERAGE_CAMPAIGN_FAILED = "coverage.campaign.failed"
_EVENT_COVERAGE_CASE_FAILED = "coverage.case.failed"
_EVENT_COVERAGE_OFFER_CANCELLED = "coverage.offer.cancelled"


def default_dispatch_channel() -> str:
    if (
        settings.retell_api_key
        and settings.retell_from_number
        and (settings.retell_agent_id or settings.retell_agent_id_outbound)
    ):
        return "voice"
    return "sms"


def _normalized_int(value: object | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _runtime_request_for_case(
    coverage_case: CoverageCase,
    *,
    channel: str | None = None,
    dispatch_limit: int | None = None,
    offer_ttl_minutes: int | None = None,
    run_metadata: dict[str, Any] | None = None,
) -> CoverageExecutionDispatchRequest:
    metadata = coverage_case.case_metadata if isinstance(coverage_case.case_metadata, dict) else {}
    stored_request = metadata.get("execution_request") if isinstance(metadata.get("execution_request"), dict) else {}
    merged_run_metadata = {
        **(stored_request.get("run_metadata") if isinstance(stored_request.get("run_metadata"), dict) else {}),
        **(run_metadata or {}),
    }
    if coverage_case.triggered_by and "triggered_by" not in merged_run_metadata:
        merged_run_metadata["triggered_by"] = coverage_case.triggered_by

    return CoverageExecutionDispatchRequest(
        phase_override=coverage_case.phase_target or None,
        channel=channel or str(stored_request.get("channel") or default_dispatch_channel()),
        dispatch_limit=dispatch_limit if dispatch_limit is not None else _normalized_int(stored_request.get("dispatch_limit")),
        offer_ttl_minutes=(
            offer_ttl_minutes
            if offer_ttl_minutes is not None
            else _normalized_int(stored_request.get("offer_ttl_minutes"))
        ),
        run_metadata=merged_run_metadata,
    )


def _runtime_error_metadata(
    coverage_case: CoverageCase,
    *,
    now: datetime,
    error_message: str,
) -> dict[str, Any]:
    metadata = coverage_case.case_metadata if isinstance(coverage_case.case_metadata, dict) else {}
    return {
        **metadata,
        "runtime_error": {
            "message": error_message,
            "failed_at": now.isoformat(),
        },
    }


async def _append_campaign_event(
    session: AsyncSession,
    *,
    coverage_case: CoverageCase,
    business_id: UUID | None,
    event_type: str,
    compatibility_event_name: str,
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    await platform_events.append(
        session,
        event_type=event_type,
        compatibility_event_name=compatibility_event_name,
        target_type="coverage_case",
        target_id=coverage_case.id,
        business_id=business_id,
        location_id=coverage_case.location_id,
        payload=payload or {},
        metadata={"channel": "worker_runtime", **(metadata or {})},
    )


async def _sync_callout_history_fact(
    session: AsyncSession,
    *,
    coverage_case: CoverageCase,
    shift: Shift,
) -> None:
    await forecast_history.sync_callout_history_fact_for_case(
        session,
        coverage_case=coverage_case,
        shift=shift,
    )


async def _append_offer_cancelled_event(
    session: AsyncSession,
    *,
    coverage_case: CoverageCase,
    offer: CoverageOffer,
    business_id: UUID | None,
    reason: str,
    occurred_at: datetime,
) -> None:
    await outreach_service.append_outreach_attempt_event(
        session,
        event_type=platform_events.PlatformEventType.COVERAGE_OUTREACH_ATTEMPT_CANCELLED,
        compatibility_event_name=_EVENT_COVERAGE_OFFER_CANCELLED,
        offer=offer,
        business_id=business_id,
        location_id=coverage_case.location_id,
        shift_id=coverage_case.shift_id,
        metadata={
            "channel": "worker_runtime",
            "reason": reason,
            "occurred_at": occurred_at.isoformat(),
        },
    )


async def _append_dispatch_events(
    session: AsyncSession,
    *,
    business_id: UUID,
    result: Any,
) -> None:
    coverage_case = getattr(result, "coverage_case", None)
    if coverage_case is None:
        return
    phase_executed = str(getattr(result, "phase_executed", "") or "").strip().lower()
    if not phase_executed:
        return

    await platform_events.append(
        session,
        event_type=platform_events.PlatformEventType.COVERAGE_DISPATCH_EXECUTED,
        target_type="coverage_case",
        target_id=coverage_case.id,
        business_id=business_id,
        location_id=coverage_case.location_id,
        payload={
            "phase_executed": phase_executed,
            "candidate_count": int(getattr(result, "candidate_count", 0) or 0),
            "offer_count": len(getattr(result, "offers", []) or []),
        },
        metadata={"channel": "worker_runtime"},
    )

    run = getattr(result, "run", None)
    if run is None:
        return
    if phase_executed == "phase_1":
        event_type = platform_events.PlatformEventType.COVERAGE_PHASE_1_EXECUTED
    elif phase_executed == "phase_2":
        event_type = platform_events.PlatformEventType.COVERAGE_PHASE_2_EXECUTED
    else:
        return

    await platform_events.append(
        session,
        event_type=event_type,
        target_type="coverage_case_run",
        target_id=run.id,
        business_id=business_id,
        location_id=coverage_case.location_id,
        payload={
            "coverage_case_id": str(coverage_case.id),
            "candidate_count": int(getattr(result, "candidate_count", 0) or 0),
            "offer_count": len(getattr(result, "offers", []) or []),
        },
        metadata={"channel": "worker_runtime"},
    )


async def execute_queued_case(
    session: AsyncSession,
    *,
    business_id: UUID,
    coverage_case_id: UUID,
    channel: str | None = None,
    dispatch_limit: int | None = None,
    offer_ttl_minutes: int | None = None,
    run_metadata: dict[str, Any] | None = None,
):
    coverage_case = await session.get(CoverageCase, coverage_case_id)
    if coverage_case is None:
        raise LookupError("coverage_case_not_found")
    request = _runtime_request_for_case(
        coverage_case,
        channel=channel,
        dispatch_limit=dispatch_limit,
        offer_ttl_minutes=offer_ttl_minutes,
        run_metadata=run_metadata,
    )
    return await coverage.execute_next_coverage_phase(
        session,
        business_id,
        coverage_case_id,
        request,
    )


async def process_queued_coverage_cases(
    session: AsyncSession,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    rows = await worker_runtime.claim_queued_coverage_cases(session, limit=limit)
    processed_case_ids: list[str] = []
    executed_count = 0
    exhausted_count = 0
    skipped_count = 0
    failed_count = 0

    for coverage_case, business_id in rows:
        processed_case_ids.append(str(coverage_case.id))
        reference_time = datetime.now(timezone.utc)
        try:
            shift = await session.get(Shift, coverage_case.shift_id)
            if shift is None:
                raise LookupError("shift_not_found")

            if shift.lifecycle_status in {ShiftLifecycleStatus.cancelled, ShiftLifecycleStatus.completed}:
                coverage_case.status = CoverageCaseStatus.cancelled
                coverage_case.closed_at = reference_time
                coverage_case.case_metadata = {
                    **(coverage_case.case_metadata or {}),
                    "runtime_skip_reason": "shift_not_actionable",
                    "runtime_skipped_at": reference_time.isoformat(),
                }
                await _append_campaign_event(
                    session,
                    coverage_case=coverage_case,
                    business_id=shift.business_id,
                    event_type=_EVENT_COVERAGE_CAMPAIGN_CANCELLED,
                    compatibility_event_name=_EVENT_COVERAGE_CASE_CANCELLED,
                    payload={
                        "shift_id": str(coverage_case.shift_id),
                        "reason": "shift_not_actionable",
                    },
                )
                await session.commit()
                skipped_count += 1
                continue

            if int(shift.seats_filled or 0) >= int(shift.seats_requested or 1):
                coverage_case.status = CoverageCaseStatus.filled
                coverage_case.closed_at = reference_time
                coverage_case.case_metadata = {
                    **(coverage_case.case_metadata or {}),
                    "runtime_skip_reason": "shift_already_filled",
                    "runtime_skipped_at": reference_time.isoformat(),
                }
                await _append_campaign_event(
                    session,
                    coverage_case=coverage_case,
                    business_id=shift.business_id,
                    event_type=_EVENT_COVERAGE_CAMPAIGN_FILLED,
                    compatibility_event_name=_EVENT_COVERAGE_CASE_FILLED,
                    payload={
                        "shift_id": str(coverage_case.shift_id),
                        "reason": "shift_already_filled",
                    },
                )
                await session.commit()
                skipped_count += 1
                continue

            if business_id is None:
                raise LookupError("business_not_found")

            result = await execute_queued_case(
                session,
                business_id=business_id,
                coverage_case_id=coverage_case.id,
            )
            await _append_dispatch_events(
                session,
                business_id=business_id,
                result=result,
            )
            if result.phase_executed is None or result.coverage_case.status == CoverageCaseStatus.exhausted:
                await _append_campaign_event(
                    session,
                    coverage_case=result.coverage_case,
                    business_id=business_id,
                    event_type=_EVENT_COVERAGE_CAMPAIGN_EXHAUSTED,
                    compatibility_event_name=_EVENT_COVERAGE_CASE_EXHAUSTED,
                    payload={
                        "shift_id": str(result.coverage_case.shift_id),
                        "reason": "no_candidates_available",
                    },
                )
            await session.commit()
            if result.phase_executed is None or result.coverage_case.status == CoverageCaseStatus.exhausted:
                exhausted_count += 1
            else:
                executed_count += 1
        except Exception as exc:
            if hasattr(session, "rollback"):
                await session.rollback()
            refreshed_case = await session.get(CoverageCase, coverage_case.id) or coverage_case
            refreshed_case.status = CoverageCaseStatus.failed
            refreshed_case.closed_at = refreshed_case.closed_at or reference_time
            refreshed_case.case_metadata = _runtime_error_metadata(
                refreshed_case,
                now=reference_time,
                error_message=str(exc),
            )
            await _append_campaign_event(
                session,
                coverage_case=refreshed_case,
                business_id=business_id,
                event_type=_EVENT_COVERAGE_CAMPAIGN_FAILED,
                compatibility_event_name=_EVENT_COVERAGE_CASE_FAILED,
                payload={
                    "shift_id": str(refreshed_case.shift_id),
                    "error_message": str(exc),
                },
            )
            await session.commit()
            failed_count += 1

    return {
        "claimed_count": len(rows),
        "executed_count": executed_count,
        "exhausted_count": exhausted_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "processed_case_ids": processed_case_ids,
    }


async def _active_case_offers(
    session: AsyncSession,
    *,
    coverage_case_id: UUID,
) -> list[CoverageOffer]:
    result = await session.execute(
        select(CoverageOffer).where(
            CoverageOffer.coverage_case_id == coverage_case_id,
            CoverageOffer.status.in_([OfferStatus.pending, OfferStatus.delivered]),
        )
    )
    return list(result.scalars().all())


async def _cancel_active_offers(
    session: AsyncSession,
    *,
    coverage_case: CoverageCase,
    business_id: UUID | None,
    now: datetime,
    reason: str,
) -> list[str]:
    offers = await _active_case_offers(session, coverage_case_id=coverage_case.id)
    cancelled_offer_ids: list[str] = []
    for offer in offers:
        coverage_transitions.mark_offer_cancelled(
            offer,
            occurred_at=now,
            reason=reason,
            metadata={
                "runtime_cancel_reason": reason,
                "runtime_cancelled_at": now.isoformat(),
            },
        )
        await delivery.mark_offer_attempt_outcome(
            session,
            offer,
            status=CoverageAttemptStatus.cancelled,
            occurred_at=now,
            response_payload={"runtime_cancel_reason": reason},
        )
        await _append_offer_cancelled_event(
            session,
            coverage_case=coverage_case,
            offer=offer,
            business_id=business_id,
            reason=reason,
            occurred_at=now,
        )
        cancelled_offer_ids.append(str(offer.id))
    return cancelled_offer_ids


async def reconcile_running_coverage_cases(
    session: AsyncSession,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    rows = await worker_runtime.claim_running_coverage_cases(session, limit=limit)
    processed_case_ids: list[str] = []
    filled_count = 0
    cancelled_count = 0
    exhausted_count = 0
    unchanged_count = 0
    failed_count = 0

    for coverage_case, business_id in rows:
        processed_case_ids.append(str(coverage_case.id))
        reference_time = datetime.now(timezone.utc)
        try:
            shift = await session.get(Shift, coverage_case.shift_id)
            if shift is None:
                raise LookupError("shift_not_found")

            if (
                int(shift.seats_filled or 0) >= int(shift.seats_requested or 1)
                or shift.staffing_status == ShiftStaffingStatus.covered
            ):
                cancelled_offer_ids = await _cancel_active_offers(
                    session,
                    coverage_case=coverage_case,
                    business_id=business_id,
                    now=reference_time,
                    reason="shift_already_filled",
                )
                coverage_transitions.mark_case_filled(coverage_case, occurred_at=reference_time)
                await _sync_callout_history_fact(session, coverage_case=coverage_case, shift=shift)
                coverage_case.case_metadata = {
                    **(coverage_case.case_metadata or {}),
                    "runtime_reconcile_reason": "shift_already_filled",
                    "runtime_reconciled_at": reference_time.isoformat(),
                    "runtime_cancelled_offer_ids": cancelled_offer_ids,
                }
                await _append_campaign_event(
                    session,
                    coverage_case=coverage_case,
                    business_id=business_id,
                    event_type=_EVENT_COVERAGE_CAMPAIGN_FILLED,
                    compatibility_event_name=_EVENT_COVERAGE_CASE_FILLED,
                    payload={
                        "shift_id": str(coverage_case.shift_id),
                        "reason": "shift_already_filled",
                        "cancelled_offer_ids": cancelled_offer_ids,
                    },
                )
                await session.commit()
                filled_count += 1
                continue

            if (
                shift.lifecycle_status in {ShiftLifecycleStatus.cancelled, ShiftLifecycleStatus.completed}
                or shift.staffing_status == ShiftStaffingStatus.no_fill
            ):
                cancelled_offer_ids = await _cancel_active_offers(
                    session,
                    coverage_case=coverage_case,
                    business_id=business_id,
                    now=reference_time,
                    reason="shift_not_actionable",
                )
                coverage_transitions.mark_case_cancelled(coverage_case, occurred_at=reference_time)
                await _sync_callout_history_fact(session, coverage_case=coverage_case, shift=shift)
                coverage_case.case_metadata = {
                    **(coverage_case.case_metadata or {}),
                    "runtime_reconcile_reason": "shift_not_actionable",
                    "runtime_reconciled_at": reference_time.isoformat(),
                    "runtime_cancelled_offer_ids": cancelled_offer_ids,
                }
                await _append_campaign_event(
                    session,
                    coverage_case=coverage_case,
                    business_id=business_id,
                    event_type=_EVENT_COVERAGE_CAMPAIGN_CANCELLED,
                    compatibility_event_name=_EVENT_COVERAGE_CASE_CANCELLED,
                    payload={
                        "shift_id": str(coverage_case.shift_id),
                        "reason": "shift_not_actionable",
                        "cancelled_offer_ids": cancelled_offer_ids,
                    },
                )
                await session.commit()
                cancelled_count += 1
                continue

            active_offers = await _active_case_offers(session, coverage_case_id=coverage_case.id)
            if not active_offers:
                coverage_transitions.mark_case_exhausted(coverage_case, occurred_at=reference_time)
                await _sync_callout_history_fact(session, coverage_case=coverage_case, shift=shift)
                coverage_case.case_metadata = {
                    **(coverage_case.case_metadata or {}),
                    "runtime_reconcile_reason": "no_active_offers",
                    "runtime_reconciled_at": reference_time.isoformat(),
                }
                await _append_campaign_event(
                    session,
                    coverage_case=coverage_case,
                    business_id=business_id,
                    event_type=_EVENT_COVERAGE_CAMPAIGN_EXHAUSTED,
                    compatibility_event_name=_EVENT_COVERAGE_CASE_EXHAUSTED,
                    payload={
                        "shift_id": str(coverage_case.shift_id),
                        "reason": "no_active_offers",
                    },
                )
                await session.commit()
                exhausted_count += 1
                continue

            unchanged_count += 1
        except Exception as exc:
            if hasattr(session, "rollback"):
                await session.rollback()
            refreshed_case = await session.get(CoverageCase, coverage_case.id) or coverage_case
            coverage_transitions.mark_case_failed(refreshed_case, occurred_at=reference_time)
            refreshed_shift = await session.get(Shift, refreshed_case.shift_id)
            if refreshed_shift is not None:
                await _sync_callout_history_fact(session, coverage_case=refreshed_case, shift=refreshed_shift)
            refreshed_case.case_metadata = _runtime_error_metadata(
                refreshed_case,
                now=reference_time,
                error_message=str(exc),
            )
            await _append_campaign_event(
                session,
                coverage_case=refreshed_case,
                business_id=business_id,
                event_type=_EVENT_COVERAGE_CAMPAIGN_FAILED,
                compatibility_event_name=_EVENT_COVERAGE_CASE_FAILED,
                payload={
                    "shift_id": str(refreshed_case.shift_id),
                    "error_message": str(exc),
                },
            )
            await session.commit()
            failed_count += 1

    return {
        "claimed_count": len(rows),
        "filled_count": filled_count,
        "cancelled_count": cancelled_count,
        "exhausted_count": exhausted_count,
        "unchanged_count": unchanged_count,
        "failed_count": failed_count,
        "processed_case_ids": processed_case_ids,
    }


async def process_coverage_runtime_batch(
    session: AsyncSession,
    *,
    limit: int = 20,
    allow_queued_dispatch: bool = True,
    queue_block_reason: str | None = None,
) -> dict[str, Any]:
    reconcile_result = await reconcile_running_coverage_cases(session, limit=limit)
    expiry_result = await delivery.expire_due_offers(session, limit=limit)
    queued_result = (
        await process_queued_coverage_cases(session, limit=limit)
        if allow_queued_dispatch
        else {
            "status": "blocked",
            "reason": queue_block_reason or "queued_dispatch_blocked",
            "claimed_count": 0,
            "executed_count": 0,
            "exhausted_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "processed_case_ids": [],
        }
    )
    delivery_result = await delivery.process_outbox_batch(session, limit=limit)

    processed_case_ids: list[str] = []
    seen_case_ids: set[str] = set()
    for case_id in [
        *reconcile_result.get("processed_case_ids", []),
        *queued_result.get("processed_case_ids", []),
        *expiry_result.get("exhausted_case_ids", []),
    ]:
        if case_id in seen_case_ids:
            continue
        seen_case_ids.add(case_id)
        processed_case_ids.append(case_id)

    return {
        "reconcile": reconcile_result,
        "offer_expiry": expiry_result,
        "queued_cases": queued_result,
        "delivery": delivery_result,
        "processed_case_ids": processed_case_ids,
    }
