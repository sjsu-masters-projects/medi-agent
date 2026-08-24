"""FHIR R4-compatible resource builder using maintained FHIR R4B models.

The FHIR objects are used for validation only. We still persist data in the
project's relational schema, so each builder returns a cleaned dict shaped for
our own tables on success.
"""

from __future__ import annotations

import logging
from typing import Any, cast
from uuid import UUID

from fhir.resources.R4B.allergyintolerance import AllergyIntolerance
from fhir.resources.R4B.condition import Condition
from fhir.resources.R4B.medicationrequest import MedicationRequest
from pydantic import ValidationError as PydanticValidationError
from pydantic.v1 import ValidationError as PydanticV1ValidationError

logger = logging.getLogger(__name__)

_VALID_ROUTES = {"oral", "topical", "iv", "im", "subcutaneous", "inhaled", "other"}
_VALID_SEVERITIES = {"mild", "moderate", "severe"}
_FHIR_VALIDATION_ERRORS = (PydanticValidationError, PydanticV1ValidationError)


def _string(value: Any) -> str:
    """Normalize a possibly-missing value to a stripped string."""
    return str(value or "").strip()


def _normalize_route(route: str) -> str:
    """Map a free-text route into the allowed medication route enum values."""
    normalized = route.strip().lower().replace("intravenous", "iv")
    return normalized if normalized in _VALID_ROUTES else "oral"


def _condition_status_payload(clinical_status: str) -> dict[str, Any]:
    """Build the FHIR clinical status coding structure."""
    code = _string(clinical_status).lower() or "active"
    return {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                "code": code,
            }
        ]
    }


def _validate_resource(resource_cls: Any, payload: dict[str, Any]) -> None:
    """Run FHIR model validation through a dynamic boundary for mypy."""
    cast(Any, resource_cls)(**payload)


def build_medication_request(
    med: dict[str, Any],
    patient_id: UUID,
    source_document_id: UUID | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Build and validate a FHIR MedicationRequest from extracted medication data."""
    name = _string(med.get("name"))
    if not name:
        return None, "Medication is missing a name"

    dosage = _string(med.get("dosage")) or "unspecified"
    frequency = _string(med.get("frequency")) or "as directed"
    instructions = _string(med.get("instructions")) or None
    route = _normalize_route(_string(med.get("route")) or "oral")

    payload: dict[str, Any] = {
        "status": "active",
        "intent": "order",
        "subject": {"reference": f"Patient/{patient_id}"},
        "medicationCodeableConcept": {"text": name},
        "dosageInstruction": [
            {"text": instructions or f"{dosage}, {frequency}", "route": {"text": route}}
        ],
    }

    try:
        _validate_resource(MedicationRequest, payload)
    except _FHIR_VALIDATION_ERRORS as exc:
        return None, f"Medication '{name}': {exc.errors()[0]['msg']}"

    return {
        "name": name,
        "dosage": dosage,
        "frequency": frequency,
        "instructions": instructions,
        "route": route,
        "source_document_id": str(source_document_id) if source_document_id else None,
    }, None


def build_condition(
    condition: dict[str, Any],
    patient_id: UUID,
) -> tuple[dict[str, Any] | None, str | None]:
    """Build and validate a FHIR Condition from extracted condition data."""
    name = _string(condition.get("name") or condition.get("code_text"))
    if not name:
        return None, "Condition is missing a name"

    clinical_status = _string(condition.get("clinical_status")) or "active"
    onset_date = _string(condition.get("onset_date")) or None
    payload: dict[str, Any] = {
        "subject": {"reference": f"Patient/{patient_id}"},
        "code": {"text": name},
        "clinicalStatus": _condition_status_payload(clinical_status),
    }
    if onset_date:
        payload["onsetString"] = onset_date

    try:
        _validate_resource(Condition, payload)
    except _FHIR_VALIDATION_ERRORS as exc:
        return None, f"Condition '{name}': {exc.errors()[0]['msg']}"

    notes = f"Onset date: {onset_date}" if onset_date else None
    return {
        "name": name,
        "status": clinical_status,
        "notes": notes,
    }, None


def build_allergy_intolerance(
    allergy: dict[str, Any],
    patient_id: UUID,
) -> tuple[dict[str, Any] | None, str | None]:
    """Build and validate a FHIR AllergyIntolerance from extracted allergy data."""
    substance = _string(allergy.get("substance") or allergy.get("allergen"))
    if not substance:
        return None, "Allergy is missing a substance"

    reaction = _string(allergy.get("reaction")) or None
    severity = (_string(allergy.get("severity")) or "moderate").lower()
    if severity not in _VALID_SEVERITIES:
        severity = "moderate"

    payload: dict[str, Any] = {
        "patient": {"reference": f"Patient/{patient_id}"},
        "code": {"text": substance},
    }
    if reaction:
        payload["reaction"] = [{"manifestation": [{"text": reaction}]}]

    try:
        _validate_resource(AllergyIntolerance, payload)
    except _FHIR_VALIDATION_ERRORS as exc:
        return None, f"Allergy '{substance}': {exc.errors()[0]['msg']}"

    return {
        "allergen": substance,
        "reaction": reaction,
        "severity": severity,
    }, None


def build_appointment(
    instruction: dict[str, Any],
    patient_id: UUID,
) -> tuple[dict[str, Any] | None, str | None]:
    """Build an appointment-shaped dict from follow-up instruction data."""
    description = _string(instruction.get("description") or instruction.get("name"))
    if not description:
        return None, "Follow-up instruction is missing a description"

    timing = _string(instruction.get("timing") or instruction.get("date")) or None
    provider = _string(instruction.get("provider")) or None
    return {
        "description": description,
        "timing": timing,
        "provider": provider,
        "patient_reference": f"Patient/{patient_id}",
    }, None


def validate_extracted_data(
    extracted_data: dict[str, Any],
    patient_id: UUID,
    source_document_id: UUID | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Validate all extracted data against FHIR schemas."""
    validated_resources: dict[str, list[dict[str, Any]]] = {
        "medications": [],
        "conditions": [],
        "allergies": [],
        "appointments": [],
        "follow_up_instructions": [],
    }
    validation_errors: list[str] = []

    for med in extracted_data.get("medications", []) or []:
        validated, error = build_medication_request(med, patient_id, source_document_id)
        if validated:
            validated_resources["medications"].append(validated)
        if error:
            validation_errors.append(error)

    for condition in extracted_data.get("conditions", []) or []:
        validated, error = build_condition(condition, patient_id)
        if validated:
            validated_resources["conditions"].append(validated)
        if error:
            validation_errors.append(error)

    for allergy in extracted_data.get("allergies", []) or []:
        validated, error = build_allergy_intolerance(allergy, patient_id)
        if validated:
            validated_resources["allergies"].append(validated)
        if error:
            validation_errors.append(error)

    appointment_candidates = [
        *(extracted_data.get("appointments", []) or []),
        *(extracted_data.get("follow_up_instructions", []) or []),
    ]
    for appointment in appointment_candidates:
        validated, error = build_appointment(appointment, patient_id)
        if validated:
            validated_resources["appointments"].append(validated)
            validated_resources["follow_up_instructions"].append(validated)
        if error:
            validation_errors.append(error)

    return validated_resources, validation_errors
