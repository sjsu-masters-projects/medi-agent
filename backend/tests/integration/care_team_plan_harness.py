"""Disposable PostgreSQL 16 harness for care-team plan contracts (PLAN-002, CLN-003 G/H).

One container per module. The whole ledger up to the first care-team-plan migration is loaded
once into a template database and the plan migrations are loaded into a second template, so
each test clones a ready database in milliseconds. Tests marked ``before_care_team_plans``
clone the first template and seed legacy rows before applying the plan migrations themselves.
Platform objects the ledger expects from hosted Supabase (storage, the auth schema, the vector
extension) are minimal stand-ins; every application table, trigger, policy, grant and function
comes from the repository migrations. Synthetic data only; nothing touches a hosted database.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest

from tests.integration.supabase_roles import create_roles_sql

MIGRATIONS = Path(__file__).resolve().parents[2] / "src/app/db/migrations"
# Tests marked with one of these stop just before that migration and apply it themselves.
BOUNDARIES = {
    "before_care_team_plans": "083",
    "before_owned_records": "084",
    "before_cross_plan_publication": "085",
}
FIRST_PLAN_MIGRATION = "083_care_team_plan_ownership.sql"
# Ledger files the stand-in platform cannot run: pgvector, and the seed-ledger reader.
SKIPPED = frozenset({"015_drug_knowledge_rag.sql", "021_allow_seed_ledger_read.sql"})

PATIENT = "00000000-0000-0000-0000-000000000001"
CLINICIAN = "00000000-0000-0000-0000-000000000002"
OTHER = "00000000-0000-0000-0000-000000000003"
THIRD = "00000000-0000-0000-0000-000000000004"
CLINIC = "00000000-0000-0000-0000-000000000011"
OTHER_CLINIC = "00000000-0000-0000-0000-000000000012"
TEAM = "00000000-0000-0000-0000-000000000021"
OTHER_TEAM = "00000000-0000-0000-0000-000000000022"
THIRD_TEAM = "00000000-0000-0000-0000-000000000023"
SECOND_PATIENT = "00000000-0000-0000-0000-000000000005"

STAND_INS = """
CREATE SCHEMA IF NOT EXISTS auth;
CREATE TABLE IF NOT EXISTS auth.users(id uuid PRIMARY KEY);
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
CREATE OR REPLACE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql STABLE AS $$
  SELECT '{}'::jsonb $$;
CREATE OR REPLACE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS $$
  SELECT 'service_role' $$;
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE SCHEMA IF NOT EXISTS storage;
GRANT USAGE ON SCHEMA storage TO anon, authenticated, service_role;
CREATE TABLE IF NOT EXISTS storage.buckets(id text PRIMARY KEY, name text, public boolean,
  file_size_limit bigint, allowed_mime_types text[]);
CREATE TABLE IF NOT EXISTS storage.objects(id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  bucket_id text, name text, owner uuid);
GRANT ALL ON storage.objects, storage.buckets TO anon, authenticated, service_role;
ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;
CREATE OR REPLACE FUNCTION storage.foldername(name text) RETURNS text[] LANGUAGE sql AS $$
  SELECT string_to_array(name, '/') $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'supabase_auth_admin') THEN
    CREATE ROLE supabase_auth_admin;
  END IF;
END $$;
CREATE OR REPLACE FUNCTION public.rls_auto_enable() RETURNS void LANGUAGE sql AS $$ SELECT 1 $$;
CREATE TABLE IF NOT EXISTS public.schema_migrations(version text);
"""


def migration_sql(*, before: str | None = None, from_name: str | None = None) -> str:
    """Concatenate ledger files in order. ``before``/``from_name`` are filename prefixes."""
    return _migration_sql(before=before, from_name=from_name)


def _migration_sql(*, before: str | None, from_name: str | None) -> str:
    """Concatenate ledger files in order; ``before``/``from_name`` select a slice."""
    parts: list[str] = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        name = path.name
        if name in SKIPPED:
            continue
        if before is not None and name[: len(before)] >= before:
            continue
        if from_name is not None and name[: len(from_name)] < from_name:
            continue
        text = path.read_text()
        if name == "020_harden_database_security.sql":
            # Everything but the one statement that needs the vector extension: the helper
            # revokes and the policy rewrites that move every policy to the private helpers.
            text = text.replace(
                "ALTER FUNCTION public.match_drug_knowledge_chunks(public.vector, integer, "
                "text[], text[], double precision)\n  SET search_path = pg_catalog, public;",
                "",
            )
        parts.append(f"-- {name}\n{text}\n")
    return "\n".join(parts)


@pytest.fixture(scope="module")
def postgres():
    docker = shutil.which("docker")
    if not docker:
        pytest.fail("Docker and a cached postgres:16 image are required")
    container = f"mediagent-care-plan-test-{uuid4().hex}"
    subprocess.run(
        [
            docker,
            "run",
            "--detach",
            "--pull=never",
            "--network=none",
            "--name",
            container,
            "--env",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "postgres:16",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    try:
        for _ in range(200):
            ready = subprocess.run(
                [
                    docker,
                    "exec",
                    container,
                    "sh",
                    "-c",
                    'test "$(head -n 1 /var/lib/postgresql/data/postmaster.pid)" = 1 '
                    "&& pg_isready -U postgres",
                ],
                capture_output=True,
                timeout=10,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.1)
        else:
            pytest.fail("Disposable PostgreSQL did not become ready")
        base = [
            docker,
            "exec",
            "--interactive",
            container,
            "psql",
            "-U",
            "postgres",
            "-X",
            "-Atq",
            "-v",
            "ON_ERROR_STOP=1",
        ]
        subprocess.run(
            base, input=create_roles_sql(), check=True, capture_output=True, text=True, timeout=60
        )

        def run(database: str, statement: str) -> None:
            result = subprocess.run(
                [*base, "-d", database],
                input=statement,
                capture_output=True,
                text=True,
                timeout=180,
            )
            assert result.returncode == 0, result.stderr

        previous = None
        for boundary in BOUNDARIES.values():
            name = f"tpl_{boundary}"
            if previous is None:
                run("postgres", f"CREATE DATABASE {name};")
                run(name, STAND_INS + migration_sql(before=boundary))
            else:
                run("postgres", f"CREATE DATABASE {name} TEMPLATE tpl_{previous};")
                run(name, migration_sql(from_name=previous, before=boundary))
            previous = boundary
        run("postgres", f"CREATE DATABASE tpl_post TEMPLATE tpl_{previous};")
        run("tpl_post", migration_sql(from_name=previous))
        yield base
    finally:
        subprocess.run(
            [docker, "rm", "--force", "--volumes", container],
            check=False,
            capture_output=True,
            timeout=30,
        )


@pytest.fixture
def sql(postgres, request):
    """Run SQL in a fresh database cloned from the right template; ``execute.start`` forks."""
    boundary = next(
        (
            value
            for marker, value in BOUNDARIES.items()
            if request.node.get_closest_marker(marker) is not None
        ),
        None,
    )
    database = "plan_" + uuid4().hex
    subprocess.run(
        [*postgres, "-d", "postgres"],
        input=f"CREATE DATABASE {database} TEMPLATE {'tpl_' + boundary if boundary else 'tpl_post'};",
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    command = [*postgres, "-d", database]
    children: list[subprocess.Popen[str]] = []

    def execute(statement: str, *, succeeds: bool = True) -> str:
        result = subprocess.run(
            command,
            input="SET statement_timeout='10s';\n" + statement,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (result.returncode == 0) is succeeds, result.stderr
        return result.stdout.strip() if succeeds else result.stderr

    def start(statement: str, name: str) -> subprocess.Popen[str]:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        children.append(process)
        assert process.stdin is not None
        process.stdin.write(
            f"SET statement_timeout='10s'; SET application_name='{name}';\n{statement}"
        )
        process.stdin.close()
        return process

    execute.start = start  # type: ignore[attr-defined]
    execute.command = command  # type: ignore[attr-defined]
    execute.apply_plan_migrations = lambda: execute(  # type: ignore[attr-defined]
        migration_sql(from_name=boundary or "999")
    )
    try:
        yield execute
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)


def finish(process: subprocess.Popen[str]) -> tuple[int, str, str]:
    assert process.stdout is not None and process.stderr is not None
    process.wait(timeout=30)
    return process.returncode, process.stdout.read().strip(), process.stderr.read().strip()


def seed_people(sql, *, second_clinic_for_clinician: bool = False) -> None:
    """One patient; clinicians at two clinics; no links yet. Synthetic names only."""
    sql(f"""
      INSERT INTO auth.users VALUES ('{PATIENT}'),('{SECOND_PATIENT}'),('{CLINICIAN}'),
        ('{OTHER}'),('{THIRD}');
      INSERT INTO patients(id,email,first_name,last_name,date_of_birth) VALUES
        ('{PATIENT}','patient@synthetic.invalid','Synthetic','Patient','1960-01-01'),
        ('{SECOND_PATIENT}','patient2@synthetic.invalid','Second','Patient','1961-01-01');
      INSERT INTO clinics(id,display_name,canonical_name) VALUES
        ('{CLINIC}','Cedar Grove','cedar grove'),('{OTHER_CLINIC}','Birch Clinic','birch clinic');
      INSERT INTO clinicians(id,email,first_name,last_name,specialty,clinic_name,clinic_id) VALUES
        ('{CLINICIAN}','c1@synthetic.invalid','Elena','Park','Cardiology','Cedar Grove','{CLINIC}'),
        ('{OTHER}','c2@synthetic.invalid','Omar','Reyes','Orthopaedics','Birch Clinic','{OTHER_CLINIC}'),
        ('{THIRD}','c3@synthetic.invalid','Tessa','Lin','ENT','Cedar Grove','{CLINIC}');
    """)
    if second_clinic_for_clinician:
        sql(f"""INSERT INTO clinic_memberships(clinician_id,clinic_id,role,status)
          VALUES('{CLINICIAN}','{OTHER_CLINIC}','provider','active');""")


def link(
    sql,
    team: str,
    clinician: str,
    clinic: str,
    patient: str = PATIENT,
    role: str = "specialist",
    status: str = "active",
) -> None:
    sql(f"""INSERT INTO care_teams(id,patient_id,clinician_id,role,status,clinic_id)
      VALUES('{team}','{patient}','{clinician}','{role}','{status}','{clinic}');""")
