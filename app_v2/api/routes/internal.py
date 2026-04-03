from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, status

from app_v2.api.deps import SessionDep
from app_v2.config import v2_settings
from app_v2.schemas.internal import (
    OfferExpiryResponse,
    OutboxProcessResponse,
    SchedulerSyncProcessResponse,
    WebhookProcessResponse,
    WorkerBatchRequest,
)
from app_v2.services import delivery, scheduler_sync, webhooks

router = APIRouter(prefix="/internal", tags=["v2-internal"])


def _assert_worker_key(x_backfill_worker_key: str | None) -> None:
    if not v2_settings.worker_api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="worker_api_key_not_configured")
    if x_backfill_worker_key != v2_settings.worker_api_key:
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
