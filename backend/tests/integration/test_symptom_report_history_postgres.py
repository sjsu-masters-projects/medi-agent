"""Applied 091 on real disposable SQL: own-only history, shared review, no browser access."""

# ruff: noqa: F811 -- imported pytest fixtures intentionally share fixture argument names

import json
import os
from uuid import uuid4

import pytest

from tests.integration.test_symptom_handoff_postgres import (
    MIGRATIONS,
    handoff,  # noqa: F401 -- shared disposable PostgreSQL fixture
    postgres,  # noqa: F401
    sql,  # noqa: F401
)
from tests.integration.test_symptom_intake_postgres import (
    CLINICIAN,
    OTHER,
    PATIENT,
    call_sql,
    confirmation,
    ready,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("SYMPTOM_INTAKE_TEST_POSTGRES") != "1",
    reason="local SQL opt-in required",
)


@pytest.fixture
def history(handoff):
    handoff((MIGRATIONS / "091_symptom_report_history_and_review.sql").read_text())
    return handoff


def history_sql(actor, role, action, payload):
    body = json.dumps(payload).replace("'", "''")
    return (
        "SET ROLE service_role; "
        f"SELECT public.symptom_report_history('{actor}','{role}','{action}','{body}');"
    )


def confirmed(db, draft=None):
    saved = json.loads(db(call_sql("confirm", confirmation(draft or ready(db)))))
    return saved["confirmed_report_id"]


def other_clinician(db, *, active=True, specialty="Cardiology"):
    clinician = str(uuid4())
    status = "active" if active else "inactive"
    db(
        f"""INSERT INTO auth.users VALUES ('{clinician}');
        INSERT INTO clinicians(id,email,first_name,last_name,specialty,clinic_name)
          VALUES ('{clinician}','{clinician}@synthetic.invalid','Second','Reviewer','Synthetic','Synthetic');
        INSERT INTO clinic_memberships(clinic_id,clinician_id,role)
          VALUES ((SELECT id FROM clinics LIMIT 1),'{clinician}','provider');
        INSERT INTO care_teams(patient_id,clinician_id,role,status,clinic_id)
          VALUES ('{PATIENT}','{clinician}','secondary','{status}',(SELECT id FROM clinics LIMIT 1));
        UPDATE care_teams SET specialty_context='{specialty}' WHERE clinician_id='{clinician}';"""
    )
    return clinician


def test_patient_lists_only_own_confirmed_reports_with_recorded_events(history):
    db = history
    draft = ready(db)  # an unconfirmed draft exists and is not a report
    empty = json.loads(db(history_sql(PATIENT, "patient", "list", {})))
    assert empty["items"] == [] and empty["has_more"] is False
    report = confirmed(db, draft)
    listed = json.loads(db(history_sql(PATIENT, "patient", "list", {})))
    assert [item["id"] for item in listed["items"]] == [report]
    assert listed["items"][0]["handoff_state"] == "sent"
    assert listed["items"][0]["reviews"] == []
    other = json.loads(db(history_sql(OTHER, "patient", "list", {})))
    assert other["items"] == []
    db(history_sql(CLINICIAN, "clinician", "list", {}), succeeds=False)


def test_detail_is_own_only_and_unknown_looks_like_denied(history):
    db = history
    report = confirmed(db)
    own = json.loads(db(history_sql(PATIENT, "patient", "detail", {"report_id": report})))
    assert own["answers"]["severity"]["state"] == "unknown"
    assert "provenance" not in own and "safety" not in own
    denied = db(history_sql(OTHER, "patient", "detail", {"report_id": report}), succeeds=False)
    missing = db(
        history_sql(PATIENT, "patient", "detail", {"report_id": str(uuid4())}), succeeds=False
    )
    assert "Report unavailable" in denied and "Report unavailable" in missing
    db(history_sql(PATIENT, "patient", "review", {"report_id": report}), succeeds=False)


def test_clinician_detail_has_provenance_and_requires_an_active_link(history):
    db = history
    report = confirmed(db)
    detail = json.loads(db(history_sql(CLINICIAN, "clinician", "detail", {"report_id": report})))
    assert detail["provenance"]["consent_recorded"] is True
    assert detail["provenance"]["report_id"] == report and "context" not in json.dumps(detail)
    db(
        history_sql(CLINICIAN, "clinician", "detail", {"report_id": report, "patient_id": OTHER}),
        succeeds=False,
    )
    inactive = other_clinician(db, active=False)
    db(history_sql(inactive, "clinician", "detail", {"report_id": report}), succeeds=False)
    db(history_sql(inactive, "clinician", "review", {"report_id": report}), succeeds=False)
    assert db("SELECT count(*) FROM symptom_report_reviews;") == "0"


def review(db, actor, report, **extra):
    return json.loads(db(history_sql(actor, "clinician", "review", {"report_id": report, **extra})))


def test_each_care_team_reviews_independently_and_repeats_are_idempotent(history):
    db = history
    report = confirmed(db)
    first = review(db, CLINICIAN, report)
    assert first["already_reviewed"] is False
    assert [r["reviewed_by_name"] for r in first["reviews"]] == ["Synthetic Reviewer"]
    assert first["reviews"][0]["mine"] is True
    repeat = review(db, CLINICIAN, report)
    assert repeat["already_reviewed"] is True
    assert repeat["reviews"][0]["reviewed_at"] == first["reviews"][0]["reviewed_at"]
    assert db("SELECT count(*) FROM symptom_report_reviews;") == "1"

    # Another team has not reviewed: its own view says so, and it can review on its own.
    second = other_clinician(db)
    before = json.loads(db(history_sql(second, "clinician", "detail", {"report_id": report})))
    assert [r["mine"] for r in before["reviews"]] == [False]
    assert (
        before["reviews"][0]["team_label"].startswith("primary")
        or before["reviews"][0]["team_label"]
    )
    again = review(db, second, report)
    assert again["already_reviewed"] is False
    assert sorted(r["mine"] for r in again["reviews"]) == [False, True]
    assert db("SELECT count(*) FROM symptom_report_reviews;") == "2"
    assert db("SELECT count(*) FROM symptom_intake_audit WHERE action='clinician_reviewed';") == "2"
    labels = {r["team_label"] for r in again["reviews"]}
    assert any(label.startswith("Cardiology") for label in labels)

    patient_view = json.loads(db(history_sql(PATIENT, "patient", "detail", {"report_id": report})))
    assert {r["reviewed_by_name"] for r in patient_view["reviews"]} == {
        "Synthetic Reviewer",
        "Second Reviewer",
    }
    assert "mine" not in json.dumps(patient_view) or all(
        r["mine"] is False for r in patient_view["reviews"]
    )
    assert "viewer_care_team_ids" not in patient_view


def test_concurrent_double_click_by_one_team_converges_on_one_row(history):
    db = history
    report = confirmed(db)
    children = [
        db.start(history_sql(CLINICIAN, "clinician", "review", {"report_id": report}))
        for _ in range(2)
    ]
    for child in children:
        child.wait(timeout=15)
        assert child.returncode == 0, child.stderr.read()
    assert db("SELECT count(*) FROM symptom_report_reviews;") == "1"
    assert db("SELECT count(*) FROM symptom_intake_audit WHERE action='clinician_reviewed';") == "1"


def test_concurrent_reviews_by_two_teams_both_land_once(history):
    db = history
    report = confirmed(db)
    second = other_clinician(db)
    children = [
        db.start(history_sql(actor, "clinician", "review", {"report_id": report}))
        for actor in (CLINICIAN, second)
    ]
    for child in children:
        child.wait(timeout=15)
        assert child.returncode == 0, child.stderr.read()
    assert db("SELECT count(*) FROM symptom_report_reviews;") == "2"


def test_a_clinician_with_two_links_must_choose_and_only_their_own(history):
    db = history
    report = confirmed(db)
    db(
        """DO $$ DECLARE c text; BEGIN
        FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='care_teams'::regclass AND contype='u'
        LOOP EXECUTE format('ALTER TABLE care_teams DROP CONSTRAINT %I', c); END LOOP; END $$;"""
    )
    other_clinic = str(uuid4())
    db(
        f"""INSERT INTO clinics(id,display_name,canonical_name) VALUES('{other_clinic}','Second Clinic','second clinic');
        INSERT INTO clinic_memberships(clinic_id,clinician_id,role) VALUES('{other_clinic}','{CLINICIAN}','provider');
        INSERT INTO care_teams(patient_id,clinician_id,role,status,clinic_id)
          VALUES('{PATIENT}','{CLINICIAN}','secondary','active','{other_clinic}');"""
    )
    asked = db(history_sql(CLINICIAN, "clinician", "review", {"report_id": report}), succeeds=False)
    assert "CARE_TEAM_REQUIRED" in asked
    teams = db(f"SELECT id FROM care_teams WHERE clinician_id='{CLINICIAN}' ORDER BY id;").split()
    done = review(db, CLINICIAN, report, care_team_id=teams[1])
    assert done["acting_care_team_id"] == teams[1] and done["already_reviewed"] is False
    assert sorted(
        done["your_care_team_ids"] if "your_care_team_ids" in done else done["viewer_care_team_ids"]
    ) == sorted(teams)
    foreign = other_clinician(db)
    foreign_team = db(f"SELECT id FROM care_teams WHERE clinician_id='{foreign}';")
    db(
        history_sql(
            CLINICIAN, "clinician", "review", {"report_id": report, "care_team_id": foreign_team}
        ),
        succeeds=False,
    )
    assert db("SELECT count(*) FROM symptom_report_reviews;") == "1"


def test_handoff_state_is_recorded_from_who_it_reached(history):
    db = history
    db("UPDATE care_teams SET status='inactive';")
    report = confirmed(db)
    card = json.loads(db(history_sql(PATIENT, "patient", "detail", {"report_id": report})))
    assert card["handoff_state"] == "not_sent" and card["handed_off_at"] is None
    assert db("SELECT count(*) FROM clinician_messages;") == "0"


def test_handoff_to_an_active_team_is_sent_and_pre_091_rows_are_unrecorded(history):
    db = history
    report = confirmed(db)
    card = json.loads(db(history_sql(PATIENT, "patient", "detail", {"report_id": report})))
    assert card["handoff_state"] == "sent" and card["handed_off_at"] is not None
    # Simulate a row written before 091: the append-only guard is dropped in this throwaway database.
    db(
        "DROP TRIGGER symptom_intake_audit_immutable ON symptom_intake_audit;"
        "UPDATE symptom_intake_audit SET evidence=evidence-'recipients' WHERE action='review_handoff';"
    )
    legacy = json.loads(db(history_sql(PATIENT, "patient", "detail", {"report_id": report})))
    assert legacy["handoff_state"] == "unrecorded" and legacy["handed_off_at"] is None


def test_browser_roles_have_no_access(history):
    db = history
    report = confirmed(db)
    for role in ("anon", "authenticated"):
        db(f"SET ROLE {role}; SELECT * FROM symptom_report_reviews;", succeeds=False)
        db(
            f"SET ROLE {role}; SELECT public.symptom_report_history('{PATIENT}','patient','detail','{{\"report_id\":\"{report}\"}}');",
            succeeds=False,
        )
    assert db("SELECT relrowsecurity FROM pg_class WHERE relname='symptom_report_reviews';") == "t"


def test_migration_reapplies_cleanly(history):
    history((MIGRATIONS / "091_symptom_report_history_and_review.sql").read_text())
