"""ADR information-loop lifecycle in disposable offline PostgreSQL 16 (PV-001-C, PR 2).

Reuses the notification-centre fixture, which applies the real ledger. With
ADR_LOOP_GAP_BASELINE=1 the lifecycle migration is skipped, so the reproduction tests
below record unmodified behaviour first; without it they prove the fix.
"""

import json
import os
from uuid import uuid4

import pytest

from tests.integration.test_email_postgres import account, delivery, verified
from tests.integration.test_notification_centre_postgres import (
    CLINICIAN,
    FOREIGN,
    OTHER,
    PATIENT,
    TEAM,
    call,
    clinician,
)

pytest_plugins = ["tests.integration.test_notification_centre_postgres"]

pytestmark = pytest.mark.skipif(
    os.environ.get("NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER") != "1",
    reason="explicit opt-in disposable Docker PostgreSQL contract check",
)


def assessment(sql, *, patient=PATIENT):
    """A draft ADR assessment on synthetic medication and symptom rows."""
    med, symptom, adr = str(uuid4()), str(uuid4()), str(uuid4())
    sql(f"""INSERT INTO medications(id,patient_id,name,dosage,frequency) VALUES('{med}','{patient}','Synthetic medication','Synthetic','daily');
      INSERT INTO symptom_reports(id,patient_id,symptom,severity) VALUES('{symptom}','{patient}','Synthetic symptom',1);
      INSERT INTO adr_assessments(id,patient_id,symptom_report_id,suspect_medication_id,suspect_medication_name,naranjo_score,causality,thinking_chain)
      VALUES('{adr}','{patient}','{symptom}','{med}','Synthetic medication',0,'Doubtful','PRIVATE MUST NOT LEAK');""")
    return adr


def review(sql, adr, action, questions=(), *, actor=CLINICIAN):
    note = "NULL" if action == "mark_reviewed" else "'Synthetic review note'"
    sql(
        f"SET ROLE service_role; SELECT id FROM review_adr_assessment('{adr}','{actor}','{action}',{note},'{json.dumps(list(questions))}');"
    )


def request(sql, adr, questions=("dose_response",), *, actor=CLINICIAN):
    review(sql, adr, "request_information", questions, actor=actor)
    return sql(
        f"SELECT id FROM adr_information_requests WHERE adr_assessment_id='{adr}' AND status='pending'"
    )


def respond(request_id, *, patient=PATIENT):
    """The respond RPC call with a valid payload, as the backend sends it."""
    responses = json.dumps(
        [
            {"question": "dose_response", "answer": "yes", "evidence": "Synthetic description"},
        ]
    )
    return f"""SET ROLE service_role; SELECT id FROM respond_to_adr_information_request('{request_id}','{patient}',
      '{responses}'::jsonb,'{{"dose_response":"yes"}}'::jsonb,'{{"score":1}}'::jsonb,
      '[{{"question":"dose_response","answer":"yes","source":"patient_follow_up"}}]'::jsonb,1::smallint,'Doubtful');"""


def answer(sql, request_id, *, patient=PATIENT):
    sql(respond(request_id, patient=patient))


def draft(sql, adr, *, actor=CLINICIAN):
    return sql(f"""SET ROLE service_role; SELECT id FROM create_medwatch_draft('{adr}','{actor}',
      '{{"event":{{"description":"Synthetic"}}}}'::jsonb,'[]'::jsonb,'Synthetic rationale');""")


def requested(sql, *, actor=PATIENT):
    return [
        r for r in call(sql, actor=actor)["items"] if r["event_type"] == "adr_information_requested"
    ]


def request_events(sql, *, patient=PATIENT):
    return int(
        sql(
            f"SELECT count(*) FROM notification_events WHERE patient_id='{patient}' AND event_type='adr_information_requested'"
        )
    )


# Reproductions (NEEDS REPRO criteria). Each was run against the unmodified ledger first.


def test_answer_creates_no_new_patient_request_event(sql):
    """R9.1: answering must not re-capture the patient's request event."""
    request_id = request(sql, assessment(sql))
    assert request_events(sql) == 1
    answer(sql, request_id)
    assert request_events(sql) == 1


def test_answered_request_item_is_history(sql):
    """R9.2: after the answer no request item asks the patient for action."""
    request_id = request(sql, assessment(sql))
    assert [r["actionable"] for r in requested(sql)] == [True]
    answer(sql, request_id)
    rows = requested(sql)
    assert rows and not any(r["actionable"] for r in rows)


def test_one_patient_item_per_request(sql):
    """R10.1: one request shows the patient exactly one new item."""
    before = {r["id"] for r in call(sql)["items"]}
    request(sql, assessment(sql))
    new = [r for r in call(sql)["items"] if r["id"] not in before]
    assert [r["event_type"] for r in new] == ["adr_information_requested"]


def test_patient_deletion_after_answer_with_medwatch_draft(sql):
    """R12.1 to R12.3: deleting an answering patient removes their ADR and MedWatch data only."""
    sql(
        f"INSERT INTO care_teams(patient_id,clinician_id,role) VALUES('{FOREIGN}','{CLINICIAN}','primary_care');"
    )
    adr = assessment(sql)
    answer(sql, request(sql, adr))
    medwatch = draft(sql, adr)
    other = assessment(sql, patient=FOREIGN)
    answer(sql, request(sql, other), patient=FOREIGN)
    owned = f"""SELECT (SELECT count(*) FROM adr_information_requests WHERE patient_id='{PATIENT}')||','||
      (SELECT count(*) FROM adr_assessment_audit_events WHERE adr_assessment_id='{adr}')||','||
      (SELECT count(*) FROM adr_assessment_audit_events WHERE patient_actor_id='{PATIENT}')||','||
      (SELECT count(*) FROM medwatch_drafts WHERE patient_id='{PATIENT}')||','||
      (SELECT count(*) FROM medwatch_draft_audit_events WHERE medwatch_draft_id='{medwatch}')"""
    assert sql(owned) == "1,3,1,1,1"  # requested, answered, marked reviewed by the draft
    foreign = f"""SELECT (SELECT count(*) FROM adr_information_requests WHERE patient_id='{FOREIGN}')||','||
      (SELECT count(*) FROM adr_assessment_audit_events WHERE adr_assessment_id='{other}')"""
    assert sql(foreign) == "1,2"
    sql(f"DELETE FROM auth.users WHERE id='{PATIENT}';")
    assert sql(f"SELECT count(*) FROM patients WHERE id='{PATIENT}'") == "0"
    assert sql(owned) == "0,0,0,0,0"
    assert sql(foreign) == "1,2"
    assert sql(f"SELECT count(*) FROM clinicians WHERE id='{CLINICIAN}'") == "1"


def test_superseded_request_is_history(sql):
    """R13.2: a replaced request is History and only the newer one asks for action."""
    adr = assessment(sql)
    first = request(sql, adr)
    requested(sql)
    second = request(sql, adr, ("similar_previous_reaction",))
    assert first != second
    rows = requested(sql)
    active = [r for r in rows if r["actionable"]]
    assert len(rows) == 2 and len(active) == 1
    assert active[0]["created_at"] == max(r["created_at"] for r in rows)


# R9: answering resolves the patient's item.


def receipts(sql, request_id):
    """The patient's receipt read state and read-audit count for one request's item."""
    return sql(f"""SELECT string_agg((r.read_at IS NOT NULL)::text||':'||(SELECT count(*) FROM notification_read_audit a
        WHERE a.receipt_id=r.id AND a.action='read' AND a.actor_id='{PATIENT}'),',')
      FROM notification_receipts r JOIN notification_events e ON e.id=r.event_id
      WHERE r.recipient_id='{PATIENT}' AND e.source_id='{request_id}' AND e.event_type='adr_information_requested'""")


@pytest.mark.parametrize("delivered", [True, False])
def test_answer_marks_the_request_receipt_read_with_audit(sql, delivered):
    """R9.3: read with one read-audit row, also when the item was never delivered."""
    request_id = request(sql, assessment(sql))
    if delivered:
        call(sql)
        assert receipts(sql, request_id) == "false:0"
    answer(sql, request_id)
    assert receipts(sql, request_id) == "true:1"
    [row] = requested(sql)
    assert row["is_read"] and not row["actionable"]


def test_assessment_touch_creates_no_patient_event(sql):
    """R9.4: a rescore, evidence change or updated_at touch is not a new request."""
    adr = assessment(sql)
    request(sql, adr)
    sql(f"""UPDATE adr_assessments SET updated_at=clock_timestamp(),naranjo_score=2,
      evidence='[{{"question":"dose_response","answer":"yes"}}]' WHERE id='{adr}';""")
    assert request_events(sql) == 1
    assert [r["actionable"] for r in requested(sql)] == [True]


def test_answer_queues_no_repeated_request_email(sql):
    """R9.5: one records notice for the request, none after the answer."""
    verified(sql)
    account(sql, "preferences", {"records": True})
    request_id = request(sql, assessment(sql))
    call(sql)
    notices = f"SELECT count(*) FROM email_outbox WHERE kind='notice' AND user_id='{PATIENT}'"
    assert sql(notices) == "1"
    answer(sql, request_id)
    call(sql)
    assert sql(notices) == "1"
    assert not any(row["kind"] == "notice" for row in delivery(sql)["items"])


def test_answer_leaves_earlier_events_unchanged(sql):
    """R9.6: history is append only."""
    request_id = request(sql, assessment(sql))
    call(sql)
    ids = sql("SELECT string_agg(id::text,',' ORDER BY id) FROM notification_events")
    snapshot = (
        "SELECT string_agg(e::text,'|' ORDER BY e.id) FROM notification_events e"
        f" WHERE e.id=ANY(string_to_array('{ids}',',')::uuid[])"
    )
    before = sql(snapshot)
    answer(sql, request_id)
    assert sql(snapshot) == before


def test_request_event_belongs_to_its_request(sql):
    """R9.7: the patient item is sourced from, and names, its information request."""
    adr = assessment(sql)
    request_id = request(sql, adr)
    [row] = requested(sql)
    assert row["source_type"] == "adr_information_requests" and row["source_id"] == request_id
    assert row["metadata"]["information_request_id"] == request_id
    assert row["metadata"]["adr_assessment_id"] == adr
    assert row["metadata"]["requested_information"] == ["dose_response"]
    assert row["metadata"]["clinician_id"] == CLINICIAN
    assert "PRIVATE" not in json.dumps(row) and "Synthetic review note" not in json.dumps(row)


# R10: one request, one patient notification.


def test_request_creates_no_legacy_notification_and_answers_without_one(sql):
    """R10.2, R10.5: no English-only row is written, and the answer needs none."""
    before = sql("SELECT count(*) FROM notifications")
    request_id = request(sql, assessment(sql))
    assert sql("SELECT count(*) FROM notifications") == before
    answer(sql, request_id)
    assert sql(f"SELECT status FROM adr_information_requests WHERE id='{request_id}'") == "answered"


def test_existing_legacy_rows_and_events_are_unchanged(sql):
    """R10.4: a pre-migration legacy row stays History and is still marked read."""
    request_id = request(sql, assessment(sql))
    sql(f"""INSERT INTO notifications(patient_id,notification_type,title,body,action_url,dedupe_key,metadata)
      VALUES('{PATIENT}','adr_alert','Your care team has follow-up questions','Synthetic legacy body','/chat',
        'adr-information-request:{request_id}','{{"adr_information_request_id":"{request_id}"}}');""")
    legacy = sql(
        f"SELECT id FROM notifications WHERE dedupe_key='adr-information-request:{request_id}'"
    )
    event = f"SELECT e::text FROM notification_events e WHERE e.source_id='{legacy}'"
    captured = sql(event)
    item = next(r for r in call(sql)["items"] if r["source_id"] == legacy)
    assert item["event_type"] == "legacy_update" and not item["actionable"]
    answer(sql, request_id)
    assert sql(event) == captured
    assert sql(f"SELECT is_read FROM notifications WHERE id='{legacy}'") == "t"
    assert next(r for r in call(sql)["items"] if r["source_id"] == legacy)["is_read"]


# R11: clinician alert when a patient answers.


def answered(sql, request_id):
    return sql(f"""SELECT e.event_key||'|'||e.audience||'|'||e.category||'|'||coalesce((SELECT string_agg(d.recipient_id::text,','
        ORDER BY d.recipient_id) FROM notification_pending_deliveries d WHERE d.event_id=e.id),'')
      FROM notification_events e WHERE e.event_type='adr_information_answered' AND e.source_id='{request_id}'""")


def test_answer_alerts_assigned_clinicians_once_as_history(sql):
    """R11.1, R11.5, R11.7: one shared, History-only, unread alert per request."""
    sql(
        f"INSERT INTO care_teams(patient_id,clinician_id,role) VALUES('{PATIENT}','{OTHER}','reviewer');"
    )
    adr = assessment(sql)
    request_id = request(sql, adr)
    assert answered(sql, request_id) == ""
    needs = clinician(sql, "summary")["action_item_count"]
    answer(sql, request_id)
    key = f"adr_information_requests:{request_id}:answered"
    assert answered(sql, request_id) == f"{key}|shared|safety|{CLINICIAN},{OTHER}"
    for actor in (CLINICIAN, OTHER):
        [row] = [
            r
            for r in clinician(sql, actor=actor)["items"]
            if r["event_type"] == "adr_information_answered"
        ]
        assert row["source_id"] == request_id and row["category"] == "safety"
        assert not row["actionable"] and not row["is_read"] and not row["can_acknowledge"]
        assert row["metadata"] == {"adr_assessment_id": adr, "information_request_id": request_id}
        assert all(
            r["event_type"] != "adr_information_answered"
            for r in clinician(sql, "action_items", actor=actor)["items"]
        )
    assert clinician(sql, "summary")["action_item_count"] == needs
    assert "already been completed" in sql(respond(request_id), succeeds=False)
    # Even if the request passed through answered again, the event key keeps one alert.
    sql(f"""UPDATE adr_information_requests SET status='pending' WHERE id='{request_id}';
      UPDATE adr_information_requests SET status='answered' WHERE id='{request_id}';""")
    assert answered(sql, request_id) == f"{key}|shared|safety|{CLINICIAN},{OTHER}"


def test_answered_alert_follows_current_assignment(sql):
    """R11.3, R11.4: assigned clinicians only; never the patient or an unassigned clinician."""
    request_id = request(sql, assessment(sql))
    answer(sql, request_id)

    def alerts(rows):
        return [r for r in rows if r["event_type"] == "adr_information_answered"]

    assert len(alerts(clinician(sql)["items"])) == 1
    assert alerts(clinician(sql, actor=OTHER)["items"]) == []
    assert alerts(call(sql)["items"]) == []
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{TEAM}';")
    assert alerts(clinician(sql)["items"]) == []


def test_answered_alert_creates_no_email(sql):
    """R11.8: the alert maps to no email category."""
    verified(sql, actor=CLINICIAN, role="clinician")
    account(
        sql, "preferences", {"reviews": True, "records": True}, actor=CLINICIAN, role="clinician"
    )
    request_id = request(sql, assessment(sql))
    answer(sql, request_id)
    clinician(sql)
    assert sql("SELECT private.email_preference('adr_information_answered') IS NULL") == "t"
    assert (
        sql("""SELECT count(*) FROM email_outbox o JOIN notification_receipts r ON r.id=o.receipt_id
      JOIN notification_events e ON e.id=r.event_id WHERE e.event_type='adr_information_answered'""")
        == "0"
    )


@pytest.mark.parametrize("table", ["notification_events", "notification_read_audit"])
def test_capture_or_read_audit_failure_rolls_back_the_answer(sql, table):
    """R11.9: capture and the read audit are part of the answer's transaction."""
    adr = assessment(sql)
    request_id = request(sql, adr)
    call(sql)
    sql(f"""CREATE FUNCTION reject_adr() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Synthetic outage'; END $$;
      CREATE TRIGGER reject_adr BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION reject_adr();""")
    assert "Synthetic outage" in sql(respond(request_id), succeeds=False)
    assert sql(f"SELECT status FROM adr_information_requests WHERE id='{request_id}'") == "pending"
    assert sql(f"SELECT naranjo_score FROM adr_assessments WHERE id='{adr}'") == "0"
    assert (
        sql(
            "SELECT count(*) FROM adr_assessment_audit_events WHERE event_type='patient_information_provided'"
        )
        == "0"
    )


# R12: deletion boundaries.


def test_no_role_can_delete_adr_or_medwatch_audit(sql):
    """R12.4: the patient cascade is the only removal path."""
    adr = assessment(sql)
    answer(sql, request(sql, adr))
    draft(sql, adr)
    for table in ("adr_assessment_audit_events", "medwatch_draft_audit_events"):
        for role in ("anon", "authenticated", "service_role"):
            for privilege in ("DELETE", "TRUNCATE"):
                assert sql(f"SELECT has_table_privilege('{role}','{table}','{privilege}')") == "f"
        assert "permission denied" in sql(
            f"SET ROLE service_role; DELETE FROM {table};", succeeds=False
        )
    assert sql("SELECT count(*) FROM adr_assessment_audit_events") == "3"


def test_clinician_deletion_is_still_blocked(sql):
    """R12.5: clinician references keep RESTRICT until decision D1."""
    request(sql, assessment(sql))
    assert "violates foreign key constraint" in sql(
        f"DELETE FROM auth.users WHERE id='{CLINICIAN}';", succeeds=False
    )
    assert sql(f"SELECT count(*) FROM clinicians WHERE id='{CLINICIAN}'") == "1"


# R13: cancelled and superseded requests.


@pytest.mark.parametrize("action", ["mark_reviewed", "dismiss", "draft", "superseded"])
def test_closed_request_is_history_with_its_unread_state_kept(sql, action):
    """R13.1, R13.3, R13.4: History, still unread, and nothing deleted."""
    adr = assessment(sql)
    request_id = request(sql, adr)
    call(sql)
    if action == "draft":
        draft(sql, adr)
    elif action == "superseded":
        request(sql, adr)
    else:
        review(sql, adr, action)
    row = next(r for r in requested(sql) if r["source_id"] == request_id)
    assert not row["actionable"] and not row["is_read"]
    assert (
        sql(f"SELECT status FROM adr_information_requests WHERE id='{request_id}'") == "cancelled"
    )
    assert sql(f"SELECT count(*) FROM notification_events WHERE source_id='{request_id}'") == "1"
    assert sql(
        f"SELECT count(*) FROM adr_assessment_audit_events WHERE adr_assessment_id='{adr}' AND event_type='information_requested'"
    ) == ("2" if action == "superseded" else "1")


# Feature: adr-loop-gap-fixes, Property 7: At most one actionable patient request item,
# and it belongs to the pending request.
SEQUENCES = [
    ("request",),
    ("request", "answer"),
    ("request", "re-request"),
    ("request", "mark_reviewed"),
    ("request", "dismiss"),
    ("request", "draft"),
    ("request", "touch"),
    ("request", "answer", "re-request"),
    ("request", "answer", "mark_reviewed"),
    ("request", "answer", "draft"),
    ("request", "re-request", "answer"),
    ("request", "touch", "answer"),
    ("request", "re-request", "dismiss"),
    ("touch", "request", "answer"),
]


@pytest.mark.parametrize("sequence", SEQUENCES, ids="+".join)
def test_one_actionable_item_follows_the_pending_request(sql, sequence):
    adr = assessment(sql)
    pending = f"SELECT id FROM adr_information_requests WHERE adr_assessment_id='{adr}' AND status='pending'"
    for step in sequence:
        if step in ("request", "re-request"):
            request(sql, adr)
        elif step == "answer":
            answer(sql, sql(pending))
        elif step == "draft":
            draft(sql, adr)
        elif step == "touch":
            sql(f"UPDATE adr_assessments SET updated_at=clock_timestamp() WHERE id='{adr}';")
        else:
            review(sql, adr, step)
        current = sql(pending)
        active = [r for r in requested(sql) if r["actionable"]]
        assert [r["source_id"] for r in active] == ([current] if current else []), step
