"""Guard the R2 reconciliation migration's least-privilege contract."""

from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "app"
    / "db"
    / "migrations"
    / "029_safe_external_record_reconciliation.sql"
)


def test_reconciliation_is_atomic_append_only_and_service_role_only() -> None:
    migration = MIGRATION_PATH.read_text()

    assert "CREATE TABLE IF NOT EXISTS external_patient_bindings" in migration
    assert "UNIQUE (issuer, external_patient_id)" in migration
    assert "CREATE TABLE IF NOT EXISTS clinical_fact_reconciliation_events" in migration
    assert "clinical_fact_reconciliation_events are append-only" in migration
    assert "FOR UPDATE" in migration
    assert "reconciled clinical facts are immutable evidence" in migration
    assert "patch fields must be explicitly selected" in migration
    assert "coalesce(nullif(btrim(p_patch->>'name'), ''), m.name)" in migration
    assert "apply_clinical_fact_reconciliation" in migration
    assert "REVOKE ALL ON FUNCTION" in migration
    assert "GRANT EXECUTE ON FUNCTION" in migration
    assert "TO service_role" in migration
    assert "FROM PUBLIC, anon, authenticated" in migration
    assert "withdraw_unapplied_document_source" in migration
    assert "withdraw_unapplied_fhir_import" in migration
    assert "withdrawn_at" in migration
    assert "v_retained_ids" in migration
    assert "source_withdrawn" in migration


def test_reconciliation_never_projects_evidence_only_types_or_demographics() -> None:
    migration = MIGRATION_PATH.read_text()

    assert "v_fact.fact_type NOT IN ('medication', 'condition', 'allergy')" in migration
    assert "patient_demographics" not in migration
    assert "new medications require name, dosage, and frequency" in migration
    assert "'unknown'::public.allergy_severity_enum" in migration
