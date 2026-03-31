from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1)
    vertical: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = Field(default=None, description="E.164 format")
    contact_email: Optional[str] = None
    location_count_estimate: Optional[int] = Field(default=None, ge=1)


class Organization(OrganizationCreate):
    id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
