"""Contract tests for the active-care-team RLS boundary."""

from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[3] / "src/app/db/migrations/020_harden_database_security.sql"
)


def test_private_assignment_helper_requires_current_clinician_active_assignment() -> None:
    sql = MIGRATION.read_text()

    assert "CREATE OR REPLACE FUNCTION private.is_assigned_clinician(p_patient_id uuid)" in sql
    assert "WHERE clinician_id = auth.uid()" in sql
    assert "AND patient_id = p_patient_id" in sql
    assert "AND status = 'active'" in sql


def test_assignment_helper_is_not_exposed_as_public_rpc() -> None:
    sql = MIGRATION.read_text()

    assert "REVOKE ALL ON FUNCTION private.is_assigned_clinician(uuid) FROM PUBLIC, anon;" in sql
    assert "GRANT EXECUTE ON FUNCTION private.is_assigned_clinician(uuid) TO authenticated;" in sql
    assert "REVOKE EXECUTE ON FUNCTION public.is_assigned_clinician(uuid)" in sql
    assert "FROM PUBLIC, anon, authenticated, supabase_auth_admin;" in sql
