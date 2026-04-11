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
            "dead_lettered_count": 0,
            "processed_callback_ids": ["cb_1", "cb_2"],
        }

    async def fake_projection_health(_session, *, business_limit):
        calls.append(("runtime_projections", business_limit))
        return {
            "status": "ready",
            "checked_at": "2026-04-10T20:00:00+00:00",
            "freshness_target_seconds": 900,
            "monitored_business_count": 2,
            "candidate_employee_count": 8,
            "fresh_employee_count": 7,
            "stale_employee_count": 1,
            "missing_employee_count": 0,
            "blocked_business_count": 0,
            "blocked_business_ids": [],
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
    monkeypatch.setattr(runtime_orchestration.runtime_projections, "monitor_runtime_projection_freshness", fake_projection_health)
    monkeypatch.setattr(runtime_orchestration.coverage_runtime, "process_coverage_runtime_batch", fake_runtime)

    result = await runtime_orchestration.process_runtime_tick(session, limit=7)

    assert calls == [
        ("callbacks", 7),
        ("runtime_projections", 7),
        ("coverage_runtime", 7),
    ]
    assert result == {
        "status": "processed",
        "summary": {
            "callback_claimed_count": 2,
            "callback_processed_count": 2,
            "callback_failed_count": 0,
            "callback_dead_lettered_count": 0,
            "coverage_claimed_case_count": 2,
            "coverage_processed_case_count": 3,
            "offer_expiry_expired_count": 1,
            "offer_expiry_advanced_offer_count": 1,
            "offer_expiry_exhausted_case_count": 1,
            "delivery_claimed_count": 1,
            "projection_monitored_business_count": 2,
            "projection_blocked_business_count": 0,
            "projection_stale_employee_count": 1,
            "projection_missing_employee_count": 0,
            "total_failed_count": 0,
        },
        "callbacks": {
            "claimed_count": 2,
            "processed_count": 2,
            "failed_count": 0,
            "dead_lettered_count": 0,
            "processed_callback_ids": ["cb_1", "cb_2"],
        },
        "runtime_projections": {
            "status": "ready",
            "checked_at": "2026-04-10T20:00:00+00:00",
            "freshness_target_seconds": 900,
            "monitored_business_count": 2,
            "candidate_employee_count": 8,
            "fresh_employee_count": 7,
            "stale_employee_count": 1,
            "missing_employee_count": 0,
            "blocked_business_count": 0,
            "blocked_business_ids": [],
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
                "dead_lettered_count": 0,
                "processed_callback_ids": ["cb_1"],
            },
            {
                "claimed_count": 0,
                "processed_count": 0,
                "failed_count": 0,
                "dead_lettered_count": 0,
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

    async def fake_projection_health(_session, *, business_limit):
        return {
            "status": "ready",
            "checked_at": "2026-04-10T20:00:00+00:00",
            "freshness_target_seconds": 900,
            "monitored_business_count": 1,
            "candidate_employee_count": 3,
            "fresh_employee_count": 3,
            "stale_employee_count": 0,
            "missing_employee_count": 0,
            "blocked_business_count": 0,
            "blocked_business_ids": [],
        }

    monkeypatch.setattr(runtime_orchestration.provider_callbacks, "process_callback_batch", fake_callbacks)
    monkeypatch.setattr(runtime_orchestration.runtime_projections, "monitor_runtime_projection_freshness", fake_projection_health)
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
            "dead_lettered_count": 0,
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

    async def fake_projection_health(_session, *, business_limit):
        return {
            "status": "ready",
            "checked_at": "2026-04-10T20:00:00+00:00",
            "freshness_target_seconds": 900,
            "monitored_business_count": 1,
            "candidate_employee_count": 2,
            "fresh_employee_count": 2,
            "stale_employee_count": 0,
            "missing_employee_count": 0,
            "blocked_business_count": 0,
            "blocked_business_ids": [],
        }

    monkeypatch.setattr(runtime_orchestration.provider_callbacks, "process_callback_batch", fake_callbacks)
    monkeypatch.setattr(runtime_orchestration.runtime_projections, "monitor_runtime_projection_freshness", fake_projection_health)
    monkeypatch.setattr(runtime_orchestration.coverage_runtime, "process_coverage_runtime_batch", fake_runtime)

    result = await runtime_orchestration.process_runtime_tick(session, limit=5)

    assert result["status"] == "processed"
    assert result["summary"]["offer_expiry_expired_count"] == 2
    assert result["summary"]["offer_expiry_advanced_offer_count"] == 1
    assert result["summary"]["offer_expiry_exhausted_case_count"] == 1


@pytest.mark.asyncio
async def test_process_runtime_tick_blocks_coverage_runtime_when_projection_health_is_too_stale(monkeypatch):
    session = DummyRuntimeSession()

    async def fake_callbacks(_session, *, limit):
        return {
            "claimed_count": 1,
            "processed_count": 1,
            "failed_count": 0,
            "dead_lettered_count": 0,
            "processed_callback_ids": ["cb_1"],
        }

    async def fake_projection_health(_session, *, business_limit):
        return {
            "status": "blocked",
            "checked_at": "2026-04-10T20:00:00+00:00",
            "freshness_target_seconds": 900,
            "monitored_business_count": 2,
            "candidate_employee_count": 10,
            "fresh_employee_count": 4,
            "stale_employee_count": 4,
            "missing_employee_count": 2,
            "blocked_business_count": 1,
            "blocked_business_ids": ["biz_1"],
            "blocked_reason": "runtime_projections_too_stale",
        }

    async def fail_if_called(_session, *, limit):
        raise AssertionError("coverage runtime should not run when projections are blocked")

    monkeypatch.setattr(runtime_orchestration.provider_callbacks, "process_callback_batch", fake_callbacks)
    monkeypatch.setattr(runtime_orchestration.runtime_projections, "monitor_runtime_projection_freshness", fake_projection_health)
    monkeypatch.setattr(runtime_orchestration.coverage_runtime, "process_coverage_runtime_batch", fail_if_called)

    result = await runtime_orchestration.process_runtime_tick(session, limit=4)

    assert result["status"] == "blocked"
    assert result["runtime_projections"]["blocked_reason"] == "runtime_projections_too_stale"
    assert result["coverage_runtime"]["status"] == "blocked"
    assert result["summary"]["projection_blocked_business_count"] == 1
    assert result["summary"]["callback_processed_count"] == 1
