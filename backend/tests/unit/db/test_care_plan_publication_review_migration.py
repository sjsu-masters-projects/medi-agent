"""Publication remains fail-closed even if an API caller skips the review UI."""

from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "src/app/db/migrations/042_care_plan_publication_review_guards.sql"
)


def test_publication_transaction_checks_locale_and_medication_decision() -> None:
    sql = MIGRATION.read_text()

    assert "reviewed_locale IS DISTINCT FROM v_locale" in sql
    assert "medication->>'decision' = 'create'" in sql
    assert "medication->>'decision' = 'update'" in sql
    assert "two plan items cannot update one medication" in sql
    assert "two plan items cannot create the same medication" in sql
    assert "active medication already exists" in sql
    assert "clinician is not assigned to patient" in sql
    assert "SECURITY INVOKER SET search_path = ''" in sql
    assert "FROM PUBLIC, anon, authenticated" in sql
    assert "TO service_role" in sql
