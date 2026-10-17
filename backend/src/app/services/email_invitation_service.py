"""Expiring addressed invitations; no membership changes merely from sending email."""

import hashlib
import logging
import secrets
from typing import Any
from uuid import UUID

from supabase import Client

from app.clients.resend import ResendClient
from app.config import settings
from app.core.exceptions import AuthorizationError, ValidationError
from app.services.clinic_membership_service import ClinicMembershipService
from app.services.email_service import (
    AccountNotFoundError,
    EmailDeliveryService,
    account_email,
    email_rpc,
)
from app.services.email_templates import render_email

logger = logging.getLogger(__name__)


class EmailInvitationService:
    def __init__(self, db: Client) -> None:
        self.db = db

    @staticmethod
    def token_hash(token: str) -> str:
        if not 32 <= len(token) <= 128:
            raise ValidationError(
                "This invitation is invalid or has expired. Ask your clinic admin for a new one."
            )
        return hashlib.sha256(token.encode()).hexdigest()

    async def operation(
        self, actor: UUID | None, action: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return await email_rpc(
            self.db,
            "clinician_email_invitation_operation",
            {"p_actor": str(actor) if actor else None, "p_action": action, "p_payload": payload},
        )

    async def history(self, actor: UUID, clinic_id: UUID | None = None) -> dict[str, Any]:
        """One clinic's invitation history: the named clinic or the admin's only clinic.

        Admin rights are the role held at that clinic (checked here and again in SQL).
        """
        membership = await ClinicMembershipService(self).acting_membership(
            actor, clinic_id, require_admin=True
        )
        if membership is None:
            raise AuthorizationError("Only a clinic admin can manage invitations.")
        return await self.operation(actor, "list", self._clinic(membership.clinic_id))

    @staticmethod
    def _clinic(clinic_id: UUID | None) -> dict[str, Any]:
        return {"clinic_id": str(clinic_id)} if clinic_id else {}

    async def revoke(self, actor: UUID, invitation_id: UUID) -> dict[str, Any]:
        return await self.operation(actor, "revoke", {"id": str(invitation_id)})

    async def create(
        self,
        actor: UUID,
        email: str,
        role: str,
        clinic_name: str,
        *,
        clinic_id: UUID | None = None,
    ) -> dict[str, Any]:
        transport = ResendClient()
        if not transport.deliverable(email):
            raise ValidationError("Use a real mailbox for a clinician invitation")
        token = secrets.token_urlsafe(32)
        clinic = " ".join(clinic_name.split())
        content = render_email(
            f"Invitation to join {clinic}",
            [
                f"You have been invited to join {clinic} as {role.replace('_', ' ').title()}.",
                (
                    "Open this link to create your clinician account. If you already have a "
                    "MediAgent Pro account, open the link and choose Sign in to accept."
                ),
                "This invitation expires in seven days. Sending or opening it does not change clinic access.",
            ],
            action_url=settings.clinician_portal_url.rstrip("/") + "/signup#invitation=" + token,
            action_label="Review clinic invitation",
            audience="clinician",
            # The invitation's own clinic, on the header line like every other email; the
            # subject already names it.
            clinic=clinic,
            clinic_in_subject=False,
        )
        result = await self.operation(
            actor,
            "create",
            {
                "email": email,
                "role": role,
                "hash": self.token_hash(token),
                "payload": transport.payload(content, email, onboarding=True),
                **self._clinic(clinic_id),
            },
        )
        outbox_id = result.pop("outbox_id", None)
        if result.get("status") == "queued" and outbox_id:
            # Send this invitation now; on failure it stays queued for the worker.
            try:
                result["email_sent"] = await EmailDeliveryService(self.db).send_now(str(outbox_id))
            except Exception as exc:
                logger.warning("Invitation email deferred to retry (%s)", type(exc).__name__)
        return result

    async def preview(self, token: str) -> dict[str, Any]:
        return await self.operation(None, "preview", {"hash": self.token_hash(token)})

    async def accept(
        self, actor: UUID, token: str, *, address: str | None = None
    ) -> dict[str, Any]:
        """Claim membership for ``actor``; the invited address must be the account's."""
        if address is None:
            try:
                address = await account_email(self.db, actor)
            except AccountNotFoundError:
                raise AuthorizationError("This invitation is no longer available.") from None
        result = await self.operation(
            actor,
            "accept",
            {"hash": self.token_hash(token), "account_email": address.strip().lower()},
        )
        return {
            "status": "accepted",
            "clinic": {
                "clinic_id": result.get("clinic_id"),
                "clinic_code": result.get("clinic_code"),
                "clinic_name": result.get("clinic_name"),
                "status": result.get("clinic_status") or "active",
            },
        }
