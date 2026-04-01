from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app_v2.models.common import AuditActorType, MembershipRole, MembershipStatus
from app_v2.models.identity import Membership, User
from app_v2.schemas.onboarding import OnboardingProfileUpdate, OwnerWorkspaceBootstrapRequest
from app_v2.services import audit as audit_service
from app_v2.services import auth as auth_service
from app_v2.services import businesses


async def _assert_email_available(session: AsyncSession, user_id: UUID, email: str) -> None:
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None and existing.id != user_id:
        raise ValueError("email_already_in_use")


async def complete_profile(
    session: AsyncSession,
    user: User,
    payload: OnboardingProfileUpdate,
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

    user.full_name = full_name
    user.email = email
    user.onboarding_completed_at = datetime.now(timezone.utc)
    await audit_service.append(
        session,
        event_name="onboarding.profile.completed",
        target_type="user",
        target_id=user.id,
        business_id=business_id,
        location_id=location_id,
        actor_type=AuditActorType.user,
        actor_user_id=user.id,
        actor_membership_id=actor_membership_id,
        ip_address=ip_address,
        user_agent=user_agent,
        payload={"email": email, "full_name": full_name},
    )
    await session.commit()
    await session.refresh(user)
    return user


async def bootstrap_owner_workspace(
    session: AsyncSession,
    auth_ctx: auth_service.AuthContext,
    payload: OwnerWorkspaceBootstrapRequest,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
):
    user = auth_ctx.user
    full_name = payload.profile.full_name.strip()
    email = payload.profile.email.strip().lower()
    if not full_name:
        raise ValueError("full_name_required")
    if not email:
        raise ValueError("email_required")

    await _assert_email_available(session, user.id, email)

    user.full_name = full_name
    user.email = email

    business_payload = payload.business.model_copy(
        update={
            "primary_phone_e164": payload.business.primary_phone_e164 or user.primary_phone_e164,
            "primary_email": payload.business.primary_email or email,
        }
    )
    business = await businesses.create_business_record(session, business_payload)
    owner_membership = Membership(
        user_id=user.id,
        business_id=business.id,
        role=MembershipRole.owner,
        status=MembershipStatus.active,
        accepted_at=datetime.now(timezone.utc),
        membership_metadata={"source": "owner_workspace_bootstrap"},
    )
    session.add(owner_membership)
    await session.flush()

    location = await businesses.create_location_record(session, business.id, payload.location)
    user.onboarding_completed_at = datetime.now(timezone.utc)

    await audit_service.append(
        session,
        event_name="business.created",
        target_type="business",
        target_id=business.id,
        business_id=business.id,
        actor_type=AuditActorType.user,
        actor_user_id=user.id,
        actor_membership_id=owner_membership.id,
        ip_address=ip_address,
        user_agent=user_agent,
        payload={"brand_name": business.brand_name, "legal_name": business.legal_name},
    )
    await audit_service.append(
        session,
        event_name="membership.granted",
        target_type="membership",
        target_id=owner_membership.id,
        business_id=business.id,
        actor_type=AuditActorType.user,
        actor_user_id=user.id,
        actor_membership_id=owner_membership.id,
        ip_address=ip_address,
        user_agent=user_agent,
        payload={"role": owner_membership.role.value, "status": owner_membership.status.value},
    )
    await audit_service.append(
        session,
        event_name="location.created",
        target_type="location",
        target_id=location.id,
        business_id=business.id,
        location_id=location.id,
        actor_type=AuditActorType.user,
        actor_user_id=user.id,
        actor_membership_id=owner_membership.id,
        ip_address=ip_address,
        user_agent=user_agent,
        payload={"name": location.name, "slug": location.slug},
    )
    await audit_service.append(
        session,
        event_name="onboarding.workspace.bootstrapped",
        target_type="business",
        target_id=business.id,
        business_id=business.id,
        location_id=location.id,
        actor_type=AuditActorType.user,
        actor_user_id=user.id,
        actor_membership_id=owner_membership.id,
        ip_address=ip_address,
        user_agent=user_agent,
        payload={"business_slug": business.slug, "location_slug": location.slug},
    )
    await session.commit()
    await session.refresh(user)
    await session.refresh(business)
    await session.refresh(location)
    await session.refresh(owner_membership)
    return user, business, location, owner_membership
