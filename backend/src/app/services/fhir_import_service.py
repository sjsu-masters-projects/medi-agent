"""FHIR R4-compatible validation, persistence, and candidate-fact mapping."""

from __future__ import annotations

import hashlib
import html
import json
import re
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
        duplicate_count = 0
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
                duplicate_count += 1
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

        if resources and persisted_count == 0 and duplicate_count:
            warnings.append(
                "No new source resources were imported because this sandbox record was already imported."
            )

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
                # Direct FHIR transport preserves the source faithfully, but it
                # does not establish clinical certainty or approval locally.
                confidence_band=ConfidenceBand.UNKNOWN,
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
                    "name": FhirImportService._human_name(name),
                    "birthDate": resource.get("birthDate"),
                    "gender": resource.get("gender"),
                },
            }
        if resource_type == "Encounter":
            return {
                "fact_type": "encounter",
                "value": {
                    "class": FhirImportService._code_text(resource.get("class")),
                    "type": FhirImportService._code_texts(resource.get("type")),
                    "period": resource.get("period", {}),
                    "status": resource.get("status"),
                },
            }
        if resource_type == "Condition":
            return {
                "fact_type": "condition",
                "value": {
                    "name": code,
                    "clinical_status": FhirImportService._code_text(resource.get("clinicalStatus")),
                    "verification_status": FhirImportService._code_text(
                        resource.get("verificationStatus")
                    ),
                    "onset": resource.get("onsetDateTime") or resource.get("onsetPeriod"),
                    "recorded": resource.get("recordedDate"),
                },
            }
        if resource_type == "AllergyIntolerance":
            return {
                "fact_type": "allergy",
                "value": {
                    "allergen": code,
                    "clinical_status": FhirImportService._code_text(resource.get("clinicalStatus")),
                    "criticality": resource.get("criticality"),
                    "reactions": FhirImportService._reaction_summaries(resource.get("reaction")),
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
                    "intent": resource.get("intent"),
                    "dosage": FhirImportService._dosage_summary(
                        resource.get("dosageInstruction") or resource.get("dosage")
                    ),
                    "authored": resource.get("authoredOn")
                    or resource.get("dateAsserted")
                    or resource.get("effectiveDateTime")
                    or resource.get("effectivePeriod"),
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
                    "interpretation": FhirImportService._code_texts(resource.get("interpretation")),
                    "reference_range": FhirImportService._reference_range_summary(
                        resource.get("referenceRange")
                    ),
                },
            }
        if resource_type == "DiagnosticReport":
            return {
                "fact_type": "diagnostic_report",
                "value": {
                    "code": code,
                    "conclusion": resource.get("conclusion"),
                    "status": resource.get("status"),
                    "effective": resource.get("effectiveDateTime")
                    or resource.get("effectivePeriod"),
                    "issued": resource.get("issued"),
                    "result_count": len(resource.get("result", []))
                    if isinstance(resource.get("result"), list)
                    else None,
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
                    "reason": FhirImportService._code_texts(resource.get("reasonCode")),
                    "body_site": FhirImportService._code_texts(resource.get("bodySite")),
                },
            }
        if resource_type == "CarePlan":
            return {
                "fact_type": "care_plan",
                "value": {
                    "title": resource.get("title")
                    or FhirImportService._code_text((resource.get("category") or [{}])[0]),
                    "description": resource.get("description")
                    or FhirImportService._narrative_text(resource.get("text")),
                    "status": resource.get("status"),
                    "intent": resource.get("intent"),
                    "period": resource.get("period"),
                    "activities": FhirImportService._care_plan_activities(resource.get("activity")),
                    "addresses": FhirImportService._references(resource.get("addresses")),
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
                    "authors": FhirImportService._references(resource.get("author")),
                    "content_types": FhirImportService._document_content_types(
                        resource.get("content")
                    ),
                },
            }
        return None

    @staticmethod
    def _code_text(value: Any) -> str | None:
        if not isinstance(value, dict):
            return None
        text = value.get("text")
        if isinstance(text, str) and text.strip():
            return text
        display = value.get("display")
        if isinstance(display, str) and display.strip():
            return display
        code = value.get("code")
        if isinstance(code, str) and code.strip():
            return code
        coding = value.get("coding")
        if isinstance(coding, list) and coding and isinstance(coding[0], dict):
            return cast(str | None, coding[0].get("display") or coding[0].get("code"))
        return None

    @staticmethod
    def _code_texts(value: Any) -> list[str]:
        """Return readable text for one or more CodeableConcept/Coding values."""
        values = value if isinstance(value, list) else [value]
        return [text for item in values if (text := FhirImportService._code_text(item))]

    @staticmethod
    def _human_name(value: Any) -> str | None:
        if not isinstance(value, dict):
            return None
        parts = [
            *value.get("prefix", []),
            *value.get("given", []),
            value.get("family"),
            *value.get("suffix", []),
        ]
        readable = [part.strip() for part in parts if isinstance(part, str) and part.strip()]
        if readable:
            return " ".join(readable)
        text = value.get("text")
        return text if isinstance(text, str) and text.strip() else None

    @staticmethod
    def _references(value: Any) -> list[str]:
        values = value if isinstance(value, list) else [value]
        result: list[str] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            reference = item.get("display") or item.get("reference")
            if isinstance(reference, str) and reference:
                result.append(reference)
        return result

    @staticmethod
    def _reaction_summaries(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        summaries: list[str] = []
        for reaction in value:
            if not isinstance(reaction, dict):
                continue
            manifestations = FhirImportService._code_texts(reaction.get("manifestation"))
            severity = reaction.get("severity")
            label = ", ".join(manifestations) or "Reaction recorded"
            summaries.append(f"{label} ({severity})" if isinstance(severity, str) else label)
        return summaries

    @staticmethod
    def _dosage_summary(value: Any) -> list[str]:
        values = value if isinstance(value, list) else [value]
        summaries: list[str] = []
        for dosage in values:
            if not isinstance(dosage, dict):
                continue
            text = dosage.get("text")
            if isinstance(text, str) and text.strip():
                summaries.append(text.strip())
                continue
            timing = dosage.get("timing")
            dose_and_rate = dosage.get("doseAndRate")
            dose = None
            if (
                isinstance(dose_and_rate, list)
                and dose_and_rate
                and isinstance(dose_and_rate[0], dict)
            ):
                quantity = dose_and_rate[0].get("doseQuantity")
                if isinstance(quantity, dict):
                    dose = FhirImportService._quantity_text(quantity)
            frequency = None
            if isinstance(timing, dict) and isinstance(timing.get("code"), dict):
                frequency = FhirImportService._code_text(timing.get("code"))
            route = FhirImportService._code_text(dosage.get("route"))
            summary = " ".join(part for part in [dose, frequency, route] if part)
            if summary:
                summaries.append(summary)
        return summaries

    @staticmethod
    def _quantity_text(value: dict[str, Any]) -> str | None:
        number = value.get("value")
        unit = value.get("unit") or value.get("code")
        if number is None:
            return None
        return " ".join(str(part) for part in (number, unit) if part not in (None, ""))

    @staticmethod
    def _observation_value(resource: dict[str, Any]) -> Any:
        for key, value in resource.items():
            if key.startswith("value"):
                if key == "valueQuantity" and isinstance(value, dict):
                    return FhirImportService._quantity_text(value)
                if key == "valueCodeableConcept":
                    return FhirImportService._code_text(value)
                return value
        return None

    @staticmethod
    def _reference_range_summary(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        ranges: list[str] = []
        for reference_range in value:
            if not isinstance(reference_range, dict):
                continue
            low = reference_range.get("low")
            high = reference_range.get("high")
            text = reference_range.get("text")
            if isinstance(text, str) and text:
                ranges.append(text)
                continue
            parts = [
                FhirImportService._quantity_text(item)
                for item in (low, high)
                if isinstance(item, dict)
            ]
            readable_parts = [part for part in parts if part]
            if readable_parts:
                ranges.append(" to ".join(readable_parts))
        return ranges

    @staticmethod
    def _narrative_text(value: Any) -> str | None:
        if not isinstance(value, dict) or not isinstance(value.get("div"), str):
            return None
        text = re.sub(r"<[^>]+>", " ", value["div"])
        normalized = " ".join(html.unescape(text).split())
        return normalized or None

    @staticmethod
    def _care_plan_activities(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        activities: list[str] = []
        for activity in value:
            if not isinstance(activity, dict):
                continue
            detail = activity.get("detail")
            if not isinstance(detail, dict):
                continue
            label = FhirImportService._code_text(detail.get("code")) or detail.get("description")
            status = detail.get("status")
            if isinstance(label, str) and label:
                activities.append(f"{label} ({status})" if isinstance(status, str) else label)
        return activities

    @staticmethod
    def _document_content_types(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        content_types: list[str] = []
        for content in value:
            if not isinstance(content, dict):
                continue
            attachment = content.get("attachment")
            if isinstance(attachment, dict) and isinstance(attachment.get("contentType"), str):
                content_types.append(attachment["contentType"])
        return content_types

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
