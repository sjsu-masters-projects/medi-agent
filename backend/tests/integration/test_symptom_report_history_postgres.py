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


def other_clinician(db, *, active=True):
    clinician = str(uuid4())
    status = "active" if active else "inactive"
    db(
        f"""INSERT INTO auth.users VALUES ('{clinician}');
        INSERT INTO clinicians(id,email,first_name,last_name,specialty,clinic_name)
          VALUES ('{clinician}','{clinician}@synthetic.invalid','Second','Reviewer','Synthetic','Synthetic');
        INSERT INTO clinic_memberships(clinic_id,clinician_id,role)
          VALUES ((SELECT id FROM clinics LIMIT 1),'{clinician}','provider');
        INSERT INTO care_teams(patient_id,clinician_id,role,status,clinic_id)
          VALUES ('{PATIENT}','{clinician}','secondary','{status}',(SELECT id FROM clinics LIMIT 1));"""
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
    assert listed["items"][0]["handed_off_at"] is not None
    assert listed["items"][0]["review"] is None
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


def test_review_is_idempotent_audited_and_shared_by_the_care_team(history):
    db = history
    report = confirmed(db)
    first = json.loads(db(history_sql(CLINICIAN, "clinician", "review", {"report_id": report})))
    assert (
        first["already_reviewed"] is False
        and first["review"]["reviewed_by_name"] == "Synthetic Reviewer"
    )
    second = other_clinician(db)
    again = json.loads(db(history_sql(second, "clinician", "review", {"report_id": report})))
    assert again["already_reviewed"] is True
    assert again["review"]["reviewed_at"] == first["review"]["reviewed_at"]
    assert db("SELECT count(*) FROM symptom_report_reviews;") == "1"
    assert db("SELECT count(*) FROM symptom_intake_audit WHERE action='clinician_reviewed';") == "1"
    patient_view = json.loads(db(history_sql(PATIENT, "patient", "detail", {"report_id": report})))
    assert patient_view["review"]["reviewed_by_name"] == "Synthetic Reviewer"
    assert "review_detail" not in patient_view


def test_concurrent_reviews_converge_on_one_row(history):
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
    assert db("SELECT count(*) FROM symptom_report_reviews;") == "1"
    assert db("SELECT count(*) FROM symptom_intake_audit WHERE action='clinician_reviewed';") == "1"


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
