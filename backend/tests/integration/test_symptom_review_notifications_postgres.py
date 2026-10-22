"""Patient review notice and hand-off report link (095) on a disposable PostgreSQL 16.

A care team's "Mark reviewed" tells the patient once per (report, team), in the review's own
transaction; the generic hand-off message to each clinician names its report. The whole ledger
is applied, so the real notification pipeline, email capture and intake functions run.
Opt-in: ``CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER=1``. Synthetic data only.
"""

# ruff: noqa: F811 -- the harness fixtures are imported (not a plugin) so that, in a combined run,
# another module's fixtures named ``sql``/``postgres`` cannot shadow them and point this file at a
# different container and schema.

from __future__ import annotations

import json
import os
from uuid import uuid4

import pytest

from tests.integration.care_team_plan_harness import (
    CLINIC,
    CLINICIAN,
    MIGRATIONS,
    OTHER,
    OTHER_CLINIC,
    OTHER_TEAM,
    PATIENT,
    SECOND_PATIENT,
    TEAM,
    THIRD,
    link,
    postgres,  # noqa: F401
    seed_people,
    sql,  # noqa: F401
)
from tests.integration.test_care_team_notifications_postgres import centre
from tests.integration.test_symptom_intake_postgres import call_sql, confirmation, ready

pytestmark = [
    pytest.mark.timeout(600),
    pytest.mark.skipif(
        os.environ.get("CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER") != "1",
        reason="explicit opt-in disposable Docker PostgreSQL contract check",
    ),
]

KIND = "symptom_report_reviewed"
MIGRATION = (MIGRATIONS / "095_symptom_review_notifications.sql").read_text()


def world(sql) -> str:
    """Two care teams (two clinics) for one patient and one confirmed report; returns its id."""
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)
    sql(f"UPDATE care_teams SET specialty_context='Cardiology' WHERE id='{TEAM}';")
    saved = json.loads(sql(call_sql("confirm", confirmation(ready(sql)))))
    return saved["confirmed_report_id"]


def history(actor, role, action, payload):
    body = json.dumps(payload).replace("'", "''")
    return (
        "SET ROLE service_role; "
        f"SELECT public.symptom_report_history('{actor}','{role}','{action}','{body}');"
    )


def review(sql, actor, report, **extra):
    out = sql(history(actor, "clinician", "review", {"report_id": report, **extra}))
    return json.loads(out.splitlines()[-1])


def events(sql) -> int:
    return int(sql(f"SELECT count(*) FROM notification_events WHERE event_type='{KIND}'"))


def patient_items(sql, patient=PATIENT):
    rows = centre(sql, patient, role="patient")["items"]
    return [row for row in rows if row["event_type"] == KIND]


def test_each_team_review_tells_the_patient_once_with_a_link_to_the_report(sql):
    report = world(sql)
    assert events(sql) == 0 and patient_items(sql) == []

    review(sql, CLINICIAN, report)
    first = patient_items(sql)
    assert len(first) == 1 and events(sql) == 1
    item = first[0]
    assert item["source_id"] == report and item["source_type"] == "symptom_reports"
    assert item["category"] == "follow_up" and item["actionable"] is False
    assert item["is_read"] is False
    assert item["metadata"]["clinician_name"] == "Elena Park"
    assert item["metadata"]["specialty"] == "Cardiology"
    assert item["metadata"]["report_title"] == sql(
        f"SELECT symptom FROM symptom_reports WHERE id='{report}'"
    )
    # Names the report title and reviewer; carries no answers, provenance or safety outcome.
    assert set(item["metadata"]) == {"care_team_id", "clinician_name", "specialty", "report_title"}
    assert item["metadata"]["care_team_id"] == TEAM

    # A second team's review is its own item; a repeat by either adds nothing.
    review(sql, OTHER, report)
    review(sql, CLINICIAN, report)
    review(sql, OTHER, report)
    both = patient_items(sql)
    assert len(both) == 2 and events(sql) == 2
    assert {row["metadata"]["care_team_id"] for row in both} == {TEAM, OTHER_TEAM}
    assert int(sql("SELECT count(*) FROM symptom_report_reviews")) == 2
    assert (
        int(
            sql(
                f"SELECT count(*) FROM notification_pending_deliveries d JOIN notification_events e "
                f"ON e.id=d.event_id WHERE e.event_type='{KIND}'"
            )
        )
        == 2
    )
    assert (
        int(
            sql(
                f"SELECT count(*) FROM notification_receipts r JOIN notification_events e "
                f"ON e.id=r.event_id WHERE e.event_type='{KIND}'"
            )
        )
        == 2
    )


def test_replayed_capture_and_concurrent_reviews_converge_on_one_item(sql):
    report = world(sql)
    runs = [
        sql.start(history(CLINICIAN, "clinician", "review", {"report_id": report}), f"review{i}")
        for i in range(4)
    ]
    for process in runs:
        assert process.wait(timeout=30) == 0
    assert events(sql) == 1 and len(patient_items(sql)) == 1
    assert int(sql("SELECT count(*) FROM symptom_report_reviews")) == 1
    assert (
        int(sql("SELECT count(*) FROM symptom_intake_audit WHERE action='clinician_reviewed'")) == 1
    )

    # An at-least-once replay of the capture itself (same key) adds no event or delivery.
    sql(f"""SELECT private.notification_capture('symptom_reports','{report}','{PATIENT}',
      '{KIND}','follow_up','patient',NULL,'{{}}','symptom_report_reviews:{report}:{TEAM}',now());""")
    assert events(sql) == 1
    assert int(sql("SELECT count(*) FROM notification_pending_deliveries")) == 1


def test_a_rolled_back_review_leaves_no_notice_and_a_denied_one_creates_none(sql):
    report = world(sql)
    sql(f"""BEGIN;
      SET ROLE service_role;
      SELECT public.symptom_report_history('{CLINICIAN}','clinician','review','{{"report_id":"{report}"}}');
      ROLLBACK;""")
    assert events(sql) == 0 and int(sql("SELECT count(*) FROM symptom_report_reviews")) == 0

    # No link, an ended link, the patient, another patient and an unknown report: all denied.
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{OTHER_TEAM}';")
    for actor, role in ((OTHER, "clinician"), (THIRD, "clinician"), (PATIENT, "patient")):
        sql(history(actor, role, "review", {"report_id": report}), succeeds=False)
    sql(history(CLINICIAN, "clinician", "review", {"report_id": str(uuid4())}), succeeds=False)
    sql(
        history(
            CLINICIAN, "clinician", "review", {"report_id": report, "care_team_id": OTHER_TEAM}
        ),
        succeeds=False,
    )
    assert events(sql) == 0 and patient_items(sql) == []


def test_only_the_patient_can_see_or_read_the_notice(sql):
    report = world(sql)
    review(sql, CLINICIAN, report)
    item = patient_items(sql)[0]

    # Not another patient, and not any clinician (the event is addressed to the patient).
    assert patient_items(sql, SECOND_PATIENT) == []
    for who in (CLINICIAN, OTHER, THIRD):
        rows = centre(sql, who)["items"]
        assert all(row["event_type"] != KIND for row in rows)
        assert "unavailable" in centre(sql, who, "read", {"id": item["id"]}, succeeds=False).lower()
    assert (
        "unavailable"
        in centre(
            sql, SECOND_PATIENT, "read", {"id": item["id"]}, role="patient", succeeds=False
        ).lower()
    )

    # The patient reads it; it stays History (never an action item) and counts as read.
    centre(sql, PATIENT, "read", {"id": item["id"]}, role="patient")
    again = patient_items(sql)[0]
    assert again["is_read"] is True and again["actionable"] is False
    summary = centre(sql, PATIENT, "summary", role="patient")
    assert summary["action_item_count"] == 0


def test_no_email_category_exists_even_when_every_notice_is_on(sql):
    report = world(sql)
    sql(f"""INSERT INTO email_contacts(user_id,role,email,verified_at,preferences,consent_at)
      VALUES('{PATIENT}','patient','{PATIENT}@synthetic.invalid',clock_timestamp(),
        '{{"messages":true,"appointments":true,"care_plans":true,"records":true,"reviews":true}}',
        clock_timestamp()-interval '1 day');""")
    assert sql(f"SELECT private.email_preference('{KIND}') IS NULL") == "t"
    review(sql, CLINICIAN, report)
    patient_items(sql)  # opening the centre materializes the receipt, as the worker does
    assert int(sql(f"SELECT count(*) FROM email_outbox WHERE user_id='{PATIENT}'")) == 0


def test_hand_off_messages_name_their_report_and_others_do_not(sql):
    report = world(sql)
    assert (
        sql("SELECT string_agg(DISTINCT symptom_report_id::text, ',') FROM clinician_messages")
        == report
    )
    assert int(sql("SELECT count(*) FROM clinician_messages")) == 2
    assert int(sql("SELECT count(*) FROM clinician_messages WHERE symptom_report_id IS NULL")) == 0
    sql(f"""INSERT INTO clinician_messages(clinician_id,patient_id,channel,subject,body)
      VALUES('{CLINICIAN}','{PATIENT}','in_app','Reminder','Please call the clinic.');""")
    assert int(sql("SELECT count(*) FROM clinician_messages WHERE symptom_report_id IS NULL")) == 1
    # The column cannot point at a missing report, and the message survives the link going away.
    sql(
        f"UPDATE clinician_messages SET symptom_report_id='{uuid4()}' WHERE subject='Reminder';",
        succeeds=False,
    )


def test_backfill_links_only_unambiguous_existing_hand_offs_and_reapplying_is_safe(sql):
    report = world(sql)
    sql("UPDATE clinician_messages SET symptom_report_id=NULL;")
    # One hand-off row no longer matches its report body exactly: it must stay unlinked.
    sql(f"""UPDATE clinician_messages SET body=body||' (edited)'
      WHERE clinician_id='{OTHER}';""")
    before = int(sql("SELECT count(*) FROM notification_events"))

    sql(MIGRATION)
    sql(MIGRATION)  # idempotent

    assert (
        sql(
            f"SELECT symptom_report_id::text FROM clinician_messages WHERE clinician_id='{CLINICIAN}'"
        )
        == report
    )
    assert (
        sql(
            f"SELECT symptom_report_id IS NULL FROM clinician_messages WHERE clinician_id='{OTHER}'"
        )
        == "t"
    )
    # Old reviews are not replayed as new notices.
    assert int(sql("SELECT count(*) FROM notification_events")) == before


def test_old_reviews_before_the_migration_are_not_announced_late(sql):
    report = world(sql)
    sql(f"""ALTER TABLE symptom_report_reviews DISABLE TRIGGER symptom_report_review_notification;
      INSERT INTO symptom_report_reviews(report_id,care_team_id,patient_id,reviewed_by)
        VALUES('{report}','{TEAM}','{PATIENT}','{CLINICIAN}');
      ALTER TABLE symptom_report_reviews ENABLE TRIGGER symptom_report_review_notification;""")
    sql(MIGRATION)
    assert events(sql) == 0
    # The repeat of that old review (already reviewed) stays quiet; a new team still notifies.
    review(sql, CLINICIAN, report)
    assert events(sql) == 0
    review(sql, OTHER, report)
    assert events(sql) == 1
