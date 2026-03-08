"""Patient schemas."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import Gender, Language


class PatientCreate(BaseModel):
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    date_of_birth: date
    gender: Gender | None = None
    preferred_language: Language = Language.EN


class PatientUpdate(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    gender: Gender | None = None
    preferred_language: Language | None = None
    avatar_url: str | None = None


class PatientRead(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: Gender | None = None
    preferred_language: Language = Language.EN
    phone: str | None = None
    avatar_url: str | None = None
    created_at: str
    updated_at: str | None = None
