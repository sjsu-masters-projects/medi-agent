"""Schemas for SMART launch sessions and imported FHIR resources."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator


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


class SmartHandoffRedeemRequest(BaseModel):
    ticket: str = Field(min_length=32, max_length=512)


class SmartHandoffRedeemResponse(BaseModel):
    import_record: SmartImportRead
    resources: list[FhirImportResourceRead] = Field(default_factory=list)
    lineage_available: bool = True
    details: dict[str, Any] = Field(default_factory=dict)
