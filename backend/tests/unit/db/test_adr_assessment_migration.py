"""Schema guarantees for auditable ADR decision support."""

from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[3] / "src/app/db/migrations/042_auditable_adr_assessments.sql"
).read_text()


def test_naranjo_score_supports_the_published_negative_range() -> None:
    assert "naranjo_score BETWEEN -4 AND 13" in MIGRATION


def test_evidence_and_complete_assessment_are_persisted_as_json() -> None:
    assert "naranjo_answers jsonb" in MIGRATION
    assert "naranjo_assessment jsonb" in MIGRATION
    assert "evidence jsonb" in MIGRATION


def test_one_review_draft_is_created_per_symptom_report() -> None:
    assert "adr_assessments_one_per_symptom" in MIGRATION
    assert "ON public.adr_assessments(symptom_report_id)" in MIGRATION


def test_only_the_backend_role_receives_write_access() -> None:
    assert "GRANT INSERT, UPDATE ON TABLE public.adr_assessments TO service_role" in MIGRATION
    assert " TO authenticated" not in MIGRATION
    assert " TO anon" not in MIGRATION
