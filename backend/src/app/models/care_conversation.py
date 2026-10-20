"""Human conversation API contract, separate from AI chat and alerts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import Language


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipient_id: UUID


class ConfirmedTranslation(BaseModel):
    """The exact wording a clinician previewed and confirmed the patient will receive.

    LOC-003 decision 3: the clinician approves specific Spanish, so that wording is stored as
    the message's translation rather than a fresh one that could differ. The server re-runs
    the LOC-001 guards against the message body before storing it.
    """

    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=8000)
    locale: Language
    #: The model that produced it, carried through so the patient's portal can say which.
    model_id: str | None = Field(default=None, max_length=200)


class ConversationPreviewRequest(BaseModel):
    """Ask what the patient will receive for this draft, before it is sent."""

    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=4000)

    @field_validator("body", mode="before")
    @classmethod
    def trim_body(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ConversationPreviewResult(BaseModel):
    """The patient-facing wording for an unsent reply, with its English back-translation.

    Nothing is stored: this describes text that has not been sent. ``needed`` is false when
    the patient reads the language the clinician wrote in, so there is nothing to confirm.
    """

    needed: bool = False
    target_locale: str
    translation: str | None = None
    back_translation: str | None = None
    guard_passed: bool | None = None
    guard_failure_code: str | None = None
    model_id: str | None = None


class ConversationSend(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=4000)
    client_message_id: UUID
    care_plan_item_id: UUID | None = None
    #: LOC-003: the previewed wording the clinician confirmed, stored with the message so the
    #: patient sees exactly what was approved. Omitted when no translation is needed.
    confirmed_translation: ConfirmedTranslation | None = None

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
    #: LOC-003 item 5: the model that produced it, shown with its "may contain errors" note.
    translation_model_id: str | None = None
    # True when the viewer needs a translation that is not stored yet: ask for it with
    # POST .../messages/{id}/translation (a read never calls the model).
    translation_pending: bool = False
    activity_context: dict[str, object] | None = None


class MessageTranslationResult(BaseModel):
    """One message's translation for the viewer, or none if it could not be produced."""

    message_id: UUID
    translation: str | None = None
    translation_locale: str | None = None
    translation_guard_passed: bool | None = None
    translation_pending: bool = False
    #: LOC-003 item 5: the model that produced it, shown with its "may contain errors" note.
    translation_model_id: str | None = None


class ConversationMessagePage(BaseModel):
    items: list[ConversationMessage]
    next_cursor: UUID | None


class ConversationReadReceipt(BaseModel):
    read_at: datetime
