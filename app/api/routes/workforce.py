from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from app.api.deps import AuthDep, SessionDep
from app.models.common import AuditActorType, MembershipRole
from app.schemas.workforce import (
    EmployeeAvailabilityRuleCreate,
    EmployeeAvailabilityRuleRead,
    EmployeeAvailabilityRuleReplace,
    EmployeeBulkImportRead,
    EmployeeCreate,
    EmployeeEnrollAtLocationCreate,
    EmployeeEnrollmentRead,
    EmployeeLocationCreate,
    EmployeeLocationRead,
    EmployeeProfileRead,
    EmployeeRead,
    EmployeeRoleCreate,
    EmployeeRoleRead,
    SelfEmployeeAvailabilityRead,
    EmployeeUpdate,
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


@router.get("/{employee_id}", response_model=EmployeeProfileRead)
async def get_employee_profile(
    business_id: UUID,
    employee_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=MANAGER_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        return await workforce.get_employee_profile(session, business_id, employee_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
async def create_employee(business_id: UUID, payload: EmployeeCreate, session: SessionDep, auth_ctx: AuthDep):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        employee = await workforce.create_employee(session, business_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    membership = auth_service.membership_for_scope(auth_ctx, business_id)
    await audit_service.append(
        session,
        event_name="employee.created",
        target_type="employee",
        target_id=employee.id,
        business_id=business_id,
        location_id=employee.primary_location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        payload={
            "primary_location_id": str(employee.primary_location_id)
            if employee.primary_location_id is not None
            else None,
        },
    )
    await session.commit()
    return employee


@router.get("/import/template")
async def download_employee_import_template(
    business_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        content = workforce.build_employee_import_template()
    except RuntimeError as exc:
        if str(exc) == "employee_import_xlsx_dependency_missing":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        raise

    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="backfill-employee-roster-template.xlsx"',
        },
    )


@router.post("/import", response_model=EmployeeBulkImportRead)
async def bulk_import_employees(
    business_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    file: UploadFile = File(...),
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        result = await workforce.bulk_import_employees(
            session,
            business_id,
            filename=file.filename or "",
            content=await file.read(),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        if str(exc) == "employee_import_xlsx_dependency_missing":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        raise

    membership = auth_service.membership_for_scope(auth_ctx, business_id)
    await audit_service.append(
        session,
        event_name="employee.bulk_imported",
        target_type="business",
        target_id=business_id,
        business_id=business_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        payload={
            "file_name": file.filename,
            "created_count": result.created_count,
            "skipped_count": result.skipped_count,
            "default_location_id": str(result.default_location_id)
            if result.default_location_id is not None
            else None,
        },
    )
    await session.commit()
    return result


@router.patch("/{employee_id}", response_model=EmployeeProfileRead)
async def update_employee(
    business_id: UUID,
    employee_id: UUID,
    payload: EmployeeUpdate,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        employee = await workforce.update_employee(session, business_id, employee_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    membership = auth_service.membership_for_scope(auth_ctx, business_id)
    await audit_service.append(
        session,
        event_name="employee.updated",
        target_type="employee",
        target_id=employee_id,
        business_id=business_id,
        location_id=employee.primary_location_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        payload={
            "updated_fields": sorted(payload.model_fields_set),
            "role_ids": [str(role_id) for role_id in employee.role_ids],
            "location_ids": [str(location_id) for location_id in employee.location_ids],
        },
    )
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
            "primary_location_id": str(payload.location_id),
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
    "/{employee_id}/locations",
    response_model=EmployeeLocationRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_employee_location(
    business_id: UUID,
    employee_id: UUID,
    payload: EmployeeLocationCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    try:
        employee_location = await workforce.add_employee_location(
            session,
            business_id,
            employee_id,
            payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return employee_location


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


@router.get(
    "/availability-rules/self",
    response_model=SelfEmployeeAvailabilityRead,
)
async def get_self_employee_availability_rules(
    business_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        employee, rules = await workforce.get_self_employee_availability_rules(
            session,
            business_id,
            user_id=auth_ctx.user.id,
            email=auth_ctx.user.email,
            phone_e164=auth_ctx.user.primary_phone_e164,
            full_name=auth_ctx.user.full_name,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    timezone = rules[0].timezone if rules else "UTC"
    return SelfEmployeeAvailabilityRead(
        employee_id=employee.id,
        employee_name=employee.preferred_name or employee.full_name,
        timezone=timezone,
        rules=rules,
    )


@router.put(
    "/availability-rules/self",
    response_model=SelfEmployeeAvailabilityRead,
)
async def replace_self_employee_availability_rules(
    business_id: UUID,
    payload: EmployeeAvailabilityRuleReplace,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_access_denied")
    try:
        employee, rules = await workforce.replace_self_employee_availability_rules(
            session,
            business_id,
            user_id=auth_ctx.user.id,
            email=auth_ctx.user.email,
            phone_e164=auth_ctx.user.primary_phone_e164,
            full_name=auth_ctx.user.full_name,
            payload=payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    timezone = rules[0].timezone if rules else "UTC"
    return SelfEmployeeAvailabilityRead(
        employee_id=employee.id,
        employee_name=employee.preferred_name or employee.full_name,
        timezone=timezone,
        rules=rules,
    )
