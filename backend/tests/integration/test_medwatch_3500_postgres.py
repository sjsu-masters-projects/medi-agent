"""Form 3500 drafts, discard and external submission records in disposable PostgreSQL 16.

PV-001-C, migration 064. Reuses the notification-centre fixture, which applies the real
ledger in order, then 063 and 064. Synthetic data only; nothing here contacts FDA.
"""

import json
import os
from uuid import uuid4

import pytest

from tests.integration.test_adr_loop_postgres import assessment, draft, request, requested
from tests.integration.test_email_postgres import account, verified
from tests.integration.test_notification_centre_postgres import (
    CLINICIAN,
    OTHER,
    PATIENT,
    call,
    clinician,
)

pytest_plugins = ["tests.integration.test_notification_centre_postgres"]

pytestmark = pytest.mark.skipif(
    os.environ.get("NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER") != "1"
    or os.environ.get("ADR_LOOP_GAP_BASELINE") == "1",
    reason="explicit opt-in disposable Docker PostgreSQL contract check with 063 and 064",
)

FORM = {
    "form_version": "fda-3500-2025-09",
    "section_a": {"identifier": "XX-ABCD"},
    "section_b": {"report_types": ["adverse_event"], "report_date": None},
}
TODAY = "(now() AT TIME ZONE 'America/Los_Angeles')::date"
SHA = "1147d7c86bb002cba7fb9352ca8e3402524d8fa0236916b7bf7e5dcdcf88bf9c"


def fails(sql, statement):
    """The error text with its SQLSTATE, which the backend maps to an HTTP status."""
    return sql("\\set VERBOSITY verbose\n" + statement, succeeds=False)


def rpc(name, *args):
    return f"SET ROLE service_role; SELECT id FROM {name}({','.join(args)});"


def q(value):
    return "NULL" if value is None else "'" + str(value).replace("'", "''") + "'"


def form_draft(sql, adr, *, actor=CLINICIAN):
    draft_id = str(uuid4())
    sql(
        rpc(
            "create_medwatch_draft",
            q(adr),
            q(actor),
            f"{q(json.dumps(FORM))}::jsonb",
            "'[]'::jsonb",
            "'Synthetic rationale'",
            q(draft_id),
        )
    )
    return draft_id


def revision(sql, draft_id):
    return sql(f"SELECT revision FROM medwatch_drafts WHERE id='{draft_id}'")


def approve_call(sql, draft_id, *, version="medwatch-3500-approval-v1"):
    approval = {
        "attestation_version": version,
        "non_serious_attested": True,
        "acknowledged_warnings": [{"path": "section_b.narrative", "kind": "patient_name"}],
    }
    return rpc(
        "approve_medwatch_draft",
        q(draft_id),
        q(CLINICIAN),
        "'Synthetic approval note'",
        revision(sql, draft_id),
        f"{q(json.dumps(approval))}::jsonb",
    )


def approve(sql, draft_id):
    sql(approve_call(sql, draft_id))


def record_call(sql, draft_id, *, on=TODAY, method="fax", detail=None, attested="true"):
    return rpc(
        "record_medwatch_external_submission",
        q(draft_id),
        q(CLINICIAN),
        on,
        q(method),
        q(detail),
        "'SYN-REF-1'",
        attested,
        revision(sql, draft_id),
    )


def record(sql, draft_id):
    sql(record_call(sql, draft_id))
    return sql(f"SELECT id FROM medwatch_external_submissions WHERE medwatch_draft_id='{draft_id}'")


def amend_call(draft_id, amends_id, *, reason="Synthetic corrected date", on=TODAY):
    return rpc(
        "amend_medwatch_external_submission",
        q(draft_id),
        q(CLINICIAN),
        q(amends_id),
        on,
        "'mail'",
        "NULL",
        "'SYN-REF-2'",
        q(reason),
    )


def discard_call(sql, draft_id, *, actor=CLINICIAN, reason="Synthetic mistaken draft", rev=None):
    return rpc(
        "discard_medwatch_draft",
        q(draft_id),
        q(actor),
        q(reason),
        rev or revision(sql, draft_id),
    )


def discard(sql, draft_id):
    sql(discard_call(sql, draft_id))


def audit(sql, draft_id, event_type):
    return sql(
        f"SELECT count(*) FROM medwatch_draft_audit_events WHERE medwatch_draft_id='{draft_id}' AND event_type='{event_type}'"
    )


def review_items(sql, adr, *, actor=CLINICIAN):
    return [
        r
        for r in clinician(sql, actor=actor)["items"]
        if r["event_type"] == "adr_review" and r["source_id"] == adr
    ]


# R23: discard and return to review.


def test_discard_returns_the_assessment_to_review_with_one_clinician_item(sql):
    """R23.1 to R23.3, R23.6: one actionable adr_review, no patient item, no email."""
    verified(sql)
    account(sql, "preferences", {"records": True})
    verified(sql, actor=CLINICIAN, role="clinician")
    account(
        sql, "preferences", {"reviews": True, "records": True}, actor=CLINICIAN, role="clinician"
    )
    adr = assessment(sql)
    request(sql, adr)
    call(sql)
    draft_id = form_draft(sql, adr)
    [original] = review_items(sql, adr)
    assert not original["actionable"]
    emails = "SELECT count(*) FROM email_outbox"
    before = sql(emails)

    discard(sql, draft_id)

    assert sql(
        f"SELECT status||','||coalesce(last_review_action,'-')||','||coalesce(reviewed_by::text,'-')||','||coalesce(reviewed_at::text,'-') FROM adr_assessments WHERE id='{adr}'"
    ) == ("draft,-,-,-")
    rows = review_items(sql, adr)
    # The return to draft is a new event; the original stays History.
    assert len(rows) == 2
    [active] = [r for r in rows if r["actionable"]]
    assert active["id"] != original["id"] and active["created_at"] > original["created_at"]
    assert [r for r in requested(sql) if r["actionable"]] == []
    assert sql("SELECT status FROM adr_information_requests") == "cancelled"
    call(sql)
    clinician(sql)
    assert sql(emails) == before
    assert (
        sql("""SELECT count(*) FROM email_outbox o JOIN notification_receipts r ON r.id=o.receipt_id
      JOIN notification_events e ON e.id=r.event_id WHERE e.event_type='adr_review'""")
        == "0"
    )
    assert audit(sql, draft_id, "discarded") == "1"
    assert sql(
        f"SELECT event_data->>'reason'||','||(event_data->>'previous_status') FROM medwatch_draft_audit_events WHERE medwatch_draft_id='{draft_id}' AND event_type='discarded'"
    ) == ("Synthetic mistaken draft,draft")
    assert (
        sql(
            f"SELECT count(*) FROM adr_assessment_audit_events WHERE adr_assessment_id='{adr}' AND event_type='medwatch_draft_discarded'"
        )
        == "1"
    )
    assert sql(
        f"SELECT (discarded_at IS NOT NULL)::text||','||discarded_by||','||discard_reason FROM medwatch_drafts WHERE id='{draft_id}'"
    ) == (f"true,{CLINICIAN},Synthetic mistaken draft")


def test_one_active_draft_and_another_after_discard(sql):
    """R23.4: at most one non-discarded draft per assessment."""
    adr = assessment(sql)
    first = form_draft(sql, adr)
    assert sql(
        f"SELECT patient_reference||','||export_version FROM medwatch_drafts WHERE id='{first}'"
    ) == ("XX-ABCD,fda-3500-2025-09")
    assert "already been completed" in fails(
        sql,
        rpc(
            "create_medwatch_draft",
            q(adr),
            q(CLINICIAN),
            f"{q(json.dumps(FORM))}::jsonb",
            "'[]'::jsonb",
            "'Again'",
            q(uuid4()),
        ),
    )
    assert "duplicate key" in fails(
        sql,
        f"""SET ROLE service_role; INSERT INTO medwatch_drafts(adr_assessment_id,patient_id)
          VALUES('{adr}','{PATIENT}');""",
    )
    discard(sql, first)
    second = form_draft(sql, adr)
    assert sql(
        f"SELECT count(*) FILTER (WHERE discarded_at IS NULL)||','||count(*) FROM medwatch_drafts WHERE adr_assessment_id='{adr}'"
    ) == ("1,2")
    assert second != first


def test_discard_checks_assignment_revision_reason_and_state(sql):
    """R23.1, R23.5, R23.8, R24.1: SQLSTATEs the backend maps to 403, 409 and 422."""
    adr = assessment(sql)
    draft_id = form_draft(sql, adr)
    assert "42501" in fails(sql, discard_call(sql, draft_id, actor=OTHER))
    assert "40001" in fails(sql, discard_call(sql, draft_id, rev="99"))
    assert "22023" in fails(sql, discard_call(sql, draft_id, reason="   "))
    assert "22023" in fails(sql, discard_call(sql, draft_id, reason="x" * 2001))
    assert "P0002" in fails(sql, discard_call(sql, str(uuid4()), rev="1"))
    discard(sql, draft_id)
    assert "23514" in fails(sql, discard_call(sql, draft_id))
    # A discarded draft is frozen: no edit, approval or export.
    assert "23514" in fails(sql, approve_call(sql, draft_id))
    assert "23514" in fails(
        sql,
        f"SET ROLE service_role; UPDATE medwatch_drafts SET form_data='{{}}' WHERE id='{draft_id}';",
    )
    assert "23514" in fails(
        sql,
        rpc("record_medwatch_draft_export", q(draft_id), q(CLINICIAN), "'json'", "NULL", "NULL"),
    )


# R22: a submission made outside MediAgent.


def test_submitted_needs_approval_and_a_record_also_for_service_role(sql):
    """R22.6: the guard, not only the RPC, keeps a draft from being marked submitted."""
    draft_id = form_draft(sql, assessment(sql))
    mark = f"SET ROLE service_role; UPDATE medwatch_drafts SET status='submitted',submitted_at=now() WHERE id='{draft_id}';"
    assert "submitted only after approval" in fails(sql, mark)
    approve(sql, draft_id)
    assert "submitted only after approval" in fails(sql, mark)
    assert "submitted only after approval" in fails(
        sql,
        f"""SET ROLE service_role; INSERT INTO medwatch_drafts(adr_assessment_id,patient_id,status,submitted_at)
          VALUES('{assessment(sql)}','{PATIENT}','submitted',now());""",
    )
    assert "check constraint" in fails(
        sql,
        f"SET ROLE service_role; UPDATE medwatch_drafts SET submitted_at=now() WHERE id='{draft_id}';",
    )
    record(sql, draft_id)
    assert (
        sql(
            f"SELECT status||','||(submitted_at IS NOT NULL)::text FROM medwatch_drafts WHERE id='{draft_id}'"
        )
        == "submitted,true"
    )
    assert audit(sql, draft_id, "submission_recorded") == "1"


def test_submission_record_validates_date_method_and_attestation(sql):
    """R22.1, R22.2: not in the future, not before approval, attested, Other described."""
    draft_id = form_draft(sql, assessment(sql))
    assert "23514" in fails(sql, record_call(sql, draft_id))  # not approved yet
    approve(sql, draft_id)
    for statement in (
        record_call(sql, draft_id, on=f"{TODAY} + 1"),
        record_call(sql, draft_id, on=f"{TODAY} - 1"),
        record_call(sql, draft_id, attested="false"),
        record_call(sql, draft_id, method="other"),
        record_call(sql, draft_id, method="carrier_pigeon"),
    ):
        assert "22023" in fails(sql, statement)
    sql(record_call(sql, draft_id, method="other", detail="Synthetic courier"))
    assert sql("SELECT method||','||method_detail FROM medwatch_external_submissions") == (
        "other,Synthetic courier"
    )
    assert "23514" in fails(sql, record_call(sql, draft_id))


def test_a_submitted_draft_is_read_only_but_still_exportable(sql):
    """R22.5, R23.5, R21.1."""
    draft_id = form_draft(sql, assessment(sql))
    approve(sql, draft_id)
    record(sql, draft_id)
    assert "23514" in fails(sql, discard_call(sql, draft_id))
    assert "23514" in fails(
        sql,
        rpc(
            "update_medwatch_draft",
            q(draft_id),
            q(CLINICIAN),
            "'{}'::jsonb",
            "'[]'::jsonb",
            revision(sql, draft_id),
        ),
    )
    assert "cannot be changed" in fails(
        sql,
        f"SET ROLE service_role; UPDATE medwatch_drafts SET status='reviewed',submitted_at=NULL WHERE id='{draft_id}';",
    )
    sql(
        rpc("record_medwatch_draft_export", q(draft_id), q(CLINICIAN), "'pdf'", "'09/2025'", q(SHA))
    )
    assert sql(
        f"SELECT event_data->>'format'||','||(event_data->>'template_revision')||','||(event_data->>'template_sha256') FROM medwatch_draft_audit_events WHERE medwatch_draft_id='{draft_id}' AND event_type='exported'"
    ) == (f"pdf,09/2025,{SHA}")


def test_submission_history_is_append_only(sql):
    """R22.4, R24.2, R24.4: no role updates, deletes, truncates or inserts directly."""
    draft_id = form_draft(sql, assessment(sql))
    approve(sql, draft_id)
    record(sql, draft_id)
    table = "medwatch_external_submissions"
    for role in ("anon", "authenticated", "service_role"):
        for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
            assert sql(f"SELECT has_table_privilege('{role}','{table}','{privilege}')") == "f"
        assert "permission denied" in fails(sql, f"SET ROLE {role}; DELETE FROM {table};")
    assert sql(f"SELECT has_table_privilege('authenticated','{table}','SELECT')") == "t"
    assert "permission denied" in fails(
        sql, f"SET ROLE service_role; UPDATE {table} SET fda_reference='X';"
    )
    # Even the owner cannot rewrite history.
    assert "append only" in fails(sql, f"UPDATE {table} SET fda_reference='X';")
    assert sql(f"SELECT fda_reference FROM {table}") == "SYN-REF-1"


def test_amendment_keeps_the_original_and_requires_the_current_record(sql):
    """R22.7: an amendment is a new row with a reason; a stale amends_id conflicts."""
    draft_id = form_draft(sql, assessment(sql))
    approve(sql, draft_id)
    original = record(sql, draft_id)
    before = revision(sql, draft_id)
    assert "22023" in fails(sql, amend_call(draft_id, original, reason=" "))
    sql(amend_call(draft_id, original))
    assert "40001" in fails(sql, amend_call(draft_id, original))
    amendment = sql(f"SELECT id FROM medwatch_external_submissions WHERE amends_id='{original}'")
    sql(amend_call(draft_id, amendment, reason="Synthetic second correction"))
    assert sql(
        f"""SELECT string_agg(method||':'||fda_reference||':'||coalesce(amend_reason,'-'),'|' ORDER BY created_at)
          FROM medwatch_external_submissions WHERE medwatch_draft_id='{draft_id}'"""
    ) == (
        "fax:SYN-REF-1:-|mail:SYN-REF-2:Synthetic corrected date|"
        "mail:SYN-REF-2:Synthetic second correction"
    )
    assert audit(sql, draft_id, "submission_amended") == "2"
    assert revision(sql, draft_id) == before
    unsubmitted = form_draft(sql, assessment(sql))
    assert "23514" in fails(sql, amend_call(unsubmitted, original))


# R21.6, R19: approval and export records.


def test_approval_records_the_attestation_and_sets_the_report_date(sql):
    """R17.5, R19.3, R19.6; B4 defaults to the approval date (America/Los_Angeles)."""
    draft_id = form_draft(sql, assessment(sql))
    assert "22023" in fails(sql, approve_call(sql, draft_id, version="medwatch-3500-approval-v0"))
    approve(sql, draft_id)
    assert sql(
        f"""SELECT (event_data->>'attestation_version')||','||(event_data->>'non_serious_attested')||','||
          (event_data->'acknowledged_warnings'->0->>'kind')||','||(event_data->>'report_date_set')
          FROM medwatch_draft_audit_events WHERE medwatch_draft_id='{draft_id}' AND event_type='approved'"""
    ) == ("medwatch-3500-approval-v1,true,patient_name,true")
    assert sql(
        f"SELECT (form_data#>>'{{section_b,report_date}}')::date = {TODAY} FROM medwatch_drafts WHERE id='{draft_id}'"
    ) == ("t")


def test_two_argument_export_records_a_json_export(sql):
    """K-P3: callers deployed before 064 keep working and their export records a format."""
    draft_id = form_draft(sql, assessment(sql))
    assert "23514" in fails(sql, rpc("record_medwatch_draft_export", q(draft_id), q(CLINICIAN)))
    approve(sql, draft_id)
    sql(rpc("record_medwatch_draft_export", q(draft_id), q(CLINICIAN)))
    assert sql(
        f"SELECT event_data->>'format' FROM medwatch_draft_audit_events WHERE medwatch_draft_id='{draft_id}' AND event_type='exported'"
    ) == ("json")
    for args in (
        ("'pdf'", "NULL", "NULL"),
        ("'pdf'", "'09/2025'", "'abc'"),
        ("'xml'", "NULL", "NULL"),
    ):
        assert "22023" in fails(
            sql, rpc("record_medwatch_draft_export", q(draft_id), q(CLINICIAN), *args)
        )


def test_legacy_create_keeps_working_and_is_labelled_legacy(sql):
    """The 048 create still runs for a backend deployed before 064."""
    legacy = draft(sql, assessment(sql))
    assert sql(
        f"SELECT export_version||','||coalesce(patient_reference,'-') FROM medwatch_drafts WHERE id='{legacy}'"
    ) == ("fda-3500-legacy-048,-")


# R24: deletion and privileges.


def test_patient_deletion_removes_form_3500_data(sql):
    """R24.2: drafts, discards, submissions, amendments and their audit go with the patient."""
    adr = assessment(sql)
    discard(sql, form_draft(sql, adr))
    draft_id = form_draft(sql, adr)
    approve(sql, draft_id)
    sql(amend_call(draft_id, record(sql, draft_id)))
    owned = f"""SELECT (SELECT count(*) FROM medwatch_drafts WHERE patient_id='{PATIENT}')||','||
      (SELECT count(*) FROM medwatch_external_submissions WHERE patient_id='{PATIENT}')||','||
      (SELECT count(*) FROM medwatch_draft_audit_events WHERE adr_assessment_id='{adr}')||','||
      (SELECT count(*) FROM adr_assessment_audit_events WHERE adr_assessment_id='{adr}')"""
    assert sql(owned) == "2,2,6,3"
    # Clinician references stay RESTRICT until D1 is decided.
    assert "violates foreign key constraint" in fails(
        sql, f"DELETE FROM auth.users WHERE id='{CLINICIAN}';"
    )
    sql(f"DELETE FROM auth.users WHERE id='{PATIENT}';")
    assert sql(owned) == "0,0,0,0"
    assert sql(f"SELECT count(*) FROM clinicians WHERE id='{CLINICIAN}'") == "1"


def test_audit_stays_append_only_and_rpcs_are_service_role_only(sql):
    """R24.4."""
    draft_id = form_draft(sql, assessment(sql))
    discard(sql, draft_id)
    for table in ("medwatch_draft_audit_events", "adr_assessment_audit_events"):
        for role in ("anon", "authenticated", "service_role"):
            assert "permission denied" in fails(sql, f"SET ROLE {role}; DELETE FROM {table};")
            assert "permission denied" in fails(sql, f"SET ROLE {role}; TRUNCATE {table};")
    for function in (
        "create_medwatch_draft(uuid,uuid,jsonb,jsonb,text,uuid)",
        "approve_medwatch_draft(uuid,uuid,text,integer,jsonb)",
        "record_medwatch_draft_export(uuid,uuid,text,text,text)",
        "discard_medwatch_draft(uuid,uuid,text,integer)",
        "record_medwatch_external_submission(uuid,uuid,date,text,text,text,boolean,integer)",
        "amend_medwatch_external_submission(uuid,uuid,uuid,date,text,text,text,text)",
    ):
        for role, expected in (("anon", "f"), ("authenticated", "f"), ("service_role", "t")):
            assert sql(f"SELECT has_function_privilege('{role}','{function}','EXECUTE')") == (
                expected
            ), (function, role)
