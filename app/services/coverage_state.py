from __future__ import annotations

from app.models.common import CoverageCaseStatus, OfferStatus, OutboxStatus

TERMINAL_COVERAGE_CASE_STATUSES = frozenset(
    {
        CoverageCaseStatus.filled,
        CoverageCaseStatus.exhausted,
        CoverageCaseStatus.cancelled,
        CoverageCaseStatus.failed,
    }
)
ACTIONABLE_COVERAGE_CASE_STATUSES = frozenset(
    {
        CoverageCaseStatus.queued,
        CoverageCaseStatus.running,
    }
)

TERMINAL_OFFER_STATUSES = frozenset(
    {
        OfferStatus.accepted,
        OfferStatus.declined,
        OfferStatus.expired,
        OfferStatus.cancelled,
        OfferStatus.failed,
    }
)
ACTIONABLE_OFFER_STATUSES = frozenset(
    {
        OfferStatus.pending,
        OfferStatus.delivered,
    }
)

REQUEUEABLE_OUTBOX_STATUSES = frozenset(
    {
        OutboxStatus.pending,
        OutboxStatus.failed,
        OutboxStatus.cancelled,
    }
)

REPROCESSABLE_CALLBACK_STATUSES = frozenset({"received", "failed"})
FORCE_REQUEUEABLE_CALLBACK_STATUSES = frozenset({"received", "failed", "processed", "dead_lettered"})


def is_terminal_coverage_case_status(status: CoverageCaseStatus | str | None) -> bool:
    if status is None:
        return False
    try:
        normalized = status if isinstance(status, CoverageCaseStatus) else CoverageCaseStatus(str(status))
    except ValueError:
        return False
    return normalized in TERMINAL_COVERAGE_CASE_STATUSES


def is_actionable_coverage_case_status(status: CoverageCaseStatus | str | None) -> bool:
    if status is None:
        return False
    try:
        normalized = status if isinstance(status, CoverageCaseStatus) else CoverageCaseStatus(str(status))
    except ValueError:
        return False
    return normalized in ACTIONABLE_COVERAGE_CASE_STATUSES


def is_terminal_offer_status(status: OfferStatus | str | None) -> bool:
    if status is None:
        return False
    try:
        normalized = status if isinstance(status, OfferStatus) else OfferStatus(str(status))
    except ValueError:
        return False
    return normalized in TERMINAL_OFFER_STATUSES


def is_actionable_offer_status(status: OfferStatus | str | None) -> bool:
    if status is None:
        return False
    try:
        normalized = status if isinstance(status, OfferStatus) else OfferStatus(str(status))
    except ValueError:
        return False
    return normalized in ACTIONABLE_OFFER_STATUSES


def is_requeueable_outbox_status(status: OutboxStatus | str | None) -> bool:
    if status is None:
        return False
    try:
        normalized = status if isinstance(status, OutboxStatus) else OutboxStatus(str(status))
    except ValueError:
        return False
    return normalized in REQUEUEABLE_OUTBOX_STATUSES


def is_callback_reprocessable_status(status: str | None) -> bool:
    return str(status or "").strip().lower() in REPROCESSABLE_CALLBACK_STATUSES


def is_callback_force_requeueable_status(status: str | None) -> bool:
    return str(status or "").strip().lower() in FORCE_REQUEUEABLE_CALLBACK_STATUSES
