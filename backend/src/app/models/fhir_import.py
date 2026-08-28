"""Schemas for SMART launch sessions and imported FHIR resources."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.models.clinical_fact import ClinicalFactRead, ClinicalFactReviewState


class FhirImportStatus(StrEnum):
    PENDING = "pending"
    IMPORTING = "importing"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"


class SmartLaunchRequest(BaseModel):
    """A locally authorized request to start a SMART launch for one patient.

    ``launch_context`` is the opaque EHR-launch handle.  It is accepted only
    after local clinician and care-team authorization, and is never returned to
    the browser by this API.
    """

    patient_id: UUID
    issuer: HttpUrl
    launch_context: str | None = Field(default=None, min_length=1, max_length=2048)

    @field_validator("issuer")
    @classmethod
    def issuer_must_use_https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("SMART issuer must use HTTPS")
        return value


class SmartLaunchResponse(BaseModel):
    authorization_url: str
    expires_at: datetime


class SmartCallbackResult(BaseModel):
    handoff_url: str
    import_id: UUID


class SmartImportRead(BaseModel):
    id: UUID
    patient_id: UUID
    issuer: str
    external_patient_id: str | None = None
    external_encounter_id: str | None = None
    status: FhirImportStatus
    resource_count: int = 0
    candidate_fact_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None = None


class FhirImportResourceRead(BaseModel):
    id: UUID
    resource_type: str
    external_resource_id: str | None = None
    version_id: str | None = None
    validation_errors: list[str] = Field(default_factory=list)
    mapping_warnings: list[str] = Field(default_factory=list)
    created_at: datetime


class FhirReviewSourceRead(BaseModel):
    """Minimal, clinician-facing lineage for one imported candidate fact."""

    issuer: str
    resource_type: str
    external_resource_id: str | None = None
    version_id: str | None = None
    mapping_warnings: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)


class FhirReviewSourceDetailRead(FhirReviewSourceRead):
    """The original synthetic FHIR envelope for clinician source inspection."""

    raw_resource: dict[str, Any]


class FhirReviewFactRead(ClinicalFactRead):
    """A pending or reviewed fact with the source envelope that produced it."""

    source: FhirReviewSourceRead | None = None


class FhirPatientReviewRead(BaseModel):
    """A paginated, clinician-authorized SMART import review view."""

    patient_id: UUID
    review_state: ClinicalFactReviewState
    facts: list[FhirReviewFactRead] = Field(default_factory=list)
    total_count: int = 0
    state_counts: dict[str, int] = Field(default_factory=dict)
    fact_type_counts: dict[str, int] = Field(default_factory=dict)
    offset: int = 0
    limit: int = 25


class ClinicalFactReviewRequest(BaseModel):
    """A clinician's explicit review decision without any clinical-value mutation."""

    note: str | None = Field(default=None, max_length=2000)


class ClinicalFactCorrectionRequest(BaseModel):
    """A corrected candidate value and the reason for the correction."""

    value: dict[str, Any] = Field(default_factory=dict)
    note: str = Field(min_length=1, max_length=2000)


class SmartHandoffRedeemRequest(BaseModel):
    ticket: str = Field(min_length=32, max_length=512)


class SmartHandoffRedeemResponse(BaseModel):
    import_record: SmartImportRead
    resources: list[FhirImportResourceRead] = Field(default_factory=list)
    lineage_available: bool = True
    details: dict[str, Any] = Field(default_factory=dict)
