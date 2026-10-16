"""Text-level guarantees of the clinic-membership migration (CLN-003 slice A, 065)."""

import re
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "src/app/db/migrations"
MIGRATION = (MIGRATIONS / "065_clinic_memberships.sql").read_text()
CODE = "\n".join(line.split("--", 1)[0] for line in MIGRATION.splitlines())


def _function(name: str) -> str:
    start = MIGRATION.index(f"CREATE FUNCTION {name}(")
    return MIGRATION[start : MIGRATION.index("$$;", start)]


def test_it_is_the_one_065_migration_and_it_is_not_applied_anywhere() -> None:
    assert [p.name for p in MIGRATIONS.glob("065_*.sql")] == ["065_clinic_memberships.sql"]
    assert "applied to a hosted project only on explicit authorization" in MIGRATION
    assert "apply first, merge after" in MIGRATION
    for transaction in ("BEGIN;", "COMMIT;", "ROLLBACK;"):
        assert transaction not in CODE


def test_memberships_table_shape_and_constraints() -> None:
    table = CODE.split("CREATE TABLE public.clinic_memberships (")[1].split(");")[0]
    assert "clinician_id uuid NOT NULL REFERENCES public.clinicians(id) ON DELETE CASCADE" in table
    assert "clinic_id uuid NOT NULL REFERENCES public.clinics(id) ON DELETE RESTRICT" in table
    assert "role public.clinician_role_enum NOT NULL" in table
    assert "CHECK (status IN ('active', 'inactive'))" in table
    assert (
        "CONSTRAINT clinic_memberships_clinician_clinic_key UNIQUE (clinician_id, clinic_id)"
        in (table)
    )
    assert "created_at timestamptz NOT NULL" in table
    assert "updated_at timestamptz NOT NULL" in table


def test_memberships_are_least_privilege() -> None:
    assert "ALTER TABLE public.clinic_memberships ENABLE ROW LEVEL SECURITY;" in CODE
    assert re.search(
        r"CREATE POLICY clinic_memberships_own_select ON public.clinic_memberships\s+"
        r"FOR SELECT TO authenticated\s+USING \(clinician_id = auth.uid\(\)\);",
        CODE,
    )
    assert (
        "REVOKE ALL ON TABLE public.clinic_memberships FROM PUBLIC, anon, authenticated, "
        "service_role;"
    ) in CODE
    assert "GRANT SELECT ON TABLE public.clinic_memberships TO authenticated;" in CODE
    assert "GRANT SELECT, INSERT, UPDATE ON TABLE public.clinic_memberships TO service_role;" in (
        CODE
    )
    assert "DELETE ON TABLE public.clinic_memberships" not in CODE
    assert CODE.count("CREATE POLICY") == 1


def test_backfill_skips_clinicians_without_a_clinic_and_reports_only_a_count() -> None:
    backfill = CODE.split("INSERT INTO public.clinic_memberships (clinician_id, clinic_id, role")[
        1
    ].split(";")[0]
    assert "FROM public.clinicians c" in backfill
    assert "WHERE c.clinic_id IS NOT NULL" in backfill
    assert "have no clinic and received no membership" in CODE
    notice = CODE.split("RAISE NOTICE")[1].split(";")[0]
    assert "v_without_clinic" in notice
    assert "c.id" not in notice and "email" not in notice


def test_legacy_columns_are_mirrored_during_the_compatibility_period() -> None:
    body = _function("private.mirror_legacy_clinic_membership")
    assert "SECURITY DEFINER" in body and "SET search_path = ''" in body
    assert "SET status = 'inactive'" in body
    assert "ON CONFLICT (clinician_id, clinic_id) DO UPDATE" in body
    assert re.search(
        r"AFTER INSERT OR UPDATE OF clinic_id, role ON public.clinicians\s+"
        r"FOR EACH ROW EXECUTE FUNCTION private.mirror_legacy_clinic_membership\(\);",
        CODE,
    )
    assert "ALTER TABLE public.clinicians DROP" not in CODE


def test_care_teams_take_a_clinic_and_are_unique_per_clinic() -> None:
    assert "ADD COLUMN clinic_id uuid REFERENCES public.clinics(id);" in CODE
    assert re.search(
        r"UPDATE public.care_teams t\s+SET clinic_id = c.clinic_id\s+FROM public.clinicians c",
        CODE,
    )
    assert "pg_catalog.pg_get_constraintdef(c.oid) = 'UNIQUE (patient_id, clinician_id)'" in CODE
    assert re.search(
        r"ADD CONSTRAINT care_teams_patient_clinician_clinic_key\s+"
        r"UNIQUE \(patient_id, clinician_id, clinic_id\);",
        CODE,
    )
    assert re.search(
        r"CREATE UNIQUE INDEX uq_care_teams_patient_clinician_without_clinic\s+"
        r"ON public.care_teams \(patient_id, clinician_id\)\s+WHERE clinic_id IS NULL;",
        CODE,
    )


def test_nothing_depends_on_the_replaced_constraint() -> None:
    old_conflict = re.compile(r"ON\s+CONFLICT\s*\(\s*patient_id\s*,\s*clinician_id\s*\)", re.I)
    for path in MIGRATIONS.glob("*.sql"):
        assert not old_conflict.search(path.read_text()), path.name
    source = Path(__file__).resolve().parents[3] / "src"
    for path in source.rglob("*.py"):
        text = path.read_text()
        assert not re.search(r"on_conflict\s*=\s*[\"']patient_id,\s*clinician_id[\"']", text), path


def test_a_links_clinic_comes_from_the_code_or_the_clinicians_membership() -> None:
    body = _function("private.care_team_clinic_guard")
    assert "SECURITY DEFINER" in body and "SET search_path = ''" in body
    assert "IF NEW.clinic_id IS NULL THEN" in body
    assert "NEW.clinician_id IS DISTINCT FROM OLD.clinician_id" in body
    assert "FROM public.clinic_memberships m" in body and "m.status = 'active'" in body
    assert "A care-team link keeps its clinic" in body
    assert re.search(
        r"BEFORE INSERT OR UPDATE OF clinic_id, clinician_id ON public.care_teams",
        CODE,
    )


def test_access_rules_are_not_widened() -> None:
    assert "is_assigned_clinician" not in CODE
    assert "ALTER POLICY" not in CODE and "DROP POLICY" not in CODE
    helper = _function("private.is_clinic_member")
    assert "m.clinician_id = auth.uid()" in helper
    assert "m.status = 'active'" in helper and "cl.status = 'active'" in helper
    assert "SECURITY DEFINER" in helper and "SET search_path = pg_catalog" in helper
    assert "REVOKE ALL ON FUNCTION private.is_clinic_member(uuid) FROM PUBLIC, anon;" in CODE
    assert "GRANT EXECUTE ON FUNCTION private.is_clinic_member(uuid) TO authenticated;" in CODE


def test_it_ends_with_a_fail_closed_verification_block() -> None:
    verification = MIGRATION.split("── 4. Fail-closed")[1]
    for message in (
        "Every clinician with a clinic needs exactly one membership",
        "Every care-team link needs a clinic unless its clinician has none",
        "care_teams must be unique on (patient_id, clinician_id, clinic_id) only",
        "clinic_memberships must have row-level security enabled",
        "clinic_memberships grants are wider than service-role writes and own reads",
    ):
        assert f"RAISE EXCEPTION '{message}'" in verification
    assert MIGRATION.rstrip().endswith("END $$;")
