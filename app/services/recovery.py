from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.common import OfferStatus, OutboxStatus
from app.models.coverage import CoverageCase, CoverageOffer, OutboxEvent
from app.models.integrations import ProviderCallbackLog
from app.services import coverage_state, delivery, provider_callbacks

ReplayMode = Literal["dry_run", "reprocess_if_preconditions_match", "force_requeue"]

_COVERAGE_OUTBOX_TOPIC = "coverage.offer.created"


async def _load_callback_entry_for_update(
    session: AsyncSession,
    callback_log_id: UUID,
) -> ProviderCallbackLog | None:
    result = await session.execute(
        select(ProviderCallbackLog)
        .where(ProviderCallbackLog.id == callback_log_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def _load_outbox_event_for_update(
    session: AsyncSession,
    outbox_event_id: UUID,
) -> OutboxEvent | None:
    result = await session.execute(
        select(OutboxEvent)
        .where(OutboxEvent.id == outbox_event_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


def _callback_replay_guard(
    entry: ProviderCallbackLog,
    *,
    mode: ReplayMode,
) -> tuple[bool, list[str], list[str]]:
    status = str(entry.status or "").strip().lower()
    reasons: list[str] = []
    warnings: list[str] = []

    if mode == "dry_run":
        if status == "processing":
            reasons.append("callback_processing_in_progress")
        elif status == "processed":
            reasons.append("callback_already_processed")
            warnings.append("callback_replay_can_repeat_side_effects")
        elif status == "dead_lettered":
            reasons.append("callback_dead_lettered")
        elif not coverage_state.is_callback_reprocessable_status(status):
            reasons.append("callback_status_not_reprocessable")
        return not reasons, reasons, warnings

    if mode == "reprocess_if_preconditions_match":
        if status == "processing":
            reasons.append("callback_processing_in_progress")
        elif not coverage_state.is_callback_reprocessable_status(status):
            if status == "processed":
                reasons.append("callback_already_processed")
            elif status == "dead_lettered":
                reasons.append("callback_dead_lettered")
            else:
                reasons.append("callback_status_not_reprocessable")
        return not reasons, reasons, warnings

    if status == "processing":
        reasons.append("callback_processing_in_progress")
    elif not coverage_state.is_callback_force_requeueable_status(status):
        reasons.append("callback_status_not_force_requeueable")
    elif status == "processed":
        warnings.append("callback_force_requeue_can_repeat_side_effects")
    return not reasons, reasons, warnings


async def replay_provider_callback_log(
    session: AsyncSession,
    *,
    callback_log_id: UUID,
    mode: ReplayMode,
) -> dict[str, Any]:
    entry = await _load_callback_entry_for_update(session, callback_log_id)
    if entry is None:
        return {
            "callback_log_id": callback_log_id,
            "mode": mode,
            "action": "not_found",
            "allowed": False,
            "reason_codes": ["provider_callback_log_not_found"],
            "warnings": [],
        }

    status_before = str(entry.status)
    allowed, reason_codes, warnings = _callback_replay_guard(entry, mode=mode)
    base_payload = {
        "callback_log_id": entry.id,
        "provider": entry.provider,
        "route_key": entry.route_key,
        "status_before": status_before,
        "mode": mode,
        "allowed": allowed,
        "reason_codes": reason_codes,
        "warnings": warnings,
    }

    if mode == "dry_run" or not allowed:
        return {
            **base_payload,
            "action": "preview" if mode == "dry_run" else "skipped",
            "status_after": status_before,
            "response_kind": None,
            "response_payload": {},
        }

    if mode == "reprocess_if_preconditions_match":
        try:
            result = await provider_callbacks.process_callback_entry_synchronously(session, entry)
        except provider_callbacks.CallbackProcessingError as exc:
            refreshed = await provider_callbacks.get_callback_log(session, callback_log_id=entry.id)
            return {
                **base_payload,
                "action": "failed",
                "status_after": str((refreshed or entry).status),
                "error_message": exc.error_message,
                "response_kind": None,
                "response_payload": exc.result_payload,
            }
        refreshed = await provider_callbacks.get_callback_log(session, callback_log_id=entry.id)
        return {
            **base_payload,
            "action": "reprocessed",
            "status_after": str((refreshed or entry).status),
            "error_message": None,
            "response_kind": result.response_kind,
            "response_payload": result.response_payload,
        }

    entry.status = "received"
    entry.processed_at = None
    entry.error_message = None
    entry.result_payload = {
        **(entry.result_payload or {}),
        "force_requeue_requested_at": datetime.now(timezone.utc).isoformat(),
        "force_requeue_previous_status": status_before,
    }
    await session.commit()
    return {
        **base_payload,
        "action": "requeued",
        "status_after": "received",
        "error_message": None,
        "response_kind": None,
        "response_payload": {},
    }


def _coverage_outbox_replay_guard(
    event: OutboxEvent,
    *,
    coverage_offer: CoverageOffer | None,
    coverage_case: CoverageCase | None,
    mode: ReplayMode,
) -> tuple[bool, list[str], list[str]]:
    reasons: list[str] = []
    warnings: list[str] = []
    try:
        status = event.status if isinstance(event.status, OutboxStatus) else OutboxStatus(str(event.status))
    except ValueError:
        reasons.append("outbox_status_unknown")
        return False, reasons, warnings

    if event.topic != _COVERAGE_OUTBOX_TOPIC:
        reasons.append("outbox_topic_not_replay_supported")
        return False, reasons, warnings

    if status == OutboxStatus.processing:
        reasons.append("outbox_processing_in_progress")
        return False, reasons, warnings

    if coverage_offer is None:
        reasons.append("coverage_offer_not_found")
    elif coverage_state.is_terminal_offer_status(coverage_offer.status):
        reasons.append("coverage_offer_no_longer_actionable")
    elif coverage_offer.status != OfferStatus.pending:
        reasons.append("coverage_offer_not_pending")

    if coverage_case is None:
        reasons.append("coverage_case_not_found")
    elif not coverage_state.is_actionable_coverage_case_status(coverage_case.status):
        reasons.append("coverage_case_not_actionable")

    if mode == "dry_run":
        if status == OutboxStatus.sent:
            reasons.append("outbox_already_sent")
            warnings.append("outbox_replay_can_duplicate_provider_delivery")
        elif not coverage_state.is_requeueable_outbox_status(status):
            reasons.append("outbox_status_not_requeueable")
        return not reasons, reasons, warnings

    if mode == "reprocess_if_preconditions_match":
        if status == OutboxStatus.sent:
            reasons.append("outbox_already_sent")
        elif not coverage_state.is_requeueable_outbox_status(status):
            reasons.append("outbox_status_not_requeueable")
        return not reasons, reasons, warnings

    if status == OutboxStatus.sent:
        reasons.append("outbox_already_sent")
    elif not coverage_state.is_requeueable_outbox_status(status):
        reasons.append("outbox_status_not_force_requeueable")
    return not reasons, reasons, warnings


async def replay_coverage_outbox_event(
    session: AsyncSession,
    *,
    outbox_event_id: UUID,
    mode: ReplayMode,
) -> dict[str, Any]:
    event = await _load_outbox_event_for_update(session, outbox_event_id)
    if event is None:
        return {
            "outbox_event_id": outbox_event_id,
            "mode": mode,
            "action": "not_found",
            "allowed": False,
            "reason_codes": ["outbox_event_not_found"],
            "warnings": [],
        }

    coverage_offer = (
        await session.get(CoverageOffer, event.aggregate_id)
        if event.aggregate_type == "coverage_offer"
        else None
    )
    coverage_case = (
        await session.get(CoverageCase, coverage_offer.coverage_case_id)
        if coverage_offer is not None
        else None
    )

    status_before = str(event.status)
    allowed, reason_codes, warnings = _coverage_outbox_replay_guard(
        event,
        coverage_offer=coverage_offer,
        coverage_case=coverage_case,
        mode=mode,
    )
    base_payload = {
        "outbox_event_id": event.id,
        "mode": mode,
        "topic": event.topic,
        "status_before": status_before,
        "offer_id": coverage_offer.id if coverage_offer is not None else None,
        "coverage_case_id": coverage_case.id if coverage_case is not None else None,
        "allowed": allowed,
        "reason_codes": reason_codes,
        "warnings": warnings,
    }

    if mode == "dry_run" or not allowed:
        return {
            **base_payload,
            "action": "preview" if mode == "dry_run" else "skipped",
            "status_after": status_before,
            "processed": False,
            "sent": False,
            "failed": False,
            "result_payload": {},
        }

    if mode == "reprocess_if_preconditions_match":
        reference_time = datetime.now(timezone.utc)
        event.status = OutboxStatus.processing
        event.locked_at = reference_time
        event.attempt_count = int(event.attempt_count or 0) + 1
        result = await delivery.process_outbox_event(
            session,
            outbox_event=event,
            now=reference_time,
        )
        await session.commit()
        return {
            **base_payload,
            "action": "reprocessed",
            "status_after": event.status.value if isinstance(event.status, OutboxStatus) else str(event.status),
            **result,
        }

    event.status = OutboxStatus.pending
    event.available_at = datetime.now(timezone.utc)
    event.locked_at = None
    event.processed_at = None
    event.error_message = None
    event.result_payload = {
        **(event.result_payload or {}),
        "force_requeue_requested_at": datetime.now(timezone.utc).isoformat(),
        "force_requeue_previous_status": status_before,
    }
    await session.commit()
    return {
        **base_payload,
        "action": "requeued",
        "status_after": OutboxStatus.pending.value,
        "processed": False,
        "sent": False,
        "failed": False,
        "result_payload": {},
    }
