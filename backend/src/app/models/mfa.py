"""MFA request/response schemas for TOTP enrollment and verification."""

from __future__ import annotations

from pydantic import BaseModel, Field

# ── Requests ────────────────────────────────────────────────


class MFAEnrollRequest(BaseModel):
    """Start TOTP enrollment with an optional friendly name."""

    friendly_name: str = Field(default="Authenticator", max_length=100)


class MFAVerifyRequest(BaseModel):
    """Verify a TOTP code to complete enrollment or authenticate."""

    factor_id: str = Field(..., min_length=1)
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class MFAUnenrollRequest(BaseModel):
    """Remove an enrolled MFA factor."""

    factor_id: str = Field(..., min_length=1)


# ── Responses ───────────────────────────────────────────────


class TOTPDetails(BaseModel):
    """TOTP setup details returned during enrollment."""

    qr_code: str = Field(description="Data URI of the QR code image")
    secret: str = Field(description="Base32 secret for manual entry")
    uri: str = Field(description="otpauth:// URI")


class MFAEnrollResponse(BaseModel):
    """Returned after starting TOTP enrollment."""

    factor_id: str
    totp: TOTPDetails
    friendly_name: str


class MFAVerifyResponse(BaseModel):
    """Returned after successful TOTP verification — upgraded tokens."""

    access_token: str
    refresh_token: str
    expires_at: int
    token_type: str = "bearer"


class MFAFactorInfo(BaseModel):
    """Summary of one enrolled MFA factor."""

    id: str
    friendly_name: str | None
    factor_type: str
    status: str
    created_at: str | None


class MFAFactorsResponse(BaseModel):
    """List of enrolled factors."""

    factors: list[MFAFactorInfo]


class MFAUnenrollResponse(BaseModel):
    """Confirmation of factor removal."""

    status: str
    factor_id: str
