from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Header, HTTPException, status

from app.bootstrap import run_migrations_with_advisory_lock
from app.config import settings
from app.schemas.common import BaseSchema

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/migrations", tags=["internal"])


class MigrationRunResponse(BaseSchema):
    status: str
    message: str


def _assert_worker_key(x_backfill_worker_key: str | None) -> None:
    if not settings.worker_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="worker_api_key_not_configured",
        )
    if x_backfill_worker_key != settings.worker_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="worker_auth_failed",
        )


@router.post("/run", response_model=MigrationRunResponse)
async def run_migrations(
    x_backfill_worker_key: str | None = Header(default=None),
) -> MigrationRunResponse:
    _assert_worker_key(x_backfill_worker_key)
    try:
        await asyncio.to_thread(run_migrations_with_advisory_lock)
    except Exception as exc:
        logger.exception("Migration run failed via /internal/migrations/run")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Migration failed: {exc.__class__.__name__}: {exc}",
        ) from exc
    return MigrationRunResponse(
        status="ok",
        message="Migrations applied successfully",
    )
