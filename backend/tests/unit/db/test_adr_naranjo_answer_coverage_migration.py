"""Text-level guarantees of the Naranjo answer-coverage migration (PV-001-D)."""

import re
from pathlib import Path

from app.pharmacovigilance import (
    CLINICIAN_ANSWERABLE_NARANJO_QUESTIONS,
    PATIENT_ANSWERABLE_NARANJO_QUESTIONS,
)

MIGRATIONS = Path(__file__).resolve().parents[3] / "src/app/db/migrations"
MIGRATION = (MIGRATIONS / "100_adr_naranjo_answer_coverage.sql").read_text()
PREVIOUS = (MIGRATIONS / "063_adr_information_loop_lifecycle.sql").read_text()


def _function(source: str, header: str) -> str:
    start = source.index(header)
    return source[start : source.index("$$;", start)]


def _quoted(text: str) -> set[str]:
    return set(re.findall(r'"([a-z_]+)"', text)) | set(re.findall(r"'([a-z_]+)'", text))


def test_it_follows_the_ledger_with_one_file() -> None:
    assert [p.name for p in MIGRATIONS.glob("100_*.sql")] == ["100_adr_naranjo_answer_coverage.sql"]
    assert (MIGRATIONS / "099_medication_question_alert.sql").exists()


def test_request_allowlists_match_the_python_patient_questions() -> None:
    patient = {question.value for question in PATIENT_ANSWERABLE_NARANJO_QUESTIONS}
    constraint = MIGRATION.split("ADD CONSTRAINT adr_information_requests_patient_safe_questions")[
        1
    ].split(";")[0]
    assert _quoted(constraint) == patient
    review = _function(MIGRATION, "CREATE OR REPLACE FUNCTION private.review_adr_assessment(")
    requested = review.split("v_requested_information <@")[1].split("::jsonb")[0]
    assert _quoted(requested) == patient


def test_review_body_is_the_063_body_with_only_the_list_changed() -> None:
    old = _function(PREVIOUS, "CREATE OR REPLACE FUNCTION public.review_adr_assessment(")
    new = _function(MIGRATION, "CREATE OR REPLACE FUNCTION private.review_adr_assessment(")
    old_list = '\'["reappeared_on_rechallenge", "dose_response", "similar_previous_reaction"]\''
    assert old.count(old_list) == 1
    normalized_new = re.sub(r"'\[.*?\]'::jsonb", "LIST", new, flags=re.S)
    normalized_old = re.sub(r"'\[.*?\]'::jsonb", "LIST", old, flags=re.S)
    assert normalized_new.replace("private.review_adr_assessment", "X") == normalized_old.replace(
        "public.review_adr_assessment", "X"
    )


def test_respond_keeps_the_063_body_and_adds_the_stale_guard() -> None:
    old = _function(
        PREVIOUS, "CREATE OR REPLACE FUNCTION public.respond_to_adr_information_request("
    )
    new = _function(
        MIGRATION, "CREATE OR REPLACE FUNCTION public.respond_to_adr_information_request("
    )
    guard = new[new.index("  -- PV-001-D") : new.index("  -- Captures the clinicians'")]
    assert "USING ERRCODE = '40001'" in guard
    assert "(p_naranjo_answers - v_answered) IS DISTINCT FROM" in guard
    assert "NOT (p_evidence @> v_assessment.evidence)" in guard
    restored = new.replace(guard, "").replace("  v_answered text[];\n", "")
    assert restored == old


def test_clinician_function_accepts_only_clinician_questions_and_audits() -> None:
    body = _function(MIGRATION, "CREATE FUNCTION public.record_adr_clinician_answers(")
    clinician = {question.value for question in CLINICIAN_ANSWERABLE_NARANJO_QUESTIONS}
    allowed = body.split("COALESCE(answer->>'question', '') NOT IN (")[1].split(")")[0]
    assert _quoted(allowed) == clinician
    assert "SECURITY DEFINER" in body and "SET search_path = ''" in body
    assert "FOR UPDATE" in body
    assert (
        "private.resolve_acting_team(p_actor_id, v_assessment.patient_id, p_care_team_id)" in body
    )
    assert "reviewed_by_care_team_id IS DISTINCT FROM v_team" in body
    assert "v_assessment.status <> 'draft'" in body
    assert "USING ERRCODE = '40001'" in body
    assert "'source', 'clinician_entry'" in body
    assert "'clinician_naranjo_answers_recorded'" in body
    # The evidence entries are built here, never taken from the caller.
    assert "p_evidence" not in body
    # The basis is evidence, not audit: the audit records questions and answers only.
    audit = body.split("INSERT INTO public.adr_assessment_audit_events")[1]
    assert "basis" not in audit


def test_audit_allowlist_is_a_superset_and_browser_roles_cannot_execute() -> None:
    audit = MIGRATION.split("ADD CONSTRAINT adr_assessment_audit_events_event_type_check")[1].split(
        ";"
    )[0]
    for kind in (
        "marked_reviewed",
        "dismissed",
        "information_requested",
        "patient_information_provided",
        "medwatch_draft_discarded",
        "clinician_naranjo_answers_recorded",
    ):
        assert f"'{kind}'" in audit
    grants = MIGRATION.split("-- 5. Grants.")[1]
    assert "FROM PUBLIC, anon, authenticated;" in grants
    assert "TO service_role;" in grants
    assert "has_function_privilege('anon'" in grants
