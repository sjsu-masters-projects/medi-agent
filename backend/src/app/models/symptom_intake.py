"""Strict patient inputs: no actor, patient, clinical snapshot or approval fields."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IntakeStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_message_id: UUID
    session_id: str = Field(min_length=1, max_length=128, pattern=r"^\S+$")


class IntakeMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0, strict=True)
    mutation_id: UUID


class IntakeAnswer(IntakeMutation):
    question_id: str = Field(min_length=1, max_length=40)
    state: Literal["answered", "unknown", "declined"]
    value: Any = None
    wording: str = Field(default="", max_length=1000)
    locale: Literal["en-US", "es-MX"]


class IntakePreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0, strict=True)


class IntakeConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0, strict=True)
    preview_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmation_id: UUID
    consent: Literal[True]

    @field_validator("consent", mode="before")
    @classmethod
    def explicit_consent(cls, value: Any) -> bool:
        if value is not True:
            raise ValueError("Explicit consent required")
        return True
