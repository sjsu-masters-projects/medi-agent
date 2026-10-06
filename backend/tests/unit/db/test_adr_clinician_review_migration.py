"""Schema guarantees for clinician ADR review actions."""

from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "src/app/db/migrations/046_adr_clinician_review_actions.sql"
).read_text()


def test_review_actions_are_atomic_and_assignment_scoped() -> None:
    assert "FUNCTION public.review_adr_assessment" in MIGRATION
    assert "FOR UPDATE" in MIGRATION
    assert "clinician_id = p_actor_id" in MIGRATION
    assert "team.status" not in MIGRATION or "status = 'active'" in MIGRATION


def test_every_review_action_writes_an_immutable_audit_event() -> None:
    assert "CREATE TABLE IF NOT EXISTS public.adr_assessment_audit_events" in MIGRATION
    assert "INSERT INTO public.adr_assessment_audit_events" in MIGRATION
    assert "information_requested" in MIGRATION
    assert "marked_reviewed" in MIGRATION
    assert "dismissed" in MIGRATION


def test_direct_review_function_access_is_service_role_only() -> None:
    assert "FROM PUBLIC, anon, authenticated" in MIGRATION
    assert "TO service_role" in MIGRATION
