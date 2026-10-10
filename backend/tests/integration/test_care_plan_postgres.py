"""Operator-run, disposable PostgreSQL contract tests; no remote DB or model calls."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.care_plan_service import CarePlanService

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
    """Create an isolated cluster with hardened helpers and care-plan migrations."""
    programs = {name: shutil.which(name) for name in ("initdb", "pg_ctl", "psql")}
    docker_mode = os.environ.get("CARE_PLAN_TEST_POSTGRES_DOCKER") == "1"
    docker = shutil.which("docker")
    if docker_mode and not docker:
        pytest.fail("docker is required for the opt-in container check")
    if not docker_mode and not all(programs.values()):
        pytest.fail("initdb, pg_ctl and psql are required for this local check")
    data = tmp_path / "data"
    container = None
    # macOS limits Unix socket paths to 103 bytes; pytest's tmp_path is longer.
    sockets = tempfile.TemporaryDirectory(prefix="care-plan-pg-", dir="/tmp")
    if docker_mode:
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
            timeout=30,
        )
        try:
            for _ in range(100):
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
                    timeout=5,
                )
                if ready.returncode == 0:
                    break
                time.sleep(0.1)
            else:
                pytest.fail("Disposable PostgreSQL container did not become ready")
        except BaseException:
            subprocess.run([docker, "rm", "--force", container], check=True, capture_output=True)
            sockets.cleanup()
            raise
        command = [docker, "exec", "--interactive", container, "psql", "-U", "postgres"]
    else:
        initialization = subprocess.run(
            [programs["initdb"], "-D", str(data), "-A", "trust"],
            check=False,
            capture_output=True,
            text=True,
        )
        if initialization.returncode:
            sockets.cleanup()
            pytest.fail(f"Disposable PostgreSQL initialization failed: {initialization.stderr}")
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

        command = [programs["psql"], "-h", sockets.name]
    command += [
        "-X",
        "-d",
        "postgres",
        "-At",
        "-q",
        "-v",
        "ON_ERROR_STOP=1",
    ]
    children = []

    def start(statement: str, name: str):
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        children.append(process)
        process.stdin.write(
            f"SET statement_timeout='8s'; SET application_name='{name}';\n{statement}\n"
        )
        process.stdin.close()
        return process

    def execute(statement: str, *, succeeds: bool = True) -> str:
        result = subprocess.run(
            command,
            input=f"SET statement_timeout='8s';\n{statement}",
            capture_output=True,
            text=True,
            timeout=12,
        )
        assert (result.returncode == 0) is succeeds, result.stderr
        return result.stdout.strip() if succeeds else result.stderr

    execute.start = start

    try:
        execute("""
          CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
          CREATE SCHEMA auth; CREATE TABLE auth.users(id uuid PRIMARY KEY);
          CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
            SELECT (nullif(current_setting('request.jwt.claims', true), '')::jsonb->>'sub')::uuid;
          $$;
          GRANT USAGE ON SCHEMA auth TO authenticated, anon;
          CREATE TABLE public.patients(id uuid PRIMARY KEY, preferred_language text DEFAULT 'en-US');
          CREATE TABLE public.clinicians(id uuid PRIMARY KEY);
          CREATE TABLE public.clinical_recommendations(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            patient_id uuid, action_type text, proposed_payload jsonb, evidence jsonb,
            rationale text, proposer_type text, proposer_reference text, state text);
          CREATE TABLE public.clinical_facts(id uuid PRIMARY KEY, patient_id uuid,
            review_state text, fact_type text, value jsonb);
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
        execute((MIGRATIONS / "044_care_plan_overlap_publication_guard.sql").read_text())
        execute((MIGRATIONS / "045_care_plan_activity_continuity.sql").read_text())
        execute("""
          CREATE FUNCTION public.is_clinician() RETURNS boolean LANGUAGE sql STABLE
            AS $$ SELECT EXISTS (SELECT 1 FROM public.clinicians WHERE id=auth.uid()); $$;
          CREATE FUNCTION public.is_assigned_clinician(uuid) RETURNS boolean LANGUAGE sql STABLE
            AS $$ SELECT EXISTS (SELECT 1 FROM public.care_teams
                  WHERE clinician_id=auth.uid() AND patient_id=$1 AND status='active'); $$;
          REVOKE ALL ON FUNCTION public.is_clinician(), public.is_assigned_clinician(uuid)
            FROM PUBLIC, anon, authenticated;
        """)
        hardening = (MIGRATIONS / "020_harden_database_security.sql").read_text()
        execute(hardening.split("-- Public helper functions remain")[0])
        execute(
            foundation[
                foundation.index(
                    "ALTER TABLE public.care_plan_versions ENABLE ROW LEVEL SECURITY;"
                ) :
            ].split("CREATE OR REPLACE FUNCTION public.request_care_plan_generation")[0]
        )
        execute((MIGRATIONS / "047_care_plan_private_rls_helpers.sql").read_text())
        # Use the real request RPC, including its original privilege boundary.
        execute(
            foundation[
                foundation.index(
                    "CREATE OR REPLACE FUNCTION public.request_care_plan_generation"
                ) : foundation.index(
                    "CREATE OR REPLACE FUNCTION public.claim_pending_care_plan_generation"
                )
            ]
        )
        execute("""
          REVOKE ALL ON FUNCTION public.request_care_plan_generation(uuid,timestamptz)
            FROM PUBLIC, anon, authenticated;
          GRANT EXECUTE ON FUNCTION public.request_care_plan_generation(uuid,timestamptz) TO service_role;
        """)
        execute(f"""
          INSERT INTO patients(id) VALUES ('{PATIENT}');
          INSERT INTO auth.users VALUES ('{PATIENT}');
          INSERT INTO clinicians VALUES ('{PATIENT}');
          INSERT INTO care_teams(clinician_id,patient_id,status) VALUES ('{PATIENT}', '{PATIENT}', 'active');
          INSERT INTO clinical_facts(id, patient_id, review_state) VALUES ('{FACT}', '{PATIENT}', 'pending_review');
          INSERT INTO care_plan_versions(id,patient_id,version_number,source_watermark)
            VALUES ('{PLAN}', '{PATIENT}', 1, '2026-10-01T00:00:00Z');
          INSERT INTO care_plan_generation_requests(id,patient_id,source_watermark,status)
            VALUES ('{REQUEST}', '{PATIENT}', '2026-10-01T00:00:00Z', 'processing');
        """)
        yield execute
    finally:
        for process in children:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        cleanup = (
            [docker, "rm", "--force", container]
            if container
            else [programs["pg_ctl"], "-D", str(data), "-m", "fast", "-w", "stop"]
        )
        subprocess.run(
            cleanup,
            check=True,
            capture_output=True,
            text=True,
        )
        sockets.cleanup()


def batch(items: str) -> str:
    return f"""SELECT complete_care_plan_generation('{PLAN}', '{REQUEST}',
      '2026-10-01T00:00:00Z', '{items}'::jsonb);"""


def setup_review_sources(sql, decision="approved", *, apply_gate=True):
    sql("""
      CREATE TABLE documents(id uuid PRIMARY KEY, patient_id uuid REFERENCES patients(id),
        uploaded_by_role text, review_status text, parse_status text);
      CREATE TABLE source_provenances(id uuid PRIMARY KEY, document_id uuid REFERENCES documents(id),
        artifact_type text, withdrawn_at timestamptz);
      CREATE TABLE evidence_citations(fact_id uuid REFERENCES clinical_facts(id),
        provenance_id uuid REFERENCES source_provenances(id));
    """)
    sql(f"""
      UPDATE clinical_facts SET fact_type='obligation' WHERE id='{FACT}';
      INSERT INTO documents VALUES ('{FACT}', '{PATIENT}', 'patient', '{decision}', 'completed');
      INSERT INTO source_provenances VALUES ('{FACT}', '{FACT}', 'document', NULL);
      INSERT INTO evidence_citations VALUES ('{FACT}', '{FACT}');
    """)
    if apply_gate:
        sql((MIGRATIONS / "048_patient_upload_care_plan_review_gate.sql").read_text())


def review_batch():
    return batch(
        json.dumps(
            [
                {
                    "source_fact_id": FACT,
                    "category": "movement",
                    "title": "Walk",
                    "instructions": "Synthetic walk",
                    "frequency": "daily",
                    "confidence_score": 1,
                }
            ]
        )
    )


def wait_for_session(sql, name, *, waiting=False):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        event = "wait_event_type='Lock'" if waiting else "wait_event='PgSleep'"
        if (
            sql(
                f"SELECT count(*) FROM pg_stat_activity WHERE application_name='{name}' AND {event}"
            )
            == "1"
        ):
            return
        time.sleep(0.01)
    pytest.fail(f"Synthetic session {name} did not reach its synchronization point")


def finish_session(process, *, succeeds=True):
    process.wait(timeout=10)
    output, error = process.stdout.read(), process.stderr.read()
    assert (process.returncode == 0) is succeeds, error
    return output if succeeds else error


@pytest.mark.parametrize("decision", ["pending", "rejected", "approved"])
def test_atomic_patient_upload_review_gate(sql, decision):
    # Historical draft predates 048, so generation does not hide publication denials.
    setup_review_sources(sql, decision, apply_gate=False)
    sql(review_batch())
    sql((MIGRATIONS / "048_patient_upload_care_plan_review_gate.sql").read_text())
    sql(f"UPDATE care_plan_items SET reviewed_locale='en-US' WHERE plan_version_id='{PLAN}';")
    statement = (
        f"SELECT approve_care_plan_version('{PLAN}', '{PATIENT}', 'Synthetic source review');"
    )
    if decision == "approved":
        sql(statement)
        assert sql(f"SELECT status FROM care_plan_versions WHERE id='{PLAN}';") == "approved"
    else:
        assert "Review and approve patient-uploaded" in sql(statement, succeeds=False)
        assert sql(f"SELECT status FROM care_plan_versions WHERE id='{PLAN}';") == "draft"
        assert sql("SELECT count(*) FROM obligations;") == "0"


def test_accepted_parsed_document_requests_generation(sql):
    setup_review_sources(sql, "pending")
    sql(f"""
      UPDATE care_plan_generation_requests SET status='completed' WHERE id='{REQUEST}';
      UPDATE documents SET review_status='approved' WHERE id='{FACT}';
    """)
    assert (
        sql(f"SELECT status FROM care_plan_generation_requests WHERE id='{REQUEST}'") == "completed"
    )
    assert sql("SELECT count(*) FROM care_plan_generation_requests WHERE status='pending'") == "1"


EVIDENCE_MUTATIONS = [
    "UPDATE source_provenances SET withdrawn_at=now()",
    "UPDATE clinical_facts SET review_state='rejected'",
    "UPDATE clinical_facts SET review_state='deleted'",
    "DELETE FROM evidence_citations",
    f"""INSERT INTO documents VALUES ('00000000-0000-0000-0000-000000000005',
          '{PATIENT}', 'patient', 'pending', 'completed');
        INSERT INTO source_provenances VALUES ('00000000-0000-0000-0000-000000000005',
          '00000000-0000-0000-0000-000000000005', 'document', NULL);
        INSERT INTO evidence_citations VALUES ('{FACT}',
          '00000000-0000-0000-0000-000000000005');""",
]


@pytest.mark.parametrize("mutation", EVIDENCE_MUTATIONS)
@pytest.mark.parametrize("stage", ["generation", "publication"])
def test_current_evidence_rechecked_atomically(sql, mutation, stage):
    setup_review_sources(sql)
    if stage == "publication":
        sql(review_batch())
        sql("UPDATE care_plan_items SET reviewed_locale='en-US'")
    sql(mutation)
    statement = (
        review_batch()
        if stage == "generation"
        else f"SELECT approve_care_plan_version('{PLAN}', '{PATIENT}', 'Synthetic review')"
    )
    assert "Review and approve patient-uploaded" in sql(statement, succeeds=False)
    assert sql("SELECT status FROM care_plan_versions") == "draft"
    assert sql("SELECT count(*) FROM obligations") == "0"
    assert sql("SELECT count(*) FROM clinical_recommendations") == "0"
    if stage == "generation":
        assert sql("SELECT count(*) FROM care_plan_items") == "0"
        assert sql("SELECT count(*) FROM care_plan_audit_events") == "0"
        assert sql("SELECT status FROM care_plan_generation_requests") == "processing"


@pytest.mark.parametrize("mutation", EVIDENCE_MUTATIONS)
@pytest.mark.parametrize("stage", ["generation", "publication"])
def test_committed_concurrent_mutation_is_seen_after_fence_wait(sql, mutation, stage):
    setup_review_sources(sql)
    if stage == "publication":
        sql(review_batch())
        sql("UPDATE care_plan_items SET reviewed_locale='en-US'")
    writer = sql.start(f"BEGIN; {mutation}; SELECT pg_sleep(1.5); COMMIT;", "evidence-writer")
    wait_for_session(sql, "evidence-writer")
    statement = (
        review_batch()
        if stage == "generation"
        else f"SELECT approve_care_plan_version('{PLAN}', '{PATIENT}', 'Synthetic review')"
    )
    reader = sql.start(statement, "care-plan-reader")
    wait_for_session(sql, "care-plan-reader", waiting=True)
    finish_session(writer)
    assert "Review and approve patient-uploaded" in finish_session(reader, succeeds=False)
    assert sql("SELECT status FROM care_plan_versions") == "draft"
    assert sql("SELECT count(*) FROM obligations") == "0"


@pytest.mark.parametrize("mutation", EVIDENCE_MUTATIONS[:4])
def test_publication_fence_rejects_reverse_lock_order_without_deadlock(sql, mutation):
    setup_review_sources(sql)
    sql(review_batch())
    sql("UPDATE care_plan_items SET reviewed_locale='en-US'")
    publisher = sql.start(
        f"BEGIN; SELECT approve_care_plan_version('{PLAN}', '{PATIENT}', 'Synthetic review');"
        " SELECT pg_sleep(1.5); COMMIT;",
        "care-plan-publisher",
    )
    wait_for_session(sql, "care-plan-publisher")
    # Reconciliation/withdrawal RPCs can lock a fact before their mutation trigger.
    writer = sql.start(
        f"BEGIN; SELECT id FROM clinical_facts FOR UPDATE; {mutation}; COMMIT;",
        "reverse-order-writer",
    )
    error = finish_session(writer, succeeds=False)
    assert "retry the transaction" in error
    assert "deadlock" not in error.lower()
    finish_session(publisher)
    assert sql("SELECT status FROM care_plan_versions") == "approved"
    assert sql("SELECT review_state FROM clinical_facts") == "pending_review"
    assert sql("SELECT count(*) FROM evidence_citations") == "1"
    assert sql("SELECT count(*) FROM source_provenances WHERE withdrawn_at IS NOT NULL") == "0"


def test_two_document_reviews_serialize_and_queue_once(sql):
    setup_review_sources(sql, "pending")
    second = "00000000-0000-0000-0000-000000000005"
    sql(f"""
      INSERT INTO clinical_facts(id, patient_id, review_state, fact_type) VALUES ('{second}', '{PATIENT}', 'pending_review', 'obligation');
      INSERT INTO documents VALUES ('{second}', '{PATIENT}', 'patient', 'pending', 'completed');
      INSERT INTO source_provenances VALUES ('{second}', '{second}', 'document', NULL);
      INSERT INTO evidence_citations VALUES ('{second}', '{second}');
      UPDATE care_plan_generation_requests SET status='completed';
    """)
    first = sql.start(
        f"BEGIN; UPDATE documents SET review_status='approved' WHERE id='{FACT}' AND review_status='pending';"
        " SELECT pg_sleep(1.5); COMMIT;",
        "first-review",
    )
    wait_for_session(sql, "first-review")
    other = sql.start(
        f"UPDATE documents SET review_status='approved' WHERE id='{second}' AND review_status='pending';",
        "second-review",
    )
    wait_for_session(sql, "second-review", waiting=True)
    finish_session(first)
    finish_session(other)
    assert sql("SELECT count(*) FROM documents WHERE review_status='approved'") == "2"
    assert sql("SELECT count(*) FROM care_plan_generation_requests WHERE status='pending'") == "1"
    assert (
        sql(f"SELECT status FROM care_plan_generation_requests WHERE id='{REQUEST}'") == "completed"
    )


def test_two_request_rpcs_serialize_when_no_open_request_exists(sql):
    setup_review_sources(sql)
    sql("UPDATE care_plan_generation_requests SET status='completed'")
    first = sql.start(
        f"BEGIN; SELECT request_care_plan_generation('{PATIENT}', '2026-10-02');"
        " SELECT pg_sleep(1.5); COMMIT;",
        "first-request",
    )
    wait_for_session(sql, "first-request")
    second = sql.start(
        f"SELECT request_care_plan_generation('{PATIENT}', '2026-10-03');", "second-request"
    )
    wait_for_session(sql, "second-request", waiting=True)
    finish_session(first)
    finish_session(second)
    assert sql("SELECT count(*) FROM care_plan_generation_requests WHERE status='pending'") == "1"
    assert (
        sql(
            "SELECT source_watermark::date FROM care_plan_generation_requests WHERE status='pending'"
        )
        == "2026-10-03"
    )


def test_review_compare_and_set_preserves_first_decision(sql):
    setup_review_sources(sql, "pending")
    first = sql.start(
        f"BEGIN; UPDATE documents SET review_status='approved' WHERE id='{FACT}' AND review_status='pending';"
        " SELECT pg_sleep(1.5); COMMIT;",
        "winning-review",
    )
    wait_for_session(sql, "winning-review")
    second = sql.start(
        f"UPDATE documents SET review_status='rejected' WHERE id='{FACT}' AND review_status='pending' RETURNING id;",
        "losing-review",
    )
    wait_for_session(sql, "losing-review", waiting=True)
    finish_session(first)
    assert finish_session(second).strip() == ""
    assert sql("SELECT review_status FROM documents") == "approved"


def test_source_gate_preserves_approved_projection_and_history(sql):
    setup_review_sources(sql)
    sql(review_batch())
    sql("UPDATE care_plan_items SET reviewed_locale='en-US'")
    sql(f"SELECT approve_care_plan_version('{PLAN}', '{PATIENT}', 'Synthetic baseline')")
    target = sql("SELECT id FROM obligations WHERE is_active")
    old_item = sql(f"SELECT id FROM care_plan_items WHERE plan_version_id='{PLAN}'")
    new_plan = "00000000-0000-0000-0000-000000000007"
    sql(f"""
      CREATE TABLE synthetic_reminders(target_id uuid REFERENCES obligations(id), time text);
      CREATE TABLE synthetic_logs(target_id uuid REFERENCES obligations(id), outcome text);
      INSERT INTO synthetic_reminders VALUES ('{target}', '08:00');
      INSERT INTO synthetic_logs VALUES ('{target}', 'completed');
      INSERT INTO care_plan_versions(id,patient_id,version_number,source_watermark)
        VALUES ('{new_plan}', '{PATIENT}', 2, '2026-10-02');
      INSERT INTO care_plan_items(plan_version_id,source_fact_id,category,title,instructions,
        frequency,confidence_score,reviewed_locale)
        SELECT '{new_plan}',source_fact_id,category,title,instructions,frequency,
          confidence_score,reviewed_locale FROM care_plan_items WHERE id='{old_item}';
      UPDATE source_provenances SET withdrawn_at=now();
    """)
    assert "Review and approve patient-uploaded" in sql(
        f"SELECT approve_care_plan_version('{new_plan}', '{PATIENT}', 'Synthetic revision')",
        succeeds=False,
    )
    assert sql(f"SELECT status FROM care_plan_versions WHERE id='{PLAN}'") == "approved"
    assert sql("SELECT id FROM obligations WHERE is_active") == target
    assert sql(f"SELECT care_plan_item_id FROM obligations WHERE id='{target}'") == old_item
    assert sql("SELECT time FROM synthetic_reminders") == "08:00"
    assert sql("SELECT count(*) FROM synthetic_logs") == "1"


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_review_gate_helpers_and_rpcs_are_not_browser_callable(sql, role):
    setup_review_sources(sql)
    for signature in (
        "public.approve_care_plan_version(uuid,uuid,text)",
        "public.complete_care_plan_generation(uuid,uuid,timestamptz,jsonb)",
        "public.request_care_plan_generation(uuid,timestamptz)",
        "private.approve_care_plan_version(uuid,uuid,text)",
        "private.complete_care_plan_generation(uuid,uuid,timestamptz,jsonb)",
        "private.lock_care_plan_evidence(uuid,boolean)",
        "private.care_plan_fact_is_eligible(uuid,uuid)",
        "private.fence_care_plan_evidence_mutation()",
    ):
        assert sql(f"SELECT has_function_privilege('{role}', '{signature}', 'execute')") == "f"


def test_service_role_can_execute_guarded_generation_and_publication(sql):
    setup_review_sources(sql)
    sql("""
      ALTER ROLE service_role BYPASSRLS;
      GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO service_role;
    """)
    sql(f"SET ROLE service_role; {review_batch()}")
    sql("UPDATE care_plan_items SET reviewed_locale='en-US'")
    sql(
        f"SET ROLE service_role; SELECT approve_care_plan_version('{PLAN}', '{PATIENT}', 'Synthetic role check')"
    )
    assert sql("SELECT status FROM care_plan_versions") == "approved"


def test_non_read_committed_generation_fails_closed(sql):
    setup_review_sources(sql)
    assert "fresh read-committed snapshot" in sql(
        f"BEGIN ISOLATION LEVEL REPEATABLE READ; {review_batch()} COMMIT;", succeeds=False
    )
    assert sql("SELECT status FROM care_plan_generation_requests") == "processing"
    assert sql("SELECT count(*) FROM care_plan_items") == "0"


def test_generation_retry_preserves_explicitly_removed_pending_upload(sql):
    setup_review_sources(sql, "pending", apply_gate=False)
    sql(review_batch())
    excluded = sql("SELECT id FROM care_plan_items")
    sql("UPDATE care_plan_items SET is_removed=true")
    sql("UPDATE care_plan_generation_requests SET status='processing'")
    sql((MIGRATIONS / "048_patient_upload_care_plan_review_gate.sql").read_text())
    sql(review_batch())
    assert sql("SELECT status FROM care_plan_generation_requests") == "completed"
    assert sql("SELECT id FROM care_plan_items WHERE is_removed") == excluded
    assert sql("SELECT count(*) FROM care_plan_items") == "1"


def test_failed_queue_handoff_rolls_back_document_review(sql):
    setup_review_sources(sql, "pending")
    sql("""
      UPDATE care_plan_generation_requests SET status='completed';
      ALTER TABLE care_plan_generation_requests ADD CONSTRAINT synthetic_queue_failure
        CHECK (status <> 'pending');
    """)
    assert "synthetic_queue_failure" in sql(
        "UPDATE documents SET review_status='approved'", succeeds=False
    )
    assert sql("SELECT review_status FROM documents") == "pending"
    assert sql("SELECT count(*) FROM care_plan_generation_requests") == "1"


def test_unlinked_provenance_cannot_gain_first_citation_during_withdrawal(sql):
    setup_review_sources(sql)
    second = "00000000-0000-0000-0000-000000000005"
    sql(f"""
      INSERT INTO clinical_facts(id, patient_id, review_state, fact_type) VALUES ('{second}', '{PATIENT}', 'pending_review', 'obligation');
      INSERT INTO source_provenances VALUES ('{second}', NULL, 'clinician_entry', NULL);
    """)
    writer = sql.start(
        f"BEGIN; UPDATE source_provenances SET withdrawn_at=now() WHERE id='{second}';"
        " SELECT pg_sleep(1.5); COMMIT;",
        "unlinked-source-writer",
    )
    wait_for_session(sql, "unlinked-source-writer")
    error = sql(f"INSERT INTO evidence_citations VALUES ('{second}', '{second}')", succeeds=False)
    assert "retry the transaction" in error
    assert "deadlock" not in error.lower()
    finish_session(writer)
    assert sql(f"SELECT count(*) FROM evidence_citations WHERE fact_id='{second}'") == "0"


def test_null_old_or_new_patient_does_not_loop_on_insert_or_delete(sql):
    setup_review_sources(sql)
    second = "00000000-0000-0000-0000-000000000005"
    sql(f"""
      SET statement_timeout='2s';
      INSERT INTO clinical_facts(id, patient_id, review_state, fact_type) VALUES ('{second}', '{PATIENT}', 'pending_review', 'obligation');
      INSERT INTO documents VALUES ('{second}', '{PATIENT}', 'patient', 'pending', 'completed');
      INSERT INTO patients(id) VALUES ('{second}');
      INSERT INTO care_plan_versions(id,patient_id,version_number,source_watermark)
        VALUES ('{second}', '{second}', 1, '2026-10-02');
    """)
    assert sql(f"SELECT count(*) FROM clinical_facts WHERE id='{second}'") == "1"
    assert sql(f"SELECT count(*) FROM documents WHERE id='{second}'") == "1"
    assert sql(f"SELECT count(*) FROM care_plan_versions WHERE id='{second}'") == "1"
    sql(f"""
      SET statement_timeout='2s';
      DELETE FROM care_plan_versions WHERE id='{second}';
      DELETE FROM documents WHERE id='{second}';
      DELETE FROM clinical_facts WHERE id='{second}';
    """)
    assert sql(f"SELECT count(*) FROM clinical_facts WHERE id='{second}'") == "0"
    assert sql(f"SELECT count(*) FROM documents WHERE id='{second}'") == "0"
    assert sql(f"SELECT count(*) FROM care_plan_versions WHERE id='{second}'") == "0"


@pytest.mark.parametrize(
    "change", [None, "instructions", "schedule", "source", "inactive", "canonical", "rollback"]
)
def test_revision_preserves_only_exact_unchanged_activity_identity(sql, change) -> None:
    sql(
        batch(
            json.dumps(
                [
                    {
                        "source_fact_id": FACT,
                        "category": "movement",
                        "title": "Walk",
                        "instructions": "Synthetic walk",
                        "frequency": "daily",
                        "confidence_score": 1,
                    }
                ]
            )
        )
    )
    sql("UPDATE care_plan_items SET reviewed_locale='en-US'")
    sql(f"SELECT approve_care_plan_version('{PLAN}', '{PATIENT}', 'Synthetic review')")
    old_item = sql("SELECT id FROM care_plan_items")
    target = sql("SELECT id FROM obligations")
    sql(f"""
      CREATE TABLE synthetic_reminders(target_id uuid REFERENCES obligations(id), time text);
      CREATE TABLE synthetic_logs(target_id uuid REFERENCES obligations(id), item_id uuid, outcome text);
      INSERT INTO synthetic_reminders VALUES ('{target}', '08:00');
      INSERT INTO synthetic_logs VALUES ('{target}', '{old_item}', 'completed'),
                                        ('{target}', '{old_item}', 'schedule');
    """)
    new_plan = "00000000-0000-0000-0000-000000000007"
    sql(f"""
      INSERT INTO care_plan_versions(id,patient_id,version_number,source_watermark)
        VALUES ('{new_plan}', '{PATIENT}', 2, '2026-10-02T00:00:00Z');
      INSERT INTO care_plan_items(plan_version_id,source_fact_id,category,title,instructions,
                                 frequency,confidence_score,reviewed_locale)
        SELECT '{new_plan}',source_fact_id,category,title,instructions,frequency,
               confidence_score,reviewed_locale FROM care_plan_items WHERE id='{old_item}';
    """)
    if change == "instructions":
        sql(
            f"UPDATE care_plan_items SET instructions='Changed walk' WHERE plan_version_id='{new_plan}'"
        )
    elif change == "schedule":
        sql(
            f"UPDATE care_plan_items SET schedule='{{\"days\":[\"mon\"]}}' WHERE plan_version_id='{new_plan}'"
        )
    elif change == "source":
        sql(
            f"INSERT INTO clinical_facts(id, patient_id, review_state) VALUES ('{new_plan}', '{PATIENT}', 'pending_review')"
        )
        sql(
            f"UPDATE care_plan_items SET source_fact_id='{new_plan}' WHERE plan_version_id='{new_plan}'"
        )
    elif change == "inactive":
        sql("UPDATE obligations SET is_active=false")
    elif change == "canonical":
        sql("UPDATE obligations SET description='Changed canonical activity'")
    if change == "rollback":
        sql("UPDATE care_plan_generation_requests SET status='failed'")
        assert "generation must complete" in sql(
            f"SELECT approve_care_plan_version('{new_plan}', '{PATIENT}', 'Synthetic revision')",
            succeeds=False,
        )
        assert sql(f"SELECT status FROM care_plan_versions WHERE id='{PLAN}'") == "approved"
        assert (
            sql(f"SELECT care_plan_item_id FROM obligations WHERE id='{target}' AND is_active")
            == old_item
        )
        sql("UPDATE care_plan_generation_requests SET status='completed'")
    sql(f"SELECT approve_care_plan_version('{new_plan}', '{PATIENT}', 'Synthetic revision')")
    current = sql("SELECT id FROM obligations WHERE is_active")
    assert (current == target) is (change in (None, "rollback"))
    assert sql(f"SELECT status FROM care_plan_versions WHERE id='{PLAN}'") == "superseded"
    assert sql(f"SELECT projection_id FROM care_plan_items WHERE id='{old_item}'") == target
    assert sql("SELECT time FROM synthetic_reminders") == "08:00"
    assert sql(f"SELECT count(*) FROM synthetic_logs WHERE item_id='{old_item}'") == "2"
    assert sql(f"SELECT count(*) FROM synthetic_logs WHERE target_id='{current}'") == (
        "2" if change in (None, "rollback") else "0"
    )
    assert "only draft" in sql(
        f"UPDATE care_plan_items SET title='Rewritten' WHERE id='{old_item}'", succeeds=False
    )


@pytest.mark.parametrize("cadence", ["daily", "weekly"])
def test_overlap_guard_rolls_back_publication_and_preserves_sources(sql, cadence) -> None:
    second = "00000000-0000-0000-0000-000000000005"
    sql(
        f"INSERT INTO clinical_facts(id, patient_id, review_state) VALUES ('{second}', '{PATIENT}', 'pending_review')"
    )
    prepared = {
        "source_fact_id": FACT,
        "category": "movement",
        "title": "Walk",
        "instructions": "Walk 20 minutes",
        "frequency": "daily",
        "confidence_score": 1,
    }
    sql(
        batch(
            json.dumps(
                [
                    prepared,
                    {
                        **prepared,
                        "source_fact_id": second,
                        "title": "Another heading",
                        "frequency": cadence,
                    },
                ]
            )
        )
    )
    sql("UPDATE care_plan_items SET reviewed_locale='en-US'")
    old_plan = "00000000-0000-0000-0000-000000000006"
    sql(f"UPDATE care_plan_versions SET version_number=2 WHERE id='{PLAN}'")
    sql(
        f"INSERT INTO care_plan_versions(id, patient_id, version_number, source_watermark, status, approved_by, approved_at) "
        f"VALUES ('{old_plan}', '{PATIENT}', 1, '2026-09-01T00:00:00Z', 'approved', '{PATIENT}', now())"
    )
    error = sql(
        f"SELECT approve_care_plan_version('{PLAN}', '{PATIENT}', 'Synthetic review')",
        succeeds=False,
    )
    assert "overlapping" in error
    assert sql(f"SELECT status FROM care_plan_versions WHERE id='{PLAN}'") == "draft"
    assert sql(f"SELECT status FROM care_plan_versions WHERE id='{old_plan}'") == "approved"
    assert sql("SELECT count(*) FROM obligations") == "0"
    assert sql("SELECT count(*) FROM clinical_recommendations") == "0"
    assert sql("SELECT count(*) FROM care_plan_items") == "2"
    sql(f"UPDATE care_plan_items SET is_removed=true WHERE source_fact_id='{second}'")
    sql(f"SELECT approve_care_plan_version('{PLAN}', '{PATIENT}', 'Synthetic review')")
    assert sql("SELECT count(*) FROM obligations") == "1"
    assert sql("SELECT count(*) FROM clinical_facts") == "2"


def test_translated_duplicate_source_cannot_bypass_atomic_guard(sql) -> None:
    second = "00000000-0000-0000-0000-000000000005"
    sql(
        f"INSERT INTO clinical_facts(id, patient_id, review_state) VALUES ('{second}', '{PATIENT}', 'pending_review')"
    )
    sql(
        "UPDATE clinical_facts SET fact_type='obligation', value="
        '\'{"description":"Caminar 20 minutos","frequency":"daily"}\'::jsonb'
    )
    prepared = {
        "source_fact_id": FACT,
        "category": "movement",
        "title": "Walk",
        "instructions": "Walk 20 minutes",
        "frequency": "daily",
        "confidence_score": 1,
    }
    sql(
        batch(
            json.dumps(
                [
                    prepared,
                    {**prepared, "source_fact_id": second, "instructions": "Take a 20-minute walk"},
                ]
            )
        )
    )
    sql("UPDATE care_plan_items SET reviewed_locale='en-US'")
    assert "overlapping" in sql(
        f"SELECT approve_care_plan_version('{PLAN}', '{PATIENT}', 'Reviewed')", succeeds=False
    )
    assert sql("SELECT count(*) FROM obligations") == "0"


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


@pytest.mark.parametrize(
    "field,length", [("description", 338), ("instructions", 2001), ("frequency", 201)]
)
def test_oversized_evidence_commits_a_blocked_draft_against_real_constraints(
    sql, field: str, length: int
) -> None:
    medication = field == "instructions"
    fact = {
        "id": FACT,
        "fact_type": "medication" if medication else "obligation",
        "value": {
            "name": "Synthetic medication",
            "dosage": "1 mg",
            "route": "oral",
            "description": "Synthetic activity",
            "instructions": "Synthetic instruction",
            "frequency": "daily",
            field: "x" * length,
        },
        "confidence_score": 0.95,
    }
    prepared = CarePlanService(MagicMock())._item_from_fact(
        fact, category="medication" if medication else "monitoring", conflict={}
    )
    sql(batch(json.dumps([prepared])))
    assert sql("SELECT status FROM care_plan_generation_requests") == "completed"
    assert sql("SELECT count(*) FROM care_plan_items WHERE blocker_reason IS NOT NULL") == "1"
    sql("UPDATE care_plan_items SET reviewed_locale='en-US'")
    assert (
        "blockers must be resolved"
        in sql(
            f"SELECT approve_care_plan_version('{PLAN}', '{PATIENT}', 'Synthetic review')",
            succeeds=False,
        ).lower()
    )
    assert sql("SELECT status FROM care_plan_versions") == "draft"
    assert sql("SELECT count(*) FROM medications") == "0"
    assert sql("SELECT count(*) FROM obligations") == "0"


def test_bad_batch_rolls_back_items_audit_and_completion(sql) -> None:
    other = item(category="invented").replace(FACT, "00000000-0000-0000-0000-000000000005")
    sql(
        "INSERT INTO clinical_facts(id, patient_id, review_state) VALUES ('00000000-0000-0000-0000-000000000005',"
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
                "'approve_care_plan_version(uuid,uuid,text)', 'execute')"
            )
            == "f"
        )
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


def _authenticated_read(sql, actor: str, query: str) -> str:
    return sql(
        f"SET ROLE authenticated; SET request.jwt.claims='{json.dumps({'sub': actor})}'; {query}"
    )


def test_hardened_rls_allows_assigned_clinician_and_approved_plan_owner(sql) -> None:
    owner = "00000000-0000-0000-0000-000000000021"
    # A distinct owner avoids confusing the patient with the assigned clinician.
    sql(f"INSERT INTO public.patients(id) VALUES ('{owner}');")
    sql(f"UPDATE public.care_plan_versions SET patient_id='{owner}' WHERE id='{PLAN}';")
    sql(f"UPDATE public.clinical_facts SET patient_id='{owner}';")
    sql(f"UPDATE public.care_plan_generation_requests SET patient_id='{owner}';")
    sql(
        f"INSERT INTO public.care_teams(clinician_id,patient_id,status) VALUES ('{PATIENT}','{owner}','active');"
    )
    sql(
        batch(
            json.dumps(
                [
                    {
                        "source_fact_id": FACT,
                        "category": "movement",
                        "title": "Walk",
                        "instructions": "Synthetic walk",
                        "frequency": "daily",
                        "confidence_score": 1,
                    }
                ]
            )
        )
    )
    sql("UPDATE care_plan_items SET reviewed_locale='en-US'")
    sql(f"SELECT approve_care_plan_version('{PLAN}', '{PATIENT}', 'Synthetic review')")
    sql(
        f"INSERT INTO public.care_plan_versions(patient_id,version_number,source_watermark) VALUES ('{owner}',2,now());"
    )
    assert _authenticated_read(sql, owner, "SELECT count(*) FROM care_plan_versions") == "1"
    assert _authenticated_read(sql, owner, "SELECT count(*) FROM care_plan_items") == "1"
    assert _authenticated_read(sql, owner, "SELECT count(*) FROM care_plan_audit_events") == "0"
    assert (
        _authenticated_read(sql, owner, "SELECT count(*) FROM care_plan_generation_requests") == "0"
    )
    assert _authenticated_read(sql, PATIENT, "SELECT count(*) FROM care_plan_versions") == "2"
    assert _authenticated_read(sql, PATIENT, "SELECT count(*) FROM care_plan_items") == "1"
    assert int(_authenticated_read(sql, PATIENT, "SELECT count(*) FROM care_plan_audit_events")) > 0
    assert (
        _authenticated_read(sql, PATIENT, "SELECT count(*) FROM care_plan_generation_requests")
        == "1"
    )


@pytest.mark.parametrize("clinician", [False, True])
def test_hardened_rls_hides_all_care_plan_rows_from_outsiders(sql, clinician) -> None:
    outsider = "00000000-0000-0000-0000-000000000022"
    table = "clinicians" if clinician else "patients"
    sql(f"INSERT INTO public.{table}(id) VALUES ('{outsider}')")
    sql(batch(f"[{item()}]"))
    sql(
        "UPDATE care_plan_items SET instructions='Synthetic activity', frequency='daily', blocker_reason=NULL, reviewed_locale='en-US'"
    )
    sql(f"SELECT approve_care_plan_version('{PLAN}', '{PATIENT}', 'Synthetic review')")
    for resource in (
        "care_plan_versions",
        "care_plan_items",
        "care_plan_generation_requests",
        "care_plan_audit_events",
    ):
        assert int(sql(f"SELECT count(*) FROM {resource}")) > 0
        assert _authenticated_read(sql, outsider, f"SELECT count(*) FROM {resource}") == "0"
    if clinician:
        sql(
            f"INSERT INTO care_teams(patient_id,clinician_id,status) VALUES ('{PATIENT}','{outsider}','inactive')"
        )
        assert _authenticated_read(sql, outsider, "SELECT count(*) FROM care_plan_versions") == "0"


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_hardened_rls_has_no_browser_writes_or_public_helper_execution(sql, role) -> None:
    for resource in (
        "care_plan_versions",
        "care_plan_items",
        "care_plan_generation_requests",
        "care_plan_audit_events",
    ):
        for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            assert (
                sql(f"SELECT has_table_privilege('{role}','public.{resource}','{privilege}')")
                == "f"
            )
        error = sql(f"SET ROLE {role}; DELETE FROM public.{resource} WHERE false", succeeds=False)
        assert "permission denied for table" in error
    for helper in ("is_clinician()", "is_assigned_clinician(uuid)"):
        assert sql(f"SELECT has_function_privilege('{role}','public.{helper}','EXECUTE')") == "f"


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
