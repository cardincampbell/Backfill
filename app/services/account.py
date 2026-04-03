from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.common import AuditActorType
from app.models.identity import User
from app.schemas.account import AccountProfileUpdate
from app.services import audit as audit_service


async def _assert_email_available(session: AsyncSession, user_id: UUID, email: str) -> None:
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None and existing.id != user_id:
        raise ValueError("email_already_in_use")


async def update_profile(
    session: AsyncSession,
    user: User,
    payload: AccountProfileUpdate,
    *,
    business_id: UUID | None = None,
    location_id: UUID | None = None,
    actor_membership_id: UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> User:
    full_name = payload.full_name.strip()
    email = payload.email.strip().lower()
    if not full_name:
        raise ValueError("full_name_required")
    if not email:
        raise ValueError("email_required")

    await _assert_email_available(session, user.id, email)

    changes: dict[str, object] = {}
    if user.full_name != full_name:
        changes["full_name"] = full_name
        user.full_name = full_name
    if user.email != email:
        changes["email"] = email
        user.email = email
    if user.onboarding_completed_at is None:
        completed_at = datetime.now(timezone.utc)
        changes["onboarding_completed_at"] = completed_at.isoformat()
        user.onboarding_completed_at = completed_at

    if changes:
        await audit_service.append(
            session,
            event_name="account.profile.updated",
            target_type="user",
            target_id=user.id,
            business_id=business_id,
            location_id=location_id,
            actor_type=AuditActorType.user,
            actor_user_id=user.id,
            actor_membership_id=actor_membership_id,
            ip_address=ip_address,
            user_agent=user_agent,
            payload=changes,
        )
        await session.commit()
        await session.refresh(user)

    return user
