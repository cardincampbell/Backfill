from __future__ import annotations

from datetime import datetime

from app.models.common import CoverageCaseStatus, OfferStatus
from app.models.coverage import CoverageCase, CoverageOffer
from app.services import coverage_state


class CoverageTransitionError(ValueError):
    pass


def ensure_offer_actionable(offer: CoverageOffer) -> None:
    if not coverage_state.is_actionable_offer_status(offer.status):
        raise CoverageTransitionError("offer_not_actionable")


def ensure_case_actionable(coverage_case: CoverageCase) -> None:
    if not coverage_state.is_actionable_coverage_case_status(coverage_case.status):
        raise CoverageTransitionError("coverage_case_not_actionable")


def mark_case_running(coverage_case: CoverageCase) -> None:
    if coverage_case.status in {CoverageCaseStatus.cancelled, CoverageCaseStatus.failed}:
        raise CoverageTransitionError("coverage_case_not_reopenable")
    coverage_case.status = CoverageCaseStatus.running
    coverage_case.closed_at = None


def mark_case_filled(coverage_case: CoverageCase, *, occurred_at: datetime) -> None:
    if coverage_case.status == CoverageCaseStatus.filled:
        coverage_case.closed_at = coverage_case.closed_at or occurred_at
        return
    coverage_case.status = CoverageCaseStatus.filled
    coverage_case.closed_at = coverage_case.closed_at or occurred_at


def mark_case_exhausted(coverage_case: CoverageCase, *, occurred_at: datetime) -> None:
    if coverage_case.status == CoverageCaseStatus.exhausted:
        coverage_case.closed_at = coverage_case.closed_at or occurred_at
        return
    coverage_case.status = CoverageCaseStatus.exhausted
    coverage_case.closed_at = occurred_at


def mark_case_cancelled(coverage_case: CoverageCase, *, occurred_at: datetime) -> None:
    if coverage_case.status == CoverageCaseStatus.cancelled:
        coverage_case.closed_at = coverage_case.closed_at or occurred_at
        return
    coverage_case.status = CoverageCaseStatus.cancelled
    coverage_case.closed_at = occurred_at


def mark_case_failed(coverage_case: CoverageCase, *, occurred_at: datetime) -> None:
    if coverage_case.status == CoverageCaseStatus.failed:
        coverage_case.closed_at = coverage_case.closed_at or occurred_at
        return
    coverage_case.status = CoverageCaseStatus.failed
    coverage_case.closed_at = occurred_at


def mark_offer_accepted(offer: CoverageOffer, *, occurred_at: datetime) -> None:
    if offer.status == OfferStatus.accepted:
        offer.accepted_at = offer.accepted_at or occurred_at
        return
    ensure_offer_actionable(offer)
    offer.status = OfferStatus.accepted
    offer.accepted_at = occurred_at


def mark_offer_declined(offer: CoverageOffer, *, occurred_at: datetime) -> None:
    if offer.status == OfferStatus.declined:
        offer.declined_at = offer.declined_at or occurred_at
        return
    ensure_offer_actionable(offer)
    offer.status = OfferStatus.declined
    offer.declined_at = occurred_at


def mark_offer_expired(offer: CoverageOffer, *, occurred_at: datetime) -> None:
    if offer.status == OfferStatus.expired:
        offer.offer_metadata = {**(offer.offer_metadata or {}), "expired_at": occurred_at.isoformat()}
        return
    ensure_offer_actionable(offer)
    offer.status = OfferStatus.expired
    offer.offer_metadata = {**(offer.offer_metadata or {}), "expired_at": occurred_at.isoformat()}


def mark_offer_cancelled(
    offer: CoverageOffer,
    *,
    occurred_at: datetime,
    reason: str | None = None,
    metadata: dict | None = None,
) -> None:
    if offer.status == OfferStatus.cancelled:
        merged_metadata = {
            **(offer.offer_metadata or {}),
            **(metadata or {}),
            "cancelled_at": occurred_at.isoformat(),
        }
        if reason:
            merged_metadata["cancel_reason"] = reason
        offer.offer_metadata = merged_metadata
        return
    if not coverage_state.is_actionable_offer_status(offer.status):
        raise CoverageTransitionError("offer_not_actionable")
    offer.status = OfferStatus.cancelled
    merged_metadata = {
        **(offer.offer_metadata or {}),
        **(metadata or {}),
        "cancelled_at": occurred_at.isoformat(),
    }
    if reason:
        merged_metadata["cancel_reason"] = reason
    offer.offer_metadata = merged_metadata


def mark_offer_failed(
    offer: CoverageOffer,
    *,
    occurred_at: datetime,
    reason: str | None = None,
    metadata: dict | None = None,
) -> None:
    if offer.status == OfferStatus.failed:
        merged_metadata = {
            **(offer.offer_metadata or {}),
            **(metadata or {}),
            "terminal_failure_at": occurred_at.isoformat(),
        }
        if reason:
            merged_metadata["terminal_failure_reason"] = reason
        offer.offer_metadata = merged_metadata
        return
    if coverage_state.is_terminal_offer_status(offer.status):
        raise CoverageTransitionError("offer_already_terminal")
    offer.status = OfferStatus.failed
    merged_metadata = {
        **(offer.offer_metadata or {}),
        **(metadata or {}),
        "terminal_failure_at": occurred_at.isoformat(),
    }
    if reason:
        merged_metadata["terminal_failure_reason"] = reason
    offer.offer_metadata = merged_metadata


def mark_offer_pending(offer: CoverageOffer) -> None:
    if coverage_state.is_terminal_offer_status(offer.status):
        raise CoverageTransitionError("offer_already_terminal")
    offer.status = OfferStatus.pending


def mark_offer_delivered(
    offer: CoverageOffer,
    *,
    sent_at: datetime,
    delivered_at: datetime | None,
) -> None:
    if offer.status == OfferStatus.delivered and delivered_at is not None:
        offer.sent_at = sent_at
        return
    if coverage_state.is_terminal_offer_status(offer.status):
        raise CoverageTransitionError("offer_already_terminal")
    offer.sent_at = sent_at
    offer.status = OfferStatus.delivered if delivered_at is not None else OfferStatus.pending
