from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

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
        self.pending_insert: dict[str, Any] | None = None
        self.pending_update: dict[str, Any] | None = None

    def insert(self, payload: dict[str, Any]) -> FakeTable:
        self.pending_insert = payload
        return self

    def update(self, payload: dict[str, Any]) -> FakeTable:
        self.pending_update = payload
        return self

    def eq(self, *_args: Any) -> FakeTable:
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

        return FakeResult(self.store.get(self.name, []))


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


@pytest.mark.asyncio
async def test_import_demo_extraction_creates_document_derived_feed_records() -> None:
    db = FakeSupabase()
    service = DocumentExtractionImportService(db)  # type: ignore[arg-type]

    result = await service.import_extraction(
        patient_id=PATIENT_ID,
        uploaded_by=PATIENT_ID,
        uploaded_by_role="patient",
    )

    assert result["document"]["document_type"] == "discharge_summary"
    assert result["document"]["mime_type"] == "application/json"
    assert result["document"]["parse_status"] == "completed"
    assert result["medications_created"] == 2
    assert result["obligations_created"] == 1
    assert result["conditions_created"] == 1
    assert result["allergies_created"] == 1

    medication_names = {row["name"] for row in db.store["medications"]}
    assert {"Theophylline", "Ventolin Inhaler"} == medication_names
    assert all(
        row["source_document_id"] == result["document"]["id"] for row in db.store["medications"]
    )
    assert (
        db.store["obligations"][0]["description"]
        == "Review discharge instructions from Discharge Summary"
    )
    assert db.store["obligations"][0]["source_document_id"] == result["document"]["id"]
    assert db.store["documents_updates"][0]["parse_status"] == "completed"


@pytest.mark.asyncio
async def test_import_custom_extraction_uses_project_owned_schema() -> None:
    db = FakeSupabase()
    service = DocumentExtractionImportService(db)  # type: ignore[arg-type]
    extraction = DocumentExtractionResult.model_validate(
        {
            "document": {
                "title": "Clinic Instructions",
                "document_type": "other",
                "source_name": "City Health",
            },
            "summary": "Patient should hydrate and check blood pressure daily.",
            "medications": [],
            "conditions": [],
            "allergies": [],
            "obligations": [
                {
                    "description": "Check blood pressure",
                    "frequency": "daily",
                    "obligation_type": "custom",
                }
            ],
        }
    )

    result = await service.import_extraction(
        patient_id=PATIENT_ID,
        uploaded_by=PATIENT_ID,
        uploaded_by_role="patient",
        extraction=extraction,
    )

    assert result["document"]["file_name"] == "Clinic Instructions.json"
    assert result["document"]["source_clinic"] == "City Health"
    assert result["summary"] == "Patient should hydrate and check blood pressure daily."
    assert db.store["obligations"][0]["frequency"] == "daily"
    assert db.store["obligations"][0]["source_document_id"] == result["document"]["id"]
