from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app_v2.models.business import Business, Location
from app_v2.models.identity import Membership, User
from app_v2.schemas.identity import MembershipCreate, UserUpsert


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())


async def get_user(session: AsyncSession, user_id: UUID) -> Optional[User]:
    return await session.get(User, user_id)


async def upsert_user(session: AsyncSession, payload: UserUpsert) -> User:
    if not payload.email and not payload.primary_phone_e164:
        raise ValueError("email or primary_phone_e164 is required")

    existing: Optional[User] = None
    if payload.primary_phone_e164:
        existing = await session.scalar(
            select(User).where(User.primary_phone_e164 == payload.primary_phone_e164)
        )
    if existing is None and payload.email:
        existing = await session.scalar(select(User).where(User.email == payload.email))

    if existing is None:
        existing = User(
            full_name=payload.full_name,
            email=payload.email,
            primary_phone_e164=payload.primary_phone_e164,
            is_phone_verified=payload.is_phone_verified,
            profile_metadata=payload.profile_metadata,
        )
        session.add(existing)
    else:
        if payload.full_name is not None:
            existing.full_name = payload.full_name
        if payload.email is not None:
            existing.email = payload.email
        if payload.primary_phone_e164 is not None:
            existing.primary_phone_e164 = payload.primary_phone_e164
        existing.is_phone_verified = payload.is_phone_verified or existing.is_phone_verified
        existing.profile_metadata = {**existing.profile_metadata, **payload.profile_metadata}

    await session.commit()
    await session.refresh(existing)
    return existing


async def list_memberships_for_business(session: AsyncSession, business_id: UUID) -> list[Membership]:
    result = await session.execute(
        select(Membership).where(Membership.business_id == business_id).order_by(Membership.created_at.desc())
    )
    return list(result.scalars().all())


async def create_membership(session: AsyncSession, business_id: UUID, payload: MembershipCreate) -> Membership:
    business = await session.get(Business, business_id)
    user = await session.get(User, payload.user_id)
    if business is None or user is None:
        raise LookupError("business_or_user_not_found")
    if payload.location_id is not None:
        location = await session.get(Location, payload.location_id)
        if location is None or location.business_id != business_id:
            raise LookupError("location_not_found")

    membership = Membership(
        user_id=payload.user_id,
        business_id=business_id,
        location_id=payload.location_id,
        role=payload.role,
        status=payload.status,
        invited_by_user_id=payload.invited_by_user_id,
        membership_metadata=payload.membership_metadata,
    )
    session.add(membership)
    await session.commit()
    await session.refresh(membership)
    return membership
