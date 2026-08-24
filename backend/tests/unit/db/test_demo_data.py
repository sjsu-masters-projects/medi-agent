"""Regression tests for the canonical synthetic demo source."""

import hashlib

from app.db.seed.demo_data import CANONICAL_FIXTURE_PATH, load_canonical_fixture


def test_canonical_fixture_identity_and_language_mix_are_immutable() -> None:
    fixture = load_canonical_fixture()

    assert CANONICAL_FIXTURE_PATH.is_file()
    assert fixture.dataset_id == "SYN-CA-PORTAL-DEMO-2026-08"
    assert (
        hashlib.sha256(CANONICAL_FIXTURE_PATH.read_bytes()).hexdigest()
        == "841d59500293c946729f4a1e06a89a702070d79b6ff1408d9cd82769dd548fb8"
    )
    assert len(fixture.patients) == 8
    assert len({patient.source_id for patient in fixture.patients}) == 8
    assert [patient.preferred_language for patient in fixture.patients].count("en-US") == 5
    assert [patient.preferred_language for patient in fixture.patients].count("es-MX") == 3


def test_every_patient_has_source_specific_clinical_content() -> None:
    fixture = load_canonical_fixture()

    assert all(
        patient.conditions and patient.medications and patient.documents
        for patient in fixture.patients
    )
    assert (
        len(
            {
                tuple(medication.label for medication in patient.medications)
                for patient in fixture.patients
            }
        )
        == 8
    )
