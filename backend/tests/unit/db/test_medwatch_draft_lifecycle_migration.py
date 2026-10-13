"""Schema contracts for clinician-controlled MedWatch drafts."""

from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[3] / "src/app/db/migrations/048_medwatch_draft_lifecycle.sql"
).read_text()


def test_medwatch_mutations_are_assignment_scoped_atomic_rpcs() -> None:
    for function_name in (
        "create_medwatch_draft",
        "update_medwatch_draft",
        "approve_medwatch_draft",
        "record_medwatch_draft_export",
    ):
        assert f"FUNCTION public.{function_name}" in MIGRATION
    assert MIGRATION.count("FOR UPDATE") >= 4
    assert MIGRATION.count("Clinician is not assigned to this patient") >= 4


def test_medwatch_browser_access_is_read_only_and_rpc_is_service_role_only() -> None:
    assert "REVOKE ALL ON TABLE public.medwatch_drafts FROM anon, authenticated" in MIGRATION
    assert "GRANT SELECT ON TABLE public.medwatch_drafts TO authenticated" in MIGRATION
    assert "DROP POLICY IF EXISTS medwatch_clinician_update" in MIGRATION
    assert MIGRATION.count("FROM PUBLIC, anon, authenticated") >= 4
    assert MIGRATION.count("TO service_role") >= 6


def test_medwatch_lifecycle_is_audited_without_an_fda_submission_operation() -> None:
    assert "medwatch_draft_audit_events" in MIGRATION
    assert "('created', 'edited', 'approved', 'exported')" in MIGRATION
    assert "not FDA submissions" in MIGRATION
    assert "submit_medwatch" not in MIGRATION
    assert "status = 'reviewed'" in MIGRATION


def test_medwatch_draft_preserves_source_and_clinician_edit_attribution() -> None:
    assert "source_evidence jsonb" in MIGRATION
    assert "clinician_edited_fields jsonb" in MIGRATION
    assert "approved_by uuid" in MIGRATION
    assert "p_expected_revision" in MIGRATION
    assert "idx_medwatch_one_draft_per_assessment" in MIGRATION
