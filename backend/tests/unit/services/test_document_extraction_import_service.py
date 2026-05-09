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

        if self.return_single:
            return FakeResult(rows[0] if rows else None)
        return FakeResult(rows)


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


@pytest.mark.asyncio
async def test_import_extraction_can_attach_to_existing_uploaded_document() -> None:
    db = FakeSupabase()
    document_id = uuid4()
    db.store["documents"] = [
        {
            "id": str(document_id),
            "patient_id": str(PATIENT_ID),
            "uploaded_by": str(PATIENT_ID),
            "uploaded_by_role": "patient",
            "file_name": "vatsal-discharge-summary.pdf",
            "file_url": "https://storage.example.test/document.pdf",
            "file_path": f"{PATIENT_ID}/vatsal-discharge-summary.pdf",
            "file_size_bytes": 1200,
            "mime_type": "application/pdf",
            "document_type": "discharge_summary",
            "source_clinic": "Patient uploaded document",
            "parsed": False,
            "ai_summary": None,
            "parse_status": "pending",
            "parse_error": None,
            "parse_attempts": 0,
            "visibility": "all_providers",
            "created_at": "2026-05-01T00:00:00Z",
        }
    ]
    service = DocumentExtractionImportService(db)  # type: ignore[arg-type]

    result = await service.import_extraction(
        patient_id=PATIENT_ID,
        uploaded_by=PATIENT_ID,
        uploaded_by_role="patient",
        document_id=document_id,
    )

    assert result["document"]["id"] == str(document_id)
    assert result["document"]["file_name"] == "vatsal-discharge-summary.pdf"
    assert len(db.store["documents"]) == 1
    assert db.store["documents_updates"][0]["parse_status"] == "completed"
    assert all(row["source_document_id"] == str(document_id) for row in db.store["medications"])
    assert all(row["source_document_id"] == str(document_id) for row in db.store["obligations"])
