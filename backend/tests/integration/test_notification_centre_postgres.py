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

from tests.integration.supabase_roles import create_roles_sql

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
            input=create_roles_sql(),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        yield command
    finally:
        # --volumes also removes the image's anonymous data volume, which otherwise
        # accumulates with every run and fills the Docker disk.
        subprocess.run(
            [docker, "rm", "--force", "--volumes", container],
            check=True,
            capture_output=True,
            timeout=15,
        )


def apply_clinic_memberships(execute, *, scheduling=True):
    """Apply CLN-003 slices A (065), B (066), C+D (067), E+F (069) and 070, found by name like 063/064."""
    for pattern in (
        "*_clinic_memberships.sql",
        "*_clinic_sign_in_once.sql",
        "*_clinic_lists_and_roles.sql",
        *(
            ("*_clinic_scheduling_and_tags.sql", "*_browser_grants_and_medwatch_preview_audit.sql")
            if scheduling
            else ()
        ),
    ):
        for path in sorted(MIGRATIONS.glob(pattern)):
            execute(path.read_text())


@pytest.fixture
def sql(postgres, request):
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
    execute.command = command
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
        "033_authorization_denial_audit.sql",
        "038_appointment_proposal_lifecycle.sql",
        "039_appointment_patient_changes.sql",
        "040_clinician_approved_care_plans.sql",
        "042_care_plan_publication_review_guards.sql",
        "043_incomplete_care_plan_drafts.sql",
        "042_auditable_adr_assessments.sql",
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
    # Remaining 047/048 ledger entries the ADR loop and the notification sources depend on.
    for name in (
        "047_adr_patient_information_loop.sql",
        "047_care_plan_private_rls_helpers.sql",
        "048_care_team_conversations.sql",
        "048_medwatch_draft_lifecycle.sql",
    ):
        execute((MIGRATIONS / name).read_text())
    execute(Path(__file__).with_name("notification_centre_seed.sql").read_text())
    # Baseline old notices exist before capture installation; old safety rows
    # must never become new shared work. Reminder adapter preserves original rows.
    execute(f"""INSERT INTO notifications(patient_id,notification_type,title,body,is_read) VALUES
      ('{PATIENT}','med_reminder','Old reminder','Synthetic',true),
      ('{PATIENT}','adr_alert','Old internal notice','Do not replay urgent text',false);
      INSERT INTO clinician_messages(clinician_id,patient_id,channel,subject,body) VALUES
      ('{CLINICIAN}','{PATIENT}','in_app','Urgent patient chat escalation','Chat escalation flagged (urgent/general). Historical');""")
    execute((MIGRATIONS / "051_notification_centre.sql").read_text())
    for name in (
        "052_notification_source_times.sql",
        "053_account_deletion_conversations_and_offers.sql",
        "054_notification_page_proportional_reads.sql",
        "055_notification_one_response_per_offer.sql",
        "056_notification_prepare_waits.sql",
        "057_email_delivery.sql",
    ):
        execute((MIGRATIONS / name).read_text())
    # Hosted migrations cannot grant auth privileges to service_role; prove 058 needs none.
    execute(
        "REVOKE ALL ON auth.users FROM service_role; REVOKE USAGE ON SCHEMA auth FROM service_role;"
    )
    execute((MIGRATIONS / "058_email_delivery_fixes.sql").read_text())
    for name in (
        "059_critical_result_alerts.sql",
        "060_critical_result_open_work.sql",
        "061_critical_result_acknowledge.sql",
    ):
        execute((MIGRATIONS / name).read_text())
    # The ADR information-loop lifecycle migration (PV-001-C, PR 2) applies on top of the ledger
    # once it exists. It is found by name, not number, because main keeps taking numbers.
    # ADR_LOOP_GAP_BASELINE=1 skips it to record unmodified behaviour.
    # The Form 3500 migration (PR 3) requires it and follows it in ledger order, so the
    # baseline run skips both.
    if os.environ.get("ADR_LOOP_GAP_BASELINE") != "1":
        for pattern in ("*_adr_information_loop_lifecycle.sql", "*_medwatch_form_3500.sql"):
            for path in sorted(MIGRATIONS.glob(pattern)):
                execute(path.read_text())
    # Clinic memberships (CLN-003 slice A, 065) apply last, so every suite on this fixture
    # runs with them. A test marked before_clinic_memberships seeds pre-065 rows and applies
    # 065 itself to check the backfill.
    if request.node.get_closest_marker("before_clinic_memberships") is None:
        # before_clinic_scheduling stops short of 069 so a test can seed appointments the way
        # the deployed schema holds them and check the backfill and its fail-closed checks.
        apply_clinic_memberships(
            execute, scheduling=request.node.get_closest_marker("before_clinic_scheduling") is None
        )
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


def test_existing_work_keeps_the_time_it_happened(sql):
    """Work captured on a clinician's first load keeps its source time, not the load time."""
    key = document(sql)
    sql(f"UPDATE documents SET created_at=clock_timestamp()-interval '3 days' WHERE id='{key}';")
    # Remove the trigger-captured event (owner only; no role is granted DELETE) so the
    # first load has to capture this pending review as existing work.
    sql(f"DELETE FROM notification_events WHERE source_id='{key}';")
    row = next(r for r in clinician(sql)["items"] if r["source_id"] == key)
    age = sql(
        f"SELECT extract(epoch FROM clock_timestamp()-'{row['created_at']}'::timestamptz)::int;"
    )
    assert int(age) >= 3 * 24 * 3600 - 60


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
    assert clinician(sql, "summary") == {"unread_count": 0, "action_item_count": 0}
    assert clinician(sql, "read_through", {"ids": [row["id"]]}) == {
        "updated_count": 0,
        "skipped_count": 1,
    }
    assert sql(f"SELECT read_at IS NULL FROM notification_receipts WHERE id='{row['id']}'") == "t"
    assert "Notification unavailable" in sql(
        operation("read", {"id": row["id"]}, actor=CLINICIAN, role="clinician"), succeeds=False
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


def test_parallel_request_sees_what_a_concurrent_prepare_delivered(sql):
    send(sql, thread(sql))
    # A refresh sends the summary and the lists together; the summary delivers first.
    summary = sql.start(f"BEGIN; {operation('summary')} SELECT pg_sleep(1); COMMIT;", "summary")
    wait_event(sql, "summary")
    items = call(sql)["items"]
    counted = next(line for line in finish(summary).splitlines() if line.startswith("{"))
    unread = [r["event_type"] for r in items if not r["is_read"]]
    assert "message_received" in unread
    assert len(unread) == json.loads(counted)["unread_count"]


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
        f"SELECT review_adr_assessment('{adr}','{CLINICIAN}','request_information','Reviewed request','[\"dose_response\"]');"
    )
    row = next(r for r in call(sql)["items"] if r["event_type"] == "adr_information_requested")
    assert row["metadata"]["requested_information"] == ["dose_response"]
    assert row["metadata"]["clinician_id"] == CLINICIAN
    assert "PRIVATE" not in json.dumps(row)
    sql(f"SELECT review_adr_assessment('{adr}','{CLINICIAN}','mark_reviewed');")
    assert clinician(sql, "action_items")["items"] == []
    # The same patient item, whichever source captured it (the request after 063).
    assert not next(r for r in call(sql)["items"] if r["id"] == row["id"])["actionable"]


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


def read_thread(sql, conversation, message, *, actor=PATIENT, role="patient"):
    payload = json.dumps({"conversation_id": conversation, "last_message_id": message})
    sql(
        f"SET ROLE service_role; SELECT care_conversation_operation('{actor}','{role}','read','{payload}');"
    )


def test_read_through_marks_authorized_and_skips_the_rest(sql):
    """Mark all read keeps going when one item in the snapshot is no longer visible."""
    foreign_team = str(uuid4())
    sql(f"""INSERT INTO care_teams(id,patient_id,clinician_id,role) VALUES('{foreign_team}','{FOREIGN}','{CLINICIAN}','reviewer');
      INSERT INTO care_teams(patient_id,clinician_id,role) VALUES('{PATIENT}','{OTHER}','reviewer');""")
    mine = {document(sql), document(sql)}
    revoked = document(sql, patient=FOREIGN)
    page = clinician(sql)
    by_source = {r["source_id"]: r["id"] for r in page["items"]}
    assert set(by_source) == mine | {revoked} and len(page["read_ids"]) == 3
    others = [r["id"] for r in clinician(sql, actor=OTHER)["items"]]
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{foreign_team}';")
    snapshot = {"ids": page["read_ids"]}
    assert clinician(sql, "read_through", snapshot) == {"updated_count": 2, "skipped_count": 1}
    read = "SELECT string_agg(e.source_id||':'||(r.read_at IS NOT NULL),',' ORDER BY e.source_id) FROM notification_receipts r JOIN notification_events e ON e.id=r.event_id WHERE r.recipient_id='{0}'"
    expected = ",".join(
        f"{key}:{'true' if key in mine else 'false'}" for key in sorted(mine | {revoked})
    )
    assert sql(read.format(CLINICIAN)) == expected
    # Idempotent: nothing new is marked or audited on retry.
    assert clinician(sql, "read_through", snapshot) == {"updated_count": 0, "skipped_count": 1}
    assert sql("SELECT count(*) FROM notification_read_audit WHERE action='read'") == "2"
    # Another person's receipt is never marked, even inside a snapshot.
    result = clinician(sql, "read_through", {"ids": [*page["read_ids"], *others]})
    assert result == {"updated_count": 0, "skipped_count": 1 + len(others)}
    assert sql(read.format(OTHER)).count(":true") == 0


def test_read_markers_and_legacy_reads_keep_the_unread_index_current(sql):
    conv = thread(sql)
    first = send(sql, conv)
    call(sql)
    read_thread(sql, conv, first["id"])
    second = send(sql, conv)
    read_thread(sql, conv, second["id"])  # read before the centre ever loaded it
    unread_messages = f"""SELECT count(*) FROM notification_receipts r JOIN notification_events e ON e.id=r.event_id
      WHERE r.recipient_id='{PATIENT}' AND e.event_type='message_received' AND r.read_at IS NULL"""
    assert sql(unread_messages) == "0"
    assert all(r["is_read"] for r in call(sql)["items"] if r["event_type"] == "message_received")
    assert sql(unread_messages) == "0"
    legacy = next(r for r in call(sql)["items"] if r["event_type"] == "legacy_update")
    sql(f"UPDATE notifications SET is_read=true WHERE id='{legacy['source_id']}';")
    assert (
        sql(f"SELECT read_at IS NOT NULL FROM notification_receipts WHERE id='{legacy['id']}'")
        == "t"
    )
    assert call(sql, "summary")["unread_count"] == 0
    # Reads made elsewhere are not notification-centre reads, so they write no audit row.
    assert sql("SELECT count(*) FROM notification_read_audit") == "0"


def test_unread_group_appears_once_across_cursor_pages(sql):
    conv = thread(sql)
    for index in range(3):
        send(sql, conv)
        if index < 2:
            sql(f"""INSERT INTO notifications(patient_id,notification_type,title,body)
              VALUES('{PATIENT}','adr_alert','Synthetic {index}','Synthetic');""")
    whole = call(sql)["items"]
    pages, page = [], call(sql, payload={"limit": 1})
    pages.extend(page["items"])
    while page["next_cursor"]:
        page = call(sql, payload={"limit": 1, "before": page["next_cursor"]})
        pages.extend(page["items"])
    assert [r["id"] for r in pages] == [r["id"] for r in whole]
    groups = [r for r in pages if r["event_type"] == "message_received"]
    assert len(groups) == 1 and len(groups[0]["receipt_ids"]) == 3
    unread = call(sql, payload={"unread": True, "limit": 2})
    assert [r["id"] for r in unread["items"]] == [r["id"] for r in whole if not r["is_read"]][:2]


def test_reads_scale_with_the_page_not_the_history(sql):
    """2,000 history items: the first page and the counts evaluate only what they show."""
    sql(f"""INSERT INTO documents(patient_id,uploaded_by,uploaded_by_role,document_type,file_name,file_url,file_size_bytes,review_status)
      SELECT '{PATIENT}','{PATIENT}','patient','other','synthetic-'||n||'.pdf','synthetic',10,'pending'
      FROM generate_series(1,2000) n;""")
    clinician(sql, "summary")  # first load turns 2,000 deliveries into receipts
    sql(f"""UPDATE documents SET review_status='approved';
      UPDATE notification_receipts SET read_at=clock_timestamp() WHERE recipient_id='{CLINICIAN}';""")
    newest = document(sql)

    def measured(action, payload=None):
        encoded = json.dumps(payload or {})
        out = sql(f"""BEGIN; SET LOCAL track_functions='all'; SET ROLE service_role;
          SELECT clock_timestamp()::text;
          SELECT notification_centre_operation('{CLINICIAN}','clinician','{action}','{encoded}'::jsonb);
          SELECT clock_timestamp()::text;
          SELECT pg_stat_get_xact_function_calls('private.notification_row(public.notification_receipts,uuid,text)'::regprocedure);
          COMMIT;""").splitlines()
        started, result, ended, rows = out
        elapsed = sql(f"SELECT extract(epoch FROM '{ended}'::timestamptz-'{started}'::timestamptz)")
        return json.loads(result), int(rows or 0), float(elapsed)

    page, rows, elapsed = measured("list")
    expected = sql(f"""SELECT string_agg(id::text,',' ORDER BY created_at DESC,id DESC) FROM (SELECT id,created_at
      FROM notification_receipts WHERE recipient_id='{CLINICIAN}' ORDER BY created_at DESC,id DESC LIMIT 100) q""")
    expected = expected.split(",")
    assert (
        sql(f"SELECT count(*) FROM notification_receipts WHERE recipient_id='{CLINICIAN}'")
        == "2001"
    )
    assert [r["id"] for r in page["items"]] == expected[:50]
    assert page["items"][0]["source_id"] == newest and page["items"][0]["actionable"]
    assert rows <= 60 and elapsed < 5, (rows, elapsed)
    second, rows, _ = measured("list", {"before": page["next_cursor"]})
    assert [r["id"] for r in second["items"]] == expected[50:100] and rows <= 60
    summary, rows, _ = measured("summary")
    assert summary == {"unread_count": 1, "action_item_count": 1} and rows <= 5, rows
    actions, rows, _ = measured("action_items")
    assert [r["source_id"] for r in actions["items"]] == [newest] and rows <= 5, rows
    assert clinician(sql, "summary", actor=OTHER) == {"unread_count": 0, "action_item_count": 0}


def conversation_with_offers(sql):
    """A thread both people wrote in and read, plus an answered offer, via the real RPCs."""
    conv = thread(sql)
    send(sql, conv, actor=PATIENT, role="patient")
    reply = send(sql, conv)
    read_thread(sql, conv, reply["id"])
    read_thread(sql, conv, reply["id"], actor=CLINICIAN, role="clinician")
    sql(f"""SELECT propose_appointment_slots('{CLINICIAN}','{TEAM}',ARRAY[clock_timestamp()+interval '1 day',
      clock_timestamp()+interval '2 days'],30,'follow_up','Synthetic room','Synthetic');""")
    slot = sql("SELECT id FROM appointments ORDER BY scheduled_at LIMIT 1")
    assert "error" not in sql(
        f"SELECT respond_to_appointment_offer('{PATIENT}','{slot}','accept',NULL);"
    )
    call(sql)
    clinician(sql)
    return conv


HISTORY = """SELECT (SELECT count(*) FROM care_conversations)||','||(SELECT count(*) FROM care_conversation_messages)
  ||','||(SELECT count(*) FROM care_conversation_reads)||','||(SELECT count(*) FROM care_conversation_audit_events)
  ||','||(SELECT count(*) FROM appointment_offer_events)"""


def test_patient_with_conversations_and_offer_history_can_be_deleted(sql):
    conversation_with_offers(sql)
    assert sql(HISTORY) == "1,2,2,5,4"  # opened, 2 sent, 2 read; 2 proposed, accept, withdraw
    sql(f"DELETE FROM auth.users WHERE id='{PATIENT}';")
    assert sql(f"SELECT count(*) FROM patients WHERE id='{PATIENT}'") == "0"
    assert sql(HISTORY) == "0,0,0,0,0"
    assert sql(f"SELECT count(*) FROM clinicians WHERE id='{CLINICIAN}'") == "1"
    assert clinician(sql)["items"] == []


def test_clinician_deletion_keeps_the_patients_thread_readable_in_storage(sql):
    conv = conversation_with_offers(sql)
    sql(f"DELETE FROM auth.users WHERE id='{CLINICIAN}';")
    # The thread, both messages and the patient's marker stay; the clinician's own read
    # marker goes, and references to them become NULL with the sender name kept.
    assert sql(HISTORY) == "1,2,1,5,0"
    assert (
        sql(
            f"SELECT clinician_id IS NULL AND care_team_id IS NULL FROM care_conversations WHERE id='{conv}'"
        )
        == "t"
    )
    assert (
        sql(
            "SELECT string_agg(sender_role||':'||sender_name||':'||(sender_id IS NULL),',' ORDER BY created_at) FROM care_conversation_messages"
        )
        == "patient:Synthetic Patient:false,clinician:First Clinician:true"
    )
    assert (
        sql(f"SELECT actor_id FROM care_conversation_reads WHERE conversation_id='{conv}'")
        == PATIENT
    )
    assert (
        sql("SELECT count(*) FROM care_conversation_audit_events WHERE actor_id IS NULL") == "2"
    )  # its send and read
    # Appointments already go with the care team (001), and their offer audit with them.
    assert sql("SELECT count(*) FROM appointments") == "0"
    assert not any(r["event_type"] == "message_received" for r in call(sql)["items"])


def test_history_tables_keep_no_delete_privilege_and_reject_updates(sql):
    conversation_with_offers(sql)
    for table in (
        "care_conversations",
        "care_conversation_messages",
        "care_conversation_reads",
        "care_conversation_audit_events",
        "appointment_offer_events",
    ):
        for role in ("anon", "authenticated", "service_role"):
            assert sql(f"SELECT has_table_privilege('{role}','{table}','DELETE')") == "f"
        assert "permission denied" in sql(
            f"SET ROLE service_role; DELETE FROM {table};", succeeds=False
        )
    assert "append-only" in sql(
        "UPDATE appointment_offer_events SET action='cancel';", succeeds=False
    )
    assert sql("SELECT count(*) FROM appointment_offer_events") == "4"


def offer(sql, slots=2):
    times = ",".join(f"clock_timestamp()+interval '{n} days'" for n in range(1, slots + 1))
    sql(f"""SELECT propose_appointment_slots('{CLINICIAN}','{TEAM}',ARRAY[{times}],30,'follow_up',
      'Synthetic room','Synthetic');""")
    return sql(
        "SELECT id FROM appointments WHERE status='proposed' ORDER BY created_at DESC,scheduled_at LIMIT 1"
    )


def answer(sql, slot, action):
    result = json.loads(
        sql(f"SELECT respond_to_appointment_offer('{PATIENT}','{slot}','{action}',NULL);")
    )
    assert "error" not in result, result


def test_confirmed_response_is_news_not_needs_attention(sql):
    answer(sql, offer(sql), "accept")
    response = next(r for r in clinician(sql)["items"] if r["event_type"] == "appointment_response")
    assert not response["actionable"] and not response["can_acknowledge"]
    assert not response["is_read"]
    assert clinician(sql, "action_items")["items"] == []
    assert clinician(sql, "summary") == {"unread_count": 1, "action_item_count": 0}
    assert "cannot be acknowledged" in sql(
        operation("acknowledge", {"id": response["id"]}, actor=CLINICIAN, role="clinician"),
        succeeds=False,
    )


def test_request_for_another_time_needs_attention_until_acknowledged(sql):
    sql(
        f"INSERT INTO care_teams(patient_id,clinician_id,role) VALUES('{PATIENT}','{OTHER}','reviewer');"
    )
    answer(sql, offer(sql, slots=3), "request_alternative")
    # Every slot of the offer changed; the answer is one notification, on the lowest-ID slot.
    events = "SELECT string_agg(source_id::text,',') FROM notification_events WHERE event_type='appointment_response'"
    assert sql(events) == sql("SELECT min(id::text) FROM appointments")
    history = [r for r in clinician(sql)["items"] if r["event_type"] == "appointment_response"]
    assert len(history) == 1 and not history[0]["is_read"]
    assert clinician(sql, "summary") == {"unread_count": 1, "action_item_count": 1}
    items = clinician(sql, "action_items")["items"]
    assert len(items) == 1 and items[0]["event_type"] == "appointment_response"
    assert items[0]["id"] == history[0]["id"]
    assert items[0]["can_acknowledge"] and items[0]["metadata"]["status"] == "alternative_requested"
    assert clinician(sql, "summary")["action_item_count"] == 1
    assert clinician(sql, "action_items", actor=OTHER)["items"] == []
    note = {"id": items[0]["id"], "note": "Calling the patient"}
    clinician(sql, "acknowledge", note)
    clinician(sql, "acknowledge", note)  # idempotent retry
    assert clinician(sql, "action_items")["items"] == []
    assert clinician(sql, "summary")["action_item_count"] == 0
    history = next(r for r in clinician(sql)["items"] if r["id"] == items[0]["id"])
    assert not history["actionable"] and not history["can_acknowledge"]
    assert sql("SELECT count(*) FROM notification_read_audit WHERE action='acknowledge'") == "1"
    assert sql("SELECT string_agg(DISTINCT status::text,',') FROM appointments") == (
        "alternative_requested"
    )


def test_a_later_offer_answers_a_declined_response(sql):
    answer(sql, offer(sql), "decline")
    assert [r["event_type"] for r in clinician(sql, "action_items")["items"]] == [
        "appointment_response"
    ]
    offer(sql)
    assert clinician(sql, "action_items")["items"] == []
    assert clinician(sql, "summary")["action_item_count"] == 0
    assert any(r["event_type"] == "appointment_response" for r in clinician(sql)["items"])


def test_cancelled_visit_needs_attention_whatever_its_time(sql):
    sql("ALTER TABLE appointments DISABLE TRIGGER appointments_booking_guard;")
    key = appointment(sql, "confirmed", when="-1 hour")
    sql(f"UPDATE appointments SET status='cancelled' WHERE id='{key}';")
    sql("ALTER TABLE appointments ENABLE TRIGGER appointments_booking_guard;")
    items = clinician(sql, "action_items")["items"]
    assert [(r["source_id"], r["can_acknowledge"]) for r in items] == [(key, True)]


def result(sql, doc, *, flag_meaning="critical", state="pending_review"):
    """A lab-result candidate cited to ``doc``, as document grounding writes it."""
    fact, provenance = str(uuid4()), str(uuid4())
    value = json.dumps({"test_name": "Potassium", "value": "6.9", "flag_meaning": flag_meaning})
    sql(f"""INSERT INTO clinical_facts(id,patient_id,fact_type,subject_type,value,review_state)
      VALUES('{fact}','{PATIENT}','lab_result','lab_result','{value}'::jsonb,'{state}');
      INSERT INTO source_provenances(id,artifact_type,source_system,source_reference,document_id)
      VALUES('{provenance}','document','document_intelligence','document:{doc}','{doc}');
      INSERT INTO evidence_citations(fact_id,provenance_id,excerpt)
      VALUES('{fact}','{provenance}','Potassium | 6.9 | HH');""")
    return fact


def critical_events(sql, doc):
    rows = sql(f"""SELECT e.audience||'|'||coalesce((SELECT string_agg(d.recipient_id::text,','
        ORDER BY d.recipient_id) FROM notification_pending_deliveries d WHERE d.event_id=e.id),'')
      FROM notification_events e WHERE e.event_type='critical_result' AND e.source_id='{doc}'""")
    return [tuple(row.split("|")) for row in rows.splitlines()]


def test_critical_result_alerts_the_care_team_once_per_document(sql):
    doc = document(sql)
    result(sql, doc)
    result(sql, doc)  # a second critical result on the same report adds no second alert
    assert critical_events(sql, doc) == [("shared", CLINICIAN)]
    rows = [row for row in clinician(sql)["items"] if row["event_type"] == "critical_result"]
    assert len(rows) == 1 and rows[0]["source_id"] == doc and rows[0]["actionable"]
    assert rows[0]["category"] == "safety"
    # The patient is told by their own explanation; they never receive this alert.
    assert all(row["event_type"] != "critical_result" for row in call(sql)["items"])


def test_non_critical_or_rejected_results_raise_no_alert(sql):
    doc = document(sql)
    result(sql, doc, flag_meaning="high")
    result(sql, doc, state="rejected")
    assert critical_events(sql, doc) == []


def test_critical_alert_stops_being_work_when_the_document_is_rejected(sql):
    doc = document(sql)
    result(sql, doc)
    sql(f"UPDATE documents SET review_status='rejected' WHERE id='{doc}'")
    rows = [
        row
        for row in clinician(sql)["items"]
        if row["source_id"] == doc and row["event_type"] == "critical_result"
    ]
    assert rows == [] or not rows[0]["actionable"]


def test_critical_result_is_open_work_until_acknowledged(sql):
    doc = document(sql)
    result(sql, doc)
    items = [
        row
        for row in clinician(sql, "action_items")["items"]
        if row["event_type"] == "critical_result" and row["source_id"] == doc
    ]
    assert len(items) == 1 and items[0]["can_acknowledge"]
    clinician(sql, "acknowledge", {"id": items[0]["id"], "note": "Reviewed the document"})
    assert all(
        row["source_id"] != doc or row["event_type"] != "critical_result"
        for row in clinician(sql, "action_items")["items"]
    )


# ── CLN-003 slice C (067): the clinic filter and the link's clinic on each item ──────────

SECOND_NOTIFICATION_CLINIC = "00000000-0000-0000-0000-0000000000a8"


def test_clinic_filter_and_link_clinic_on_notification_items(sql):
    first_clinic = sql(f"SELECT clinic_id FROM clinicians WHERE id='{CLINICIAN}'")
    sql(
        f"""INSERT INTO clinics(id,display_name,canonical_name)
        VALUES('{SECOND_NOTIFICATION_CLINIC}','Second synthetic clinic','second synthetic clinic');
      SET ROLE service_role;
      INSERT INTO clinic_memberships(clinician_id,clinic_id,role)
        VALUES('{CLINICIAN}','{SECOND_NOTIFICATION_CLINIC}','provider');
      INSERT INTO care_teams(patient_id,clinician_id,role,clinic_id)
        VALUES('{FOREIGN}','{CLINICIAN}','primary_care','{SECOND_NOTIFICATION_CLINIC}');"""
    )
    here = document(sql, patient=PATIENT)
    there = document(sql, patient=FOREIGN)

    everything = clinician(sql)["items"]
    assert {r["source_id"] for r in everything} == {here, there}
    # Each item names the clinic of the clinician's link, not the default clinic.
    assert {r["source_id"]: r["clinic_id"] for r in everything} == {
        here: first_clinic,
        there: SECOND_NOTIFICATION_CLINIC,
    }
    assert {r["clinic_name"] for r in everything if r["source_id"] == there} == {
        "Second synthetic clinic"
    }

    for action in ("list", "action_items"):
        own = clinician(sql, action, {"clinic_id": SECOND_NOTIFICATION_CLINIC})["items"]
        assert {r["source_id"] for r in own} == {there}, action
        # A clinic the caller does not belong to, or that does not exist, is just empty.
        for stranger in (str(uuid4()),):
            assert clinician(sql, action, {"clinic_id": stranger})["items"] == [], action
    sql(
        f"SET ROLE service_role; UPDATE clinic_memberships SET status='inactive' "
        f"WHERE clinician_id='{CLINICIAN}' AND clinic_id='{SECOND_NOTIFICATION_CLINIC}';"
    )
    assert clinician(sql, "list", {"clinic_id": SECOND_NOTIFICATION_CLINIC})["items"] == []
    # Patients never take the filter.
    assert call(sql, "list", {"clinic_id": str(uuid4())})["items"] is not None
