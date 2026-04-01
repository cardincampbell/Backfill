from app_v2.api.routes.audit import router as audit_router
from app_v2.api.routes.auth import router as auth_router
from app_v2.api.routes.businesses import router as businesses_router
from app_v2.api.routes.coverage import router as coverage_router
from app_v2.api.routes.identity import router as identity_router
from app_v2.api.routes.internal import router as internal_router
from app_v2.api.routes.invites import router as invites_router
from app_v2.api.routes.onboarding import router as onboarding_router
from app_v2.api.routes.places import legacy_places_router, places_router
from app_v2.api.routes.providers import router as providers_router
from app_v2.api.routes.scheduling import router as scheduling_router
from app_v2.api.routes.workspace import router as workspace_router
from app_v2.api.routes.workforce import router as workforce_router

__all__ = [
    "audit_router",
    "auth_router",
    "businesses_router",
    "coverage_router",
    "identity_router",
    "internal_router",
    "invites_router",
    "legacy_places_router",
    "onboarding_router",
    "places_router",
    "providers_router",
    "scheduling_router",
    "workspace_router",
    "workforce_router",
]
