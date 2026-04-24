"""Dashboard and risk radar schemas.

Used by GET /api/v1/clinicians/me/dashboard and patient deep-dive endpoints.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import DocumentReviewStatus, DocumentType, UploaderRole

# ── Risk level type alias ────────────────────────────────────────────────────

RiskLevel = Literal["low", "medium", "high", "unknown"]
DashboardSortBy = Literal["risk", "adherence", "last_activity", "med_count"]
DashboardSortOrder = Literal["asc", "desc"]
A2ATaskStatus = Literal[
    "submitted",
    "working",
    "retrying",
    "completed",
    "failed",
    "dead_letter",
]


# ── Per-patient risk card ────────────────────────────────────────────────────


class PatientRiskData(BaseModel):
    """Risk snapshot for a single patient — shown on the Risk Radar dashboard."""

    patient_id: UUID
    first_name: str
    last_name: str
    risk_level: RiskLevel
    adherence_score: float = Field(..., ge=0.0, le=1.0, description="0.0 – 1.0")
    open_adr_count: int = Field(default=0, ge=0)
    active_med_count: int = Field(default=0, ge=0)
    recent_symptom_severity: int = Field(
        default=0, ge=0, le=10, description="Max severity in last 7 days"
    )
    last_activity: str = Field(default="", description="Human-readable last activity string")


# ── Dashboard aggregate ──────────────────────────────────────────────────────


class DashboardResponse(BaseModel):
    """Full clinician dashboard payload."""

    patients: list[PatientRiskData]
    total: int
    high_risk: int
    medium_risk: int
    low_risk: int
    medwatch_pending: int


# ── SOAP note ────────────────────────────────────────────────────────────────


class SoapNote(BaseModel):
    """AI-generated SOAP note for a patient visit."""

    subjective: str = Field(..., description="Patient-reported symptoms and history")
    objective: str = Field(..., description="Objective measurements, labs, and observations")
    assessment: str = Field(..., description="Clinical assessment and differential")
    plan: str = Field(..., description="Treatment plan and follow-up actions")


class SoapNoteRead(BaseModel):
    """Stored SOAP note returned from the database."""

    id: UUID
    patient_id: UUID
    clinician_id: UUID
    subjective: str
    objective: str
    assessment: str
    plan: str
    generated_at: str
    model_used: str


class SoapNoteRequest(BaseModel):
    """Request body for on-demand SOAP note generation."""

    # Optional: fetch and use only the last N days of data
    lookback_days: int = Field(default=30, ge=7, le=365)


class SoapNoteGenerationResponse(BaseModel):
    """Response payload for on-demand SOAP generation endpoint."""

    status: str
    soap_note_id: UUID | None = None
    soap_note: SoapNote | SoapNoteRead | None = None


# ── Patient deep dive ────────────────────────────────────────────────────────


class AdherenceDataPoint(BaseModel):
    """Single day's adherence score — used in Recharts LineChart."""

    date: str  # ISO 8601, e.g. "2026-03-15"
    score: float = Field(..., ge=0.0, le=1.0)
    completed: int
    expected: int


class DocumentReviewerRead(BaseModel):
    """Reviewer metadata shown for patient-uploaded document decisions."""

    id: UUID
    first_name: str | None = None
    last_name: str | None = None


class PatientDocumentRead(BaseModel):
    """Document record shown in clinician-facing patient deep dives."""

    id: UUID
    file_name: str
    document_type: DocumentType
    parse_status: str
    ai_summary: str | None = None
    created_at: str
    uploaded_by_role: UploaderRole
    clinician_annotation: str | None = None
    review_status: DocumentReviewStatus | None = None
    reviewed_by: UUID | None = None
    reviewed_at: str | None = None
    review_note: str | None = None
    reviewer: DocumentReviewerRead | None = None


class DocumentReviewQueueItem(BaseModel):
    """Pending patient-uploaded document awaiting clinician review."""

    id: UUID
    patient_id: UUID
    patient_first_name: str
    patient_last_name: str
    file_name: str
    document_type: DocumentType
    parse_status: str
    ai_summary: str | None = None
    source_clinic: str | None = None
    created_at: str
    uploaded_by_role: UploaderRole
    review_status: DocumentReviewStatus


class DocumentReviewActionRequest(BaseModel):
    """Optional note when rejecting a reviewed patient-uploaded document."""

    review_note: str | None = Field(default=None, max_length=2000)


class DocumentReviewActionResponse(BaseModel):
    """Updated review metadata returned after approve/reject actions."""

    status: str
    document_id: UUID
    patient_id: UUID
    review_status: DocumentReviewStatus
    reviewed_by: UUID
    reviewed_at: str
    review_note: str | None = None


class PatientDeepDive(BaseModel):
    """Aggregated patient data for the Patient Deep Dive view."""

    # Basic profile
    patient_id: UUID
    first_name: str
    last_name: str
    email: str
    date_of_birth: str | None = None
    avatar_url: str | None = None

    # Risk
    risk_level: RiskLevel
    adherence_score: float

    # Sub-resources
    medications: list[dict[str, Any]] = Field(default_factory=list)
    adherence_series: list[AdherenceDataPoint] = Field(default_factory=list)
    symptom_reports: list[dict[str, Any]] = Field(default_factory=list)
    chat_messages: list[dict[str, Any]] = Field(default_factory=list)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    allergies: list[dict[str, Any]] = Field(default_factory=list)
    documents: list[PatientDocumentRead] = Field(default_factory=list)
    latest_soap_note: SoapNoteRead | None = None
    obligations: list[dict[str, Any]] = Field(default_factory=list)
    obligation_completion_rate: float = Field(default=0.0, ge=0.0, le=1.0)


# ── Clinician annotation ──────────────────────────────────────────────────────


class AnnotationCreate(BaseModel):
    """Clinician's free-text annotation on a document summary."""

    annotation_text: str = Field(..., min_length=1, max_length=2000)


class AnnotationSaveResponse(BaseModel):
    """Response after saving clinician annotation."""

    status: str
    document_id: str


class ObligationSetRequest(BaseModel):
    """Clinician sets an obligation for a patient."""

    obligation_type: Literal["diet", "exercise", "custom"]
    description: str = Field(..., min_length=1, max_length=500)
    frequency: str = Field(..., examples=["daily", "3x per week", "with each meal"])
    notes: str | None = None


class A2ATimelineTask(BaseModel):
    """Single A2A task event shown in clinician timeline views."""

    id: UUID
    patient_id: UUID
    symptom_event_id: UUID | None = None
    idempotency_key: str
    conversation_session_id: str
    source_agent: str
    target_agent: str
    task_type: str
    status: A2ATaskStatus
    retry_attempt: int = Field(default=0, ge=0)
    max_retries: int = Field(default=0, ge=0)
    next_retry_at: str | None = None
    dead_lettered_at: str | None = None
    error_message: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] | None = None
    worker_payload: dict[str, Any] | None = None


class A2ATimelineResponse(BaseModel):
    """Clinician-facing A2A timeline for a patient/session."""

    patient_id: UUID
    session_id: str | None = None
    tasks: list[A2ATimelineTask]
