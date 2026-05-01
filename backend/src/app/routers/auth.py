"""Auth routes — signup, login, token refresh, current user.

Thin router — all business logic lives in AuthService.
Each endpoint validates input via Pydantic, delegates to the
service, and returns a structured response.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from supabase import Client

from app.core.security import get_current_user
from app.db.connection import get_db
from app.models.auth import (
    AuthLoginResponse,
    AuthResponse,
    AuthTokens,
    ClinicAdminSignupRequest,
    ClinicianSignupRequest,
    CurrentUser,
    LoginRequest,
    PasswordResetRequest,
    PatientSignupRequest,
    TokenRefreshRequest,
    UserInfo,
)
from app.services.auth_service import AuthService

router = APIRouter()


def _get_auth_service(db: Client = Depends(get_db)) -> AuthService:
    """Dependency injection — build AuthService with the DB client."""
    return AuthService(db)


# ── Signup ──────────────────────────────────────────────────


@router.post(
    "/signup/patient",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new patient",
    description="Creates a Supabase auth user and a patient profile row.",
)
async def signup_patient(
    body: PatientSignupRequest,
    service: AuthService = Depends(_get_auth_service),
) -> AuthResponse:
    result = await service.signup_patient(
        email=body.email,
        password=body.password,
        first_name=body.first_name,
        last_name=body.last_name,
        date_of_birth=body.date_of_birth,
        preferred_language=body.preferred_language.value,
    )
    return AuthResponse(
        tokens=AuthTokens(**result["tokens"]),
        user=UserInfo(**result["user"]),
    )


@router.post(
    "/signup/clinic-admin",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register clinic and first admin",
    description="Creates a clinic and provisions the first clinician account with admin role.",
)
async def signup_clinic_admin(
    body: ClinicAdminSignupRequest,
    service: AuthService = Depends(_get_auth_service),
) -> AuthResponse:
    result = await service.signup_clinic_admin(
        email=body.email,
        password=body.password,
        first_name=body.first_name,
        last_name=body.last_name,
        specialty=body.specialty,
        clinic_name=body.clinic_name,
        type1_npi=body.type1_npi,
        type2_npi=body.type2_npi,
    )
    return AuthResponse(
        tokens=AuthTokens(**result["tokens"]),
        user=UserInfo(**result["user"]),
    )


@router.post(
    "/signup/clinician",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new clinician",
    description="Creates a Supabase auth user and a clinician profile row.",
)
async def signup_clinician(
    body: ClinicianSignupRequest,
    service: AuthService = Depends(_get_auth_service),
) -> AuthResponse:
    result = await service.signup_clinician(
        email=body.email,
        password=body.password,
        first_name=body.first_name,
        last_name=body.last_name,
        specialty=body.specialty,
        clinic_code=body.clinic_code,
        type1_npi=body.type1_npi,
        role=body.role,
        allow_admin_role=body.role == "admin",
    )
    return AuthResponse(
        tokens=AuthTokens(**result["tokens"]),
        user=UserInfo(**result["user"]),
    )


# ── Login ───────────────────────────────────────────────────


@router.post(
    "/login",
    response_model=AuthLoginResponse,
    summary="Login with email + password",
    description="Works for both patients and clinicians.",
)
async def login(
    body: LoginRequest,
    service: AuthService = Depends(_get_auth_service),
) -> AuthLoginResponse:
    result = await service.login(
        email=body.email,
        password=body.password,
        clinic_code=body.clinic_code,
    )
    return AuthLoginResponse(
        tokens=AuthTokens(**result["tokens"]),
        user=UserInfo(**result["user"]),
        mfa_required=result.get("mfa_required", False),
        mfa_factors=result.get("mfa_factors", []),
    )


# ── Token Refresh ───────────────────────────────────────────


@router.post(
    "/refresh",
    response_model=AuthResponse,
    summary="Refresh access token",
    description="Exchange a refresh token for a new access + refresh token pair.",
)
async def refresh_token(
    body: TokenRefreshRequest,
    service: AuthService = Depends(_get_auth_service),
) -> AuthResponse:
    result = await service.refresh_token(
        body.refresh_token,
        expected_role=body.expected_role,
    )
    return AuthResponse(
        tokens=AuthTokens(**result["tokens"]),
        user=UserInfo(**result["user"]),
    )


# ── Password Reset ──────────────────────────────────────────


@router.post(
    "/password-reset",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    response_class=Response,
    summary="Request password reset email",
    description="Sends a reset link. Always returns 204 (doesn't reveal if email exists).",
)
async def password_reset(
    body: PasswordResetRequest,
    service: AuthService = Depends(_get_auth_service),
) -> None:
    await service.request_password_reset(body.email)


# ── Current User ────────────────────────────────────────────


@router.get(
    "/me",
    response_model=CurrentUser,
    summary="Get current authenticated user",
    description="Returns the user's identity from the JWT. Good for testing auth.",
)
async def get_me(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return user
