"""Regression tests for deterministic demo-environment content."""

from app.db.seed.demo_data import CLINICS, DEMO_EMAIL_DOMAIN, PEOPLE, people_by_role


def test_demo_environment_has_two_clinics_and_bilingual_patients() -> None:
    assert len(CLINICS) == 2
    patients = people_by_role("patient")
    assert {patient.language for patient in patients} == {"en-US", "es-MX"}


def test_demo_account_addresses_use_only_the_reserved_demo_domain() -> None:
    assert PEOPLE
    assert all(person.email.endswith(f"@{DEMO_EMAIL_DOMAIN}") for person in PEOPLE)
