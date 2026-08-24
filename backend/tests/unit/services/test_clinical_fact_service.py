"""Unit tests for the clinical-fact review gate and provenance lineage."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import ValidationError
from app.models.clinical_fact import ClinicalFactCreate
from app.services.clinical_fact_service import ClinicalFactService

PATIENT_ID = UUID("00000000-0000-0000-0000-000000000111")
ACTOR_ID = UUID("00000000-0000-0000-0000-000000000222")
REVIEWER_ID = UUID("00000000-0000-0000-0000-000000000333")
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000444")


class FakeResult:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeTable:
    def __init__(self, name: str, store: dict[str, list[dict[str, Any]]]) -> None:
        self.name = name
        self.store = store
        self.filters: list[tuple[str, set[str]]] = []
        self.pending_insert: dict[str, Any] | None = None
        self.pending_update: dict[str, Any] | None = None
        self.return_single = False

    def insert(self, payload: dict[str, Any]) -> FakeTable:
        self.pending_insert = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeTable:
        self.pending_update = payload
        return self

    def select(self, *_fields: str) -> FakeTable:
        return self

    def eq(self, column: str, value: Any) -> FakeTable:
        self.filters.append((column, {str(value)}))
        return self

    def in_(self, column: str, values: list[str]) -> FakeTable:
        self.filters.append((column, {str(value) for value in values}))
        return self

    def order(self, *_args: Any, **_kwargs: Any) -> FakeTable:
        return self

    def single(self) -> FakeTable:
        self.return_single = True
        return self

    def execute(self) -> FakeResult:
        rows = self.store.setdefault(self.name, [])
        matches = [
            row
            for row in rows
            if all(str(row.get(column)) in values for column, values in self.filters)
        ]
        if self.pending_insert is not None:
            row = {
                "id": str(uuid4()),
                "created_at": "2026-08-20T00:00:00Z",
                "updated_at": "2026-08-20T00:00:00Z",
                **self.pending_insert,
            }
            rows.append(row)
            return FakeResult([row])
        if self.pending_update is not None:
            for row in matches:
                row.update(self.pending_update)
            return FakeResult(matches)
        return FakeResult(
            matches[0]
            if self.return_single and matches
            else (None if self.return_single else matches)
        )


class FakeDatabase:
    def __init__(self) -> None:
        self.store: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> FakeTable:
        return FakeTable(name, self.store)


def candidate() -> ClinicalFactCreate:
    return ClinicalFactCreate.model_validate(
        {
            "patient_id": str(PATIENT_ID),
            "fact_type": "medication",
            "subject_type": "medication",
            "value": {"name": "Metformin", "dose": "500 mg"},
            "confidence_score": 0.72,
            "confidence_band": "medium",
            "uncertainty": ["Dose frequency is absent from the source."],
            "provenance": {
                "artifact_type": "document",
                "source_system": "patient_upload",
                "source_reference": "document:discharge-summary.pdf",
                "document_id": str(DOCUMENT_ID),
                "document_location": {"page": 2, "section": "Medications"},
                "extractor_version": "document-parser/1.0",
                "model_version": "structured-extraction/1.0",
            },
            "citations": [
                {
                    "excerpt": "Continue metformin 500 mg.",
                    "location": {"page": 2, "start": 12, "end": 38},
                }
            ],
        }
    )


def test_candidate_is_pending_with_provenance_citation_and_creation_audit() -> None:
    db = FakeDatabase()
    service = ClinicalFactService(db)  # type: ignore[arg-type]

    fact = service.create_candidate(candidate(), actor_id=ACTOR_ID)

    assert fact["review_state"] == "pending_review"
    assert db.store["source_provenances"][0]["document_id"] == str(DOCUMENT_ID)
    assert db.store["evidence_citations"][0]["fact_id"] == fact["id"]
    assert db.store["clinical_fact_audit_events"][0]["event_type"] == "created"
    assert service.list_approved(PATIENT_ID) == []


def test_approval_is_explicit_and_makes_fact_available_to_clinical_consumers() -> None:
    db = FakeDatabase()
    service = ClinicalFactService(db)  # type: ignore[arg-type]
    fact = service.create_candidate(candidate(), actor_id=ACTOR_ID)

    approved = service.approve(UUID(fact["id"]), PATIENT_ID, reviewer_id=REVIEWER_ID)

    assert approved["review_state"] == "approved"
    assert approved["reviewed_by"] == str(REVIEWER_ID)
    assert [row["id"] for row in service.list_approved(PATIENT_ID)] == [fact["id"]]
    assert [row["event_type"] for row in db.store["clinical_fact_audit_events"]] == [
        "created",
        "approved",
    ]


def test_rejection_requires_a_reason_and_cannot_be_followed_by_approval() -> None:
    db = FakeDatabase()
    service = ClinicalFactService(db)  # type: ignore[arg-type]
    fact = service.create_candidate(candidate(), actor_id=ACTOR_ID)

    with pytest.raises(ValidationError, match="rejection note"):
        service.reject(UUID(fact["id"]), PATIENT_ID, reviewer_id=REVIEWER_ID, note=" ")

    service.reject(UUID(fact["id"]), PATIENT_ID, reviewer_id=REVIEWER_ID, note="Wrong patient")
    with pytest.raises(ValidationError, match="Only pending"):
        service.approve(UUID(fact["id"]), PATIENT_ID, reviewer_id=REVIEWER_ID)


def test_correction_and_deletion_are_audited_and_deleted_facts_are_not_lineage_results() -> None:
    db = FakeDatabase()
    service = ClinicalFactService(db)  # type: ignore[arg-type]
    fact = service.create_candidate(candidate(), actor_id=ACTOR_ID)
    fact_id = UUID(fact["id"])

    corrected = service.correct(
        fact_id,
        PATIENT_ID,
        actor_id=REVIEWER_ID,
        value={"name": "Metformin", "dose": "1000 mg"},
        note="Corrected from clinician review.",
    )
    assert corrected["review_state"] == "pending_review"
    assert corrected["value"]["dose"] == "1000 mg"

    service.delete(fact_id, PATIENT_ID, actor_id=REVIEWER_ID, note="Duplicate source artifact")
    assert service.list_facts_for_document(DOCUMENT_ID, PATIENT_ID) == []
    assert [row["event_type"] for row in db.store["clinical_fact_audit_events"]] == [
        "created",
        "corrected",
        "deleted",
    ]


def test_lineage_returns_the_source_artifact_and_evidence_excerpt() -> None:
    db = FakeDatabase()
    service = ClinicalFactService(db)  # type: ignore[arg-type]
    fact = service.create_candidate(candidate(), actor_id=ACTOR_ID)

    lineage = service.get_lineage(UUID(fact["id"]), PATIENT_ID)

    assert lineage["fact"]["id"] == fact["id"]
    assert lineage["provenances"][0]["document_location"]["page"] == 2
    assert lineage["citations"][0]["excerpt"] == "Continue metformin 500 mg."
