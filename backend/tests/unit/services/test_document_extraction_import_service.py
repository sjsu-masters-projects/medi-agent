from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import ValidationError
from app.models.document_extraction import DocumentExtractionResult
from app.services.document_extraction_import_service import DocumentExtractionImportService

PATIENT_ID = UUID("00000000-0000-0000-0000-000000000222")


class FakeResult:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeTable:
    def __init__(self, name: str, store: dict[str, list[dict[str, Any]]]) -> None:
        self.name = name
        self.store = store
        self.filters: list[tuple[str, str]] = []
        self.pending_insert: dict[str, Any] | None = None
        self.pending_update: dict[str, Any] | None = None
        self.return_single = False

    def insert(self, payload: dict[str, Any]) -> FakeTable:
        self.pending_insert = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeTable:
        self.pending_update = payload
        return self

    def select(self, *_args: Any) -> FakeTable:
        return self

    def single(self) -> FakeTable:
        self.return_single = True
        return self

    def eq(self, column: str, value: Any) -> FakeTable:
        self.filters.append((column, str(value)))
        return self

    def execute(self) -> FakeResult:
        if self.pending_insert is not None:
            row = {
                "id": str(uuid4()),
                "created_at": "2026-05-01T00:00:00Z",
                "visibility": "all_providers",
                **self.pending_insert,
            }
            self.store.setdefault(self.name, []).append(row)
            self.pending_insert = None
            return FakeResult([row])
        if self.pending_update is not None:
            self.store.setdefault(f"{self.name}_updates", []).append(self.pending_update)
            payload = self.pending_update
            self.pending_update = None
            return FakeResult([payload])
        rows = self.store.get(self.name, [])
        for column, value in self.filters:
            rows = [row for row in rows if str(row.get(column)) == value]
        return FakeResult(rows[0] if self.return_single and rows else (None if self.return_single else rows))


class FakeStorageBucket:
    def create_signed_url(self, _file_path: str, _expiry_seconds: int) -> dict[str, str]:
        return {"signedURL": "https://storage.example.test/document.json"}


class FakeStorage:
    def from_(self, _bucket_name: str) -> FakeStorageBucket:
        return FakeStorageBucket()


class FakeSupabase:
    def __init__(self) -> None:
        self.store: dict[str, list[dict[str, Any]]] = {}
        self.storage = FakeStorage()

    def table(self, name: str) -> FakeTable:
        return FakeTable(name, self.store)


def _extraction() -> DocumentExtractionResult:
    return DocumentExtractionResult.model_validate(
        {
            "document": {"title": "Clinic Instructions", "document_type": "other"},
            "medications": [
                {
                    "name": "Aspirin",
                    "dosage": "81 mg",
                    "frequency": "daily",
                    "route": "oral",
                }
            ],
            "conditions": [{"name": "Hypertension"}],
            "allergies": [{"allergen": "Penicillin", "severity": "mild"}],
            "obligations": [{"description": "Walk daily"}],
        }
    )


@pytest.mark.asyncio
async def test_import_requires_a_verified_extraction() -> None:
    service = DocumentExtractionImportService(FakeSupabase())  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="verified extraction"):
        await service.import_extraction(
            patient_id=PATIENT_ID,
            uploaded_by=PATIENT_ID,
            uploaded_by_role="patient",
        )


@pytest.mark.asyncio
async def test_import_creates_pending_candidates_not_canonical_rows() -> None:
    db = FakeSupabase()
    service = DocumentExtractionImportService(db)  # type: ignore[arg-type]

    result = await service.import_extraction(
        patient_id=PATIENT_ID,
        uploaded_by=PATIENT_ID,
        uploaded_by_role="patient",
        extraction=_extraction(),
    )

    assert result["clinical_facts_created"] == 4
    assert result["medications_created"] == 0
    assert result["conditions_created"] == 0
    assert result["allergies_created"] == 0
    assert result["obligations_created"] == 0
    assert {fact["fact_type"] for fact in db.store["clinical_facts"]} == {
        "medication",
        "condition",
        "allergy",
        "obligation",
    }
    assert {fact["review_state"] for fact in db.store["clinical_facts"]} == {"pending_review"}
    assert all(
        fact["external_source_key"].startswith(f"document/{result['document']['id']}/")
        and fact["external_source_version"] == result["document"]["id"]
        for fact in db.store["clinical_facts"]
    )
    assert "medications" not in db.store
    assert "conditions" not in db.store
    assert "allergies" not in db.store
    assert "obligations" not in db.store
    assert db.store["document_ingestion_runs"][0]["status"] == "processing"
    assert db.store["document_ingestion_runs_updates"][-1] == {
        "status": "completed",
        "candidate_fact_count": 4,
        "error_message": None,
    }


@pytest.mark.asyncio
async def test_import_can_attach_candidates_to_the_explicit_patient_document() -> None:
    db = FakeSupabase()
    document_id = uuid4()
    db.store["documents"] = [
        {
            "id": str(document_id),
            "patient_id": str(PATIENT_ID),
            "uploaded_by": str(PATIENT_ID),
            "file_name": "uploaded.pdf",
        }
    ]
    service = DocumentExtractionImportService(db)  # type: ignore[arg-type]

    result = await service.import_extraction(
        patient_id=PATIENT_ID,
        uploaded_by=PATIENT_ID,
        uploaded_by_role="patient",
        document_id=document_id,
        extraction=_extraction(),
    )

    assert result["document"]["id"] == str(document_id)
    assert all(
        item["document_id"] == str(document_id) for item in db.store["source_provenances"]
    )
