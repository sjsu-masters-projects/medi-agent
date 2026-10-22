"""Care-handoff summary request and response contracts (CON-001)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

HandoffPurpose = Literal["colleague", "care_team", "transition"]
ExportFormat = Literal["print", "fhir"]


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class HandoffCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: HandoffPurpose
    recipient_label: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    care_team_id: UUID | None = None
    # A retry of the same create carries the same id and returns the same summary.
    client_request_id: UUID | None = None

    _strip = field_validator("recipient_label", "title")(_clean)


class HandoffSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1, le=200)
    narrative: str | None = Field(default=None, max_length=4000)
    notes: str | None = Field(default=None, max_length=4000)
    title: str | None = Field(default=None, max_length=200)
    # Rebuild the deterministic sections from current records as the next version.
    refresh: bool = False

    _strip = field_validator("narrative", "notes", "title")(_clean)


class HandoffVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, le=200)


class HandoffExportRequest(HandoffVersionRequest):
    format: ExportFormat


class HandoffSource(BaseModel):
    kind: Literal["record", "rule"] = "record"
    table: str | None = None
    id: str | None = None
    label: str
    href: str | None = None


class HandoffItem(BaseModel):
    id: str
    text: str
    detail: str | None = None
    source: HandoffSource


class HandoffSection(BaseModel):
    key: str
    title: str
    status: Literal["available", "empty", "unavailable"]
    note: str | None = None
    items: list[HandoffItem] = Field(default_factory=list)


class HandoffHeader(BaseModel):
    id: UUID
    patient_id: UUID
    care_team_id: UUID
    author_id: UUID
    title: str
    purpose: HandoffPurpose
    recipient_label: str | None = None
    status: Literal["draft", "approved"]
    current_version: int
    approved_version: int | None = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    # Set by create/save/approve: False when the call was a replay or a no-op.
    changed: bool | None = None
    replayed: bool | None = None


class HandoffVersionBody(BaseModel):
    version: int
    sections: list[HandoffSection]
    narrative: str | None = None
    notes: str | None = None
    built_at: datetime
    created_by: UUID
    created_at: datetime


class HandoffVersionSummary(BaseModel):
    version: int
    created_by: UUID
    created_at: datetime


class HandoffEvent(BaseModel):
    event_type: str
    version: int
    export_format: str | None = None
    actor_id: UUID
    created_at: datetime


class HandoffDetail(HandoffHeader):
    version: HandoffVersionBody
    versions: list[HandoffVersionSummary]
    events: list[HandoffEvent]
    patient_name: str | None = None


class HandoffExportResponse(BaseModel):
    format: ExportFormat
    summary: HandoffDetail
    # The FHIR R4 document Bundle for format "fhir"; absent for the printable view.
    bundle: dict[str, Any] | None = None
