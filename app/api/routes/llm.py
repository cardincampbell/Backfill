from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.api.deps import AuthDep, SessionDep
from app.models.common import MembershipRole
from app.schemas.llm import LlmGenerationDetailRead, LlmGenerationSummaryRead
from app.services import auth as auth_service
from app.services import llm_gateway

router = APIRouter(prefix="/businesses/{business_id}/llm-generations", tags=["llm"])
MANAGER_ROLES = {MembershipRole.owner, MembershipRole.admin, MembershipRole.manager}


@router.get("", response_model=list[LlmGenerationSummaryRead])
async def list_llm_generations(
    business_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    location_id: UUID | None = None,
    purpose: str | None = None,
    provider: str | None = None,
    trace_id: str | None = None,
    limit: int = 50,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=403, detail="business_access_denied")

    rows = await llm_gateway.list_generations(
        session,
        business_id=business_id,
        location_id=location_id,
        purpose=purpose,
        provider=provider,
        trace_id=trace_id,
        limit=limit,
    )
    return [LlmGenerationSummaryRead.model_validate(row) for row in rows]


@router.get("/{generation_id}", response_model=LlmGenerationDetailRead)
async def get_llm_generation(
    business_id: UUID,
    generation_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=403, detail="business_access_denied")

    row = await llm_gateway.get_generation(
        session,
        business_id=business_id,
        generation_id=generation_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="llm_generation_not_found")
    return LlmGenerationDetailRead.model_validate(row)
