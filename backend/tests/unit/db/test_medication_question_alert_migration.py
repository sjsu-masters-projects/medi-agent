"""Text-level guarantees of migration 099 (patient alert for a medication question)."""

from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "src/app/db/migrations"
MIGRATION = (MIGRATIONS / "099_medication_question_alert.sql").read_text()


def _function(name: str) -> str:
    start = MIGRATION.index(f"CREATE OR REPLACE FUNCTION {name}(")
    return MIGRATION[start : MIGRATION.index("$$;", start)]


def test_it_is_the_only_099_and_is_idempotent_to_reapply() -> None:
    assert [p.name for p in MIGRATIONS.glob("099_*.sql")] == ["099_medication_question_alert.sql"]
    assert "DROP TRIGGER IF EXISTS medication_confirmation_asked_notification" in MIGRATION
    assert MIGRATION.count("to_regprocedure(") == 3  # each rename is guarded


def test_the_event_is_captured_by_trigger_once_per_request_key() -> None:
    body = _function("private.capture_medication_confirmation_asked")
    assert "AFTER INSERT ON public.medication_confirmation_requests" in MIGRATION
    assert "'medication_confirmation:' || NEW.id::text" in body
    assert "'patient', NULL" in body  # patient audience, no named recipient
    # Names and ids only: no medicine, dose, answer or note.
    for forbidden in ("medication_name", "dosage", "frequency", "answer"):
        assert forbidden not in body


def test_it_extends_the_096_wrappers_instead_of_replacing_them() -> None:
    for name, call in (
        ("private.notification_source", "notification_source_handoff(p_type, p_id)"),
        ("private.notification_authorized", "notification_authorized_handoff(e, p_actor, p_role)"),
        ("private.notification_actionable", "notification_actionable_handoff(e, p_role)"),
    ):
        assert f"RETURN private.{call}" in _function(name)
    assert "_core" not in MIGRATION.replace("notification_capture", "")


def test_actionable_only_while_open_and_unexpired_on_the_database_clock() -> None:
    body = _function("private.notification_actionable")
    assert "r.status = 'open'" in body and "r.expires_at > clock_timestamp()" in body
    assert "p_role = 'patient'" in body


def test_authorization_is_the_asked_patient_with_an_active_link() -> None:
    body = _function("private.notification_authorized")
    assert "p_role = 'patient'" in body and "p_actor = e.patient_id" in body
    assert "e.audience = 'patient'" in body and "t.status = 'active'" in body


def test_grants_search_path_and_email_are_verified() -> None:
    assert "REVOKE ALL ON FUNCTION" in MIGRATION and "FROM PUBLIC, anon, authenticated" in MIGRATION
    assert MIGRATION.count("SET search_path = ''") == 4
    assert "private.email_preference('medication_confirmation_asked') IS NOT NULL" in MIGRATION
    assert "DO $verify$" in MIGRATION
