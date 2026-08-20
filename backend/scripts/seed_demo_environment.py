"""Provision or reset the deterministic synthetic demonstration environment."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable
from typing import Any

from app.db.seed.demo_data import CLINICS, DEMO_CLINIC_CODES, DEMO_EMAIL_DOMAIN, PEOPLE, DemoPerson

DEMO_PASSWORD_ENV = "DEMO_ACCOUNT_PASSWORD"
SAFE_ENVIRONMENTS = {"development", "demo", "staging"}


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


def _ensure_auth_user(client: Any, person: DemoPerson, password: str) -> str:
    profile_table = "patients" if person.role == "patient" else "clinicians"
    existing = _find_one(client, profile_table, {"email": person.email})
    if existing:
        return str(existing["id"])

    response = client.auth.admin.create_user(
        {
            "email": person.email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"demo": True, "role": person.role},
        }
    )
    user = getattr(response, "user", None)
    user_id = getattr(user, "id", None)
    if not user_id:
        raise RuntimeError(f"Could not create demo auth user for {person.email}")
    return str(user_id)


def _ensure_clinics(client: Any) -> dict[str, str]:
    clinic_ids: dict[str, str] = {}
    for clinic in CLINICS:
        row = _ensure_row(
            client,
            "clinics",
            {"code": clinic.code},
            {
                "code": clinic.code,
                "display_name": clinic.display_name,
                "canonical_name": clinic.canonical_name,
                "type2_npi": clinic.type2_npi,
                "status": "active",
            },
        )
        clinic_ids[clinic.code] = str(row["id"])
    return clinic_ids


def _ensure_people(client: Any, password: str, clinic_ids: dict[str, str]) -> dict[str, str]:
    person_ids: dict[str, str] = {}
    for person in PEOPLE:
        person_id = _ensure_auth_user(client, person, password)
        person_ids[person.key] = person_id
        clinic = next(clinic for clinic in CLINICS if clinic.code == person.clinic_code)
        if person.role == "patient":
            _ensure_row(
                client,
                "patients",
                {"email": person.email},
                {
                    "id": person_id,
                    "email": person.email,
                    "first_name": person.first_name,
                    "last_name": person.last_name,
                    "date_of_birth": person.date_of_birth,
                    "preferred_language": person.language,
                    "timezone": person.timezone,
                    "gender": "prefer_not_to_say",
                },
            )
            continue
        _ensure_row(
            client,
            "clinicians",
            {"email": person.email},
            {
                "id": person_id,
                "email": person.email,
                "first_name": person.first_name,
                "last_name": person.last_name,
                "specialty": person.specialty,
                "clinic_name": clinic.display_name,
                "clinic_id": clinic_ids[person.clinic_code],
                "role": person.role,
            },
        )
    return person_ids


def _ensure_care_team(
    client: Any, patient_id: str, clinician_id: str, role: str, clinic_name: str
) -> str:
    row = _ensure_row(
        client,
        "care_teams",
        {"patient_id": patient_id, "clinician_id": clinician_id},
        {
            "patient_id": patient_id,
            "clinician_id": clinician_id,
            "role": role,
            "specialty_context": role.replace("_", " "),
            "clinic_name": clinic_name,
            "status": "active",
        },
    )
    return str(row["id"])


def _ensure_patient_timeline(
    client: Any,
    *,
    patient_id: str,
    uploaded_by: str,
    care_team_id: str,
    patient_key: str,
    language: str,
) -> None:
    prior_document = _ensure_row(
        client,
        "documents",
        {
            "patient_id": patient_id,
            "file_name": f"demo-{patient_key}-medication-reconciliation.pdf",
        },
        {
            "patient_id": patient_id,
            "uploaded_by": uploaded_by,
            "uploaded_by_role": "clinician",
            "document_type": "prescription",
            "file_name": f"demo-{patient_key}-medication-reconciliation.pdf",
            "file_url": f"demo/{patient_key}/medication-reconciliation.pdf",
            "file_size_bytes": 1536,
            "parsed": True,
            "ai_summary": "Synthetic prior medication reconciliation for demonstration only.",
            "source_clinic": "Synthetic demonstration environment",
            "notes": f"demo:{patient_key}:prior-document",
        },
    )
    document = _ensure_row(
        client,
        "documents",
        {"patient_id": patient_id, "file_name": f"demo-{patient_key}-care-summary.pdf"},
        {
            "patient_id": patient_id,
            "uploaded_by": uploaded_by,
            "uploaded_by_role": "clinician",
            "document_type": "discharge_summary",
            "file_name": f"demo-{patient_key}-care-summary.pdf",
            "file_url": f"demo/{patient_key}/care-summary.pdf",
            "file_size_bytes": 2048,
            "parsed": True,
            "ai_summary": "Synthetic longitudinal care summary for demonstration only.",
            "source_clinic": "Synthetic demonstration environment",
            "notes": f"demo:{patient_key}:document",
        },
    )
    medication = _ensure_row(
        client,
        "medications",
        {"patient_id": patient_id, "name": "Metformin"},
        {
            "patient_id": patient_id,
            "name": "Metformin",
            "generic_name": "metformin",
            "rxcui": "6809",
            "dosage": "500 mg",
            "frequency": "twice daily",
            "route": "oral",
            "prescribed_by_care_team_id": care_team_id,
            "start_date": "2025-11-01",
            "instructions": "Take with food.",
            "source_document_id": document["id"],
            "is_active": True,
        },
    )
    _ensure_row(
        client,
        "medications",
        {"patient_id": patient_id, "name": "Lisinopril", "dosage": "20 mg"},
        {
            "patient_id": patient_id,
            "name": "Lisinopril",
            "generic_name": "lisinopril",
            "rxcui": "29046",
            "dosage": "20 mg",
            "frequency": "once daily",
            "route": "oral",
            "prescribed_by_care_team_id": care_team_id,
            "start_date": "2025-10-01",
            "end_date": "2026-08-15",
            "instructions": "Historical synthetic dose before reconciliation.",
            "source_document_id": prior_document["id"],
            "is_active": False,
        },
    )
    changed_medication = _ensure_row(
        client,
        "medications",
        {"patient_id": patient_id, "name": "Lisinopril", "dosage": "10 mg"},
        {
            "patient_id": patient_id,
            "name": "Lisinopril",
            "generic_name": "lisinopril",
            "rxcui": "29046",
            "dosage": "10 mg",
            "frequency": "once daily",
            "route": "oral",
            "prescribed_by_care_team_id": care_team_id,
            "start_date": "2026-08-16",
            "instructions": "Synthetic dose change awaiting clinician review in the demonstration.",
            "source_document_id": document["id"],
            "is_active": True,
        },
    )
    _ensure_row(
        client,
        "conditions",
        {"patient_id": patient_id, "name": "Type 2 diabetes mellitus"},
        {"patient_id": patient_id, "name": "Type 2 diabetes mellitus", "icd10_code": "E11.9"},
    )
    _ensure_row(
        client,
        "conditions",
        {"patient_id": patient_id, "name": "Essential hypertension"},
        {"patient_id": patient_id, "name": "Essential hypertension", "icd10_code": "I10"},
    )
    _ensure_row(
        client,
        "allergies",
        {"patient_id": patient_id, "allergen": "Penicillin"},
        {
            "patient_id": patient_id,
            "allergen": "Penicillin",
            "reaction": "Rash",
            "severity": "moderate",
        },
    )
    obligation = _ensure_row(
        client,
        "obligations",
        {"patient_id": patient_id, "description": "Walk for 20 minutes"},
        {
            "patient_id": patient_id,
            "obligation_type": "exercise",
            "description": "Walk for 20 minutes",
            "frequency": "daily",
            "set_by_care_team_id": care_team_id,
            "source_document_id": document["id"],
            "notes": f"demo:{patient_key}:obligation",
            "is_active": True,
        },
    )
    _ensure_row(
        client,
        "adherence_logs",
        {"patient_id": patient_id, "notes": f"demo:{patient_key}:metformin-adherence"},
        {
            "patient_id": patient_id,
            "target_type": "medication",
            "target_id": medication["id"],
            "status": "taken",
            "scheduled_time": "2026-08-18T08:00:00-07:00",
            "notes": f"demo:{patient_key}:metformin-adherence",
            "logged_at": "2026-08-18T08:05:00-07:00",
        },
    )
    _ensure_row(
        client,
        "adherence_logs",
        {"patient_id": patient_id, "notes": f"demo:{patient_key}:walk-adherence"},
        {
            "patient_id": patient_id,
            "target_type": "obligation",
            "target_id": obligation["id"],
            "status": "completed",
            "scheduled_time": "2026-08-18T17:00:00-07:00",
            "notes": f"demo:{patient_key}:walk-adherence",
            "logged_at": "2026-08-18T17:22:00-07:00",
        },
    )
    _ensure_row(
        client,
        "symptom_reports",
        {"patient_id": patient_id, "notes": f"demo:{patient_key}:symptom"},
        {
            "patient_id": patient_id,
            "symptom": "Dizziness after a medication change",
            "severity": 5,
            "onset": "2026-08-16",
            "duration": "two days",
            "related_medication_id": changed_medication["id"],
            "related_medication_name": "Lisinopril",
            "flagged_for_adr": False,
            "notes": f"demo:{patient_key}:symptom",
        },
    )
    _ensure_row(
        client,
        "appointments",
        {"patient_id": patient_id, "reason": f"demo:{patient_key}:follow-up"},
        {
            "patient_id": patient_id,
            "care_team_id": care_team_id,
            "clinician_name": "Synthetic care team",
            "scheduled_at": "2026-09-01T10:00:00-07:00",
            "appointment_type": "follow_up",
            "location": "Demo clinic",
            "reason": f"demo:{patient_key}:follow-up",
            "status": "scheduled",
        },
    )
    _ensure_row(
        client,
        "notifications",
        {"patient_id": patient_id, "dedupe_key": f"demo:{patient_key}:follow-up"},
        {
            "patient_id": patient_id,
            "notification_type": "appointment",
            "title": "Synthetic follow-up appointment",
            "body": "This is synthetic demonstration data.",
            "dedupe_key": f"demo:{patient_key}:follow-up",
            "metadata": {"language": language, "synthetic": True},
        },
    )


def seed(client: Any, password: str) -> None:
    clinic_ids = _ensure_clinics(client)
    person_ids = _ensure_people(client, password, clinic_ids)
    assignments = (
        ("patient-en", "north-clinician", "primary_care"),
        ("patient-es", "south-clinician", "primary_care"),
    )
    people = {person.key: person for person in PEOPLE}
    for patient_key, clinician_key, role in assignments:
        patient = people[patient_key]
        clinician = people[clinician_key]
        care_team_id = _ensure_care_team(
            client,
            person_ids[patient_key],
            person_ids[clinician_key],
            role,
            next(clinic.display_name for clinic in CLINICS if clinic.code == clinician.clinic_code),
        )
        _ensure_patient_timeline(
            client,
            patient_id=person_ids[patient_key],
            uploaded_by=person_ids[clinician_key],
            care_team_id=care_team_id,
            patient_key=patient_key,
            language=str(patient.language),
        )


def reset(client: Any) -> None:
    environment = os.environ.get("ENVIRONMENT", "development").lower()
    if environment not in SAFE_ENVIRONMENTS:
        raise RuntimeError("Demo reset is refused outside development, demo, or staging.")
    for table in ("patients", "clinicians"):
        rows = _rows(
            client.table(table)
            .select("id, email")
            .ilike("email", f"%@{DEMO_EMAIL_DOMAIN}")
            .execute()
        )
        for row in rows:
            client.auth.admin.delete_user(str(row["id"]))
    client.table("clinics").delete().in_("code", list(DEMO_CLINIC_CODES)).execute()


def _parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Remove only reserved demo accounts and clinics before seeding.",
    )
    parser.add_argument("--confirm-demo-reset", action="store_true", help="Required with --reset.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the plan without contacting Supabase."
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.reset and not args.confirm_demo_reset:
        raise SystemExit("--reset requires --confirm-demo-reset")
    if args.dry_run:
        print(f"Would provision {len(CLINICS)} clinics and {len(PEOPLE)} synthetic accounts.")
        return 0
    password = os.environ.get(DEMO_PASSWORD_ENV)
    if not password:
        raise SystemExit(f"Set {DEMO_PASSWORD_ENV}; never commit a demo password.")
    from app.clients.supabase import create_admin_client

    client = create_admin_client()
    if args.reset:
        reset(client)
    seed(client, password)
    print("Synthetic demo environment is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
