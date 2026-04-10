from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import AuthDep, SessionDep
from app.models.common import MembershipRole
from app.schemas.events import PlatformEventRead
from app.schemas.finance import BillingLedgerEntryRead, CostLedgerEntryRead
from app.schemas.llm import LlmGenerationSummaryRead
from app.schemas.ops import BusinessTraceRead
from app.services import auth as auth_service
from app.services import ops_reporting

router = APIRouter(prefix="/businesses/{business_id}/ops", tags=["ops"])
MANAGER_ROLES = {MembershipRole.owner, MembershipRole.admin, MembershipRole.manager}


@router.get("/traces/{trace_id}", response_model=BusinessTraceRead)
async def get_trace_report(
    business_id: UUID,
    trace_id: str,
    session: SessionDep,
    auth_ctx: AuthDep,
    location_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=403, detail="business_access_denied")

    report = await ops_reporting.trace_report(
        session,
        business_id=business_id,
        trace_id=trace_id,
        location_id=location_id,
        limit=limit,
    )
    return BusinessTraceRead(
        trace_id=report.trace_id,
        platform_event_count=len(report.platform_events),
        llm_generation_count=len(report.llm_generations),
        cost_entry_count=len(report.cost_entries),
        billing_entry_count=len(report.billing_entries),
        total_cost_micros=report.total_cost_micros,
        total_billed_cents=report.total_billed_cents,
        platform_events=[PlatformEventRead.model_validate(item) for item in report.platform_events],
        llm_generations=[
            LlmGenerationSummaryRead.model_validate(item) for item in report.llm_generations
        ],
        cost_entries=[CostLedgerEntryRead.model_validate(item) for item in report.cost_entries],
        billing_entries=[
            BillingLedgerEntryRead.model_validate(item) for item in report.billing_entries
        ],
    )
