"""Opt-in, isolated PostgreSQL 16 container contract tests; no network or remote DB."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest

from tests.integration.supabase_roles import create_roles_sql

pytestmark = pytest.mark.skipif(
    os.environ.get("CARE_CONVERSATION_TEST_POSTGRES_DOCKER") != "1",
    reason="explicitly opt-in disposable Docker PostgreSQL contract check",
)
MIGRATION = (
    Path(__file__).resolve().parents[2] / "src/app/db/migrations/048_care_team_conversations.sql"
)
PATIENT = "00000000-0000-0000-0000-000000000001"
CLINICIAN = "00000000-0000-0000-0000-000000000002"
OTHER = "00000000-0000-0000-0000-000000000003"
FOREIGN = "00000000-0000-0000-0000-000000000004"
TEAM = "00000000-0000-0000-0000-000000000005"
OTHER_TEAM = "00000000-0000-0000-0000-000000000006"
CLINIC = "00000000-0000-0000-0000-000000000007"
OTHER_CLINIC = "00000000-0000-0000-0000-000000000008"


@pytest.fixture(scope="module")
def postgres():
    docker = shutil.which("docker")
    if not docker:
        pytest.fail("Docker and cached postgres:16 required for opt-in database checks")
    container = f"mediagent-conversation-test-{uuid4().hex}"
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
            command,
            input=create_roles_sql(),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        yield command
    finally:
        subprocess.run(
            [docker, "rm", "--force", container], check=True, capture_output=True, timeout=15
        )


@pytest.fixture
def sql(postgres):
    database = "conversation_" + uuid4().hex
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

    def start(statement, name):
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        children.append(process)
        process.stdin.write(
            f"SET statement_timeout='8s'; SET application_name='{name}';\n{statement}"
        )
        process.stdin.close()
        return process

    execute.start = start
    try:
        # Auth is a platform prerequisite; application tables/grants come from
        # the actual migrations rather than permissive handwritten stand-ins.
        execute("""
          CREATE SCHEMA auth;
          CREATE TABLE auth.users(id uuid PRIMARY KEY);
          CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT null::uuid $$;
        """)
        for name in (
            "001_initial_schema.sql",
            "002_rls_policies.sql",
            "006_care_team_invite_compat.sql",
            "007_clinic_identity_foundation.sql",
        ):
            execute((MIGRATION.parent / name).read_text())
        # Remaining 020 sections depend on unrelated storage/vector/Auth-hook
        # platform objects. Load its real private-helper bootstrap unchanged.
        hardening = (MIGRATION.parent / "020_harden_database_security.sql").read_text()
        execute(hardening.split("-- Public helper functions remain")[0])
        execute((MIGRATION.parent / "022_grant_service_role_seed_access.sql").read_text())
        execute(MIGRATION.read_text())
        # Clinic memberships (065, CLN-003 slice A): the rows below go through its triggers.
        for path in sorted(MIGRATION.parent.glob("*_clinic_memberships.sql")):
            execute(path.read_text())
        # CLN-003 slice B (066): conversations take the care-team link's clinic. Its last two
        # sections replace invitation and notification functions this fixture does not install.
        for path in sorted(MIGRATION.parent.glob("*_clinic_sign_in_once.sql")):
            execute(path.read_text().split("-- ── 6. Invitations")[0])
        execute(f"""
          INSERT INTO auth.users VALUES ('{PATIENT}'),('{CLINICIAN}'),('{OTHER}'),('{FOREIGN}');
          INSERT INTO patients(id,email,first_name,last_name,date_of_birth) VALUES
            ('{PATIENT}','patient@synthetic.invalid','Synthetic','Patient','1960-01-01'),
            ('{FOREIGN}','foreign@synthetic.invalid','Foreign','Patient','1960-01-01');
          INSERT INTO clinics(id,display_name,canonical_name) VALUES
            ('{CLINIC}','Synthetic clinic','synthetic clinic'),('{OTHER_CLINIC}','Second clinic','second clinic');
          INSERT INTO clinicians(id,email,first_name,last_name,specialty,clinic_name,clinic_id) VALUES
            ('{CLINICIAN}','one@synthetic.invalid','Synthetic','Clinician','Synthetic','Synthetic clinic','{CLINIC}'),
            ('{OTHER}','two@synthetic.invalid','Second','Clinician','Synthetic','Second clinic','{OTHER_CLINIC}');
          INSERT INTO care_teams(id,patient_id,clinician_id,role,status) VALUES
            ('{TEAM}','{PATIENT}','{CLINICIAN}','primary_care','active'),
            ('{OTHER_TEAM}','{PATIENT}','{OTHER}','primary_care','active');
        """)
        yield execute
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)


def operation(action, payload=None, *, actor=PATIENT, role="patient"):
    encoded = json.dumps(payload or {}).replace("'", "''")
    return f"SET ROLE service_role; SELECT public.care_conversation_operation('{actor}','{role}','{action}','{encoded}'::jsonb);"


def call(sql, action, payload=None, **actor):
    return json.loads(sql(operation(action, payload, **actor)))


def open_thread(sql, recipient=CLINICIAN):
    return call(sql, "open", {"recipient_id": recipient})


def send(sql, thread, body="Synthetic message", key=None, **actor):
    return call(
        sql,
        "send",
        {"conversation_id": thread["id"], "body": body, "client_message_id": key or str(uuid4())},
        **actor,
    )


def wait_event(sql, name, event):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if (
            sql(
                f"SELECT count(*) FROM pg_stat_activity WHERE application_name='{name}' AND wait_event{'' if event == 'PgSleep' else '_type'}='{event}'"
            )
            == "1"
        ):
            return
        time.sleep(0.03)
    pytest.fail(f"Session {name} did not reach expected {event} wait")


def finish(process, *, succeeds=True):
    process.wait(timeout=10)
    out, err = process.stdout.read(), process.stderr.read()
    assert (process.returncode == 0) is succeeds, err
    return out if succeeds else err


def test_two_way_sender_clinic_and_partition(sql):
    first, second = open_thread(sql), open_thread(sql, OTHER)
    assert first["id"] != second["id"]
    assert {r["clinic_name"] for r in call(sql, "recipients")} == {
        "Synthetic clinic",
        "Second clinic",
    }
    a = send(sql, first, "  Patient reply\n")
    b = send(sql, first, "Clinician reply", actor=CLINICIAN, role="clinician")
    assert (
        a["sender_id"] == PATIENT
        and a["sender_name"] == "Synthetic Patient"
        and a["body"] == "Patient reply"
    )
    assert b["sender_id"] == CLINICIAN and b["sender_role"] == "clinician"
    assert [m["id"] for m in call(sql, "messages", {"conversation_id": first["id"]})["items"]] == [
        a["id"],
        b["id"],
    ]
    assert [t["id"] for t in call(sql, "list", actor=CLINICIAN, role="clinician")] == [first["id"]]
    denied = sql(
        operation("messages", {"conversation_id": first["id"]}, actor=OTHER, role="clinician"),
        succeeds=False,
    )
    assert "Conversation unavailable" in denied
    assert call(sql, "list", actor=FOREIGN) == []
    assert call(sql, "recipients", actor=FOREIGN) == []


def test_same_clinic_clinicians_still_have_separate_private_threads(sql):
    # Since 066 a thread belongs to the care-team link's clinic: move the clinician and the
    # link to the first clinic.
    sql(f"UPDATE clinicians SET clinic_id='{CLINIC}' WHERE id='{OTHER}';")
    sql(f"UPDATE care_teams SET clinic_id='{CLINIC}' WHERE id='{OTHER_TEAM}';")
    first, second = open_thread(sql), open_thread(sql, OTHER)
    assert first["id"] != second["id"]
    assert first["clinic_name"] == second["clinic_name"] == "Synthetic clinic"
    send(sql, first, "For the first clinician only")
    send(sql, second, "For the second clinician only")
    assert [t["id"] for t in call(sql, "list", actor=CLINICIAN, role="clinician")] == [first["id"]]
    assert [t["id"] for t in call(sql, "list", actor=OTHER, role="clinician")] == [second["id"]]
    denied = sql(
        operation("messages", {"conversation_id": first["id"]}, actor=OTHER, role="clinician"),
        succeeds=False,
    )
    assert "Conversation unavailable" in denied


def test_actual_prerequisite_schema_and_assignment_compatibility(sql):
    assert (
        sql(
            "SELECT udt_name FROM information_schema.columns WHERE table_name='care_teams' AND column_name='status'"
        )
        == "care_team_status_enum"
    )
    assert (
        sql(
            "SELECT udt_name FROM information_schema.columns WHERE table_name='clinicians' AND column_name='role'"
        )
        == "clinician_role_enum"
    )
    assert (
        sql(
            "SELECT count(*) FROM pg_class WHERE relname IN ('patients','clinicians','care_teams') AND relrowsecurity"
        )
        == "3"
    )
    assert sql("SELECT has_table_privilege('service_role','care_teams','UPDATE')") == "t"
    sql(f"""
      UPDATE clinicians SET role='nurse' WHERE id='{OTHER}';
      INSERT INTO care_teams(clinician_id,role,status) VALUES ('{CLINICIAN}','provider','pending');
    """)
    recipients = call(sql, "recipients")
    assert {r["id"] for r in recipients} == {CLINICIAN, OTHER}
    assert {r["role"] for r in recipients} == {"provider", "nurse"}
    assert {r["id"] for r in call(sql, "recipients", actor=CLINICIAN, role="clinician")} == {
        PATIENT
    }
    sql(f"UPDATE clinicians SET clinic_id=NULL WHERE id='{CLINICIAN}';")
    assert {r["id"] for r in call(sql, "recipients")} == {OTHER}
    assert "Conversation unavailable" in sql(
        operation("open", {"recipient_id": CLINICIAN}), succeeds=False
    )


@pytest.mark.parametrize("change", ["patient", "clinician", "clinic"])
def test_new_authorized_binding_opens_without_old_history(sql, change):
    old = open_thread(sql)
    old_message = send(sql, old, "Preserved old-binding history")
    patient, clinician = PATIENT, CLINICIAN
    if change == "patient":
        sql(f"UPDATE care_teams SET patient_id='{FOREIGN}' WHERE id='{TEAM}';")
        patient = FOREIGN
    elif change == "clinician":
        sql(
            f"DELETE FROM care_teams WHERE id='{OTHER_TEAM}'; UPDATE care_teams SET clinician_id='{OTHER}' WHERE id='{TEAM}';"
        )
        clinician = OTHER
    else:
        move_link_to_other_clinic(sql)
    opened = call(sql, "open", {"recipient_id": clinician}, actor=patient)
    assert opened["id"] != old["id"]
    assert opened["unread_count"] == 0 and opened["last_message_preview"] is None
    assert (
        call(sql, "open", {"recipient_id": patient}, actor=clinician, role="clinician")["id"]
        == opened["id"]
    )
    assert call(sql, "open", {"recipient_id": clinician}, actor=patient)["id"] == opened["id"]
    assert call(sql, "messages", {"conversation_id": opened["id"]}, actor=patient)["items"] == []
    for actor, role in {
        (PATIENT, "patient"),
        (CLINICIAN, "clinician"),
        (patient, "patient"),
        (clinician, "clinician"),
    }:
        assert old["id"] not in {t["id"] for t in call(sql, "list", actor=actor, role=role)}
        assert "Conversation unavailable" in sql(
            operation("messages", {"conversation_id": old["id"]}, actor=actor, role=role),
            succeeds=False,
        )
        assert "Conversation unavailable" in sql(
            operation(
                "read",
                {"conversation_id": old["id"], "last_message_id": old_message["id"]},
                actor=actor,
                role=role,
            ),
            succeeds=False,
        )
        assert "Conversation unavailable" in sql(
            operation(
                "send",
                {
                    "conversation_id": old["id"],
                    "body": "Must not transfer",
                    "client_message_id": str(uuid4()),
                },
                actor=actor,
                role=role,
            ),
            succeeds=False,
        )
    reply = send(sql, opened, "New-binding message", actor=patient)
    assert call(
        sql, "messages", {"conversation_id": opened["id"]}, actor=clinician, role="clinician"
    )["items"] == [reply]
    assert (
        sql(f"SELECT body FROM care_conversation_messages WHERE id='{old_message['id']}'")
        == "Preserved old-binding history"
    )
    assert (
        sql(
            f"SELECT count(*) FROM care_conversation_audit_events WHERE conversation_id='{old['id']}'"
        )
        == "2"
    )


def move_link_to_other_clinic(sql):
    """The clinician also works at the second clinic, and the link moves there (066)."""
    sql(
        "INSERT INTO clinic_memberships(clinician_id,clinic_id,role) "
        f"VALUES('{CLINICIAN}','{OTHER_CLINIC}','provider');"
    )
    sql(f"UPDATE care_teams SET clinic_id='{OTHER_CLINIC}' WHERE id='{TEAM}';")


def test_concurrent_open_after_clinic_reassignment_creates_one_binding(sql):
    old = open_thread(sql)
    move_link_to_other_clinic(sql)
    stmt = operation("open", {"recipient_id": CLINICIAN})
    a = sql.start(f"BEGIN; {stmt} SELECT pg_sleep(1.5); COMMIT;", "first")
    wait_event(sql, "first", "PgSleep")
    b = sql.start(stmt, "second")
    wait_event(sql, "second", "Lock")
    finish(a)
    finish(b)
    assert sql(f"SELECT count(*) FROM care_conversations WHERE care_team_id='{TEAM}'") == "2"
    assert len(call(sql, "list")) == 1 and call(sql, "list")[0]["id"] != old["id"]
    assert sql("SELECT count(*) FROM care_conversation_audit_events WHERE action='opened'") == "2"


def test_open_and_send_are_idempotent_with_one_audit(sql):
    thread = open_thread(sql)
    assert open_thread(sql)["id"] == thread["id"]
    key = str(uuid4())
    first = send(sql, thread, key=key)
    assert send(sql, thread, " Synthetic message ", key) == first
    assert sql("SELECT count(*) FROM care_conversation_messages") == "1"
    assert sql("SELECT count(*) FROM care_conversation_audit_events WHERE action='sent'") == "1"
    assert sql("SELECT count(*) FROM care_conversation_audit_events WHERE action='opened'") == "1"


def test_inbox_orders_latest_activity_then_stable_id_with_null_last(sql):
    first, second = open_thread(sql), open_thread(sql, OTHER)
    send(sql, second, "Recent second thread")
    assert [t["id"] for t in call(sql, "list")] == [second["id"], first["id"]]
    send(sql, first, "Newer first thread")
    assert [t["id"] for t in call(sql, "list")] == [first["id"], second["id"]]
    sql("UPDATE care_conversations SET last_message_at='2026-10-09T12:00:00Z'")
    tied = sorted([first["id"], second["id"]])
    assert [t["id"] for t in call(sql, "list")] == tied
    sql("UPDATE care_conversations SET last_message_at=NULL")
    assert [t["id"] for t in call(sql, "list")] == tied


@pytest.mark.parametrize("changed", ["body", "thread"])
def test_key_reuse_mismatch_is_rejected(sql, changed):
    thread = open_thread(sql)
    key = str(uuid4())
    send(sql, thread, key=key)
    target = open_thread(sql, OTHER) if changed == "thread" else thread
    error = sql(
        operation(
            "send",
            {
                "conversation_id": target["id"],
                "body": "Changed" if changed == "body" else "Synthetic message",
                "client_message_id": key,
            },
        ),
        succeeds=False,
    )
    assert "Message idempotency mismatch" in error
    assert sql("SELECT count(*) FROM care_conversation_messages") == "1"


@pytest.mark.parametrize(
    "change", ["inactive", "transferred", "patient", "clinician", "clinic", "suspended"]
)
def test_revocation_reassignment_or_clinic_change_denies_all_access(sql, change):
    thread = open_thread(sql)
    message = send(sql, thread)
    mutations = {
        "inactive": f"UPDATE care_teams SET status='inactive' WHERE id='{TEAM}'",
        "transferred": f"UPDATE care_teams SET status='transferred' WHERE id='{TEAM}'",
        "patient": f"UPDATE care_teams SET patient_id='{FOREIGN}' WHERE id='{TEAM}'",
        "clinician": f"DELETE FROM care_teams WHERE id='{OTHER_TEAM}'; UPDATE care_teams SET clinician_id='{OTHER}' WHERE id='{TEAM}'",
        "clinic": f"UPDATE clinicians SET clinic_id='{OTHER_CLINIC}' WHERE id='{CLINICIAN}'",
        "suspended": f"UPDATE clinics SET status='suspended' WHERE id='{CLINIC}'",
    }
    sql(mutations[change])
    assert thread["id"] not in {t["id"] for t in call(sql, "list")}
    for action, extra in [
        ("messages", {}),
        ("send", {"body": "Retry", "client_message_id": str(uuid4())}),
        ("read", {"last_message_id": message["id"]}),
    ]:
        assert "Conversation unavailable" in sql(
            operation(action, {"conversation_id": thread["id"], **extra}), succeeds=False
        )
    assert sql("SELECT count(*) FROM care_conversation_messages") == "1"


@pytest.mark.parametrize("action", ["messages", "send", "read"])
def test_foreign_patient_and_unassigned_clinician_denied(sql, action):
    thread = open_thread(sql)
    message = send(sql, thread)
    payload = {
        "conversation_id": thread["id"],
        "body": "Synthetic",
        "client_message_id": str(uuid4()),
        "last_message_id": message["id"],
    }
    for actor, role in [(FOREIGN, "patient"), (OTHER, "clinician"), (PATIENT, "clinician")]:
        assert "Conversation unavailable" in sql(
            operation(action, payload, actor=actor, role=role), succeeds=False
        )


def test_sender_scoped_uuid_key_not_shared_between_senders(sql):
    thread, key = open_thread(sql), str(uuid4())
    first = send(sql, thread, key=key)
    second = send(sql, thread, key=key, actor=CLINICIAN, role="clinician")
    assert first["id"] != second["id"]


def test_read_is_monotonic_and_does_not_consume_new_arrivals(sql):
    thread = open_thread(sql)
    first = send(sql, thread, actor=CLINICIAN, role="clinician")
    second = send(sql, thread, actor=CLINICIAN, role="clinician")
    initial = call(sql, "read", {"conversation_id": thread["id"], "last_message_id": first["id"]})
    assert call(sql, "list")[0]["unread_count"] == 1
    latest = call(sql, "read", {"conversation_id": thread["id"], "last_message_id": second["id"]})
    assert (
        call(sql, "read", {"conversation_id": thread["id"], "last_message_id": first["id"]})
        == latest
    )
    assert latest["read_at"] >= initial["read_at"]
    send(sql, thread, actor=CLINICIAN, role="clinician")
    assert call(sql, "list")[0]["unread_count"] == 1
    assert sql("SELECT count(*) FROM care_conversation_audit_events WHERE action='read'") == "2"


def test_stable_cursor_ties_and_new_arrivals(sql):
    thread = open_thread(sql)
    messages = [send(sql, thread) for _ in range(5)]
    sql("UPDATE care_conversation_messages SET created_at='2026-10-09T12:00:00Z'")
    ordered = sorted(messages, key=lambda m: m["id"])
    page = call(sql, "messages", {"conversation_id": thread["id"], "limit": 2})
    assert [m["id"] for m in page["items"]] == [m["id"] for m in ordered[-2:]]
    assert page["next_cursor"] == ordered[-2]["id"]
    send(sql, thread, "New arrival")
    seen = list(page["items"])
    while page["next_cursor"]:
        page = call(
            sql,
            "messages",
            {"conversation_id": thread["id"], "limit": 2, "before": page["next_cursor"]},
        )
        seen.extend(page["items"])
    assert len(seen) == 5 and {m["id"] for m in seen} == {m["id"] for m in messages}


@pytest.mark.parametrize("action", ["messages", "read"])
def test_cursor_and_read_marker_must_belong_to_thread(sql, action):
    first, second = open_thread(sql), open_thread(sql, OTHER)
    message = send(sql, second)
    field = "before" if action == "messages" else "last_message_id"
    assert "Invalid conversation request" in sql(
        operation(action, {"conversation_id": first["id"], field: message["id"]}), succeeds=False
    )


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_browser_cannot_read_write_or_call_rpc(sql, role):
    thread = open_thread(sql)
    for table in [
        "care_conversations",
        "care_conversation_messages",
        "care_conversation_reads",
        "care_conversation_audit_events",
    ]:
        assert "permission denied" in sql(f"SET ROLE {role}; SELECT * FROM {table}", succeeds=False)
    assert "permission denied" in sql(
        f"SET ROLE {role}; SELECT care_conversation_operation('{PATIENT}','patient','list')",
        succeeds=False,
    )
    assert "permission denied" in sql(
        f"SET ROLE {role}; INSERT INTO care_conversation_messages(conversation_id) VALUES ('{thread['id']}')",
        succeeds=False,
    )
    assert (
        sql(
            "SELECT count(*) FROM pg_class WHERE relname IN ('care_conversations','care_conversation_messages','care_conversation_reads','care_conversation_audit_events') AND relrowsecurity"
        )
        == "4"
    )


def test_failed_audit_rolls_back_send_and_marker(sql):
    thread = open_thread(sql)
    sql("""CREATE FUNCTION reject_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Synthetic audit outage'; END $$;
      CREATE TRIGGER reject_audit BEFORE INSERT ON care_conversation_audit_events FOR EACH ROW EXECUTE FUNCTION reject_audit();""")
    assert "Synthetic audit outage" in sql(
        operation(
            "send",
            {
                "conversation_id": thread["id"],
                "body": "Synthetic",
                "client_message_id": str(uuid4()),
            },
        ),
        succeeds=False,
    )
    assert sql("SELECT count(*) FROM care_conversation_messages") == "0"
    assert sql("SELECT count(*) FROM care_conversations WHERE last_message_at IS NOT NULL") == "0"


@pytest.mark.parametrize("first", ["send", "revoke"])
def test_concurrent_send_and_revoke_have_atomic_order(sql, first):
    thread = open_thread(sql)
    send_stmt = operation(
        "send",
        {
            "conversation_id": thread["id"],
            "body": "Synthetic race",
            "client_message_id": str(uuid4()),
        },
    )
    revoke_stmt = f"UPDATE care_teams SET status='inactive' WHERE id='{TEAM}';"
    first_stmt, second_stmt = (
        (send_stmt, revoke_stmt) if first == "send" else (revoke_stmt, send_stmt)
    )
    a = sql.start(f"BEGIN; {first_stmt} SELECT pg_sleep(1.5); COMMIT;", "first")
    wait_event(sql, "first", "PgSleep")
    b = sql.start(second_stmt, "second")
    wait_event(sql, "second", "Lock")
    finish(a)
    finish(b, succeeds=first == "send")
    expected = "1" if first == "send" else "0"
    assert sql("SELECT count(*) FROM care_conversation_messages") == expected
    assert (
        sql("SELECT count(*) FROM care_conversation_audit_events WHERE action='sent'") == expected
    )


def test_concurrent_duplicate_send_returns_one_message(sql):
    thread, key = open_thread(sql), str(uuid4())
    stmt = operation(
        "send",
        {
            "conversation_id": thread["id"],
            "body": "Synthetic concurrent retry",
            "client_message_id": key,
        },
    )
    a = sql.start(f"BEGIN; {stmt} SELECT pg_sleep(1.5); COMMIT;", "first")
    wait_event(sql, "first", "PgSleep")
    b = sql.start(stmt, "second")
    wait_event(sql, "second", "Lock")
    finish(a)
    finish(b)
    assert sql("SELECT count(*) FROM care_conversation_messages") == "1"
    assert sql("SELECT count(*) FROM care_conversation_audit_events WHERE action='sent'") == "1"


def test_concurrent_read_then_send_leaves_arrival_unread(sql):
    thread = open_thread(sql)
    message = send(sql, thread, actor=CLINICIAN, role="clinician")
    a = sql.start(
        f"BEGIN; {operation('read', {'conversation_id': thread['id'], 'last_message_id': message['id']})} SELECT pg_sleep(1.5); COMMIT;",
        "first",
    )
    wait_event(sql, "first", "PgSleep")
    b = sql.start(
        operation(
            "send",
            {
                "conversation_id": thread["id"],
                "body": "Concurrent arrival",
                "client_message_id": str(uuid4()),
            },
            actor=CLINICIAN,
            role="clinician",
        ),
        "second",
    )
    wait_event(sql, "second", "Lock")
    finish(a)
    finish(b)
    assert call(sql, "list")[0]["unread_count"] == 1


def test_stale_transaction_isolation_fails_closed(sql):
    error = sql("BEGIN ISOLATION LEVEL REPEATABLE READ; " + operation("list"), succeeds=False)
    assert "requires read committed" in error


@pytest.fixture
def activity_sql(sql):
    # Install actual care-plan table/wording definitions. Clinical-source tables
    # are prerequisites only; no approval/projection function is replaced here.
    sql("""
      CREATE TABLE clinical_recommendations(id uuid PRIMARY KEY);
      CREATE TABLE clinical_facts(id uuid PRIMARY KEY);
    """)
    sql(
        (MIGRATION.parent / "040_clinician_approved_care_plans.sql")
        .read_text()
        .split("ALTER TABLE public.medications")[0]
    )
    sql(
        (MIGRATION.parent / "049_bilingual_care_plan_wording.sql")
        .read_text()
        .split("-- Projection copies")[0]
    )
    gate = (MIGRATION.parent / "048_patient_upload_care_plan_review_gate.sql").read_text()
    sql(gate.split("CREATE FUNCTION private.care_plan_fact_is_eligible")[0])
    sql("""
      GRANT SELECT,INSERT,UPDATE ON care_plan_versions,care_plan_items,care_plan_audit_events TO service_role;
      ALTER TABLE care_plan_versions ENABLE ROW LEVEL SECURITY;
      ALTER TABLE care_plan_items ENABLE ROW LEVEL SECURITY;
      ALTER TABLE care_plan_audit_events ENABLE ROW LEVEL SECURITY;
      REVOKE ALL ON care_plan_items FROM PUBLIC,anon,authenticated;
      REVOKE ALL ON FUNCTION private.lock_care_plan_evidence(uuid,boolean) FROM PUBLIC,anon,authenticated;
      GRANT EXECUTE ON FUNCTION private.lock_care_plan_evidence(uuid,boolean) TO service_role;
    """)
    migration = (MIGRATION.parent / "074_care_conversation_activity_review.sql").read_text()
    clinic_guards = """SELECT md5(pg_get_functiondef(
      'public.care_conversation_operation(uuid,text,text,jsonb)'::regprocedure)) ||
      md5(pg_get_functiondef('private.lock_care_conversation_pair(uuid,uuid,text)'::regprocedure));"""
    existing_guards = sql(clinic_guards)
    sql(migration)
    sql(migration)  # rerun safety, including grants and final assertions
    assert sql(clinic_guards) == existing_guards
    plan, item = str(uuid4()), str(uuid4())
    sql(f"""
      INSERT INTO care_plan_versions(id,patient_id,version_number,status,approved_by,approved_at)
        VALUES('{plan}','{PATIENT}',1,'approved','{CLINICIAN}',now());
      INSERT INTO care_plan_items(id,plan_version_id,category,title,instructions,frequency)
        VALUES('{item}','{plan}','hydration','Synthetic activity','Approved source instruction','daily');
    """)
    return sql, plan, item


def activity_operation(action, payload, *, actor=PATIENT, role="patient"):
    return operation(action, payload, actor=actor, role=role).replace(
        "public.care_conversation_operation(", "public.care_conversation_activity_operation("
    )


def attached_message(sql, item):
    thread = open_thread(sql)
    payload = {
        "conversation_id": thread["id"],
        "body": "Question about frequency",
        "client_message_id": str(uuid4()),
        "care_plan_item_id": item,
    }
    message = json.loads(sql(activity_operation("send", payload)))
    return thread, payload, message


def test_activity_send_replay_and_context_mismatch(activity_sql):
    sql, _, item = activity_sql
    _, payload, message = attached_message(sql, item)
    assert message["activity_context"]["item_id"] == item
    assert json.loads(sql(activity_operation("send", payload)))["id"] == message["id"]
    error = sql(activity_operation("send", {**payload, "care_plan_item_id": None}), succeeds=False)
    assert "idempotency mismatch" in error
    assert sql("SELECT count(*) FROM care_conversation_messages") == "1"


def test_activity_draft_reuses_items_and_never_publishes(activity_sql):
    sql, plan, item = activity_sql
    thread, _, message = attached_message(sql, item)
    payload = {"conversation_id": thread["id"], "message_id": message["id"]}
    first = json.loads(
        sql(activity_operation("review", payload, actor=CLINICIAN, role="clinician"))
    )
    second = json.loads(
        sql(activity_operation("review", payload, actor=CLINICIAN, role="clinician"))
    )
    assert first == second
    assert sql(f"SELECT status FROM care_plan_versions WHERE id='{plan}'") == "approved"
    assert sql(f"SELECT status FROM care_plan_versions WHERE id='{first['plan_id']}'") == "draft"
    assert (
        sql(f"SELECT review_source_item_id FROM care_plan_items WHERE id='{first['item_id']}'")
        == item
    )
    assert sql("SELECT count(*) FROM care_plan_items") == "2"
    assert (
        sql("SELECT count(*) FROM care_plan_audit_events WHERE event_type='message_review_opened'")
        == "1"
    )
    assert sql("SELECT count(*) FROM medications") == "0"
    assert sql("SELECT count(*) FROM obligations") == "0"


@pytest.mark.parametrize(
    "actor,role", [(PATIENT, "patient"), (OTHER, "clinician"), (FOREIGN, "patient")]
)
def test_activity_review_does_not_cross_private_threads(activity_sql, actor, role):
    sql, _, item = activity_sql
    thread, _, message = attached_message(sql, item)
    sql(
        activity_operation(
            "review",
            {"conversation_id": thread["id"], "message_id": message["id"]},
            actor=actor,
            role=role,
        ),
        succeeds=False,
    )
    assert sql("SELECT count(*) FROM care_plan_versions WHERE status='draft'") == "0"


def test_activity_source_replacement_blocks_new_sends_and_review(activity_sql):
    sql, plan, item = activity_sql
    thread, payload, message = attached_message(sql, item)
    sql(f"UPDATE care_plan_versions SET status='superseded' WHERE id='{plan}'")
    # Same saved request remains recoverable; no new send or draft from stale data.
    assert json.loads(sql(activity_operation("send", payload)))["id"] == message["id"]
    sql(activity_operation("send", {**payload, "client_message_id": str(uuid4())}), succeeds=False)
    sql(
        activity_operation(
            "review",
            {"conversation_id": thread["id"], "message_id": message["id"]},
            actor=CLINICIAN,
            role="clinician",
        ),
        succeeds=False,
    )
    assert sql("SELECT count(*) FROM care_conversation_messages") == "1"


def test_activity_foreign_item_rolls_back_message_and_audit(activity_sql):
    sql, plan, item = activity_sql
    sql(f"UPDATE care_plan_versions SET patient_id='{FOREIGN}' WHERE id='{plan}'")
    thread = open_thread(sql)
    sql(
        activity_operation(
            "send",
            {
                "conversation_id": thread["id"],
                "body": "Synthetic",
                "client_message_id": str(uuid4()),
                "care_plan_item_id": item,
            },
        ),
        succeeds=False,
    )
    assert sql("SELECT count(*) FROM care_conversation_messages") == "0"
    assert sql("SELECT count(*) FROM care_conversation_audit_events WHERE action='sent'") == "0"


def test_activity_revocation_and_browser_roles_fail_closed(activity_sql):
    sql, _, item = activity_sql
    thread, _, message = attached_message(sql, item)
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{TEAM}'")
    payload = {"conversation_id": thread["id"], "message_id": message["id"]}
    sql(activity_operation("review", payload, actor=CLINICIAN, role="clinician"), succeeds=False)
    for role in ("anon", "authenticated"):
        sql(
            f"SET ROLE {role}; SELECT public.care_conversation_activity_operation('{PATIENT}','patient','send','{{}}');",
            succeeds=False,
        )


def test_activity_concurrent_draft_review_is_idempotent(activity_sql):
    sql, _, item = activity_sql
    thread, _, message = attached_message(sql, item)
    request = activity_operation(
        "review",
        {"conversation_id": thread["id"], "message_id": message["id"]},
        actor=CLINICIAN,
        role="clinician",
    )
    first = sql.start("BEGIN; " + request + " SELECT pg_sleep(0.4); COMMIT;", "activity-first")
    wait_event(sql, "activity-first", "PgSleep")
    second = sql.start(request, "activity-second")
    wait_event(sql, "activity-second", "Lock")
    finish(first)
    finish(second)
    assert sql("SELECT count(*) FROM care_plan_versions WHERE status='draft'") == "1"
    assert sql("SELECT count(*) FROM care_plan_items") == "2"


def test_activity_review_waits_before_publication_row_locks(activity_sql):
    sql, _, item = activity_sql
    thread, _, message = attached_message(sql, item)
    request = activity_operation(
        "review",
        {"conversation_id": thread["id"], "message_id": message["id"]},
        actor=CLINICIAN,
        role="clinician",
    )
    draft = json.loads(sql(request))
    # Reproduce publication's actual evidence -> draft -> patient lock footprint.
    publication = sql.start(
        f"""BEGIN; SET ROLE service_role;
      SELECT private.lock_care_plan_evidence('{PATIENT}',true);
      SELECT id FROM care_plan_versions WHERE id='{draft["plan_id"]}' FOR UPDATE;
      SELECT pg_sleep(0.4);
      SELECT id FROM patients WHERE id='{PATIENT}' FOR UPDATE;
      COMMIT;""",
        "publication-locks",
    )
    wait_event(sql, "publication-locks", "PgSleep")
    review = sql.start(request, "activity-after-publication")
    wait_event(sql, "activity-after-publication", "Lock")
    finish(publication)
    finish(review)
    assert sql("SELECT count(*) FROM care_plan_versions WHERE status='draft'") == "1"
