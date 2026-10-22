"""Explicitly routed patient/clinician conversations, never AI or alert transcripts."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client

from app.core.exceptions import AuthorizationError
from app.core.security import get_current_user, require_role
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.care_conversation import (
    ConversationCreate,
    ConversationMessage,
    ConversationMessagePage,
    ConversationPreviewRequest,
    ConversationPreviewResult,
    ConversationReadMarker,
    ConversationReadReceipt,
    ConversationRecipient,
    ConversationSend,
    ConversationSummary,
    MessageTranslationResult,
)
from app.services.care_conversation_service import CareConversationService

router = APIRouter()
_clinician_check = require_role("clinician")


async def conversation_actor(
    user: CurrentUser = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
) -> CurrentUser:
    if user.role not in {"patient", "clinician"}:
        raise AuthorizationError("Conversation unavailable")
    if user.role == "clinician":
        await _clinician_check(user=user, credentials=credentials)
    return user


async def conversation_service(
    response: Response,
    user: CurrentUser = Depends(conversation_actor),
    db: Client = Depends(get_db),
) -> CareConversationService:
    response.headers["Cache-Control"] = "private, no-store"
    return CareConversationService(db, user)


@router.get("/recipients", response_model=list[ConversationRecipient])
async def recipients(
    clinic_id: UUID | None = Query(default=None),
    service: CareConversationService = Depends(conversation_service),
) -> Any:
    return await service.recipients(clinic_id)


@router.get("/", response_model=list[ConversationSummary])
async def conversations(
    clinic_id: UUID | None = Query(default=None),
    service: CareConversationService = Depends(conversation_service),
) -> Any:
    return await service.list_conversations(clinic_id)


@router.post("/", response_model=ConversationSummary)
async def open_conversation(
    data: ConversationCreate,
    service: CareConversationService = Depends(conversation_service),
) -> Any:
    return await service.open_conversation(data)


@router.get("/{conversation_id}/messages", response_model=ConversationMessagePage)
async def messages(
    conversation_id: UUID,
    before: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    service: CareConversationService = Depends(conversation_service),
) -> Any:
    return await service.messages(
        conversation_id, {"before": str(before) if before else None, "limit": limit}
    )


@router.post("/{conversation_id}/messages", response_model=ConversationMessage)
async def send_message(
    conversation_id: UUID,
    data: ConversationSend,
    service: CareConversationService = Depends(conversation_service),
) -> Any:
    return await service.send(conversation_id, data)


@router.post(
    "/{conversation_id}/messages/preview",
    response_model=ConversationPreviewResult,
    summary="LOC-003: what the patient will receive for an unsent reply",
    description=(
        "Clinician-only. Translates a draft reply into the patient's language and returns it "
        "with an English back-translation and the guard results, so the clinician can confirm "
        "the wording the patient will read without reading that language. Nothing is stored: "
        "the reply has not been sent. `needed` is false when the patient already reads the "
        "language the clinician wrote in, and a translation that failed a guard is reported "
        "but never offered for confirmation."
    ),
)
async def preview_reply(
    conversation_id: UUID,
    data: ConversationPreviewRequest,
    service: CareConversationService = Depends(conversation_service),
) -> Any:
    return await service.preview_reply(conversation_id, data.body)


@router.post(
    "/{conversation_id}/messages/{message_id}/translation",
    response_model=MessageTranslationResult,
)
async def translate_message(
    conversation_id: UUID,
    message_id: UUID,
    service: CareConversationService = Depends(conversation_service),
) -> Any:
    """Translate one message into the viewer's language (stored once, never on read or send)."""
    return await service.translate_message(conversation_id, message_id)


@router.post("/{conversation_id}/read", response_model=ConversationReadReceipt)
async def mark_read(
    conversation_id: UUID,
    data: ConversationReadMarker,
    service: CareConversationService = Depends(conversation_service),
) -> Any:
    return await service.mark_read(conversation_id, data)


@router.post("/{conversation_id}/messages/{message_id}/activity-review")
async def review_activity(
    conversation_id: UUID,
    message_id: UUID,
    service: CareConversationService = Depends(conversation_service),
) -> Any:
    """Open the message's approved activity in a draft; publication is separate."""
    return await service.review_activity(conversation_id, message_id)
