from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Optional
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app_v2.config import v2_settings
from app_v2.models.business import Business, Location
from app_v2.models.common import InviteStatus, MembershipRole, MembershipStatus
from app_v2.models.identity import ManagerInvite, Membership, User
from app_v2.services import messaging, rate_limit


INVITE_TTL_HOURS = 72


@dataclass
class ManagerAccessView:
    id: UUID
    location_id: UUID
    entry_kind: str
    manager_name: str | None
    manager_email: str | None
    phone_e164: str | None
    role: str
    invite_status: str
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass
class ManagerInvitePreview:
    invite: ManagerInvite
    business: Business
    location: Location
    recipient_has_phone: bool
    manager_name: str | None


def _invite_token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def new_invite_token(prefix: str = "bfv2invite") -> str:
    return f"{prefix}_{secrets.token_urlsafe(24)}"


def build_manager_invite_link(raw_token: str) -> str:
    return f"{v2_settings.web_base_url}/onboarding?invite={quote(raw_token)}"


def location_address(location: Location) -> str | None:
    parts = [
        location.address_line_1,
        location.locality,
        location.region,
        location.postal_code,
    ]
    value = ", ".join(part.strip() for part in parts if part and str(part).strip())
    return value or None


def invite_manager_name(invite: ManagerInvite) -> str | None:
    metadata = invite.invite_metadata or {}
    value = metadata.get("manager_name") or metadata.get("claimed_name")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def recipient_has_phone(invite: ManagerInvite) -> bool:
    metadata = invite.invite_metadata or {}
    if invite.recipient_phone_e164:
        return True
    return bool(metadata.get("matched_user_has_phone"))


def build_manager_invite_email_content(
    *,
    business_name: str,
    location_name: str,
    inviter_name: str,
    raw_token: str,
    recipient_has_existing_account: bool,
) -> tuple[str, str, str]:
    invite_url = build_manager_invite_link(raw_token)
    subject = f"You're invited to manage {business_name} in Backfill"
    setup_copy = (
        "Click on the link below to accept this invitation and sign in."
        if recipient_has_existing_account
        else "Click on the link below to accept this invitation and get your account setup."
    )
    location_line = f"{business_name} + {location_name}"
    intro = f"{inviter_name} has invited you to manage {location_line} in Backfill. {setup_copy}"
    footer = "If you believe this email has been sent in error, please ignore it."
    support = "Backfill handles callouts and last-minute shift changes automatically — so you never have to."
    text_body = "\n\n".join(
        [
            intro,
            f"Accept the invitation: {invite_url}",
            support,
            footer,
        ]
    )

    headline = escape(f"You've been invited to manage {business_name}")
    intro_html = escape(intro)
    invite_url_html = escape(invite_url)
    support_html = escape(support)
    footer_html = escape(footer)
    tagline_html = escape("Callouts covered.")
    logo_html = escape("Backfill")
    cta_html = escape("Accept invitation")

    html_body = f"""
<div style="margin:0;padding:24px 0;background:#ffffff;font-family:Helvetica Neue,Arial,sans-serif;color:#111111;">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:640px;margin:0 auto;padding:0 16px;">
    <tr>
      <td align="left" style="padding:0 0 28px 0;font-size:32px;font-weight:800;letter-spacing:-0.04em;">{logo_html}</td>
      <td align="right" style="padding:0 0 28px 0;font-size:14px;font-weight:600;color:#666666;white-space:nowrap;">{tagline_html}</td>
    </tr>
    <tr>
      <td colspan="2">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f3f3f3;border:1px solid #dfdfdf;border-radius:18px;padding:32px;">
          <tr>
            <td style="font-size:44px;line-height:1.02;font-weight:800;letter-spacing:-0.06em;padding:0 0 18px 0;">{headline}</td>
          </tr>
          <tr>
            <td style="font-size:18px;line-height:1.6;color:#3f3f3f;padding:0 0 24px 0;">{intro_html}</td>
          </tr>
          <tr>
            <td style="padding:0 0 24px 0;">
              <a href="{invite_url_html}" style="display:inline-block;padding:16px 30px;background:#111111;color:#ffffff;text-decoration:none;border-radius:14px;font-size:18px;font-weight:700;">{cta_html}</a>
            </td>
          </tr>
          <tr>
            <td style="font-size:18px;line-height:1.65;color:#3f3f3f;padding:0;">{support_html}</td>
          </tr>
        </table>
      </td>
    </tr>
    <tr>
      <td colspan="2" style="padding:22px 0 0 0;font-size:13px;line-height:1.55;color:#8a8a8a;">{footer_html}</td>
    </tr>
  </table>
</div>
""".strip()
    return subject, text_body, html_body


async def get_business_location(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
) -> tuple[Business, Location]:
    business = await session.get(Business, business_id)
    location = await session.get(Location, location_id)
    if business is None or location is None or location.business_id != business_id:
        raise LookupError("business_or_location_not_found")
    return business, location


async def list_location_manager_access(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
) -> list[ManagerAccessView]:
    await get_business_location(session, business_id=business_id, location_id=location_id)
    rows: list[ManagerAccessView] = []

    membership_rows = await session.execute(
        select(Membership, User)
        .join(User, Membership.user_id == User.id)
        .where(
            Membership.business_id == business_id,
            Membership.location_id == location_id,
            Membership.revoked_at.is_(None),
            Membership.status.in_([MembershipStatus.active, MembershipStatus.pending]),
        )
        .order_by(Membership.created_at.asc())
    )
    for membership, user in membership_rows.all():
        rows.append(
            ManagerAccessView(
                id=membership.id,
                location_id=location_id,
                entry_kind="membership",
                manager_name=user.full_name,
                manager_email=user.email,
                phone_e164=user.primary_phone_e164,
                role=membership.role.value,
                invite_status=membership.status.value,
                accepted_at=membership.accepted_at,
                revoked_at=membership.revoked_at,
                created_at=membership.created_at,
                updated_at=membership.updated_at,
            )
        )

    invite_rows = await session.execute(
        select(ManagerInvite)
        .where(
            ManagerInvite.business_id == business_id,
            ManagerInvite.location_id == location_id,
            ManagerInvite.status == InviteStatus.pending,
        )
        .order_by(ManagerInvite.created_at.asc())
    )
    for invite in invite_rows.scalars().all():
        rows.append(
            ManagerAccessView(
                id=invite.id,
                location_id=location_id,
                entry_kind="invite",
                manager_name=invite_manager_name(invite),
                manager_email=invite.recipient_email,
                phone_e164=invite.recipient_phone_e164,
                role=invite.role.value,
                invite_status=invite.status.value,
                accepted_at=invite.accepted_at,
                revoked_at=None,
                created_at=invite.created_at,
                updated_at=invite.updated_at,
            )
        )

    rows.sort(key=lambda item: ((item.manager_name or item.manager_email or "").lower(), item.created_at))
    return rows


async def revoke_location_membership(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
    membership_id: UUID,
) -> Membership:
    membership = await session.get(Membership, membership_id)
    if (
        membership is None
        or membership.business_id != business_id
        or membership.location_id != location_id
        or membership.revoked_at is not None
    ):
        raise LookupError("membership_not_found")

    membership.status = MembershipStatus.revoked
    membership.revoked_at = datetime.now(timezone.utc)
    return membership


async def create_manager_invite(
    session: AsyncSession,
    *,
    business_id: UUID,
    location_id: UUID,
    email: str,
    manager_name: str | None,
    role: str,
    invited_by_user_id: UUID,
    inviter_name: str,
) -> tuple[ManagerInvite | None, bool, str | None]:
    normalized_email = email.strip().lower()
    if "@" not in normalized_email:
        raise ValueError("valid_email_required")

    rate_limit.assert_within_limit(
        "manager_invite_actor",
        str(invited_by_user_id),
        limit=20,
        window_seconds=3600,
        detail="Too many manager invites. Please wait and try again.",
    )
    rate_limit.assert_within_limit(
        "manager_invite_location",
        str(location_id),
        limit=10,
        window_seconds=3600,
        detail="This location has sent too many invites recently. Please wait and try again.",
    )
    rate_limit.assert_within_limit(
        "manager_invite_recipient",
        normalized_email,
        limit=3,
        window_seconds=3600,
        detail="This email has been invited too many times recently. Please wait and try again.",
    )

    business, location = await get_business_location(
        session,
        business_id=business_id,
        location_id=location_id,
    )
    matched_user = await session.scalar(select(User).where(User.email == normalized_email))
    if matched_user is not None:
        existing_membership = await session.scalar(
            select(Membership).where(
                Membership.business_id == business_id,
                Membership.location_id == location_id,
                Membership.user_id == matched_user.id,
                Membership.revoked_at.is_(None),
                Membership.status == MembershipStatus.active,
            )
        )
        if existing_membership is not None:
            return None, False, None

    invite = await session.scalar(
        select(ManagerInvite)
        .where(
            ManagerInvite.business_id == business_id,
            ManagerInvite.location_id == location_id,
            ManagerInvite.recipient_email == normalized_email,
        )
        .order_by(ManagerInvite.created_at.desc())
    )

    created = invite is None or invite.status in {InviteStatus.revoked, InviteStatus.expired}
    now = datetime.now(timezone.utc)
    raw_token = new_invite_token()
    metadata = dict(invite.invite_metadata) if invite is not None else {}
    if manager_name:
        metadata["manager_name"] = manager_name.strip()
    metadata["matched_user_has_phone"] = bool(
        matched_user is not None and matched_user.primary_phone_e164
    )

    if invite is None:
        invite = ManagerInvite(
            business_id=business_id,
            location_id=location_id,
            invited_by_user_id=invited_by_user_id,
            matched_user_id=matched_user.id if matched_user is not None else None,
            role=MembershipRole(role),
            recipient_email=normalized_email,
            token_hash=_invite_token_hash(raw_token),
            status=InviteStatus.pending,
            subject_business_name=business.brand_name or business.legal_name,
            sent_at=now,
            expires_at=now + timedelta(hours=INVITE_TTL_HOURS),
            invite_metadata=metadata,
        )
        session.add(invite)
        await session.flush()
    else:
        invite.invited_by_user_id = invited_by_user_id
        invite.matched_user_id = matched_user.id if matched_user is not None else None
        invite.role = MembershipRole(role)
        invite.token_hash = _invite_token_hash(raw_token)
        invite.status = InviteStatus.pending
        invite.subject_business_name = business.brand_name or business.legal_name
        invite.sent_at = now
        invite.expires_at = now + timedelta(hours=INVITE_TTL_HOURS)
        invite.invite_metadata = metadata

    subject, text_body, html_body = build_manager_invite_email_content(
        business_name=business.brand_name or business.legal_name,
        location_name=location.name,
        inviter_name=inviter_name.strip() or "A Backfill manager",
        raw_token=raw_token,
        recipient_has_existing_account=bool(
            matched_user is not None and matched_user.primary_phone_e164
        ),
    )
    delivery_id = messaging.send_email(
        to=normalized_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )
    return invite, created, delivery_id


async def get_invite_preview(
    session: AsyncSession,
    *,
    raw_token: str,
) -> ManagerInvitePreview:
    invite = await session.scalar(
        select(ManagerInvite).where(ManagerInvite.token_hash == _invite_token_hash(raw_token))
    )
    if invite is None:
        raise LookupError("invite_not_found")

    business, location = await get_business_location(
        session,
        business_id=invite.business_id,
        location_id=invite.location_id,
    )
    matched_user = (
        await session.get(User, invite.matched_user_id)
        if invite.matched_user_id is not None
        else await session.scalar(select(User).where(User.email == invite.recipient_email))
    )
    return ManagerInvitePreview(
        invite=invite,
        business=business,
        location=location,
        recipient_has_phone=bool(matched_user is not None and matched_user.primary_phone_e164),
        manager_name=invite_manager_name(invite),
    )


def assert_invite_is_usable(preview: ManagerInvitePreview) -> None:
    if preview.invite.status == InviteStatus.accepted:
        raise ValueError("invite_already_accepted")
    if preview.invite.status == InviteStatus.revoked:
        raise ValueError("invite_revoked")
    if preview.invite.status == InviteStatus.expired:
        raise ValueError("invite_expired")
    if preview.invite.expires_at is not None and preview.invite.expires_at < datetime.now(timezone.utc):
        raise ValueError("invite_expired")


def assert_invite_record_is_usable(invite: ManagerInvite) -> None:
    if invite.status == InviteStatus.accepted:
        raise ValueError("invite_already_accepted")
    if invite.status == InviteStatus.revoked:
        raise ValueError("invite_revoked")
    if invite.status == InviteStatus.expired:
        raise ValueError("invite_expired")
    if invite.expires_at is not None and invite.expires_at < datetime.now(timezone.utc):
        raise ValueError("invite_expired")


async def accept_invite_for_verified_user(
    session: AsyncSession,
    *,
    invite_id: UUID,
    user: User,
    phone_e164: str,
    manager_name: str | None = None,
) -> tuple[ManagerInvite, Membership]:
    invite = await session.get(ManagerInvite, invite_id)
    if invite is None:
        raise LookupError("invite_not_found")
    assert_invite_record_is_usable(invite)

    existing_email_user = await session.scalar(select(User).where(User.email == invite.recipient_email))
    if existing_email_user is not None and existing_email_user.id != user.id:
        raise PermissionError("invite_email_belongs_to_existing_user")
    if invite.matched_user_id is not None and invite.matched_user_id != user.id:
        raise PermissionError("invite_claimed_for_another_user")
    if user.email and user.email.strip().lower() != invite.recipient_email.strip().lower():
        raise PermissionError("invite_email_mismatch")

    if not user.email:
        user.email = invite.recipient_email
    if manager_name and not user.full_name:
        user.full_name = manager_name.strip()

    membership = await session.scalar(
        select(Membership)
        .where(
            Membership.business_id == invite.business_id,
            Membership.location_id == invite.location_id,
            Membership.user_id == user.id,
        )
        .order_by(Membership.created_at.desc())
    )
    now = datetime.now(timezone.utc)
    if membership is None:
        membership = Membership(
            user_id=user.id,
            business_id=invite.business_id,
            location_id=invite.location_id,
            role=invite.role,
            status=MembershipStatus.active,
            invited_by_user_id=invite.invited_by_user_id,
            accepted_at=now,
            membership_metadata={"source": "manager_invite", "invite_id": str(invite.id)},
        )
        session.add(membership)
        await session.flush()
    else:
        membership.role = invite.role
        membership.status = MembershipStatus.active
        membership.accepted_at = now
        membership.revoked_at = None
        membership.invited_by_user_id = invite.invited_by_user_id
        membership.membership_metadata = {
            **(membership.membership_metadata or {}),
            "source": "manager_invite",
            "invite_id": str(invite.id),
        }

    invite.matched_user_id = user.id
    invite.recipient_phone_e164 = phone_e164
    invite.status = InviteStatus.accepted
    invite.accepted_at = now
    invite.invite_metadata = {
        **(invite.invite_metadata or {}),
        **({"claimed_name": manager_name.strip()} if manager_name and manager_name.strip() else {}),
    }
    return invite, membership
