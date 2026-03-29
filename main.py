from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.database import init_db
from app.routes import router as api_router
from app.services import ops_queue
from app.webhooks.retell_hooks import router as retell_router
from app.webhooks.scheduling_hooks import router as scheduling_router
from app.webhooks.twilio_hooks import router as twilio_router
from app.web_views import router as web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    stop_event: asyncio.Event | None = None
    worker_task: asyncio.Task | None = None
    if settings.backfill_ops_worker_enabled:
        stop_event = asyncio.Event()
        worker_task = asyncio.create_task(
            ops_queue.worker_loop(stop_event=stop_event),
            name="backfill-ops-worker",
        )
        app.state.ops_worker_stop_event = stop_event
        app.state.ops_worker_task = worker_task
    try:
        yield
    finally:
        if stop_event is not None:
            stop_event.set()
        if worker_task is not None:
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task


app = FastAPI(
    title="Backfill",
    description="Autonomous coverage infrastructure for hourly labor — powered by Retell AI",
    version="0.1.0",
    lifespan=lifespan,
)

if settings.backfill_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backfill_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


app.include_router(api_router)
app.include_router(web_router)
app.include_router(retell_router)
app.include_router(scheduling_router)
app.include_router(twilio_router)
