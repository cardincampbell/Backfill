from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.common import (
    ChallengeChannel,
    ChallengePurpose,
    ChallengeStatus,
    InviteStatus,
    MembershipRole,
    MembershipStatus,
    SessionRiskLevel,
)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(320), unique=True)
    primary_phone_e164: Mapped[Optional[str]] = mapped_column(String(24), unique=True)
    is_phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    onboarding_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_sign_in_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    profile_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="Membership.user_id",
    )
    sessions: Mapped[list["Session"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    invites_sent: Mapped[list["ManagerInvite"]] = relationship(
        back_populates="invited_by_user",
        foreign_keys="ManagerInvite.invited_by_user_id",
    )
    invites_matched: Mapped[list["ManagerInvite"]] = relationship(
        back_populates="matched_user",
        foreign_keys="ManagerInvite.matched_user_id",
    )


class Membership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        Index("ix_memberships_business_id_status", "business_id", "status"),
        Index("ix_memberships_location_id_status", "location_id", "status"),
        Index(
            "uq_memberships_user_business_scope",
            "user_id",
            "business_id",
            unique=True,
            postgresql_where=text("location_id IS NULL"),
        ),
        Index(
            "uq_memberships_user_location_scope",
            "user_id",
            "location_id",
            unique=True,
            postgresql_where=text("location_id IS NOT NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"))
    role: Mapped[MembershipRole] = mapped_column(
        Enum(MembershipRole, name="membership_role"),
        nullable=False,
        server_default=MembershipRole.manager.value,
    )
    status: Mapped[MembershipStatus] = mapped_column(
        Enum(MembershipStatus, name="membership_status"),
        nullable=False,
        server_default=MembershipStatus.pending.value,
    )
    invited_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    membership_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    user: Mapped["User"] = relationship(back_populates="memberships", foreign_keys=[user_id])
    business: Mapped["Business"] = relationship(back_populates="memberships")
    location: Mapped[Optional["Location"]] = relationship(back_populates="memberships")


class ManagerInvite(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "manager_invites"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_manager_invites_token_hash"),
        Index("ix_manager_invites_location_id_status", "location_id", "status"),
        Index("ix_manager_invites_recipient_email", "recipient_email"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    invited_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    matched_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    role: Mapped[MembershipRole] = mapped_column(
        Enum(MembershipRole, name="manager_invite_role"),
        nullable=False,
        server_default=MembershipRole.manager.value,
    )
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    recipient_phone_e164: Mapped[Optional[str]] = mapped_column(String(24))
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[InviteStatus] = mapped_column(
        Enum(InviteStatus, name="invite_status"),
        nullable=False,
        server_default=InviteStatus.pending.value,
    )
    subject_business_name: Mapped[Optional[str]] = mapped_column(String(255))
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    invite_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    invited_by_user: Mapped[Optional["User"]] = relationship(back_populates="invites_sent", foreign_keys=[invited_by_user_id])
    matched_user: Mapped[Optional["User"]] = relationship(back_populates="invites_matched", foreign_keys=[matched_user_id])


class OTPChallenge(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "otp_challenges"
    __table_args__ = (
        Index("ix_otp_challenges_phone_status", "phone_e164", "status"),
    )

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    phone_e164: Mapped[str] = mapped_column(String(24), nullable=False)
    external_sid: Mapped[Optional[str]] = mapped_column(String(255))
    channel: Mapped[ChallengeChannel] = mapped_column(
        Enum(ChallengeChannel, name="challenge_channel"),
        nullable=False,
        server_default=ChallengeChannel.sms.value,
    )
    purpose: Mapped[ChallengePurpose] = mapped_column(
        Enum(ChallengePurpose, name="challenge_purpose"),
        nullable=False,
    )
    status: Mapped[ChallengeStatus] = mapped_column(
        Enum(ChallengeStatus, name="challenge_status"),
        nullable=False,
        server_default=ChallengeStatus.pending.value,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    requested_for_business_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("businesses.id", ondelete="SET NULL"))
    requested_for_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    challenge_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)


class Session(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
        Index("ix_sessions_user_id_expires_at", "user_id", "expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    device_fingerprint: Mapped[Optional[str]] = mapped_column(String(255))
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(String(1024))
    risk_level: Mapped[SessionRiskLevel] = mapped_column(
        Enum(SessionRiskLevel, name="session_risk_level"),
        nullable=False,
        server_default=SessionRiskLevel.low.value,
    )
    elevated_actions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    session_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    user: Mapped["User"] = relationship(back_populates="sessions")


from app.models.business import Business, Location  # noqa: E402
