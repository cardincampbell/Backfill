from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.common import CoverageCaseStatus, ShiftStatus
from app.models.coverage import CoverageCase
from app.models.scheduling import Shift
from app.services import coverage_runtime


class FakeCoverageRuntimeSession:
    def __init__(self):
        self.get_map: dict[tuple[type, object], object] = {}
        self.commits = 0
        self.rollbacks = 0
        self.execute_queue: list[list[object]] = []

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))

    async def execute(self, _query):
        class _ExecuteResult:
            def __init__(self, values):
                self._values = values

            def scalars(self):
                class _ScalarResult:
                    def __init__(self, values):
                        self._values = values

                    def all(self):
                        return list(self._values)

                return _ScalarResult(self._values)

        values = self.execute_queue.pop(0) if self.execute_queue else []
        return _ExecuteResult(values)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_execute_queued_case_uses_case_defaults(monkeypatch):
    business_id = uuid4()
    case = CoverageCase(
        id=uuid4(),
        shift_id=uuid4(),
        location_id=uuid4(),
        role_id=uuid4(),
        status=CoverageCaseStatus.queued,
        phase_target="phase_2",
        priority=100,
        requires_manager_approval=False,
        triggered_by="scheduler:test",
        case_metadata={
            "execution_request": {
                "channel": "voice",
                "dispatch_limit": 3,
                "offer_ttl_minutes": 4,
                "run_metadata": {"source": "stored"},
            }
        },
    )
    session = FakeCoverageRuntimeSession()
    session.get_map[(CoverageCase, case.id)] = case

    async def fake_execute(_session, _business_id, coverage_case_id, payload):
        assert _business_id == business_id
        assert coverage_case_id == case.id
        assert payload.phase_override == "phase_2"
        assert payload.channel == "voice"
        assert payload.dispatch_limit == 3
        assert payload.offer_ttl_minutes == 4
        assert payload.run_metadata["source"] == "stored"
        assert payload.run_metadata["triggered_by"] == "scheduler:test"
        return SimpleNamespace(phase_executed="phase_2")

    monkeypatch.setattr(coverage_runtime.coverage, "execute_next_coverage_phase", fake_execute)

    result = await coverage_runtime.execute_queued_case(
        session,
        business_id=business_id,
        coverage_case_id=case.id,
    )

    assert result.phase_executed == "phase_2"


@pytest.mark.asyncio
async def test_process_queued_coverage_cases_executes_and_skips_filled(monkeypatch):
    now = datetime.now(timezone.utc)
    business_a = uuid4()
    business_b = uuid4()
    executable_case = CoverageCase(
        id=uuid4(),
        shift_id=uuid4(),
        location_id=uuid4(),
        role_id=uuid4(),
        status=CoverageCaseStatus.queued,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
        opened_at=now,
    )
    filled_case = CoverageCase(
        id=uuid4(),
        shift_id=uuid4(),
        location_id=uuid4(),
        role_id=uuid4(),
        status=CoverageCaseStatus.queued,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
        opened_at=now + timedelta(seconds=1),
    )
    executable_shift = Shift(
        id=executable_case.shift_id,
        business_id=business_a,
        location_id=executable_case.location_id,
        role_id=executable_case.role_id,
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
    )
    filled_shift = Shift(
        id=filled_case.shift_id,
        business_id=business_b,
        location_id=filled_case.location_id,
        role_id=filled_case.role_id,
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
        status=ShiftStatus.covered,
        seats_requested=1,
        seats_filled=1,
    )
    session = FakeCoverageRuntimeSession()
    session.get_map[(CoverageCase, executable_case.id)] = executable_case
    session.get_map[(CoverageCase, filled_case.id)] = filled_case
    session.get_map[(Shift, executable_shift.id)] = executable_shift
    session.get_map[(Shift, filled_shift.id)] = filled_shift
    appended_events: list[str] = []

    async def fake_claim(_session, *, limit):
        assert limit == 5
        return [
            (executable_case, business_a),
            (filled_case, business_b),
        ]

    async def fake_execute(_session, *, business_id, coverage_case_id, channel=None, dispatch_limit=None, offer_ttl_minutes=None, run_metadata=None):
        assert business_id == business_a
        assert coverage_case_id == executable_case.id
        return SimpleNamespace(
            phase_executed="phase_1",
            coverage_case=executable_case,
            run=SimpleNamespace(id=uuid4()),
            candidate_count=3,
            offers=[SimpleNamespace(id=uuid4())],
        )

    async def fake_platform_event_append(_session, *, event_type, **kwargs):
        appended_events.append(event_type)
        return None

    monkeypatch.setattr(coverage_runtime.worker_runtime, "claim_queued_coverage_cases", fake_claim)
    monkeypatch.setattr(coverage_runtime, "execute_queued_case", fake_execute)
    monkeypatch.setattr(coverage_runtime.platform_events, "append", fake_platform_event_append)

    result = await coverage_runtime.process_queued_coverage_cases(session, limit=5)

    assert result == {
        "claimed_count": 2,
        "executed_count": 1,
        "exhausted_count": 0,
        "skipped_count": 1,
        "failed_count": 0,
        "processed_case_ids": [str(executable_case.id), str(filled_case.id)],
    }
    assert filled_case.status == CoverageCaseStatus.filled
    assert session.commits == 2
    assert appended_events == [
        coverage_runtime.platform_events.PlatformEventType.COVERAGE_DISPATCH_EXECUTED,
        coverage_runtime.platform_events.PlatformEventType.COVERAGE_PHASE_1_EXECUTED,
        "coverage.campaign.filled",
    ]


@pytest.mark.asyncio
async def test_reconcile_running_coverage_cases_marks_filled_and_cancels_active_offers(monkeypatch):
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    coverage_case = CoverageCase(
        id=uuid4(),
        shift_id=uuid4(),
        location_id=uuid4(),
        role_id=uuid4(),
        status=CoverageCaseStatus.running,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
        opened_at=now,
    )
    shift = Shift(
        id=coverage_case.shift_id,
        business_id=business_id,
        location_id=coverage_case.location_id,
        role_id=coverage_case.role_id,
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
        status=ShiftStatus.covered,
        seats_requested=1,
        seats_filled=1,
    )
    active_offer = coverage_runtime.CoverageOffer(
        id=uuid4(),
        coverage_case_id=coverage_case.id,
        employee_id=uuid4(),
        channel="sms",
        status=coverage_runtime.OfferStatus.pending,
        idempotency_key="offer-active",
        offer_metadata={},
    )
    session = FakeCoverageRuntimeSession()
    session.get_map[(CoverageCase, coverage_case.id)] = coverage_case
    session.get_map[(Shift, shift.id)] = shift
    session.execute_queue = [[active_offer]]
    appended_events: list[str] = []

    async def fake_claim(_session, *, limit):
        assert limit == 5
        return [(coverage_case, business_id)]

    async def fake_mark_offer_attempt_outcome(*args, **kwargs):
        return None

    async def fake_platform_event_append(_session, *, event_type, **kwargs):
        appended_events.append(event_type)
        return None

    monkeypatch.setattr(coverage_runtime.worker_runtime, "claim_running_coverage_cases", fake_claim)
    monkeypatch.setattr(coverage_runtime.delivery, "mark_offer_attempt_outcome", fake_mark_offer_attempt_outcome)
    monkeypatch.setattr(coverage_runtime.platform_events, "append", fake_platform_event_append)

    result = await coverage_runtime.reconcile_running_coverage_cases(session, limit=5)

    assert result["filled_count"] == 1
    assert result["cancelled_count"] == 0
    assert result["exhausted_count"] == 0
    assert active_offer.status == coverage_runtime.OfferStatus.cancelled
    assert coverage_case.status == CoverageCaseStatus.filled
    assert session.commits == 1
    assert appended_events == [
        "coverage.offer.cancelled",
        "coverage.campaign.filled",
    ]


@pytest.mark.asyncio
async def test_reconcile_running_coverage_cases_exhausts_when_no_active_offers(monkeypatch):
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    coverage_case = CoverageCase(
        id=uuid4(),
        shift_id=uuid4(),
        location_id=uuid4(),
        role_id=uuid4(),
        status=CoverageCaseStatus.running,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
        opened_at=now,
    )
    shift = Shift(
        id=coverage_case.shift_id,
        business_id=business_id,
        location_id=coverage_case.location_id,
        role_id=coverage_case.role_id,
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
        status=ShiftStatus.open,
        seats_requested=1,
        seats_filled=0,
    )
    session = FakeCoverageRuntimeSession()
    session.get_map[(CoverageCase, coverage_case.id)] = coverage_case
    session.get_map[(Shift, shift.id)] = shift
    session.execute_queue = [[]]
    appended_events: list[str] = []

    async def fake_claim(_session, *, limit):
        return [(coverage_case, business_id)]

    async def fake_platform_event_append(_session, *, event_type, **kwargs):
        appended_events.append(event_type)
        return None

    monkeypatch.setattr(coverage_runtime.worker_runtime, "claim_running_coverage_cases", fake_claim)
    monkeypatch.setattr(coverage_runtime.platform_events, "append", fake_platform_event_append)

    result = await coverage_runtime.reconcile_running_coverage_cases(session, limit=5)

    assert result["filled_count"] == 0
    assert result["cancelled_count"] == 0
    assert result["exhausted_count"] == 1
    assert coverage_case.status == CoverageCaseStatus.exhausted
    assert appended_events == ["coverage.campaign.exhausted"]


@pytest.mark.asyncio
async def test_reconcile_running_coverage_cases_marks_cancelled_when_shift_not_actionable(monkeypatch):
    now = datetime.now(timezone.utc)
    business_id = uuid4()
    coverage_case = CoverageCase(
        id=uuid4(),
        shift_id=uuid4(),
        location_id=uuid4(),
        role_id=uuid4(),
        status=CoverageCaseStatus.running,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
        opened_at=now,
    )
    shift = Shift(
        id=coverage_case.shift_id,
        business_id=business_id,
        location_id=coverage_case.location_id,
        role_id=coverage_case.role_id,
        timezone="America/Los_Angeles",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=10),
        status=ShiftStatus.cancelled,
        seats_requested=1,
        seats_filled=0,
    )
    active_offer = coverage_runtime.CoverageOffer(
        id=uuid4(),
        coverage_case_id=coverage_case.id,
        employee_id=uuid4(),
        channel="sms",
        status=coverage_runtime.OfferStatus.delivered,
        idempotency_key="offer-cancelled",
        offer_metadata={},
    )
    session = FakeCoverageRuntimeSession()
    session.get_map[(CoverageCase, coverage_case.id)] = coverage_case
    session.get_map[(Shift, shift.id)] = shift
    session.execute_queue = [[active_offer]]
    appended_events: list[str] = []

    async def fake_claim(_session, *, limit):
        assert limit == 5
        return [(coverage_case, business_id)]

    async def fake_mark_offer_attempt_outcome(*args, **kwargs):
        return None

    async def fake_platform_event_append(_session, *, event_type, **kwargs):
        appended_events.append(event_type)
        return None

    monkeypatch.setattr(coverage_runtime.worker_runtime, "claim_running_coverage_cases", fake_claim)
    monkeypatch.setattr(coverage_runtime.delivery, "mark_offer_attempt_outcome", fake_mark_offer_attempt_outcome)
    monkeypatch.setattr(coverage_runtime.platform_events, "append", fake_platform_event_append)

    result = await coverage_runtime.reconcile_running_coverage_cases(session, limit=5)

    assert result["filled_count"] == 0
    assert result["cancelled_count"] == 1
    assert result["exhausted_count"] == 0
    assert active_offer.status == coverage_runtime.OfferStatus.cancelled
    assert coverage_case.status == CoverageCaseStatus.cancelled
    assert session.commits == 1
    assert appended_events == [
        "coverage.offer.cancelled",
        "coverage.campaign.cancelled",
    ]


@pytest.mark.asyncio
async def test_process_coverage_runtime_batch_runs_runtime_stages_in_order(monkeypatch):
    session = FakeCoverageRuntimeSession()
    calls: list[tuple[str, int]] = []

    async def fake_reconcile(_session, *, limit):
        calls.append(("reconcile", limit))
        return {
            "claimed_count": 1,
            "filled_count": 1,
            "cancelled_count": 0,
            "exhausted_count": 0,
            "unchanged_count": 0,
            "failed_count": 0,
            "processed_case_ids": ["case-running"],
        }

    async def fake_expire(_session, *, limit):
        calls.append(("expire", limit))
        return {
            "expired_count": 1,
            "exhausted_case_ids": ["case-expired"],
            "advanced_offer_ids": ["offer-next"],
        }

    async def fake_process_queued(_session, *, limit):
        calls.append(("queued", limit))
        return {
            "claimed_count": 1,
            "executed_count": 1,
            "exhausted_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "processed_case_ids": ["case-queued", "case-running"],
        }

    async def fake_process_outbox(_session, *, limit):
        calls.append(("delivery", limit))
        return {
            "claimed_count": 2,
            "sent_count": 2,
            "failed_count": 0,
            "processed_event_ids": ["event-1", "event-2"],
        }

    monkeypatch.setattr(coverage_runtime, "reconcile_running_coverage_cases", fake_reconcile)
    monkeypatch.setattr(coverage_runtime.delivery, "expire_due_offers", fake_expire)
    monkeypatch.setattr(coverage_runtime, "process_queued_coverage_cases", fake_process_queued)
    monkeypatch.setattr(coverage_runtime.delivery, "process_outbox_batch", fake_process_outbox)

    result = await coverage_runtime.process_coverage_runtime_batch(session, limit=7)

    assert calls == [
        ("reconcile", 7),
        ("expire", 7),
        ("queued", 7),
        ("delivery", 7),
    ]
    assert result == {
        "reconcile": {
            "claimed_count": 1,
            "filled_count": 1,
            "cancelled_count": 0,
            "exhausted_count": 0,
            "unchanged_count": 0,
            "failed_count": 0,
            "processed_case_ids": ["case-running"],
        },
        "offer_expiry": {
            "expired_count": 1,
            "exhausted_case_ids": ["case-expired"],
            "advanced_offer_ids": ["offer-next"],
        },
        "queued_cases": {
            "claimed_count": 1,
            "executed_count": 1,
            "exhausted_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "processed_case_ids": ["case-queued", "case-running"],
        },
        "delivery": {
            "claimed_count": 2,
            "sent_count": 2,
            "failed_count": 0,
            "processed_event_ids": ["event-1", "event-2"],
        },
        "processed_case_ids": ["case-running", "case-queued", "case-expired"],
    }
