"""Notification centre and email follow record ownership (087) in a disposable PostgreSQL 16.

A patient with two care teams: a clinician of team B must not be told about, shown, emailed
about, or able to open an item for a record team A owns. Critical-result alerts and pending
ADR assessments stay shared; a "Not sure" document is in every active team's queue until one
clinician claims it. Opt-in: ``CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER=1``. Synthetic data only.
"""

from __future__ import annotations

import json
import os
from uuid import uuid4

import pytest

from tests.integration.care_team_plan_harness import (
    CLINIC,
    CLINICIAN,
    OTHER,
    OTHER_CLINIC,
    OTHER_TEAM,
    PATIENT,
    TEAM,
    THIRD,
    THIRD_TEAM,
    link,
    seed_people,
)
from tests.integration.test_care_team_records_postgres import document, fact

pytest_plugins = ["tests.integration.care_team_plan_harness"]

pytestmark = [
    # The first test builds the template databases for the module.
    pytest.mark.timeout(600),
    pytest.mark.skipif(
        os.environ.get("CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER") != "1",
        reason="explicit opt-in disposable Docker PostgreSQL contract check",
    ),
]

REFUSED = "Notification unavailable"


def two_teams(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)


def centre(sql, actor, action="list", payload=None, role="clinician", succeeds=True):
    statement = (
        "SET ROLE service_role; SELECT public.notification_centre_operation("
        f"'{actor}','{role}','{action}',$p${json.dumps(payload or {})}$p$::jsonb);"
    )
    out = sql(statement, succeeds=succeeds)
    return json.loads(out.splitlines()[-1]) if succeeds else out


def items(sql, actor, kind=None):
    rows = centre(sql, actor)["items"]
    return [row for row in rows if kind is None or row["event_type"] == kind]


def recipients(sql, source, kind) -> list[str]:
    """Clinicians holding a pending delivery for the source's event, before anyone opens it."""
    out = sql(f"""SELECT d.recipient_id FROM notification_pending_deliveries d
      JOIN notification_events e ON e.id=d.event_id
      WHERE e.source_id='{source}' AND e.event_type='{kind}' AND d.recipient_role='clinician'
      ORDER BY d.recipient_id""")
    return out.splitlines()


def seen_by(sql, source, kind) -> list[str]:
    """Clinicians whose centre lists the item."""
    return [
        who
        for who in (CLINICIAN, OTHER, THIRD)
        if any(row["source_id"] == source for row in items(sql, who, kind))
    ]


def pending_doc(sql, **kwargs) -> str:
    return document(sql, parse="completed", review="pending", **kwargs)


# ── Patient-uploaded document awaiting review ─────────────────────────────────────────────


def test_a_routed_upload_alerts_only_the_owning_team(sql):
    two_teams(sql)
    doc = pending_doc(sql, team=TEAM)

    assert recipients(sql, doc, "document_review") == [CLINICIAN]
    assert seen_by(sql, doc, "document_review") == [CLINICIAN]


def test_the_other_team_is_alerted_to_its_own_upload_not_the_first_teams(sql):
    two_teams(sql)
    first, second = pending_doc(sql, team=TEAM), pending_doc(sql, team=OTHER_TEAM)

    assert seen_by(sql, first, "document_review") == [CLINICIAN]
    assert seen_by(sql, second, "document_review") == [OTHER]


def test_not_sure_reaches_every_active_team_and_no_stranger(sql):
    two_teams(sql)
    doc = pending_doc(sql, state="unrouted")

    assert recipients(sql, doc, "document_review") == sorted([CLINICIAN, OTHER])
    assert seen_by(sql, doc, "document_review") == [CLINICIAN, OTHER]  # THIRD has no link


def test_a_claim_takes_the_item_out_of_the_other_teams_centre_and_it_cannot_be_opened(sql):
    two_teams(sql)
    doc = pending_doc(sql, state="unrouted")
    theirs = next(row for row in items(sql, OTHER, "document_review") if row["source_id"] == doc)

    sql(f"SET ROLE service_role; SELECT public.claim_document('{doc}','{CLINICIAN}','{TEAM}');")

    assert seen_by(sql, doc, "document_review") == [CLINICIAN]
    for action in ("read", "acknowledge"):
        assert REFUSED in centre(sql, OTHER, action, {"id": theirs["id"]}, succeeds=False)
    # The unread marker is untouched: a refused open changes nothing.
    assert (
        sql(f"SELECT read_at IS NULL FROM notification_receipts WHERE id='{theirs['id']}'") == "t"
    )


def test_a_clinician_without_a_link_gets_nothing_and_cannot_open_anything(sql):
    two_teams(sql)
    doc = pending_doc(sql, state="unrouted")
    receipt = items(sql, CLINICIAN, "document_review")[0]["id"]

    assert items(sql, THIRD) == []
    assert recipients(sql, doc, "document_review") == sorted([CLINICIAN, OTHER])
    assert REFUSED in centre(sql, THIRD, "read", {"id": receipt}, succeeds=False)
    assert centre(sql, THIRD, "summary") == {"unread_count": 0, "action_item_count": 0}


def test_a_team_linked_later_receives_open_not_sure_work_but_not_a_routed_upload(sql):
    two_teams(sql)
    routed, unrouted = pending_doc(sql, team=TEAM), pending_doc(sql, state="unrouted")
    link(sql, THIRD_TEAM, THIRD, CLINIC)

    assert seen_by(sql, routed, "document_review") == [CLINICIAN]
    assert THIRD in seen_by(sql, unrouted, "document_review")


def test_a_routed_upload_whose_owner_link_was_removed_alerts_nobody(sql):
    two_teams(sql)
    doc = pending_doc(sql, team=TEAM)
    sql(f"DELETE FROM care_teams WHERE id='{TEAM}';")

    assert seen_by(sql, doc, "document_review") == []


# ── Document processing outcome ───────────────────────────────────────────────────────────


def test_a_failed_parse_reaches_the_owning_team_only(sql):
    two_teams(sql)
    doc = document(sql, team=TEAM, parse="processing", review="pending")
    sql(f"UPDATE documents SET parse_status='failed' WHERE id='{doc}';")

    assert recipients(sql, doc, "document_failed") == [CLINICIAN]
    assert seen_by(sql, doc, "document_failed") == [CLINICIAN]


def test_a_failed_parse_of_a_not_sure_document_reaches_every_active_team(sql):
    two_teams(sql)
    doc = document(sql, state="unrouted", parse="processing", review="pending")
    sql(f"UPDATE documents SET parse_status='failed' WHERE id='{doc}';")

    assert seen_by(sql, doc, "document_failed") == [CLINICIAN, OTHER]


# ── Critical results stay shared, without the document ─────────────────────────────────────


def critical(sql, doc) -> str:
    fact(sql, doc, kind="lab_result", value='{"name":"Potassium","flag_meaning":"critical"}')
    return doc


def test_a_critical_result_reaches_every_team_but_only_the_owner_gets_the_document(sql):
    two_teams(sql)
    doc = critical(sql, document(sql, team=TEAM, review="pending"))

    assert seen_by(sql, doc, "critical_result") == [CLINICIAN, OTHER]
    owner = items(sql, CLINICIAN, "critical_result")[0]
    other = items(sql, OTHER, "critical_result")[0]
    assert "source_accessible" not in owner["metadata"]
    assert other["metadata"]["source_accessible"] is False
    # The neutral item carries no test name or value for either team.
    assert "Potassium" not in json.dumps(other) + json.dumps(owner)
    # And it can still be acknowledged by the team that cannot open the document.
    assert centre(sql, OTHER, "acknowledge", {"id": other["id"]})["updated_count"] == 1


def test_a_critical_result_on_a_not_sure_document_is_openable_by_every_team(sql):
    two_teams(sql)
    critical(sql, document(sql, state="unrouted", review="pending"))

    for who in (CLINICIAN, OTHER):
        assert "source_accessible" not in items(sql, who, "critical_result")[0]["metadata"]


# ── Care-plan draft ────────────────────────────────────────────────────────────────────────


def draft(sql, team) -> str:
    plan = sql(f"SET ROLE service_role; SELECT private.ensure_care_plan('{team}');").splitlines()[
        -1
    ]
    version = sql(f"""INSERT INTO care_plan_versions(patient_id,care_plan_id,version_number,status,generated_at)
      VALUES('{PATIENT}','{plan}',1,'draft',clock_timestamp()) RETURNING id;""").splitlines()[0]
    sql(f"""INSERT INTO care_plan_items(plan_version_id,category,title,instructions,frequency)
      VALUES('{version}','movement','Walk','Walk daily','daily');""")
    return version


def test_a_draft_is_ready_only_for_the_clinician_who_owns_that_plan(sql):
    two_teams(sql)
    mine, theirs = draft(sql, TEAM), draft(sql, OTHER_TEAM)

    assert recipients(sql, mine, "care_plan_draft") == [CLINICIAN]
    assert recipients(sql, theirs, "care_plan_draft") == [OTHER]
    assert seen_by(sql, mine, "care_plan_draft") == [CLINICIAN]
    assert seen_by(sql, theirs, "care_plan_draft") == [OTHER]


def test_the_draft_item_names_the_owners_clinic_for_a_clinician_at_two_clinics(sql):
    seed_people(sql, second_clinic_for_clinician=True)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, CLINICIAN, OTHER_CLINIC)
    version = draft(sql, OTHER_TEAM)

    row = next(
        row for row in items(sql, CLINICIAN, "care_plan_draft") if row["source_id"] == version
    )
    assert row["clinic_name"] == "Birch Clinic"


def test_a_draft_of_an_unowned_plan_alerts_no_clinician(sql):
    two_teams(sql)
    version = draft(sql, TEAM)
    plan = sql(f"SELECT care_plan_id FROM care_plan_versions WHERE id='{version}'")
    sql(f"""SET session_replication_role = replica;
      UPDATE care_plans SET care_team_id=NULL, ownership_state='unowned' WHERE id='{plan}';""")

    assert seen_by(sql, version, "care_plan_draft") == []


def test_a_receipt_for_a_plan_the_team_no_longer_owns_stops_opening(sql):
    two_teams(sql)
    version = draft(sql, TEAM)
    receipt = items(sql, CLINICIAN, "care_plan_draft")[0]["id"]
    plan = sql(f"SELECT care_plan_id FROM care_plan_versions WHERE id='{version}'")
    sql(f"""SET session_replication_role = replica;
      UPDATE care_plans SET care_team_id='{OTHER_TEAM}' WHERE id='{plan}';""")

    assert REFUSED in centre(sql, CLINICIAN, "read", {"id": receipt}, succeeds=False)
    assert seen_by(sql, version, "care_plan_draft") == [OTHER]


# ── Medication-safety (ADR) review ─────────────────────────────────────────────────────────


def assessment(sql, *, status="draft", reviewer=None, team=None) -> str:
    symptom, medication, adr = str(uuid4()), str(uuid4()), str(uuid4())
    sql(f"""
      SET session_replication_role = replica;
      INSERT INTO medications(id,patient_id,name,dosage,frequency,route)
        VALUES('{medication}','{PATIENT}','M','1','daily','oral');
      INSERT INTO symptom_reports(id,patient_id,symptom,severity) VALUES('{symptom}','{PATIENT}','rash',3);
      SET session_replication_role = origin;
      INSERT INTO adr_assessments(id,patient_id,symptom_report_id,suspect_medication_id,
          suspect_medication_name,naranjo_score,causality,status,reviewed_by,reviewed_by_care_team_id)
        VALUES('{adr}','{PATIENT}','{symptom}','{medication}','M',3,'Possible','{status}',
          {f"'{reviewer}'" if reviewer else "NULL"},{f"'{team}'" if team else "NULL"});""")
    return adr


def test_a_pending_assessment_reaches_every_active_team(sql):
    two_teams(sql)
    adr = assessment(sql)

    assert recipients(sql, adr, "adr_review") == sorted([CLINICIAN, OTHER])
    assert seen_by(sql, adr, "adr_review") == [CLINICIAN, OTHER]


def test_an_assessment_a_team_has_taken_up_leaves_the_other_teams_centre(sql):
    two_teams(sql)
    adr = assessment(sql)
    receipt = items(sql, OTHER, "adr_review")[0]["id"]
    # Team A asks the patient for information: the assessment is theirs now (085 policy).
    sql(f"""UPDATE adr_assessments SET reviewed_by='{CLINICIAN}', reviewed_by_care_team_id='{TEAM}',
      last_review_action='request_information' WHERE id='{adr}';""")

    assert seen_by(sql, adr, "adr_review") == [CLINICIAN]
    assert REFUSED in centre(sql, OTHER, "read", {"id": receipt}, succeeds=False)


# ── Care-team messages, appointments, safety flags ─────────────────────────────────────────


def conversation(sql, team, clinician, clinic, clinic_name) -> str:
    conv = str(uuid4())
    sql(f"""INSERT INTO care_conversations(id,care_team_id,patient_id,clinician_id,clinic_id,clinic_name)
      VALUES('{conv}','{team}','{PATIENT}','{clinician}','{clinic}','{clinic_name}');""")
    return conv


def message(sql, conv) -> str:
    msg = str(uuid4())
    sql(f"""INSERT INTO care_conversation_messages(id,conversation_id,sender_id,sender_role,
      sender_name,body,client_message_id,created_at)
      VALUES('{msg}','{conv}','{PATIENT}','patient','Synthetic Patient','Hello',gen_random_uuid(),clock_timestamp());""")
    return msg


def test_a_message_reaches_only_the_clinician_of_that_conversation(sql):
    two_teams(sql)
    mine = conversation(sql, TEAM, CLINICIAN, CLINIC, "Cedar Grove")
    conversation(sql, OTHER_TEAM, OTHER, OTHER_CLINIC, "Birch Clinic")
    msg = message(sql, mine)

    assert recipients(sql, msg, "message_received") == [CLINICIAN]
    assert seen_by(sql, msg, "message_received") == [CLINICIAN]
    receipt = items(sql, CLINICIAN, "message_received")[0]["id"]
    assert REFUSED in centre(sql, OTHER, "read", {"id": receipt}, succeeds=False)


def test_a_read_marker_changes_only_its_own_actors_receipts(sql):
    two_teams(sql)
    mine = conversation(sql, TEAM, CLINICIAN, CLINIC, "Cedar Grove")
    msg = message(sql, mine)
    items(sql, CLINICIAN)  # delivers the receipt

    def marker(actor):
        sql(f"""INSERT INTO care_conversation_reads(conversation_id,actor_id,last_message_id,last_message_at,read_at)
          SELECT '{mine}','{actor}',id,created_at,clock_timestamp() FROM care_conversation_messages
          WHERE id='{msg}';""")

    unread = f"""SELECT count(*) FROM notification_receipts r JOIN notification_events e ON e.id=r.event_id
      WHERE e.source_id='{msg}' AND r.read_at IS NULL"""
    marker(OTHER)  # another team's clinician moving a marker on this thread reads nothing of theirs
    assert sql(unread) == "1"
    marker(CLINICIAN)
    assert sql(unread) == "0"


def test_a_decline_goes_to_the_clinician_of_that_visit_only(sql):
    two_teams(sql)
    appointment = str(uuid4())
    sql(f"""INSERT INTO appointments(id,patient_id,care_team_id,scheduled_at,status,clinic_id,clinician_id,
        proposal_group_id,proposal_expires_at)
      SELECT '{appointment}','{PATIENT}',t.id,clock_timestamp()+interval '3 days','proposed',t.clinic_id,
        t.clinician_id,gen_random_uuid(),clock_timestamp()+interval '2 days'
      FROM care_teams t WHERE t.id='{TEAM}';
      UPDATE appointments SET status='declined' WHERE id='{appointment}';""")

    assert recipients(sql, appointment, "appointment_response") == [CLINICIAN]
    assert seen_by(sql, appointment, "appointment_response") == [CLINICIAN]


def test_a_chat_safety_flag_stays_shared_with_every_active_team(sql):
    two_teams(sql)
    for clinician in (CLINICIAN, OTHER):
        sql(f"""INSERT INTO clinician_messages(clinician_id,patient_id,channel,subject,body)
          VALUES('{clinician}','{PATIENT}','in_app','Urgent patient chat escalation',
            'Chat escalation flagged (emergency). Private answers are not included.');""")

    event = sql("SELECT id FROM notification_events WHERE event_type='safety_flag'")
    assert event
    assert {row["event_type"] for row in items(sql, CLINICIAN)} == {"safety_flag"}
    assert {row["event_type"] for row in items(sql, OTHER)} == {"safety_flag"}


# ── Email ──────────────────────────────────────────────────────────────────────────────────


def opt_in(sql, *clinicians):
    for clinician in clinicians:
        sql(f"""INSERT INTO email_contacts(user_id,role,email,verified_at,preferences,consent_at)
        VALUES('{clinician}','clinician','{clinician}@synthetic.invalid',clock_timestamp(),
          '{{"reviews":true}}',clock_timestamp()-interval '1 day');""")


def outbox(sql, clinician) -> int:
    return int(
        sql(f"SELECT count(*) FROM email_outbox WHERE user_id='{clinician}' AND kind='notice'")
    )


def test_a_review_email_is_queued_for_the_owning_team_only(sql):
    two_teams(sql)
    opt_in(sql, CLINICIAN, OTHER)
    pending_doc(sql, team=TEAM)
    for clinician in (CLINICIAN, OTHER):
        items(sql, clinician)  # opening the centre materializes receipts, as the worker does

    assert outbox(sql, CLINICIAN) == 1
    assert outbox(sql, OTHER) == 0


def test_a_review_email_to_a_team_that_lost_the_record_is_not_sent(sql):
    two_teams(sql)
    opt_in(sql, CLINICIAN, OTHER)
    doc = pending_doc(sql, state="unrouted")
    for clinician in (CLINICIAN, OTHER):
        items(sql, clinician)
    assert outbox(sql, OTHER) == 1
    sql(f"SET ROLE service_role; SELECT public.claim_document('{doc}','{CLINICIAN}','{TEAM}');")

    eligible = {
        who: sql(f"""SELECT private.email_eligible(o) FROM email_outbox o
          WHERE o.user_id='{who}' AND o.kind='notice'""")
        for who in (CLINICIAN, OTHER)
    }
    assert eligible == {CLINICIAN: "t", OTHER: "f"}


# ── Hardening ──────────────────────────────────────────────────────────────────────────────


def test_helpers_are_reachable_by_the_service_role_only(sql):
    for function in (
        "private.notification_links(uuid,uuid)",
        "private.notification_owner_team(text,uuid)",
        "private.notification_owner_sees(text,uuid,text,uuid,uuid)",
    ):
        assert (
            sql(
                f"""SELECT has_function_privilege('anon','{function}','EXECUTE')
              OR has_function_privilege('authenticated','{function}','EXECUTE'),
            has_function_privilege('service_role','{function}','EXECUTE');"""
            )
            == "f|t"
        )
