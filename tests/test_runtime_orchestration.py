from __future__ import annotations

import pytest

from app.services import runtime_orchestration


class DummyRuntimeSession:
    async def commit(self):
        return None

    async def rollback(self):
        return None


@pytest.mark.asyncio
async def test_process_runtime_tick_runs_callback_and_coverage_batches_in_order(monkeypatch):
    session = DummyRuntimeSession()
    calls: list[tuple[str, int]] = []

    async def fake_callbacks(_session, *, limit):
        calls.append(("callbacks", limit))
        return {
            "claimed_count": 2,
            "processed_count": 2,
            "failed_count": 0,
            "processed_callback_ids": ["cb_1", "cb_2"],
        }

    async def fake_runtime(_session, *, limit):
        calls.append(("coverage_runtime", limit))
        return {
            "reconcile": {
                "claimed_count": 1,
                "filled_count": 1,
                "cancelled_count": 0,
                "exhausted_count": 0,
                "unchanged_count": 0,
                "failed_count": 0,
                "processed_case_ids": ["case_running"],
            },
            "offer_expiry": {
                "expired_count": 1,
                "exhausted_case_ids": ["case_expired"],
                "advanced_offer_ids": ["offer_next"],
            },
            "queued_cases": {
                "claimed_count": 1,
                "executed_count": 1,
                "exhausted_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "processed_case_ids": ["case_queued"],
            },
            "delivery": {
                "claimed_count": 1,
                "sent_count": 1,
                "failed_count": 0,
                "processed_event_ids": ["evt_1"],
            },
            "processed_case_ids": ["case_running", "case_queued", "case_expired"],
        }

    monkeypatch.setattr(runtime_orchestration.provider_callbacks, "process_callback_batch", fake_callbacks)
    monkeypatch.setattr(runtime_orchestration.coverage_runtime, "process_coverage_runtime_batch", fake_runtime)

    result = await runtime_orchestration.process_runtime_tick(session, limit=7)

    assert calls == [
        ("callbacks", 7),
        ("coverage_runtime", 7),
    ]
    assert result == {
        "status": "processed",
        "summary": {
            "callback_claimed_count": 2,
            "callback_processed_count": 2,
            "callback_failed_count": 0,
            "coverage_claimed_case_count": 2,
            "coverage_processed_case_count": 3,
            "offer_expiry_expired_count": 1,
            "offer_expiry_advanced_offer_count": 1,
            "offer_expiry_exhausted_case_count": 1,
            "delivery_claimed_count": 1,
            "total_failed_count": 0,
        },
        "callbacks": {
            "claimed_count": 2,
            "processed_count": 2,
            "failed_count": 0,
            "processed_callback_ids": ["cb_1", "cb_2"],
        },
        "coverage_runtime": {
            "reconcile": {
                "claimed_count": 1,
                "filled_count": 1,
                "cancelled_count": 0,
                "exhausted_count": 0,
                "unchanged_count": 0,
                "failed_count": 0,
                "processed_case_ids": ["case_running"],
            },
            "offer_expiry": {
                "expired_count": 1,
                "exhausted_case_ids": ["case_expired"],
                "advanced_offer_ids": ["offer_next"],
            },
            "queued_cases": {
                "claimed_count": 1,
                "executed_count": 1,
                "exhausted_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "processed_case_ids": ["case_queued"],
            },
            "delivery": {
                "claimed_count": 1,
                "sent_count": 1,
                "failed_count": 0,
                "processed_event_ids": ["evt_1"],
            },
            "processed_case_ids": ["case_running", "case_queued", "case_expired"],
        },
    }


@pytest.mark.asyncio
async def test_process_runtime_tick_is_duplicate_safe_on_repeated_ticks(monkeypatch):
    session = DummyRuntimeSession()
    call_state = {
        "callbacks": [
            {
                "claimed_count": 1,
                "processed_count": 1,
                "failed_count": 0,
                "processed_callback_ids": ["cb_1"],
            },
            {
                "claimed_count": 0,
                "processed_count": 0,
                "failed_count": 0,
                "processed_callback_ids": [],
            },
        ],
        "runtime": [
            {
                "reconcile": {
                    "claimed_count": 0,
                    "filled_count": 0,
                    "cancelled_count": 0,
                    "exhausted_count": 0,
                    "unchanged_count": 0,
                    "failed_count": 0,
                    "processed_case_ids": [],
                },
                "offer_expiry": {
                    "expired_count": 0,
                    "exhausted_case_ids": [],
                    "advanced_offer_ids": [],
                },
                "queued_cases": {
                    "claimed_count": 1,
                    "executed_count": 1,
                    "exhausted_count": 0,
                    "skipped_count": 0,
                    "failed_count": 0,
                    "processed_case_ids": ["case_1"],
                },
                "delivery": {
                    "claimed_count": 0,
                    "sent_count": 0,
                    "failed_count": 0,
                    "processed_event_ids": [],
                },
                "processed_case_ids": ["case_1"],
            },
            {
                "reconcile": {
                    "claimed_count": 0,
                    "filled_count": 0,
                    "cancelled_count": 0,
                    "exhausted_count": 0,
                    "unchanged_count": 0,
                    "failed_count": 0,
                    "processed_case_ids": [],
                },
                "offer_expiry": {
                    "expired_count": 0,
                    "exhausted_case_ids": [],
                    "advanced_offer_ids": [],
                },
                "queued_cases": {
                    "claimed_count": 0,
                    "executed_count": 0,
                    "exhausted_count": 0,
                    "skipped_count": 0,
                    "failed_count": 0,
                    "processed_case_ids": [],
                },
                "delivery": {
                    "claimed_count": 0,
                    "sent_count": 0,
                    "failed_count": 0,
                    "processed_event_ids": [],
                },
                "processed_case_ids": [],
            },
        ],
    }
    processed_ids: list[str] = []

    async def fake_callbacks(_session, *, limit):
        result = call_state["callbacks"].pop(0)
        processed_ids.extend(result["processed_callback_ids"])
        return result

    async def fake_runtime(_session, *, limit):
        result = call_state["runtime"].pop(0)
        processed_ids.extend(result["processed_case_ids"])
        return result

    monkeypatch.setattr(runtime_orchestration.provider_callbacks, "process_callback_batch", fake_callbacks)
    monkeypatch.setattr(runtime_orchestration.coverage_runtime, "process_coverage_runtime_batch", fake_runtime)

    first_result = await runtime_orchestration.process_runtime_tick(session, limit=5)
    second_result = await runtime_orchestration.process_runtime_tick(session, limit=5)

    assert first_result["status"] == "processed"
    assert second_result["status"] == "idle"
    assert first_result["summary"]["callback_processed_count"] == 1
    assert first_result["summary"]["coverage_processed_case_count"] == 1
    assert first_result["summary"]["offer_expiry_expired_count"] == 0
    assert second_result["summary"]["callback_processed_count"] == 0
    assert second_result["summary"]["coverage_processed_case_count"] == 0
    assert processed_ids == ["cb_1", "case_1"]


@pytest.mark.asyncio
async def test_process_runtime_tick_reports_processed_when_only_offer_expiry_did_work(monkeypatch):
    session = DummyRuntimeSession()

    async def fake_callbacks(_session, *, limit):
        return {
            "claimed_count": 0,
            "processed_count": 0,
            "failed_count": 0,
            "processed_callback_ids": [],
        }

    async def fake_runtime(_session, *, limit):
        return {
            "reconcile": {
                "claimed_count": 0,
                "filled_count": 0,
                "cancelled_count": 0,
                "exhausted_count": 0,
                "unchanged_count": 0,
                "failed_count": 0,
                "processed_case_ids": [],
            },
            "offer_expiry": {
                "expired_count": 2,
                "exhausted_case_ids": ["case_expired"],
                "advanced_offer_ids": ["offer_next"],
            },
            "queued_cases": {
                "claimed_count": 0,
                "executed_count": 0,
                "exhausted_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "processed_case_ids": [],
            },
            "delivery": {
                "claimed_count": 0,
                "sent_count": 0,
                "failed_count": 0,
                "processed_event_ids": [],
            },
            "processed_case_ids": ["case_expired"],
        }

    monkeypatch.setattr(runtime_orchestration.provider_callbacks, "process_callback_batch", fake_callbacks)
    monkeypatch.setattr(runtime_orchestration.coverage_runtime, "process_coverage_runtime_batch", fake_runtime)

    result = await runtime_orchestration.process_runtime_tick(session, limit=5)

    assert result["status"] == "processed"
    assert result["summary"]["offer_expiry_expired_count"] == 2
    assert result["summary"]["offer_expiry_advanced_offer_count"] == 1
    assert result["summary"]["offer_expiry_exhausted_case_count"] == 1
