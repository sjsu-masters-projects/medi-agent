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

import hashlib
import logging
import time
from typing import Any
from uuid import UUID

from jwt import PyJWTError as JWTError
from supabase import Client

from app.clients.supabase import create_anon_client
from app.config import settings
from app.core.exceptions import AuthenticationError, ExternalServiceError, ValidationError
from app.core.jwt_utils import decode_unverified_claims
from app.db.repositories import ClinicianRepository, ClinicRepository
from app.middleware.rate_limit import (
    password_reset_client_limiter,
    password_reset_email_limiter,
)
from app.models.enums import ClinicianRole, coerce_locale
from app.services.clinic_membership_service import ClinicMembershipService
from app.services.clinic_service import ClinicService
from app.services.email_invitation_service import EmailInvitationService
from app.services.mfa_service import MFAService

logger = logging.getLogger(__name__)
_SUPPORTED_ROLES = {"patient", "clinician"}
ACCOUNT_EXISTS_MESSAGE = (
    "This email already has a MediAgent clinician account. Sign in to add this clinic to it."
)


class AuthService:
    """Handles user authentication lifecycle.

    Injected with a Supabase admin client (bypasses RLS)
    so it can create profile rows during signup.
    """

    def __init__(self, db: Client, auth_client: Client | None = None) -> None:
        self.db = db
        self.auth_client = auth_client or create_anon_client()
        self.clinic_repo = ClinicRepository(self)
        self.clinician_repo = ClinicianRepository(self)
        self.memberships = ClinicMembershipService(self)

    # ── Signup ──────────────────────────────────────────────

    async def signup_patient(
        self,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        date_of_birth: str,
        preferred_language: str = "en-US",
    ) -> Any:
        """Create a patient account: auth user + profile row.

        Returns the Supabase session (access_token, refresh_token, user).
        """
        auth_response = self._create_auth_user(email=email, password=password)

        if not auth_response.user:
            raise ValidationError(
                self._build_signup_validation_message(
                    getattr(auth_response, "error", None),
                )
            )

        user_id = auth_response.user.id

        try:
            self.db.table("patients").insert(
                {
                    "id": user_id,
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "date_of_birth": date_of_birth,
                    "preferred_language": coerce_locale(preferred_language).value,
                }
            ).execute()
        except Exception as e:
            logger.error("Failed to create patient profile for %s: %s", user_id, e)
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
        clinic_code: str | None,
        type1_npi: str | None = None,
        role: str = ClinicianRole.PROVIDER,
        *,
        allow_admin_role: bool = False,
        invitation_token: str | None = None,
    ) -> Any:
        """Create a clinician account: auth user + profile row.

        With an invitation, the invitation decides clinic and role, and membership is
        claimed in the same request. If that claim fails the account is kept (signed
        in, ``invitation_status="pending"``) and can retry with Sign in to accept.
        """
        role_value = role.value if isinstance(role, ClinicianRole) else str(role)
        invitations = EmailInvitationService(self.db)
        if invitation_token:
            invitation = await invitations.preview(invitation_token)
            if str(invitation["email"]).strip().lower() != email.strip().lower():
                raise ValidationError("Use the email address this invitation was sent to.")
            role_value = str(invitation["role"])
            allow_admin_role = role_value == ClinicianRole.ADMIN.value

        allowed_roles = {
            ClinicianRole.PROVIDER.value,
            ClinicianRole.NURSE.value,
        }
        if allow_admin_role:
            allowed_roles.add(ClinicianRole.ADMIN.value)

        if role_value not in allowed_roles:
            raise ValidationError("Invalid clinician role")

        clinic = None if invitation_token else self._resolve_active_clinic(clinic_code or "")
        # One account per address: an existing clinician adds a clinic by signing in.
        if self.clinician_repo.list_by_email_any_case(email):
            raise ValidationError(ACCOUNT_EXISTS_MESSAGE, code="ACCOUNT_EXISTS")
        auth_response = self._create_auth_user(email=email, password=password)

        if not auth_response.user:
            raise ValidationError(
                self._build_signup_validation_message(
                    getattr(auth_response, "error", None),
                )
            )
        if getattr(auth_response.user, "identities", None) == []:
            # Auth answers an existing address (under email confirmation) with a user that has
            # no identities. It is not a new account: create nothing and delete nothing.
            raise ValidationError(ACCOUNT_EXISTS_MESSAGE, code="ACCOUNT_EXISTS")

        user_id = auth_response.user.id

        try:
            self.db.table("clinicians").insert(
                {
                    "id": user_id,
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "specialty": specialty,
                    "clinic_id": clinic["id"] if clinic else None,
                    "clinic_name": clinic["display_name"] if clinic else None,
                    "type1_npi": type1_npi,
                    "role": role_value if clinic else ClinicianRole.PROVIDER.value,
                }
            ).execute()
        except Exception as e:
            logger.error("Failed to create clinician profile for %s: %s", user_id, e)
            self._delete_auth_user(user_id)
            raise ValidationError(f"Profile creation failed: {e}") from e

        try:
            result = self._sign_in_and_format(
                email=email,
                password=password,
                expected_role="clinician",
            )
        except Exception as e:
            logger.error("Failed to finalize clinician signup for %s: %s", user_id, e)
            self._cleanup_signup("clinicians", user_id)
            raise

        if invitation_token:
            try:
                accepted = await invitations.accept(
                    UUID(str(user_id)), invitation_token, address=email
                )
                result["invitation_status"] = "accepted"
                result["clinic"] = accepted["clinic"]
            except Exception as e:
                # The account stays; deleting it would lose a valid signup on a retryable error.
                logger.warning("Invitation claim after signup deferred (%s)", type(e).__name__)
                result["invitation_status"] = "pending"
        return result

    async def accept_invitation_with_password(
        self,
        *,
        email: str,
        password: str,
        invitation_token: str,
        mfa_code: str | None = None,
    ) -> dict[str, Any]:
        """Claim an invitation for an existing clinician account without a portal session.

        Works for an account that cannot pass the normal sign-in yet (no active clinic). An
        account that already has an active clinic and a verified authenticator must sign in
        normally instead (``SIGN_IN_TO_ACCEPT``); one with no active clinic gives its current
        code here, so adding a clinic never skips the second factor. The temporary session is ended; the clinician
        then signs in normally, MFA included.
        """
        session = self._sign_in_and_format(
            email=email, password=password, expected_role="clinician"
        )
        try:
            tokens = session["tokens"]
            factors = self._list_verified_mfa_factors(
                tokens["access_token"], tokens["refresh_token"]
            )
            if factors:
                if self.memberships.active_memberships_sync(str(session["user"]["id"])):
                    # Adding a clinic to a working MFA account must pass the second factor
                    # at a normal sign-in, then accept from the signed-in session.
                    raise AuthenticationError(
                        "Sign in first, then open the invitation link again.",
                        code="SIGN_IN_TO_ACCEPT",
                    )
                if not mfa_code:
                    raise AuthenticationError(
                        "Enter the 6-digit code from your authenticator app to accept.",
                        code="MFA_CODE_REQUIRED",
                    )
                await MFAService().verify(
                    tokens["access_token"],
                    tokens["refresh_token"],
                    str(factors[0]["id"]),
                    mfa_code,
                )
            return await EmailInvitationService(self.db).accept(
                UUID(str(session["user"]["id"])), invitation_token
            )
        finally:
            try:
                self.auth_client.auth.sign_out({"scope": "local"})
            except Exception:
                logger.warning("Temporary invitation session cleanup failed")

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
        clinic = await clinic_service.provision_clinic(
            clinic_name=clinic_name,
            type2_npi=type2_npi,
        )

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
            try:
                self.db.table("clinics").delete().eq("id", str(clinic["id"])).execute()
            except Exception as cleanup_error:  # pragma: no cover
                logger.warning(
                    "Failed to rollback clinic %s after admin signup failure: %s",
                    clinic.get("id"),
                    cleanup_error,
                )
            raise

    # ── Login ───────────────────────────────────────────────

    async def login(
        self,
        email: str,
        password: str,
        clinic_code: str | None = None,
    ) -> Any:
        """Authenticate with email + password. Works for both roles."""
        response = self._sign_in_and_format(email=email, password=password)

        if response["user"]["role"] != "clinician":
            return {
                **response,
                "mfa_required": False,
                "mfa_factors": [],
                "requires_clinic_join": not self._has_active_care_team(response["user"]["id"]),
            }

        if clinic_code:
            # Deployed portals still send the verified code during rollout.
            self._assert_clinician_matches_clinic(response["user"]["id"], clinic_code)
        else:
            self._assert_clinician_can_sign_in(response["user"]["id"])
        factors = self._list_verified_mfa_factors(
            response["tokens"]["access_token"],
            response["tokens"]["refresh_token"],
        )
        return {
            **response,
            "mfa_required": bool(factors)
            and self._extract_aal(response["tokens"]["access_token"]) != "aal2",
            "mfa_factors": factors,
        }

    # ── Token Refresh ───────────────────────────────────────

    async def refresh_token(
        self,
        refresh_token: str,
        expected_role: str | None = None,
    ) -> Any:
        """Exchange a refresh token for a new access token."""
        try:
            response = self.auth_client.auth.refresh_session(refresh_token)
        except Exception as e:
            logger.warning("Token refresh failed: %s", e)
            raise AuthenticationError("Invalid or expired refresh token") from None

        return self._format_session(response, expected_role=expected_role)

    # ── Password Reset ──────────────────────────────────────

    async def request_password_reset(
        self,
        email: str,
        *,
        portal: str = "patient",
        locale: str = "en-US",
        client: str | None = None,
    ) -> None:
        """Send a password reset email via Supabase.

        Callers always receive the same neutral response; over the per-address or
        per-client limit the provider request is skipped.
        """
        address_key = hashlib.sha256(email.strip().lower().encode()).hexdigest()
        if (
            client is not None
            and not (await password_reset_client_limiter.check(f"reset-client:{client}")).allowed
        ):
            logger.warning("Password recovery request rate limited (client)")
            return
        if not (await password_reset_email_limiter.check(f"reset-email:{address_key}")).allowed:
            logger.warning("Password recovery request rate limited (address)")
            return
        try:
            base_url = (
                settings.clinician_portal_url
                if portal == "clinician"
                else settings.patient_portal_url
            )
            language = "en-US" if portal == "clinician" else coerce_locale(locale).value
            redirect_url = base_url.rstrip("/") + "/reset-password?lang=" + language
            self.auth_client.auth.reset_password_email(email, {"redirect_to": redirect_url})
        except Exception:
            # Neither provider diagnostics nor the address belongs in recovery logs.
            logger.warning("Password recovery delivery request failed")

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
            response = self.auth_client.auth.sign_in_with_password(
                {
                    "email": email,
                    "password": password,
                }
            )
        except Exception as e:
            logger.warning("Login failed for %s: %s", email, e)
            raise AuthenticationError("Invalid email or password") from None

        return self._format_session(response, expected_role=expected_role)

    def _has_active_care_team(self, patient_id: str) -> bool:
        """Return the tiny onboarding decision without exposing care-team data at login."""
        try:
            result = (
                self.db.table("care_teams")
                .select("id")
                .eq("patient_id", patient_id)
                .eq("status", "active")
                .limit(1)
                .execute()
            )
            return bool(result.data)
        except Exception:
            # Authentication must remain available if the optional onboarding lookup is delayed.
            logger.warning("Could not read care-team onboarding state for patient login")
            return True

    def _cleanup_signup(self, profile_table: str, user_id: str) -> None:
        """Best-effort rollback for partially created signup records."""
        try:
            self.db.table(profile_table).delete().eq("id", user_id).execute()
        except Exception as e:
            logger.warning(
                "Failed to delete %s profile for %s: %s",
                profile_table,
                user_id,
                e,
            )

        self._delete_auth_user(user_id)

    def _create_auth_user(self, *, email: str, password: str) -> Any:
        """Create Supabase auth user and map SDK failures to ValidationError."""
        try:
            return self.auth_client.auth.sign_up(
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
        clinics = self.clinic_repo.find_matching_by_code(clinic_code)
        if not clinics:
            raise ValidationError("Clinic code is invalid", code="CLINIC_CODE_INVALID")

        clinic = clinics[0]
        if clinic.get("status") != "active":
            raise ValidationError("Clinic code is inactive", code="CLINIC_CODE_INACTIVE")

        return clinic

    def _sign_in_profile(self, clinician_id: str) -> tuple[dict[str, Any], list[Any]]:
        """Load the clinician row and the active memberships the sign-in checks need."""
        try:
            profile = self.clinician_repo.get_context(clinician_id)
            memberships = self.memberships.active_memberships_sync(clinician_id)
        except (ValidationError, AuthenticationError):
            raise
        except Exception as e:
            logger.warning("Failed to verify clinician clinic context (%s)", type(e).__name__)
            raise ExternalServiceError("clinic lookup is temporarily unavailable") from None
        if not profile:
            raise AuthenticationError(
                "Clinician account is not linked to a clinic",
                code="CLINIC_CONTEXT_INVALID",
            )
        if not profile.get("clinic_id") and not profile.get("clinic_name") and not memberships:
            # Created from an invitation whose claim did not finish.
            raise AuthenticationError(
                "Finish joining your clinic: open your invitation email and choose "
                "Sign in to accept.",
                code="INVITATION_ACCEPTANCE_REQUIRED",
            )
        return profile, memberships

    def _assert_clinician_can_sign_in(self, clinician_id: str) -> None:
        """Sign in once: an active membership at any active clinic is enough (CLN-003)."""
        _profile, memberships = self._sign_in_profile(clinician_id)
        if memberships:
            return
        raise AuthenticationError(
            "Your account is not active at any clinic. Ask a clinic admin to invite you.",
            code="NO_ACTIVE_CLINIC",
        )

    def _assert_clinician_matches_clinic(
        self,
        clinician_id: str,
        clinic_code: str | None,
    ) -> None:
        """A client that sends a clinic code must name a clinic the clinician belongs to."""
        if not clinic_code:
            raise AuthenticationError(
                "Clinic code is required for clinician login",
                code="CLINIC_CONTEXT_INVALID",
            )

        clinic = self._resolve_active_clinic(clinic_code)
        # Clinics are compared by id against active memberships, never by name.
        _profile, memberships = self._sign_in_profile(clinician_id)
        if any(str(m.clinic_id) == str(clinic["id"]) for m in memberships):
            return
        raise AuthenticationError(
            "Clinician account does not belong to the selected clinic",
            code="CLINIC_CONTEXT_INVALID",
        )

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
    def _extract_aal(access_token: str) -> str:
        """Read the current MFA assurance level from the JWT."""
        try:
            claims = decode_unverified_claims(access_token)
        except JWTError:
            return "aal1"
        return str(claims.get("aal", "aal1"))

    @staticmethod
    def _list_verified_mfa_factors(
        access_token: str,
        refresh_token: str,
    ) -> list[dict[str, Any]]:
        """Return verified MFA factors for the just-authenticated user."""
        client = create_anon_client()
        try:
            client.auth.set_session(access_token, refresh_token)
            response = client.auth.mfa.list_factors()
        except Exception as e:
            logger.warning("Failed to determine MFA status after login: %s", e)
            raise AuthenticationError("Unable to determine MFA status") from None

        return [
            {
                "id": str(factor.id),
                "friendly_name": factor.friendly_name,
                "factor_type": factor.factor_type,
                "status": factor.status,
                "created_at": str(factor.created_at) if factor.created_at else None,
            }
            for factor in (response.totp or [])
            if factor.status == "verified"
        ]

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
            claims = decode_unverified_claims(access_token)
        except Exception:  # pragma: no cover
            return None

        role = claims.get("user_role")
        if isinstance(role, str) and role:
            return role
        return None

    @staticmethod
    def _resolve_expires_at(session: Any) -> int:
        """Return an absolute expiry in epoch seconds; never 0.

        Prefers the provider's ``expires_at``, then ``expires_in`` from now, then the
        access token's ``exp`` claim (read without verification, only for scheduling).
        """
        expires_at = getattr(session, "expires_at", None)
        if isinstance(expires_at, int | float) and expires_at > 0:
            return int(expires_at)
        expires_in = getattr(session, "expires_in", None)
        if isinstance(expires_in, int | float) and expires_in > 0:
            return int(time.time() + expires_in)
        token = getattr(session, "access_token", None)
        if token:
            try:
                exp = decode_unverified_claims(token).get("exp")
            except JWTError:
                exp = None
            if isinstance(exp, int | float) and exp > 0:
                return int(exp)
        raise AuthenticationError("Authentication failed — session has no expiry")

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
                "expires_at": cls._resolve_expires_at(session),
            },
            "user": {
                "id": str(user.id),
                "email": user.email or "",
                "role": role,
                "created_at": user.created_at,
            },
        }
