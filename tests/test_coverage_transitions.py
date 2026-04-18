from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.common import CoverageCaseStatus, OutboxChannel, OfferStatus
from app.models.coverage import CoverageCase, CoverageOffer
from app.services import coverage_transitions


def _case(**overrides) -> CoverageCase:
    return CoverageCase(
        id=overrides.pop("id", uuid4()),
        shift_id=overrides.pop("shift_id", uuid4()),
        location_id=overrides.pop("location_id", uuid4()),
        role_id=overrides.pop("role_id", uuid4()),
        status=overrides.pop("status", CoverageCaseStatus.queued),
        phase_target=overrides.pop("phase_target", "phase_1"),
        priority=overrides.pop("priority", 100),
        requires_manager_approval=overrides.pop("requires_manager_approval", False),
        case_metadata=overrides.pop("case_metadata", {}),
        closed_at=overrides.pop("closed_at", None),
    )


def _offer(**overrides) -> CoverageOffer:
    return CoverageOffer(
        id=overrides.pop("id", uuid4()),
        coverage_case_id=overrides.pop("coverage_case_id", uuid4()),
        employee_id=overrides.pop("employee_id", uuid4()),
        channel=overrides.pop("channel", OutboxChannel.voice),
        status=overrides.pop("status", OfferStatus.pending),
        idempotency_key=overrides.pop("idempotency_key", "offer-key"),
        offer_metadata=overrides.pop("offer_metadata", {}),
        accepted_at=overrides.pop("accepted_at", None),
        declined_at=overrides.pop("declined_at", None),
        sent_at=overrides.pop("sent_at", None),
    )


def test_mark_case_running_clears_closed_at_for_actionable_case() -> None:
    coverage_case = _case(status=CoverageCaseStatus.queued, closed_at=datetime.now(timezone.utc))

    coverage_transitions.mark_case_running(coverage_case)

    assert coverage_case.status == CoverageCaseStatus.running
    assert coverage_case.closed_at is None


def test_mark_case_running_rejects_terminal_case() -> None:
    coverage_case = _case(status=CoverageCaseStatus.cancelled)

    with pytest.raises(coverage_transitions.CoverageTransitionError):
        coverage_transitions.mark_case_running(coverage_case)


def test_mark_case_running_can_reopen_filled_case() -> None:
    coverage_case = _case(status=CoverageCaseStatus.filled, closed_at=datetime.now(timezone.utc))

    coverage_transitions.mark_case_running(coverage_case)

    assert coverage_case.status == CoverageCaseStatus.running
    assert coverage_case.closed_at is None


def test_mark_offer_accepted_requires_actionable_offer() -> None:
    offer = _offer(status=OfferStatus.expired)

    with pytest.raises(coverage_transitions.CoverageTransitionError):
        coverage_transitions.mark_offer_accepted(offer, occurred_at=datetime.now(timezone.utc))


def test_mark_offer_cancelled_is_idempotent_and_stamps_reason() -> None:
    occurred_at = datetime.now(timezone.utc)
    offer = _offer(status=OfferStatus.cancelled)

    coverage_transitions.mark_offer_cancelled(
        offer,
        occurred_at=occurred_at,
        reason="shift_filled",
        metadata={"source": "runtime"},
    )

    assert offer.status == OfferStatus.cancelled
    assert offer.offer_metadata["cancel_reason"] == "shift_filled"
    assert offer.offer_metadata["source"] == "runtime"


def test_mark_offer_failed_is_idempotent_for_duplicate_provider_failure() -> None:
    occurred_at = datetime.now(timezone.utc)
    offer = _offer(status=OfferStatus.failed)

    coverage_transitions.mark_offer_failed(
        offer,
        occurred_at=occurred_at,
        reason="provider_delivery_failed",
        metadata={"provider": "twilio"},
    )

    assert offer.status == OfferStatus.failed
    assert offer.offer_metadata["terminal_failure_reason"] == "provider_delivery_failed"
    assert offer.offer_metadata["provider"] == "twilio"
