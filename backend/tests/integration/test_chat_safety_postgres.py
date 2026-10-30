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

from app.safety.triage_floor import FLOOR_RULE_URGENCY

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
        "010_chat_state_and_a2a_tasks.sql",
        "051_health_knowledge_and_chat_sessions.sql",
        "059_chat_safety_alerts.sql",
        "097_medication_error_safety_persistence.sql",
        "098_safety_audit_retention.sql",
        "104_model_escalation_delivery.sql",
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


def record_sql(
    *,
    patient=PATIENT,
    turn=TURN,
    content="Synthetic chest pain",
    rule="emergency_symptom_keyword",
    language="en-US",
    extra=None,
):
    payload = json.dumps(
        {
            **(extra or {}),
            "content": content,
            "session_id": "nora-safety-test",
            "language": language,
            "safety_rule": rule,
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
    assert first["user_message"]["session_id"] == "nora-safety-test"
    assert first["assistant_message"]["session_id"] == "nora-safety-test"
    assert sql("SELECT count(*) FROM chat_messages;") == "2"
    assert sql("SELECT count(*) FROM chat_safety_alerts;") == "1"
    assert sql("SELECT count(*) FROM symptom_reports;") == "0"
    assert sql("SELECT count(*) FROM adr_assessments;") == "0"
    sql(record_sql(content="Different synthetic payload"), succeeds=False)
    sql(record_sql(patient=OTHER), succeeds=False)
    sql(record_sql().replace("nora-safety-test", "another-conversation"), succeeds=False)


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


# ---------------------------------------------------------------------------
# SAFE-002: every rule the floor can emit is accepted, typed and alerted
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", ["en-US", "es-MX"])
@pytest.mark.parametrize("rule", sorted(FLOOR_RULE_URGENCY))
def test_every_floor_rule_is_saved_with_its_urgency_and_alerts_the_care_team(sql, rule, language):
    """The guard that would have caught urgent_medication_error being rejected."""
    saved = json.loads(sql(record_sql(rule=rule, language=language)))
    assert saved["urgency"] == FLOOR_RULE_URGENCY[rule]
    assert sql("SELECT count(*) FROM chat_messages;") == "2"
    assert sql("SELECT safety_rule || '/' || urgency FROM chat_safety_alerts;") == (
        f"{rule}/{FLOOR_RULE_URGENCY[rule]}"
    )
    sent = json.loads(sql(deliver_sql()))
    assert sent[0]["clinicians_notified"] == 1
    assert json.loads(sql(deliver_sql())) == []
    assert sql("SELECT count(*) FROM clinician_messages;") == "1"
    body = sql("SELECT body FROM clinician_messages;")
    if rule == "urgent_medication_error":
        assert "(urgent/medication_question)" in body
        assert "not an emergency alert" in body
        assert sql("SELECT subject FROM clinician_messages;").startswith("Same-day review")
        assert sql("SELECT intent FROM chat_messages WHERE role::text='assistant';") == (
            "medication_question"
        )
    else:
        assert "(emergency/" in body


def test_medication_error_retry_and_concurrency_create_one_alert(sql):
    first = sql.start(record_sql(rule="urgent_medication_error"))
    second = sql.start(record_sql(rule="urgent_medication_error"))
    for process in (first, second):
        assert process.wait(timeout=10) == 0, process.stderr.read()
    sql(record_sql(rule="urgent_medication_error"))
    assert sql("SELECT count(*) FROM chat_safety_alerts;") == "1"
    sql("SET ROLE service_role; SELECT public.deliver_chat_safety_alerts();")
    deliveries = [
        sql.start("SET ROLE service_role; SELECT public.deliver_chat_safety_alerts();")
        for _ in range(2)
    ]
    for process in deliveries:
        assert process.wait(timeout=10) == 0, process.stderr.read()
    assert sql("SELECT count(*) FROM clinician_messages;") == "1"


def test_unknown_rules_and_mismatched_urgency_are_rejected(sql):
    sql(record_sql(rule="not_a_floor_rule"), succeeds=False)
    sql(record_sql(rule="urgent_medication_error", extra={"urgency": "emergency"}), succeeds=False)
    sql(record_sql(rule="emergency_symptom_keyword", extra={"urgency": "urgent"}), succeeds=False)
    assert sql("SELECT count(*) FROM chat_safety_alerts;") == "0"
    sql(
        f"""
        INSERT INTO chat_messages(id, patient_id, content, role, language) VALUES
          ('{TURN}', '{PATIENT}', 'Synthetic', 'user', 'en-US'),
          ('{OTHER}', '{PATIENT}', 'Synthetic', 'assistant', 'en-US');
        INSERT INTO chat_safety_alerts(id, patient_id, source_message_id, assistant_message_id,
          safety_rule, urgency, rule_version)
          VALUES ('{TURN}', '{PATIENT}', '{TURN}', '{OTHER}', 'urgent_medication_error',
            'emergency', 'triage-floor/1');
        """,
        succeeds=False,
    )


def test_alert_urgency_is_immutable(sql):
    sql(record_sql(rule="urgent_medication_error"))
    sql("UPDATE chat_safety_alerts SET urgency='emergency';", succeeds=False)


def audit_sql(*, patient=PATIENT, turn=TURN, role="service_role", **fields):
    payload = {
        "safety_rule": "adverse_effect_signal",
        "rule_version": "triage-floor/1",
        "model_urgency": "routine",
        "final_urgency": "urgent",
        "outcome": "urgency_raised",
        "escalation_required": True,
        **fields,
    }
    body = json.dumps(payload).replace("'", "''")
    return (
        f"SET ROLE {role}; SELECT public.record_chat_turn_safety_audit('{patient}','{turn}',"
        f"'{body}'::jsonb);"
    )


def test_turn_audit_is_idempotent_typed_and_holds_no_message_text(sql):
    first = json.loads(sql(audit_sql()))
    again = json.loads(sql(audit_sql()))
    assert (
        first
        == again
        == {
            "turn_id": TURN,
            "safety_rule": "adverse_effect_signal",
            "outcome": "urgency_raised",
        }
    )
    assert sql("SELECT count(*) FROM chat_turn_safety_audits;") == "1"
    columns = sql(
        "SELECT string_agg(column_name, ',') FROM information_schema.columns "
        "WHERE table_name='chat_turn_safety_audits';"
    )
    assert "content" not in columns and "message" not in columns
    # Same turn id for a different patient is not an alias for someone else's audit.
    sql(audit_sql(patient=OTHER), succeeds=False)
    # An escalation the model chose itself.
    other_turn = "00000000-0000-0000-0000-000000000009"
    json.loads(
        sql(
            audit_sql(
                turn=other_turn,
                safety_rule="model_classification",
                model_urgency="urgent",
                outcome="model_escalated",
            )
        )
    )
    assert sql("SELECT count(*) FROM chat_turn_safety_audits;") == "2"


@pytest.mark.parametrize(
    "fields",
    [
        {"safety_rule": "invented_rule"},
        {"outcome": "something_else"},
        {"final_urgency": "routine"},
        {"model_urgency": "urgent"},  # urgency_raised requires the urgency to differ
        {"rule_version": "triage-floor/2"},
        {"outcome": "model_escalated", "model_urgency": "urgent"},  # needs model_classification
    ],
)
def test_invalid_audit_is_rejected(sql, fields):
    sql(audit_sql(**fields), succeeds=False)
    assert sql("SELECT count(*) FROM chat_turn_safety_audits;") == "0"


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_audit_is_backend_only_and_immutable(sql, role):
    sql(audit_sql())
    sql(audit_sql(role=role, turn=OTHER), succeeds=False)
    sql(f"SET ROLE {role}; SELECT * FROM chat_turn_safety_audits;", succeeds=False)
    sql("SET ROLE service_role; SELECT * FROM chat_turn_safety_audits;", succeeds=False)
    sql("UPDATE chat_turn_safety_audits SET final_urgency='emergency';", succeeds=False)
    sql("DELETE FROM chat_turn_safety_audits;", succeeds=False)


def test_migration_097_reapplies_cleanly_without_losing_alerts(sql):
    sql(record_sql(rule="urgent_medication_error"))
    sql((MIGRATIONS / "097_medication_error_safety_persistence.sql").read_text())
    assert sql("SELECT safety_rule || '/' || urgency FROM chat_safety_alerts;") == (
        "urgent_medication_error/urgent"
    )


def _seed_audits(sql, *, age: str, count: int) -> None:
    sql(
        f"INSERT INTO chat_turn_safety_audits(turn_id, patient_id, safety_rule, rule_version,"
        f" model_urgency, final_urgency, outcome, escalation_required, evaluated_at)"
        f" SELECT gen_random_uuid(), '{PATIENT}', 'adverse_effect_signal', 'triage-floor/1',"
        f" 'routine', 'urgent', 'urgency_raised', true, clock_timestamp() - interval '{age}'"
        f" FROM generate_series(1, {count});"
    )


def _purge(sql, limit=500):
    return sql(f"SET ROLE service_role; SELECT public.purge_chat_turn_safety_audits({limit});")


def test_retention_deletes_only_rows_older_than_365_days(sql):
    _seed_audits(sql, age="400 days", count=3)
    _seed_audits(sql, age="364 days", count=1)
    _seed_audits(sql, age="1 day", count=1)
    assert _purge(sql) == "3"
    assert sql("SELECT count(*) FROM chat_turn_safety_audits;") == "2"
    assert _purge(sql) == "0"


def test_retention_deletes_in_batches_of_at_most_500(sql):
    _seed_audits(sql, age="400 days", count=501)
    assert _purge(sql) == "500"
    assert sql("SELECT count(*) FROM chat_turn_safety_audits;") == "1"
    assert _purge(sql) == "1"
    for bad in ("0", "501", "NULL"):
        sql(
            f"SET ROLE service_role; SELECT public.purge_chat_turn_safety_audits({bad});",
            succeeds=False,
        )


def test_retention_does_not_loosen_immutability_or_grants(sql):
    _seed_audits(sql, age="400 days", count=1)
    # Even an expired row cannot be deleted or edited outside the purge function.
    sql("DELETE FROM chat_turn_safety_audits;", succeeds=False)
    sql("UPDATE chat_turn_safety_audits SET final_urgency='emergency';", succeeds=False)
    for role in ("anon", "authenticated"):
        sql(f"SET ROLE {role}; SELECT public.purge_chat_turn_safety_audits(1);", succeeds=False)
        sql(f"SET ROLE {role}; DELETE FROM chat_turn_safety_audits;", succeeds=False)
    sql("SET ROLE service_role; DELETE FROM chat_turn_safety_audits;", succeeds=False)
    assert sql("SELECT count(*) FROM chat_turn_safety_audits;") == "1"
    # The flag is transaction-local: a purge does not leave later deletes unlocked.
    _seed_audits(sql, age="400 days", count=1)
    assert _purge(sql, 1) == "1"
    sql("DELETE FROM chat_turn_safety_audits;", succeeds=False)
    assert sql("SELECT count(*) FROM chat_turn_safety_audits;") == "1"


def test_a_new_audit_write_runs_the_retention_pass_and_stays_idempotent(sql):
    _seed_audits(sql, age="400 days", count=2)
    first = json.loads(sql(audit_sql()))
    assert first["safety_rule"] == "adverse_effect_signal"
    assert sql("SELECT count(*) FROM chat_turn_safety_audits;") == "1"
    json.loads(sql(audit_sql()))
    assert sql("SELECT count(*) FROM chat_turn_safety_audits;") == "1"


def test_migration_098_reapplies_cleanly(sql):
    sql(audit_sql())
    sql((MIGRATIONS / "098_safety_audit_retention.sql").read_text())
    assert sql("SELECT count(*) FROM chat_turn_safety_audits;") == "1"


def model_alert_sql(*, patient=PATIENT, reply=None, rule="model_classification", urgency="urgent"):
    if reply is None:
        reply = "00000000-0000-0000-0000-000000000005"
    payload = json.dumps(
        {
            "assistant_message_id": reply,
            "safety_rule": rule,
            "urgency": urgency,
            "rule_version": "triage-floor/1",
        }
    )
    return f"SET ROLE service_role; SELECT record_model_chat_safety_alert('{patient}','{TURN}','{payload}');"


def seed_model_turn(sql, *, session="default", patient=PATIENT):
    sql(f"""INSERT INTO chat_messages(id,patient_id,role,content,session_id)
      VALUES('{TURN}','{PATIENT}','user','Synthetic symptom','default'),
      ('00000000-0000-0000-0000-000000000005','{patient}','assistant','Synthetic guidance','{session}');""")


@pytest.mark.parametrize("urgency", ["urgent", "emergency"])
@pytest.mark.parametrize("rule", ["model_classification", "adverse_effect_signal"])
def test_model_escalation_is_durable_idempotent_and_retryable(sql, rule, urgency):
    seed_model_turn(sql)
    saved = json.loads(sql(model_alert_sql(rule=rule, urgency=urgency)))
    assert saved["delivery_state"] == "pending"
    assert saved["urgency"] == urgency
    sql(model_alert_sql(rule=rule, urgency=urgency))
    assert sql("SELECT count(*) FROM chat_safety_alerts;") == "1"
    sql("""CREATE FUNCTION public.fail_model_delivery() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'Synthetic delivery outage'; END $$;
      CREATE TRIGGER fail_model_delivery BEFORE INSERT ON clinician_messages
        FOR EACH ROW EXECUTE FUNCTION public.fail_model_delivery();""")
    sql(deliver_sql(), succeeds=False)
    assert sql("SELECT delivery_state FROM chat_safety_alerts;") == "pending"
    sql("DROP TRIGGER fail_model_delivery ON clinician_messages;")
    assert json.loads(sql(deliver_sql()))[0]["delivery_state"] == "delivered"
    assert json.loads(sql(deliver_sql())) == []
    assert sql("SELECT count(*) FROM clinician_messages;") == "1"
    assert f"({urgency}/" in sql("SELECT body FROM clinician_messages;")
    sql(model_alert_sql(rule=rule, urgency=urgency))
    assert sql("SELECT count(*) FROM chat_messages;") == "2"
    sql("UPDATE chat_messages SET content='changed' WHERE role::text='user';", succeeds=False)


@pytest.mark.parametrize("session,patient", [("other", PATIENT), ("default", OTHER)])
def test_model_alert_rejects_cross_patient_or_session_reply(sql, session, patient):
    seed_model_turn(sql, session=session, patient=patient)
    sql(model_alert_sql(), succeeds=False)
    assert sql("SELECT count(*) FROM chat_safety_alerts;") == "0"


def test_model_alert_rejects_identity_changes_and_browser_writes(sql):
    seed_model_turn(sql)
    sql(model_alert_sql())
    sql(model_alert_sql(urgency="emergency"), succeeds=False)
    sql(model_alert_sql(patient=OTHER), succeeds=False)
    sql(model_alert_sql(rule="unknown"), succeeds=False)
    sql(
        "SET ROLE authenticated; SELECT record_model_chat_safety_alert(NULL,NULL,'{}');",
        succeeds=False,
    )


def test_model_alert_concurrent_registration_and_dispatch_do_not_duplicate(sql):
    seed_model_turn(sql)
    for statement in (model_alert_sql(), deliver_sql()):
        children = [sql.start(statement), sql.start(statement)]
        for child in children:
            assert child.wait(timeout=10) == 0, child.stderr.read()
    assert sql("SELECT count(*) FROM chat_safety_alerts;") == "1"
    assert sql("SELECT count(*) FROM clinician_messages;") == "1"
