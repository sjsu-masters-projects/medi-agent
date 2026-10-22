"""Read models for the confirmed-symptom history (PAT-002-C). Only confirmed reports exist here."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ReportStatus = Literal["reported", "shared", "reviewed"]
EventKind = Literal["reported", "shared_with_care_team", "flagged_urgent", "reviewed"]


class ReportEvent(BaseModel):
    """One thing that actually happened to the report, read from a recorded row."""

    kind: EventKind
    at: datetime
    actor_name: str | None = None


class ReportAnswer(BaseModel):
    """An answer exactly as the patient confirmed it, in the language they used."""

    question_id: str
    label: str
    state: Literal["answered", "unknown", "declined"]
    display: str
    wording: str | None = None
    captured_at: datetime | None = None


class SymptomReportListItem(BaseModel):
    id: UUID
    symptom: str
    severity: int | None = None
    onset: str | None = None
    duration: str | None = None
    confirmed_at: datetime
    locale: Literal["en-US", "es-MX"]
    status: ReportStatus
    events: list[ReportEvent]


class SymptomReportList(BaseModel):
    items: list[SymptomReportListItem]
    has_more: bool = False
    timezone: str = "UTC"


class SymptomReportDetail(SymptomReportListItem):
    body_area: str | None = None
    timezone: str | None = None
    answers: list[ReportAnswer] = Field(default_factory=list)
    summary: str | None = None


class ReportProvenance(BaseModel):
    report_id: UUID
    intake_id: UUID | None = None
    source_message_id: UUID | None = None
    session_id: str | None = None
    schema_version: str | None = None
    library_version: str | None = None
    submitted_status: str | None = None
    confirmed_at: datetime
    confirmed_by: UUID | None = None
    language: Literal["en-US", "es-MX"]
    timezone: str | None = None
    consent_recorded: bool


class ReportReviewState(BaseModel):
    state: Literal["pending", "reviewed"]
    reviewed_at: datetime | None = None
    reviewed_by_name: str | None = None
    care_team_id: UUID | None = None


class ReportTriage(BaseModel):
    """What the deterministic gate recorded, never a clinical triage conclusion."""

    safety_rule_version: str | None = None
    safety_result: str | None = None
    escalation_urgency: Literal["urgent", "emergency"] | None = None
    escalation_delivery: str | None = None
    escalation_at: datetime | None = None


class ClinicianSymptomReport(SymptomReportDetail):
    patient_id: UUID
    flagged_for_adr: bool = False
    related_medication_name: str | None = None
    provenance: ReportProvenance
    triage: ReportTriage
    review: ReportReviewState
    already_reviewed: bool | None = None
