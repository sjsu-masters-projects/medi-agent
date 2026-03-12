"""Auth routes — signup, login, token refresh, current user.

Thin router — all business logic lives in AuthService.
Each endpoint validates input via Pydantic, delegates to the
service, and returns a structured response.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from supabase import Client

from app.core.security import get_current_user
from app.db.connection import get_db
from app.models.auth import (
    AuthResponse,
    AuthTokens,
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
        clinic_name=body.clinic_name,
        npi_number=body.npi_number,
    )
    return AuthResponse(
        tokens=AuthTokens(**result["tokens"]),
        user=UserInfo(**result["user"]),
    )


# ── Login ───────────────────────────────────────────────────


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Login with email + password",
    description="Works for both patients and clinicians.",
)
async def login(
    body: LoginRequest,
    service: AuthService = Depends(_get_auth_service),
) -> AuthResponse:
    result = await service.login(email=body.email, password=body.password)
    return AuthResponse(
        tokens=AuthTokens(**result["tokens"]),
        user=UserInfo(**result["user"]),
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
    result = await service.refresh_token(body.refresh_token)
    return AuthResponse(
        tokens=AuthTokens(**result["tokens"]),
        user=UserInfo(**result["user"]),
    )


# ── Password Reset ──────────────────────────────────────────


@router.post(
    "/password-reset",
    status_code=status.HTTP_204_NO_CONTENT,
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
