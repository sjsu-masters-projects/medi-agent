"""Test Pydantic model validation — ensures schemas reject bad data."""

import pytest
from pydantic import ValidationError


def test_patient_signup_rejects_short_password():
    from app.models.auth import PatientSignupRequest

    with pytest.raises(ValidationError, match="String should have at least 8 characters"):
        PatientSignupRequest(
            email="test@example.com",
            password="short",
            first_name="Test",
            last_name="User",
            date_of_birth="2000-01-01",
        )


def test_patient_signup_rejects_bad_email():
    from app.models.auth import PatientSignupRequest

    with pytest.raises(ValidationError):
        PatientSignupRequest(
            email="not-an-email",
            password="validpassword123",
            first_name="Test",
            last_name="User",
            date_of_birth="2000-01-01",
        )


def test_patient_signup_rejects_bad_date_format():
    from app.models.auth import PatientSignupRequest

    with pytest.raises(ValidationError, match="String should match pattern"):
        PatientSignupRequest(
            email="test@example.com",
            password="validpassword123",
            first_name="Test",
            last_name="User",
            date_of_birth="Jan 1, 2000",
        )


def test_patient_signup_accepts_valid_data():
    from app.models.auth import PatientSignupRequest

    req = PatientSignupRequest(
        email="test@example.com",
        password="validpassword123",
        first_name="Test",
        last_name="User",
        date_of_birth="2000-01-15",
    )
    assert req.email == "test@example.com"
    assert req.first_name == "Test"


def test_medication_create_requires_name():
    from app.models.medication import MedicationCreate

    with pytest.raises(ValidationError):
        MedicationCreate(dosage="500mg", frequency="daily")  # missing name


def test_medication_create_valid():
    from app.models.medication import MedicationCreate

    med = MedicationCreate(
        name="Metformin",
        dosage="500mg",
        frequency="twice daily",
    )
    assert med.name == "Metformin"
    assert med.route.value == "oral"  # default


def test_adherence_log_requires_target():
    from app.models.adherence import AdherenceLog

    with pytest.raises(ValidationError):
        AdherenceLog(status="completed")  # missing target_type and target_id
