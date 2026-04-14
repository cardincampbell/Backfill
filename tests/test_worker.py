from __future__ import annotations

import asyncio

import pytest

from app import worker


class DummySession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class DummySessionContext:
    def __init__(self, session: DummySession):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _sessionmaker_for(session: DummySession):
    def factory():
        return DummySessionContext(session)

    return factory


@pytest.mark.asyncio
async def test_process_worker_tick_commits_on_success(monkeypatch):
    session = DummySession()

    async def fake_tick(_session, *, limit):
        assert limit == 7
        return {"status": "processed", "summary": {"delivery_claimed_count": 1}}

    monkeypatch.setattr(worker, "get_async_sessionmaker", lambda: _sessionmaker_for(session))
    monkeypatch.setattr(worker.runtime_orchestration, "process_runtime_tick", fake_tick)

    result = await worker.process_worker_tick(limit=7)

    assert result["status"] == "processed"
    assert session.commits == 1
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_process_worker_tick_rolls_back_on_error(monkeypatch):
    session = DummySession()

    async def fake_tick(_session, *, limit):
        raise RuntimeError("boom")

    monkeypatch.setattr(worker, "get_async_sessionmaker", lambda: _sessionmaker_for(session))
    monkeypatch.setattr(worker.runtime_orchestration, "process_runtime_tick", fake_tick)

    with pytest.raises(RuntimeError, match="boom"):
        await worker.process_worker_tick(limit=5)

    assert session.commits == 0
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_run_worker_loop_run_once_initializes_and_processes(monkeypatch):
    calls: list[tuple[str, int | None]] = []

    async def fake_initialize():
        calls.append(("initialize", None))

    async def fake_process_worker_tick(*, limit=None):
        calls.append(("tick", limit))
        return {"status": "processed", "summary": {"delivery_claimed_count": 1}}

    monkeypatch.setattr(worker, "_install_signal_handlers", lambda _stop_event: None)
    monkeypatch.setattr(worker, "process_worker_tick", fake_process_worker_tick)

    await worker.run_worker_loop(
        run_once=True,
        limit=9,
        initialize_runtime_fn=fake_initialize,
        stop_event=asyncio.Event(),
    )

    assert calls == [
        ("initialize", None),
        ("tick", 9),
    ]
