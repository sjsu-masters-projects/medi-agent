"""Provision the canonical synthetic California portal fixture.

The adapter stores only fields represented by existing production tables. It does
not turn declared preferences, proxy access, accessibility metadata, or external
notification delivery into invented database state.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.db.seed.demo_data import (
    DEMO_EMAIL_DOMAIN,
    CanonicalDemoFixture,
    DemoDocument,
    DemoMedication,
    DemoPatientScenario,
    load_canonical_fixture,
)

DEMO_PASSWORD_ENV = "DEMO_ACCOUNT_PASSWORD"
SAFE_ENVIRONMENTS = {"development", "demo", "staging"}
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "src/app/db/migrations"
REQUIRED_TABLES = (
    "patients",
    "clinicians",
    "care_teams",
    "documents",
    "medications",
    "conditions",
    "allergies",
    "appointments",
    "chat_messages",
    "notifications",
)
DATE_OF_BIRTH_PLACEHOLDERS = {
    "19-24": "2004-01-01",
    "25-34": "1996-01-01",
    "35-44": "1986-01-01",
    "45-54": "1976-01-01",
    "55-64": "1966-01-01",
    "65-74": "1956-01-01",
    "75-84": "1946-01-01",
    "85+": "1936-01-01",
}
ROUTE_MAP = {"oral": "oral", "topical": "topical", "inhalation": "inhaled", "nasal": "other"}
DOCUMENT_TYPE_MAP = {
    "lab_report_metadata": "lab_report",
    "imaging_report_metadata": "diagnostic_report",
    "visit_summary": "other",
    "medication_list": "other",
    "service_request_metadata": "other",
    "correspondence": "other",
}
STAFF_ROLE_MAP = {
    "physician": "provider",
    "nurse_practitioner": "provider",
    "physician_assistant": "provider",
    "registered_nurse": "nurse",
    "front_desk_admin": "admin",
    "records_admin": "admin",
}
DOSE_FREQUENCY = re.compile(r"^.+? ((?:once|twice) daily|once weekly)$")
# Reviewed, source-ID based decision: only these five fixed events explicitly say
# "Portal message" in the canonical fixture. Other concern transports are not
# represented by the current chat table and must remain unpersisted.
PORTAL_CONCERN_EVENT_IDS = frozenset(
    {
        "SYN-EVT-001-05",
        "SYN-EVT-003-07",
        "SYN-EVT-005-03",
        "SYN-EVT-006-06",
        "SYN-EVT-007-04",
    }
)


def _rows(result: Any) -> list[dict[str, Any]]:
    data = getattr(result, "data", None) or []
    return [row for row in data if isinstance(row, dict)]


def _find_one(client: Any, table: str, filters: dict[str, str]) -> dict[str, Any] | None:
    query = client.table(table).select("*")
    for column, value in filters.items():
        query = query.eq(column, value)
    rows = _rows(query.limit(1).execute())
    return rows[0] if rows else None


def _ensure_row(
    client: Any, table: str, filters: dict[str, str], payload: dict[str, Any]
) -> dict[str, Any]:
    existing = _find_one(client, table, filters)
    if existing:
        client.table(table).update(payload).eq("id", existing["id"]).execute()
        return {**existing, **payload}
    rows = _rows(client.table(table).insert(payload).execute())
    if not rows:
        raise RuntimeError(f"Could not create demo {table} row")
    return rows[0]


def _expected_migration_checksums() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(MIGRATIONS_DIR.glob("*.sql"))
    }


def assert_schema_ready(client: Any) -> None:
    """Refuse mutation until the database has the exact committed migration ledger."""
    expected = _expected_migration_checksums()
    applied = {
        str(row["filename"]): str(row["checksum"])
        for row in _rows(client.table("schema_migrations").select("filename, checksum").execute())
    }
    missing_or_changed = sorted(
        filename for filename, checksum in expected.items() if applied.get(filename) != checksum
    )
    if missing_or_changed:
        raise RuntimeError(
            "Demo seed requires a synchronized migration ledger; run "
            "scripts/apply-supabase-migrations.sh first. "
            f"Missing or changed: {', '.join(missing_or_changed)}"
        )
    for table in REQUIRED_TABLES:
        client.table(table).select("id").limit(1).execute()


def fixture_email(source_id: str) -> str:
    """Create a non-clinical Auth identifier from the canonical synthetic ID."""
    return f"{source_id.lower()}@{DEMO_EMAIL_DOMAIN}"


def clinic_code(source_id: str) -> str:
    return f"DEMO-CA-{source_id}"


def _label_parts(display_label: str) -> tuple[str, str]:
    parts = display_label.split(maxsplit=1)
    return (parts[0], parts[1] if len(parts) > 1 else "(synthetic)")


def _staff_specialty(source_role: str) -> str:
    return source_role.replace("_", " ")


def _ensure_auth_user(client: Any, *, email: str, profile_table: str, password: str) -> str:
    existing = _find_one(client, profile_table, {"email": email})
    if existing:
        return str(existing["id"])
    response = client.auth.admin.create_user(
        {
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"demo": True, "synthetic": True},
        }
    )
    user_id = getattr(getattr(response, "user", None), "id", None)
    if not user_id:
        raise RuntimeError(f"Could not create synthetic auth user for {email}")
    return str(user_id)


def _ensure_clinics(client: Any, fixture: CanonicalDemoFixture) -> dict[str, str]:
    clinic_ids: dict[str, str] = {}
    for clinic in fixture.clinics:
        row = _ensure_row(
            client,
            "clinics",
            {"code": clinic_code(clinic.source_id)},
            {
                "code": clinic_code(clinic.source_id),
                "display_name": clinic.display_name,
                "canonical_name": clinic.display_name.lower(),
                "status": "active",
            },
        )
        clinic_ids[clinic.source_id] = str(row["id"])
    return clinic_ids


def _ensure_staff(
    client: Any, fixture: CanonicalDemoFixture, password: str, clinic_ids: dict[str, str]
) -> dict[str, str]:
    staff_ids: dict[str, str] = {}
    for staff in fixture.staff:
        email = fixture_email(staff.source_id)
        staff_id = _ensure_auth_user(
            client, email=email, profile_table="clinicians", password=password
        )
        first_name, last_name = _label_parts(staff.display_label)
        clinic = next(item for item in fixture.clinics if item.source_id == staff.clinic_source_id)
        _ensure_row(
            client,
            "clinicians",
            {"email": email},
            {
                "id": staff_id,
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "specialty": _staff_specialty(staff.source_role),
                "clinic_name": clinic.display_name,
                "clinic_id": clinic_ids[staff.clinic_source_id],
                "role": STAFF_ROLE_MAP[staff.source_role],
            },
        )
        staff_ids[staff.source_id] = staff_id
    return staff_ids


def _ensure_patients(client: Any, fixture: CanonicalDemoFixture, password: str) -> dict[str, str]:
    patient_ids: dict[str, str] = {}
    for patient in fixture.patients:
        email = fixture_email(patient.source_id)
        patient_id = _ensure_auth_user(
            client, email=email, profile_table="patients", password=password
        )
        first_name, last_name = _label_parts(patient.display_label)
        _ensure_row(
            client,
            "patients",
            {"email": email},
            {
                "id": patient_id,
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "date_of_birth": DATE_OF_BIRTH_PLACEHOLDERS[patient.age_band],
                "gender": None,
                "preferred_language": patient.preferred_language,
                "timezone": "America/Los_Angeles",
            },
        )
        patient_ids[patient.source_id] = patient_id
    return patient_ids


def _ensure_care_teams(
    client: Any,
    fixture: CanonicalDemoFixture,
    patient_ids: dict[str, str],
    staff_ids: dict[str, str],
) -> dict[tuple[str, str], str]:
    care_team_ids: dict[tuple[str, str], str] = {}
    clinic_names = {clinic.source_id: clinic.display_name for clinic in fixture.clinics}
    for assignment in fixture.care_team_assignments:
        if not assignment.grants_record_access or assignment.staff_source_id not in staff_ids:
            continue
        row = _ensure_row(
            client,
            "care_teams",
            {
                "patient_id": patient_ids[assignment.patient_source_id],
                "clinician_id": staff_ids[assignment.staff_source_id],
            },
            {
                "patient_id": patient_ids[assignment.patient_source_id],
                "clinician_id": staff_ids[assignment.staff_source_id],
                "role": assignment.role,
                "specialty_context": assignment.role.replace("_", " "),
                "clinic_name": clinic_names[assignment.clinic_source_id],
                "status": "active",
                "created_at": f"{assignment.effective_start}T00:00:00-08:00",
            },
        )
        care_team_ids[(assignment.patient_source_id, assignment.staff_source_id)] = str(row["id"])
    return care_team_ids


def _medication_payload(medication: DemoMedication) -> dict[str, Any]:
    frequency_match = DOSE_FREQUENCY.match(medication.dose_text)
    frequency = frequency_match.group(1) if frequency_match else "as recorded"
    return {
        "name": medication.label,
        "generic_name": medication.label,
        "dosage": medication.dose_text,
        "frequency": frequency,
        "route": ROUTE_MAP[medication.route],
        "start_date": medication.start_date,
        "end_date": medication.end_date,
        "is_active": medication.status == "active",
    }


def _document_payload(document: DemoDocument, patient_id: str, clinician_id: str) -> dict[str, Any]:
    return {
        "patient_id": patient_id,
        "uploaded_by": clinician_id,
        "uploaded_by_role": "clinician",
        "document_type": DOCUMENT_TYPE_MAP[document.document_type],
        "file_name": f"{document.source_id}.pdf",
        "file_url": f"demo/{patient_id}/{document.source_id}.pdf",
        "mime_type": document.mime_type,
        "file_size_bytes": 0,
        "parsed": False,
        "ai_summary": document.title,
        "visibility": "all_providers",
        "created_at": document.created_at,
    }


def _ensure_patient_content(
    client: Any,
    patient: DemoPatientScenario,
    patient_id: str,
    clinician_id: str,
    care_team_id: str,
) -> None:
    for condition in patient.conditions:
        _ensure_row(
            client,
            "conditions",
            {"patient_id": patient_id, "name": condition.label},
            {"patient_id": patient_id, "name": condition.label, "status": condition.status},
        )
    for allergy in patient.allergies:
        _ensure_row(
            client,
            "allergies",
            {"patient_id": patient_id, "allergen": allergy.substance},
            {
                "patient_id": patient_id,
                "allergen": allergy.substance,
                "reaction": allergy.reaction,
                "severity": allergy.severity,
            },
        )
    for medication in patient.medications:
        payload = {"patient_id": patient_id, **_medication_payload(medication)}
        _ensure_row(
            client,
            "medications",
            {
                "patient_id": patient_id,
                "name": medication.label,
                "dosage": medication.dose_text,
                "start_date": medication.start_date,
            },
            payload,
        )
    for document in patient.documents:
        payload = _document_payload(document, patient_id, clinician_id)
        _ensure_row(
            client,
            "documents",
            {"patient_id": patient_id, "file_name": payload["file_name"]},
            payload,
        )
    for event in patient.timeline_events:
        if event.source_id in PORTAL_CONCERN_EVENT_IDS:
            _ensure_row(
                client,
                "chat_messages",
                {"patient_id": patient_id, "content": event.summary},
                {
                    "patient_id": patient_id,
                    "content": event.summary,
                    "role": "user",
                    "intent": "patient_reported_concern",
                    "language": patient.preferred_language,
                    "created_at": event.timestamp,
                },
            )
        elif event.event_type == "appointment_scheduled":
            _ensure_row(
                client,
                "appointments",
                {"patient_id": patient_id, "reason": event.summary},
                {
                    "patient_id": patient_id,
                    "care_team_id": care_team_id,
                    "clinician_name": patient.assigned_provider_source_id,
                    "scheduled_at": event.timestamp,
                    "appointment_type": "follow_up",
                    "reason": event.summary,
                    "status": "scheduled",
                    "created_at": event.timestamp,
                },
            )
        elif event.event_type == "notification_sent" and event.channel == "portal_message":
            _ensure_row(
                client,
                "notifications",
                {"patient_id": patient_id, "body": event.summary},
                {
                    "patient_id": patient_id,
                    "notification_type": "appointment",
                    "title": "Synthetic portal notification",
                    "body": event.summary,
                    "created_at": event.timestamp,
                },
            )


def seed(client: Any, password: str) -> None:
    fixture = load_canonical_fixture()
    clinic_ids = _ensure_clinics(client, fixture)
    staff_ids = _ensure_staff(client, fixture, password, clinic_ids)
    patient_ids = _ensure_patients(client, fixture, password)
    care_team_ids = _ensure_care_teams(client, fixture, patient_ids, staff_ids)
    for patient in fixture.patients:
        care_team_id = care_team_ids[(patient.source_id, patient.assigned_provider_source_id)]
        _ensure_patient_content(
            client,
            patient,
            patient_ids[patient.source_id],
            staff_ids[patient.assigned_provider_source_id],
            care_team_id,
        )


def _reserved_demo_user_ids(client: Any, fixture: CanonicalDemoFixture) -> list[str]:
    expected_emails = {fixture_email(staff.source_id) for staff in fixture.staff}
    expected_emails.update(fixture_email(patient.source_id) for patient in fixture.patients)
    user_ids: list[str] = []
    page = 1
    while True:
        users = client.auth.admin.list_users(page=page, per_page=100)
        if not users:
            break
        for user in users:
            if str(getattr(user, "email", "")).lower() in expected_emails:
                user_ids.append(str(user.id))
        if len(users) < 100:
            break
        page += 1
    return sorted(set(user_ids))


def reset(client: Any) -> None:
    environment = os.environ.get("ENVIRONMENT", "development").lower()
    if environment not in SAFE_ENVIRONMENTS:
        raise RuntimeError("Demo reset is refused outside development, demo, or staging.")
    fixture = load_canonical_fixture()
    for user_id in _reserved_demo_user_ids(client, fixture):
        client.auth.admin.delete_user(user_id)
    client.table("clinics").delete().in_(
        "code", [clinic_code(clinic.source_id) for clinic in fixture.clinics]
    ).execute()


def _parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--confirm-demo-reset", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.reset and not args.confirm_demo_reset:
        raise SystemExit("--reset requires --confirm-demo-reset")
    fixture = load_canonical_fixture()
    if args.dry_run:
        print(
            f"Would provision {len(fixture.clinics)} clinics, {len(fixture.staff) + len(fixture.patients)} "
            f"synthetic accounts, and {len(fixture.patients)} patient scenarios."
        )
        return 0
    password = os.environ.get(DEMO_PASSWORD_ENV)
    if not password:
        raise SystemExit(f"Set {DEMO_PASSWORD_ENV}; never commit a demo password.")
    from app.clients.supabase import create_admin_client

    client = create_admin_client()
    assert_schema_ready(client)
    if args.reset:
        reset(client)
    seed(client, password)
    print("Canonical synthetic demo environment is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
