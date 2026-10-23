"""Notification-centre alert for a patient medication question (099, MED-002) on PostgreSQL 16.

Asking creates exactly one patient item in the request's own transaction; it links to Today,
carries no medicine or answer, is actionable only while the question is open, and the earlier
handoff-share (096) and symptom-review (095) notifications still work through the layered
ledger wrappers. Opt-in: ``CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER=1``. Synthetic data only.
"""

from __future__ import annotations

import json
import os

import pytest

from tests.integration.care_team_plan_harness import (
    CLINICIAN,
    MIGRATIONS,
    OTHER,
    PATIENT,
    SECOND_PATIENT,
    TEAM,
    THIRD,
)
from tests.integration.test_care_handoff_shares_postgres import (
    handoff_items,
)
from tests.integration.test_care_handoff_shares_postgres import (
    shared as share_handoff,
)
from tests.integration.test_care_handoff_shares_postgres import (
    world as handoff_world,
)
from tests.integration.test_care_team_notifications_postgres import centre
from tests.integration.test_medication_confirmations_postgres import (
    answer,
    create,
    create_sql,
    med_fact,
    world,
)
from tests.integration.test_symptom_review_notifications_postgres import (
    patient_items as review_items,
)
from tests.integration.test_symptom_review_notifications_postgres import (
    review,
)
from tests.integration.test_symptom_review_notifications_postgres import (
    world as review_world,
)

pytest_plugins = ["tests.integration.care_team_plan_harness"]

pytestmark = [
    pytest.mark.timeout(600),
    pytest.mark.skipif(
        os.environ.get("CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER") != "1",
        reason="explicit opt-in disposable Docker PostgreSQL contract check",
    ),
]

KIND = "medication_confirmation_asked"
MIGRATION = (MIGRATIONS / "099_medication_question_alert.sql").read_text()


def mine(sql, patient=PATIENT):
    rows = centre(sql, patient, role="patient")["items"]
    return [row for row in rows if row["event_type"] == KIND]


def count(sql, table_sql: str) -> int:
    return int(sql(f"SELECT count(*) FROM {table_sql}"))


def expire(sql, request):
    sql(f"""SET session_replication_role = replica;
      UPDATE medication_confirmation_requests
         SET created_at = clock_timestamp() - interval '20 days',
             expires_at = clock_timestamp() - interval '6 days' WHERE id='{request}';""")


def test_asking_tells_the_patient_once_with_no_clinical_content(sql):
    world(sql)
    assert mine(sql) == [] and count(sql, "notification_events") == 0
    made = create(sql, med_fact(sql))

    items = mine(sql)
    assert len(items) == 1
    item = items[0]
    assert item["source_id"] == made["id"]
    assert item["source_type"] == "medication_confirmation_requests"
    assert item["category"] == "follow_up" and item["actionable"] is True
    assert item["is_read"] is False
    assert item["metadata"]["clinician_name"] == "Elena Park"
    assert set(item["metadata"]) == {"care_team_id", "clinician_name", "specialty"}
    assert item["metadata"]["care_team_id"] == TEAM
    # The medicine, dose and wording stay on the Today card.
    assert "Metformin" not in json.dumps(item) and "500 mg" not in json.dumps(item)
    event = f"event_type='{KIND}'"
    assert count(sql, f"notification_events WHERE {event}") == 1
    assert (
        count(
            sql,
            "notification_pending_deliveries d JOIN notification_events e ON e.id=d.event_id "
            f"WHERE e.{event}",
        )
        == 1
    )
    assert (
        count(
            sql,
            "notification_receipts r JOIN notification_events e ON e.id=r.event_id "
            f"WHERE e.{event}",
        )
        == 1
    )
    assert sql(f"SELECT audience FROM notification_events WHERE {event}") == "patient"


def test_replays_and_repeat_asks_do_not_add_items(sql):
    world(sql)
    fid = med_fact(sql)
    first = create(sql, fid)
    create(sql, fid, request=first["id"])  # same request id
    create(sql, fid)  # second ask while open returns the open one
    assert len(mine(sql)) == 1 and count(sql, "medication_confirmation_requests") == 1
    # An at-least-once replay of the capture itself (same key) adds nothing.
    sql(f"""SELECT private.notification_capture('medication_confirmation_requests','{first["id"]}',
      '{PATIENT}','{KIND}','follow_up','patient',NULL,'{{}}',
      'medication_confirmation:{first["id"]}',now());""")
    assert count(sql, f"notification_events WHERE event_type='{KIND}'") == 1
    assert (
        count(
            sql,
            "notification_pending_deliveries d JOIN notification_events e ON e.id=d.event_id "
            f"WHERE e.event_type='{KIND}'",
        )
        == 1
    )
    # Re-applying the migration is harmless.
    sql(MIGRATION)
    sql(MIGRATION)
    assert len(mine(sql)) == 1


def test_a_refused_or_rolled_back_ask_leaves_nothing(sql):
    world(sql)
    fid = med_fact(sql)
    assert "confirmation unavailable" in sql(create_sql(fid, actor=OTHER), succeeds=False)
    assert "invalid confirmation request" in sql(create_sql(fid, ttl=99), succeeds=False)
    assert count(sql, f"notification_events WHERE event_type='{KIND}'") == 0
    assert mine(sql) == []


def test_answering_ends_the_call_to_act_but_keeps_the_history(sql):
    world(sql)
    fid = med_fact(sql)
    made = create(sql, fid)
    assert mine(sql)[0]["actionable"] is True
    answer(sql, made["id"], "yes")
    after = mine(sql)
    assert len(after) == 1 and after[0]["actionable"] is False
    assert count(sql, f"notification_events WHERE event_type='{KIND}'") == 1


def test_expiry_ends_the_call_to_act_and_a_fresh_ask_is_a_new_item(sql):
    world(sql)
    fid = med_fact(sql)
    made = create(sql, fid)
    assert mine(sql)[0]["actionable"] is True
    expire(sql, made["id"])
    stale = mine(sql)
    assert len(stale) == 1 and stale[0]["actionable"] is False

    fresh = create(sql, fid)
    assert fresh["id"] != made["id"]
    items = mine(sql)
    assert len(items) == 2
    assert sorted(i["actionable"] for i in items) == [False, True]


def test_only_the_asked_patient_sees_it_and_only_while_the_link_is_active(sql):
    world(sql)
    create(sql, med_fact(sql))
    assert mine(sql, SECOND_PATIENT) == []
    # No clinician, including the one who asked, receives it.
    for who in (CLINICIAN, OTHER, THIRD):
        rows = centre(sql, who, role="clinician")["items"]
        assert [r for r in rows if r["event_type"] == KIND] == []
    # A clinician id presented as a patient is refused outright.
    assert "Notification unavailable" in centre(sql, CLINICIAN, role="patient", succeeds=False)
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{TEAM}';")
    assert mine(sql) == []


def test_it_is_never_email_and_browser_roles_reach_nothing(sql):
    world(sql)
    create(sql, med_fact(sql))
    assert sql(f"SELECT private.email_preference('{KIND}') IS NULL") == "t"
    assert count(sql, f"email_outbox WHERE user_id='{PATIENT}'") == 0
    for function in (
        "private.capture_medication_confirmation_asked()",
        "private.notification_source_handoff(text,uuid)",
        "private.notification_authorized_handoff(public.notification_events,uuid,text)",
        "private.notification_actionable_handoff(public.notification_events,text)",
        "private.notification_source(text,uuid)",
        "private.notification_authorized(public.notification_events,uuid,text)",
        "private.notification_actionable(public.notification_events,text)",
    ):
        got = sql(
            f"SELECT has_function_privilege('anon','{function}','EXECUTE'), "
            f"has_function_privilege('authenticated','{function}','EXECUTE'), "
            f"has_function_privilege('service_role','{function}','EXECUTE');"
        )
        assert got.splitlines()[-1] == "f|f|t", function


def test_handoff_share_notifications_still_work_through_the_wrapper(sql):
    summary = handoff_world(sql)
    share = share_handoff(sql, summary, THIRD)
    item = handoff_items(sql, THIRD)[0]
    assert item["source_id"] == share and item["actionable"] is False
    assert item["metadata"]["actor_name"] == "Elena Park"
    for who in (CLINICIAN, OTHER):
        assert handoff_items(sql, who) == []
    # The new migration re-applied on top changes none of that.
    sql(MIGRATION)
    assert [i["source_id"] for i in handoff_items(sql, THIRD)] == [share]


def test_symptom_review_notifications_still_work_through_the_wrapper(sql):
    report = review_world(sql)
    review(sql, CLINICIAN, report)
    items = review_items(sql)
    assert len(items) == 1 and items[0]["source_id"] == report
    assert items[0]["actionable"] is False
    review(sql, CLINICIAN, report)
    assert len(review_items(sql)) == 1


def test_a_question_and_a_review_share_one_patient_centre(sql):
    report = review_world(sql)
    review(sql, CLINICIAN, report)
    create(sql, med_fact(sql))
    kinds = {r["event_type"] for r in centre(sql, PATIENT, role="patient")["items"]}
    assert {KIND, "symptom_report_reviewed"} <= kinds
