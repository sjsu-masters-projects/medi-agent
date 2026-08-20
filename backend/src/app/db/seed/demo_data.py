"""Deterministic, synthetic content for the local and demonstration environment."""

from __future__ import annotations

from dataclasses import dataclass

DEMO_EMAIL_DOMAIN = "demo.mediagent.local"
DEMO_CLINIC_CODES = ("DEMO-CA-NORTH", "DEMO-CA-SOUTH")


@dataclass(frozen=True)
class DemoClinic:
    code: str
    display_name: str
    canonical_name: str
    type2_npi: str


@dataclass(frozen=True)
class DemoPerson:
    key: str
    email: str
    first_name: str
    last_name: str
    role: str
    clinic_code: str
    specialty: str | None = None
    language: str | None = None
    date_of_birth: str | None = None
    timezone: str | None = None


CLINICS = (
    DemoClinic(
        code="DEMO-CA-NORTH",
        display_name="North Valley Chronic Care",
        canonical_name="north valley chronic care",
        type2_npi="9000000001",
    ),
    DemoClinic(
        code="DEMO-CA-SOUTH",
        display_name="South Bay Care Collaborative",
        canonical_name="south bay care collaborative",
        type2_npi="9000000002",
    ),
)

PEOPLE = (
    DemoPerson(
        key="north-clinician",
        email=f"dr.avery@{DEMO_EMAIL_DOMAIN}",
        first_name="Avery",
        last_name="Morgan",
        role="provider",
        clinic_code="DEMO-CA-NORTH",
        specialty="Family Medicine",
    ),
    DemoPerson(
        key="north-nurse",
        email=f"nurse.taylor@{DEMO_EMAIL_DOMAIN}",
        first_name="Taylor",
        last_name="Reed",
        role="nurse",
        clinic_code="DEMO-CA-NORTH",
        specialty="Chronic Care Nursing",
    ),
    DemoPerson(
        key="south-clinician",
        email=f"dr.rivera@{DEMO_EMAIL_DOMAIN}",
        first_name="Lucia",
        last_name="Rivera",
        role="provider",
        clinic_code="DEMO-CA-SOUTH",
        specialty="Internal Medicine",
    ),
    DemoPerson(
        key="south-admin",
        email=f"staff.chen@{DEMO_EMAIL_DOMAIN}",
        first_name="Morgan",
        last_name="Chen",
        role="admin",
        clinic_code="DEMO-CA-SOUTH",
        specialty="Clinic Operations",
    ),
    DemoPerson(
        key="patient-en",
        email=f"maria.garcia@{DEMO_EMAIL_DOMAIN}",
        first_name="Maria",
        last_name="Garcia",
        role="patient",
        clinic_code="DEMO-CA-NORTH",
        language="en-US",
        date_of_birth="1958-09-14",
        timezone="America/Los_Angeles",
    ),
    DemoPerson(
        key="patient-es",
        email=f"jose.martinez@{DEMO_EMAIL_DOMAIN}",
        first_name="Jose",
        last_name="Martinez",
        role="patient",
        clinic_code="DEMO-CA-SOUTH",
        language="es-MX",
        date_of_birth="1962-04-21",
        timezone="America/Los_Angeles",
    ),
)


def people_by_role(role: str) -> tuple[DemoPerson, ...]:
    """Return deterministic people for one supported role."""
    return tuple(person for person in PEOPLE if person.role == role)


def clinic_for_code(code: str) -> DemoClinic:
    """Resolve a seeded clinic or raise a clear programming error."""
    for clinic in CLINICS:
        if clinic.code == code:
            return clinic
    raise ValueError(f"Unknown demo clinic code: {code}")
