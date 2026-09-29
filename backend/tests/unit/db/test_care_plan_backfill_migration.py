"""Guard the one-time care-plan request backfill's safety boundary."""

from pathlib import Path

MIGRATION = (
    Path(__file__).parents[3]
    / "src/app/db/migrations/041_backfill_document_grounded_care_plan_requests.sql"
)


def test_backfill_queues_only_document_grounded_care_plan_facts_without_plan_history():
    sql = MIGRATION.read_text()

    assert "facts.fact_type IN ('medication', 'obligation')" in sql
    assert "facts.review_state IN ('pending_review', 'approved')" in sql
    assert "provenance.artifact_type = 'document'" in sql
    assert "documents.parse_status = 'completed'" in sql
    assert "FROM public.care_plan_versions AS plans" in sql
    assert "FROM public.care_plan_generation_requests AS requests" in sql
    assert "ON CONFLICT DO NOTHING" in sql
