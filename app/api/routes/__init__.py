from app.api.routes.account import router as account_router
from app.api.routes.calendar_feeds import router as calendar_feeds_router
from app.api.routes.audit import router as audit_router
from app.api.routes.auth import router as auth_router
from app.api.routes.businesses import router as businesses_router
from app.api.routes.communications import router as communications_router
from app.api.routes.copilot import router as copilot_router
from app.api.routes.coverage import router as coverage_router
from app.api.routes.employee_schedules import router as employee_schedules_router
from app.api.routes.events import router as events_router
from app.api.routes.finance import router as finance_router
from app.api.routes.identity import router as identity_router
from app.api.routes.internal import router as internal_router
from app.api.routes.llm import router as llm_router
from app.api.routes.migrations import router as migrations_router
from app.api.routes.invites import router as invites_router
from app.api.routes.onboarding import router as onboarding_router
from app.api.routes.ops import router as ops_router
from app.api.routes.places import places_router
from app.api.routes.providers import router as providers_router
from app.api.routes.realtime import router as realtime_router
from app.api.routes.retell_provider import router as retell_provider_router
from app.api.routes.scheduler_integrations import router as scheduler_integrations_router
from app.api.routes.scheduler_provider_webhooks import router as scheduler_provider_webhooks_router
from app.api.routes.scheduling import router as scheduling_router
from app.api.routes.weather import router as weather_router
from app.api.routes.workspace import router as workspace_router
from app.api.routes.webhooks import router as webhooks_router
from app.api.routes.workforce import router as workforce_router

__all__ = [
    "account_router",
    "calendar_feeds_router",
    "audit_router",
    "auth_router",
    "businesses_router",
    "communications_router",
    "copilot_router",
    "coverage_router",
    "employee_schedules_router",
    "events_router",
    "finance_router",
    "identity_router",
    "internal_router",
    "llm_router",
    "migrations_router",
    "invites_router",
    "onboarding_router",
    "ops_router",
    "places_router",
    "providers_router",
    "realtime_router",
    "retell_provider_router",
    "scheduler_integrations_router",
    "scheduler_provider_webhooks_router",
    "scheduling_router",
    "weather_router",
    "workspace_router",
    "webhooks_router",
    "workforce_router",
]
