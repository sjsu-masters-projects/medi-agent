"""Real migration/trigger/RPC contracts in disposable offline PostgreSQL 16."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER") != "1",
    reason="explicit opt-in disposable Docker PostgreSQL contract check",
)
MIGRATIONS = Path(__file__).resolve().parents[2] / "src/app/db/migrations"
PATIENT = "00000000-0000-0000-0000-000000000001"
CLINICIAN = "00000000-0000-0000-0000-000000000002"
OTHER = "00000000-0000-0000-0000-000000000003"
FOREIGN = "00000000-0000-0000-0000-000000000004"
TEAM = "00000000-0000-0000-0000-000000000005"


@pytest.fixture(scope="module")
def postgres():
    docker = shutil.which("docker")
    if not docker:
        pytest.fail("Docker and cached postgres:16 required")
    container = f"mediagent-notification-test-{uuid4().hex}"
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
            result = subprocess.run(
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
            if result.returncode == 0:
                break
            time.sleep(0.1)
        else:
            pytest.fail("Disposable PostgreSQL did not become ready")
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
            input="CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;",
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
    database = "notification_" + uuid4().hex
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
            input="SET statement_timeout='12s';\n" + statement,
            capture_output=True,
            text=True,
            timeout=18,
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
            f"SET statement_timeout='12s'; SET application_name='{name}';\n{statement}"
        )
        process.stdin.close()
        return process

    execute.start = start
    execute("""CREATE SCHEMA auth; CREATE TABLE auth.users(id uuid PRIMARY KEY);
      CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;""")
    # Auth/platform bootstrap only is synthetic. Every application table and
    # source lifecycle exercised below comes from the repository migrations.
    for name in (
        "001_initial_schema.sql",
        "002_rls_policies.sql",
        "005_document_parse_tracking.sql",
        "006_care_team_invite_compat.sql",
        "007_clinic_identity_foundation.sql",
        "012_document_review_queue.sql",
        "013_cron_scheduler_foundation.sql",
        "014_patient_timezones_and_reminder_schedules.sql",
        "017_clinical_facts_provenance.sql",
        "019_clinical_action_approvals.sql",
        "022_grant_service_role_seed_access.sql",
        "038_appointment_proposal_lifecycle.sql",
        "039_appointment_patient_changes.sql",
        "040_clinician_approved_care_plans.sql",
        "042_care_plan_publication_review_guards.sql",
        "043_incomplete_care_plan_drafts.sql",
        "046_adr_clinician_review_actions.sql",
    ):
        execute((MIGRATIONS / name).read_text())
    hardening = (MIGRATIONS / "020_harden_database_security.sql").read_text()
    execute(hardening.split("-- Public helper functions remain")[0])
    # Grouped offers, withdrawal, expiry and booking guards use the private helpers above.
    for name in (
        "040_appointment_offer_groups.sql",
        "041_atomic_appointment_offers.sql",
        "042_appointment_expired_status.sql",
        "043_appointment_booking_guards.sql",
    ):
        execute((MIGRATIONS / name).read_text())
    execute((MIGRATIONS / "048_care_team_conversations.sql").read_text())
    execute(Path(__file__).with_name("notification_centre_seed.sql").read_text())
    # Baseline old notices exist before capture installation; old safety rows
    # must never become new shared work. Reminder adapter preserves original rows.
    execute(f"""INSERT INTO notifications(patient_id,notification_type,title,body,is_read) VALUES
      ('{PATIENT}','med_reminder','Old reminder','Synthetic',true),
      ('{PATIENT}','adr_alert','Old internal notice','Do not replay urgent text',false);
      INSERT INTO clinician_messages(clinician_id,patient_id,channel,subject,body) VALUES
      ('{CLINICIAN}','{PATIENT}','in_app','Urgent patient chat escalation','Chat escalation flagged (urgent/general). Historical');""")
    execute((MIGRATIONS / "051_notification_centre.sql").read_text())
    try:
        yield execute
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)


def operation(action, payload=None, *, actor=PATIENT, role="patient"):
    encoded = json.dumps(payload or {}).replace("'", "''")
    return f"SET ROLE service_role; SELECT notification_centre_operation('{actor}','{role}','{action}','{encoded}'::jsonb);"


def call(sql, action="list", payload=None, **actor):
    return json.loads(sql(operation(action, payload, **actor)))


def clinician(sql, action="list", payload=None, *, actor=CLINICIAN):
    return call(sql, action, payload, actor=actor, role="clinician")


def document(sql, *, patient=PATIENT):
    key = str(uuid4())
    sql(f"""INSERT INTO documents(id,patient_id,uploaded_by,uploaded_by_role,document_type,file_name,file_url,file_size_bytes,review_status)
      VALUES('{key}','{patient}','{patient}','patient','other','synthetic.pdf','synthetic',10,'pending');""")
    return key


def thread(sql):
    payload = json.dumps({"recipient_id": CLINICIAN})
    return json.loads(
        sql(
            f"SET ROLE service_role; SELECT care_conversation_operation('{PATIENT}','patient','open','{payload}');"
        )
    )["id"]


def send(sql, conversation, *, actor=CLINICIAN, role="clinician"):
    payload = json.dumps(
        {
            "conversation_id": conversation,
            "body": "Synthetic message",
            "client_message_id": str(uuid4()),
        }
    )
    return json.loads(
        sql(
            f"SET ROLE service_role; SELECT care_conversation_operation('{actor}','{role}','send','{payload}');"
        )
    )


def appointment(sql, status, *, when="2 days", created="0 seconds", location="Synthetic room 1"):
    key = str(uuid4())
    sql(f"""INSERT INTO appointments(id,patient_id,care_team_id,scheduled_at,status,location,created_at)
      VALUES('{key}','{PATIENT}','{TEAM}',clock_timestamp()+interval '{when}','{status}','{location}',
        clock_timestamp()-interval '{created}');""")
    return key


def events(sql, key):
    # Who is actually delivered each event, not the informational recipient column.
    rows = sql(f"""SELECT e.id||'|'||e.event_type||'|'||e.audience||'|'||(SELECT string_agg(d.recipient_id::text,','
        ORDER BY d.recipient_id) FROM notification_pending_deliveries d WHERE d.event_id=e.id)
      FROM notification_events e WHERE e.source_type='appointments' AND e.source_id='{key}' ORDER BY e.created_at,e.id""")
    return [tuple(row.split("|")) for row in rows.splitlines()]


def finish(process):
    process.wait(timeout=15)
    out, err = process.stdout.read(), process.stderr.read()
    assert process.returncode == 0, err
    return out


def wait_event(sql, name, event="PgSleep"):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if (
            sql(
                f"SELECT count(*) FROM pg_stat_activity WHERE application_name='{name}' AND wait_event='{event}'"
            )
            == "1"
        ):
            return
        time.sleep(0.03)
    pytest.fail(f"Session {name} did not reach {event}")


def test_schema_real_capture_and_durable_delivery(sql):
    key = document(sql)
    assert sql(f"SELECT count(*) FROM notification_events WHERE source_id='{key}'") == "1"
    assert (
        sql("SELECT count(*) FROM notification_pending_deliveries WHERE delivered_at IS NULL")
        == "3"
    )
    assert sql("SELECT count(*) FROM notification_receipts") == "0"
    rows = clinician(sql)["items"]
    assert (
        len(rows) == 1
        and rows[0]["source_id"] == key
        and rows[0]["event_type"] == "document_review"
    )
    assert rows[0]["patient_name"] == "Synthetic Patient"
    assert rows[0]["clinic_name"] == "Synthetic clinic"
    assert clinician(sql)["items"] == rows
    assert (
        sql(
            f"SELECT count(*) FROM notification_receipts r JOIN notification_events e ON e.id=r.event_id WHERE e.source_id='{key}'"
        )
        == "1"
    )


def test_legacy_history_no_safety_backfill_or_reminder_regeneration(sql):
    rows = call(sql)["items"]
    assert len(rows) == 2
    legacy = next(r for r in rows if r["event_type"] == "legacy_update")
    assert not legacy["actionable"] and not legacy["can_acknowledge"]
    assert "urgent text" not in json.dumps(rows)
    assert clinician(sql)["items"] == []
    assert sql("SELECT count(*) FROM notifications") == "2"
    assert sql("SELECT count(*) FROM notification_events WHERE event_type='safety_flag'") == "0"
    assert next(r for r in rows if r["event_type"] == "med_reminder")["is_read"]


def test_private_messages_grouping_snapshot_and_new_arrival(sql):
    conv = thread(sql)
    send(sql, conv)
    send(sql, conv)
    page = call(sql)
    row = next(r for r in page["items"] if r["event_type"] == "message_received")
    assert len(row["receipt_ids"]) == 2
    assert call(sql, "summary")["unread_count"] == 2  # one message group + old notice
    send(sql, conv)
    call(sql, "read", {"id": row["id"]})
    remaining = next(
        r for r in call(sql)["items"] if r["event_type"] == "message_received" and not r["is_read"]
    )
    assert len(remaining["receipt_ids"]) == 1
    call(sql, "read_through", {"ids": page["read_ids"]})
    assert call(sql, "summary")["unread_count"] == 1
    assert clinician(sql, actor=OTHER)["items"] == []


def test_conversation_marker_clears_notification_unread(sql):
    conv = thread(sql)
    message = send(sql, conv)
    assert any(
        not r["is_read"] for r in call(sql)["items"] if r["event_type"] == "message_received"
    )
    payload = json.dumps({"conversation_id": conv, "last_message_id": message["id"]})
    sql(
        f"SET ROLE service_role; SELECT care_conversation_operation('{PATIENT}','patient','read','{payload}');"
    )
    assert all(r["is_read"] for r in call(sql)["items"] if r["event_type"] == "message_received")


def test_new_assignment_current_work_not_private_history(sql):
    key = document(sql)
    conv = thread(sql)
    send(sql, conv, actor=PATIENT, role="patient")
    clinician(sql)
    assert clinician(sql, actor=OTHER)["items"] == []
    sql(
        f"INSERT INTO care_teams(patient_id,clinician_id,role) VALUES('{PATIENT}','{OTHER}','reviewer');"
    )
    rows = clinician(sql, actor=OTHER)["items"]
    assert {r["source_id"] for r in rows} == {key}
    sql(f"UPDATE documents SET review_status='approved' WHERE id='{key}';")
    assert clinician(sql, "action_items", actor=OTHER)["items"] == []


def test_revoked_foreign_and_wrong_role_denied(sql):
    key = document(sql)
    row = clinician(sql)["items"][0]
    assert call(sql, actor=FOREIGN)["items"] == []
    assert "Notification unavailable" in sql(operation("read", {"id": row["id"]}), succeeds=False)
    assert "Notification unavailable" in sql(
        operation("list", actor=PATIENT, role="clinician"), succeeds=False
    )
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{TEAM}';")
    assert clinician(sql)["items"] == []
    assert "Notification unavailable" in sql(
        operation("read_through", {"ids": [row["id"]]}, actor=CLINICIAN, role="clinician"),
        succeeds=False,
    )
    assert sql(f"SELECT count(*) FROM notification_events WHERE source_id='{key}'") == "1"


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_browser_denial_all_tables_and_rpc(sql, role):
    for table in (
        "notification_events",
        "notification_receipts",
        "notification_pending_deliveries",
        "notification_read_audit",
    ):
        assert "permission denied" in sql(
            f"SET ROLE {role}; SELECT * FROM {table};", succeeds=False
        )
        assert "permission denied" in sql(f"SET ROLE {role}; DELETE FROM {table};", succeeds=False)
        assert sql(f"SELECT relrowsecurity FROM pg_class WHERE oid='{table}'::regclass") == "t"
    assert "permission denied" in sql(
        f"SET ROLE {role}; SELECT notification_centre_operation('{PATIENT}','patient','list');",
        succeeds=False,
    )
    assert "permission denied" in sql(
        f"SET ROLE {role}; SELECT private.notification_prepare('{PATIENT}','patient');",
        succeeds=False,
    )


def test_source_capture_failure_rolls_back_source(sql):
    sql("""CREATE FUNCTION reject_capture() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Synthetic capture outage'; END $$;
      CREATE TRIGGER reject_capture BEFORE INSERT ON notification_events FOR EACH ROW EXECUTE FUNCTION reject_capture();""")
    assert "Synthetic capture outage" in sql(
        f"""INSERT INTO documents(patient_id,uploaded_by,uploaded_by_role,document_type,file_name,file_url,file_size_bytes,review_status)
      VALUES('{PATIENT}','{PATIENT}','patient','other','synthetic.pdf','synthetic',10,'pending');""",
        succeeds=False,
    )
    assert sql("SELECT count(*) FROM documents") == "0"


def test_read_audit_failure_rolls_back_receipt_and_legacy(sql):
    row = next(r for r in call(sql)["items"] if r["event_type"] == "legacy_update")
    sql("""CREATE FUNCTION reject_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Synthetic audit outage'; END $$;
      CREATE TRIGGER reject_audit BEFORE INSERT ON notification_read_audit FOR EACH ROW EXECUTE FUNCTION reject_audit();""")
    assert "Synthetic audit outage" in sql(operation("read", {"id": row["id"]}), succeeds=False)
    assert sql(f"SELECT read_at IS NULL FROM notification_receipts WHERE id='{row['id']}'") == "t"
    assert sql(f"SELECT is_read FROM notifications WHERE id='{row['source_id']}'") == "f"


def test_safety_fanout_new_only_and_per_reviewer_ack(sql):
    sql(f"""INSERT INTO care_teams(patient_id,clinician_id,role) VALUES('{PATIENT}','{OTHER}','reviewer');
      INSERT INTO clinician_messages(clinician_id,patient_id,channel,subject,body) VALUES
      ('{CLINICIAN}','{PATIENT}','in_app','Urgent patient chat escalation','Chat escalation flagged (urgent/general). New synthetic flag'),
      ('{OTHER}','{PATIENT}','in_app','Urgent patient chat escalation','Chat escalation flagged (urgent/general). New synthetic flag');""")
    assert sql("SELECT count(*) FROM notification_events WHERE event_type='safety_flag'") == "1"
    row = clinician(sql, "action_items")["items"][0]
    assert row["can_acknowledge"]
    clinician(sql, "acknowledge", {"id": row["id"], "note": "Seen; source workflow remains open"})
    clinician(sql, "acknowledge", {"id": row["id"], "note": "Retry"})
    assert clinician(sql, "action_items")["items"] == []
    assert len(clinician(sql, "action_items", actor=OTHER)["items"]) == 1
    assert sql("SELECT count(*) FROM notification_read_audit WHERE action='acknowledge'") == "1"
    assert sql("SELECT count(*) FROM clinician_messages") == "3"


def test_appointments_responsible_clinician_and_stale_actions(sql):
    sql(
        f"INSERT INTO care_teams(patient_id,clinician_id,role) VALUES('{PATIENT}','{OTHER}','reviewer');"
    )
    key = str(uuid4())
    sql(
        f"INSERT INTO appointments(id,patient_id,care_team_id,scheduled_at,status) VALUES('{key}','{PATIENT}','{TEAM}',clock_timestamp()+interval '2 days','proposed');"
    )
    assert any(r["event_type"] == "appointment_offered" for r in call(sql)["items"])
    assert clinician(sql)["items"] == []
    sql(f"UPDATE appointments SET status='confirmed' WHERE id='{key}';")
    assert clinician(sql)["items"][0]["event_type"] == "appointment_response"
    assert clinician(sql, actor=OTHER)["items"] == []
    assert not any(r["event_type"] == "appointment_response" for r in call(sql)["items"])
    sql(f"""INSERT INTO notifications(patient_id,notification_type,title,body,metadata)
      VALUES('{PATIENT}','appointment','Synthetic','Synthetic','{{"appointment_id":"{key}"}}');""")
    assert next(r for r in call(sql)["items"] if r["event_type"] == "appointment_reminder")[
        "actionable"
    ]
    sql(f"UPDATE appointments SET status='cancelled' WHERE id='{key}';")
    assert not any(r["actionable"] for r in call(sql)["items"] if r["category"] == "appointments")


def test_document_processing_and_rejection_are_distinct(sql):
    key = document(sql)
    sql(f"UPDATE documents SET parse_status='completed' WHERE id='{key}';")
    processed = next(r for r in call(sql)["items"] if r["event_type"] == "document_processed")
    assert processed["metadata"]["review_status"] == "pending"
    assert len(clinician(sql, "action_items")["items"]) == 1
    sql(f"UPDATE documents SET review_status='rejected' WHERE id='{key}';")
    assert clinician(sql, "action_items")["items"] == []
    assert next(r for r in call(sql)["items"] if r["event_type"] == "document_reviewed")[
        "actionable"
    ]
    sql(f"UPDATE documents SET parse_status='failed' WHERE id='{key}';")
    assert next(r for r in call(sql)["items"] if r["event_type"] == "document_failed")["actionable"]


def test_keyset_pages_counts_not_page_size(sql):
    keys = [document(sql) for _ in range(5)]
    page = clinician(sql, payload={"limit": 2})
    assert set(page["next_cursor"]) == {"created_at", "id"}
    assert clinician(sql, "summary")["unread_count"] == 5
    assert clinician(sql, "summary")["action_item_count"] == 5
    seen = list(page["items"])
    document(sql)
    while page["next_cursor"]:
        page = clinician(sql, payload={"limit": 2, "before": page["next_cursor"]})
        seen.extend(page["items"])
    assert len(seen) == 5 and {r["source_id"] for r in seen} == set(keys)
    actions = clinician(sql, "action_items", {"limit": 2, "category": "documents"})
    assert actions["next_cursor"] and len(actions["items"]) == 2


def test_snapshot_concurrent_arrival_and_idempotent_audit(sql):
    conv = thread(sql)
    send(sql, conv)
    page = call(sql)
    stmt = operation("read_through", {"ids": page["read_ids"]})
    first = sql.start(f"BEGIN; {stmt} SELECT pg_sleep(1); COMMIT;", "snapshot")
    wait_event(sql, "snapshot")
    send(sql, conv)
    finish(first)
    call(sql, "read_through", {"ids": page["read_ids"]})
    assert call(sql, "summary")["unread_count"] == 1
    assert sql("SELECT count(*) FROM notification_read_audit WHERE action='read'") == str(
        len(page["read_ids"])
    )


def test_draft_waits_for_items_and_generation_completion(sql):
    plan, request = str(uuid4()), str(uuid4())
    sql(f"""INSERT INTO care_plan_versions(id,patient_id,version_number) VALUES('{plan}','{PATIENT}',1);
      INSERT INTO care_plan_generation_requests(id,patient_id,source_watermark,status,plan_version_id)
      SELECT '{request}',patient_id,source_watermark,'processing',id FROM care_plan_versions WHERE id='{plan}';""")
    assert clinician(sql)["items"] == []
    sql(f"""INSERT INTO care_plan_items(plan_version_id,category,title,instructions,frequency)
      VALUES('{plan}','movement','Synthetic movement','Reviewed synthetic wording','daily');
      UPDATE care_plan_versions SET generated_at=clock_timestamp() WHERE id='{plan}';""")
    assert clinician(sql)["items"] == []
    sql(f"UPDATE care_plan_generation_requests SET status='completed' WHERE id='{request}';")
    assert clinician(sql)["items"][0]["event_type"] == "care_plan_draft"
    assert not any(r["source_id"] == plan for r in call(sql)["items"])
    sql(f"UPDATE care_plan_versions SET status='rejected' WHERE id='{plan}';")
    assert clinician(sql, "action_items")["items"] == []


def test_adr_reviewed_questions_only_and_current_status(sql):
    med, symptom, adr = str(uuid4()), str(uuid4()), str(uuid4())
    sql(f"""INSERT INTO medications(id,patient_id,name,dosage,frequency) VALUES('{med}','{PATIENT}','Synthetic medication','Synthetic','daily');
      INSERT INTO symptom_reports(id,patient_id,symptom,severity) VALUES('{symptom}','{PATIENT}','Synthetic symptom',1);
      INSERT INTO adr_assessments(id,patient_id,symptom_report_id,suspect_medication_id,suspect_medication_name,naranjo_score,causality,thinking_chain)
      VALUES('{adr}','{PATIENT}','{symptom}','{med}','Synthetic medication',0,'Doubtful','PRIVATE MUST NOT LEAK');""")
    assert clinician(sql, "action_items")["items"][0]["event_type"] == "adr_review"
    sql(
        f"SELECT review_adr_assessment('{adr}','{CLINICIAN}','request_information','Reviewed request','[\"¿Cuándo comenzó?\"]');"
    )
    row = next(r for r in call(sql)["items"] if r["event_type"] == "adr_information_requested")
    assert row["metadata"]["requested_information"] == ["¿Cuándo comenzó?"]
    assert row["metadata"]["clinician_id"] == CLINICIAN
    assert "PRIVATE" not in json.dumps(row)
    sql(f"SELECT review_adr_assessment('{adr}','{CLINICIAN}','mark_reviewed');")
    assert clinician(sql, "action_items")["items"] == []
    assert not next(r for r in call(sql)["items"] if r["source_id"] == adr)["actionable"]


def test_invalid_bounds_and_role_actions(sql):
    for action, payload in [
        ("list", {"limit": 101}),
        ("read_through", {"ids": [str(uuid4())] * 1001}),
        ("list", {"before": {"id": str(uuid4())}}),
        ("unknown", {}),
    ]:
        assert "Invalid notification request" in sql(operation(action, payload), succeeds=False)
    assert "Notification unavailable" in sql(operation("action_items"), succeeds=False)
    assert "requires read committed" in sql(
        "BEGIN ISOLATION LEVEL REPEATABLE READ; " + operation("list"), succeeds=False
    )


RESPONSE = ("appointment_response", "clinician")
CHANGED = ("appointment_changed", "patient")
OFFERED = ("appointment_offered", "patient")


@pytest.mark.parametrize(
    ("start", "change", "expected"),
    [
        ("proposed", "status='confirmed'", RESPONSE),
        ("proposed", "status='declined',patient_note='Synthetic reason'", RESPONSE),
        ("proposed", "status='alternative_requested'", RESPONSE),
        ("proposed", "status='cancelled'", RESPONSE),
        ("confirmed", "status='cancelled'", RESPONSE),
        ("scheduled", "status='cancelled'", RESPONSE),
        ("confirmed", "patient_note='Synthetic running late'", RESPONSE),
        ("confirmed", "scheduled_at=scheduled_at+interval '1 hour'", CHANGED),
        ("scheduled", "location='Synthetic room 2'", CHANGED),
        ("scheduled", "status='proposed'", OFFERED),
        ("proposed", "status='withdrawn'", None),
        ("confirmed", "status='completed'", None),
        ("confirmed", "status='no_show'", None),
    ],
)
def test_appointment_transitions_route_to_the_right_person(sql, start, change, expected):
    sql(
        f"INSERT INTO care_teams(patient_id,clinician_id,role) VALUES('{PATIENT}','{OTHER}','reviewer');"
    )
    key = appointment(sql, start)
    call(sql)
    before = events(sql, key)
    sql(f"UPDATE appointments SET {change} WHERE id='{key}';")
    added = [row[1:] for row in events(sql, key)[len(before) :]]
    patient_kinds = [r["event_type"] for r in call(sql)["items"] if r["source_id"] == key]
    clinician_kinds = [r["event_type"] for r in clinician(sql)["items"]]
    assert clinician(sql, actor=OTHER)["items"] == []
    if expected is None:
        assert added == [] and clinician_kinds == []
    elif expected == RESPONSE:
        assert added == [(*RESPONSE, CLINICIAN)]
        assert clinician_kinds == ["appointment_response"]
        assert "appointment_response" not in patient_kinds
    else:
        assert added == [(*expected, PATIENT)]
        assert clinician_kinds == [] and expected[0] in patient_kinds


def test_grouped_offer_is_one_item_and_withdrawn_siblings_stay_quiet(sql):
    sql(
        f"INSERT INTO care_teams(patient_id,clinician_id,role) VALUES('{PATIENT}','{OTHER}','reviewer');"
    )
    unread = call(sql, "summary")["unread_count"]
    sql(f"""SELECT propose_appointment_slots('{CLINICIAN}','{TEAM}',ARRAY[clock_timestamp()+interval '1 day',
      clock_timestamp()+interval '2 days',clock_timestamp()+interval '3 days'],30,'follow_up','Synthetic room','Synthetic');""")
    slots = sql("SELECT id FROM appointments ORDER BY scheduled_at").splitlines()
    group = sql("SELECT DISTINCT proposal_group_id FROM appointments")
    assert len(slots) == 3
    offer_key = "SELECT event_key FROM notification_events WHERE event_type='appointment_offered'"
    assert sql(offer_key) == f"appointments:offer:{group}"
    offers = [r for r in call(sql)["items"] if r["event_type"] == "appointment_offered"]
    assert len(offers) == 1 and offers[0]["actionable"]
    assert call(sql, "summary")["unread_count"] == unread + 1
    assert clinician(sql)["items"] == []
    result = json.loads(
        sql(f"SELECT respond_to_appointment_offer('{PATIENT}','{slots[1]}','accept',NULL);")
    )
    assert "error" not in result, result
    assert sql("SELECT string_agg(status::text,',' ORDER BY scheduled_at) FROM appointments") == (
        "withdrawn,confirmed,withdrawn"
    )
    kinds = sql(
        "SELECT string_agg(event_type||':'||source_id,',' ORDER BY created_at) FROM notification_events WHERE category='appointments'"
    )
    assert kinds == f"appointment_offered:{slots[0]},appointment_response:{slots[1]}"
    patient_items = [r for r in call(sql)["items"] if r["category"] == "appointments"]
    assert [r["event_type"] for r in patient_items] == ["appointment_offered"]
    assert not patient_items[0]["actionable"]
    assert call(sql, "summary")["unread_count"] == unread + 1
    rows = clinician(sql)["items"]
    assert [(r["event_type"], r["source_id"]) for r in rows] == [("appointment_response", slots[1])]
    assert clinician(sql, actor=OTHER)["items"] == []


def test_offer_actionable_only_while_open_and_expiry_tells_patient(sql):
    open_offer = appointment(sql, "proposed")
    lapsed = appointment(sql, "proposed", created="8 days")
    sql("ALTER TABLE appointments DISABLE TRIGGER appointments_booking_guard;")
    past = appointment(sql, "proposed", when="-1 hour")
    sql("ALTER TABLE appointments ENABLE TRIGGER appointments_booking_guard;")
    offered = {
        r["source_id"]: r["actionable"]
        for r in call(sql)["items"]
        if r["event_type"] == "appointment_offered"
    }
    assert offered == {open_offer: True, lapsed: False, past: False}
    assert (
        json.loads(sql(f"SELECT expire_appointment_proposals('{PATIENT}','patient');"))[
            "expired_count"
        ]
        == 1
    )
    assert sql(f"SELECT status FROM appointments WHERE id='{lapsed}'") == "expired"
    assert [row[1:] for row in events(sql, lapsed)] == [(*OFFERED, PATIENT), (*CHANGED, PATIENT)]
    changed = next(r for r in call(sql)["items"] if r["event_type"] == "appointment_changed")
    assert changed["source_id"] == lapsed and changed["metadata"]["status"] == "expired"
    assert not changed["actionable"]
    assert clinician(sql)["items"] == []
    sql(f"UPDATE appointments SET status='confirmed' WHERE id='{open_offer}';")
    offered = {
        r["source_id"]: r["actionable"]
        for r in call(sql)["items"]
        if r["event_type"] == "appointment_offered"
    }
    assert not any(offered.values())


def test_patient_account_deletion_removes_notification_history(sql):
    key = appointment(sql, "proposed")
    sql(f"UPDATE appointments SET status='confirmed' WHERE id='{key}';")
    sql(f"""INSERT INTO notifications(patient_id,notification_type,title,body) VALUES
      ('{FOREIGN}','med_reminder','Synthetic other patient','Synthetic');""")
    assert len(call(sql, actor=FOREIGN)["items"]) == 1
    legacy = next(r for r in call(sql)["items"] if r["event_type"] == "legacy_update")
    call(sql, "read", {"id": legacy["id"]})
    response = next(r for r in clinician(sql)["items"] if r["event_type"] == "appointment_response")
    clinician(sql, "read", {"id": response["id"]})
    sql(f"""INSERT INTO notifications(patient_id,notification_type,title,body) VALUES
      ('{PATIENT}','med_reminder','Synthetic undelivered','Synthetic');""")
    owned = f"""SELECT (SELECT count(*) FROM notification_events WHERE patient_id='{PATIENT}')||','||
      (SELECT count(*) FROM notification_receipts r JOIN notification_events e ON e.id=r.event_id WHERE e.patient_id='{PATIENT}')||','||
      (SELECT count(*) FROM notification_pending_deliveries WHERE recipient_id='{PATIENT}' AND delivered_at IS NULL)||','||
      (SELECT count(*) FROM notification_read_audit a JOIN notification_receipts r ON r.id=a.receipt_id
        JOIN notification_events e ON e.id=r.event_id WHERE e.patient_id='{PATIENT}')"""
    assert all(int(count) > 0 for count in sql(owned).split(","))
    sql(f"DELETE FROM auth.users WHERE id='{PATIENT}';")
    assert sql(f"SELECT count(*) FROM patients WHERE id='{PATIENT}'") == "0"
    assert sql(owned) == "0,0,0,0"
    assert sql(f"SELECT count(*) FROM notification_receipts WHERE recipient_id='{PATIENT}'") == "0"
    assert sql(f"SELECT count(*) FROM notification_read_audit WHERE actor_id='{PATIENT}'") == "0"
    assert len(call(sql, actor=FOREIGN)["items"]) == 1
    assert clinician(sql)["items"] == []


def test_clinician_account_deletion_removes_their_receipts_and_audit(sql):
    key = document(sql)
    sql(f"""INSERT INTO clinician_messages(clinician_id,patient_id,channel,subject,body) VALUES
      ('{CLINICIAN}','{PATIENT}','in_app','Urgent patient chat escalation','Chat escalation flagged (urgent/general). New synthetic flag');""")
    rows = {r["event_type"]: r for r in clinician(sql)["items"]}
    clinician(sql, "read", {"id": rows["document_review"]["id"]})
    clinician(
        sql, "acknowledge", {"id": rows["safety_flag"]["id"], "note": "Synthetic acknowledgement"}
    )
    mine = f"""SELECT (SELECT count(*) FROM notification_receipts WHERE recipient_id='{CLINICIAN}')||','||
      (SELECT count(*) FROM notification_read_audit WHERE actor_id='{CLINICIAN}')||','||
      (SELECT count(*) FROM notification_pending_deliveries WHERE recipient_id='{CLINICIAN}')"""
    assert all(int(count) > 0 for count in sql(mine).split(","))
    sql(f"DELETE FROM auth.users WHERE id='{CLINICIAN}';")
    assert sql(f"SELECT count(*) FROM clinicians WHERE id='{CLINICIAN}'") == "0"
    assert sql(mine) == "0,0,0"
    assert sql(f"SELECT count(*) FROM notification_events WHERE source_id='{key}'") == "1"
    assert len(call(sql)["items"]) == 2


def test_history_append_only_and_no_delete_grant(sql):
    row = next(r for r in call(sql)["items"] if r["event_type"] == "legacy_update")
    call(sql, "read", {"id": row["id"]})
    assert "Notification history is append only" in sql(
        "UPDATE notification_events SET metadata='{}';", succeeds=False
    )
    assert "Notification history is append only" in sql(
        "UPDATE notification_read_audit SET note='Edited';", succeeds=False
    )
    for table in (
        "notification_events",
        "notification_receipts",
        "notification_pending_deliveries",
        "notification_read_audit",
    ):
        assert sql(f"SELECT has_table_privilege('service_role','{table}','DELETE')") == "f"
        assert "permission denied" in sql(
            f"SET ROLE service_role; DELETE FROM {table};", succeeds=False
        )
    assert sql("SELECT count(*) FROM notification_read_audit") == "1"


def test_malformed_source_values_do_not_break_the_centre(sql):
    sql(f"""UPDATE patients SET timezone='Mars/Olympus' WHERE id='{PATIENT}';
      INSERT INTO notifications(patient_id,notification_type,title,body,metadata) VALUES
      ('{PATIENT}','med_reminder','Synthetic reminder','Synthetic',
        '{{"target_id":"{uuid4()}","target_type":"medication","scheduled_at":"not-a-date"}}'),
      ('{PATIENT}','appointment','Synthetic visit','Synthetic','{{"appointment_id":"xyz"}}');""")
    appointment(sql, "confirmed")
    summary = call(sql, "summary")
    assert isinstance(summary["unread_count"], int) and summary["action_item_count"] == 0
    items = call(sql)["items"]
    reminder = next(r for r in items if r["metadata"].get("scheduled_at") == "not-a-date")
    visit = next(r for r in items if r["metadata"].get("appointment_id") == "xyz")
    assert (
        reminder["event_type"] == "med_reminder" and visit["event_type"] == "appointment_reminder"
    )
    assert not reminder["actionable"] and not visit["actionable"]
    assert next(r for r in items if r["event_type"] == "appointment_changed")["actionable"]
    assert call(sql, payload={"unread": True})["items"]
    assert clinician(sql)["items"] == []
