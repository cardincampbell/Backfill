from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, status

from app.api.deps import SessionDep
from app.config import settings
from app.schemas.internal import (
    FeedProjectionProcessResponse,
    FeedProjectionRebuildResponse,
    OfferExpiryResponse,
    OutboxProcessResponse,
    ProjectionStatus,
    SchedulerSyncProcessResponse,
    WebhookProcessResponse,
    WorkerBatchRequest,
)
from app.schemas.ops import ProviderCallbackLogRead
from app.services import (
    coverage_runtime,
    delivery,
    feed_projections,
    provider_callbacks,
    runtime_orchestration,
    scheduler_sync,
    webhooks,
)

router = APIRouter(prefix="/internal", tags=["internal"])


def _assert_worker_key(x_backfill_worker_key: str | None) -> None:
    if not settings.worker_api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="worker_api_key_not_configured")
    if x_backfill_worker_key != settings.worker_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="worker_auth_failed")


@router.post("/coverage/outbox/process", response_model=OutboxProcessResponse)
async def process_coverage_outbox(
    payload: WorkerBatchRequest,
    session: SessionDep,
    x_backfill_worker_key: str | None = Header(default=None),
):
    _assert_worker_key(x_backfill_worker_key)
    return await delivery.process_outbox_batch(session, limit=payload.limit)


@router.post("/coverage/offers/expire", response_model=OfferExpiryResponse)
async def expire_coverage_offers(
    payload: WorkerBatchRequest,
    session: SessionDep,
    x_backfill_worker_key: str | None = Header(default=None),
):
    _assert_worker_key(x_backfill_worker_key)
    return await delivery.expire_due_offers(session, limit=payload.limit)


@router.post("/coverage/cases/process")
async def process_queued_coverage_cases(
    payload: WorkerBatchRequest,
    session: SessionDep,
    x_backfill_worker_key: str | None = Header(default=None),
):
    _assert_worker_key(x_backfill_worker_key)
    return await coverage_runtime.process_queued_coverage_cases(session, limit=payload.limit)


@router.post("/coverage/cases/reconcile")
async def reconcile_running_coverage_cases(
    payload: WorkerBatchRequest,
    session: SessionDep,
    x_backfill_worker_key: str | None = Header(default=None),
):
    _assert_worker_key(x_backfill_worker_key)
    return await coverage_runtime.reconcile_running_coverage_cases(session, limit=payload.limit)


@router.post("/coverage/runtime/process")
async def process_coverage_runtime(
    payload: WorkerBatchRequest,
    session: SessionDep,
    x_backfill_worker_key: str | None = Header(default=None),
):
    _assert_worker_key(x_backfill_worker_key)
    return await coverage_runtime.process_coverage_runtime_batch(session, limit=payload.limit)


@router.post("/runtime/tick")
async def process_runtime_tick(
    payload: WorkerBatchRequest,
    session: SessionDep,
    x_backfill_worker_key: str | None = Header(default=None),
):
    _assert_worker_key(x_backfill_worker_key)
    return await runtime_orchestration.process_runtime_tick(session, limit=payload.limit)


@router.post("/feed/projections/process", response_model=FeedProjectionProcessResponse)
async def process_feed_projection_batch(
    payload: WorkerBatchRequest,
    session: SessionDep,
    x_backfill_worker_key: str | None = Header(default=None),
):
    _assert_worker_key(x_backfill_worker_key)
    return await feed_projections.process_feed_projection_batch(session, limit=payload.limit)


@router.post("/feed/projections/rebuild", response_model=FeedProjectionRebuildResponse)
async def rebuild_feed_projection(
    payload: WorkerBatchRequest,
    session: SessionDep,
    x_backfill_worker_key: str | None = Header(default=None),
):
    _assert_worker_key(x_backfill_worker_key)
    return await feed_projections.rebuild_feed_projection(session, limit=payload.limit)


@router.get("/projections/status", response_model=list[ProjectionStatus])
async def get_projection_status(
    session: SessionDep,
    x_backfill_worker_key: str | None = Header(default=None),
):
    _assert_worker_key(x_backfill_worker_key)
    cursors = await feed_projections.get_all_projection_cursors(session)
    return [
        ProjectionStatus(
            projection_name=c.projection_name,
            schema_version=c.schema_version,
            last_source_created_at=c.last_source_created_at,
            last_source_event_id=c.last_source_event_id,
            cursor_status=c.cursor_status,
            last_run_started_at=c.last_run_started_at,
            last_run_completed_at=c.last_run_completed_at,
            last_error=c.last_error,
            cursor_metadata=c.cursor_metadata,
        )
        for c in cursors
    ]


@router.post("/providers/callbacks/process")
async def process_provider_callbacks(
    payload: WorkerBatchRequest,
    session: SessionDep,
    x_backfill_worker_key: str | None = Header(default=None),
):
    _assert_worker_key(x_backfill_worker_key)
    return await provider_callbacks.process_callback_batch(session, limit=payload.limit)


@router.get("/providers/callbacks", response_model=list[ProviderCallbackLogRead])
async def list_provider_callback_logs(
    session: SessionDep,
    x_backfill_worker_key: str | None = Header(default=None),
    provider: str | None = None,
    route_key: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    event_type: str | None = None,
    provider_event_id: str | None = None,
    dedupe_key: str | None = None,
    limit: int = Query(default=50, ge=1, le=250),
):
    _assert_worker_key(x_backfill_worker_key)
    rows = await provider_callbacks.list_callback_logs(
        session,
        provider=provider,
        route_key=route_key,
        status=status_filter,
        event_type=event_type,
        provider_event_id=provider_event_id,
        dedupe_key=dedupe_key,
        limit=limit,
    )
    return [ProviderCallbackLogRead.model_validate(row) for row in rows]


@router.get("/providers/callbacks/{callback_log_id}", response_model=ProviderCallbackLogRead)
async def get_provider_callback_log(
    callback_log_id: UUID,
    session: SessionDep,
    x_backfill_worker_key: str | None = Header(default=None),
):
    _assert_worker_key(x_backfill_worker_key)
    row = await provider_callbacks.get_callback_log(
        session,
        callback_log_id=callback_log_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="provider_callback_log_not_found")
    return ProviderCallbackLogRead.model_validate(row)


@router.post("/webhooks/process", response_model=WebhookProcessResponse)
async def process_webhook_outbox(
    payload: WorkerBatchRequest,
    session: SessionDep,
    x_backfill_worker_key: str | None = Header(default=None),
):
    _assert_worker_key(x_backfill_worker_key)
    return await webhooks.process_outbox_batch(session, limit=payload.limit)


@router.post("/schedulers/process", response_model=SchedulerSyncProcessResponse)
async def process_scheduler_jobs(
    payload: WorkerBatchRequest,
    session: SessionDep,
    x_backfill_worker_key: str | None = Header(default=None),
):
    _assert_worker_key(x_backfill_worker_key)
    results = await scheduler_sync.process_due_sync_jobs(session, limit=payload.limit)
    return SchedulerSyncProcessResponse(
        claimed_count=len(results),
        completed_count=sum(1 for item in results if item.get("status") == "completed"),
        failed_count=sum(1 for item in results if item.get("status") == "failed"),
        retrying_count=sum(1 for item in results if item.get("status") == "retrying"),
        processed_job_ids=[str(item["job_id"]) for item in results if item.get("job_id")],
    )
