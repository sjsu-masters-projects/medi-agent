"""Text-level guarantees for confirmed symptom ADR handoff migration 076."""

from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "src/app/db/migrations"
MIGRATION = (MIGRATIONS / "076_confirmed_symptom_adr_handoff.sql").read_text()
CODE = "\n".join(line.split("--", 1)[0] for line in MIGRATION.splitlines())


def test_it_follows_confirmed_intake_without_editing_applied_migration() -> None:
    assert [path.name for path in MIGRATIONS.glob("076_*.sql")] == [
        "076_confirmed_symptom_adr_handoff.sql"
    ]
    assert (MIGRATIONS / "060_confirmed_symptom_intake.sql").exists()
    assert "CREATE OR REPLACE FUNCTION private.symptom_context" in MIGRATION
    assert "lower(btrim(name))=lower(btrim(" in MIGRATION


def test_confirmation_enqueues_one_canonical_report_keyed_task() -> None:
    assert "CREATE TRIGGER confirmed_symptom_adr_outbox" in MIGRATION
    assert "AFTER INSERT ON public.symptom_reports" in MIGRATION
    assert "NEW.confirmation_state='patient_confirmed'" in MIGRATION
    assert "product->>'state'='answered'" in MIGRATION
    assert "product->'value'->'concern'='true'::jsonb" in MIGRATION
    assert "jsonb_array_length(medications)>0" in MIGRATION
    assert "'symptom_event:' || NEW.id::text" in MIGRATION
    assert "'symptom','pharmacovigilance','symptom_adr_screen','submitted'" in MIGRATION
    assert "'symptom_report',jsonb_build_object('id',NEW.id)" in MIGRATION
    assert "ON CONFLICT(patient_id,idempotency_key) DO NOTHING" in MIGRATION


def test_trigger_is_private_and_does_not_make_a_clinical_decision() -> None:
    assert "REVOKE ALL ON FUNCTION private.enqueue_confirmed_symptom_adr_task()" in MIGRATION
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
