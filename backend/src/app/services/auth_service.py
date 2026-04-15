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
from typing import Any, cast

from jose import jwt
from supabase import Client

from app.core.exceptions import AuthenticationError, ValidationError
from app.models.enums import ClinicianRole
from app.services.clinic_service import ClinicService

logger = logging.getLogger(__name__)
_SUPPORTED_ROLES = {"patient", "clinician"}


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
        auth_response = self._create_auth_user(email=email, password=password)

        if not auth_response.user:
            raise ValidationError(
                self._build_signup_validation_message(
                    getattr(auth_response, "error", None),
                )
            )

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
            self._delete_auth_user(user_id)
            raise ValidationError(f"Profile creation failed: {e}") from e

        try:
            return self._sign_in_and_format(
                email=email,
                password=password,
                expected_role="patient",
            )
        except Exception as e:
            logger.error("Failed to finalize patient signup for %s: %s", user_id, e)
            self._cleanup_signup("patients", user_id)
            raise

    async def signup_clinician(
        self,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        specialty: str,
        clinic_code: str,
        type1_npi: str | None = None,
        role: str = ClinicianRole.PROVIDER,
        *,
        allow_admin_role: bool = False,
    ) -> Any:
        """Create a clinician account: auth user + profile row."""
        role_value = role.value if isinstance(role, ClinicianRole) else str(role)

        allowed_roles = {
            ClinicianRole.PROVIDER.value,
            ClinicianRole.NURSE.value,
        }
        if allow_admin_role:
            allowed_roles.add(ClinicianRole.ADMIN.value)

        if role_value not in allowed_roles:
            raise ValidationError("Invalid clinician role")

        clinic = self._resolve_active_clinic(clinic_code)

        auth_response = self._create_auth_user(email=email, password=password)

        if not auth_response.user:
            raise ValidationError(
                self._build_signup_validation_message(
                    getattr(auth_response, "error", None),
                )
            )

        user_id = auth_response.user.id

        try:
            self.db.table("clinicians").insert(
                {
                    "id": user_id,
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "specialty": specialty,
                    "clinic_id": clinic["id"],
                    "clinic_name": clinic["display_name"],
                    "type1_npi": type1_npi,
                    "role": role_value,
                }
            ).execute()
        except Exception as e:
            logger.error("Failed to create clinician profile for %s: %s", user_id, e)
            self._delete_auth_user(user_id)
            raise ValidationError(f"Profile creation failed: {e}") from e

        try:
            return self._sign_in_and_format(
                email=email,
                password=password,
                expected_role="clinician",
            )
        except Exception as e:
            logger.error("Failed to finalize clinician signup for %s: %s", user_id, e)
            self._cleanup_signup("clinicians", user_id)
            raise

    async def signup_clinic_admin(
        self,
        *,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        specialty: str,
        clinic_name: str,
        type1_npi: str | None = None,
        type2_npi: str | None = None,
    ) -> Any:
        """Create a new clinic and bootstrap its first admin account."""
        clinic_service = ClinicService(self.db)
        clinic = await clinic_service.provision_clinic(clinic_name=clinic_name, type2_npi=type2_npi)

        try:
            return await self.signup_clinician(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                specialty=specialty,
                clinic_code=str(clinic["code"]),
                type1_npi=type1_npi,
                role=ClinicianRole.ADMIN,
                allow_admin_role=True,
            )
        except Exception:
            # Best-effort cleanup of orphan clinic if admin signup fails.
            try:
                self.db.table("clinics").delete().eq("id", str(clinic["id"])).execute()
            except Exception as cleanup_error:  # pragma: no cover - defensive branch
                logger.warning(
                    "Failed to rollback clinic %s after admin signup failure: %s",
                    clinic.get("id"),
                    cleanup_error,
                )
            raise

    # ── Login ───────────────────────────────────────────────

    async def login(self, email: str, password: str) -> Any:
        """Authenticate with email + password. Works for both roles."""
        return self._sign_in_and_format(email=email, password=password)

    # ── Token Refresh ───────────────────────────────────────

    async def refresh_token(
        self,
        refresh_token: str,
        expected_role: str | None = None,
    ) -> Any:
        """Exchange a refresh token for a new access token."""
        try:
            response = self.db.auth.refresh_session(refresh_token)
        except Exception as e:
            logger.warning("Token refresh failed: %s", e)
            raise AuthenticationError("Invalid or expired refresh token") from None

        return self._format_session(response, expected_role=expected_role)

    # ── Password Reset ──────────────────────────────────────

    async def request_password_reset(self, email: str) -> None:
        """Send a password reset email via Supabase."""
        try:
            self.db.auth.reset_password_email(email)
        except Exception as e:
            # Don't reveal whether the email exists — always return success
            logger.info("Password reset requested for %s: %s", email, e)

    # ── Helpers ─────────────────────────────────────────────

    def _sign_in_and_format(
        self,
        *,
        email: str,
        password: str,
        expected_role: str | None = None,
    ) -> Any:
        """Sign in with email/password and validate the returned role."""
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

        return self._format_session(response, expected_role=expected_role)

    def _cleanup_signup(self, profile_table: str, user_id: str) -> None:
        """Best-effort rollback for partially created signup records."""
        try:
            self.db.table(profile_table).delete().eq("id", user_id).execute()
        except Exception as e:
            logger.warning("Failed to delete %s profile for %s: %s", profile_table, user_id, e)

        self._delete_auth_user(user_id)

    def _create_auth_user(self, *, email: str, password: str) -> Any:
        """Create Supabase auth user and map SDK failures to ValidationError."""
        try:
            return self.db.auth.sign_up(
                {
                    "email": email,
                    "password": password,
                }
            )
        except Exception as e:
            logger.warning("Supabase signup failed for %s: %s", email, e)
            raise ValidationError(self._build_signup_validation_message(e)) from None

    def _resolve_active_clinic(self, clinic_code: str) -> dict[str, Any]:
        """Resolve clinic identity by code and enforce active status."""
        normalized_code = clinic_code.strip().upper()

        response = (
            self.db.table("clinics")
            .select("id, code, display_name, status")
            .eq("code", normalized_code)
            .execute()
        )

        clinics = [row for row in (response.data or []) if isinstance(row, dict)]
        if not clinics:
            raise ValidationError("Clinic code is invalid")

        clinic = cast("dict[str, Any]", clinics[0])
        if clinic.get("status") != "active":
            raise ValidationError("Clinic code is inactive")

        return clinic

    @staticmethod
    def _build_signup_validation_message(error: Any) -> str:
        """Generate client-safe signup error text from Supabase responses/exceptions."""
        detail = str(error).lower() if error else ""

        hook_hints = (
            "error running hook",
            "custom_access_token_hook",
            "access token hook",
        )
        if any(hint in detail for hint in hook_hints):
            return "Signup failed — Supabase access token hook is misconfigured"

        duplicate_hints = (
            "already registered",
            "already exists",
            "duplicate",
            "user already",
        )
        if any(hint in detail for hint in duplicate_hints):
            return "Signup failed — email is already registered"

        return "Signup failed — check email format or try a different email"

    def _delete_auth_user(self, user_id: str) -> None:
        """Best-effort auth cleanup without masking original failures."""
        try:
            self.db.auth.admin.delete_user(user_id)
        except Exception as e:
            logger.warning("Failed to delete auth user %s during rollback: %s", user_id, e)

    @staticmethod
    def _validate_role(role: str, expected_role: str | None = None) -> str:
        """Reject unknown roles and mismatched role expectations."""
        if role not in _SUPPORTED_ROLES:
            raise AuthenticationError("Authentication failed — invalid user role")
        if expected_role and role != expected_role:
            raise AuthenticationError(
                f"Authentication failed — expected '{expected_role}' role but received '{role}'"
            )
        return role

    @staticmethod
    def _extract_role_from_access_token(access_token: str | None) -> str | None:
        """Best-effort extraction of `user_role` from JWT claims."""
        if not access_token:
            return None

        try:
            claims = jwt.get_unverified_claims(access_token)
        except Exception:  # pragma: no cover - malformed tokens are handled by role validation
            return None

        role = claims.get("user_role")
        if isinstance(role, str) and role:
            return role
        return None

    @classmethod
    def _format_session(cls, response: Any, expected_role: str | None = None) -> Any:
        """Normalize Supabase auth response into our standard shape."""
        session = response.session
        user = response.user

        if not session or not user:
            raise AuthenticationError("Authentication failed — no session returned")

        role = cls._validate_role(
            (user.app_metadata or {}).get("user_role")
            or cls._extract_role_from_access_token(getattr(session, "access_token", None))
            or "unknown",
            expected_role,
        )

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
                "role": role,
                "created_at": user.created_at,
            },
        }
