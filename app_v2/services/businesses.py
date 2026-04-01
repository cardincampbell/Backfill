from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app_v2.models.business import Business, Location, LocationRole, Role
from app_v2.models.scheduling import Shift
from app_v2.schemas.business import (
    BusinessCreate,
    LocationCreate,
    LocationRoleAttach,
    RoleCreate,
)
from app_v2.services.utils import role_code_from_name, slugify


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
    return business


async def create_business(session: AsyncSession, payload: BusinessCreate) -> Business:
    business = await create_business_record(session, payload)
    await session.commit()
    await session.refresh(business)
    return business


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
    return location


async def create_location(session: AsyncSession, business_id: UUID, payload: LocationCreate) -> Location:
    location = await create_location_record(session, business_id, payload)
    await session.commit()
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
        select(Role).where(Role.business_id == business_id).order_by(Role.created_at.desc())
    )
    return list(result.scalars().all())


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
    await session.commit()
    await session.refresh(role)
    return role


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

    await session.commit()
    await session.refresh(existing)
    return existing
