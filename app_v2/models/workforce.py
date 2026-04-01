from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text, Time, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app_v2.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app_v2.models.common import EmployeeStatus


class Employee(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("business_id", "external_ref", name="uq_employees_business_id_external_ref"),
        Index("ix_employees_business_id_status", "business_id", "status"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    home_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
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
    home_location: Mapped[Optional["Location"]] = relationship()
    employee_roles: Mapped[list["EmployeeRole"]] = relationship(back_populates="employee", cascade="all, delete-orphan")
    clearances: Mapped[list["EmployeeLocationClearance"]] = relationship(back_populates="employee", cascade="all, delete-orphan")
    availability_rules: Mapped[list["EmployeeAvailabilityRule"]] = relationship(back_populates="employee", cascade="all, delete-orphan")
    availability_exceptions: Mapped[list["EmployeeAvailabilityException"]] = relationship(back_populates="employee", cascade="all, delete-orphan")
    assignments: Mapped[list["ShiftAssignment"]] = relationship(back_populates="employee")


class EmployeeRole(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employee_roles"
    __table_args__ = (
        UniqueConstraint("employee_id", "role_id", name="uq_employee_roles_employee_id_role_id"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    proficiency_level: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    acquired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    role_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    employee: Mapped["Employee"] = relationship(back_populates="employee_roles")
    role: Mapped["Role"] = relationship(back_populates="employee_roles")


class EmployeeLocationClearance(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employee_location_clearances"
    __table_args__ = (
        UniqueConstraint("employee_id", "location_id", name="uq_employee_location_clearances_employee_id_location_id"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    access_level: Mapped[str] = mapped_column(String(32), nullable=False, server_default="approved")
    clearance_source: Mapped[Optional[str]] = mapped_column(String(64))
    can_cover_last_minute: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    can_blast: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    travel_radius_miles: Mapped[Optional[int]] = mapped_column(Integer)
    clearance_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict)

    employee: Mapped["Employee"] = relationship(back_populates="clearances")
    location: Mapped["Location"] = relationship(back_populates="clearances")


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


from app_v2.models.business import Business, Location, Role  # noqa: E402
from app_v2.models.scheduling import ShiftAssignment  # noqa: E402
