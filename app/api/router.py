from __future__ import annotations

from fastapi import APIRouter

from app.config import settings
from app.api.routes import (
    account_router,
    audit_router,
    auth_router,
    businesses_router,
    coverage_router,
    identity_router,
    internal_router,
    invites_router,
    onboarding_router,
    places_router,
    providers_router,
    retell_provider_router,
    scheduler_integrations_router,
    scheduler_provider_webhooks_router,
    scheduling_router,
    workspace_router,
    webhooks_router,
    workforce_router,
)

router = APIRouter(prefix=settings.api_prefix, tags=["api"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/meta")
async def meta() -> dict[str, str]:
    return {
        "environment": settings.environment,
        "database_backend": "postgresql",
        "api_prefix": settings.api_prefix,
    }


router.include_router(identity_router)
router.include_router(auth_router)
router.include_router(account_router)
router.include_router(internal_router)
router.include_router(invites_router)
router.include_router(onboarding_router)
router.include_router(places_router)
router.include_router(providers_router)
router.include_router(retell_provider_router)
router.include_router(scheduler_integrations_router)
router.include_router(scheduler_provider_webhooks_router)
router.include_router(workspace_router)
router.include_router(audit_router)
router.include_router(businesses_router)
router.include_router(webhooks_router)
router.include_router(workforce_router)
router.include_router(scheduling_router)
router.include_router(coverage_router)
