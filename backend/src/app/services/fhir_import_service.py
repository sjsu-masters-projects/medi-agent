"""FHIR R4-compatible validation, persistence, and candidate-fact mapping."""

from __future__ import annotations

import hashlib
import json
from importlib import import_module
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core.exceptions import ValidationError
from app.models.clinical_fact import (
    ClinicalFactCreate,
    ConfidenceBand,
    EvidenceCitationCreate,
    SourceArtifactType,
    SourceProvenanceCreate,
)
from app.services.clinical_fact_service import ClinicalFactService

SUPPORTED_RESOURCE_TYPES = frozenset(
    {
        "Patient",
        "Encounter",
        "Condition",
        "AllergyIntolerance",
        "MedicationRequest",
        "MedicationStatement",
        "Observation",
        "DiagnosticReport",
        "Procedure",
        "CarePlan",
        "DocumentReference",
        "Bundle",
    }
)

_FHIR_MODULES = {
    "Patient": "patient",
    "Encounter": "encounter",
    "Condition": "condition",
    "AllergyIntolerance": "allergyintolerance",
    "MedicationRequest": "medicationrequest",
    "MedicationStatement": "medicationstatement",
    "Observation": "observation",
    "DiagnosticReport": "diagnosticreport",
    "Procedure": "procedure",
    "CarePlan": "careplan",
    "DocumentReference": "documentreference",
    "Bundle": "bundle",
}


class FhirImportService:
    """Store raw resources and create only pending, provenance-backed facts."""

    def __init__(self, db: Client) -> None:
        self.db = db
        self.facts = ClinicalFactService(db)

    def import_resources(
        self,
        *,
        import_id: UUID,
        patient_id: UUID,
        actor_id: UUID,
        issuer: str,
        resources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Validate and persist resources; unsupported types stay visible as warnings."""
        warnings: list[str] = []
        persisted_count = 0
        candidate_count = 0
        for resource in self.expand_bundles(resources):
            resource_type = str(resource.get("resourceType", ""))
            validation_errors = self.validate_resource(resource)
            if validation_errors:
                warnings.append(
                    f"{resource_type or 'Unknown'} resource was not mapped: validation failed."
                )

            mapping_warnings: list[str] = []
            if resource_type not in SUPPORTED_RESOURCE_TYPES - {"Bundle"}:
                mapping_warnings.append(
                    f"Unsupported FHIR resource type: {resource_type or 'missing'}."
                )
                warnings.extend(mapping_warnings)

            stored, is_new = self._store_resource(
                import_id=import_id,
                issuer=issuer,
                resource=resource,
                validation_errors=validation_errors,
                mapping_warnings=mapping_warnings,
            )
            if not is_new:
                continue
            persisted_count += 1
            if validation_errors or mapping_warnings:
                continue
            for candidate in self._map_candidates(
                patient_id=patient_id,
                issuer=issuer,
                stored_resource=stored,
                resource=resource,
            ):
                self.facts.create_candidate(candidate, actor_id=actor_id)
                candidate_count += 1

        return {
            "resources_persisted": persisted_count,
            "candidate_facts_created": candidate_count,
            "warnings": sorted(set(warnings)),
        }

    @staticmethod
    def expand_bundles(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Preserve raw Bundle envelopes and recursively expose their entries for mapping."""
        flattened: list[dict[str, Any]] = []
        for resource in resources:
            if resource.get("resourceType") != "Bundle":
                flattened.append(resource)
                continue
            flattened.append(resource)
            for entry in resource.get("entry", []):
                nested = entry.get("resource") if isinstance(entry, dict) else None
                if isinstance(nested, dict):
                    flattened.extend(FhirImportService.expand_bundles([nested]))
        return flattened

    @staticmethod
    def validate_resource(resource: dict[str, Any]) -> list[str]:
        """Validate supported JSON with the maintained R4B model boundary."""
        resource_type = resource.get("resourceType")
        if not isinstance(resource_type, str) or not resource_type:
            return ["resourceType is required"]
        module_name = _FHIR_MODULES.get(resource_type)
        if not module_name:
            return []
        try:
            module = import_module(f"fhir.resources.R4B.{module_name}")
            model = getattr(module, resource_type)
            model.model_validate(resource)
        except Exception as exc:
            return [str(exc)]
        return []

    def _store_resource(
        self,
        *,
        import_id: UUID,
        issuer: str,
        resource: dict[str, Any],
        validation_errors: list[str],
        mapping_warnings: list[str],
    ) -> tuple[dict[str, Any], bool]:
        resource_type = str(resource.get("resourceType", "Unknown"))
        external_id = str(resource.get("id")) if resource.get("id") else None
        version_id = self._nested_string(resource, "meta", "versionId")
        content_hash = hashlib.sha256(
            json.dumps(resource, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        dedupe_key = f"{issuer.rstrip('/')}/{resource_type}/{external_id or content_hash}/{version_id or content_hash}"
        existing = (
            self.db.table("fhir_import_resources")
            .select("*")
            .eq("dedupe_key", dedupe_key)
            .execute()
        )
        rows = cast(list[dict[str, Any]], existing.data or [])
        if rows:
            return rows[0], False
        result = (
            self.db.table("fhir_import_resources")
            .insert(
                {
                    "import_id": str(import_id),
                    "issuer": issuer.rstrip("/"),
                    "resource_type": resource_type,
                    "external_resource_id": external_id,
                    "version_id": version_id,
                    "dedupe_key": dedupe_key,
                    "content_hash": content_hash,
                    "raw_resource": resource,
                    "validation_errors": validation_errors,
                    "mapping_warnings": mapping_warnings,
                }
            )
            .execute()
        )
        rows = cast(list[dict[str, Any]], result.data or [])
        if not rows:
            raise ValidationError("Could not persist FHIR resource")
        return rows[0], True

    def _map_candidates(
        self,
        *,
        patient_id: UUID,
        issuer: str,
        stored_resource: dict[str, Any],
        resource: dict[str, Any],
    ) -> list[ClinicalFactCreate]:
        mapped = self._map_resource(resource)
        if mapped is None:
            return []
        resource_id = str(stored_resource["id"])
        resource_type = str(resource["resourceType"])
        return [
            ClinicalFactCreate(
                patient_id=patient_id,
                fact_type=mapped["fact_type"],
                subject_type=resource_type,
                value=mapped["value"],
                confidence_band=ConfidenceBand.HIGH,
                uncertainty=["Imported data requires clinician review before clinical use."],
                provenance=SourceProvenanceCreate(
                    artifact_type=SourceArtifactType.FHIR_RESOURCE,
                    source_system=issuer.rstrip("/"),
                    source_reference=f"fhir_import_resources/{resource_id}",
                    document_location={
                        "resource_type": resource_type,
                        "resource_id": resource.get("id"),
                    },
                    extractor_version="fhir-r4-import/1",
                ),
                citations=[
                    EvidenceCitationCreate(
                        excerpt=self._citation_excerpt(resource),
                        location={"resource_id": resource.get("id"), "json_path": "$"},
                    )
                ],
            )
        ]

    @staticmethod
    def _map_resource(resource: dict[str, Any]) -> dict[str, Any] | None:
        resource_type = resource.get("resourceType")
        code = FhirImportService._code_text(resource.get("code"))
        if resource_type == "Patient":
            name = (resource.get("name") or [{}])[0]
            return {
                "fact_type": "patient_demographics",
                "value": {
                    "name": name,
                    "birthDate": resource.get("birthDate"),
                    "gender": resource.get("gender"),
                },
            }
        if resource_type == "Encounter":
            return {
                "fact_type": "encounter",
                "value": {
                    "class": resource.get("class"),
                    "type": resource.get("type", []),
                    "period": resource.get("period", {}),
                    "status": resource.get("status"),
                },
            }
        if resource_type == "Condition":
            return {
                "fact_type": "condition",
                "value": {
                    "name": code,
                    "clinical_status": resource.get("clinicalStatus"),
                    "onset": resource.get("onsetDateTime") or resource.get("onsetPeriod"),
                },
            }
        if resource_type == "AllergyIntolerance":
            return {
                "fact_type": "allergy",
                "value": {
                    "allergen": code,
                    "clinical_status": resource.get("clinicalStatus"),
                    "reactions": resource.get("reaction", []),
                },
            }
        if resource_type in {"MedicationRequest", "MedicationStatement"}:
            medication = (
                resource.get("medicationCodeableConcept")
                or resource.get("medicationReference")
                or {}
            )
            return {
                "fact_type": "medication",
                "value": {
                    "name": FhirImportService._code_text(medication),
                    "status": resource.get("status"),
                    "dosage": resource.get("dosageInstruction") or resource.get("dosage", []),
                },
            }
        if resource_type == "Observation":
            return {
                "fact_type": "observation",
                "value": {
                    "code": code,
                    "value": FhirImportService._observation_value(resource),
                    "effective": resource.get("effectiveDateTime")
                    or resource.get("effectivePeriod"),
                    "status": resource.get("status"),
                },
            }
        if resource_type == "DiagnosticReport":
            return {
                "fact_type": "diagnostic_report",
                "value": {
                    "code": code,
                    "conclusion": resource.get("conclusion"),
                    "status": resource.get("status"),
                },
            }
        if resource_type == "Procedure":
            return {
                "fact_type": "procedure",
                "value": {
                    "code": code,
                    "status": resource.get("status"),
                    "performed": resource.get("performedDateTime")
                    or resource.get("performedPeriod"),
                },
            }
        if resource_type == "CarePlan":
            return {
                "fact_type": "care_plan",
                "value": {
                    "title": resource.get("title"),
                    "description": resource.get("description"),
                    "status": resource.get("status"),
                    "intent": resource.get("intent"),
                },
            }
        if resource_type == "DocumentReference":
            return {
                "fact_type": "document_reference",
                "value": {
                    "type": FhirImportService._code_text(resource.get("type")),
                    "description": resource.get("description"),
                    "status": resource.get("status"),
                    "date": resource.get("date"),
                },
            }
        return None

    @staticmethod
    def _code_text(value: Any) -> str | None:
        if not isinstance(value, dict):
            return None
        text = value.get("text")
        if isinstance(text, str):
            return text
        coding = value.get("coding")
        if isinstance(coding, list) and coding and isinstance(coding[0], dict):
            return cast(str | None, coding[0].get("display") or coding[0].get("code"))
        return None

    @staticmethod
    def _observation_value(resource: dict[str, Any]) -> Any:
        for key, value in resource.items():
            if key.startswith("value"):
                return value
        return None

    @staticmethod
    def _citation_excerpt(resource: dict[str, Any]) -> str:
        return f"FHIR {resource.get('resourceType', 'resource')} {resource.get('id', '')}".strip()

    @staticmethod
    def _nested_string(data: dict[str, Any], *keys: str) -> str | None:
        value: Any = data
        for key in keys:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        return value if isinstance(value, str) else None
