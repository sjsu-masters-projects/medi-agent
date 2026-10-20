"""Text-level guarantees for the applied confirmed symptom ADR handoff migration."""

import hashlib
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "src/app/db/migrations"
MIGRATION_PATH = MIGRATIONS / "071_confirmed_symptom_handoff.sql"
MIGRATION = MIGRATION_PATH.read_text()
CODE = "\n".join(line.split("--", 1)[0] for line in MIGRATION.splitlines())
EXPECTED_SHA256 = "f690b788d5f29c3d7583f2fe8cc43b7a51a6af817c276d6839cc9c9ab2ded36b"


def test_it_follows_confirmed_intake_without_editing_applied_migration() -> None:
    assert (MIGRATIONS / "060_confirmed_symptom_intake.sql").exists()
    assert (MIGRATIONS / "071_clinician_visit_management.sql").exists()
    assert MIGRATION_PATH.exists()
    assert hashlib.sha256(MIGRATION_PATH.read_bytes()).hexdigest() == EXPECTED_SHA256
    assert "CREATE OR REPLACE FUNCTION private.symptom_context" in MIGRATION
    assert "lower(btrim(name))=lower(btrim(" in MIGRATION


def test_confirmation_enqueues_one_canonical_report_keyed_task() -> None:
    assert "CREATE FUNCTION private.map_confirmed_symptom_product()" in MIGRATION
    assert "CREATE FUNCTION private.enqueue_confirmed_symptom_review()" in MIGRATION
    assert "CREATE TRIGGER symptom_intake_confirmed_handoff" in MIGRATION
    assert "AFTER UPDATE OF status ON public.symptom_intakes" in MIGRATION
    assert "'confirmed_symptom:'||report.id::text" in MIGRATION
    assert "'symptom','pharmacovigilance','symptom_adr_screen','retrying'" in MIGRATION
    assert "'symptom_report',jsonb_build_object('id',report.id)" in MIGRATION
    assert "ON CONFLICT(patient_id,idempotency_key) DO NOTHING" in MIGRATION


def test_trigger_is_private_and_does_not_make_a_clinical_decision() -> None:
    assert (
        "REVOKE ALL ON FUNCTION private.map_confirmed_symptom_product(),private.enqueue_confirmed_symptom_review()"
        in MIGRATION
    )
    assert "report.confirmed_content-'context'" in MIGRATION
    assert "'naranjo_answers','{}'::jsonb,'adr_evidence','[]'::jsonb" in MIGRATION
    lowered = CODE.lower()
    for forbidden in (
        "insert into public.adr_assessments",
        "insert into public.medwatch_drafts",
        "naranjo_score",
        "causality",
        "delete from",
        "truncate ",
    ):
        assert forbidden not in lowered
