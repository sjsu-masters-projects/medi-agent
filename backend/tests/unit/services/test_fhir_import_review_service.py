"""Tests for the clinician-facing SMART import review projection."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.clinical_fact import ClinicalFactReviewState
from app.services.fhir_import_review_service import FhirImportReviewService

PATIENT_ID = UUID("00000000-0000-0000-0000-000000000111")
PENDING_FACT_ID = "00000000-0000-0000-0000-000000000222"
APPROVED_FACT_ID = "00000000-0000-0000-0000-000000000333"
DELETED_FACT_ID = "00000000-0000-0000-0000-000000000444"
NON_FHIR_FACT_ID = "00000000-0000-0000-0000-000000000777"
PROVENANCE_ID = "00000000-0000-0000-0000-000000000555"
RESOURCE_ID = "00000000-0000-0000-0000-000000000666"


class Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class Table:
    def __init__(self, name: str, store: dict[str, list[dict[str, Any]]]) -> None:
        self.name = name
        self.store = store
        self.filters: list[tuple[str, set[str]]] = []
        self.return_single = False
        self.slice: tuple[int, int] | None = None

    def select(self, *_fields: str) -> Table:
        return self

    def eq(self, column: str, value: Any) -> Table:
        self.filters.append((column, {str(value)}))
        return self

    def in_(self, column: str, values: list[str]) -> Table:
        self.filters.append((column, {str(value) for value in values}))
        return self

    def order(self, *_args: Any, **_kwargs: Any) -> Table:
        return self

    def range(self, start: int, end: int) -> Table:
        self.slice = (start, end)
        return self

    def single(self) -> Table:
        self.return_single = True
        return self

    def execute(self) -> Result:
        rows = [
            row
            for row in self.store.get(self.name, [])
            if all(str(row.get(column)) in values for column, values in self.filters)
        ]
        if self.slice is not None:
            start, end = self.slice
            rows = rows[start : end + 1]
        if self.return_single:
            return Result(rows[0] if rows else None)
        return Result(rows)


class Database:
    def __init__(self, store: dict[str, list[dict[str, Any]]]) -> None:
        self.store = store

    def table(self, name: str) -> Table:
        return Table(name, self.store)


def fact(fact_id: str, review_state: str, fact_type: str = "medication") -> dict[str, Any]:
    return {
        "id": fact_id,
        "patient_id": str(PATIENT_ID),
        "fact_type": fact_type,
        "subject_type": fact_type,
        "value": {"name": "Metformin", "status": "active"},
        "confidence_score": None,
        "confidence_band": "unknown",
        "uncertainty": [],
        "review_state": review_state,
        "created_at": "2026-08-28T00:00:00Z",
        "updated_at": "2026-08-28T00:00:00Z",
    }


def database() -> Database:
    return Database(
        {
            "clinical_facts": [
                fact(PENDING_FACT_ID, "pending_review"),
                fact(APPROVED_FACT_ID, "approved", "condition"),
                fact(DELETED_FACT_ID, "deleted", "observation"),
                fact(NON_FHIR_FACT_ID, "pending_review", "document_reference"),
            ],
            "evidence_citations": [
                {"fact_id": PENDING_FACT_ID, "provenance_id": PROVENANCE_ID},
                {"fact_id": APPROVED_FACT_ID, "provenance_id": PROVENANCE_ID},
            ],
            "source_provenances": [
                {
                    "id": PROVENANCE_ID,
                    "source_system": "https://sandbox.example/fhir",
                    "source_reference": f"fhir_import_resources/{RESOURCE_ID}",
                }
            ],
            "fhir_import_resources": [
                {
                    "id": RESOURCE_ID,
                    "issuer": "https://sandbox.example/fhir",
                    "resource_type": "MedicationRequest",
                    "external_resource_id": "med-123",
                    "version_id": "7",
                    "mapping_warnings": ["Dose frequency was not supplied."],
                    "validation_errors": [],
                    "raw_resource": {"resourceType": "MedicationRequest", "id": "med-123"},
                }
            ],
        }
    )


def test_review_projection_shows_candidate_fields_and_source_metadata_without_raw_resource() -> (
    None
):
    service = FhirImportReviewService(database())  # type: ignore[arg-type]

    review = service.list_facts(
        patient_id=PATIENT_ID,
        review_state=ClinicalFactReviewState.PENDING_REVIEW,
        fact_type=None,
        offset=0,
        limit=25,
    )

    assert review["total_count"] == 1
    assert review["state_counts"] == {"pending_review": 1, "approved": 1}
    assert review["fact_type_counts"] == {"medication": 1, "condition": 1}
    assert review["facts"][0]["value"] == {"name": "Metformin", "status": "active"}
    assert review["facts"][0]["source"] == {
        "issuer": "https://sandbox.example/fhir",
        "resource_type": "MedicationRequest",
        "external_resource_id": "med-123",
        "version_id": "7",
        "mapping_warnings": ["Dose frequency was not supplied."],
        "validation_errors": [],
    }
    assert "raw_resource" not in review["facts"][0]["source"]


def test_review_projection_filters_by_mapped_type_and_excludes_non_fhir_candidates() -> None:
    service = FhirImportReviewService(database())  # type: ignore[arg-type]

    review = service.list_facts(
        patient_id=PATIENT_ID,
        review_state=ClinicalFactReviewState.PENDING_REVIEW,
        fact_type="condition",
        offset=0,
        limit=25,
    )

    assert review["total_count"] == 0
    assert review["state_counts"] == {"pending_review": 1, "approved": 1}
    assert review["fact_type_counts"] == {"medication": 1, "condition": 1}


def test_original_resource_is_available_only_from_the_explicit_source_read() -> None:
    service = FhirImportReviewService(database())  # type: ignore[arg-type]

    source = service.get_source(fact_id=UUID(PENDING_FACT_ID), patient_id=PATIENT_ID)

    assert source is not None
    assert source["raw_resource"] == {"resourceType": "MedicationRequest", "id": "med-123"}
    assert service.get_source(fact_id=UUID(NON_FHIR_FACT_ID), patient_id=PATIENT_ID) is None
    assert service.get_source(fact_id=UUID(PENDING_FACT_ID), patient_id=UUID(int=999)) is None
