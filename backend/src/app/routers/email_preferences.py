"""Authenticated contact verification and optional email preferences."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from supabase import Client

from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.email_preferences import (
    EmailInvitationToken,
    EmailPreferences,
    EmailPreferencesRead,
    EmailVerification,
)
from app.routers.care_conversations import conversation_actor
from app.services.email_invitation_service import EmailInvitationService
from app.services.email_service import EmailService

router = APIRouter()


@router.get("/invitations")
async def invitation_history(
    actor: CurrentUser = Depends(conversation_actor), db: Client = Depends(get_db)
) -> Any:
    return await EmailInvitationService(db).operation(actor.id, "list", {})


@router.post("/invitations/{invitation_id}/revoke")
async def revoke_invitation(
    invitation_id: UUID,
    actor: CurrentUser = Depends(conversation_actor),
    db: Client = Depends(get_db),
) -> Any:
    return await EmailInvitationService(db).operation(
        actor.id, "revoke", {"id": str(invitation_id)}
    )


@router.post("/invitations/preview")
async def preview_invitation(
    data: EmailInvitationToken, response: Response, db: Client = Depends(get_db)
) -> Any:
    response.headers["Cache-Control"] = "no-store"
    return await EmailInvitationService(db).preview(data.token)


@router.post("/invitations/accept")
async def accept_invitation(
    data: EmailInvitationToken,
    actor: CurrentUser = Depends(conversation_actor),
    db: Client = Depends(get_db),
) -> Any:
    return await EmailInvitationService(db).accept(actor.id, data.token)


def email_service(
    response: Response,
    actor: CurrentUser = Depends(conversation_actor),
    db: Client = Depends(get_db),
) -> EmailService:
    response.headers["Cache-Control"] = "private, no-store"
    return EmailService(db, actor)


@router.get("/preferences", response_model=EmailPreferencesRead)
async def preferences(service: EmailService = Depends(email_service)) -> EmailPreferencesRead:
    return await service.preferences()


@router.put("/preferences", response_model=EmailPreferencesRead)
async def save_preferences(
    data: EmailPreferences, service: EmailService = Depends(email_service)
) -> EmailPreferencesRead:
    return await service.save(data)


@router.post("/verify/request")
async def request_verification(service: EmailService = Depends(email_service)) -> Any:
    return await service.challenge()


@router.post("/verify")
async def verify(data: EmailVerification, service: EmailService = Depends(email_service)) -> Any:
    return await service.verify(data.code)
