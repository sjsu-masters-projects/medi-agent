"""JWT verification and FastAPI auth dependencies.

Two dependencies for route protection:

    get_current_user  — any authenticated user (patient or clinician)
    require_role      — only users with a specific role

Usage:
    @router.get("/me")
    async def me(user: CurrentUser = Depends(get_current_user)):
        return user

    @router.get("/clinician-only")
    async def dashboard(user: CurrentUser = Depends(require_role("clinician"))):
        return {"welcome": user.email}
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

import httpx
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.models.auth import CurrentUser

logger = logging.getLogger(__name__)

# Supabase uses HS256 with the JWT secret from project settings.
ALGORITHM = "HS256"

# HTTPBearer extracts the token from "Authorization: Bearer <token>"
_bearer_scheme = HTTPBearer(auto_error=False)
_MFA_FACTOR_ENDPOINT = "/rest/v1/auth/factors"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    """Verify the JWT and return the authenticated user's identity.

    Raises AuthenticationError if the token is missing, expired, or invalid.
    """
    if credentials is None:
        raise AuthenticationError("Missing authorization header")

    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=[ALGORITHM],
            audience="authenticated",
        )
    except JWTError as e:
        logger.warning("JWT verification failed: %s", e)
        raise AuthenticationError("Invalid or expired token") from None

    # Extract claims — Supabase puts user ID in "sub"
    user_id = payload.get("sub")
    email = payload.get("email", "")
    role = payload.get("user_role", "unknown")
    aal = payload.get("aal", "aal1")

    if not user_id:
        raise AuthenticationError("Token missing user identity")

    return CurrentUser(
        id=UUID(user_id),
        email=email,
        role=role,
        aal=str(aal),
    )


async def _has_verified_mfa_factor(access_token: str) -> bool:
    """Check whether the current user already has a verified MFA factor."""
    headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {access_token}",
    }
    params = {
        "select": "id",
        "status": "eq.verified",
        "limit": "1",
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{settings.supabase_url.rstrip('/')}{_MFA_FACTOR_ENDPOINT}",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Unable to determine MFA factor state: %s", exc)
        raise AuthenticationError("Unable to determine MFA status") from None

    data = response.json()
    return isinstance(data, list) and len(data) > 0


def require_role(role: str, *, allow_unverified_mfa: bool = False) -> Callable[..., Any]:
    """Factory that creates a dependency requiring a specific user role.

    The returned dependency calls get_current_user first, then
    checks the role claim. Raises AuthorizationError if mismatched.
    """

    async def _check_role(
        user: CurrentUser = Depends(get_current_user),
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    ) -> CurrentUser:
        if user.role != role:
            raise AuthorizationError(
                f"This endpoint requires '{role}' role, but you are '{user.role}'"
            )
        if (
            role == "clinician"
            and not allow_unverified_mfa
            and user.aal != "aal2"
        ):
            if credentials is None:
                raise AuthenticationError("Missing authorization header")
            if await _has_verified_mfa_factor(credentials.credentials):
                raise AuthorizationError(
                    "MFA verification required before accessing clinician resources"
                )
        return user

    return _check_role


async def require_internal_admin_token(
    token: str | None = Header(default=None, alias="X-Internal-Admin-Token"),
) -> None:
    """Require a shared internal token for private operational endpoints."""
    configured_token = settings.internal_admin_token.strip()
    if not configured_token:
        raise AuthorizationError("Internal provisioning endpoint is disabled")

    if token is None or not hmac.compare_digest(token, configured_token):
        raise AuthorizationError("Invalid internal admin token")
