"""Clinic schemas for clinic-code resolution and clinic entities."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ClinicStatus


class ClinicCodeResolveRequest(BaseModel):
    """Public request for resolving clinician clinic context before auth."""

    clinic_code: str = Field(..., min_length=6, max_length=20)


class ClinicCodeResolveResponse(BaseModel):
    """Public response containing clinic context for clinician auth flows."""

    clinic_id: UUID
    clinic_code: str
    clinic_name: str
    status: ClinicStatus


class ClinicRead(BaseModel):
    """Canonical clinic entity read model."""

    id: UUID
    code: str
    display_name: str
    canonical_name: str
    type2_npi: str | None = None
    status: ClinicStatus = ClinicStatus.ACTIVE
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
