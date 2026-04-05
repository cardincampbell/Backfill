from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Business, Location, LocationRole, Role
from app.models.scheduling import Shift
from app.schemas.business import (
    BusinessCreate,
    BusinessProfileUpdate,
    LocationCreate,
    LocationRoleAttach,
    RoleCreate,
)
from app.services import role_derivation
from app.services.utils import role_code_from_name, slugify


async def _next_unique_business_slug(session: AsyncSession, requested: str) -> str:
    base = slugify(requested)
    slug = base
    suffix = 2
    while await session.scalar(select(Business.id).where(Business.slug == slug)) is not None:
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


async def _next_unique_location_slug(session: AsyncSession, business_id: UUID, requested: str) -> str:
    base = slugify(requested)
    slug = base
    suffix = 2
    while (
        await session.scalar(
            select(Location.id).where(Location.business_id == business_id, Location.slug == slug)
        )
        is not None
    ):
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


async def _next_unique_role_code(session: AsyncSession, business_id: UUID, requested: str) -> str:
    base = role_code_from_name(requested)
    code = base
    suffix = 2
    while (
        await session.scalar(select(Role.id).where(Role.business_id == business_id, Role.code == code))
        is not None
    ):
        code = f"{base}_{suffix}"
        suffix += 1
    return code


def _merge_role_metadata(
    existing: dict | None,
    *,
    source: str,
    source_metadata: dict | None = None,
) -> dict:
    metadata = dict(existing or {})
    sources = [item for item in metadata.get("sources", []) if isinstance(item, str) and item.strip()]
    if source not in sources:
        sources.append(source)
    metadata["sources"] = sorted(set(sources))
    metadata["last_source"] = source

    source_details = dict(metadata.get("source_details") or {})
    current_source_payload = dict(source_details.get(source) or {})
    if source_metadata:
        current_source_payload.update(source_metadata)
    source_details[source] = current_source_payload
    metadata["source_details"] = source_details
    return metadata


async def list_businesses(session: AsyncSession, business_ids: Optional[Sequence[UUID]] = None) -> list[Business]:
    stmt = select(Business).order_by(Business.created_at.desc())
    if business_ids is not None:
        if not business_ids:
            return []
        stmt = stmt.where(Business.id.in_(business_ids))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_business(session: AsyncSession, business_id: UUID) -> Optional[Business]:
    return await session.get(Business, business_id)


async def create_business_record(session: AsyncSession, payload: BusinessCreate) -> Business:
    slug = await _next_unique_business_slug(session, payload.slug or payload.brand_name or payload.legal_name)
    business = Business(
        legal_name=payload.legal_name,
        brand_name=payload.brand_name,
        slug=slug,
        vertical=payload.vertical,
        primary_phone_e164=payload.primary_phone_e164,
        primary_email=payload.primary_email,
        timezone=payload.timezone,
        settings=payload.settings,
        place_metadata=payload.place_metadata,
    )
    session.add(business)
    await session.flush()
    await role_derivation.sync_business_role_catalog(session, business, locations=[])
    return business


async def create_business(session: AsyncSession, payload: BusinessCreate) -> Business:
    business = await create_business_record(session, payload)
    await session.refresh(business)
    return business


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


async def update_business_profile(
    session: AsyncSession,
    business: Business,
    payload: BusinessProfileUpdate,
) -> dict[str, object]:
    brand_name = payload.brand_name.strip()
    timezone = payload.timezone.strip()
    if not brand_name:
        raise ValueError("business_name_required")
    if not timezone:
        raise ValueError("timezone_required")

    vertical = _normalize_optional(payload.vertical)
    primary_email = _normalize_optional(payload.primary_email)
    if primary_email is not None:
        primary_email = primary_email.lower()
    company_address = _normalize_optional(payload.company_address)

    changes: dict[str, object] = {}
    if business.brand_name != brand_name:
        business.brand_name = brand_name
        changes["brand_name"] = brand_name
    settings = dict(business.settings or {})

    if business.vertical != vertical:
        business.vertical = vertical
        changes["vertical"] = vertical
        if vertical is None:
            settings.pop("vertical_source", None)
        else:
            settings["vertical_source"] = "manual"
    if business.primary_email != primary_email:
        business.primary_email = primary_email
        changes["primary_email"] = primary_email
    if business.timezone != timezone:
        business.timezone = timezone
        changes["timezone"] = timezone

    current_company_address = _normalize_optional(settings.get("company_profile_address"))
    if current_company_address != company_address:
        if company_address is None:
            settings.pop("company_profile_address", None)
        else:
            settings["company_profile_address"] = company_address
        business.settings = settings
        changes["company_address"] = company_address

    await session.flush()
    await session.refresh(business)
    return changes


async def list_locations(session: AsyncSession, business_id: UUID) -> list[Location]:
    result = await session.execute(
        select(Location).where(Location.business_id == business_id).order_by(Location.created_at.desc())
    )
    return list(result.scalars().all())


async def get_location(
    session: AsyncSession,
    business_id: UUID,
    location_id: UUID,
) -> Optional[Location]:
    location = await session.get(Location, location_id)
    if location is None or location.business_id != business_id:
        return None
    return location


async def create_location_record(session: AsyncSession, business_id: UUID, payload: LocationCreate) -> Location:
    business = await get_business(session, business_id)
    if business is None:
        raise LookupError("business_not_found")

    slug = await _next_unique_location_slug(session, business_id, payload.slug or payload.name)
    location = Location(
        business_id=business_id,
        name=payload.name,
        slug=slug,
        address_line_1=payload.address_line_1,
        address_line_2=payload.address_line_2,
        locality=payload.locality,
        region=payload.region,
        postal_code=payload.postal_code,
        country_code=payload.country_code,
        timezone=payload.timezone,
        latitude=payload.latitude,
        longitude=payload.longitude,
        google_place_id=payload.google_place_id,
        google_place_metadata=payload.google_place_metadata,
        settings=payload.settings,
    )
    session.add(location)
    await session.flush()
    existing_locations = await list_locations(session, business_id)
    await role_derivation.sync_business_role_catalog(session, business, locations=existing_locations)
    return location


async def create_location(session: AsyncSession, business_id: UUID, payload: LocationCreate) -> Location:
    location = await create_location_record(session, business_id, payload)
    await session.refresh(location)
    return location


async def delete_location(
    session: AsyncSession,
    business_id: UUID,
    location_id: UUID,
) -> Location:
    location = await get_location(session, business_id, location_id)
    if location is None:
        raise LookupError("location_not_found")

    shift_count = await session.scalar(
        select(func.count(Shift.id)).where(Shift.location_id == location_id)
    )
    if int(shift_count or 0) > 0:
        raise ValueError("location_has_operational_data")

    await session.delete(location)
    await session.flush()
    return location


async def list_roles(session: AsyncSession, business_id: UUID) -> list[Role]:
    result = await session.execute(
        select(Role).where(Role.business_id == business_id).order_by(Role.name.asc(), Role.created_at.asc())
    )
    return list(result.scalars().all())


async def ensure_business_role(
    session: AsyncSession,
    *,
    business_id: UUID,
    role_name: str,
    source: str,
    role_code: str | None = None,
    category: str | None = None,
    description: str | None = None,
    min_notice_minutes: int | None = None,
    default_shift_length_minutes: int | None = None,
    coverage_priority: int | None = None,
    source_metadata: dict | None = None,
) -> Role:
    normalized_name = role_name.strip()
    if not normalized_name:
        raise ValueError("role_name_required")

    code = role_code_from_name(role_code or normalized_name)
    existing = await session.scalar(
        select(Role).where(Role.business_id == business_id, Role.code == code)
    )
    if existing is None:
        role = Role(
            business_id=business_id,
            code=code,
            name=normalized_name,
            category=category,
            description=description,
            min_notice_minutes=max(0, int(min_notice_minutes or 0)),
            default_shift_length_minutes=default_shift_length_minutes,
            coverage_priority=max(0, int(coverage_priority if coverage_priority is not None else 100)),
            metadata_json=_merge_role_metadata(
                {},
                source=source,
                source_metadata=source_metadata,
            ),
        )
        session.add(role)
        await session.flush()
        return role

    if not existing.name:
        existing.name = normalized_name
    if category and not existing.category:
        existing.category = category
    if description and not existing.description:
        existing.description = description
    if default_shift_length_minutes is not None and existing.default_shift_length_minutes is None:
        existing.default_shift_length_minutes = default_shift_length_minutes
    if min_notice_minutes is not None and existing.min_notice_minutes == 0 and min_notice_minutes > 0:
        existing.min_notice_minutes = min_notice_minutes
    if coverage_priority is not None and existing.coverage_priority == 100 and coverage_priority != 100:
        existing.coverage_priority = max(0, int(coverage_priority))

    existing.metadata_json = _merge_role_metadata(
        existing.metadata_json,
        source=source,
        source_metadata=source_metadata,
    )
    await session.flush()
    return existing


async def create_role(session: AsyncSession, business_id: UUID, payload: RoleCreate) -> Role:
    business = await get_business(session, business_id)
    if business is None:
        raise LookupError("business_not_found")

    code = await _next_unique_role_code(session, business_id, payload.code or payload.name)
    role = Role(
        business_id=business_id,
        code=code,
        name=payload.name,
        category=payload.category,
        description=payload.description,
        min_notice_minutes=payload.min_notice_minutes,
        default_shift_length_minutes=payload.default_shift_length_minutes,
        coverage_priority=payload.coverage_priority,
        metadata_json=payload.metadata_json,
    )
    session.add(role)
    await session.flush()
    await session.refresh(role)
    return role


async def rerun_role_derivation(session: AsyncSession, business_id: UUID) -> tuple[Business, list[Role]]:
    business = await get_business(session, business_id)
    if business is None:
        raise LookupError("business_not_found")

    locations = await list_locations(session, business_id)
    await role_derivation.sync_business_role_catalog(session, business, locations=locations)
    await session.flush()
    await session.refresh(business)
    roles = await list_roles(session, business_id)
    return business, roles


async def attach_role_to_location(
    session: AsyncSession,
    business_id: UUID,
    location_id: UUID,
    role_id: UUID,
    payload: LocationRoleAttach,
) -> LocationRole:
    location = await session.get(Location, location_id)
    role = await session.get(Role, role_id)
    if location is None or role is None or location.business_id != business_id or role.business_id != business_id:
        raise LookupError("location_or_role_not_found")

    existing = await session.scalar(
        select(LocationRole).where(LocationRole.location_id == location_id, LocationRole.role_id == role_id)
    )
    if existing is None:
        existing = LocationRole(
            location_id=location_id,
            role_id=role_id,
            min_headcount=payload.min_headcount,
            max_headcount=payload.max_headcount,
            premium_rules=payload.premium_rules,
            coverage_settings=payload.coverage_settings,
        )
        session.add(existing)
    else:
        existing.is_active = True
        existing.min_headcount = payload.min_headcount
        existing.max_headcount = payload.max_headcount
        existing.premium_rules = payload.premium_rules
        existing.coverage_settings = payload.coverage_settings

    await session.flush()
    await session.refresh(existing)
    return existing


async def ensure_location_role(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
    role_id: UUID,
    source: str,
) -> LocationRole:
    location = await session.get(Location, location_id)
    role = await session.get(Role, role_id)
    if location is None or role is None or location.business_id != business_id or role.business_id != business_id:
        raise LookupError("location_or_role_not_found")

    existing = await session.scalar(
        select(LocationRole).where(LocationRole.location_id == location_id, LocationRole.role_id == role_id)
    )
    if existing is None:
        existing = LocationRole(
            location_id=location_id,
            role_id=role_id,
            coverage_settings={"source": source},
        )
        session.add(existing)
    else:
        existing.is_active = True
        coverage_settings = dict(existing.coverage_settings or {})
        coverage_settings.setdefault("source", source)
        coverage_settings["last_source"] = source
        existing.coverage_settings = coverage_settings

    await session.flush()
    return existing
