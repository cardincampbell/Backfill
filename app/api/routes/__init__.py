from app.api.routes.account import router as account_router
from app.api.routes.audit import router as audit_router
from app.api.routes.auth import router as auth_router
from app.api.routes.businesses import router as businesses_router
from app.api.routes.coverage import router as coverage_router
from app.api.routes.identity import router as identity_router
from app.api.routes.internal import router as internal_router
from app.api.routes.invites import router as invites_router
from app.api.routes.onboarding import router as onboarding_router
from app.api.routes.places import places_router
from app.api.routes.providers import router as providers_router
from app.api.routes.retell_provider import router as retell_provider_router
from app.api.routes.scheduler_integrations import router as scheduler_integrations_router
from app.api.routes.scheduler_provider_webhooks import router as scheduler_provider_webhooks_router
from app.api.routes.scheduling import router as scheduling_router
from app.api.routes.workspace import router as workspace_router
from app.api.routes.webhooks import router as webhooks_router
from app.api.routes.workforce import router as workforce_router

__all__ = [
    "account_router",
    "audit_router",
    "auth_router",
    "businesses_router",
    "coverage_router",
    "identity_router",
    "internal_router",
    "invites_router",
    "onboarding_router",
    "places_router",
    "providers_router",
    "retell_provider_router",
    "scheduler_integrations_router",
    "scheduler_provider_webhooks_router",
    "scheduling_router",
    "workspace_router",
    "webhooks_router",
    "workforce_router",
]
