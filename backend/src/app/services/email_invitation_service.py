"""Expiring addressed invitations; no membership changes merely from sending email."""

import hashlib
import secrets
from typing import Any
from uuid import UUID

from supabase import Client

from app.clients.resend import ResendClient
from app.config import settings
from app.core.exceptions import ValidationError
from app.services.email_service import email_rpc
from app.services.email_templates import render_email


class EmailInvitationService:
    def __init__(self, db: Client) -> None:
        self.db = db

    @staticmethod
    def token_hash(token: str) -> str:
        if not 32 <= len(token) <= 128:
            raise ValidationError("Invitation invalid or expired")
        return hashlib.sha256(token.encode()).hexdigest()

    async def operation(
        self, actor: UUID | None, action: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return await email_rpc(
            self.db,
            "clinician_email_invitation_operation",
            {"p_actor": str(actor) if actor else None, "p_action": action, "p_payload": payload},
        )

    async def create(self, actor: UUID, email: str, role: str, clinic_name: str) -> dict[str, Any]:
        transport = ResendClient()
        if not transport.deliverable(email):
            raise ValidationError("Use a real mailbox for a clinician invitation")
        token = secrets.token_urlsafe(32)
        content = render_email(
            f"Invitation to join {' '.join(clinic_name.split())}",
            [
                f"You have been invited to join {clinic_name} as {role.replace('_', ' ').title()}.",
                "Create your account using this invitation. If you already have an account, sign in first, reopen this link and accept explicitly.",
                "This invitation expires in seven days. Sending or opening it does not change clinic access.",
            ],
            action_url=settings.clinician_portal_url.rstrip("/") + "/signup#invitation=" + token,
            action_label="Review clinic invitation",
        )
        return await self.operation(
            actor,
            "create",
            {
                "email": email,
                "role": role,
                "hash": self.token_hash(token),
                "payload": transport.payload(content, email, onboarding=True),
            },
        )

    async def preview(self, token: str) -> dict[str, Any]:
        return await self.operation(None, "preview", {"hash": self.token_hash(token)})

    async def accept(self, actor: UUID, token: str) -> dict[str, Any]:
        return await self.operation(actor, "accept", {"hash": self.token_hash(token)})
