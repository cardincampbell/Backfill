from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text, Time, UniqueConstraint, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.common import EmployeeStatus


class Employee(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("business_id", "external_ref", name="uq_employees_business_id_external_ref"),
        UniqueConstraint("business_id", "user_id", name="uq_employees_business_id_user_id"),
        Index("ix_employees_business_id_status", "business_id", "status"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    external_ref: Mapped[Optional[str]] = mapped_column(String(255))
    employee_number: Mapped[Optional[str]] = mapped_column(String(80))
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    preferred_name: Mapped[Optional[str]] = mapped_column(String(255))
    phone_e164: Mapped[Optional[str]] = mapped_column(String(24))
    email: Mapped[Optional[str]] = mapped_column(String(320))
    reliability_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, server_default="0.700")
    avg_response_time_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[EmployeeStatus] = mapped_column(
        Enum(EmployeeStatus, name="employee_status"),
        nullable=False,
        server_default=EmployeeStatus.active.value,
    )
    employment_type: Mapped[Optional[str]] = mapped_column(String(80))
    hire_date: Mapped[Optional[date]] = mapped_column(Date)
    termination_date: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    response_profile: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)
    employee_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    business: Mapped["Business"] = relationship(back_populates="employees")
    employee_roles: Mapped[list["EmployeeRole"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        order_by="EmployeeRole.created_at.asc()",
    )
    employee_locations: Mapped[list["EmployeeLocation"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        order_by="EmployeeLocation.created_at.asc()",
    )
    schedule_access_link: Mapped[Optional["EmployeeScheduleAccessLink"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        uselist=False,
    )
    availability_rules: Mapped[list["EmployeeAvailabilityRule"]] = relationship(back_populates="employee", cascade="all, delete-orphan")
    availability_exceptions: Mapped[list["EmployeeAvailabilityException"]] = relationship(back_populates="employee", cascade="all, delete-orphan")
    assignments: Mapped[list["ShiftAssignment"]] = relationship(back_populates="employee")

    def _loaded_employee_roles(self) -> list["EmployeeRole"]:
        state = inspect(self)
        if "employee_roles" in state.unloaded:
            return []
        return list(self.employee_roles or [])

    def _loaded_employee_locations(self) -> list["EmployeeLocation"]:
        state = inspect(self)
        if "employee_locations" in state.unloaded:
            return []
        return list(self.employee_locations or [])

    @property
    def primary_location_id(self) -> Optional[uuid.UUID]:
        employee_locations = self._loaded_employee_locations()
        for employee_location in employee_locations:
            if employee_location.is_primary:
                return employee_location.location_id
        if employee_locations:
            return employee_locations[0].location_id
        return None

    @property
    def primary_location_name(self) -> Optional[str]:
        employee_locations = self._loaded_employee_locations()
        for employee_location in employee_locations:
            if employee_location.is_primary:
                return employee_location.location_name
        if employee_locations:
            return employee_locations[0].location_name
        return None

    @property
    def primary_role_id(self) -> Optional[uuid.UUID]:
        employee_roles = self._loaded_employee_roles()
        for employee_role in employee_roles:
            if employee_role.is_primary:
                return employee_role.role_id
        if employee_roles:
            return employee_roles[0].role_id
        return None

    @property
    def primary_role_name(self) -> Optional[str]:
        employee_roles = self._loaded_employee_roles()
        for employee_role in employee_roles:
            if employee_role.is_primary:
                return employee_role.role_name
        if employee_roles:
            return employee_roles[0].role_name
        return None

    @property
    def role_ids(self) -> list[uuid.UUID]:
        return [employee_role.role_id for employee_role in self._loaded_employee_roles()]

    @property
    def role_names(self) -> list[str]:
        return [
            role_name
            for role_name in (
                employee_role.role_name for employee_role in self._loaded_employee_roles()
            )
            if role_name
        ]

    @property
    def location_ids(self) -> list[uuid.UUID]:
        return [employee_location.location_id for employee_location in self._loaded_employee_locations()]

    @property
    def location_names(self) -> list[str]:
        return [
            location_name
            for location_name in (
                employee_location.location_name
                for employee_location in self._loaded_employee_locations()
            )
            if location_name
        ]

    @property
    def roles(self) -> list["EmployeeRole"]:
        return self._loaded_employee_roles()

    @property
    def locations(self) -> list["EmployeeLocation"]:
        return self._loaded_employee_locations()


class EmployeeRole(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employee_roles"
    __table_args__ = (
        UniqueConstraint("employee_id", "role_id", name="uq_employee_roles_employee_id_role_id"),
        Index(
            "uq_employee_roles_employee_id_primary",
            "employee_id",
            unique=True,
            postgresql_where=text("is_primary = true"),
        ),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    proficiency_level: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    acquired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    role_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    employee: Mapped["Employee"] = relationship(back_populates="employee_roles")
    role: Mapped["Role"] = relationship(back_populates="employee_roles")

    @property
    def role_code(self) -> Optional[str]:
        state = inspect(self)
        if "role" in state.unloaded:
            return None
        return self.role.code if self.role is not None else None

    @property
    def role_name(self) -> Optional[str]:
        state = inspect(self)
        if "role" in state.unloaded:
            return None
        return self.role.name if self.role is not None else None


class EmployeeLocation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employee_locations"
    __table_args__ = (
        UniqueConstraint("employee_id", "location_id", name="uq_employee_locations_employee_id_location_id"),
        Index(
            "uq_employee_locations_employee_id_primary",
            "employee_id",
            unique=True,
            postgresql_where=text("is_primary = true"),
        ),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    access_level: Mapped[str] = mapped_column(String(32), nullable=False, server_default="approved")
    location_source: Mapped[Optional[str]] = mapped_column(String(64))
    can_cover_last_minute: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    can_blast: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    travel_radius_miles: Mapped[Optional[int]] = mapped_column(Integer)
    location_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    employee: Mapped["Employee"] = relationship(back_populates="employee_locations")
    location: Mapped["Location"] = relationship(back_populates="employee_locations")

    @property
    def location_name(self) -> Optional[str]:
        state = inspect(self)
        if "location" in state.unloaded:
            return None
        return self.location.display_name if self.location is not None else None

    @property
    def location_slug(self) -> Optional[str]:
        state = inspect(self)
        if "location" in state.unloaded:
            return None
        return self.location.slug if self.location is not None else None


class EmployeeScheduleAccessLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employee_schedule_access_links"
    __table_args__ = (
        UniqueConstraint("employee_id", name="uq_employee_schedule_access_links_employee_id"),
        Index("ix_employee_schedule_access_links_business_id", "business_id"),
        Index("ix_employee_schedule_access_links_revoked_at", "revoked_at"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    rotated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    link_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    business: Mapped["Business"] = relationship()
    employee: Mapped["Employee"] = relationship(back_populates="schedule_access_link")


class EmployeeAvailabilityRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employee_availability_rules"
    __table_args__ = (
        Index("ix_employee_availability_rules_employee_id_day_of_week", "employee_id", "day_of_week"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_local_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_local_time: Mapped[time] = mapped_column(Time, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    availability_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="available")
    valid_from: Mapped[Optional[date]] = mapped_column(Date)
    valid_until: Mapped[Optional[date]] = mapped_column(Date)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    availability_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    employee: Mapped["Employee"] = relationship(back_populates="availability_rules")


class EmployeeAvailabilityException(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employee_availability_exceptions"
    __table_args__ = (
        Index("ix_employee_availability_exceptions_employee_id_starts_at", "employee_id", "starts_at"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exception_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(64))
    reason: Mapped[Optional[str]] = mapped_column(Text)
    exception_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    employee: Mapped["Employee"] = relationship(back_populates="availability_exceptions")


from app.models.business import Business, Location, Role  # noqa: E402
from app.models.scheduling import ShiftAssignment  # noqa: E402
