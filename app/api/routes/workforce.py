from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AuthDep, SessionDep
from app.models.common import AuditActorType, MembershipRole
from app.schemas.workforce import (
    EmployeeAvailabilityRuleCreate,
    EmployeeAvailabilityRuleRead,
    EmployeeCreate,
    EmployeeEnrollAtLocationCreate,
    EmployeeEnrollmentRead,
    EmployeeLocationClearanceCreate,
    EmployeeLocationClearanceRead,
    EmployeeRead,
    EmployeeRoleCreate,
    EmployeeRoleRead,
)
from app.services import audit as audit_service
from app.services import auth as auth_service, workforce

router = APIRouter(prefix="/businesses/{business_id}/employees", tags=["workforce"])
MANAGER_ROLES = {MembershipRole.owner, MembershipRole.admin, MembershipRole.manager}
ADMIN_ROLES = {MembershipRole.owner, MembershipRole.admin}


@router.get("", response_model=list[EmployeeRead])
async def list_employees(business_id: UUID, session: SessionDep, auth_ctx: AuthDep):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    return await workforce.list_employees(session, business_id)


@router.post("", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
async def create_employee(business_id: UUID, payload: EmployeeCreate, session: SessionDep, auth_ctx: AuthDep):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        employee = await workforce.create_employee(session, business_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return employee


@router.post("/enroll", response_model=EmployeeEnrollmentRead, status_code=status.HTTP_201_CREATED)
async def enroll_employee_at_location(
    business_id: UUID,
    payload: EmployeeEnrollAtLocationCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        result = await workforce.enroll_employee_at_location(session, business_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    membership = auth_service.membership_for_scope(auth_ctx, business_id, location_id=payload.location_id)
    await audit_service.append(
        session,
        event_name="employee.enrolled",
        target_type="employee",
        target_id=result.employee.id,
        business_id=business_id,
        location_id=payload.location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        payload={
            "role_ids": [str(role.id) for role in result.roles],
            "home_location_id": str(payload.location_id),
        },
    )
    await session.commit()
    return result


@router.post("/{employee_id}/roles", response_model=EmployeeRoleRead, status_code=status.HTTP_201_CREATED)
async def add_employee_role(
    business_id: UUID,
    employee_id: UUID,
    payload: EmployeeRoleCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        role = await workforce.add_employee_role(session, business_id, employee_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return role


@router.post(
    "/{employee_id}/clearances",
    response_model=EmployeeLocationClearanceRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_employee_clearance(
    business_id: UUID,
    employee_id: UUID,
    payload: EmployeeLocationClearanceCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        clearance = await workforce.add_employee_location_clearance(session, business_id, employee_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return clearance


@router.post(
    "/{employee_id}/availability-rules",
    response_model=EmployeeAvailabilityRuleRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_employee_availability_rule(
    business_id: UUID,
    employee_id: UUID,
    payload: EmployeeAvailabilityRuleCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        rule = await workforce.add_employee_availability_rule(session, business_id, employee_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return rule
