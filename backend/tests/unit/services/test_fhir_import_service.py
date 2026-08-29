"""FHIR import mapping tests using an in-memory Supabase-shaped store."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from app.services.fhir_import_service import FhirImportService

PATIENT_ID = UUID("00000000-0000-0000-0000-000000000111")
CLINICIAN_ID = UUID("00000000-0000-0000-0000-000000000222")
IMPORT_ID = UUID("00000000-0000-0000-0000-000000000333")


class Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class Table:
    def __init__(self, name: str, store: dict[str, list[dict[str, Any]]]) -> None:
        self.name = name
        self.store = store
        self.filters: list[tuple[str, str]] = []
        self.payload: dict[str, Any] | None = None

    def select(self, *_fields: str) -> Table:
        return self

    def eq(self, column: str, value: Any) -> Table:
        self.filters.append((column, str(value)))
        return self

    def insert(self, payload: dict[str, Any]) -> Table:
        self.payload = payload
        return self

    def execute(self) -> Result:
        rows = self.store.setdefault(self.name, [])
        if self.payload is not None:
            row = {"id": str(uuid4()), "created_at": "2026-08-20T00:00:00Z", **self.payload}
            rows.append(row)
            return Result([row])
        return Result(
            [
                row
                for row in rows
                if all(str(row.get(column)) == value for column, value in self.filters)
            ]
        )


class Database:
    def __init__(self) -> None:
        self.store: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> Table:
        return Table(name, self.store)


def patient() -> dict[str, Any]:
    return {
        "resourceType": "Patient",
        "id": "sandbox-patient",
        "name": [{"family": "Garcia", "given": ["Elena"]}],
        "gender": "female",
        "birthDate": "1988-05-20",
    }


def medication() -> dict[str, Any]:
    return {
        "resourceType": "MedicationRequest",
        "id": "med-1",
        "status": "active",
        "intent": "order",
        "subject": {"reference": "Patient/sandbox-patient"},
        "medicationCodeableConcept": {"text": "Metformin"},
    }


def test_supported_resources_become_pending_provenance_backed_facts() -> None:
    db = Database()
    service = FhirImportService(db)  # type: ignore[arg-type]

    result = service.import_resources(
        import_id=IMPORT_ID,
        patient_id=PATIENT_ID,
        actor_id=CLINICIAN_ID,
        issuer="https://sandbox.example/fhir",
        resources=[patient(), medication()],
    )

    assert result == {"resources_persisted": 2, "candidate_facts_created": 2, "warnings": []}
    assert {row["review_state"] for row in db.store["clinical_facts"]} == {"pending_review"}
    assert {row["confidence_band"] for row in db.store["clinical_facts"]} == {"unknown"}
    assert len(db.store["source_provenances"]) == 2
    assert all(row["artifact_type"] == "fhir_resource" for row in db.store["source_provenances"])
    assert len(db.store["clinical_fact_audit_events"]) == 2


def test_duplicate_resource_does_not_create_duplicate_candidate_facts() -> None:
    db = Database()
    service = FhirImportService(db)  # type: ignore[arg-type]
    kwargs = {
        "import_id": IMPORT_ID,
        "patient_id": PATIENT_ID,
        "actor_id": CLINICIAN_ID,
        "issuer": "https://sandbox.example/fhir",
        "resources": [medication()],
    }

    service.import_resources(**kwargs)
    second = service.import_resources(**kwargs)

    assert second["resources_persisted"] == 0
    assert second["candidate_facts_created"] == 0
    assert second["warnings"] == [
        "No new source resources were imported because this sandbox record was already imported."
    ]
    assert len(db.store["clinical_facts"]) == 1


def test_unsupported_and_invalid_resources_are_preserved_without_mapping() -> None:
    db = Database()
    service = FhirImportService(db)  # type: ignore[arg-type]
    unsupported = {"resourceType": "Immunization", "id": "imm-1", "status": "completed"}
    invalid = {"resourceType": "MedicationRequest", "id": "missing-required-fields"}

    result = service.import_resources(
        import_id=IMPORT_ID,
        patient_id=PATIENT_ID,
        actor_id=CLINICIAN_ID,
        issuer="https://sandbox.example/fhir",
        resources=[unsupported, invalid],
    )

    assert result["resources_persisted"] == 2
    assert result["candidate_facts_created"] == 0
    assert len(result["warnings"]) == 2
    assert len(db.store.get("clinical_facts", [])) == 0
    assert db.store["fhir_import_resources"][0]["raw_resource"] == unsupported


def test_bundle_envelopes_and_entries_are_preserved_for_validation_and_mapping() -> None:
    bundle = {"resourceType": "Bundle", "type": "searchset", "entry": [{"resource": medication()}]}

    assert FhirImportService.expand_bundles([bundle]) == [bundle, medication()]
    assert FhirImportService.validate_resource(medication()) == []


def test_care_plan_mapping_uses_category_narrative_and_activities_when_title_is_absent() -> None:
    mapped = FhirImportService._map_resource(
        {
            "resourceType": "CarePlan",
            "status": "completed",
            "intent": "order",
            "category": [{"coding": [{"display": "Fracture care"}]}],
            "text": {"div": "<div>Care plan for fracture care.<br/>Activities: rest.</div>"},
            "period": {"start": "2016-01-03", "end": "2016-02-02"},
            "activity": [
                {
                    "detail": {
                        "code": {"coding": [{"display": "Recommendation to rest"}]},
                        "status": "completed",
                    }
                }
            ],
        }
    )

    assert mapped == {
        "fact_type": "care_plan",
        "value": {
            "title": "Fracture care",
            "description": "Care plan for fracture care. Activities: rest.",
            "status": "completed",
            "intent": "order",
            "period": {"start": "2016-01-03", "end": "2016-02-02"},
            "activities": ["Recommendation to rest (completed)"],
            "addresses": [],
        },
    }


def test_observation_mapping_keeps_quantity_interpretation_and_reference_range_readable() -> None:
    mapped = FhirImportService._map_resource(
        {
            "resourceType": "Observation",
            "status": "final",
            "code": {"coding": [{"display": "Hemoglobin"}]},
            "valueQuantity": {"value": 12.4, "unit": "g/dL"},
            "interpretation": [{"coding": [{"display": "Normal"}]}],
            "referenceRange": [
                {"low": {"value": 12, "unit": "g/dL"}, "high": {"value": 16, "unit": "g/dL"}}
            ],
        }
    )

    assert mapped is not None
    assert mapped["value"]["value"] == "12.4 g/dL"
    assert mapped["value"]["interpretation"] == ["Normal"]
    assert mapped["value"]["reference_range"] == ["12 g/dL to 16 g/dL"]
