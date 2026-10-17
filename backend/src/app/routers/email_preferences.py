"""Authenticated contact verification, optional email preferences and invitations."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from supabase import Client

from app.core.security import require_role
from app.db.connection import get_db
from app.models.auth import CurrentUser, InvitationAcceptResponse
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

# Invitation management and acceptance are clinician-only and keep the MFA gate.
_clinician = require_role("clinician")


@router.get("/invitations")
async def invitation_history(
    response: Response,
    clinic_id: UUID | None = Query(default=None),
    actor: CurrentUser = Depends(_clinician),
    db: Client = Depends(get_db),
) -> Any:
    response.headers["Cache-Control"] = "private, no-store"
    return await EmailInvitationService(db).history(actor.id, clinic_id)


@router.post("/invitations/{invitation_id}/revoke")
async def revoke_invitation(
    invitation_id: UUID,
    actor: CurrentUser = Depends(_clinician),
    db: Client = Depends(get_db),
) -> Any:
    return await EmailInvitationService(db).revoke(actor.id, invitation_id)


@router.post("/invitations/preview")
async def preview_invitation(
    data: EmailInvitationToken, response: Response, db: Client = Depends(get_db)
) -> Any:
    response.headers["Cache-Control"] = "no-store"
    return await EmailInvitationService(db).preview(data.token)


@router.post("/invitations/accept", response_model=InvitationAcceptResponse)
async def accept_invitation(
    data: EmailInvitationToken,
    response: Response,
    actor: CurrentUser = Depends(_clinician),
    db: Client = Depends(get_db),
) -> Any:
    response.headers["Cache-Control"] = "no-store"
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
