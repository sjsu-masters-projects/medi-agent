"""Text-level guarantees of migration 095 (symptom-review notification and hand-off report link)."""

from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "src/app/db/migrations"
MIGRATION = (MIGRATIONS / "095_symptom_review_notifications.sql").read_text()


def _function(name: str) -> str:
    start = MIGRATION.index(f"CREATE OR REPLACE FUNCTION {name}(")
    return MIGRATION[start : MIGRATION.index("$$;", start)]


def test_it_follows_the_reserved_sequences_and_is_idempotent_to_reapply() -> None:
    assert [p.name for p in MIGRATIONS.glob("095_*.sql")] == [
        "095_symptom_review_notifications.sql"
    ]
    assert "ADD COLUMN IF NOT EXISTS symptom_report_id" in MIGRATION
    assert "DROP CONSTRAINT IF EXISTS notification_events_event_type_check" in MIGRATION
    assert "DROP TRIGGER IF EXISTS symptom_report_review_notification" in MIGRATION
    assert "WHERE cm.symptom_report_id IS NULL" in MIGRATION


def test_the_event_type_is_added_to_a_superset_allowlist() -> None:
    allowlist = MIGRATION.split("ADD CONSTRAINT notification_events_event_type_check")[1]
    allowlist = allowlist.split("));")[0]
    for kind in (
        "message_received",
        "critical_result",
        "adr_information_answered",
        "care_plan_review",
        "symptom_report_reviewed",
    ):
        assert f"'{kind}'" in allowlist


def test_review_event_is_history_only_patient_audience_and_one_per_team() -> None:
    assert "WHEN 'symptom_report_reviewed' THEN RETURN false" in _function(
        "private.notification_actionable"
    )
    body = _function("private.capture_symptom_report_review")
    assert "'symptom_report_reviewed', 'follow_up', 'patient', NULL" in body
    assert (
        "'symptom_report_reviews:' || NEW.report_id::text || ':' || NEW.care_team_id::text" in body
    )
    assert "confirmation_state = 'patient_confirmed'" in body
    assert "AFTER INSERT ON public.symptom_report_reviews" in MIGRATION
    # Nothing from the report beyond its title, and no answers or provenance.
    for forbidden in ("confirmed_content", "answers", "severity", "body_area"):
        assert forbidden not in body


def test_handoff_records_its_report_and_backfill_links_only_unambiguous_matches() -> None:
    assert (
        "INSERT INTO public.clinician_messages(clinician_id,patient_id,channel,subject,body,symptom_report_id)"
        in _function("private.enqueue_confirmed_symptom_review")
    )
    backfill = MIGRATION.split("UPDATE public.clinician_messages m")[1].split("-- ── 2.")[0]
    assert "a.action = 'review_handoff'" in backfill
    assert "HAVING count(DISTINCT r.id) = 1" in backfill
    assert "cm.body = 'Patient confirmed: '" in backfill


def test_grants_and_verification_cover_the_new_objects() -> None:
    assert "REVOKE ALL ON FUNCTION private.capture_symptom_report_review()" in MIGRATION
    assert "private.email_preference('symptom_report_reviewed') IS NOT NULL" in MIGRATION
    assert "SET search_path = ''" in _function("private.capture_symptom_report_review")
