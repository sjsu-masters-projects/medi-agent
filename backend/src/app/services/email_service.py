"""Verified opt-in delivery backed by atomic, server-only PostgreSQL operations."""

import asyncio
import hashlib
import hmac
import logging
import secrets
from typing import Any, cast
from uuid import uuid4

from postgrest.exceptions import APIError
from supabase import Client

from app.clients.resend import ResendClient
from app.config import settings
from app.core.exceptions import AuthorizationError, ExternalServiceError, ValidationError
from app.models.auth import CurrentUser
from app.models.email_preferences import EmailPreferences, EmailPreferencesRead
from app.services.email_templates import render_email, verification_email
from app.services.notification_centre_presentation import destination

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
logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self, db: Client, actor: CurrentUser) -> None:
        self.db, self.actor = db, actor

    async def _call(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return await email_rpc(
            self.db,
            "email_account_operation",
            {
                "p_actor_id": str(self.actor.id),
                "p_role": self.actor.role,
                "p_action": action,
                "p_payload": payload or {},
            },
        )

    async def preferences(self) -> EmailPreferencesRead:
        return EmailPreferencesRead.model_validate(await self._call("get"))

    async def save(self, preferences: EmailPreferences) -> EmailPreferencesRead:
        return EmailPreferencesRead.model_validate(
            await self._call("preferences", preferences.model_dump())
        )

    def _hash(self, code: str) -> str:
        # Codes are scoped to an authenticated account, bounded in DB and never logged.
        return hmac.new(
            settings.supabase_jwt_secret.encode(),
            f"email-contact/{self.actor.id}/{code}".encode(),
            hashlib.sha256,
        ).hexdigest()

    async def challenge(self) -> dict[str, Any]:
        account = await self.preferences()
        if account.synthetic:
            return {"status": "synthetic"}
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
        transport = ResendClient()
        if not transport.enabled or not transport.default_from_email:
            raise ExternalServiceError("Email", "Email delivery is unavailable. Try again later.")
        payload = transport.payload(
            verification_email(code, root.rstrip("/") + path, locale), account.email
        )
        result = await self._call(
            "challenge", {"hash": self._hash(code), "key": f"verify/{uuid4()}", "payload": payload}
        )
        if result.get("status") == "queued":
            try:
                await EmailDeliveryService(self.db).dispatch()
            except ExternalServiceError:
                logger.warning("Queued email retained; dispatch will retry")
        return result

    async def verify(self, code: str) -> dict[str, Any]:
        return await self._call("verify", {"hash": self._hash(code)})


async def email_rpc(db: Client, name: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        result = await asyncio.to_thread(db.rpc(name, params).execute)
    except APIError as exc:
        if exc.code == "42501":
            raise AuthorizationError("Email settings unavailable") from None
        if exc.code == "22023":
            raise ValidationError("Verify your email and check your preferences") from None
        raise ExternalServiceError(
            "Email", "Email settings unavailable. Try again later."
        ) from None
    if not isinstance(result.data, dict):
        raise ExternalServiceError("Email", "Email settings unavailable. Try again later.")
    return result.data


class EmailDeliveryService:
    def __init__(self, db: Client) -> None:
        self.db, self.transport = db, ResendClient()

    async def _call(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return await email_rpc(
            self.db, "email_delivery_operation", {"p_action": action, "p_payload": payload or {}}
        )

    def _payload(self, row: dict[str, Any]) -> dict[str, Any]:
        if isinstance(row.get("payload"), dict):
            return cast(dict[str, Any], row["payload"])
        event = row.get("event") or {}
        kind = event.get("event_type")
        if kind not in _COPY:
            raise ValueError("Unsupported email event")
        role = row["role"]
        spanish = role == "patient" and row.get("locale") == "es-MX"
        root = settings.patient_portal_url if role == "patient" else settings.clinician_portal_url
        path, action_en, action_es = destination(event, role)
        if kind in {"document_review", "care_plan_draft"}:
            path = "/alerts"
        if not path or not path.startswith("/") or path.startswith("//"):
            raise ValueError("Email destination unavailable")
        content = render_email(
            _COPY[kind][int(spanish)],
            [
                "Abre el portal para consultar la actualización guardada. Por privacidad, este correo no incluye información de salud."
                if spanish
                else "Open the portal to see the saved update. For privacy, this email does not include health details."
            ],
            action_url=root.rstrip("/") + path,
            action_label=action_es if spanish else action_en,
            locale="es-MX" if spanish else "en-US",
            note=(
                "Puedes cambiar los avisos opcionales en Preferencias de correo."
                if spanish
                else "You can change optional notices in Email preferences."
            ),
        )
        return self.transport.payload(content, row["email"])

    async def dispatch(self) -> dict[str, int]:
        counts = {"claimed": 0, "accepted": 0, "retry": 0, "delivered": 0, "bounced": 0}
        if not self.transport.enabled:
            return counts
        for row in (await self._call("claim")).get("items", []):
            counts["claimed"] += 1
            try:
                payload = self._payload(row)
            except ValueError:
                payload = None
            frozen = await self._call(
                "freeze", {"id": row["id"], "lease": row["lease"], "payload": payload}
            )
            provider = None
            if frozen.get("payload"):
                provider = await asyncio.to_thread(
                    self.transport.send, frozen["payload"], row["dedupe_key"]
                )
            await self._call(
                "finish", {"id": row["id"], "lease": row["lease"], "provider_id": provider}
            )
            counts["accepted" if provider else "retry"] += 1
        for row in (await self._call("accepted")).get("items", []):
            state = await asyncio.to_thread(self.transport.status, row["provider_id"])
            mapped = {
                "delivered": "delivered",
                "bounced": "bounced",
                "failed": "failed",
                "complained": "bounced",
            }.get(state or "", "accepted")
            await self._call("status", {**row, "state": mapped})
            if mapped in counts:
                counts[mapped] += 1
        return counts
