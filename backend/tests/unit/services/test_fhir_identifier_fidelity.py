"""The supported synthetic R4 import set retains exact identifiers and raw JSON."""

import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.fhir_identifiers import source_identifiers
from app.services.fhir_import_service import SUPPORTED_RESOURCE_TYPES, FhirImportService
from tests.unit.services.test_fhir_import_service import Database

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures/fhir/synthetic-r4-collection.json"


def test_all_supported_resources_retain_identifiers_original_json_and_duplicate_semantics():
    bundle = json.loads(FIXTURE.read_text())
    original = deepcopy(bundle)
    resources = FhirImportService.expand_bundles([bundle])
    assert {row["resourceType"] for row in resources} == SUPPORTED_RESOURCE_TYPES
    assert all(FhirImportService.validate_resource(row) == [] for row in resources)
    db = Database()
    service = FhirImportService(db)
    kwargs = dict(
        import_id=uuid4(),
        patient_id=uuid4(),
        actor_id=uuid4(),
        issuer="https://synthetic.example/fhir",
        resources=[bundle],
    )
    first = service.import_resources(**kwargs)
    assert first["candidate_facts_created"] == 11
    assert first["resources_persisted"] == 12
    assert first["warnings"] == []
    assert bundle == original
    assert [row["raw_resource"] for row in db.store["fhir_import_resources"]] == resources
    for row in db.store["source_provenances"]:
        assert row["document_location"]["identifiers"][0]["value"] == "00aBc"
    second = service.import_resources(**kwargs)
    assert second["candidate_facts_created"] == 0
    assert second["resources_persisted"] == 0


@pytest.mark.parametrize(
    "identifier", ["bad", [{"system": "urn:synthetic", "value": {"nested": "bad"}}]]
)
def test_malformed_identifiers_are_retained_only_as_invalid_source_evidence(identifier):
    resource = {"resourceType": "Patient", "id": "synthetic", "identifier": identifier}
    db = Database()
    result = FhirImportService(db).import_resources(
        import_id=uuid4(),
        patient_id=uuid4(),
        actor_id=uuid4(),
        issuer="https://synthetic.example/fhir",
        resources=[resource],
    )
    assert result["candidate_facts_created"] == 0
    assert db.store["fhir_import_resources"][0]["raw_resource"] == resource
    assert db.store["fhir_import_resources"][0]["validation_errors"]


def test_identifier_cardinality_is_normalized_but_value_whitespace_case_and_zeroes_are_not():
    resource = {"identifier": {"system": "urn:synthetic:Bundle", "value": " 00aBc "}}
    result = source_identifiers(resource)
    assert result["identifiers"] == [resource["identifier"]]
    result["identifiers"][0]["value"] = "edited"
    assert resource["identifier"]["value"] == " 00aBc "
