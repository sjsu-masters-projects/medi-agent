"""JWT auth dependency for protecting routes."""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import AuthenticationError

security_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> dict:
    """Validate JWT from Authorization header, return decoded claims."""
    token = credentials.credentials
    if not token:
        raise AuthenticationError("Missing token")

    # TODO: Supabase JWT verification (JWKS or service-role key)
    raise AuthenticationError("JWT verification not implemented yet")
