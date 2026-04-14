from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from typing import Any

from app.bootstrap import initialize_runtime
from app.config import settings
from app.db.session import get_async_sessionmaker
from app.services import runtime_orchestration

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def process_worker_tick(*, limit: int | None = None) -> dict[str, Any]:
    sessionmaker = get_async_sessionmaker()
    async with sessionmaker() as session:
        try:
            result = await runtime_orchestration.process_runtime_tick(
                session,
                limit=limit or settings.worker_batch_limit,
            )
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


def _log_tick_result(result: dict[str, Any]) -> None:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    logger.info(
        "Worker tick status=%s callback_claimed=%s coverage_claimed=%s delivery_claimed=%s total_failed=%s",
        result.get("status"),
        summary.get("callback_claimed_count", 0),
        summary.get("coverage_claimed_case_count", 0),
        summary.get("delivery_claimed_count", 0),
        summary.get("total_failed_count", 0),
    )


async def _sleep_or_stop(stop_event: asyncio.Event, seconds: float) -> None:
    if seconds <= 0:
        await asyncio.sleep(0)
        return
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        return


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()

    def _stop() -> None:
        if not stop_event.is_set():
            logger.info("Worker shutdown requested")
            stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_args: _stop())


async def run_worker_loop(
    *,
    run_once: bool | None = None,
    poll_seconds: float | None = None,
    error_backoff_seconds: float | None = None,
    limit: int | None = None,
    initialize_runtime_fn: Callable[[], Awaitable[None]] | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    effective_run_once = settings.worker_run_once if run_once is None else run_once
    effective_poll_seconds = settings.worker_poll_seconds if poll_seconds is None else poll_seconds
    effective_error_backoff = (
        settings.worker_error_backoff_seconds
        if error_backoff_seconds is None
        else error_backoff_seconds
    )
    effective_limit = settings.worker_batch_limit if limit is None else limit
    loop_stop_event = stop_event or asyncio.Event()
    _install_signal_handlers(loop_stop_event)
    await (initialize_runtime_fn() if initialize_runtime_fn is not None else initialize_runtime())
    logger.info(
        "Worker started run_once=%s poll_seconds=%s batch_limit=%s",
        effective_run_once,
        effective_poll_seconds,
        effective_limit,
    )

    while not loop_stop_event.is_set():
        try:
            result = await process_worker_tick(limit=effective_limit)
            _log_tick_result(result)
        except Exception:
            logger.exception("Worker tick failed")
            if effective_run_once:
                raise
            await _sleep_or_stop(loop_stop_event, effective_error_backoff)
            continue

        if effective_run_once:
            break

        await _sleep_or_stop(loop_stop_event, effective_poll_seconds)

    logger.info("Worker stopped")


def main() -> None:
    _configure_logging()
    asyncio.run(run_worker_loop())


if __name__ == "__main__":
    main()
