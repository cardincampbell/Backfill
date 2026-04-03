from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import AuthDep, SessionDep
from app.models.common import MembershipRole
from app.schemas.audit import AuditLogRead
from app.services import audit as audit_service
from app.services import auth as auth_service

router = APIRouter(prefix="/businesses/{business_id}/audit-logs", tags=["audit"])
MANAGER_ROLES = {MembershipRole.owner, MembershipRole.admin, MembershipRole.manager}


@router.get("", response_model=list[AuditLogRead])
async def list_audit_logs(
    business_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    location_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=250),
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=403, detail="business_access_denied")
    return await audit_service.list_logs(
        session,
        business_id=business_id,
        location_id=location_id,
        limit=limit,
    )
