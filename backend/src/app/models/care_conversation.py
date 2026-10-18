"""Human conversation API contract, separate from AI chat and alerts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipient_id: UUID


class ConversationSend(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=4000)
    client_message_id: UUID

    @field_validator("body", mode="before")
    @classmethod
    def trim_body(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ConversationReadMarker(BaseModel):
    model_config = ConfigDict(extra="forbid")
    last_message_id: UUID


class ConversationRecipient(BaseModel):
    id: UUID
    clinic_id: UUID | None = None
    name: str
    role: str
    clinic_name: str


class ConversationSummary(BaseModel):
    id: UUID
    clinic_id: UUID | None = None
    patient_id: UUID
    clinician_id: UUID
    patient_name: str
    clinician_name: str
    clinic_name: str
    last_message_at: datetime | None
    last_message_preview: str | None
    unread_count: int = Field(ge=0)
    writable: bool


class ConversationMessage(BaseModel):
    id: UUID
    conversation_id: UUID
    sender_id: UUID
    sender_role: Literal["patient", "clinician"]
    sender_name: str
    body: str
    created_at: datetime
    # LOC-003: optional stored translation
    translation: str | None = None
    translation_locale: str | None = None
    translation_guard_passed: bool | None = None
    # True when the viewer needs a translation that is not stored yet: ask for it with
    # POST .../messages/{id}/translation (a read never calls the model).
    translation_pending: bool = False


class MessageTranslationResult(BaseModel):
    """One message's translation for the viewer, or none if it could not be produced."""

    message_id: UUID
    translation: str | None = None
    translation_locale: str | None = None
    translation_guard_passed: bool | None = None
    translation_pending: bool = False


class ConversationMessagePage(BaseModel):
    items: list[ConversationMessage]
    next_cursor: UUID | None


class ConversationReadReceipt(BaseModel):
    read_at: datetime
