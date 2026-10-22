"""A read-only FHIR snapshot of the clinician-visible canonical clinical core.

This is not an order, a complete chart, a handoff approval or an external write.
Sensitive-condition visibility is owned by the existing shared-core database function.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from supabase import Client

from app.core.exceptions import ExternalServiceError, ValidationError
from app.services.fhir_import_limits import MAX_IMPORT_BYTES, MAX_IMPORT_RESOURCES
from app.services.fhir_import_service import FhirImportService
from app.services.shared_clinical_core_service import SharedClinicalCoreService

IDENTIFIER_SYSTEM = "urn:mediagent:local-record"
EXPORT_SCOPE_SYSTEM = "urn:mediagent:export-scope"


def _full_url(resource_type: str, resource_id: str) -> str:
    return f"urn:uuid:{uuid5(NAMESPACE_URL, f'{IDENTIFIER_SYSTEM}/{resource_type}/{resource_id}')}"


def _medication_fields(row: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "status": "active",
        "medicationCodeableConcept": {"text": row["name"]},
    }
    text = "; ".join(
        str(row[key]) for key in ("dosage", "frequency", "instructions") if row.get(key)
    )
    dosage: dict[str, Any] = {"text": text} if text else {}
    if row.get("route"):
        dosage["route"] = {"text": row["route"]}
    if dosage:
        fields["dosage"] = [dosage]
    return fields


def _condition_fields(row: dict[str, Any]) -> dict[str, Any]:
    code: dict[str, Any] = {"text": row["name"]}
    if row.get("icd10_code"):
        code["coding"] = [
            {"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": row["icd10_code"]}
        ]
    return {
        "code": code,
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active",
                }
            ]
        },
    }


def _allergy_fields(row: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {"code": {"text": row["allergen"]}}
    if row.get("reaction"):
        reaction: dict[str, Any] = {"manifestation": [{"text": row["reaction"]}]}
        if row.get("severity") in {"mild", "moderate", "severe"}:
            reaction["severity"] = row["severity"]
        fields["reaction"] = [reaction]
    return fields


def _resource(table: str, row: dict[str, Any], patient_id: UUID) -> dict[str, Any]:
    resource_type = {
        "medications": "MedicationStatement",
        "conditions": "Condition",
        "allergies": "AllergyIntolerance",
    }[table]
    local_id = str(UUID(str(row["id"])))
    reference = {"reference": _full_url("Patient", str(patient_id))}
    resource: dict[str, Any] = {
        "resourceType": resource_type,
        "id": local_id,
        "identifier": [{"system": IDENTIFIER_SYSTEM, "value": f"{table}/{local_id}"}],
        "patient" if table == "allergies" else "subject": reference,
    }
    fields = {
        "medications": _medication_fields,
        "conditions": _condition_fields,
        "allergies": _allergy_fields,
    }[table]
    resource.update(fields(row))
    return resource


def _resources(patient_id: UUID, core: dict[str, Any]) -> list[dict[str, Any]]:
    tables = ("medications", "conditions", "allergies")
    if any(not isinstance(core.get(table), list) for table in tables):
        raise ExternalServiceError("FHIR export", "Clinical core is unavailable")
    if sum(len(core[table]) for table in tables) + 2 > MAX_IMPORT_RESOURCES:
        raise ValidationError("FHIR export resource limit exceeded")
    resources: list[dict[str, Any]] = [{"resourceType": "Patient", "id": str(patient_id)}]
    try:
        for table in tables:
            for row in core[table]:
                resources.append(_resource(table, row, patient_id))
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValidationError(
            "Canonical records cannot be represented in the supported FHIR subset"
        ) from None
    return resources


def build_record_bundle(patient_id: UUID, core: dict[str, Any]) -> dict[str, Any]:
    """Export only the supported canonical subset; refuse invalid or oversized snapshots."""
    resources = _resources(patient_id, core)
    tags = [{"system": EXPORT_SCOPE_SYSTEM, "code": "clinical-core-subset"}]
    if core.get("some_conditions_private"):
        tags.append({"system": EXPORT_SCOPE_SYSTEM, "code": "some-conditions-withheld"})
    bundle = {
        "resourceType": "Bundle",
        "id": str(uuid4()),
        "type": "collection",
        "timestamp": datetime.now(UTC).isoformat(),
        "meta": {"tag": tags},
        "entry": [
            {"fullUrl": _full_url(row["resourceType"], row["id"]), "resource": row}
            for row in resources
        ],
    }
    if any(FhirImportService.validate_resource(row) for row in [*resources, bundle]):
        raise ValidationError("Canonical records failed FHIR export validation")
    if len(json.dumps([bundle], allow_nan=False).encode()) > MAX_IMPORT_BYTES:
        raise ValidationError("FHIR export byte limit exceeded")
    return bundle


class FhirRecordExportService:
    def __init__(self, db: Client) -> None:
        self.core = SharedClinicalCoreService(db)

    def export(self, *, clinician_id: UUID, patient_id: UUID) -> dict[str, Any]:
        # This RPC rechecks current assignment and sensitive-condition permissions on every call.
        return build_record_bundle(
            patient_id, self.core.summary_for_clinician(clinician_id, patient_id)
        )
