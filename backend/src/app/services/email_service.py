"""Verified opt-in delivery backed by atomic, server-only PostgreSQL operations."""

import asyncio
import hashlib
import hmac
import logging
import secrets
from collections.abc import Callable
from typing import Any, cast
from uuid import UUID, uuid4

from postgrest.exceptions import APIError
from supabase import Client

from app.clients.resend import ResendClient
from app.config import settings
from app.core.exceptions import (
    AuthorizationError,
    ExternalServiceError,
    MediAgentError,
    ServiceUnavailableError,
    ValidationError,
)
from app.models.auth import CurrentUser
from app.models.email_preferences import EmailPreferences, EmailPreferencesRead
from app.services.email_templates import render_email, verification_email

_COPY = {
    "message_received": ("New care-team messages", "Nuevos mensajes del equipo de atención"),
    "appointment_offered": ("Appointment choices available", "Horarios de cita disponibles"),
    "appointment_changed": ("Appointment updated", "Cita actualizada"),
    "appointment_response": ("Appointment response received", "Respuesta a la cita recibida"),
    "care_plan_published": ("Your care plan was updated", "Tu plan de cuidado se actualizó"),
    "document_failed": ("A document needs your attention", "Un documento necesita tu atención"),
    "adr_information_requested": (
        "Your care team requested information",
        "Tu equipo de atención solicita información",
    ),
    "document_review": ("Review work available", "Revisión pendiente"),
    "care_plan_draft": ("Review work available", "Revisión pendiente"),
}

# Provider ``last_event`` values. Opens and clicks imply delivery. A complaint is
# recorded separately and is never reported as a bounce. Anything else (sent, queued,
# scheduled, delivery_delayed, unknown) stays "accepted": acceptance is not delivery.
PROVIDER_STATUS = {
    "delivered": "delivered",
    "opened": "delivered",
    "clicked": "delivered",
    "bounced": "bounced",
    "failed": "failed",
    "canceled": "failed",
    "complained": "complained",
}

# PostgREST/PostgreSQL codes for a function, table or column that does not exist yet:
# the email migrations have not been applied to this database.
_SETUP_PENDING_CODES = {"PGRST202", "PGRST204", "PGRST205", "42883", "42P01", "42703"}


def _authorization(message: str) -> MediAgentError:
    return AuthorizationError(message)


def _validation(message: str) -> MediAgentError:
    return ValidationError(message)


# Stable hints raised by the email SQL operations, mapped to accurate public copy.
_ERRORS: dict[str, tuple[Callable[[str], MediAgentError], str]] = {
    "email_unavailable": (_authorization, "Email settings are unavailable for this account."),
    "verify_first": (_validation, "Verify your email before choosing optional notices."),
    "invalid_preferences": (_validation, "Those email preferences are not supported."),
    "clinician_only": (_validation, "Review reminders are available to clinicians only."),
    "invalid_operation": (_validation, "That email request is not supported."),
    "admin_required": (_authorization, "Only a clinic admin can manage invitations."),
    "clinic_unavailable": (_authorization, "This clinic is not active."),
    "invitation_invalid": (
        _validation,
        "This invitation is invalid or has expired. Ask your clinic admin for a new one.",
    ),
    "invitation_unavailable": (_authorization, "This invitation is no longer available."),
    "invitation_wrong_account": (
        _authorization,
        "This invitation was sent to a different email address. "
        "Use the account for the invited address.",
    ),
    "existing_membership": (
        _validation,
        "This clinician already belongs to a clinic. An invitation cannot move them.",
    ),
    "synthetic_address": (_validation, "Demo login addresses cannot receive email."),
    "invalid_address": (_validation, "Enter a valid email address."),
}

logger = logging.getLogger(__name__)


class EmailSetupPendingError(ServiceUnavailableError):
    """The email schema is not installed in this database yet."""

    def __init__(self) -> None:
        super().__init__(
            "Email features are not available yet. Try again later.",
            code="EMAIL_SETUP_PENDING",
        )


async def email_rpc(db: Client, name: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        result = await asyncio.to_thread(db.rpc(name, params).execute)
    except APIError as exc:
        if exc.code in _SETUP_PENDING_CODES:
            raise EmailSetupPendingError() from None
        mapped = _ERRORS.get(str(exc.hint or ""))
        if mapped:
            factory, message = mapped
            raise factory(message) from None
        if exc.code == "42501":
            raise AuthorizationError("Email settings unavailable") from None
        if exc.code == "22023":
            raise ValidationError("That email request is not supported.") from None
        raise ExternalServiceError(
            "Email", "Email settings unavailable. Try again later."
        ) from None
    except Exception as exc:
        # Network timeouts and transport errors: keep provider/database text out of logs.
        logger.warning("Email database operation unavailable (%s)", type(exc).__name__)
        raise ExternalServiceError(
            "Email", "Email settings unavailable. Try again later."
        ) from None
    if not isinstance(result.data, dict):
        raise ExternalServiceError("Email", "Email settings unavailable. Try again later.")
    return result.data


class AccountNotFoundError(Exception):
    """Auth no longer has this account."""


async def account_email(db: Client, user_id: UUID | str) -> str:
    """The current Auth address, read through the Admin API rather than the auth schema."""
    try:
        response = await asyncio.to_thread(db.auth.admin.get_user_by_id, str(user_id))
    except Exception as exc:
        if getattr(exc, "status", None) == 404:
            raise AccountNotFoundError() from None
        logger.warning("Account address lookup unavailable (%s)", type(exc).__name__)
        raise ExternalServiceError(
            "Email", "Email settings unavailable. Try again later."
        ) from None
    email = getattr(getattr(response, "user", None), "email", None)
    if not isinstance(email, str) or "@" not in email:
        raise AccountNotFoundError()
    return email.strip().lower()


def idempotency_key(row: dict[str, Any]) -> str:
    """Stable per logical email and generation; carries no user or record identifiers."""
    material = f"{row['dedupe_key']}/{int(row.get('generation') or 0)}"
    return "mediagent-email-" + hashlib.sha256(material.encode()).hexdigest()


class EmailService:
    def __init__(self, db: Client, actor: CurrentUser) -> None:
        self.db, self.actor = db, actor
        self._address: str | None = None

    async def _account_email(self) -> str:
        if self._address is None:
            try:
                self._address = await account_email(self.db, self.actor.id)
            except AccountNotFoundError:
                raise AuthorizationError("Email settings unavailable") from None
        return self._address

    async def _call(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        address = await self._account_email()
        return await email_rpc(
            self.db,
            "email_account_operation",
            {
                "p_actor_id": str(self.actor.id),
                "p_role": self.actor.role,
                "p_action": action,
                "p_payload": {**(payload or {}), "account_email": address},
            },
        )

    async def preferences(self) -> EmailPreferencesRead:
        try:
            return EmailPreferencesRead.model_validate(await self._call("get"))
        except EmailSetupPendingError:
            # Shown calmly by both portals until the email migrations are applied.
            return EmailPreferencesRead(
                email=self.actor.email or "",
                verified=False,
                synthetic=False,
                preferences=EmailPreferences(),
                available=False,
            )

    async def save(self, preferences: EmailPreferences) -> EmailPreferencesRead:
        return EmailPreferencesRead.model_validate(
            await self._call("preferences", preferences.model_dump())
        )

    def _hash(self, code: str) -> str:
        # Codes are scoped to an authenticated account, bounded in DB and never logged.
        secret = settings.email_code_hmac_secret or settings.supabase_jwt_secret
        return hmac.new(
            secret.encode(),
            f"email-contact/{self.actor.id}/{code}".encode(),
            hashlib.sha256,
        ).hexdigest()

    async def challenge(self) -> dict[str, Any]:
        account = await self.preferences()
        if not account.available:
            raise EmailSetupPendingError()
        if account.synthetic:
            return {"status": "synthetic"}
        transport = ResendClient()
        if not transport.enabled or not transport.default_from_email:
            raise ServiceUnavailableError("Email verification is unavailable. Try again later.")
        code = f"{secrets.randbelow(1000000):06d}"
        locale = "en-US"
        if self.actor.role == "patient":
            profile = await asyncio.to_thread(
                self.db.table("patients")
                .select("preferred_language")
                .eq("id", str(self.actor.id))
                .single()
                .execute
            )
            if isinstance(profile.data, dict):
                locale = str(profile.data.get("preferred_language", "en-US"))
        root = (
            settings.patient_portal_url
            if self.actor.role == "patient"
            else settings.clinician_portal_url
        )
        path = "/profile" if self.actor.role == "patient" else "/settings"
        payload = transport.payload(
            verification_email(code, root.rstrip("/") + path, locale), account.email
        )
        result = await self._call(
            "challenge", {"hash": self._hash(code), "key": f"verify/{uuid4()}", "payload": payload}
        )
        status = str(result.get("status") or "")
        if status == "queued" and result.get("outbox_id"):
            # Send only this account's new code now. A failure stays queued for the
            # scheduled worker; this request never processes anyone else's mail.
            try:
                await EmailDeliveryService(self.db).send_now(str(result["outbox_id"]))
            except Exception as exc:
                logger.warning("Verification email deferred to retry (%s)", type(exc).__name__)
        return {"status": status}

    async def verify(self, code: str) -> dict[str, Any]:
        return await self._call("verify", {"hash": self._hash(code)})


class EmailDeliveryService:
    _missing_sender_logged = False

    def __init__(self, db: Client) -> None:
        self.db, self.transport = db, ResendClient()
        self._addresses: dict[str, str | None] = {}

    async def _call(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return await email_rpc(
            self.db, "email_delivery_operation", {"p_action": action, "p_payload": payload or {}}
        )

    def kinds(self) -> list[str]:
        """Mail kinds that have a configured sender. Others stay queued, unclaimed."""
        kinds: list[str] = []
        if self.transport.default_from_email:
            kinds += ["verification", "notice"]
        if self.transport.clinician_onboarding_from_email:
            kinds.append("invitation")
        if (
            self.transport.enabled
            and not self.transport.default_from_email
            and not EmailDeliveryService._missing_sender_logged
        ):
            EmailDeliveryService._missing_sender_logged = True
            logger.warning(
                "RESEND_FROM_EMAIL is not set; verification and notice email stay queued"
            )
        return kinds

    def _payload(self, row: dict[str, Any]) -> dict[str, Any]:
        if isinstance(row.get("payload"), dict):
            return cast(dict[str, Any], row["payload"])
        event = row.get("event") or {}
        kind = event.get("event_type")
        if kind not in _COPY:
            raise ValueError("Unsupported email event")
        role = row["role"]
        spanish = role == "patient" and row.get("locale") == "es-MX"
        # Links carry no record identifiers. The authenticated in-app centre routes on.
        if role == "patient":
            root, path = settings.patient_portal_url, "/notifications"
            label = "Abrir notificaciones" if spanish else "Open notifications"
        else:
            root, path, label = settings.clinician_portal_url, "/alerts", "Open alerts"
        content = render_email(
            _COPY[kind][int(spanish)],
            [
                "Abre el portal para consultar la actualización guardada. Por privacidad, este correo no incluye información de salud."
                if spanish
                else "Open the portal to see the saved update. For privacy, this email does not include health details."
            ],
            action_url=root.rstrip("/") + path,
            action_label=label,
            locale="es-MX" if spanish else "en-US",
            note=(
                "Puedes cambiar los avisos opcionales en Preferencias de correo."
                if spanish
                else "You can change optional notices in Email preferences."
            ),
        )
        return self.transport.payload(content, row["email"])

    async def _address(self, user_id: str) -> str | None:
        if user_id not in self._addresses:
            try:
                self._addresses[user_id] = await account_email(self.db, user_id)
            except AccountNotFoundError:
                self._addresses[user_id] = None
        return self._addresses[user_id]

    @staticmethod
    def _counts() -> dict[str, int]:
        return {
            "claimed": 0,
            "accepted": 0,
            "retry": 0,
            "stopped": 0,
            "errors": 0,
            "status_checked": 0,
            "delivered": 0,
            "bounced": 0,
            "failed": 0,
            "complained": 0,
        }

    async def dispatch(self) -> dict[str, int]:
        counts = self._counts()
        if not self.transport.enabled:
            return counts
        kinds = self.kinds()
        if kinds:
            for row in (await self._call("claim", {"kinds": kinds})).get("items", []):
                await self._deliver(row, counts)
        await self._reconcile(counts)
        return counts

    async def send_now(self, outbox_id: str) -> bool:
        """Send one just-created row; on any failure it stays queued for the worker."""
        kinds = self.kinds() if self.transport.enabled else []
        if not kinds:
            return False
        counts = self._counts()
        claimed = await self._call("claim", {"id": outbox_id, "kinds": kinds})
        for row in claimed.get("items", []):
            await self._deliver(row, counts)
        return counts["accepted"] > 0

    async def pending(self) -> dict[str, int]:
        """Read-only counts for a dry run; nothing is claimed or sent."""
        result = await self._call("pending")
        return {
            "due": int(result.get("due") or 0),
            "awaiting_status": int(result.get("awaiting_status") or 0),
        }

    async def _deliver(self, row: dict[str, Any], counts: dict[str, int]) -> None:
        counts["claimed"] += 1
        try:
            try:
                payload: dict[str, Any] | None = self._payload(row)
            except ValueError:
                payload = None
            request: dict[str, Any] = {"id": row["id"], "lease": row["lease"], "payload": payload}
            if row.get("user_id"):
                request["account_email"] = await self._address(str(row["user_id"])) or ""
            frozen = await self._call("freeze", request)
            if not frozen.get("payload"):
                counts["stopped"] += 1
                return
            provider = await asyncio.to_thread(
                self.transport.send, frozen["payload"], idempotency_key(row)
            )
            await self._call(
                "finish", {"id": row["id"], "lease": row["lease"], "provider_id": provider}
            )
            counts["accepted" if provider else "retry"] += 1
        except Exception as exc:
            # The lease expires and the row is retried with the same idempotency key.
            counts["errors"] += 1
            logger.warning("Email delivery deferred (%s)", type(exc).__name__)

    async def _reconcile(self, counts: dict[str, int]) -> None:
        if not self.transport.status_available():
            return
        for row in (await self._call("accepted")).get("items", []):
            event = await asyncio.to_thread(self.transport.status, row["provider_id"])
            if not self.transport.status_available():
                return
            mapped = PROVIDER_STATUS.get(event or "", "accepted")
            try:
                await self._call("status", {**row, "state": mapped})
            except Exception as exc:
                counts["errors"] += 1
                logger.warning("Email status update deferred (%s)", type(exc).__name__)
                continue
            counts["status_checked"] += 1
            if mapped != "accepted":
                counts[mapped] += 1
