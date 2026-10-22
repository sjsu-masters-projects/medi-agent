"""Synthetic clinical-core export, privacy delegation and pending-only re-import."""

from copy import deepcopy
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import AuthorizationError, ExternalServiceError, ValidationError
from app.services import fhir_record_export_service as exporter
from app.services.fhir_import_service import FhirImportService
from app.services.fhir_record_export_service import FhirRecordExportService, build_record_bundle
from tests.unit.services.test_fhir_import_service import Database


def core():
    return {
        "medications": [
            {
                "id": str(uuid4()),
                "name": "Synthetic medicine",
                "dosage": "10 mg",
                "frequency": "daily",
                "route": "oral",
                "instructions": "Synthetic instruction exactly as recorded",
            }
        ],
        "conditions": [
            {
                "id": str(uuid4()),
                "name": "Synthetic condition",
                "icd10_code": "E11.9",
                "status": "active",
            }
        ],
        "allergies": [
            {
                "id": str(uuid4()),
                "allergen": "Synthetic allergen",
                "reaction": "Rash",
                "severity": "unknown",
            }
        ],
        "some_conditions_private": True,
    }


def test_canonical_subset_round_trips_to_pending_candidates_without_mutating_records():
    patient_id = uuid4()
    source = core()
    original = deepcopy(source)
    bundle = build_record_bundle(patient_id, source)
    entries = bundle["entry"]
    assert FhirImportService.validate_resource(bundle) == []
    assert {entry["resource"]["resourceType"] for entry in entries} == {
        "Patient",
        "Condition",
        "AllergyIntolerance",
        "MedicationStatement",
    }
    full_urls = {entry["fullUrl"] for entry in entries}
    assert len(full_urls) == len(entries)
    for entry in entries[1:]:
        resource = entry["resource"]
        assert (resource.get("subject") or resource.get("patient"))["reference"] in full_urls
        assert resource["identifier"][0]["value"]
    allergy = entries[-1]["resource"]
    assert "severity" not in allergy["reaction"][0]
    assert any(tag["code"] == "some-conditions-withheld" for tag in bundle["meta"]["tag"])
    assert source == original
    db = Database()
    result = FhirImportService(db).import_resources(
        import_id=uuid4(),
        patient_id=patient_id,
        actor_id=uuid4(),
        issuer="https://synthetic.example/fhir",
        resources=[bundle],
    )
    assert result["candidate_facts_created"] == 4
    assert {row["review_state"] for row in db.store["clinical_facts"]} == {"pending_review"}
    assert not {"medications", "conditions", "allergies"}.intersection(db.store)
    assert not result["warnings"]
    mapped = {row["fact_type"]: row["value"] for row in db.store["clinical_facts"]}
    assert mapped["medication"]["name"] == source["medications"][0]["name"]
    assert "10 mg" in mapped["medication"]["dosage"][0]
    assert "daily" in mapped["medication"]["dosage"][0]
    assert mapped["medication"]["frequency"] == "daily"
    assert mapped["medication"]["instructions"] == "Synthetic instruction exactly as recorded"
    assert mapped["condition"]["icd10_code"] == "E11.9"
    assert mapped["allergy"]["reaction"] == "Rash"
    assert mapped["allergy"]["severity"] is None


def test_a_second_export_after_an_approved_update_uses_current_canonical_values():
    service = FhirRecordExportService(MagicMock())
    value = core()
    service.core.summary_for_clinician = MagicMock(side_effect=[deepcopy(value), value])
    patient_id, clinician_id = uuid4(), uuid4()
    first = service.export(clinician_id=clinician_id, patient_id=patient_id)
    value["medications"][0]["dosage"] = "20 mg"
    second = service.export(clinician_id=clinician_id, patient_id=patient_id)
    assert "10 mg" in first["entry"][1]["resource"]["dosage"][0]["text"]
    assert "20 mg" in second["entry"][1]["resource"]["dosage"][0]["text"]
    assert first["entry"][1]["fullUrl"] == second["entry"][1]["fullUrl"]


def test_export_uses_current_assignment_and_shared_core_privacy_not_raw_patient_tables():
    db = MagicMock()
    db.rpc.return_value.execute.return_value.data = core()
    patient_id, clinician_id = uuid4(), uuid4()
    result = FhirRecordExportService(db).export(clinician_id=clinician_id, patient_id=patient_id)
    assert result["type"] == "collection"
    db.rpc.assert_called_once_with(
        "shared_clinical_summary",
        {"p_clinician_id": str(clinician_id), "p_patient_id": str(patient_id)},
    )
    db.table.assert_not_called()


def test_revoked_assignment_cannot_export():
    service = FhirRecordExportService(MagicMock())
    service.core.summary_for_clinician = MagicMock(side_effect=AuthorizationError("unassigned"))
    with pytest.raises(AuthorizationError):
        service.export(clinician_id=uuid4(), patient_id=uuid4())


@pytest.mark.parametrize("value", [{}, {"medications": None, "conditions": [], "allergies": []}])
def test_unavailable_core_is_not_exported_as_empty(value):
    with pytest.raises(ExternalServiceError):
        build_record_bundle(uuid4(), value)


def test_invalid_canonical_data_fails_before_download():
    value = core()
    value["conditions"][0].pop("name")
    with pytest.raises(ValidationError):
        build_record_bundle(uuid4(), value)


@pytest.mark.parametrize("limit,value", [("MAX_IMPORT_RESOURCES", 3), ("MAX_IMPORT_BYTES", 100)])
def test_export_never_returns_a_truncated_bundle(monkeypatch, limit, value):
    monkeypatch.setattr(exporter, limit, value)
    with pytest.raises(ValidationError, match="limit exceeded"):
        build_record_bundle(uuid4(), core())


def test_empty_visible_core_contains_patient_and_explicit_subset_scope():
    bundle = build_record_bundle(uuid4(), {"medications": [], "conditions": [], "allergies": []})
    assert len(bundle["entry"]) == 1
    assert bundle["meta"]["tag"][0]["code"] == "clinical-core-subset"
