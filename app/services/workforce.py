from __future__ import annotations

import csv
import re
from datetime import date, datetime
from io import BytesIO, StringIO
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.models.business import Business, Location, Role
from app.models.common import AssignmentStatus, ShiftStatus
from app.models.workforce import (
    Employee,
    EmployeeAvailabilityRule,
    EmployeeLocation,
    EmployeeRole,
)
from app.schemas.workforce import (
    EmployeeAvailabilityRuleCreate,
    EmployeeAvailabilityRuleReplace,
    EmployeeBulkImportRead,
    EmployeeCreate,
    EmployeeEnrollAtLocationCreate,
    EmployeeEnrollmentRead,
    EmployeeImportErrorRead,
    EmployeeLocationCreate,
    EmployeeLocationUpsert,
    EmployeeRoleCreate,
    EmployeeRoleUpsert,
    EmployeeUpdate,
)

EMPLOYEE_IMPORT_HEADERS = (
    "full_name",
    "preferred_name",
    "email",
    "phone_e164",
    "employee_number",
    "external_ref",
    "employment_type",
    "hire_date",
    "notes",
)

EMPLOYEE_IMPORT_REQUIRED_FIELDS = (
    "full_name",
    "email",
    "phone_e164",
)

EMPLOYEE_IMPORT_HEADER_ALIASES = {
    "full_name": "full_name",
    "employee_name": "full_name",
    "name": "full_name",
    "preferred_name": "preferred_name",
    "email": "email",
    "email_address": "email",
    "phone": "phone_e164",
    "phone_number": "phone_e164",
    "phone_e164": "phone_e164",
    "mobile": "phone_e164",
    "mobile_phone": "phone_e164",
    "employee_number": "employee_number",
    "employee_id": "employee_number",
    "external_ref": "external_ref",
    "external_id": "external_ref",
    "employment_type": "employment_type",
    "employment_status": "employment_type",
    "hire_date": "hire_date",
    "start_date": "hire_date",
    "notes": "notes",
    "first_name": "first_name",
    "last_name": "last_name",
}


def _require_openpyxl():
    try:
        from openpyxl import Workbook, load_workbook
        from openpyxl.styles import Font, PatternFill
    except ModuleNotFoundError as exc:
        raise RuntimeError("employee_import_xlsx_dependency_missing") from exc
    return Workbook, load_workbook, Font, PatternFill


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
        .options(selectinload(EmployeeLocation.location))
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


EMPLOYEE_DELETE_BLOCKING_SHIFT_STATUSES = (
    ShiftStatus.scheduled,
    ShiftStatus.open,
    ShiftStatus.filling,
    ShiftStatus.covered,
    ShiftStatus.no_fill,
    ShiftStatus.completed,
)

EMPLOYEE_DELETE_BLOCKING_ASSIGNMENT_STATUSES = (
    AssignmentStatus.assigned,
    AssignmentStatus.accepted,
    AssignmentStatus.completed,
)


async def _list_employee_availability_rules(
    session: AsyncSession,
    employee_id: UUID,
) -> list[EmployeeAvailabilityRule]:
    result = await session.execute(
        select(EmployeeAvailabilityRule)
        .where(EmployeeAvailabilityRule.employee_id == employee_id)
        .order_by(
            EmployeeAvailabilityRule.day_of_week.asc(),
            EmployeeAvailabilityRule.start_local_time.asc(),
            EmployeeAvailabilityRule.priority.asc(),
            EmployeeAvailabilityRule.created_at.asc(),
        )
    )
    return list(result.scalars().all())


def _self_service_employee_name(
    *,
    full_name: str | None,
    email: str | None,
    phone_e164: str | None,
) -> str:
    normalized_name = full_name.strip() if full_name else ""
    if normalized_name:
        return normalized_name

    normalized_email = email.strip() if email else ""
    if normalized_email:
        return normalized_email

    normalized_phone = phone_e164.strip() if phone_e164 else ""
    if normalized_phone:
        return normalized_phone

    return "Backfill User"


def _pick_linkable_employee_match(
    matches: list[Employee],
    *,
    user_id: UUID | None,
) -> Employee | None:
    if user_id is None:
        return matches[0] if len(matches) == 1 else None

    eligible = [
        employee
        for employee in matches
        if employee.user_id is None or employee.user_id == user_id
    ]
    return eligible[0] if len(eligible) == 1 else None


async def _find_self_service_employee(
    session: AsyncSession,
    business_id: UUID,
    *,
    user_id: UUID | None,
    email: str | None,
    phone_e164: str | None,
    full_name: str | None,
) -> Employee | None:
    if user_id is not None:
        linked_employee = await session.scalar(
            _employee_query().where(
                Employee.business_id == business_id,
                Employee.user_id == user_id,
            )
        )
        if linked_employee is not None:
            return linked_employee

    normalized_phone = phone_e164.strip() if phone_e164 else ""
    if normalized_phone:
        phone_result = await session.execute(
            _employee_query().where(
                Employee.business_id == business_id,
                Employee.phone_e164 == normalized_phone,
            )
        )
        phone_match = _pick_linkable_employee_match(
            list(phone_result.scalars().all()),
            user_id=user_id,
        )
        if phone_match is not None:
            return phone_match

    normalized_email = email.strip().lower() if email else ""
    if normalized_email:
        email_result = await session.execute(
            _employee_query().where(
                Employee.business_id == business_id,
                func.lower(Employee.email) == normalized_email,
            )
        )
        email_match = _pick_linkable_employee_match(
            list(email_result.scalars().all()),
            user_id=user_id,
        )
        if email_match is not None:
            return email_match

    normalized_name = full_name.strip() if full_name else ""
    if normalized_name:
        result = await session.execute(
            _employee_query().where(
                Employee.business_id == business_id,
                Employee.full_name == normalized_name,
            )
        )
        name_match = _pick_linkable_employee_match(
            list(result.scalars().all()),
            user_id=user_id,
        )
        if name_match is not None:
            return name_match

    return None


async def _resolve_self_service_employee(
    session: AsyncSession,
    business_id: UUID,
    *,
    user_id: UUID | None,
    email: str | None,
    phone_e164: str | None,
    full_name: str | None,
) -> Employee:
    employee = await _find_self_service_employee(
        session,
        business_id,
        user_id=user_id,
        email=email,
        phone_e164=phone_e164,
        full_name=full_name,
    )
    if employee is not None:
        return employee

    raise LookupError("employee_self_not_found")


async def _link_employee_to_user(
    session: AsyncSession,
    employee: Employee,
    *,
    user_id: UUID | None,
) -> Employee:
    if user_id is None or employee.user_id == user_id:
        return employee
    if employee.user_id is not None:
        raise LookupError("employee_self_link_conflict")
    employee.user_id = user_id
    await session.flush()
    return employee


async def _get_or_create_self_service_employee(
    session: AsyncSession,
    business_id: UUID,
    *,
    user_id: UUID | None,
    email: str | None,
    phone_e164: str | None,
    full_name: str | None,
) -> Employee:
    employee = await _find_self_service_employee(
        session,
        business_id,
        user_id=user_id,
        email=email,
        phone_e164=phone_e164,
        full_name=full_name,
    )
    if employee is not None:
        return await _link_employee_to_user(session, employee, user_id=user_id)

    employee = await create_employee(
        session,
        business_id,
        EmployeeCreate(
            full_name=_self_service_employee_name(
                full_name=full_name,
                email=email,
                phone_e164=phone_e164,
            ),
            phone_e164=phone_e164.strip() if phone_e164 else None,
            email=email.strip().lower() if email else None,
            employee_metadata={
                "source": "self_service_availability",
                "auto_created_from_user": True,
            },
        ),
        linked_user_id=user_id,
    )
    return employee


def _normalize_import_header(value: object) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    return normalized.strip("_")


def _normalize_import_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _parse_hire_date(raw: object) -> date | None:
    if raw in (None, ""):
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw

    normalized = str(raw).strip()
    if not normalized:
        return None

    for candidate in (normalized, normalized.replace("/", "-")):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass

    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y"):
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue

    raise ValueError("invalid_hire_date")


def _canonicalize_import_row(raw_row: dict[object, object]) -> dict[str, object]:
    canonical: dict[str, object] = {}
    first_name = ""
    last_name = ""

    for header, value in raw_row.items():
        normalized_header = _normalize_import_header(header)
        if not normalized_header:
            continue
        target = EMPLOYEE_IMPORT_HEADER_ALIASES.get(normalized_header)
        if target is None:
            continue
        if target == "first_name":
            first_name = _normalize_import_value(value)
            continue
        if target == "last_name":
            last_name = _normalize_import_value(value)
            continue
        canonical[target] = _normalize_import_value(value)

    if not canonical.get("full_name"):
        full_name = " ".join(part for part in (first_name, last_name) if part)
        if full_name:
            canonical["full_name"] = full_name

    return canonical


def parse_employee_import_file(
    filename: str,
    content: bytes,
    *,
    default_location_id: UUID | None = None,
) -> tuple[list[EmployeeCreate], list[EmployeeImportErrorRead]]:
    normalized_name = filename.lower().strip()
    if normalized_name.endswith(".csv"):
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(StringIO(text))
        rows = [(index, row) for index, row in enumerate(reader, start=2)]
    elif normalized_name.endswith(".xlsx"):
        _, load_workbook, _, _ = _require_openpyxl()
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        sheet = workbook.active
        iterator = sheet.iter_rows(values_only=True)
        headers = next(iterator, None)
        if headers is None:
            return [], []
        rows = []
        for index, values in enumerate(iterator, start=2):
            row = {
                headers[column_index]: values[column_index]
                for column_index in range(len(headers))
            }
            rows.append((index, row))
    else:
        raise ValueError("employee_import_file_type_unsupported")

    employees: list[EmployeeCreate] = []
    errors: list[EmployeeImportErrorRead] = []

    for row_number, raw_row in rows:
        canonical = _canonicalize_import_row(raw_row)
        if not any(str(value).strip() for value in canonical.values() if value is not None):
            continue

        missing_fields = [
            field_name
            for field_name in EMPLOYEE_IMPORT_REQUIRED_FIELDS
            if not str(canonical.get(field_name) or "").strip()
        ]
        if missing_fields:
            errors.append(
                EmployeeImportErrorRead(
                    row_number=row_number,
                    message=f"missing_required_fields:{','.join(missing_fields)}",
                )
            )
            continue

        try:
            employee = EmployeeCreate(
                full_name=str(canonical.get("full_name") or "").strip(),
                preferred_name=str(canonical.get("preferred_name") or "").strip() or None,
                email=str(canonical.get("email") or "").strip() or None,
                phone_e164=str(canonical.get("phone_e164") or "").strip() or None,
                employee_number=str(canonical.get("employee_number") or "").strip() or None,
                external_ref=str(canonical.get("external_ref") or "").strip() or None,
                employment_type=str(canonical.get("employment_type") or "").strip() or None,
                primary_location_id=default_location_id,
                hire_date=_parse_hire_date(canonical.get("hire_date")),
                notes=str(canonical.get("notes") or "").strip() or None,
                employee_metadata={"source": "bulk_import"},
            )
        except ValueError as exc:
            errors.append(
                EmployeeImportErrorRead(
                    row_number=row_number,
                    message=str(exc),
                )
            )
            continue

        employees.append(employee)

    if not employees and not errors:
        raise ValueError("employee_import_no_rows")

    return employees, errors


def build_employee_import_template() -> bytes:
    Workbook, _, Font, PatternFill = _require_openpyxl()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Employees"
    sheet.append(list(EMPLOYEE_IMPORT_HEADERS))
    sheet.append(
        [
            "Taylor Smith",
            "Taylor",
            "taylor@example.com",
            "+15555550123",
            "EMP-001",
            "source-123",
            "part_time",
            "2026-04-08",
            "Weekend closer",
        ]
    )

    header_fill = PatternFill("solid", fgColor="EEF2FF")
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = header_fill

    column_widths = {
        "A": 24,
        "B": 18,
        "C": 28,
        "D": 18,
        "E": 16,
        "F": 18,
        "G": 18,
        "H": 14,
        "I": 28,
    }
    for column, width in column_widths.items():
        sheet.column_dimensions[column].width = width

    instructions = workbook.create_sheet("Instructions")
    instructions.append(["Backfill Employee Import"])
    instructions.append(
        [
            "Import only general employee details here. Assign roles and locations later from the Team UI.",
        ]
    )
    instructions.append(
        [
            "Required columns: full_name, email, phone_e164. Optional columns: preferred_name, employee_number, external_ref, employment_type, hire_date, notes",
        ]
    )
    instructions["A1"].font = Font(bold=True)
    instructions["A1"].fill = header_fill
    instructions.column_dimensions["A"].width = 120

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


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


async def create_employee(
    session: AsyncSession,
    business_id: UUID,
    payload: EmployeeCreate,
    *,
    linked_user_id: UUID | None = None,
) -> Employee:
    await _require_business(session, business_id)
    primary_business_location: Location | None = None
    if payload.primary_location_id is not None:
        primary_business_location = await session.get(Location, payload.primary_location_id)
        if primary_business_location is None or primary_business_location.business_id != business_id:
            raise LookupError("primary_location_not_found")

    employee = Employee(
        business_id=business_id,
        user_id=linked_user_id,
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
    primary_location: EmployeeLocation | None = None
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

    await session.flush()
    await session.refresh(employee)
    if primary_location is not None:
        if primary_business_location is not None:
            set_committed_value(primary_location, "location", primary_business_location)
        set_committed_value(employee, "employee_locations", [primary_location])
    else:
        set_committed_value(employee, "employee_locations", [])
    set_committed_value(employee, "employee_roles", [])
    return employee


async def bulk_import_employees(
    session: AsyncSession,
    business_id: UUID,
    *,
    filename: str,
    content: bytes,
) -> EmployeeBulkImportRead:
    await _require_business(session, business_id)

    if not content:
        raise ValueError("employee_import_file_empty")

    location_result = await session.execute(
        select(Location)
        .where(Location.business_id == business_id, Location.is_active.is_(True))
        .order_by(Location.created_at.asc())
    )
    active_locations = list(location_result.scalars().all())
    default_location = active_locations[0] if len(active_locations) == 1 else None

    parsed_rows, errors = parse_employee_import_file(
        filename,
        content,
        default_location_id=default_location.id if default_location is not None else None,
    )

    created_employees: list[Employee] = []
    for row in parsed_rows:
        created_employees.append(await create_employee(session, business_id, row))

    return EmployeeBulkImportRead(
        created_count=len(created_employees),
        skipped_count=len(errors),
        employees=created_employees,
        errors=errors,
        default_location_id=default_location.id if default_location is not None else None,
        default_location_name=default_location.location_display_name if default_location is not None else None,
    )


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
    set_committed_value(primary_employee_location, "location", location)
    for employee_role, role in zip(employee_roles, roles):
        set_committed_value(employee_role, "role", role)
    set_committed_value(employee, "employee_locations", [primary_employee_location])
    set_committed_value(employee, "employee_roles", employee_roles)

    return EmployeeEnrollmentRead(employee=employee, roles=employee_roles)


async def get_employee_profile(
    session: AsyncSession,
    business_id: UUID,
    employee_id: UUID,
) -> Employee:
    employee = await _require_employee(session, business_id, employee_id)
    employee_roles = await _list_employee_roles(session, employee_id)
    employee_locations = await _list_employee_locations(session, employee_id)
    set_committed_value(employee, "employee_roles", employee_roles)
    set_committed_value(employee, "employee_locations", employee_locations)
    return employee


async def _blocking_employee_assignment_count(
    session: AsyncSession,
    business_id: UUID,
    employee_id: UUID,
) -> int:
    count = await session.scalar(
        select(func.count(ShiftAssignment.id))
        .select_from(ShiftAssignment)
        .join(Shift, Shift.id == ShiftAssignment.shift_id)
        .where(
            Shift.business_id == business_id,
            ShiftAssignment.employee_id == employee_id,
            Shift.status.in_(EMPLOYEE_DELETE_BLOCKING_SHIFT_STATUSES),
            ShiftAssignment.status.in_(EMPLOYEE_DELETE_BLOCKING_ASSIGNMENT_STATUSES),
        )
    )
    return int(count or 0)


async def get_employee_delete_readiness(
    session: AsyncSession,
    business_id: UUID,
    employee_id: UUID,
) -> dict[str, object]:
    await _require_employee(session, business_id, employee_id)
    blocking_assignment_count = await _blocking_employee_assignment_count(
        session,
        business_id,
        employee_id,
    )
    reason = (
        "This employee has scheduled shifts and cannot be removed until those shifts are cleared."
        if blocking_assignment_count > 0
        else None
    )
    return {
        "business_id": business_id,
        "employee_id": employee_id,
        "can_delete": blocking_assignment_count == 0,
        "reason": reason,
    }


async def delete_employee(
    session: AsyncSession,
    business_id: UUID,
    employee_id: UUID,
) -> Employee:
    employee = await _require_employee(session, business_id, employee_id)
    blocking_assignment_count = await _blocking_employee_assignment_count(
        session,
        business_id,
        employee_id,
    )
    if blocking_assignment_count > 0:
        raise ValueError("employee_has_operational_data")
    await session.delete(employee)
    await session.flush()
    return employee


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
    employee_roles = await _list_employee_roles(session, employee_id)
    employee_locations = await _list_employee_locations(session, employee_id)
    set_committed_value(refreshed, "employee_roles", employee_roles)
    set_committed_value(refreshed, "employee_locations", employee_locations)
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


async def replace_employee_availability_rules(
    session: AsyncSession,
    business_id: UUID,
    employee_id: UUID,
    payload: EmployeeAvailabilityRuleReplace,
) -> list[EmployeeAvailabilityRule]:
    employee = await session.get(Employee, employee_id)
    if employee is None or employee.business_id != business_id:
        raise LookupError("employee_not_found")

    await session.execute(
        delete(EmployeeAvailabilityRule).where(
            EmployeeAvailabilityRule.employee_id == employee_id,
        )
    )

    for rule in payload.rules:
        session.add(
            EmployeeAvailabilityRule(
                employee_id=employee_id,
                day_of_week=rule.day_of_week,
                start_local_time=rule.start_local_time,
                end_local_time=rule.end_local_time,
                timezone=rule.timezone,
                availability_type=rule.availability_type,
                valid_from=rule.valid_from,
                valid_until=rule.valid_until,
                priority=rule.priority,
                availability_metadata=rule.availability_metadata,
            )
        )

    await session.flush()
    return await _list_employee_availability_rules(session, employee_id)


async def get_self_employee_availability_rules(
    session: AsyncSession,
    business_id: UUID,
    *,
    user_id: UUID | None,
    email: str | None,
    phone_e164: str | None,
    full_name: str | None,
) -> tuple[Employee, list[EmployeeAvailabilityRule]]:
    employee = await _resolve_self_service_employee(
        session,
        business_id,
        user_id=user_id,
        email=email,
        phone_e164=phone_e164,
        full_name=full_name,
    )
    rules = await _list_employee_availability_rules(session, employee.id)
    return employee, rules


async def replace_self_employee_availability_rules(
    session: AsyncSession,
    business_id: UUID,
    *,
    user_id: UUID | None,
    email: str | None,
    phone_e164: str | None,
    full_name: str | None,
    payload: EmployeeAvailabilityRuleReplace,
) -> tuple[Employee, list[EmployeeAvailabilityRule]]:
    employee = await _get_or_create_self_service_employee(
        session,
        business_id,
        user_id=user_id,
        email=email,
        phone_e164=phone_e164,
        full_name=full_name,
    )
    rules = await replace_employee_availability_rules(
        session,
        business_id,
        employee.id,
        payload,
    )
    return employee, rules


from app.models.scheduling import Shift, ShiftAssignment  # noqa: E402
