"""Regression tests for the canonical synthetic demo source."""

import hashlib
import json

from app.db.seed.demo_data import CANONICAL_FIXTURE_PATH, load_canonical_fixture


def test_canonical_fixture_identity_and_language_mix_are_immutable() -> None:
    fixture = load_canonical_fixture()

    assert CANONICAL_FIXTURE_PATH.is_file()
    assert fixture.dataset_id == "SYN-CA-PORTAL-DEMO-2026-08"
    assert (
        hashlib.sha256(CANONICAL_FIXTURE_PATH.read_bytes()).hexdigest()
        == "f051f5499bfee4384c0327b7d25b0aa59fb52a011b14c4140ba726cc4a1c7ad7"
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


def test_customer_facing_fixture_content_uses_natural_fictional_names() -> None:
    raw = json.loads(CANONICAL_FIXTURE_PATH.read_text(encoding="utf-8"))
    customer_facing_strings = [
        *(clinic["display_name_en_us"] for clinic in raw["clinics"]),
        *(staff["display_label"] for staff in raw["staff_accounts"]),
        *(patient["display_label"] for patient in raw["patient_scenarios"]),
        *(
            document.get("title_en_us") or document["title_es_mx"]
            for patient in raw["patient_scenarios"]
            for document in patient["documents_metadata_only"]
        ),
        *(
            event.get("summary_en_us") or event.get("summary_es_mx")
            for patient in raw["patient_scenarios"]
            for event in patient["timeline_events"]
        ),
    ]

    prohibited_placeholders = ("demo patient", "provider one", "synthetic scenario")
    assert all(
        placeholder not in value.casefold()
        for value in customer_facing_strings
        for placeholder in prohibited_placeholders
    )
    assert [patient["display_label"] for patient in raw["patient_scenarios"]] == [
        "Maya Patel",
        "José Ramírez",
        "Avery Chen",
        "Rafael Torres",
        "Hannah Brooks",
        "Daniel Kim",
        "Lucía Morales",
        "Evelyn Wright",
    ]
