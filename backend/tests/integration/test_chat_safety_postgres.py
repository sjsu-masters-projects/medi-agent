"""Opt-in disposable PostgreSQL checks (native or Docker); no configured DB URLs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CHAT_SAFETY_TEST_POSTGRES") != "1",
    reason="explicit opt-in disposable PostgreSQL safety check",
)
MIGRATIONS = Path(__file__).resolve().parents[2] / "src/app/db/migrations"
PATIENT = "00000000-0000-0000-0000-000000000001"
CLINICIAN = "00000000-0000-0000-0000-000000000002"
OTHER = "00000000-0000-0000-0000-000000000003"
TURN = "00000000-0000-0000-0000-000000000004"


@pytest.fixture(scope="module")
def postgres(tmp_path_factory):
    if os.environ.get("CHAT_SAFETY_TEST_POSTGRES_DOCKER") == "1":
        yield from _docker_postgres()
        return
    programs = {name: shutil.which(name) for name in ("initdb", "pg_ctl", "psql")}
    if not all(programs.values()):
        pytest.fail("Native initdb, pg_ctl and psql are required for the opt-in SQL check")
    root = tmp_path_factory.mktemp("chat-safety-pg")
    data = root / "data"
    with tempfile.TemporaryDirectory(prefix="safety-pg-", dir="/tmp") as sockets:
        initialized = subprocess.run(
            [programs["initdb"], "-D", str(data), "-A", "trust"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert initialized.returncode == 0, initialized.stderr
        started = False
        try:
            startup = subprocess.run(
                [
                    programs["pg_ctl"],
                    "-D",
                    str(data),
                    "-l",
                    str(root / "server.log"),
                    "-o",
                    f"-k {sockets} -h ''",
                    "-w",
                    "start",
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            assert startup.returncode == 0, startup.stderr + (root / "server.log").read_text()
            started = True
            command = [
                programs["psql"],
                "-h",
                sockets,
                "-X",
                "-d",
                "postgres",
                "-Atq",
                "-v",
                "ON_ERROR_STOP=1",
            ]
            subprocess.run(
                command,
                input="CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;",
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            yield command
        finally:
            if started:
                subprocess.run(
                    [programs["pg_ctl"], "-D", str(data), "-m", "immediate", "-w", "stop"],
                    capture_output=True,
                    check=True,
                    timeout=15,
                )


def _docker_postgres():
    docker = shutil.which("docker")
    if not docker:
        pytest.fail("Docker and cached official postgres:16-alpine required")
    name = "mediagent-chat-safety-test-" + uuid4().hex
    subprocess.run(
        [
            docker,
            "run",
            "--detach",
            "--pull=never",
            "--network=none",
            "--name",
            name,
            "--env",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "postgres:16-alpine",
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
                    name,
                    "sh",
                    "-c",
                    'test "$(head -n 1 /var/lib/postgresql/data/postmaster.pid)" = 1 && pg_isready -U postgres',
                ],
                capture_output=True,
                timeout=5,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.1)
        else:
            pytest.fail("Disposable PostgreSQL container did not become ready")
        command = [
            docker,
            "exec",
            "--interactive",
            name,
            "psql",
            "-U",
            "postgres",
            "-X",
            "-Atq",
            "-v",
            "ON_ERROR_STOP=1",
        ]
        subprocess.run(
            command,
            input="CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;",
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        yield command
    finally:
        subprocess.run([docker, "rm", "--force", name], check=True, capture_output=True, timeout=15)


@pytest.fixture
def sql(postgres):
    database = "safety_" + uuid4().hex
    subprocess.run(
        postgres,
        input=f"CREATE DATABASE {database};",
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    command = postgres + ["-d", database]
    children = []

    def execute(statement, *, succeeds=True):
        result = subprocess.run(
            command,
            input="SET statement_timeout='8s';\n" + statement,
            capture_output=True,
            text=True,
            timeout=12,
        )
        assert (result.returncode == 0) is succeeds, result.stderr
        return result.stdout.strip() if succeeds else result.stderr

    def start(statement):
        child = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        children.append(child)
        child.stdin.write("SET statement_timeout='8s';\n" + statement)
        child.stdin.close()
        return child

    execute.start = start
    execute("""
        CREATE SCHEMA auth;
        CREATE TABLE auth.users(id uuid PRIMARY KEY);
        CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT null::uuid $$;
        CREATE SCHEMA private;
    """)
    for name in (
        "001_initial_schema.sql",
        "002_rls_policies.sql",
        "006_care_team_invite_compat.sql",
        "007_clinic_identity_foundation.sql",
        "051_health_knowledge_and_chat_sessions.sql",
        "059_chat_safety_alerts.sql",
    ):
        execute((MIGRATIONS / name).read_text())
    execute(f"""
        INSERT INTO auth.users VALUES ('{PATIENT}'),('{CLINICIAN}'),('{OTHER}');
        INSERT INTO patients(id,email,first_name,last_name,date_of_birth) VALUES
          ('{PATIENT}','one@synthetic.invalid','Synthetic','Patient','1960-01-01'),
          ('{OTHER}','other@synthetic.invalid','Other','Patient','1960-01-01');
        INSERT INTO clinicians(id,email,first_name,last_name,specialty,clinic_name) VALUES
          ('{CLINICIAN}','reviewer@synthetic.invalid','Synthetic','Reviewer','Synthetic','Synthetic');
        INSERT INTO care_teams(patient_id,clinician_id,role,status)
          VALUES ('{PATIENT}','{CLINICIAN}','primary','active');
    """)
    try:
        yield execute
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)


def record_sql(*, patient=PATIENT, turn=TURN, content="Synthetic chest pain"):
    payload = json.dumps(
        {
            "content": content,
            "language": "en-US",
            "safety_rule": "emergency_symptom_keyword",
            "rule_version": "triage-floor/1",
            "response_text": "Synthetic SQL-only response fixture",
        }
    ).replace("'", "''")
    return f"SET ROLE service_role; SELECT public.record_chat_safety_turn('{patient}','{turn}','{payload}'::jsonb);"


def deliver_sql():
    return "SET ROLE service_role; SELECT public.deliver_chat_safety_alerts();"


def test_record_atomic_retry_and_no_report_or_adr(sql):
    first = json.loads(sql(record_sql()))
    again = json.loads(sql(record_sql()))
    assert first == again
    assert first["user_message"]["id"] == TURN
    assert sql("SELECT count(*) FROM chat_messages;") == "2"
    assert sql("SELECT count(*) FROM chat_safety_alerts;") == "1"
    assert sql("SELECT count(*) FROM symptom_reports;") == "0"
    assert sql("SELECT count(*) FROM adr_assessments;") == "0"
    sql(record_sql(content="Different synthetic payload"), succeeds=False)
    sql(record_sql(patient=OTHER), succeeds=False)


def test_dispatch_failure_retains_pending_and_atomic_retry_deduplicates(sql):
    sql(record_sql())
    sql("""
        CREATE FUNCTION public.synthetic_failure() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN RAISE EXCEPTION 'Synthetic dispatch failure'; END $$;
        CREATE TRIGGER synthetic_failure BEFORE INSERT ON clinician_messages
          FOR EACH ROW EXECUTE FUNCTION public.synthetic_failure();
    """)
    sql(deliver_sql(), succeeds=False)
    assert sql("SELECT delivery_state FROM chat_safety_alerts;") == "pending"
    assert sql("SELECT count(*) FROM clinician_messages;") == "0"
    sql("DROP TRIGGER synthetic_failure ON clinician_messages;")
    sent = json.loads(sql(deliver_sql()))
    assert sent[0]["clinicians_notified"] == 1
    assert sent[0]["delivery_state"] == "delivered"
    assert json.loads(sql(deliver_sql())) == []
    assert sql("SELECT count(*) FROM clinician_messages;") == "1"


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_browser_read_write_and_rpc_denial(sql, role):
    sql(record_sql())
    sql(f"SET ROLE {role}; SELECT * FROM chat_safety_alerts;", succeeds=False)
    sql(
        f"SET ROLE {role}; UPDATE chat_safety_alerts SET delivery_state='delivered';",
        succeeds=False,
    )
    sql(record_sql().replace("ROLE service_role", f"ROLE {role}"), succeeds=False)
    sql(deliver_sql().replace("ROLE service_role", f"ROLE {role}"), succeeds=False)


def test_reassignment_at_dispatch_and_immutable_safety_evidence(sql):
    sql(record_sql())
    sql("UPDATE care_teams SET status='inactive';")
    assert json.loads(sql(deliver_sql()))[0]["delivery_state"] == "no_recipients"
    assert sql("SELECT count(*) FROM clinician_messages;") == "0"
    sql(
        "UPDATE chat_safety_alerts SET safety_rule='emergency_mental_health_keyword';",
        succeeds=False,
    )
    sql("DELETE FROM chat_safety_alerts;", succeeds=False)
    sql("UPDATE chat_messages SET content='Changed' WHERE role::text='user';", succeeds=False)
    sql("UPDATE chat_messages SET content='Changed' WHERE role::text='assistant';", succeeds=False)
    sql("SET ROLE service_role; SELECT * FROM chat_safety_alerts;", succeeds=False)


def test_record_failure_rolls_back_messages_and_event(sql):
    sql("""
        CREATE FUNCTION public.synthetic_failure() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN RAISE EXCEPTION 'Synthetic event failure'; END $$;
        CREATE TRIGGER synthetic_failure BEFORE INSERT ON chat_safety_alerts
          FOR EACH ROW EXECUTE FUNCTION public.synthetic_failure();
    """)
    sql(record_sql(), succeeds=False)
    assert sql("SELECT count(*) FROM chat_messages;") == "0"
    assert sql("SELECT count(*) FROM chat_safety_alerts;") == "0"


def test_concurrent_dispatch_creates_one_alert(sql):
    sql(record_sql())
    first = sql.start(deliver_sql())
    second = sql.start(deliver_sql())
    for process in (first, second):
        assert process.wait(timeout=10) == 0, process.stderr.read()
    assert sql("SELECT count(*) FROM clinician_messages;") == "1"


def test_concurrent_record_reuses_one_turn(sql):
    first = sql.start(record_sql())
    second = sql.start(record_sql())
    for process in (first, second):
        assert process.wait(timeout=10) == 0, process.stderr.read()
    assert sql("SELECT count(*) FROM chat_messages;") == "2"
    assert sql("SELECT count(*) FROM chat_safety_alerts;") == "1"
