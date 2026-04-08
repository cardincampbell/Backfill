from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BusinessVertical(TimestampMixin, Base):
    __tablename__ = "business_verticals"

    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    type_mappings: Mapped[list["BusinessVerticalTypeMapping"]] = relationship(
        back_populates="business_vertical",
        cascade="all, delete-orphan",
    )
    role_archetypes: Mapped[list["BusinessVerticalRoleArchetype"]] = relationship(
        back_populates="business_vertical",
        cascade="all, delete-orphan",
    )


class BusinessVerticalTypeMapping(TimestampMixin, Base):
    __tablename__ = "business_vertical_type_mappings"
    __table_args__ = (
        Index(
            "ix_bvtm_vertical_active",
            "business_vertical_code",
            "is_active",
        ),
    )

    place_type: Mapped[str] = mapped_column(String(120), primary_key=True)
    business_vertical_code: Mapped[str] = mapped_column(
        ForeignKey("business_verticals.code", ondelete="CASCADE"),
        nullable=False,
    )
    subvertical_code: Mapped[Optional[str]] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    business_vertical: Mapped["BusinessVertical"] = relationship(back_populates="type_mappings")


class BusinessPlaceType(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "business_place_types"
    __table_args__ = (
        Index(
            "ix_business_place_types_business_id_location_id",
            "business_id",
            "location_id",
        ),
        Index(
            "ix_business_place_types_business_id_source_provider",
            "business_id",
            "source_provider",
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"),
    )
    source_provider: Mapped[str] = mapped_column(String(80), nullable=False, server_default="google_places")
    place_type: Mapped[str] = mapped_column(String(120), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    business: Mapped["Business"] = relationship(back_populates="place_types")
    location: Mapped[Optional["Location"]] = relationship(back_populates="place_types")


class BusinessRoleArchetype(TimestampMixin, Base):
    __tablename__ = "business_role_archetypes"

    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role_family: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    vertical_assignments: Mapped[list["BusinessVerticalRoleArchetype"]] = relationship(
        back_populates="business_role_archetype",
        cascade="all, delete-orphan",
    )


class BusinessVerticalRoleArchetype(TimestampMixin, Base):
    __tablename__ = "business_vertical_role_archetypes"
    __table_args__ = (
        Index(
            "ix_business_vertical_role_archetypes_vertical_code_is_active",
            "business_vertical_code",
            "is_active",
        ),
    )

    business_vertical_code: Mapped[str] = mapped_column(
        ForeignKey("business_verticals.code", ondelete="CASCADE"),
        primary_key=True,
    )
    business_role_code: Mapped[str] = mapped_column(
        ForeignKey("business_role_archetypes.code", ondelete="CASCADE"),
        primary_key=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    business_vertical: Mapped["BusinessVertical"] = relationship(back_populates="role_archetypes")
    business_role_archetype: Mapped["BusinessRoleArchetype"] = relationship(
        back_populates="vertical_assignments"
    )


from app.models.business import Business, Location  # noqa: E402
