from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.common import CoverageCaseStatus, OutboxChannel, OutboxStatus, SchedulerProvider, SchedulerSyncJobStatus
from app.models.coverage import CoverageCase, OutboxEvent
from app.models.integrations import SchedulerSyncJob
from app.services import worker_runtime


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarResult(self._values)

    def all(self):
        return list(self._values)


class FakeWorkerSession:
    def __init__(self):
        self.execute_queue: list[list[object]] = []
        self.flushes = 0

    async def execute(self, _query):
        values = self.execute_queue.pop(0) if self.execute_queue else []
        return _ExecuteResult(values)

    async def flush(self):
        self.flushes += 1


@pytest.mark.asyncio
async def test_claim_outbox_events_enforces_business_isolation() -> None:
    now = datetime.now(timezone.utc)
    business_a = uuid4()
    business_b = uuid4()
    first = OutboxEvent(
        id=uuid4(),
        aggregate_type="coverage_offer",
        aggregate_id=uuid4(),
        topic="coverage.offer.created",
        channel=OutboxChannel.sms,
        status=OutboxStatus.pending,
        attempt_count=0,
        available_at=now,
        payload={},
    )
    second = OutboxEvent(
        id=uuid4(),
        aggregate_type="coverage_offer",
        aggregate_id=uuid4(),
        topic="coverage.offer.created",
        channel=OutboxChannel.sms,
        status=OutboxStatus.pending,
        attempt_count=1,
        available_at=now,
        payload={},
    )
    third = OutboxEvent(
        id=uuid4(),
        aggregate_type="coverage_offer",
        aggregate_id=uuid4(),
        topic="coverage.offer.created",
        channel=OutboxChannel.sms,
        status=OutboxStatus.pending,
        attempt_count=0,
        available_at=now,
        payload={},
    )
    session = FakeWorkerSession()
    session.execute_queue = [[first, second, third]]

    async def fake_business_resolver(_session, events):
        return {
            first.id: business_a,
            second.id: business_a,
            third.id: business_b,
        }

    claimed = await worker_runtime.claim_outbox_events(
        session,
        now=now,
        limit=3,
        topic="coverage.offer.created",
        business_resolver=fake_business_resolver,
    )

    assert claimed == [first, third]
    assert first.status == OutboxStatus.processing
    assert first.locked_at == now
    assert first.attempt_count == 1
    assert second.status == OutboxStatus.pending
    assert second.attempt_count == 1
    assert third.status == OutboxStatus.processing
    assert third.attempt_count == 1


@pytest.mark.asyncio
async def test_claim_scheduler_jobs_enforces_business_isolation() -> None:
    now = datetime.now(timezone.utc)
    business_a = uuid4()
    business_b = uuid4()
    first = SchedulerSyncJob(
        id=uuid4(),
        connection_id=None,
        scheduler_event_id=None,
        business_id=business_a,
        location_id=None,
        provider=SchedulerProvider.backfill_native,
        job_type="rolling_reconcile",
        priority=10,
        scope=None,
        scope_ref=None,
        status=SchedulerSyncJobStatus.queued,
        attempt_count=0,
        max_attempts=3,
        next_run_at=now - timedelta(minutes=1),
    )
    second = SchedulerSyncJob(
        id=uuid4(),
        connection_id=None,
        scheduler_event_id=None,
        business_id=business_a,
        location_id=None,
        provider=SchedulerProvider.backfill_native,
        job_type="daily_reconcile",
        priority=20,
        scope=None,
        scope_ref=None,
        status=SchedulerSyncJobStatus.queued,
        attempt_count=1,
        max_attempts=3,
        next_run_at=now - timedelta(minutes=1),
    )
    third = SchedulerSyncJob(
        id=uuid4(),
        connection_id=None,
        scheduler_event_id=None,
        business_id=business_b,
        location_id=None,
        provider=SchedulerProvider.backfill_native,
        job_type="writeback",
        priority=30,
        scope=None,
        scope_ref=None,
        status=SchedulerSyncJobStatus.queued,
        attempt_count=0,
        max_attempts=3,
        next_run_at=now - timedelta(minutes=1),
    )
    session = FakeWorkerSession()
    session.execute_queue = [[first, second, third]]

    claimed = await worker_runtime.claim_scheduler_jobs(
        session,
        now=now,
        limit=3,
    )

    assert claimed == [first, third]
    assert first.status == SchedulerSyncJobStatus.running
    assert first.started_at == now
    assert first.attempt_count == 1
    assert second.status == SchedulerSyncJobStatus.queued
    assert second.attempt_count == 1
    assert third.status == SchedulerSyncJobStatus.running
    assert third.attempt_count == 1


def test_retry_delay_for_attempt_caps_at_last_schedule_entry() -> None:
    first = worker_runtime.retry_delay_for_attempt(1)
    second = worker_runtime.retry_delay_for_attempt(2)
    third = worker_runtime.retry_delay_for_attempt(5)

    assert first == timedelta(minutes=1)
    assert second == timedelta(minutes=5)
    assert third == timedelta(minutes=15)


@pytest.mark.asyncio
async def test_claim_queued_coverage_cases_enforces_business_isolation() -> None:
    now = datetime.now(timezone.utc)
    business_a = uuid4()
    business_b = uuid4()
    first = CoverageCase(
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
    second = CoverageCase(
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
    third = CoverageCase(
        id=uuid4(),
        shift_id=uuid4(),
        location_id=uuid4(),
        role_id=uuid4(),
        status=CoverageCaseStatus.queued,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
        opened_at=now + timedelta(seconds=2),
    )
    session = FakeWorkerSession()
    session.execute_queue = [[(first, business_a), (second, business_a), (third, business_b)]]

    claimed = await worker_runtime.claim_queued_coverage_cases(session, limit=3)

    assert claimed == [(first, business_a), (third, business_b)]


@pytest.mark.asyncio
async def test_claim_running_coverage_cases_enforces_business_isolation() -> None:
    now = datetime.now(timezone.utc)
    business_a = uuid4()
    business_b = uuid4()
    first = CoverageCase(
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
    second = CoverageCase(
        id=uuid4(),
        shift_id=uuid4(),
        location_id=uuid4(),
        role_id=uuid4(),
        status=CoverageCaseStatus.running,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
        opened_at=now + timedelta(seconds=1),
    )
    third = CoverageCase(
        id=uuid4(),
        shift_id=uuid4(),
        location_id=uuid4(),
        role_id=uuid4(),
        status=CoverageCaseStatus.running,
        phase_target="phase_1",
        priority=100,
        requires_manager_approval=False,
        case_metadata={},
        opened_at=now + timedelta(seconds=2),
    )
    session = FakeWorkerSession()
    session.execute_queue = [[(first, business_a), (second, business_a), (third, business_b)]]

    claimed = await worker_runtime.claim_running_coverage_cases(session, limit=3)

    assert claimed == [(first, business_a), (third, business_b)]
