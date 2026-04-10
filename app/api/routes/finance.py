from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.api.deps import AuthDep, SessionDep
from app.models.business import Location
from app.models.common import MembershipRole
from app.models.coverage import CoverageCase
from app.schemas.finance import (
    BillingLedgerEntryRead,
    CampaignCostBreakdownRead,
    CampaignEconomicsRead,
    CostLedgerEntryRead,
    LocationBillingCapRead,
)
from app.services import auth as auth_service
from app.services import finance_reporting

router = APIRouter(prefix="/businesses/{business_id}/locations/{location_id}/finance", tags=["finance"])
MANAGER_ROLES = {MembershipRole.owner, MembershipRole.admin, MembershipRole.manager}


async def _load_location_or_404(
    session: SessionDep,
    *,
    business_id: UUID,
    location_id: UUID,
) -> Location:
    location = await session.get(Location, location_id)
    if location is None or location.business_id != business_id:
        raise HTTPException(status_code=404, detail="location_not_found")
    return location


async def _load_coverage_case_or_404(
    session: SessionDep,
    *,
    location_id: UUID,
    coverage_case_id: UUID,
) -> CoverageCase:
    coverage_case = await session.get(CoverageCase, coverage_case_id)
    if coverage_case is None or coverage_case.location_id != location_id:
        raise HTTPException(status_code=404, detail="coverage_case_not_found")
    return coverage_case


@router.get("/billing-cap", response_model=LocationBillingCapRead)
async def get_location_billing_cap(
    business_id: UUID,
    location_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    occurred_at: datetime | None = None,
):
    if not auth_service.has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=MANAGER_ROLES,
    ):
        raise HTTPException(status_code=403, detail="location_access_denied")

    location = await _load_location_or_404(
        session,
        business_id=business_id,
        location_id=location_id,
    )
    snapshot = await finance_reporting.location_billing_cap_snapshot(
        session,
        location_id=location_id,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        timezone_name=location.timezone,
    )
    return LocationBillingCapRead.model_validate(snapshot)


@router.get("/coverage-cases/{coverage_case_id}/economics", response_model=CampaignEconomicsRead)
async def get_campaign_economics(
    business_id: UUID,
    location_id: UUID,
    coverage_case_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=MANAGER_ROLES,
    ):
        raise HTTPException(status_code=403, detail="location_access_denied")

    await _load_location_or_404(
        session,
        business_id=business_id,
        location_id=location_id,
    )
    await _load_coverage_case_or_404(
        session,
        location_id=location_id,
        coverage_case_id=coverage_case_id,
    )

    snapshot = await finance_reporting.campaign_economics_snapshot(session, coverage_case_id)
    breakdown = await finance_reporting.campaign_cost_breakdown(session, coverage_case_id)
    return CampaignEconomicsRead(
        coverage_case_id=snapshot.coverage_case_id,
        total_cost_micros=snapshot.total_cost_micros,
        total_cost_cents_rounded=snapshot.total_cost_cents_rounded,
        total_billed_cents=snapshot.total_billed_cents,
        total_billed_micros=snapshot.total_billed_micros,
        gross_margin_micros=snapshot.gross_margin_micros,
        gross_margin_cents_rounded=snapshot.gross_margin_cents_rounded,
        billed_entry_count=snapshot.billed_entry_count,
        cost_entry_count=snapshot.cost_entry_count,
        cost_breakdown=[CampaignCostBreakdownRead.model_validate(item) for item in breakdown],
    )


@router.get(
    "/coverage-cases/{coverage_case_id}/cost-entries",
    response_model=list[CostLedgerEntryRead],
)
async def list_campaign_cost_entries(
    business_id: UUID,
    location_id: UUID,
    coverage_case_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    limit: int = 50,
):
    if not auth_service.has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=MANAGER_ROLES,
    ):
        raise HTTPException(status_code=403, detail="location_access_denied")

    await _load_location_or_404(
        session,
        business_id=business_id,
        location_id=location_id,
    )
    await _load_coverage_case_or_404(
        session,
        location_id=location_id,
        coverage_case_id=coverage_case_id,
    )
    entries = await finance_reporting.list_cost_entries(
        session,
        coverage_case_id=coverage_case_id,
        limit=limit,
    )
    return [CostLedgerEntryRead.model_validate(item) for item in entries]


@router.get(
    "/coverage-cases/{coverage_case_id}/billing-entries",
    response_model=list[BillingLedgerEntryRead],
)
async def list_campaign_billing_entries(
    business_id: UUID,
    location_id: UUID,
    coverage_case_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    limit: int = 50,
):
    if not auth_service.has_location_access(
        auth_ctx,
        business_id,
        location_id,
        allowed_roles=MANAGER_ROLES,
    ):
        raise HTTPException(status_code=403, detail="location_access_denied")

    await _load_location_or_404(
        session,
        business_id=business_id,
        location_id=location_id,
    )
    await _load_coverage_case_or_404(
        session,
        location_id=location_id,
        coverage_case_id=coverage_case_id,
    )
    entries = await finance_reporting.list_billing_entries(
        session,
        coverage_case_id=coverage_case_id,
        limit=limit,
    )
    return [BillingLedgerEntryRead.model_validate(item) for item in entries]
