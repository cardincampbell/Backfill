from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app_v2.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Business(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "businesses"

    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand_name: Mapped[Optional[str]] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    vertical: Mapped[Optional[str]] = mapped_column(String(80))
    primary_phone_e164: Mapped[Optional[str]] = mapped_column(String(24))
    primary_email: Mapped[Optional[str]] = mapped_column(String(320))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="America/Los_Angeles")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    place_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    locations: Mapped[list["Location"]] = relationship(back_populates="business", cascade="all, delete-orphan")
    roles: Mapped[list["Role"]] = relationship(back_populates="business", cascade="all, delete-orphan")
    employees: Mapped[list["Employee"]] = relationship(back_populates="business", cascade="all, delete-orphan")
    memberships: Mapped[list["Membership"]] = relationship(back_populates="business", cascade="all, delete-orphan")


class Location(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("business_id", "slug", name="uq_locations_business_id_slug"),
        Index("ix_locations_business_id_is_active", "business_id", "is_active"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    address_line_1: Mapped[Optional[str]] = mapped_column(String(255))
    address_line_2: Mapped[Optional[str]] = mapped_column(String(255))
    locality: Mapped[Optional[str]] = mapped_column(String(120))
    region: Mapped[Optional[str]] = mapped_column(String(120))
    postal_code: Mapped[Optional[str]] = mapped_column(String(32))
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, server_default="US")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6))
    google_place_id: Mapped[Optional[str]] = mapped_column(String(255))
    google_place_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    business: Mapped["Business"] = relationship(back_populates="locations")
    memberships: Mapped[list["Membership"]] = relationship(back_populates="location", cascade="all, delete-orphan")
    location_roles: Mapped[list["LocationRole"]] = relationship(back_populates="location", cascade="all, delete-orphan")
    clearances: Mapped[list["EmployeeLocationClearance"]] = relationship(back_populates="location", cascade="all, delete-orphan")
    shifts: Mapped[list["Shift"]] = relationship(back_populates="location", cascade="all, delete-orphan")


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("business_id", "code", name="uq_roles_business_id_code"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(80))
    description: Mapped[Optional[str]] = mapped_column(Text)
    min_notice_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    default_shift_length_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    coverage_priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    business: Mapped["Business"] = relationship(back_populates="roles")
    location_roles: Mapped[list["LocationRole"]] = relationship(back_populates="role", cascade="all, delete-orphan")
    employee_roles: Mapped[list["EmployeeRole"]] = relationship(back_populates="role", cascade="all, delete-orphan")
    shifts: Mapped[list["Shift"]] = relationship(back_populates="role")


class LocationRole(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "location_roles"
    __table_args__ = (
        UniqueConstraint("location_id", "role_id", name="uq_location_roles_location_id_role_id"),
    )

    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    min_headcount: Mapped[Optional[int]] = mapped_column(Integer)
    max_headcount: Mapped[Optional[int]] = mapped_column(Integer)
    premium_rules: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    coverage_settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    location: Mapped["Location"] = relationship(back_populates="location_roles")
    role: Mapped["Role"] = relationship(back_populates="location_roles")


from app_v2.models.identity import Membership  # noqa: E402
from app_v2.models.scheduling import Shift  # noqa: E402
from app_v2.models.workforce import Employee, EmployeeLocationClearance, EmployeeRole  # noqa: E402
