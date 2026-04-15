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
import threading
import time
from collections.abc import Callable
from typing import Any, TypedDict
from uuid import UUID

import httpx
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.models.auth import CurrentUser

logger = logging.getLogger(__name__)

# Supabase may sign JWTs with symmetric (HS256) or asymmetric (RS256/ES256) keys.
_LEGACY_ALGORITHM = "HS256"
_ASYMMETRIC_ALGORITHMS = {"RS256", "ES256"}
_JWKS_CACHE_TTL_SECONDS = 300


class JwksCacheState(TypedDict):
    keys: list[dict[str, Any]]
    expires_at: float


_jwks_cache_state: JwksCacheState = {"keys": [], "expires_at": 0.0}
_jwks_cache_lock = threading.Lock()

# HTTPBearer extracts the token from "Authorization: Bearer <token>"
_bearer_scheme = HTTPBearer(auto_error=False)


def _supabase_issuer() -> str:
    return f"{settings.supabase_url.rstrip('/')}/auth/v1"


def _coerce_jwks_keys(value: Any) -> list[dict[str, Any]]:
    """Return only dict-shaped keys from a JWKS payload value."""
    if not isinstance(value, list):
        return []

    return [item for item in value if isinstance(item, dict)]


def _load_jwks(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    """Load and cache Supabase JWKS for asymmetric token verification."""
    now = time.time()

    with _jwks_cache_lock:
        if (
            not force_refresh
            and _jwks_cache_state["keys"]
            and now < _jwks_cache_state["expires_at"]
        ):
            return _coerce_jwks_keys(_jwks_cache_state["keys"])

    url = f"{_supabase_issuer()}/.well-known/jwks.json"
    try:
        response = httpx.get(url, timeout=5.0)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.warning("Failed to fetch Supabase JWKS: %s", exc)
        with _jwks_cache_lock:
            if _jwks_cache_state["keys"]:
                return _coerce_jwks_keys(_jwks_cache_state["keys"])
        raise JWTError("Unable to load Supabase signing keys") from None

    keys = _coerce_jwks_keys(payload.get("keys") if isinstance(payload, dict) else None)

    with _jwks_cache_lock:
        _jwks_cache_state["keys"] = keys
        _jwks_cache_state["expires_at"] = now + _JWKS_CACHE_TTL_SECONDS

    return keys


def _find_jwks_key(kid: str) -> dict[str, Any] | None:
    """Locate signing key by key id, with one forced JWKS refresh fallback."""
    for force_refresh in (False, True):
        keys = _load_jwks(force_refresh=force_refresh)
        for key in keys:
            if isinstance(key, dict) and key.get("kid") == kid:
                return key
    return None


def _decode_supabase_token(token: str) -> dict[str, Any]:
    """Decode Supabase JWT supporting both legacy and asymmetric signing modes."""
    header = jwt.get_unverified_header(token)
    algorithm = header.get("alg")

    if algorithm == _LEGACY_ALGORITHM:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=[_LEGACY_ALGORITHM],
            audience="authenticated",
            issuer=_supabase_issuer(),
        )

    if algorithm in _ASYMMETRIC_ALGORITHMS:
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise JWTError("Token is missing key identifier")

        jwk_key = _find_jwks_key(kid)
        if not jwk_key:
            raise JWTError("Unable to find signing key for token")

        return jwt.decode(
            token,
            jwk_key,
            algorithms=[algorithm],
            audience="authenticated",
            issuer=_supabase_issuer(),
        )

    raise JWTError("Unsupported token signing algorithm")


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
        payload = _decode_supabase_token(token)
    except JWTError as e:
        logger.warning("JWT verification failed: %s", e)
        raise AuthenticationError("Invalid or expired token") from None

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


def require_role(role: str) -> Callable[..., Any]:
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


async def require_internal_admin_token(
    token: str | None = Header(default=None, alias="X-Internal-Admin-Token"),
) -> None:
    """Require a shared internal token for private operational endpoints."""
    configured_token = settings.internal_admin_token.strip()
    if not configured_token:
        raise AuthorizationError("Internal provisioning endpoint is disabled")

    if token is None or not hmac.compare_digest(token, configured_token):
        raise AuthorizationError("Invalid internal admin token")
