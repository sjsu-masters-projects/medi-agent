"""Chat message schemas."""

from typing import Any, Literal
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
    session_id: str = "default"
    created_at: str
    # Server-built cards under a reply, e.g. the results of a document the reply cited.
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class ChatConversation(BaseModel):
    """One entry in the patient's conversation list."""

    session_id: str
    title: str = ""
    turn_count: int = 0
    language: Language = Language.EN
    created_at: str
    updated_at: str
    # Set when the latest saved turn is unfinished and the patient can recover it.
    status: Literal["needs_attention"] | None = None
    reply_in_progress: bool = False


class ReplyEvidence(BaseModel):
    """The structured evidence one assistant reply used (tools, sources, care plan ids)."""

    message_id: str
    session_id: str
    evidence: dict[str, Any]
    created_at: str


class TranscriptTranslationResult(BaseModel):
    """LOC-003: one Nora transcript turn translated into the clinician's English.

    The original turn stays the record: it is what the patient actually wrote, and safety
    checks and escalation read only it. A translation whose guard failed is not returned.
    """

    message_id: UUID
    translation: str | None = None
    translation_locale: str | None = None
    translation_guard_passed: bool | None = None
    translation_pending: bool = False
    #: The model that produced the translation, shown with its "may contain errors" caveat.
    translation_model_id: str | None = None
