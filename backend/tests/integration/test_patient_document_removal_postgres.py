"""Owned unused uploads only; real locking, grants, audit and refusal behavior (101)."""

import json
import os
import time
from uuid import uuid4

import pytest

from tests.integration.care_team_plan_harness import (
    CLINICIAN,
    PATIENT,
    SECOND_PATIENT,
    TEAM,
    finish,
)
from tests.integration.test_care_team_publication_postgres import draft
from tests.integration.test_care_team_records_postgres import document, fact, two_teams

pytest_plugins = ["tests.integration.care_team_plan_harness"]
pytestmark = [
    pytest.mark.timeout(600),
    pytest.mark.skipif(
        os.environ.get("CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER") != "1",
        reason="explicit opt-in disposable Docker PostgreSQL contracts",
    ),
]


def rpc(
    doc, patient=PATIENT, actor=PATIENT, name="remove_patient_document_upload", role="service_role"
):
    return f"SET ROLE {role}; SELECT public.{name}('{doc}','{patient}','{actor}');"


def snapshot(sql, doc):
    return sql(f"""SELECT jsonb_build_object(
      'doc',(SELECT to_jsonb(d) FROM documents d WHERE id='{doc}'),
      'sources',(SELECT coalesce(jsonb_agg(to_jsonb(p) ORDER BY id),'[]') FROM source_provenances p WHERE document_id='{doc}'),
      'facts',(SELECT coalesce(jsonb_agg(to_jsonb(f) ORDER BY id),'[]') FROM clinical_facts f),
      'audit',(SELECT coalesce(jsonb_agg(to_jsonb(e) ORDER BY id),'[]') FROM clinical_fact_audit_events e),
      'medications',(SELECT coalesce(jsonb_agg(to_jsonb(m) ORDER BY id),'[]') FROM medications m));""")


def test_removes_only_unused_owned_upload_and_replays_without_extra_audit(sql):
    two_teams(sql)
    doc = document(sql, team=TEAM, review="pending")
    candidate = fact(sql, doc)
    other = document(sql, team=TEAM, review="pending")
    status = json.loads(sql(rpc(doc, name="patient_document_removal_status")))
    assert status == {"can_remove": True, "reason": None}
    result = json.loads(sql(rpc(doc)))
    assert result["removed"] is True and result["replayed"] is False
    assert result["file_path"].startswith(PATIENT + "/")
    assert sql(f"SELECT count(*) FROM documents WHERE id='{doc}'") == "0"
    assert sql(f"SELECT count(*) FROM clinical_facts WHERE id='{candidate}'") == "0"
    assert sql(f"SELECT count(*) FROM documents WHERE id='{other}'") == "1"
    assert json.loads(sql(rpc(doc))) == {"removed": True, "replayed": True}
    assert (
        sql(
            f"SELECT count(*) FROM document_removal_events WHERE document_id='{doc}' AND actor_id='{PATIENT}'"
        )
        == "1"
    )


@pytest.mark.parametrize("review", ["approved", "rejected"])
def test_reviewed_source_without_candidates_is_retained_without_any_withdrawal(sql, review):
    two_teams(sql)
    doc = document(sql, team=TEAM, review=review)
    before = snapshot(sql, doc)
    assert json.loads(sql(rpc(doc, name="patient_document_removal_status")))["can_remove"] is False
    assert "requires care-team review" in sql(rpc(doc), succeeds=False)
    assert snapshot(sql, doc) == before


def test_clinician_source_is_never_patient_removable(sql):
    two_teams(sql)
    doc = document(sql, by=CLINICIAN, role="clinician", team=TEAM)
    before = snapshot(sql, doc)
    assert "requires care-team review" in sql(rpc(doc), succeeds=False)
    assert snapshot(sql, doc) == before


def test_an_unused_upload_cannot_remove_an_object_shared_with_another_record(sql):
    two_teams(sql)
    doc = document(sql, team=TEAM, review="pending")
    protected = document(sql, by=CLINICIAN, role="clinician", team=TEAM)
    sql(
        f"UPDATE documents SET file_path=(SELECT '/'||file_path FROM documents WHERE id='{doc}') WHERE id='{protected}'"
    )
    before = snapshot(sql, doc)
    assert json.loads(sql(rpc(doc, name="patient_document_removal_status"))) == {
        "can_remove": False,
        "reason": "used_in_record",
    }
    assert "requires care-team review" in sql(rpc(doc), succeeds=False)
    assert snapshot(sql, doc) == before
    assert sql("SELECT count(*) FROM documents") == "2"


@pytest.mark.parametrize(
    "mutation",
    [
        "reconciled",
        "corrected",
        "withdrawn",
        "legacy_medication",
        "active_processing",
        "summary_processing",
        "run_processing",
        "fact_approved",
        "fact_rejected",
        "annotation",
        "review_note",
        "unknown_review",
    ],
)
def test_protected_document_refusal_does_not_change_clinical_or_source_history(sql, mutation):
    two_teams(sql)
    doc = document(sql, team=TEAM, review="pending")
    candidate = fact(sql, doc)
    if mutation == "reconciled":
        sql(
            f"UPDATE clinical_facts SET reconciliation_state='kept_existing' WHERE id='{candidate}'"
        )
    elif mutation == "corrected":
        sql(
            f"INSERT INTO clinical_fact_audit_events(fact_id,actor_id,event_type) VALUES('{candidate}','{CLINICIAN}','corrected')"
        )
    elif mutation == "withdrawn":
        sql(f"UPDATE source_provenances SET withdrawn_at=now() WHERE document_id='{doc}'")
    elif mutation == "legacy_medication":
        sql(
            f"INSERT INTO medications(patient_id,name,dosage,frequency,route,source_document_id) VALUES('{PATIENT}','Synthetic medicine','10 mg','daily','oral','{doc}')"
        )
    elif mutation == "active_processing":
        sql(f"UPDATE documents SET parse_status='processing' WHERE id='{doc}'")
    elif mutation == "summary_processing":
        sql(f"UPDATE documents SET summary_status='processing' WHERE id='{doc}'")
    elif mutation == "run_processing":
        sql(
            f"INSERT INTO document_ingestion_runs(document_id,patient_id,status) VALUES('{doc}','{PATIENT}','processing')"
        )
    elif mutation == "fact_approved":
        sql(
            f"UPDATE clinical_facts SET review_state='approved',reviewed_by='{CLINICIAN}',reviewed_at=now() WHERE id='{candidate}'"
        )
    elif mutation == "fact_rejected":
        sql(f"UPDATE clinical_facts SET review_state='rejected' WHERE id='{candidate}'")
    elif mutation == "annotation":
        sql(
            f"UPDATE documents SET clinician_annotation='A recorded clinician note' WHERE id='{doc}'"
        )
    elif mutation == "review_note":
        sql(f"UPDATE documents SET review_note='Review needs follow-up' WHERE id='{doc}'")
    else:
        sql(f"UPDATE documents SET review_status=NULL WHERE id='{doc}'")
    before = snapshot(sql, doc)
    assert "requires care-team review" in sql(rpc(doc), succeeds=False)
    assert snapshot(sql, doc) == before
    assert sql("SELECT count(*) FROM document_removal_events") == "0"


def test_even_a_draft_plan_reference_preserves_the_pending_source(sql):
    two_teams(sql)
    _, version, items = draft(sql, TEAM, CLINICIAN, items=[{"name": "Synthetic medicine"}])
    source = sql(
        f"SELECT p.document_id FROM care_plan_items i JOIN evidence_citations c ON c.fact_id=i.source_fact_id JOIN source_provenances p ON p.id=c.provenance_id WHERE i.id='{items[0]}'"
    )
    sql(
        f"UPDATE documents SET uploaded_by='{PATIENT}',uploaded_by_role='patient',review_status='pending' WHERE id='{source}'"
    )
    before = snapshot(sql, source)
    assert "requires care-team review" in sql(rpc(source), succeeds=False)
    assert snapshot(sql, source) == before
    assert sql(f"SELECT count(*) FROM care_plan_items WHERE plan_version_id='{version}'") == "1"


def test_foreign_actor_and_forged_actor_are_refused(sql):
    two_teams(sql)
    doc = document(sql, team=TEAM, review="pending")
    before = snapshot(sql, doc)
    assert "Document unavailable" in sql(
        rpc(doc, patient=SECOND_PATIENT, actor=SECOND_PATIENT), succeeds=False
    )
    assert "Patient actor required" in sql(rpc(doc, actor=CLINICIAN), succeeds=False)
    assert "Document unavailable" in sql(rpc(str(uuid4())), succeeds=False)
    assert snapshot(sql, doc) == before


@pytest.mark.parametrize("role", ["authenticated", "anon"])
def test_client_roles_cannot_call_removal_functions_or_mutate_audit(sql, role):
    two_teams(sql)
    doc = document(sql, team=TEAM, review="pending")
    for name in ("remove_patient_document_upload", "patient_document_removal_status"):
        assert "permission denied" in sql(rpc(doc, name=name, role=role), succeeds=False)
    assert "permission denied" in sql(
        f"SET ROLE {role}; SELECT * FROM document_removal_events", succeeds=False
    )
    assert "permission denied" in sql(
        "SET ROLE service_role; DELETE FROM document_removal_events", succeeds=False
    )


def test_concurrent_review_wins_before_removal_and_no_source_is_withdrawn(sql):
    two_teams(sql)
    doc = document(sql, team=TEAM, review="pending")
    review = sql.start(
        f"BEGIN; UPDATE documents SET review_status='approved' WHERE id='{doc}'; SELECT pg_sleep(1); COMMIT;",
        "removal-review-owner",
    )
    for _ in range(100):
        if (
            sql(
                "SELECT count(*) FROM pg_stat_activity WHERE application_name='removal-review-owner' AND wait_event='PgSleep'"
            )
            == "1"
        ):
            break
        time.sleep(0.01)
    else:
        pytest.fail("Review transaction did not reach its lock checkpoint")
    removal = sql.start(rpc(doc), "removal-contender")
    assert finish(review)[0] == 0
    code, _, error = finish(removal)
    assert code != 0 and "requires care-team review" in error
    assert sql(f"SELECT review_status FROM documents WHERE id='{doc}'") == "approved"
    assert sql("SELECT count(*) FROM document_removal_events") == "0"


def test_removal_refuses_a_reverse_fence_lock_without_deadlocking(sql):
    two_teams(sql)
    doc = document(sql, team=TEAM, review="pending")
    fence = sql.start(
        f"BEGIN; SELECT private.lock_care_plan_evidence('{PATIENT}',true); SELECT pg_sleep(1); COMMIT;",
        "removal-evidence-owner",
    )
    for _ in range(100):
        if (
            sql(
                "SELECT count(*) FROM pg_stat_activity WHERE application_name='removal-evidence-owner' AND wait_event='PgSleep'"
            )
            == "1"
        ):
            break
        time.sleep(0.01)
    else:
        pytest.fail("Evidence transaction did not reach its checkpoint")
    removal = sql.start(rpc(doc), "removal-fence-contender")
    code, _, error = finish(removal)
    assert code != 0 and "changed concurrently" in error
    assert finish(fence)[0] == 0
    assert sql(f"SELECT count(*) FROM documents WHERE id='{doc}'") == "1"
    assert sql("SELECT count(*) FROM document_removal_events") == "0"


def test_simultaneous_removals_produce_one_audit_and_one_replay(sql):
    two_teams(sql)
    doc = document(sql, team=TEAM, review="pending")
    first = sql.start("BEGIN; " + rpc(doc) + " SELECT pg_sleep(1); COMMIT;", "removal-first")
    for _ in range(100):
        if (
            sql(
                "SELECT count(*) FROM pg_stat_activity WHERE application_name='removal-first' AND wait_event='PgSleep'"
            )
            == "1"
        ):
            break
        time.sleep(0.01)
    else:
        pytest.fail("Removal transaction did not reach its checkpoint")
    second = sql.start(rpc(doc), "removal-second")
    assert finish(first)[0] == 0
    code, output, error = finish(second)
    assert code == 0, error
    assert json.loads(output)["replayed"] is True
    assert sql("SELECT count(*) FROM document_removal_events") == "1"
