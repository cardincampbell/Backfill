from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import AuthDep, SessionDep
from app.models.common import AuditActorType, MembershipRole
from app.schemas.coverage import (
    CoverageCampaignCreate,
    CoverageCampaignDispatchRequest,
    CoverageCampaignDispatchResult,
    CoverageCampaignExecutionDecision,
    CoverageCampaignRead,
    CoverageOfferActionResult,
    CoverageOutreachAttemptRead,
    CoverageOfferResponseCreate,
    Phase1CoveragePreview,
    Phase1ExecutionRequest,
    Phase1ExecutionResult,
    Phase2CoveragePreview,
    Phase2ExecutionRequest,
    Phase2ExecutionResult,
)
from app.services import audit as audit_service
from app.services import auth as auth_service, coverage, outreach as outreach_service
from app.services import platform_events

router = APIRouter(tags=["coverage"])
MANAGER_ROLES = {MembershipRole.owner, MembershipRole.admin, MembershipRole.manager}
CAMPAIGN_PREFIX = "/businesses/{business_id}/coverage-campaigns"
LEGACY_PREFIX = "/businesses/{business_id}/coverage-cases"


def _ensure_manager_access(auth_ctx: AuthDep, business_id: UUID) -> None:
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")


@router.get(f"{CAMPAIGN_PREFIX}", response_model=list[CoverageCampaignRead])
@router.get(f"{LEGACY_PREFIX}", response_model=list[CoverageCampaignRead], include_in_schema=False)
async def list_campaigns(business_id: UUID, session: SessionDep, auth_ctx: AuthDep):
    _ensure_manager_access(auth_ctx, business_id)
    return await coverage.list_campaigns(session, business_id)


@router.get(f"{CAMPAIGN_PREFIX}/{{campaign_id}}/outreach-attempts", response_model=list[CoverageOutreachAttemptRead])
@router.get(
    f"{LEGACY_PREFIX}/{{campaign_id}}/outreach-attempts",
    response_model=list[CoverageOutreachAttemptRead],
    include_in_schema=False,
)
async def list_campaign_outreach_attempts(
    business_id: UUID,
    campaign_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    _ensure_manager_access(auth_ctx, business_id)
    try:
        return await outreach_service.list_campaign_outreach_attempts(
            session,
            business_id=business_id,
            campaign_id=campaign_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(f"{CAMPAIGN_PREFIX}", response_model=CoverageCampaignRead, status_code=status.HTTP_201_CREATED)
@router.post(
    f"{LEGACY_PREFIX}",
    response_model=CoverageCampaignRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_campaign(
    business_id: UUID,
    payload: CoverageCampaignCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    _ensure_manager_access(auth_ctx, business_id)
    try:
        campaign = await coverage.create_campaign(session, business_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=campaign.location_id)
    await platform_events.append(
        session,
        event_type=platform_events.PlatformEventType.COVERAGE_CAMPAIGN_CREATED,
        compatibility_event_name="coverage.case.created",
        target_type="coverage_case",
        target_id=campaign.id,
        business_id=business_id,
        location_id=campaign.location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={
            "campaign_id": str(campaign.id),
            "coverage_case_id": str(campaign.id),
            "shift_id": str(campaign.shift_id),
            "phase_target": campaign.phase_target,
        },
        metadata={"channel": "dashboard"},
    )
    await session.commit()
    return campaign


@router.get(f"{CAMPAIGN_PREFIX}/{{campaign_id}}/plan", response_model=CoverageCampaignExecutionDecision)
@router.get(
    f"{LEGACY_PREFIX}/{{campaign_id}}/plan",
    response_model=CoverageCampaignExecutionDecision,
    include_in_schema=False,
)
async def plan_campaign_execution(
    business_id: UUID,
    campaign_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    _ensure_manager_access(auth_ctx, business_id)
    try:
        return await coverage.plan_campaign_execution(session, business_id, campaign_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(f"{CAMPAIGN_PREFIX}/preview/phase-1/{{shift_id}}", response_model=Phase1CoveragePreview)
@router.post(
    f"{LEGACY_PREFIX}/preview/phase-1/{{shift_id}}",
    response_model=Phase1CoveragePreview,
    include_in_schema=False,
)
async def preview_phase_1_candidates(business_id: UUID, shift_id: UUID, session: SessionDep, auth_ctx: AuthDep):
    _ensure_manager_access(auth_ctx, business_id)
    try:
        return await coverage.preview_phase_1_candidates(session, business_id, shift_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(f"{CAMPAIGN_PREFIX}/preview/phase-2/{{shift_id}}", response_model=Phase2CoveragePreview)
@router.post(
    f"{LEGACY_PREFIX}/preview/phase-2/{{shift_id}}",
    response_model=Phase2CoveragePreview,
    include_in_schema=False,
)
async def preview_phase_2_candidates(business_id: UUID, shift_id: UUID, session: SessionDep, auth_ctx: AuthDep):
    _ensure_manager_access(auth_ctx, business_id)
    try:
        return await coverage.preview_phase_2_candidates(session, business_id, shift_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(f"{CAMPAIGN_PREFIX}/{{campaign_id}}/execute/phase-1", response_model=Phase1ExecutionResult)
@router.post(
    f"{LEGACY_PREFIX}/{{campaign_id}}/execute/phase-1",
    response_model=Phase1ExecutionResult,
    include_in_schema=False,
)
async def execute_phase_1_campaign_run(
    business_id: UUID,
    campaign_id: UUID,
    payload: Phase1ExecutionRequest,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    _ensure_manager_access(auth_ctx, business_id)
    try:
        result = await coverage.execute_phase_1_run(session, business_id, campaign_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=result.campaign.location_id)
    await platform_events.append(
        session,
        event_type=platform_events.PlatformEventType.COVERAGE_PHASE_1_EXECUTED,
        target_type="coverage_case_run",
        target_id=result.run.id,
        business_id=business_id,
        location_id=result.campaign.location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={
            "campaign_id": str(result.campaign.id),
            "coverage_case_id": str(result.campaign.id),
            "candidate_count": result.candidate_count,
            "offer_count": len(result.offers),
        },
        metadata={"channel": "dashboard"},
    )
    await session.commit()
    return result


@router.post(f"{CAMPAIGN_PREFIX}/{{campaign_id}}/execute/phase-2", response_model=Phase2ExecutionResult)
@router.post(
    f"{LEGACY_PREFIX}/{{campaign_id}}/execute/phase-2",
    response_model=Phase2ExecutionResult,
    include_in_schema=False,
)
async def execute_phase_2_campaign_run(
    business_id: UUID,
    campaign_id: UUID,
    payload: Phase2ExecutionRequest,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    _ensure_manager_access(auth_ctx, business_id)
    try:
        result = await coverage.execute_phase_2_run(session, business_id, campaign_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=result.campaign.location_id)
    await platform_events.append(
        session,
        event_type=platform_events.PlatformEventType.COVERAGE_PHASE_2_EXECUTED,
        target_type="coverage_case_run",
        target_id=result.run.id,
        business_id=business_id,
        location_id=result.campaign.location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={
            "campaign_id": str(result.campaign.id),
            "coverage_case_id": str(result.campaign.id),
            "candidate_count": result.candidate_count,
            "offer_count": len(result.offers),
        },
        metadata={"channel": "dashboard"},
    )
    await session.commit()
    return result


@router.post(f"{CAMPAIGN_PREFIX}/{{campaign_id}}/execute", response_model=CoverageCampaignDispatchResult)
@router.post(
    f"{LEGACY_PREFIX}/{{campaign_id}}/execute",
    response_model=CoverageCampaignDispatchResult,
    include_in_schema=False,
)
async def execute_campaign(
    business_id: UUID,
    campaign_id: UUID,
    payload: CoverageCampaignDispatchRequest,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    _ensure_manager_access(auth_ctx, business_id)
    try:
        result = await coverage.execute_next_campaign_phase(session, business_id, campaign_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=result.campaign.location_id)
    await platform_events.append(
        session,
        event_type=platform_events.PlatformEventType.COVERAGE_DISPATCH_EXECUTED,
        target_type="coverage_case",
        target_id=result.campaign.id,
        business_id=business_id,
        location_id=result.campaign.location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={
            "campaign_id": str(result.campaign.id),
            "coverage_case_id": str(result.campaign.id),
            "phase_executed": result.phase_executed,
            "recommended_phase": result.decision.recommended_phase,
            "recommendation_reason": result.decision.recommendation_reason,
            "candidate_count": result.candidate_count,
            "offer_count": len(result.offers),
        },
        metadata={"channel": "dashboard"},
    )
    await session.commit()
    return result


@router.post(f"{CAMPAIGN_PREFIX}/offers/{{offer_id}}/respond", response_model=CoverageOfferActionResult)
@router.post(
    f"{LEGACY_PREFIX}/offers/{{offer_id}}/respond",
    response_model=CoverageOfferActionResult,
    include_in_schema=False,
)
async def respond_to_offer(
    business_id: UUID,
    offer_id: UUID,
    payload: CoverageOfferResponseCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    _ensure_manager_access(auth_ctx, business_id)
    try:
        membership = auth_service.membership_for_scope(auth_ctx, business_id)
        result = await coverage.respond_to_offer(
            session,
            business_id,
            offer_id,
            payload,
            actor_type=AuditActorType.user,
            actor_user_id=auth_ctx.user.id,
            actor_membership_id=membership.id if membership is not None else None,
            ip_address=audit_service.request_client_ip(request),
            user_agent=audit_service.request_user_agent(request),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return result
