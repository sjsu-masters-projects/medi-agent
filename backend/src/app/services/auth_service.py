"""Auth business logic — signup, login, token refresh.

This service owns the interaction with Supabase Auth and profile
creation. It has ZERO FastAPI imports — routers call it, tests
can instantiate it directly.

Design decisions:
    - Signup creates both an auth.users entry AND a profile row
      (patients or clinicians) in a single flow. This ensures the
      JWT claims hook can resolve the user_role immediately.
    - We use the admin client for profile creation because the user
      doesn't have a valid session yet at signup time.
    - Login and refresh are thin wrappers around the Supabase Auth SDK.
"""

from __future__ import annotations

import logging
from typing import Any

from supabase import Client

from app.core.exceptions import AuthenticationError, ValidationError

logger = logging.getLogger(__name__)


class AuthService:
    """Handles user authentication lifecycle.

    Injected with a Supabase admin client (bypasses RLS)
    so it can create profile rows during signup.
    """

    def __init__(self, db: Client) -> None:
        self.db = db

    # ── Signup ──────────────────────────────────────────────

    async def signup_patient(
        self,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        date_of_birth: str,
        preferred_language: str = "en",
    ) -> Any:
        """Create a patient account: auth user + profile row.

        Returns the Supabase session (access_token, refresh_token, user).
        """
        # 1. Create the auth user via Supabase Auth
        auth_response = self.db.auth.sign_up(
            {
                "email": email,
                "password": password,
            }
        )

        if not auth_response.user:
            raise ValidationError("Signup failed — check email format or try a different email")

        user_id = auth_response.user.id

        # 2. Insert the patient profile row (admin client bypasses RLS)
        try:
            self.db.table("patients").insert(
                {
                    "id": user_id,
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "date_of_birth": date_of_birth,
                    "preferred_language": preferred_language,
                }
            ).execute()
        except Exception as e:
            logger.error("Failed to create patient profile for %s: %s", user_id, e)
            # Clean up the orphaned auth user
            self.db.auth.admin.delete_user(user_id)
            raise ValidationError(f"Profile creation failed: {e}") from e

        return self._format_session(auth_response)

    async def signup_clinician(
        self,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        specialty: str,
        clinic_name: str,
        npi_number: str | None = None,
    ) -> Any:
        """Create a clinician account: auth user + profile row."""
        auth_response = self.db.auth.sign_up(
            {
                "email": email,
                "password": password,
            }
        )

        if not auth_response.user:
            raise ValidationError("Signup failed — check email format or try a different email")

        user_id = auth_response.user.id

        try:
            self.db.table("clinicians").insert(
                {
                    "id": user_id,
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "specialty": specialty,
                    "clinic_name": clinic_name,
                    "npi_number": npi_number,
                }
            ).execute()
        except Exception as e:
            logger.error("Failed to create clinician profile for %s: %s", user_id, e)
            self.db.auth.admin.delete_user(user_id)
            raise ValidationError(f"Profile creation failed: {e}") from e

        return self._format_session(auth_response)

    # ── Login ───────────────────────────────────────────────

    async def login(self, email: str, password: str) -> Any:
        """Authenticate with email + password. Works for both roles."""
        try:
            response = self.db.auth.sign_in_with_password(
                {
                    "email": email,
                    "password": password,
                }
            )
        except Exception as e:
            logger.warning("Login failed for %s: %s", email, e)
            raise AuthenticationError("Invalid email or password") from None

        return self._format_session(response)

    # ── Token Refresh ───────────────────────────────────────

    async def refresh_token(self, refresh_token: str) -> Any:
        """Exchange a refresh token for a new access token."""
        try:
            response = self.db.auth.refresh_session(refresh_token)
        except Exception as e:
            logger.warning("Token refresh failed: %s", e)
            raise AuthenticationError("Invalid or expired refresh token") from None

        return self._format_session(response)

    # ── Password Reset ──────────────────────────────────────

    async def request_password_reset(self, email: str) -> None:
        """Send a password reset email via Supabase."""
        try:
            self.db.auth.reset_password_email(email)
        except Exception as e:
            # Don't reveal whether the email exists — always return success
            logger.info("Password reset requested for %s: %s", email, e)

    # ── Helpers ─────────────────────────────────────────────

    @staticmethod
    def _format_session(response: Any) -> Any:
        """Normalize Supabase auth response into our standard shape."""
        session = response.session
        user = response.user

        if not session or not user:
            raise AuthenticationError("Authentication failed — no session returned")

        return {
            "tokens": {
                "access_token": session.access_token,
                "refresh_token": session.refresh_token,
                "token_type": "bearer",
                "expires_at": session.expires_at or 0,
            },
            "user": {
                "id": str(user.id),
                "email": user.email or "",
                "role": (user.app_metadata or {}).get("user_role", "unknown"),
                "created_at": user.created_at,
            },
        }
