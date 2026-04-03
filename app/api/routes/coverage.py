from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import AuthDep, SessionDep
from app.models.common import AuditActorType, MembershipRole
from app.schemas.coverage import (
    CoverageExecutionDecision,
    CoverageExecutionDispatchRequest,
    CoverageExecutionDispatchResult,
    CoverageOfferActionResult,
    CoverageOfferResponseCreate,
    CoverageCaseCreate,
    CoverageCaseRead,
    Phase1CoveragePreview,
    Phase1ExecutionRequest,
    Phase1ExecutionResult,
    Phase2CoveragePreview,
    Phase2ExecutionRequest,
    Phase2ExecutionResult,
)
from app.services import audit as audit_service
from app.services import auth as auth_service, coverage

router = APIRouter(prefix="/businesses/{business_id}/coverage-cases", tags=["coverage"])
MANAGER_ROLES = {MembershipRole.owner, MembershipRole.admin, MembershipRole.manager}


@router.get("", response_model=list[CoverageCaseRead])
async def list_coverage_cases(business_id: UUID, session: SessionDep, auth_ctx: AuthDep):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    return await coverage.list_coverage_cases(session, business_id)


@router.post("", response_model=CoverageCaseRead, status_code=status.HTTP_201_CREATED)
async def create_coverage_case(
    business_id: UUID,
    payload: CoverageCaseCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        coverage_case = await coverage.create_coverage_case(session, business_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=coverage_case.location_id)
    await audit_service.append(
        session,
        event_name="coverage.case.created",
        target_type="coverage_case",
        target_id=coverage_case.id,
        business_id=business_id,
        location_id=coverage_case.location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={"shift_id": str(coverage_case.shift_id), "phase_target": coverage_case.phase_target},
    )
    await session.commit()
    return coverage_case


@router.get("/{coverage_case_id}/plan", response_model=CoverageExecutionDecision)
async def plan_coverage_execution(
    business_id: UUID,
    coverage_case_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        return await coverage.plan_coverage_case_execution(session, business_id, coverage_case_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/preview/phase-1/{shift_id}", response_model=Phase1CoveragePreview)
async def preview_phase_1_candidates(business_id: UUID, shift_id: UUID, session: SessionDep, auth_ctx: AuthDep):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        return await coverage.preview_phase_1_candidates(session, business_id, shift_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/preview/phase-2/{shift_id}", response_model=Phase2CoveragePreview)
async def preview_phase_2_candidates(business_id: UUID, shift_id: UUID, session: SessionDep, auth_ctx: AuthDep):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        return await coverage.preview_phase_2_candidates(session, business_id, shift_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{coverage_case_id}/execute/phase-1", response_model=Phase1ExecutionResult)
async def execute_phase_1_run(
    business_id: UUID,
    coverage_case_id: UUID,
    payload: Phase1ExecutionRequest,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        result = await coverage.execute_phase_1_run(session, business_id, coverage_case_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=result.coverage_case.location_id)
    await audit_service.append(
        session,
        event_name="coverage.phase_1.executed",
        target_type="coverage_case_run",
        target_id=result.run.id,
        business_id=business_id,
        location_id=result.coverage_case.location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={
            "coverage_case_id": str(result.coverage_case.id),
            "candidate_count": result.candidate_count,
            "offer_count": len(result.offers),
        },
    )
    await session.commit()
    return result


@router.post("/{coverage_case_id}/execute/phase-2", response_model=Phase2ExecutionResult)
async def execute_phase_2_run(
    business_id: UUID,
    coverage_case_id: UUID,
    payload: Phase2ExecutionRequest,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        result = await coverage.execute_phase_2_run(session, business_id, coverage_case_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=result.coverage_case.location_id)
    await audit_service.append(
        session,
        event_name="coverage.phase_2.executed",
        target_type="coverage_case_run",
        target_id=result.run.id,
        business_id=business_id,
        location_id=result.coverage_case.location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={
            "coverage_case_id": str(result.coverage_case.id),
            "candidate_count": result.candidate_count,
            "offer_count": len(result.offers),
        },
    )
    await session.commit()
    return result


@router.post("/{coverage_case_id}/execute", response_model=CoverageExecutionDispatchResult)
async def execute_next_coverage_phase(
    business_id: UUID,
    coverage_case_id: UUID,
    payload: CoverageExecutionDispatchRequest,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        result = await coverage.execute_next_coverage_phase(session, business_id, coverage_case_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(
        auth_ctx,
        business_id,
        location_id=result.coverage_case.location_id,
    )
    await audit_service.append(
        session,
        event_name="coverage.dispatch.executed",
        target_type="coverage_case",
        target_id=result.coverage_case.id,
        business_id=business_id,
        location_id=result.coverage_case.location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={
            "phase_executed": result.phase_executed,
            "recommended_phase": result.decision.recommended_phase,
            "recommendation_reason": result.decision.recommendation_reason,
            "candidate_count": result.candidate_count,
            "offer_count": len(result.offers),
        },
    )
    await session.commit()
    return result


@router.post("/offers/{offer_id}/respond", response_model=CoverageOfferActionResult)
async def respond_to_offer(
    business_id: UUID,
    offer_id: UUID,
    payload: CoverageOfferResponseCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        result = await coverage.respond_to_offer(session, business_id, offer_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=result.coverage_case.location_id)
    await audit_service.append(
        session,
        event_name=f"coverage.offer.{payload.response.strip().lower()}",
        target_type="coverage_offer",
        target_id=result.offer.id,
        business_id=business_id,
        location_id=result.coverage_case.location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={
            "coverage_case_id": str(result.coverage_case.id),
            "shift_id": str(result.shift_id),
            "assignment_id": str(result.assignment_id) if result.assignment_id is not None else None,
        },
    )
    await session.commit()
    return result
