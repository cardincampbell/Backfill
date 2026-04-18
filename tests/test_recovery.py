from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.common import CoverageCaseStatus, OfferStatus, OutboxChannel, OutboxStatus
from app.models.coverage import CoverageCase, CoverageOffer, OutboxEvent
from app.models.integrations import ProviderCallbackLog
from app.services import provider_callbacks, recovery


class DummyRecoverySession:
    def __init__(self):
        self.get_map: dict[tuple[type, object], object] = {}
        self.commits = 0

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))

    async def commit(self):
        self.commits += 1


def _callback_entry(**overrides) -> ProviderCallbackLog:
    return ProviderCallbackLog(
        id=overrides.pop("id", uuid4()),
        provider=overrides.pop("provider", "retell"),
        route_key=overrides.pop("route_key", "retell_webhook"),
        event_type=overrides.pop("event_type", "call_analyzed"),
        provider_event_id=overrides.pop("provider_event_id", "call_123"),
        dedupe_key=overrides.pop("dedupe_key", "retell:call_analyzed:call_123"),
        status=overrides.pop("status", "received"),
        headers=overrides.pop("headers", {}),
        payload=overrides.pop("payload", {}),
        result_payload=overrides.pop("result_payload", {}),
        error_message=overrides.pop("error_message", None),
        received_at=overrides.pop("received_at", datetime.now(timezone.utc)),
        processed_at=overrides.pop("processed_at", None),
    )


@pytest.mark.asyncio
async def test_replay_provider_callback_dry_run_blocks_processed_entry(monkeypatch) -> None:
    session = DummyRecoverySession()
    entry = _callback_entry(status="processed", result_payload={"status": "ok"})

    async def fake_load(_session, _callback_log_id):
        return entry

    monkeypatch.setattr(recovery, "_load_callback_entry_for_update", fake_load)

    result = await recovery.replay_provider_callback_log(
        session,
        callback_log_id=entry.id,
        mode="dry_run",
    )

    assert result["action"] == "preview"
    assert result["allowed"] is False
    assert result["reason_codes"] == ["callback_already_processed"]
    assert "callback_replay_can_repeat_side_effects" in result["warnings"]


@pytest.mark.asyncio
async def test_replay_provider_callback_reprocesses_failed_entry(monkeypatch) -> None:
    session = DummyRecoverySession()
    entry = _callback_entry(status="failed", error_message="transient_error")

    async def fake_load(_session, _callback_log_id):
        return entry

    async def fake_process(_session, locked_entry):
        locked_entry.status = "processed"
        return provider_callbacks.CallbackProcessingResult(
            callback_log_id=locked_entry.id,
            response_kind="json",
            response_payload={"status": "processed"},
        )

    async def fake_get(_session, *, callback_log_id):
        assert callback_log_id == entry.id
        return entry

    monkeypatch.setattr(recovery, "_load_callback_entry_for_update", fake_load)
    monkeypatch.setattr(provider_callbacks, "process_callback_entry_synchronously", fake_process)
    monkeypatch.setattr(provider_callbacks, "get_callback_log", fake_get)

    result = await recovery.replay_provider_callback_log(
        session,
        callback_log_id=entry.id,
        mode="reprocess_if_preconditions_match",
    )

    assert result["action"] == "reprocessed"
    assert result["allowed"] is True
    assert result["status_after"] == "processed"
    assert result["response_payload"] == {"status": "processed"}


@pytest.mark.asyncio
async def test_replay_coverage_outbox_dry_run_blocks_sent_event(monkeypatch) -> None:
    session = DummyRecoverySession()
    case_id = uuid4()
    offer_id = uuid4()
    event = OutboxEvent(
        id=uuid4(),
        aggregate_type="coverage_offer",
        aggregate_id=offer_id,
        topic="coverage.offer.created",
        channel=OutboxChannel.voice,
        status=OutboxStatus.sent,
        attempt_count=1,
        payload={},
    )
    offer = CoverageOffer(
        id=offer_id,
        coverage_case_id=case_id,
        employee_id=uuid4(),
        channel=OutboxChannel.voice,
        status=OfferStatus.pending,
        idempotency_key="offer-key",
        offer_metadata={},
    )
    coverage_case = CoverageCase(
        id=case_id,
        shift_id=uuid4(),
        location_id=uuid4(),
        role_id=uuid4(),
        status=CoverageCaseStatus.running,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
    )
    session.get_map[(CoverageOffer, offer_id)] = offer
    session.get_map[(CoverageCase, case_id)] = coverage_case

    async def fake_load(_session, _outbox_event_id):
        return event

    monkeypatch.setattr(recovery, "_load_outbox_event_for_update", fake_load)

    result = await recovery.replay_coverage_outbox_event(
        session,
        outbox_event_id=event.id,
        mode="dry_run",
    )

    assert result["action"] == "preview"
    assert result["allowed"] is False
    assert "outbox_already_sent" in result["reason_codes"]


@pytest.mark.asyncio
async def test_replay_coverage_outbox_reprocesses_failed_pending_event(monkeypatch) -> None:
    session = DummyRecoverySession()
    case_id = uuid4()
    offer_id = uuid4()
    event = OutboxEvent(
        id=uuid4(),
        aggregate_type="coverage_offer",
        aggregate_id=offer_id,
        topic="coverage.offer.created",
        channel=OutboxChannel.voice,
        status=OutboxStatus.failed,
        attempt_count=1,
        payload={},
    )
    offer = CoverageOffer(
        id=offer_id,
        coverage_case_id=case_id,
        employee_id=uuid4(),
        channel=OutboxChannel.voice,
        status=OfferStatus.pending,
        idempotency_key="offer-key",
        offer_metadata={},
    )
    coverage_case = CoverageCase(
        id=case_id,
        shift_id=uuid4(),
        location_id=uuid4(),
        role_id=uuid4(),
        status=CoverageCaseStatus.running,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
    )
    session.get_map[(CoverageOffer, offer_id)] = offer
    session.get_map[(CoverageCase, case_id)] = coverage_case

    async def fake_load(_session, _outbox_event_id):
        return event

    async def fake_process(_session, *, outbox_event, provider=None, now=None):
        assert provider is None
        assert now is not None
        assert outbox_event.status == OutboxStatus.processing
        assert outbox_event.attempt_count == 2
        outbox_event.status = OutboxStatus.sent
        return {
            "processed": True,
            "sent": True,
            "failed": False,
            "error_message": None,
            "result_payload": {"provider_message_id": "msg_123"},
        }

    monkeypatch.setattr(recovery, "_load_outbox_event_for_update", fake_load)
    monkeypatch.setattr(recovery.delivery, "process_outbox_event", fake_process)

    result = await recovery.replay_coverage_outbox_event(
        session,
        outbox_event_id=event.id,
        mode="reprocess_if_preconditions_match",
    )

    assert result["action"] == "reprocessed"
    assert result["allowed"] is True
    assert result["status_after"] == "sent"
    assert result["sent"] is True
    assert session.commits == 1
