"""Guard the least-privilege grant contract for the SMART import backend."""

from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "app"
    / "db"
    / "migrations"
    / "026_grant_service_role_smart_import_access.sql"
)


def test_smart_import_service_role_grants_are_minimal_and_server_only() -> None:
    migration = MIGRATION_PATH.read_text()

    assert "GRANT SELECT, INSERT, UPDATE ON TABLE" in migration
    assert "public.smart_launch_sessions" in migration
    assert "public.fhir_imports" in migration
    assert "public.smart_portal_handoffs" in migration
    assert "public.clinical_facts" in migration
    assert "GRANT SELECT, INSERT ON TABLE" in migration
    assert "public.fhir_import_resources" in migration
    assert "public.source_provenances" in migration
    assert "public.evidence_citations" in migration
    assert "public.clinical_fact_audit_events" in migration
    assert "TO service_role" in migration
    assert "DELETE" not in migration
    assert "anon" not in migration
    assert "authenticated" not in migration
