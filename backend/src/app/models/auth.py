"""Auth request/response schemas.

Keeps auth concerns cleanly separated from domain models
(patient.py, clinician.py). The router imports these for
request validation; the service returns these for responses.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import Language


# ── Requests ────────────────────────────────────────────────

class PatientSignupRequest(BaseModel):
    """Patient signup — creates auth user + patient profile."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    date_of_birth: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="ISO date: YYYY-MM-DD",
    )
    preferred_language: Language = Language.EN


class ClinicianSignupRequest(BaseModel):
    """Clinician signup — creates auth user + clinician profile."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    specialty: str = Field(..., min_length=1, max_length=100)
    clinic_name: str = Field(..., min_length=1, max_length=200)
    npi_number: str | None = Field(default=None, max_length=20)


class LoginRequest(BaseModel):
    """Email + password login — works for both patients and clinicians."""
    email: EmailStr
    password: str = Field(..., min_length=1)


class TokenRefreshRequest(BaseModel):
    """Exchange a refresh token for a new access token."""
    refresh_token: str = Field(..., min_length=1)


class PasswordResetRequest(BaseModel):
    """Request a password reset email."""
    email: EmailStr


# ── Responses ───────────────────────────────────────────────

class AuthTokens(BaseModel):
    """JWT pair returned on successful auth."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_at: int = Field(description="Unix timestamp when the access token expires")


class UserInfo(BaseModel):
    """Minimal user info returned on auth. NOT the full patient/clinician profile."""
    id: UUID
    email: str
    role: str = Field(description="'patient' or 'clinician'")
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    """Full auth response — tokens + user metadata."""
    tokens: AuthTokens
    user: UserInfo


# ── JWT Claims (internal) ──────────────────────────────────

class CurrentUser(BaseModel):
    """Extracted from a verified JWT — injected into route handlers via Depends().

    This is NOT a DB model. It's the minimal identity info we need
    to authorize a request without hitting the database.
    """
    id: UUID
    email: str
    role: str  # "patient" | "clinician" | "unknown"
