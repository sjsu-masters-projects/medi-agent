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

import logging
from typing import Callable
from uuid import UUID

from fastapi import Depends
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
        raise AuthenticationError("Invalid or expired token")

    # Extract claims — Supabase puts user ID in "sub"
    user_id = payload.get("sub")
    email = payload.get("email", "")
    role = payload.get("user_role", "unknown")

    if not user_id:
        raise AuthenticationError("Token missing user identity")

    return CurrentUser(
        id=UUID(user_id),
        email=email,
        role=role,
    )


def require_role(role: str) -> Callable:
    """Factory that creates a dependency requiring a specific user role.

    The returned dependency calls get_current_user first, then
    checks the role claim. Raises AuthorizationError if mismatched.
    """

    async def _check_role(
        user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if user.role != role:
            raise AuthorizationError(
                f"This endpoint requires '{role}' role, but you are '{user.role}'"
            )
        return user

    return _check_role
