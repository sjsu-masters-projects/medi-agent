"""Clinician schemas."""

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import ClinicianRole


class ClinicianCreate(BaseModel):
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    specialty: str = Field(..., min_length=1, max_length=100)
    clinic_name: str = Field(..., min_length=1, max_length=200)
    type1_npi: str | None = Field(default=None, pattern=r"^\d{10}$")
    role: ClinicianRole = ClinicianRole.PROVIDER


class ClinicianUpdate(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    specialty: str | None = None
    clinic_code: str | None = Field(default=None, min_length=6, max_length=20)
    clinic_name: str | None = None
    type1_npi: str | None = Field(default=None, pattern=r"^\d{10}$")
    avatar_url: str | None = None


class ClinicianRead(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str
    specialty: str
    clinic_name: str
    type1_npi: str | None = None
    role: ClinicianRole = ClinicianRole.PROVIDER
    avatar_url: str | None = None
    created_at: str
    updated_at: str | None = None
