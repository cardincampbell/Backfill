from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.business import Business, Location, Role
from app.models.workforce import (
    Employee,
    EmployeeAvailabilityRule,
    EmployeeLocation,
    EmployeeRole,
)
from app.schemas.workforce import (
    EmployeeAvailabilityRuleCreate,
    EmployeeCreate,
    EmployeeEnrollAtLocationCreate,
    EmployeeEnrollmentRead,
    EmployeeLocationCreate,
    EmployeeLocationUpsert,
    EmployeeRoleCreate,
    EmployeeRoleUpsert,
    EmployeeUpdate,
)


async def _require_business(session: AsyncSession, business_id: UUID) -> Business:
    business = await session.get(Business, business_id)
    if business is None:
        raise LookupError("business_not_found")
    return business


async def _list_employee_locations(
    session: AsyncSession,
    employee_id: UUID,
) -> list[EmployeeLocation]:
    result = await session.execute(
        select(EmployeeLocation)
        .where(EmployeeLocation.employee_id == employee_id)
        .order_by(EmployeeLocation.created_at.asc())
    )
    return list(result.scalars().all())


async def _list_employee_roles(
    session: AsyncSession,
    employee_id: UUID,
) -> list[EmployeeRole]:
    result = await session.execute(
        select(EmployeeRole)
        .options(selectinload(EmployeeRole.role))
        .where(EmployeeRole.employee_id == employee_id)
        .order_by(EmployeeRole.created_at.asc())
    )
    return list(result.scalars().all())


def _employee_query():
    return select(Employee).options(
        selectinload(Employee.employee_roles).selectinload(EmployeeRole.role),
        selectinload(Employee.employee_locations).selectinload(EmployeeLocation.location),
    )


async def list_employees(session: AsyncSession, business_id: UUID) -> list[Employee]:
    result = await session.execute(
        _employee_query()
        .where(Employee.business_id == business_id)
        .order_by(Employee.created_at.desc())
    )
    return list(result.scalars().all())


async def get_employee(
    session: AsyncSession,
    business_id: UUID,
    employee_id: UUID,
) -> Optional[Employee]:
    return await session.scalar(
        _employee_query().where(
            Employee.id == employee_id,
            Employee.business_id == business_id,
        )
    )


async def _require_employee(
    session: AsyncSession,
    business_id: UUID,
    employee_id: UUID,
) -> Employee:
    employee = await get_employee(session, business_id, employee_id)
    if employee is None:
        raise LookupError("employee_not_found")
    return employee


async def _validate_roles(
    session: AsyncSession,
    business_id: UUID,
    role_ids: list[UUID],
) -> dict[UUID, Role]:
    if len(role_ids) != len(set(role_ids)):
        raise ValueError("duplicate_role_ids")
    if not role_ids:
        return {}

    result = await session.execute(
        select(Role).where(Role.business_id == business_id, Role.id.in_(role_ids))
    )
    roles = {role.id: role for role in result.scalars().all()}
    if len(roles) != len(role_ids):
        raise LookupError("role_not_found")
    return roles


async def _validate_locations(
    session: AsyncSession,
    business_id: UUID,
    location_ids: list[UUID],
) -> dict[UUID, Location]:
    if len(location_ids) != len(set(location_ids)):
        raise ValueError("duplicate_location_ids")
    if not location_ids:
        return {}

    result = await session.execute(
        select(Location).where(Location.business_id == business_id, Location.id.in_(location_ids))
    )
    locations = {location.id: location for location in result.scalars().all()}
    if len(locations) != len(location_ids):
        raise LookupError("location_not_found")
    return locations


def _primary_role_id(assignments: list[EmployeeRoleUpsert]) -> UUID | None:
    if not assignments:
        return None
    primary_ids = [item.role_id for item in assignments if item.is_primary]
    if len(primary_ids) > 1:
        raise ValueError("multiple_primary_roles")
    if primary_ids:
        return primary_ids[0]
    return assignments[0].role_id


def _primary_location_id(assignments: list[EmployeeLocationUpsert]) -> UUID | None:
    if not assignments:
        return None
    primary_ids = [item.location_id for item in assignments if item.is_primary]
    if len(primary_ids) > 1:
        raise ValueError("multiple_primary_locations")
    if primary_ids:
        return primary_ids[0]
    return assignments[0].location_id


async def _replace_employee_roles(
    session: AsyncSession,
    employee: Employee,
    business_id: UUID,
    assignments: list[EmployeeRoleUpsert],
) -> None:
    await _validate_roles(session, business_id, [item.role_id for item in assignments])
    primary_role_id = _primary_role_id(assignments)

    existing_roles = await _list_employee_roles(session, employee.id)
    existing_by_role_id = {item.role_id: item for item in existing_roles}
    desired_role_ids = {item.role_id for item in assignments}

    for existing in existing_roles:
        if existing.role_id not in desired_role_ids:
            await session.delete(existing)
            continue
        existing.is_primary = False

    await session.flush()

    for item in assignments:
        existing = existing_by_role_id.get(item.role_id)
        if existing is None:
            record = EmployeeRole(
                employee_id=employee.id,
                role_id=item.role_id,
                proficiency_level=item.proficiency_level or 1,
                is_primary=item.role_id == primary_role_id,
                role_metadata=item.role_metadata or {},
            )
            session.add(record)
            continue

        existing.is_primary = existing.role_id == primary_role_id
        if "proficiency_level" in item.model_fields_set and item.proficiency_level is not None:
            existing.proficiency_level = item.proficiency_level
        if "role_metadata" in item.model_fields_set:
            existing.role_metadata = item.role_metadata or {}


async def _replace_employee_locations(
    session: AsyncSession,
    employee: Employee,
    business_id: UUID,
    assignments: list[EmployeeLocationUpsert],
) -> None:
    await _validate_locations(session, business_id, [item.location_id for item in assignments])
    primary_location_id = _primary_location_id(assignments)

    existing_locations = await _list_employee_locations(session, employee.id)
    existing_by_location_id = {item.location_id: item for item in existing_locations}
    desired_location_ids = {item.location_id for item in assignments}

    for existing in existing_locations:
        if existing.location_id not in desired_location_ids:
            await session.delete(existing)
            continue
        existing.is_primary = False

    await session.flush()

    for item in assignments:
        existing = existing_by_location_id.get(item.location_id)
        if existing is None:
            record = EmployeeLocation(
                employee_id=employee.id,
                location_id=item.location_id,
                is_primary=item.location_id == primary_location_id,
                access_level=item.access_level or "approved",
                location_source=item.location_source,
                can_cover_last_minute=(
                    True if item.can_cover_last_minute is None else item.can_cover_last_minute
                ),
                can_blast=True if item.can_blast is None else item.can_blast,
                travel_radius_miles=item.travel_radius_miles,
                location_metadata=item.location_metadata or {},
            )
            session.add(record)
            continue

        existing.is_primary = existing.location_id == primary_location_id
        if "access_level" in item.model_fields_set and item.access_level is not None:
            existing.access_level = item.access_level
        if "location_source" in item.model_fields_set:
            existing.location_source = item.location_source
        if "can_cover_last_minute" in item.model_fields_set and item.can_cover_last_minute is not None:
            existing.can_cover_last_minute = item.can_cover_last_minute
        if "can_blast" in item.model_fields_set and item.can_blast is not None:
            existing.can_blast = item.can_blast
        if "travel_radius_miles" in item.model_fields_set:
            existing.travel_radius_miles = item.travel_radius_miles
        if "location_metadata" in item.model_fields_set:
            existing.location_metadata = item.location_metadata or {}


async def create_employee(session: AsyncSession, business_id: UUID, payload: EmployeeCreate) -> Employee:
    await _require_business(session, business_id)
    if payload.primary_location_id is not None:
        location = await session.get(Location, payload.primary_location_id)
        if location is None or location.business_id != business_id:
            raise LookupError("primary_location_not_found")

    employee = Employee(
        business_id=business_id,
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

    employee_locations: list[EmployeeLocation] = []
    if payload.primary_location_id is not None:
        primary_location = EmployeeLocation(
            employee_id=employee.id,
            location_id=payload.primary_location_id,
            is_primary=True,
            access_level="approved",
            location_source="employee_create",
            can_cover_last_minute=True,
            can_blast=True,
            location_metadata={},
        )
        session.add(primary_location)
        employee_locations.append(primary_location)

    await session.flush()
    await session.refresh(employee)
    employee.employee_locations = employee_locations
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

    primary_employee_location = EmployeeLocation(
        employee_id=employee.id,
        location_id=payload.location_id,
        is_primary=True,
        access_level="approved",
        location_source="location_enrollment",
        can_cover_last_minute=True,
        can_blast=True,
        location_metadata={},
    )
    session.add(primary_employee_location)

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
    employee.employee_locations = [primary_employee_location]
    for employee_role in employee_roles:
        await session.refresh(employee_role)

    return EmployeeEnrollmentRead(employee=employee, roles=employee_roles)


async def get_employee_profile(
    session: AsyncSession,
    business_id: UUID,
    employee_id: UUID,
) -> Employee:
    return await _require_employee(session, business_id, employee_id)


async def update_employee(
    session: AsyncSession,
    business_id: UUID,
    employee_id: UUID,
    payload: EmployeeUpdate,
) -> Employee:
    employee = await _require_employee(session, business_id, employee_id)

    field_updates = {
        "full_name": payload.full_name,
        "preferred_name": payload.preferred_name,
        "phone_e164": payload.phone_e164,
        "email": payload.email,
        "external_ref": payload.external_ref,
        "employee_number": payload.employee_number,
        "employment_type": payload.employment_type,
        "status": payload.status,
        "hire_date": payload.hire_date,
        "termination_date": payload.termination_date,
        "notes": payload.notes,
        "employee_metadata": payload.employee_metadata,
    }
    for field_name, field_value in field_updates.items():
        if field_name in payload.model_fields_set:
            setattr(employee, field_name, field_value)

    if "roles" in payload.model_fields_set:
        await _replace_employee_roles(session, employee, business_id, payload.roles or [])

    if "locations" in payload.model_fields_set:
        await _replace_employee_locations(session, employee, business_id, payload.locations or [])

    await session.flush()
    refreshed = await get_employee(session, business_id, employee_id)
    if refreshed is None:
        raise LookupError("employee_not_found")
    return refreshed


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

    existing_roles = await _list_employee_roles(session, employee_id)
    existing_role = next((item for item in existing_roles if item.role_id == payload.role_id), None)
    if payload.is_primary:
        for employee_role in existing_roles:
            if employee_role.role_id != payload.role_id and employee_role.is_primary:
                employee_role.is_primary = False
        await session.flush()

    if existing_role is not None:
        existing_role.proficiency_level = payload.proficiency_level
        existing_role.is_primary = (
            payload.is_primary
            or existing_role.is_primary
            or not any(item.is_primary for item in existing_roles)
        )
        existing_role.role_metadata = payload.role_metadata
        await session.flush()
        await session.refresh(existing_role)
        return existing_role

    record = EmployeeRole(
        employee_id=employee_id,
        role_id=payload.role_id,
        proficiency_level=payload.proficiency_level,
        is_primary=payload.is_primary or not any(item.is_primary for item in existing_roles),
        role_metadata=payload.role_metadata,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def add_employee_location(
    session: AsyncSession,
    business_id: UUID,
    employee_id: UUID,
    payload: EmployeeLocationCreate,
) -> EmployeeLocation:
    employee = await session.get(Employee, employee_id)
    location = await session.get(Location, payload.location_id)
    if employee is None or employee.business_id != business_id or location is None or location.business_id != business_id:
        raise LookupError("employee_or_location_not_found")

    existing_locations = await _list_employee_locations(session, employee_id)
    existing_location = next(
        (
            item
            for item in existing_locations
            if item.location_id == payload.location_id
        ),
        None,
    )
    has_primary_location = any(item.is_primary for item in existing_locations)

    if payload.is_primary:
        for employee_location in existing_locations:
            if employee_location.location_id != payload.location_id and employee_location.is_primary:
                employee_location.is_primary = False
        await session.flush()

    if existing_location is not None:
        existing_location.is_primary = (
            existing_location.is_primary
            or payload.is_primary
            or not has_primary_location
        )
        existing_location.access_level = payload.access_level
        existing_location.location_source = payload.location_source
        existing_location.can_cover_last_minute = payload.can_cover_last_minute
        existing_location.can_blast = payload.can_blast
        existing_location.travel_radius_miles = payload.travel_radius_miles
        existing_location.location_metadata = payload.location_metadata
        await session.flush()
        await session.refresh(existing_location)
        return existing_location

    record = EmployeeLocation(
        employee_id=employee_id,
        location_id=payload.location_id,
        is_primary=payload.is_primary or not has_primary_location,
        access_level=payload.access_level,
        location_source=payload.location_source,
        can_cover_last_minute=payload.can_cover_last_minute,
        can_blast=payload.can_blast,
        travel_radius_miles=payload.travel_radius_miles,
        location_metadata=payload.location_metadata,
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
