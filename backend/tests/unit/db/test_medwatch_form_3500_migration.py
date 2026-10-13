"""Text-level guarantees of the Form 3500 migration (PV-001-C, migration 064)."""

import re
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "src/app/db/migrations"
MIGRATION = (MIGRATIONS / "064_medwatch_form_3500.sql").read_text()
CODE = "\n".join(line.split("--", 1)[0] for line in MIGRATION.splitlines())


def _function(signature_start: str) -> str:
    start = MIGRATION.index(f"CREATE OR REPLACE FUNCTION {signature_start}")
    return MIGRATION[start : MIGRATION.index("$$;", start)]


def _created(name: str) -> str:
    start = MIGRATION.index(f"CREATE FUNCTION {name}(")
    return MIGRATION[start : MIGRATION.index("$$;", start)]


def test_it_is_the_one_form_3500_migration_after_063() -> None:
    assert [p.name for p in MIGRATIONS.glob("064_*.sql")] == ["064_medwatch_form_3500.sql"]
    assert (MIGRATIONS / "063_adr_information_loop_lifecycle.sql").exists()
    assert "Requires 063." in MIGRATION.split("\n\n")[0]
    assert "applied to a hosted project only on explicit authorization" in MIGRATION


def test_step_1_discard_columns_reference_and_form_3500_labels() -> None:
    for column in ("discarded_at timestamptz", "discard_reason text", "patient_reference text"):
        assert f"ADD COLUMN {column}" in MIGRATION
    assert "discarded_by uuid REFERENCES public.clinicians(id) ON DELETE RESTRICT" in MIGRATION
    assert "char_length(btrim(discard_reason)) BETWEEN 1 AND 2000" in MIGRATION
    assert "num_nonnulls(discarded_at, discarded_by, discard_reason) IN (0, 3)" in MIGRATION
    assert "CHECK (discarded_at IS NULL OR status <> 'submitted')" in MIGRATION
    assert "patient_reference ~ '^[A-Z]{2}-[A-Z2-7]{4}$'" in MIGRATION
    assert "ALTER COLUMN export_version SET DEFAULT 'fda-3500-2025-09'" in MIGRATION
    assert re.search(
        r"SET export_version = 'fda-3500-legacy-048'\s+WHERE export_version = 'medwatch-3500a-draft-v1'",
        MIGRATION,
    )
    assert "COMMENT ON COLUMN public.medwatch_drafts.form_data" in MIGRATION
    assert "3500A" not in CODE
    body = _created("private.medwatch_drafts_export_version")
    assert "WHEN NEW.form_data->>'form_version' = 'fda-3500-2025-09'" in body


def test_step_2_one_non_discarded_draft_per_assessment() -> None:
    assert "DROP INDEX public.idx_medwatch_one_draft_per_assessment;" in MIGRATION
    assert re.search(
        r"CREATE UNIQUE INDEX idx_medwatch_one_draft_per_assessment\s+"
        r"ON public.medwatch_drafts\(adr_assessment_id\)\s+WHERE discarded_at IS NULL;",
        MIGRATION,
    )


def test_step_3_append_only_submission_table() -> None:
    table = MIGRATION.split("CREATE TABLE public.medwatch_external_submissions (")[1].split(");")[0]
    assert "CHECK (attested)" in table
    assert "CHECK (method <> 'other' OR method_detail IS NOT NULL)" in table
    assert "CHECK ((amends_id IS NULL) = (amend_reason IS NULL))" in table
    assert "method IN ('medwatch_online', 'fax', 'mail', 'other')" in table
    assert (
        "ON public.medwatch_external_submissions(medwatch_draft_id, created_at DESC)" in MIGRATION
    )
    assert "ALTER TABLE public.medwatch_external_submissions ENABLE ROW LEVEL SECURITY" in MIGRATION
    assert "private.is_assigned_clinician(patient_id)" in MIGRATION
    assert re.search(
        r"REVOKE ALL ON TABLE public.medwatch_external_submissions\s+"
        r"FROM PUBLIC, anon, authenticated, service_role;",
        MIGRATION,
    )
    assert (
        "GRANT SELECT ON TABLE public.medwatch_external_submissions TO authenticated, service_role;"
        in MIGRATION
    )
    assert "BEFORE UPDATE ON public.medwatch_external_submissions" in MIGRATION
    assert "BEFORE DELETE" not in CODE


def test_patient_references_cascade_and_clinician_references_restrict() -> None:
    table = MIGRATION.split("CREATE TABLE public.medwatch_external_submissions (")[1].split(");")[0]
    for reference in (
        "REFERENCES public.medwatch_drafts(id) ON DELETE CASCADE",
        "REFERENCES public.adr_assessments(id) ON DELETE CASCADE",
        "REFERENCES public.patients(id) ON DELETE CASCADE",
        "REFERENCES public.medwatch_external_submissions(id) ON DELETE CASCADE",
        "recorded_by uuid NOT NULL REFERENCES public.clinicians(id) ON DELETE RESTRICT",
    ):
        assert reference in table
    assert "ON DELETE SET NULL" not in CODE


def test_step_4_submitted_state_needs_approval_and_a_record() -> None:
    assert "DROP CONSTRAINT medwatch_drafts_not_submitted_by_app" in MIGRATION
    assert "CHECK ((status = 'submitted') = (submitted_at IS NOT NULL))" in MIGRATION
    guard = _created("private.medwatch_drafts_submission_guard")
    assert "OLD.status <> 'reviewed'" in guard
    assert "NEW.approved_at IS NULL" in guard
    assert "FROM public.medwatch_external_submissions s" in guard
    for column in ("form_data", "status", "revision", "discarded_at", "discard_reason"):
        assert f"NEW.{column} IS DISTINCT FROM OLD.{column}" in guard
    assert "BEFORE INSERT OR UPDATE ON public.medwatch_drafts" in MIGRATION


def test_step_5_audit_types_are_supersets_with_the_new_events() -> None:
    medwatch = MIGRATION.split("ADD CONSTRAINT medwatch_draft_audit_events_event_type_check")[1]
    medwatch = medwatch.split(";")[0]
    for kind in (
        "created",
        "edited",
        "approved",
        "exported",
        "discarded",
        "submission_recorded",
        "submission_amended",
    ):
        assert f"'{kind}'" in medwatch
    adr = MIGRATION.split("ADD CONSTRAINT adr_assessment_audit_events_event_type_check")[1]
    adr = adr.split(";")[0]
    for kind in (
        "marked_reviewed",
        "dismissed",
        "information_requested",
        "patient_information_provided",
        "medwatch_draft_discarded",
    ):
        assert f"'{kind}'" in adr


def test_step_6_rpcs_lock_check_assignment_and_revision() -> None:
    for start in (
        "public.create_medwatch_draft(\n  p_assessment_id uuid,",
        "public.approve_medwatch_draft(",
        "public.record_medwatch_draft_export(\n  p_draft_id uuid,\n  p_actor_id uuid,\n  p_format",
        "public.discard_medwatch_draft(",
        "public.record_medwatch_external_submission(",
        "public.amend_medwatch_external_submission(",
    ):
        body = _function(start)
        assert "SECURITY DEFINER" in body and "SET search_path = public" in body, start
        assert "FOR UPDATE" in body, start
        assert "AND status = 'active'" in body, start
        assert "USING ERRCODE = '42501'" in body, start
    for start in (
        "public.approve_medwatch_draft(",
        "public.discard_medwatch_draft(",
        "public.record_medwatch_external_submission(",
    ):
        body = _function(start)
        assert "v_draft.revision <> p_expected_revision" in body
        assert "USING ERRCODE = '40001'" in body
    create = _function("public.create_medwatch_draft(\n  p_assessment_id uuid,")
    assert "p_draft_id uuid\n) RETURNS SETOF public.medwatch_drafts" in create
    assert "v_reference text := p_form_data #>> '{section_a,identifier}'" in create
    approve = _function("public.approve_medwatch_draft(")
    assert "p_approval jsonb" in approve
    assert "'medwatch-3500-approval-v1'" in approve
    for key in ("attestation_version", "non_serious_attested", "acknowledged_warnings"):
        assert f"'{key}', p_approval" in approve
    assert "'America/Los_Angeles'" in approve
    submission = _function("public.record_medwatch_external_submission(")
    assert "p_submitted_on > v_today" in submission
    assert "p_submitted_on < (v_draft.approved_at AT TIME ZONE 'America/Los_Angeles')::date" in (
        submission
    )
    amend = _function("public.amend_medwatch_external_submission(")
    assert "v_current.id IS DISTINCT FROM p_amends_id" in amend
    assert "'submission_amended'" in amend


def test_the_two_argument_export_calls_the_five_argument_one() -> None:
    delegate = _function(
        "public.record_medwatch_draft_export(\n  p_draft_id uuid,\n  p_actor_id uuid\n)"
    )
    assert (
        "SELECT * FROM public.record_medwatch_draft_export(p_draft_id, p_actor_id, 'json', NULL, NULL);"
        in delegate
    )
    export = _function(
        "public.record_medwatch_draft_export(\n  p_draft_id uuid,\n  p_actor_id uuid,\n  p_format"
    )
    assert "v_draft.status NOT IN ('reviewed', 'submitted')" in export
    assert "v_draft.discarded_at IS NOT NULL" in export
    assert "'template_sha256', p_template_sha256" in export


def test_step_7_discard_returns_the_assessment_to_review_with_both_audit_rows() -> None:
    body = _function("public.discard_medwatch_draft(")
    assert re.search(
        r"UPDATE public.adr_assessments\s+SET status = 'draft',\s+last_review_action = NULL,"
        r"\s+reviewed_by = NULL,\s+reviewed_at = NULL",
        body,
    )
    assert "'medwatch_draft_discarded'" in body
    assert "'discarded'" in body
    assert "'reason', v_reason" in body and "'previous_status', v_previous_status" in body
    assert "adr_information_requests" not in body.split("BEGIN", 1)[1]


def test_step_8_grants_are_service_role_only_and_history_is_not_deletable() -> None:
    revoke = MIGRATION.split("-- 8. Grants")[1].split("GRANT EXECUTE")[0]
    grant = MIGRATION.split("-- 8. Grants")[1].split("GRANT EXECUTE")[1].split(";")[0]
    for signature in (
        "public.create_medwatch_draft(uuid, uuid, jsonb, jsonb, text, uuid)",
        "public.approve_medwatch_draft(uuid, uuid, text, integer, jsonb)",
        "public.record_medwatch_draft_export(uuid, uuid, text, text, text)",
        "public.record_medwatch_draft_export(uuid, uuid)",
        "public.discard_medwatch_draft(uuid, uuid, text, integer)",
        "public.record_medwatch_external_submission(uuid, uuid, date, text, text, text, boolean, integer)",
        "public.amend_medwatch_external_submission(uuid, uuid, uuid, date, text, text, text, text)",
    ):
        assert signature in revoke and signature in grant
    assert "FROM PUBLIC, anon, authenticated;" in revoke
    assert grant.strip().endswith("TO service_role")
    assert re.search(
        r"REVOKE DELETE, TRUNCATE ON public.adr_assessment_audit_events,\s+"
        r"public.medwatch_draft_audit_events, public.medwatch_external_submissions\s+"
        r"FROM PUBLIC, anon, authenticated, service_role;",
        MIGRATION,
    )


def test_step_9_verification_block_fails_closed_on_each_guarantee() -> None:
    block = MIGRATION.split("DO $$")[1]
    for message in (
        "One non-discarded MedWatch draft per assessment is not enforced",
        "The MedWatch submission guards are missing",
        "Browser roles may not call a MedWatch RPC",
        "No role may write MedWatch submission history directly",
        "A MedWatch submission patient reference blocks patient deletion",
        "The 048 export signature must record a JSON export through the new one",
    ):
        assert f"RAISE EXCEPTION '{message}'" in block


def test_no_enum_value_existing_migration_edit_or_destructive_statement() -> None:
    assert not re.search(r"ALTER\s+TYPE[^;]*ADD\s+VALUE", CODE, re.IGNORECASE)
    for statement in ("DROP TABLE", "DELETE FROM", "DROP SCHEMA", "pg_net", "http"):
        assert statement not in CODE, statement
    assert not re.search(r"^\s*TRUNCATE\b", CODE, re.MULTILINE)
    assert "fda.gov" not in CODE
