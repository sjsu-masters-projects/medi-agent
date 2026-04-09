"""MFA routes — TOTP enrollment, verification, factor management.

All endpoints require clinician role authentication.
The raw access token is extracted from the Authorization header
and forwarded to the MFA service for Supabase session operations.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import require_role
from app.models.auth import CurrentUser
from app.models.mfa import (
    MFAEnrollRequest,
    MFAEnrollResponse,
    MFAFactorInfo,
    MFAFactorsResponse,
    MFAUnenrollRequest,
    MFAUnenrollResponse,
    MFAVerifyRequest,
    MFAVerifyResponse,
)
from app.services.mfa_service import MFAService

router = APIRouter()

_bearer = HTTPBearer(auto_error=False)


def _get_mfa_service() -> MFAService:
    return MFAService()


def _extract_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Extract raw JWT from the Authorization header."""
    if credentials is None:
        from app.core.exceptions import AuthenticationError

        raise AuthenticationError("Missing authorization header")
    return credentials.credentials


@router.post(
    "/enroll",
    response_model=MFAEnrollResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start TOTP MFA enrollment",
    description="Returns a QR code and secret for the authenticator app.",
)
async def mfa_enroll(
    body: MFAEnrollRequest,
    _user: CurrentUser = Depends(require_role("clinician")),
    token: str = Depends(_extract_token),
    service: MFAService = Depends(_get_mfa_service),
) -> MFAEnrollResponse:
    result = await service.enroll(token, body.friendly_name)
    return MFAEnrollResponse(**result)


@router.post(
    "/verify",
    response_model=MFAVerifyResponse,
    summary="Verify TOTP code to complete MFA setup",
    description="Submits a 6-digit code from the authenticator app.",
)
async def mfa_verify(
    body: MFAVerifyRequest,
    _user: CurrentUser = Depends(require_role("clinician")),
    token: str = Depends(_extract_token),
    service: MFAService = Depends(_get_mfa_service),
) -> MFAVerifyResponse:
    result = await service.verify(token, body.factor_id, body.code)
    return MFAVerifyResponse(**result)


@router.get(
    "/factors",
    response_model=MFAFactorsResponse,
    summary="List enrolled MFA factors",
)
async def mfa_list_factors(
    _user: CurrentUser = Depends(require_role("clinician")),
    token: str = Depends(_extract_token),
    service: MFAService = Depends(_get_mfa_service),
) -> MFAFactorsResponse:
    factors = await service.list_factors(token)
    return MFAFactorsResponse(factors=[MFAFactorInfo(**f) for f in factors])


@router.post(
    "/unenroll",
    response_model=MFAUnenrollResponse,
    summary="Remove an enrolled MFA factor",
)
async def mfa_unenroll(
    body: MFAUnenrollRequest,
    _user: CurrentUser = Depends(require_role("clinician")),
    token: str = Depends(_extract_token),
    service: MFAService = Depends(_get_mfa_service),
) -> MFAUnenrollResponse:
    result = await service.unenroll(token, body.factor_id)
    return MFAUnenrollResponse(**result)
