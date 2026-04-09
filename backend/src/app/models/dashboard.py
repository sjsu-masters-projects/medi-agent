"""Dashboard and risk radar schemas.

Used by GET /api/v1/clinicians/me/dashboard and patient deep-dive endpoints.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ── Risk level type alias ────────────────────────────────────────────────────

RiskLevel = Literal["low", "medium", "high"]


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


# ── Patient deep dive ────────────────────────────────────────────────────────


class AdherenceDataPoint(BaseModel):
    """Single day's adherence score — used in Recharts LineChart."""

    date: str  # ISO 8601, e.g. "2026-03-15"
    score: float = Field(..., ge=0.0, le=1.0)
    completed: int
    expected: int


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
    medications: list[dict] = Field(default_factory=list)
    adherence_series: list[AdherenceDataPoint] = Field(default_factory=list)
    symptom_reports: list[dict] = Field(default_factory=list)
    chat_messages: list[dict] = Field(default_factory=list)
    conditions: list[dict] = Field(default_factory=list)
    allergies: list[dict] = Field(default_factory=list)
    documents: list[dict] = Field(default_factory=list)
    latest_soap_note: SoapNoteRead | None = None


# ── Clinician annotation ──────────────────────────────────────────────────────


class AnnotationCreate(BaseModel):
    """Clinician's free-text annotation on a document summary."""

    annotation_text: str = Field(..., min_length=1, max_length=2000)


class ObligationSetRequest(BaseModel):
    """Clinician sets an obligation for a patient."""

    obligation_type: str = Field(..., description="diet | exercise | custom")
    description: str = Field(..., min_length=1, max_length=500)
    frequency: str = Field(..., examples=["daily", "3x per week", "with each meal"])
    notes: str | None = None
