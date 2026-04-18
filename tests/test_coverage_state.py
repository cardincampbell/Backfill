from __future__ import annotations

from app.models.common import CoverageCaseStatus, OfferStatus, OutboxStatus
from app.services import coverage_state


def test_coverage_state_helpers_classify_current_statuses() -> None:
    assert coverage_state.is_actionable_coverage_case_status(CoverageCaseStatus.queued) is True
    assert coverage_state.is_actionable_coverage_case_status(CoverageCaseStatus.running) is True
    assert coverage_state.is_terminal_coverage_case_status(CoverageCaseStatus.filled) is True
    assert coverage_state.is_terminal_coverage_case_status(CoverageCaseStatus.failed) is True

    assert coverage_state.is_actionable_offer_status(OfferStatus.pending) is True
    assert coverage_state.is_actionable_offer_status(OfferStatus.delivered) is True
    assert coverage_state.is_terminal_offer_status(OfferStatus.accepted) is True
    assert coverage_state.is_terminal_offer_status(OfferStatus.expired) is True

    assert coverage_state.is_requeueable_outbox_status(OutboxStatus.pending) is True
    assert coverage_state.is_requeueable_outbox_status(OutboxStatus.failed) is True
    assert coverage_state.is_requeueable_outbox_status(OutboxStatus.sent) is False


def test_coverage_state_helpers_reject_unknown_values() -> None:
    assert coverage_state.is_actionable_coverage_case_status("unknown") is False
    assert coverage_state.is_terminal_offer_status("unknown") is False
    assert coverage_state.is_requeueable_outbox_status("unknown") is False
    assert coverage_state.is_callback_reprocessable_status("processed") is False
    assert coverage_state.is_callback_force_requeueable_status("processed") is True
