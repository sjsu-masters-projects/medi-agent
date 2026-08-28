"""Guard the least-privilege reads required by clinician review routes."""

from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "app"
    / "db"
    / "migrations"
    / "028_grant_service_role_clinician_review_reads.sql"
)


def test_clinician_review_grants_are_server_only_and_read_only() -> None:
    migration = MIGRATION_PATH.read_text()

    assert (
        "GRANT SELECT ON TABLE public.soap_notes, public.adr_assessments TO service_role"
        in migration
    )
    assert "INSERT" not in migration
    assert "UPDATE" not in migration
    assert "DELETE" not in migration
    assert "anon" not in migration
    assert "authenticated" not in migration
