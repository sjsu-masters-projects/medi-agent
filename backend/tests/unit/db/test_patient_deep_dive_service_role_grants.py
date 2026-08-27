"""Guard the minimal backend grant required by the patient deep-dive route."""

from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "app"
    / "db"
    / "migrations"
    / "027_grant_service_role_symptom_report_read.sql"
)


def test_patient_deep_dive_symptom_report_grant_is_server_only() -> None:
    migration = MIGRATION_PATH.read_text()

    assert "GRANT SELECT ON TABLE public.symptom_reports TO service_role" in migration
    assert "INSERT" not in migration
    assert "UPDATE" not in migration
    assert "DELETE" not in migration
    assert "anon" not in migration
    assert "authenticated" not in migration
