"""Operator-run, disposable PostgreSQL contract tests; no remote DB or model calls."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CARE_PLAN_TEST_POSTGRES") != "1",
    reason="local PostgreSQL contract check is explicitly opt-in",
)
MIGRATIONS = Path(__file__).resolve().parents[2] / "src/app/db/migrations"
PATIENT = "00000000-0000-0000-0000-000000000001"
PLAN = "00000000-0000-0000-0000-000000000002"
REQUEST = "00000000-0000-0000-0000-000000000003"
FACT = "00000000-0000-0000-0000-000000000004"


@pytest.fixture
def sql(tmp_path: Path):
    """Create an isolated cluster, apply real table constraints and migration 043."""
    programs = {name: shutil.which(name) for name in ("initdb", "pg_ctl", "psql")}
    if not all(programs.values()):
        pytest.fail("initdb, pg_ctl and psql are required for this local check")
    data = tmp_path / "data"
    # macOS limits Unix socket paths to 103 bytes; pytest's tmp_path is longer.
    sockets = tempfile.TemporaryDirectory(prefix="care-plan-pg-", dir="/tmp")
    subprocess.run(
        [programs["initdb"], "-D", str(data), "-A", "trust"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            programs["pg_ctl"],
            "-D",
            str(data),
            "-l",
            str(tmp_path / "server.log"),
            "-o",
            f"-k {sockets.name} -h ''",
            "-w",
            "start",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    def execute(statement: str, *, succeeds: bool = True) -> str:
        result = subprocess.run(
            [
                programs["psql"],
                "-h",
                sockets.name,
                "-d",
                "postgres",
                "-At",
                "-v",
                "ON_ERROR_STOP=1",
            ],
            input=statement,
            capture_output=True,
            text=True,
        )
        assert (result.returncode == 0) is succeeds, result.stderr
        return result.stdout.strip() if succeeds else result.stderr

    try:
        execute("""
          CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
          CREATE SCHEMA auth; CREATE TABLE auth.users(id uuid PRIMARY KEY);
          CREATE TABLE public.patients(id uuid PRIMARY KEY, preferred_language text DEFAULT 'en-US');
          CREATE TABLE public.clinicians(id uuid PRIMARY KEY);
          CREATE TABLE public.clinical_recommendations(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            patient_id uuid, action_type text, proposed_payload jsonb, evidence jsonb,
            rationale text, proposer_type text, proposer_reference text, state text);
          CREATE TABLE public.clinical_facts(id uuid PRIMARY KEY, patient_id uuid,
            review_state text);
          CREATE TYPE public.adherence_target_type_enum AS ENUM ('medication', 'obligation');
          CREATE FUNCTION public.update_updated_at() RETURNS trigger LANGUAGE plpgsql
            AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;
        """)
        foundation = (MIGRATIONS / "040_clinician_approved_care_plans.sql").read_text()
        execute(foundation.split("ALTER TABLE public.medications")[0])
        execute("""
          CREATE TYPE public.medication_route_enum AS ENUM ('oral','topical','inhaled','iv','im','subcutaneous');
          CREATE TYPE public.obligation_type_enum AS ENUM ('diet','exercise','custom');
          CREATE TABLE public.care_teams(id uuid DEFAULT gen_random_uuid(), clinician_id uuid,
            patient_id uuid, status text, created_at timestamptz DEFAULT now());
          CREATE TABLE public.medications(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            patient_id uuid, name text, dosage text, frequency text, route medication_route_enum,
            instructions text, prescribed_by_care_team_id uuid, start_date date, end_date date,
            is_active boolean, care_plan_item_id uuid);
          CREATE TABLE public.obligations(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            patient_id uuid, obligation_type obligation_type_enum, description text,
            frequency text, notes text, set_by_care_team_id uuid, is_active boolean,
            care_plan_item_id uuid);
          CREATE TABLE public.approval_decisions(recommendation_id uuid, reviewer_id uuid,
            decision text, note text, edited_payload jsonb);
          CREATE TABLE public.clinical_action_audit_records(recommendation_id uuid,
            actor_id uuid, event_type text, event_data jsonb);
        """)
        execute((MIGRATIONS / "042_care_plan_publication_review_guards.sql").read_text())
        execute((MIGRATIONS / "043_incomplete_care_plan_drafts.sql").read_text())
        execute(f"""
          INSERT INTO patients(id) VALUES ('{PATIENT}');
          INSERT INTO auth.users VALUES ('{PATIENT}');
          INSERT INTO clinicians VALUES ('{PATIENT}');
          INSERT INTO care_teams(clinician_id,patient_id,status) VALUES ('{PATIENT}', '{PATIENT}', 'active');
          INSERT INTO clinical_facts VALUES ('{FACT}', '{PATIENT}', 'pending_review');
          INSERT INTO care_plan_versions(id,patient_id,version_number,source_watermark)
            VALUES ('{PLAN}', '{PATIENT}', 1, '2026-10-01T00:00:00Z');
          INSERT INTO care_plan_generation_requests(id,patient_id,source_watermark,status)
            VALUES ('{REQUEST}', '{PATIENT}', '2026-10-01T00:00:00Z', 'processing');
        """)
        yield execute
    finally:
        subprocess.run(
            [programs["pg_ctl"], "-D", str(data), "-m", "fast", "-w", "stop"],
            check=True,
            capture_output=True,
            text=True,
        )
        sockets.cleanup()


def batch(items: str) -> str:
    return f"""SELECT complete_care_plan_generation('{PLAN}', '{REQUEST}',
      '2026-10-01T00:00:00Z', '{items}'::jsonb);"""


def item(*, frequency: str = "", category: str = "monitoring") -> str:
    return (
        f'{{"source_fact_id":"{FACT}","category":"{category}",'
        f'"title":"Synthetic activity","instructions":"","frequency":"{frequency}",'
        '"blocker_reason":"Missing instruction"}'
    )


def test_missing_evidence_persists_but_confirmation_cannot_publish(sql) -> None:
    sql(batch(f"[{item()}]"))
    assert sql("SELECT status FROM care_plan_generation_requests") == "completed"
    assert sql("SELECT count(*) FROM care_plan_items WHERE frequency = ''") == "1"
    sql("UPDATE care_plan_items SET blocker_reason = NULL")
    error = sql(
        f"UPDATE care_plan_versions SET status='approved', approved_by='{PATIENT}',"
        " approved_at=now()",
        succeeds=False,
    )
    assert "complete reviewed instructions" in error
    assert sql("SELECT status FROM care_plan_versions") == "draft"


def test_bad_batch_rolls_back_items_audit_and_completion(sql) -> None:
    other = item(category="invented").replace(FACT, "00000000-0000-0000-0000-000000000005")
    sql(
        "INSERT INTO clinical_facts VALUES ('00000000-0000-0000-0000-000000000005',"
        f"'{PATIENT}', 'pending_review')"
    )
    sql(batch(f"[{item()}, {other}]"), succeeds=False)
    assert sql("SELECT count(*) FROM care_plan_items") == "0"
    assert sql("SELECT count(*) FROM care_plan_audit_events") == "0"
    assert sql("SELECT status FROM care_plan_generation_requests") == "processing"
    sql(batch(f"[{item()}]"))
    assert sql("SELECT count(*) FROM care_plan_items") == "1"


def test_stale_claim_cannot_complete_or_overwrite_new_evidence(sql) -> None:
    sql(
        "UPDATE care_plan_generation_requests SET status='pending',"
        "source_watermark='2026-10-02T00:00:00Z'"
    )
    assert "no longer current" in sql(batch(f"[{item()}]"), succeeds=False)
    assert sql("SELECT count(*) FROM care_plan_items") == "0"


def test_publication_checks_generation_and_freezes_approved_items(sql) -> None:
    sql(batch(f"[{item()}]"))
    sql(
        "UPDATE care_plan_items SET instructions='Record the sourced activity',"
        " frequency='daily', blocker_reason=NULL"
    )
    sql("UPDATE care_plan_generation_requests SET status='failed'")
    assert "generation must complete" in sql(
        f"UPDATE care_plan_versions SET status='approved', approved_by='{PATIENT}',"
        "approved_at=now()",
        succeeds=False,
    )
    sql("UPDATE care_plan_generation_requests SET status='completed'")
    sql(
        f"UPDATE care_plan_versions SET status='approved', approved_by='{PATIENT}',"
        "approved_at=now()"
    )
    assert "only draft" in sql("UPDATE care_plan_items SET title='Changed'", succeeds=False)
    assert "only draft" in sql("DELETE FROM care_plan_items", succeeds=False)


def test_browser_roles_cannot_execute_generation_or_guards(sql) -> None:
    for role in ("anon", "authenticated"):
        assert (
            sql(
                f"SELECT has_function_privilege('{role}',"
                "'complete_care_plan_generation(uuid,uuid,timestamptz,jsonb)', 'execute')"
            )
            == "f"
        )
    assert (
        sql(
            "SELECT has_function_privilege('service_role',"
            "'complete_care_plan_generation(uuid,uuid,timestamptz,jsonb)', 'execute')"
        )
        == "t"
    )


def test_actual_publication_rolls_back_projections_then_publishes_reviewed_activity(sql) -> None:
    sql(batch(f"[{item()}]"))
    sql(
        "UPDATE care_plan_items SET instructions='Record the sourced activity',"
        "frequency='daily', blocker_reason=NULL, reviewed_locale='en-US'"
    )
    sql("UPDATE care_plan_generation_requests SET status='failed'")
    approve = f"SELECT approve_care_plan_version('{PLAN}', '{PATIENT}', 'Synthetic review');"
    assert "generation must complete" in sql(approve, succeeds=False)
    assert sql("SELECT count(*) FROM obligations") == "0"
    assert sql("SELECT count(*) FROM clinical_recommendations") == "0"
    assert sql("SELECT count(*) FROM approval_decisions") == "0"
    sql("UPDATE care_plan_generation_requests SET status='completed'")
    sql(approve)
    assert sql("SELECT status FROM care_plan_versions") == "approved"
    assert sql("SELECT count(*) FROM obligations WHERE is_active") == "1"
    assert sql("SELECT count(*) FROM approval_decisions") == "1"
    assert sql("SELECT count(*) FROM clinical_action_audit_records") == "3"
    assert "not eligible" in sql(approve, succeeds=False)


def test_actual_publication_denies_unassigned_clinician(sql) -> None:
    sql(batch(f"[{item()}]"))
    error = sql(
        f"SELECT approve_care_plan_version('{PLAN}', '{FACT}', 'Synthetic review')", succeeds=False
    )
    assert "not assigned" in error
    assert sql("SELECT count(*) FROM obligations") == "0"
