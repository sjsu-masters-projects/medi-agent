"""Unit tests for FHIR validation helpers."""

from uuid import UUID

from app.tools.fhir_builder import (
    build_allergy_intolerance,
    build_appointment,
    build_condition,
    build_medication_request,
    validate_extracted_data,
)

PATIENT_ID = UUID("00000000-0000-0000-0000-000000000123")
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000999")


def test_build_medication_request_valid():
    validated, error = build_medication_request(
        {
            "name": "Aspirin",
            "dosage": "81mg",
            "frequency": "once daily",
            "instructions": "Take with food",
            "route": "oral",
        },
        PATIENT_ID,
        DOCUMENT_ID,
    )

    assert error is None
    assert validated is not None
    assert validated["name"] == "Aspirin"
    assert validated["route"] == "oral"


def test_r4b_validator_accepts_r4_medication_request_fields():
    """Guard against a silent fallback to R5's medication[x] representation."""
    from fhir.resources.R4B.medicationrequest import MedicationRequest

    resource = MedicationRequest(
        status="active",
        intent="order",
        subject={"reference": f"Patient/{PATIENT_ID}"},
        medicationCodeableConcept={"text": "Aspirin"},
    )

    assert (
        resource.model_dump(by_alias=True, exclude_none=True)["resourceType"] == "MedicationRequest"
    )


def test_build_medication_request_missing_name():
    validated, error = build_medication_request({}, PATIENT_ID, DOCUMENT_ID)

    assert validated is None
    assert error is not None


def test_build_condition_valid():
    validated, error = build_condition(
        {"name": "Hypertension", "clinical_status": "active"},
        PATIENT_ID,
    )

    assert error is None
    assert validated is not None
    assert validated["name"] == "Hypertension"


def test_build_condition_missing_code():
    validated, error = build_condition({}, PATIENT_ID)

    assert validated is None
    assert error is not None


def test_build_allergy_intolerance_valid():
    validated, error = build_allergy_intolerance(
        {
            "substance": "Penicillin",
            "reaction": "Rash",
            "severity": "severe",
        },
        PATIENT_ID,
    )

    assert error is None
    assert validated is not None
    assert validated["allergen"] == "Penicillin"
    assert validated["severity"] == "severe"


def test_build_appointment_valid():
    validated, error = build_appointment(
        {
            "description": "Follow up with cardiology",
            "timing": "2 weeks",
            "provider": "Dr. Patel",
        },
        PATIENT_ID,
    )

    assert error is None
    assert validated is not None
    assert validated["timing"] == "2 weeks"


def test_validate_extracted_data_full():
    resources, errors = validate_extracted_data(
        {
            "medications": [{"name": "Metformin", "dosage": "500mg", "frequency": "twice daily"}],
            "conditions": [{"name": "Type 2 Diabetes"}],
            "allergies": [{"substance": "Penicillin", "reaction": "Rash"}],
            "follow_up_instructions": [{"description": "Return to clinic", "timing": "2 weeks"}],
        },
        PATIENT_ID,
        DOCUMENT_ID,
    )

    assert errors == []
    assert len(resources["medications"]) == 1
    assert len(resources["conditions"]) == 1
    assert len(resources["allergies"]) == 1
    assert len(resources["appointments"]) == 1


def test_validate_extracted_data_empty():
    resources, errors = validate_extracted_data({}, PATIENT_ID, DOCUMENT_ID)

    assert errors == []
    assert resources["medications"] == []
    assert resources["conditions"] == []
    assert resources["allergies"] == []
    assert resources["appointments"] == []
