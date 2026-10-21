"""Confirmed unlisted testimony -> authorized, duplicate-safe review; offline only."""

import json
import os
from uuid import uuid4

import pytest

from tests.integration.test_notification_centre_postgres import (
    CLINICIAN,
    MIGRATIONS,
    OTHER,
    PATIENT,
    TEAM,
    call,
    clinician,
)
from tests.integration.test_symptom_intake_postgres import call_sql, confirmation, ready

pytest_plugins = ["tests.integration.test_notification_centre_postgres"]
pytestmark = pytest.mark.skipif(
    os.environ.get("NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER") != "1",
    reason="explicit offline PostgreSQL opt-in",
)


@pytest.fixture
def product_sql(sql):
    for name in (
        "010_chat_state_and_a2a_tasks.sql",
        "051_health_knowledge_and_chat_sessions.sql",
        "059_chat_safety_alerts.sql",
        "060_confirmed_symptom_intake.sql",
        "071_confirmed_symptom_handoff.sql",
        "079_unlisted_product_review_alerts.sql",
    ):
        sql((MIGRATIONS / name).read_text())
    return sql


def confirm_product(
    sql, *, state="answered", concern=True, name="Synthetic unlisted product", submit=True
):
    preview = ready(sql)
    value = {"concern": concern, "name": name} if state == "answered" else None
    updated = json.loads(
        sql(
            call_sql(
                "answer",
                {
                    "intake_id": preview["id"],
                    "expected_revision": preview["revision"],
                    "mutation_id": str(uuid4()),
                    "answer": {
                        "question_id": "product",
                        "state": state,
                        "value": value,
                        "locale": "en-US",
                        "wording": "Synthetic product answer",
                    },
                },
            )
        )
    )
    if concern is True:
        updated = json.loads(
            sql(
                call_sql(
                    "answer",
                    {
                        "intake_id": updated["id"],
                        "expected_revision": updated["revision"],
                        "mutation_id": str(uuid4()),
                        "answer": {
                            "question_id": "concomitant",
                            "state": "unknown",
                            "value": None,
                            "locale": "en-US",
                            "wording": "",
                        },
                    },
                )
            )
        )
    context = json.loads(
        sql(f"SET ROLE service_role; SELECT symptom_intake_context('{PATIENT}','{updated['id']}');")
    )
    snapshot = {**preview["preview"], "answers": updated["answers"], "context": context}
    rebuilt = json.loads(
        sql(
            call_sql(
                "preview",
                {
                    "intake_id": updated["id"],
                    "expected_revision": updated["revision"],
                    "preview": snapshot,
                },
            )
        )
    )
    payload = confirmation(rebuilt)
    if not submit:
        return rebuilt, payload
    result = json.loads(sql(call_sql("confirm", payload)))
    return result, payload


def test_confirmation_creates_one_review_not_a_medication_or_adr(product_sql):
    db = product_sql
    saved, payload = confirm_product(db)
    report = saved["confirmed_report_id"]
    again = json.loads(db(call_sql("confirm", payload)))
    assert again["confirmed_report_id"] == report
    rows = clinician(db, "action_items")["items"]
    assert len(rows) == 1 and rows[0]["source_id"] == report
    assert rows[0]["source_type"] == "symptom_reports" and rows[0]["can_acknowledge"]
    assert rows[0]["metadata"] == {"review_kind": "unlisted_product"}
    assert db("SELECT count(*) FROM medications") == "0"
    assert db("SELECT count(*) FROM adr_assessments") == "0"
    assert db("SELECT count(*) FROM notification_events WHERE source_type='symptom_reports'") == "1"
    assert not any(row["source_id"] == report for row in call(db)["items"])


@pytest.mark.parametrize(
    "state,concern", [("unknown", None), ("declined", None), ("answered", False)]
)
def test_no_alert_for_unknown_declined_or_no_product_concern(product_sql, state, concern):
    confirm_product(product_sql, state=state, concern=concern)
    assert (
        product_sql("SELECT count(*) FROM notification_events WHERE source_type='symptom_reports'")
        == "0"
    )


def test_acknowledgment_is_audited_idempotent_and_not_clinical_resolution(product_sql):
    db = product_sql
    saved, _ = confirm_product(db)
    row = clinician(db, "action_items")["items"][0]
    for _ in range(2):
        clinician(
            db,
            "acknowledge",
            {"id": row["id"], "note": "Seen for synthetic follow-up; not resolved"},
        )
    assert clinician(db, "action_items")["items"] == []
    assert db("SELECT count(*) FROM notification_read_audit WHERE action='acknowledge'") == "1"
    assert (
        db(
            f"SELECT related_medication_id IS NULL FROM symptom_reports WHERE id='{saved['confirmed_report_id']}'"
        )
        == "t"
    )
    assert db("SELECT count(*) FROM medications") == "0"
    assert db("SELECT count(*) FROM adr_assessments") == "0"


def test_unique_recorded_product_keeps_existing_adr_handoff_not_an_unlisted_alert(product_sql):
    db = product_sql
    med = str(uuid4())
    db(
        f"INSERT INTO medications(id,patient_id,name,dosage,frequency) VALUES('{med}','{PATIENT}','Synthetic recorded product','synthetic','daily');"
    )
    saved, _ = confirm_product(db, name="Synthetic recorded product")
    assert (
        db(
            f"SELECT related_medication_id FROM symptom_reports WHERE id='{saved['confirmed_report_id']}'"
        )
        == med
    )
    assert db("SELECT count(*) FROM notification_events WHERE source_type='symptom_reports'") == "0"


def test_foreign_clinician_and_revoked_assignment_cannot_open_or_acknowledge(product_sql):
    db = product_sql
    confirm_product(db)
    row = clinician(db, "action_items")["items"][0]
    assert clinician(db, "action_items", actor=OTHER)["items"] == []
    db(f"UPDATE care_teams SET status='inactive' WHERE id='{TEAM}'")
    assert clinician(db, "action_items")["items"] == []
    from tests.integration.test_notification_centre_postgres import operation

    assert "Notification unavailable" in db(
        operation("acknowledge", {"id": row["id"]}, actor=CLINICIAN, role="clinician"),
        succeeds=False,
    )


def test_migration_rerun_preserves_testimony_and_browser_cannot_capture(product_sql):
    db = product_sql
    saved, _ = confirm_product(db)
    db((MIGRATIONS / "079_unlisted_product_review_alerts.sql").read_text())
    assert db("SELECT count(*) FROM notification_events WHERE source_type='symptom_reports'") == "1"
    assert (
        db(f"SELECT count(*) FROM symptom_reports WHERE id='{saved['confirmed_report_id']}'") == "1"
    )
    for role in ("anon", "authenticated"):
        assert "permission denied" in db(
            f"SET ROLE {role}; SELECT private.notification_source('symptom_reports','{saved['confirmed_report_id']}');",
            succeeds=False,
        )
        assert "permission denied" in db(
            f"SET ROLE {role}; INSERT INTO notification_events(event_key) VALUES('forged');",
            succeeds=False,
        )


def test_capture_failure_rolls_back_confirmation_and_retry_captures_once(product_sql):
    db = product_sql
    preview, payload = confirm_product(db, submit=False)
    db("""CREATE FUNCTION private.block_review_test() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'Synthetic capture unavailable'; END; $$;
      CREATE TRIGGER block_review_test BEFORE INSERT ON notification_events
        FOR EACH ROW WHEN (NEW.source_type='symptom_reports') EXECUTE FUNCTION private.block_review_test();""")
    assert "Synthetic capture unavailable" in db(call_sql("confirm", payload), succeeds=False)
    assert db("SELECT count(*) FROM symptom_reports") == "0"
    assert (
        db(f"SELECT status FROM symptom_intakes WHERE id='{preview['id']}'")
        == "ready_for_confirmation"
    )
    db("DROP TRIGGER block_review_test ON notification_events;")
    saved = json.loads(db(call_sql("confirm", payload)))
    assert saved["confirmed_report_id"]
    assert db("SELECT count(*) FROM notification_events WHERE source_type='symptom_reports'") == "1"


def test_new_assigned_reviewer_sees_current_shared_work_not_private_history(product_sql):
    from tests.integration.test_clinic_memberships_postgres import CLINIC, link, new_clinician

    db = product_sql
    saved, _ = confirm_product(db)
    actor = new_clinician(db, clinic=CLINIC)
    link(db, actor, patient=PATIENT, clinic=CLINIC)
    items = clinician(db, "action_items", actor=actor)["items"]
    assert len(items) == 1 and items[0]["source_id"] == saved["confirmed_report_id"]
    assert all(
        row["event_type"] != "message_received" for row in clinician(db, actor=actor)["items"]
    )
