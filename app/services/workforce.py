from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Business, Location, Role
from app.models.workforce import (
    Employee,
    EmployeeAvailabilityRule,
    EmployeeLocationClearance,
    EmployeeRole,
)
from app.schemas.workforce import (
    EmployeeEnrollAtLocationCreate,
    EmployeeAvailabilityRuleCreate,
    EmployeeCreate,
    EmployeeEnrollmentRead,
    EmployeeLocationClearanceCreate,
    EmployeeRoleCreate,
)
async def _require_business(session: AsyncSession, business_id: UUID) -> Business:
    business = await session.get(Business, business_id)
    if business is None:
        raise LookupError("business_not_found")
    return business


async def list_employees(session: AsyncSession, business_id: UUID) -> list[Employee]:
    result = await session.execute(
        select(Employee).where(Employee.business_id == business_id).order_by(Employee.created_at.desc())
    )
    return list(result.scalars().all())


async def get_employee(session: AsyncSession, employee_id: UUID) -> Optional[Employee]:
    return await session.get(Employee, employee_id)


async def create_employee(session: AsyncSession, business_id: UUID, payload: EmployeeCreate) -> Employee:
    await _require_business(session, business_id)
    if payload.home_location_id is not None:
        location = await session.get(Location, payload.home_location_id)
        if location is None or location.business_id != business_id:
            raise LookupError("home_location_not_found")

    employee = Employee(
        business_id=business_id,
        home_location_id=payload.home_location_id,
        external_ref=payload.external_ref,
        employee_number=payload.employee_number,
        full_name=payload.full_name,
        preferred_name=payload.preferred_name,
        phone_e164=payload.phone_e164,
        email=payload.email,
        employment_type=payload.employment_type,
        hire_date=payload.hire_date,
        notes=payload.notes,
        employee_metadata=payload.employee_metadata,
    )
    session.add(employee)
    await session.flush()
    await session.refresh(employee)
    return employee


async def enroll_employee_at_location(
    session: AsyncSession,
    business_id: UUID,
    payload: EmployeeEnrollAtLocationCreate,
) -> EmployeeEnrollmentRead:
    await _require_business(session, business_id)

    location = await session.get(Location, payload.location_id)
    if location is None or location.business_id != business_id:
        raise LookupError("location_not_found")
    if not payload.role_ids:
        raise ValueError("role_ids_required")

    roles = []
    for role_id in payload.role_ids:
        role = await session.get(Role, role_id)
        if role is None or role.business_id != business_id:
            raise LookupError("role_not_found")
        roles.append(role)

    employee = Employee(
        business_id=business_id,
        home_location_id=payload.location_id,
        external_ref=payload.external_ref,
        employee_number=payload.employee_number,
        full_name=payload.full_name,
        preferred_name=payload.preferred_name,
        phone_e164=payload.phone_e164,
        email=payload.email,
        employment_type=payload.employment_type,
        hire_date=payload.hire_date,
        notes=payload.notes,
        employee_metadata=payload.employee_metadata,
    )
    session.add(employee)
    await session.flush()

    employee_roles: list[EmployeeRole] = []
    for index, role in enumerate(roles):
        employee_role = EmployeeRole(
            employee_id=employee.id,
            role_id=role.id,
            proficiency_level=1,
            is_primary=index == 0,
            role_metadata={"source": "location_enrollment"},
        )
        session.add(employee_role)
        employee_roles.append(employee_role)

    await session.flush()
    await session.refresh(employee)
    for employee_role in employee_roles:
        await session.refresh(employee_role)

    return EmployeeEnrollmentRead(employee=employee, roles=employee_roles)


async def add_employee_role(
    session: AsyncSession,
    business_id: UUID,
    employee_id: UUID,
    payload: EmployeeRoleCreate,
) -> EmployeeRole:
    employee = await session.get(Employee, employee_id)
    role = await session.get(Role, payload.role_id)
    if employee is None or employee.business_id != business_id or role is None or role.business_id != business_id:
        raise LookupError("employee_or_role_not_found")

    record = EmployeeRole(
        employee_id=employee_id,
        role_id=payload.role_id,
        proficiency_level=payload.proficiency_level,
        is_primary=payload.is_primary,
        role_metadata=payload.role_metadata,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def add_employee_location_clearance(
    session: AsyncSession,
    business_id: UUID,
    employee_id: UUID,
    payload: EmployeeLocationClearanceCreate,
) -> EmployeeLocationClearance:
    employee = await session.get(Employee, employee_id)
    location = await session.get(Location, payload.location_id)
    if employee is None or employee.business_id != business_id or location is None or location.business_id != business_id:
        raise LookupError("employee_or_location_not_found")

    record = EmployeeLocationClearance(
        employee_id=employee_id,
        location_id=payload.location_id,
        access_level=payload.access_level,
        clearance_source=payload.clearance_source,
        can_cover_last_minute=payload.can_cover_last_minute,
        can_blast=payload.can_blast,
        travel_radius_miles=payload.travel_radius_miles,
        clearance_metadata=payload.clearance_metadata,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def add_employee_availability_rule(
    session: AsyncSession,
    business_id: UUID,
    employee_id: UUID,
    payload: EmployeeAvailabilityRuleCreate,
) -> EmployeeAvailabilityRule:
    employee = await session.get(Employee, employee_id)
    if employee is None or employee.business_id != business_id:
        raise LookupError("employee_not_found")

    record = EmployeeAvailabilityRule(
        employee_id=employee_id,
        day_of_week=payload.day_of_week,
        start_local_time=payload.start_local_time,
        end_local_time=payload.end_local_time,
        timezone=payload.timezone,
        availability_type=payload.availability_type,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        priority=payload.priority,
        availability_metadata=payload.availability_metadata,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record
