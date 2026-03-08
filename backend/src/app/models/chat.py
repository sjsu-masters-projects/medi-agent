"""Chat message schemas."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ChatRole, Language


class ChatMessageCreate(BaseModel):
    content: str = Field(..., min_length=1)
    role: ChatRole = ChatRole.USER
    language: Language = Language.EN
    audio_url: str | None = None  # voice message


class ChatMessage(BaseModel):
    id: UUID
    patient_id: UUID
    content: str
    role: ChatRole
    intent: str | None = None  # classified by Triage Agent
    language: Language = Language.EN
    audio_url: str | None = None
    created_at: str
