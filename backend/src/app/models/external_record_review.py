"""Read-only source review workload, separate from notification counts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ExternalRecordReviewItem(BaseModel):
    patient_id: UUID
    patient_name: str
    clinic_id: str | None = None
    clinic_name: str | None = None
    pending_count: int
    inspected_candidates: int
    oldest_source_captured_at: datetime | None = None
    source_times_complete: bool


class ExternalRecordReviewsResponse(BaseModel):
    items: list[ExternalRecordReviewItem]
    retrieved_at: datetime
    page: int
    page_size: int
    assigned_patients: int
    patients_examined: int
    has_more: bool
    candidate_limit: int
    citation_limit: int
