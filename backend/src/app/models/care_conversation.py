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
    name: str
    role: str
    clinic_name: str


class ConversationSummary(BaseModel):
    id: UUID
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


class ConversationMessagePage(BaseModel):
    items: list[ConversationMessage]
    next_cursor: UUID | None


class ConversationReadReceipt(BaseModel):
    read_at: datetime
