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
    ConversationReadMarker,
    ConversationReadReceipt,
    ConversationRecipient,
    ConversationSend,
    ConversationSummary,
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
async def recipients(service: CareConversationService = Depends(conversation_service)) -> Any:
    return await service.recipients()


@router.get("/", response_model=list[ConversationSummary])
async def conversations(service: CareConversationService = Depends(conversation_service)) -> Any:
    return await service.list_conversations()


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


@router.post("/{conversation_id}/read", response_model=ConversationReadReceipt)
async def mark_read(
    conversation_id: UUID,
    data: ConversationReadMarker,
    service: CareConversationService = Depends(conversation_service),
) -> Any:
    return await service.mark_read(conversation_id, data)
