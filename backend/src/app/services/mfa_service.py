"""MFA business logic — TOTP enrollment, verification, and management.

Uses Supabase Auth MFA APIs. Each call creates a user-scoped client
by setting the session from the caller's JWT, so MFA operations
run within the correct user context.
"""

from __future__ import annotations

import logging
from typing import Any

from jose import JWTError, jwt
from supabase import Client, create_client

from app.config import settings
from app.core.exceptions import AuthenticationError, ValidationError

logger = logging.getLogger(__name__)


class MFAService:
    """Handles TOTP MFA lifecycle for clinicians."""

    @staticmethod
    def _user_client(access_token: str, refresh_token: str) -> Client:
        """Create a Supabase client authenticated as the calling user."""
        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        client.auth.set_session(access_token, refresh_token)
        return client

    @staticmethod
    def _extract_expires_at(access_token: str, fallback: int | None = None) -> int:
        """Read the JWT expiry from the returned access token."""
        try:
            claims = jwt.get_unverified_claims(access_token)
        except JWTError:
            return fallback or 0
        exp = claims.get("exp")
        return int(exp) if exp is not None else (fallback or 0)

    async def enroll(
        self, access_token: str, refresh_token: str, friendly_name: str = "Authenticator"
    ) -> dict[str, Any]:
        """Start TOTP enrollment — returns a QR code URI and secret."""
        client = self._user_client(access_token, refresh_token)
        try:
            response = client.auth.mfa.enroll(
                {"factor_type": "totp", "friendly_name": friendly_name}
            )
        except Exception as e:
            logger.error("MFA enroll failed: %s", e)
            raise ValidationError(f"MFA enrollment failed: {e}") from e

        return {
            "factor_id": str(response.id),
            "totp": {
                "qr_code": response.totp.qr_code if response.totp else "",
                "secret": response.totp.secret if response.totp else "",
                "uri": response.totp.uri if response.totp else "",
            },
            "friendly_name": friendly_name,
        }

    async def verify(
        self, access_token: str, refresh_token: str, factor_id: str, code: str
    ) -> dict[str, Any]:
        """Complete enrollment by verifying a TOTP code."""
        client = self._user_client(access_token, refresh_token)
        try:
            challenge = client.auth.mfa.challenge({"factor_id": factor_id})
            response = client.auth.mfa.verify(
                {"factor_id": factor_id, "challenge_id": challenge.id, "code": code}
            )
        except Exception as e:
            logger.warning("MFA verify failed for factor %s: %s", factor_id, e)
            raise AuthenticationError("Invalid verification code") from None

        return {
            "access_token": response.access_token,
            "refresh_token": response.refresh_token,
            "expires_at": self._extract_expires_at(
                response.access_token,
                fallback=getattr(response, "expires_at", None),
            ),
            "token_type": "bearer",
        }

    async def list_factors(self, access_token: str, refresh_token: str) -> list[dict[str, Any]]:
        """List the user's enrolled MFA factors."""
        client = self._user_client(access_token, refresh_token)
        try:
            response = client.auth.mfa.list_factors()
        except Exception as e:
            logger.error("MFA list_factors failed: %s", e)
            raise ValidationError(f"Could not list MFA factors: {e}") from e

        return [
            {
                "id": str(f.id),
                "friendly_name": f.friendly_name,
                "factor_type": f.factor_type,
                "status": f.status,
                "created_at": str(f.created_at) if f.created_at else None,
            }
            for f in (response.totp or [])
        ]

    async def unenroll(
        self, access_token: str, refresh_token: str, factor_id: str
    ) -> dict[str, str]:
        """Remove an enrolled MFA factor."""
        client = self._user_client(access_token, refresh_token)
        try:
            client.auth.mfa.unenroll({"factor_id": factor_id})
        except Exception as e:
            logger.error("MFA unenroll failed for %s: %s", factor_id, e)
            raise ValidationError(f"Could not remove MFA factor: {e}") from e

        return {"status": "removed", "factor_id": factor_id}
