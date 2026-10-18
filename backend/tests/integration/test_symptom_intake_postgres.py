"""Disposable local SQL; synthetic approval fixtures never enable the runtime library."""

import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from tests.integration.test_chat_safety_postgres import _docker_postgres

pytestmark = pytest.mark.skipif(
    os.environ.get("SYMPTOM_INTAKE_TEST_POSTGRES") != "1",
    reason="explicit local SQL opt-in required",
)
MIGRATIONS = Path(__file__).resolve().parents[2] / "src/app/db/migrations"
PATIENT = "00000000-0000-0000-0000-000000000001"
CLINICIAN = "00000000-0000-0000-0000-000000000002"
OTHER = "00000000-0000-0000-0000-000000000003"
TURN = "00000000-0000-0000-0000-000000000004"


@pytest.fixture(scope="module")
def postgres():
    yield from _docker_postgres()


@pytest.fixture
def sql(postgres):
    database = "safety_" + uuid4().hex
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
            input="SET statement_timeout='8s';\n" + statement,
            capture_output=True,
            text=True,
            timeout=12,
        )
        assert (result.returncode == 0) is succeeds, result.stderr
        return result.stdout.strip() if succeeds else result.stderr

    def start(statement):
        child = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        children.append(child)
        child.stdin.write("SET statement_timeout='8s';\n" + statement)
        child.stdin.close()
        return child

    execute.start = start
    execute("""
        CREATE SCHEMA auth;
        CREATE TABLE auth.users(id uuid PRIMARY KEY);
        CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('test.actor', true),'')::uuid $$;
        CREATE SCHEMA private;
    """)
    for name in (
        "001_initial_schema.sql",
        "002_rls_policies.sql",
        "005_document_parse_tracking.sql",
        "006_care_team_invite_compat.sql",
        "007_clinic_identity_foundation.sql",
        "010_chat_state_and_a2a_tasks.sql",
        "012_document_review_queue.sql",
        "014_patient_timezones_and_reminder_schedules.sql",
        "017_clinical_facts_provenance.sql",
        "051_health_knowledge_and_chat_sessions.sql",
        "059_chat_safety_alerts.sql",
        "060_confirmed_symptom_intake.sql",
        "076_confirmed_symptom_adr_handoff.sql",
    ):
        execute((MIGRATIONS / name).read_text())
    execute(f"""
        INSERT INTO auth.users VALUES ('{PATIENT}'),('{CLINICIAN}'),('{OTHER}');
        INSERT INTO patients(id,email,first_name,last_name,date_of_birth) VALUES
          ('{PATIENT}','one@synthetic.invalid','Synthetic','Patient','1960-01-01'),
          ('{OTHER}','other@synthetic.invalid','Other','Patient','1960-01-01');
        INSERT INTO clinicians(id,email,first_name,last_name,specialty,clinic_name) VALUES
          ('{CLINICIAN}','reviewer@synthetic.invalid','Synthetic','Reviewer','Synthetic','Synthetic');
        INSERT INTO care_teams(patient_id,clinician_id,role,status)
          VALUES ('{PATIENT}','{CLINICIAN}','primary','active');
    """)
    try:
        yield execute
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)


def call_sql(action, payload, patient=PATIENT):
    body = json.dumps(payload).replace("'", "''")
    return f"SET ROLE service_role; SELECT public.symptom_intake_operation('{patient}','{action}','{body}');"


def start(sql):
    sql("""SELECT public.set_symptom_question_eligibility('synthetic-test-only',repeat('a',64),'approved',
      '{"reference":"synthetic test only","reviewer_identity":"fixture","reviewer_role":"test","date":"2026-10-12"}');""")
    sql(
        f"INSERT INTO chat_messages(id,patient_id,role,content,session_id) VALUES('{TURN}','{PATIENT}','user','Synthetic event','default');"
    )
    return json.loads(
        sql(
            call_sql(
                "start",
                {
                    "source_message_id": TURN,
                    "session_id": "default",
                    "library_version": "synthetic-test-only",
                    "library_hash": "a" * 64,
                    "timezone": "UTC",
                },
            )
        )
    )


def test_source_identity_revision_cancel_and_private_draft(sql):
    v = start(sql)
    assert json.loads(sql(call_sql("read", {"intake_id": v["id"]})))["id"] == v["id"]
    sql(call_sql("read", {"intake_id": v["id"]}, OTHER), succeeds=False)
    sql(call_sql("start", {"source_message_id": TURN, "session_id": "other"}), succeeds=False)
    mutation = {
        "intake_id": v["id"],
        "expected_revision": 0,
        "mutation_id": str(uuid4()),
        "answer": {
            "question_id": "severity",
            "state": "unknown",
            "value": None,
            "locale": "en-US",
            "wording": "unknown",
        },
    }
    updated = json.loads(sql(call_sql("answer", mutation)))
    assert updated["answers"]["severity"]["value"] is None
    assert json.loads(sql(call_sql("answer", mutation)))["revision"] == 1
    mutation["answer"]["state"] = "declined"
    sql(call_sql("answer", mutation), succeeds=False)
    sql(
        call_sql(
            "cancel", {"intake_id": v["id"], "expected_revision": 0, "mutation_id": str(uuid4())}
        ),
        succeeds=False,
    )
    final = json.loads(
        sql(
            call_sql(
                "cancel",
                {"intake_id": v["id"], "expected_revision": 1, "mutation_id": str(uuid4())},
            )
        )
    )
    assert final["status"] == "cancelled"
    assert sql("SELECT count(*) FROM symptom_reports;") == "0"
    assert sql("SELECT count(*) FROM adr_assessments;") == "0"
    sql(
        f"SET ROLE authenticated; SELECT set_config('test.actor','{OTHER}',false); SELECT id,answers FROM symptom_intakes;"
    )
    assert (
        sql(
            f"SET ROLE authenticated; SELECT set_config('test.actor','{OTHER}',false); SELECT count(*) FROM symptom_intakes;"
        ).splitlines()[-1]
        == "0"
    )
    assert (
        sql(
            f"SET ROLE authenticated; SELECT set_config('test.actor','{PATIENT}',false); SELECT count(*) FROM symptom_intakes;"
        ).splitlines()[-1]
        == "1"
    )
    sql(
        f"SET ROLE authenticated; DELETE FROM symptom_intakes WHERE id='{v['id']}';", succeeds=False
    )
    sql(
        call_sql("read", {"intake_id": v["id"]}).replace("ROLE service_role", "ROLE authenticated"),
        succeeds=False,
    )
    sql("UPDATE symptom_intake_audit SET action='forged';", succeeds=False)
    sql("UPDATE chat_messages SET content='Changed';", succeeds=False)


def test_one_active_draft_and_no_direct_report_insert(sql):
    v = start(sql)
    other_turn = str(uuid4())
    sql(
        f"INSERT INTO chat_messages(id,patient_id,role,content,session_id) VALUES('{other_turn}','{PATIENT}','user','Next event','default');"
    )
    result = json.loads(
        sql(call_sql("start", {"source_message_id": other_turn, "session_id": "default"}))
    )
    assert result["id"] == v["id"]
    sql(
        f"SET ROLE service_role; INSERT INTO symptom_reports(patient_id,symptom,severity) VALUES('{PATIENT}','Bypass',3);",
        succeeds=False,
    )
    sql(
        f"INSERT INTO symptom_reports(patient_id,symptom,severity) VALUES('{PATIENT}','Bypass',3);",
        succeeds=False,
    )


def ready(sql):
    v = start(sql)
    for q in (
        "description",
        "location",
        "onset",
        "duration",
        "course",
        "severity",
        "associated",
        "red_flags",
        "product",
        "history",
        "outcome",
    ):
        v = json.loads(
            sql(
                call_sql(
                    "answer",
                    {
                        "intake_id": v["id"],
                        "expected_revision": v["revision"],
                        "mutation_id": str(uuid4()),
                        "answer": {
                            "question_id": q,
                            "state": "unknown",
                            "value": None,
                            "locale": "en-US",
                            "wording": "",
                        },
                    },
                )
            )
        )
    snapshot = {
        "schema_version": "symptom-report/1",
        "answers": v["answers"],
        "context": {
            "version": "symptom-context/1",
            "purpose": "patient_symptom_preview",
            "medications": [],
            "facts": [],
            "excerpts": [],
        },
        "summary": "Synthetic SQL fixture only",
        "locale": v["locale"],
        "timezone": v["timezone"],
        "library_version": v["library_version"],
        "library_hash": v["library_hash"],
        "source_message_id": TURN,
        "session_id": "default",
    }
    return json.loads(
        sql(
            call_sql(
                "preview",
                {"intake_id": v["id"], "expected_revision": v["revision"], "preview": snapshot},
            )
        )
    )


def confirmation(v, identity=None):
    return {
        "intake_id": v["id"],
        "expected_revision": v["revision"],
        "preview_hash": v["preview_hash"],
        "confirmation_id": identity or str(uuid4()),
        "consent": True,
    }


def ready_with_product_concern(sql):
    medication = str(uuid4())
    sql(
        f"INSERT INTO medications(id,patient_id,name,dosage,frequency) VALUES"
        f"('{medication}','{PATIENT}','Metformin','500 mg','once daily');"
    )
    v = start(sql)
    for q in (
        "description",
        "location",
        "onset",
        "duration",
        "course",
        "severity",
        "associated",
        "red_flags",
        "product",
        "concomitant",
        "history",
        "outcome",
    ):
        value = (
            "Nausea"
            if q == "description"
            else 4
            if q == "severity"
            else {"concern": True, "name": "metformin"}
            if q == "product"
            else None
        )
        v = json.loads(
            sql(
                call_sql(
                    "answer",
                    {
                        "intake_id": v["id"],
                        "expected_revision": v["revision"],
                        "mutation_id": str(uuid4()),
                        "answer": {
                            "question_id": q,
                            "state": "answered" if value is not None else "unknown",
                            "value": value,
                            "locale": "en-US",
                            "wording": "",
                        },
                    },
                )
            )
        )
    context = json.loads(sql(f"SELECT symptom_intake_context('{PATIENT}','{v['id']}');"))
    assert len(context["medications"]) == 1
    assert context["medications"][0]["source_id"] == medication
    assert context["medications"][0]["name"] == "Metformin"
    snapshot = {
        "schema_version": "symptom-report/1",
        "answers": v["answers"],
        "context": context,
        "summary": "Synthetic product concern",
        "locale": v["locale"],
        "timezone": v["timezone"],
        "library_version": v["library_version"],
        "library_hash": v["library_hash"],
        "source_message_id": TURN,
        "session_id": "default",
    }
    return json.loads(
        sql(
            call_sql(
                "preview",
                {"intake_id": v["id"], "expected_revision": v["revision"], "preview": snapshot},
            )
        )
    )


def test_confirm_once_retry_conflict_unknown_and_immutable(sql):
    v = ready(sql)
    request = confirmation(v)
    saved = json.loads(sql(call_sql("confirm", request)))
    assert saved["status"] == "confirmed"
    assert (
        json.loads(sql(call_sql("confirm", request)))["confirmed_report_id"]
        == saved["confirmed_report_id"]
    )
    assert (
        json.loads(sql(call_sql("confirm", confirmation(v))))["confirmed_report_id"]
        == saved["confirmed_report_id"]
    )
    request["preview_hash"] = "b" * 64
    sql(call_sql("confirm", request), succeeds=False)
    report = json.loads(sql(call_sql("report", {"report_id": saved["confirmed_report_id"]})))
    assert report["severity"] is None
    assert report["confirmation_state"] == "patient_confirmed"
    assert report["confirmed_by"] == PATIENT
    assert report["confirmed_at"]
    assert sql("SELECT count(*) FROM symptom_reports;") == "1"
    assert sql("SELECT count(*) FROM symptom_intake_audit WHERE action='confirm';") == "1"
    sql("UPDATE symptom_reports SET symptom='Rewritten';", succeeds=False)
    sql("DELETE FROM symptom_reports;", succeeds=False)
    sql(call_sql("report", {"report_id": report["id"]}, OTHER), succeeds=False)


def test_confirmed_product_concern_atomically_enqueues_one_report_task(sql):
    v = ready_with_product_concern(sql)
    saved = json.loads(sql(call_sql("confirm", confirmation(v))))
    json.loads(sql(call_sql("confirm", confirmation(v))))

    assert sql("SELECT count(*) FROM symptom_reports;") == "1"
    assert sql("SELECT count(*) FROM a2a_tasks;") == "1"
    assert sql("SELECT status FROM a2a_tasks;") == "submitted"
    assert sql("SELECT symptom_event_id::text FROM a2a_tasks;") == saved["confirmed_report_id"]
    assert (
        sql("SELECT input_payload->'symptom_report'->>'confirmation_state' FROM a2a_tasks;")
        == "patient_confirmed"
    )


def test_stale_preview_and_revoked_library_cannot_confirm(sql):
    v = ready(sql)
    payload = confirmation(v)
    sql("UPDATE symptom_question_eligibility SET status='revoked';")
    sql(call_sql("confirm", payload), succeeds=False)
    assert sql("SELECT count(*) FROM symptom_reports;") == "0"
    sql(
        call_sql(
            "cancel",
            {"intake_id": v["id"], "expected_revision": v["revision"], "mutation_id": str(uuid4())},
        )
    )


def test_answer_correction_invalidates_preview(sql):
    v = ready(sql)
    old = confirmation(v)
    updated = json.loads(
        sql(
            call_sql(
                "answer",
                {
                    "intake_id": v["id"],
                    "expected_revision": v["revision"],
                    "mutation_id": str(uuid4()),
                    "answer": {
                        "question_id": "severity",
                        "state": "answered",
                        "value": 3,
                        "wording": "3",
                        "locale": "en-US",
                    },
                },
            )
        )
    )
    assert updated["preview"] is None
    old["expected_revision"] = updated["revision"]
    sql(call_sql("confirm", old), succeeds=False)


def test_confirmation_audit_failure_rolls_back_entire_save(sql):
    v = ready(sql)
    sql("""CREATE FUNCTION synthetic_audit_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        IF NEW.action='confirm' THEN RAISE EXCEPTION 'Synthetic failure'; END IF; RETURN NEW; END $$;
        CREATE TRIGGER synthetic_failure BEFORE INSERT ON symptom_intake_audit FOR EACH ROW EXECUTE FUNCTION synthetic_audit_failure();""")
    sql(call_sql("confirm", confirmation(v)), succeeds=False)
    assert sql("SELECT count(*) FROM symptom_reports;") == "0"
    assert sql("SELECT status FROM symptom_intakes;") == "ready_for_confirmation"


def test_simultaneous_distinct_confirmation_keys_create_one_report(sql):
    v = ready(sql)
    first = sql.start(call_sql("confirm", confirmation(v)))
    second = sql.start(call_sql("confirm", confirmation(v)))
    for p in (first, second):
        assert p.wait(timeout=10) == 0, p.stderr.read()
    assert sql("SELECT count(*) FROM symptom_reports;") == "1"


def test_confirm_cancel_race_has_one_terminal_outcome(sql):
    v = ready(sql)
    first = sql.start(call_sql("confirm", confirmation(v)))
    second = sql.start(
        call_sql(
            "cancel",
            {"intake_id": v["id"], "expected_revision": v["revision"], "mutation_id": str(uuid4())},
        )
    )
    codes = [p.wait(timeout=10) for p in (first, second)]
    assert sorted(codes) == [0, 3]
    assert sql("SELECT count(*) FROM symptom_reports;") in {"0", "1"}
    assert sql("SELECT status FROM symptom_intakes;") in {"cancelled", "confirmed"}


def test_safety_interrupt_is_private_and_durable_without_report(sql):
    v = start(sql)
    result = json.loads(
        sql(
            call_sql(
                "interrupt",
                {
                    "intake_id": v["id"],
                    "expected_revision": 0,
                    "mutation_id": str(uuid4()),
                    "safety": {
                        "safety_rule": "emergency_symptom_keyword",
                        "rule_version": "triage-floor/1",
                        "result": "interrupted_safety",
                    },
                },
            )
        )
    )
    assert result["status"] == "interrupted_safety"
    assert sql("SELECT count(*) FROM chat_messages;") == "1"
    assert sql("SELECT count(*) FROM symptom_reports;") == "0"
    sql("SELECT deliver_symptom_intake_safety_alerts();")
    sql("SELECT deliver_symptom_intake_safety_alerts();")
    assert sql("SELECT count(*) FROM clinician_messages;") == "1"
    assert "Private answers" in sql("SELECT body FROM clinician_messages;")


def test_reassignment_removes_confirmed_report_browser_access(sql):
    v = ready(sql)
    sql(call_sql("confirm", confirmation(v)))
    sql("GRANT SELECT ON care_teams,clinicians TO authenticated;")
    assert (
        sql(
            f"SET ROLE authenticated; SELECT set_config('test.actor','{CLINICIAN}',false); SELECT count(*) FROM symptom_reports;"
        ).splitlines()[-1]
        == "1"
    )
    sql("UPDATE care_teams SET status='inactive';")
    assert (
        sql(
            f"SET ROLE authenticated; SELECT set_config('test.actor','{CLINICIAN}',false); SELECT count(*) FROM symptom_reports;"
        ).splitlines()[-1]
        == "0"
    )
    assert (
        sql(
            f"SET ROLE authenticated; SELECT set_config('test.actor','{CLINICIAN}',false); SELECT count(*) FROM symptom_intakes;"
        ).splitlines()[-1]
        == "0"
    )


def test_context_budgets_exact_product_approval_and_withdrawal(sql):
    v = ready(sql)
    medication = str(uuid4())
    sql(
        f"INSERT INTO medications(id,patient_id,name,dosage,frequency) VALUES('{medication}','{PATIENT}','Synthetic product','synthetic dose','synthetic frequency');"
    )
    for _ in range(7):
        fact, provenance, citation = (str(uuid4()) for _ in range(3))
        sql(f"""INSERT INTO clinical_facts(id,patient_id,fact_type,subject_type,subject_id,value,review_state,reviewed_by,reviewed_at)
          VALUES('{fact}','{PATIENT}','synthetic_context','medication','{medication}','{{"synthetic":true}}','approved','{CLINICIAN}',now());
          INSERT INTO source_provenances(id,artifact_type,source_system,source_reference)
          VALUES('{provenance}','clinician_entry','synthetic','synthetic-source');
          INSERT INTO evidence_citations(id,fact_id,provenance_id,excerpt)
          VALUES('{citation}','{fact}','{provenance}',repeat('synthetic ',100));""")
    answer = {
        "question_id": "product",
        "state": "answered",
        "value": {"concern": True, "name": "Synthetic product"},
        "locale": "en-US",
        "wording": "Synthetic product",
    }
    v = json.loads(
        sql(
            call_sql(
                "answer",
                {
                    "intake_id": v["id"],
                    "expected_revision": v["revision"],
                    "mutation_id": str(uuid4()),
                    "answer": answer,
                },
            )
        )
    )
    v = json.loads(
        sql(
            call_sql(
                "answer",
                {
                    "intake_id": v["id"],
                    "expected_revision": v["revision"],
                    "mutation_id": str(uuid4()),
                    "answer": {
                        "question_id": "concomitant",
                        "state": "unknown",
                        "value": None,
                        "locale": "en-US",
                    },
                },
            )
        )
    )
    context = json.loads(
        sql(f"SET ROLE service_role; SELECT symptom_intake_context('{PATIENT}','{v['id']}');")
    )
    assert len(context["medications"]) == 1
    assert len(context["facts"]) == 5
    assert len(context["excerpts"]) == 2
    assert all(len(item["text"]) <= 500 for item in context["excerpts"])
    snapshot = {
        "schema_version": "symptom-report/1",
        "answers": v["answers"],
        "context": context,
        "summary": "Synthetic preview",
        **{
            key: v[key]
            for key in (
                "locale",
                "timezone",
                "library_version",
                "library_hash",
                "source_message_id",
                "session_id",
            )
        },
    }
    v = json.loads(
        sql(
            call_sql(
                "preview",
                {"intake_id": v["id"], "expected_revision": v["revision"], "preview": snapshot},
            )
        )
    )
    sql(
        f"UPDATE clinical_facts SET review_state='rejected' WHERE id='{context['facts'][0]['source_id']}';"
    )
    assert "INTAKE_PREVIEW_STALE" in sql(call_sql("confirm", confirmation(v)), succeeds=False)
    assert sql("SELECT count(*) FROM symptom_reports;") == "0"
    sql(f"SELECT symptom_intake_context('{OTHER}','{v['id']}');", succeeds=False)
    sql(
        f"SET ROLE authenticated; SELECT symptom_intake_context('{PATIENT}','{v['id']}');",
        succeeds=False,
    )


def test_private_and_unapproved_documents_are_not_preview_sources(sql):
    v = ready(sql)
    medication, document, fact, provenance = (str(uuid4()) for _ in range(4))
    sql(f"""INSERT INTO medications(id,patient_id,name,dosage,frequency) VALUES('{medication}','{PATIENT}','Synthetic product','synthetic','synthetic');
      INSERT INTO documents(id,patient_id,uploaded_by,uploaded_by_role,document_type,file_name,file_url,file_size_bytes,parse_status,review_status,visibility)
      VALUES('{document}','{PATIENT}','{PATIENT}','patient','other','synthetic.txt','synthetic-only',1,'completed','pending','all_providers');
      INSERT INTO clinical_facts(id,patient_id,fact_type,subject_type,subject_id,value,review_state,reviewed_by,reviewed_at)
      VALUES('{fact}','{PATIENT}','synthetic_context','medication','{medication}','{{}}','approved','{CLINICIAN}',now());
      INSERT INTO source_provenances(id,artifact_type,source_system,source_reference,document_id)
      VALUES('{provenance}','document','synthetic','synthetic-only','{document}');
      INSERT INTO evidence_citations(fact_id,provenance_id,excerpt) VALUES('{fact}','{provenance}','Synthetic exact evidence');""")
    v = json.loads(
        sql(
            call_sql(
                "answer",
                {
                    "intake_id": v["id"],
                    "expected_revision": v["revision"],
                    "mutation_id": str(uuid4()),
                    "answer": {
                        "question_id": "product",
                        "state": "answered",
                        "value": {"concern": True, "name": "Synthetic product"},
                        "locale": "en-US",
                    },
                },
            )
        )
    )

    def context():
        return json.loads(sql(f"SELECT symptom_intake_context('{PATIENT}','{v['id']}');"))

    assert context()["facts"] == []
    sql(f"UPDATE documents SET review_status='approved' WHERE id='{document}';")
    assert len(context()["facts"]) == 1
    sql(f"UPDATE documents SET visibility='specific_provider' WHERE id='{document}';")
    assert context()["facts"] == []


def test_delegated_work_requires_canonical_confirmed_testimony(sql):
    v = ready(sql)
    payload = json.dumps({"symptom_report": {"id": str(uuid4()), "severity": 10}})
    statement = f"INSERT INTO a2a_tasks(patient_id,source_agent,target_agent,task_type,input_payload,idempotency_key) VALUES('{PATIENT}','symptom','pharmacovigilance','symptom_adr_screen','{payload}',gen_random_uuid()::text);"
    sql(statement, succeeds=False)
    saved = json.loads(sql(call_sql("confirm", confirmation(v))))
    payload = json.dumps({"symptom_report": {"id": saved["confirmed_report_id"], "severity": 10}})
    sql(
        f"INSERT INTO a2a_tasks(patient_id,source_agent,target_agent,task_type,input_payload,idempotency_key) VALUES('{PATIENT}','symptom','pharmacovigilance','symptom_adr_screen','{payload}',gen_random_uuid()::text);"
    )
    assert sql("SELECT input_payload->'symptom_report'->'severity' FROM a2a_tasks;") == "null"
    sql("UPDATE a2a_tasks SET status='working';")
    assert (
        sql("SELECT input_payload->'symptom_report'->>'confirmation_state' FROM a2a_tasks;")
        == "patient_confirmed"
    )


def test_safety_delivery_failure_is_retained_then_retry_delivers_once(sql):
    v = start(sql)
    sql(
        call_sql(
            "interrupt",
            {
                "intake_id": v["id"],
                "expected_revision": 0,
                "mutation_id": str(uuid4()),
                "safety": {
                    "safety_rule": "emergency_symptom_keyword",
                    "rule_version": "triage-floor/1",
                    "response_text": "Synthetic fixture only",
                },
            },
        )
    )
    sql("""CREATE FUNCTION private.synthetic_delivery_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
      RAISE EXCEPTION 'Synthetic delivery failure'; END $$;
      CREATE TRIGGER synthetic_failure BEFORE INSERT ON clinician_messages FOR EACH ROW EXECUTE FUNCTION private.synthetic_delivery_failure();""")
    sql("SELECT deliver_symptom_intake_safety_alerts();", succeeds=False)
    assert sql("SELECT delivery_state FROM symptom_intake_safety_alerts;") == "pending"
    assert sql("SELECT count(*) FROM clinician_messages;") == "0"
    sql(
        "DROP TRIGGER synthetic_failure ON clinician_messages; SELECT deliver_symptom_intake_safety_alerts(); SELECT deliver_symptom_intake_safety_alerts();"
    )
    assert sql("SELECT count(*) FROM clinician_messages;") == "1"
    assert sql("SELECT delivery_state FROM symptom_intake_safety_alerts;") == "delivered"
    assert sql("SELECT count(*) FROM symptom_reports;") == "0"


def test_emergency_alert_does_not_depend_on_stale_revision_or_cancelled_draft(sql):
    v = start(sql)
    sql(
        call_sql(
            "cancel", {"intake_id": v["id"], "expected_revision": 0, "mutation_id": str(uuid4())}
        )
    )
    payload = {
        "intake_id": v["id"],
        "expected_revision": 0,
        "mutation_id": str(uuid4()),
        "safety": {
            "safety_rule": "emergency_symptom_keyword",
            "rule_version": "triage-floor/1",
            "response_text": "Synthetic fixture only",
        },
    }
    result = json.loads(sql(call_sql("interrupt", payload)))
    assert result["status"] == "cancelled"
    assert result["safety"]["evaluated_at"]
    sql(call_sql("interrupt", payload))
    assert sql("SELECT count(*) FROM symptom_intake_safety_alerts;") == "1"
    assert sql("SELECT count(*) FROM symptom_reports;") == "0"


@pytest.mark.asyncio
async def test_service_to_real_sql_complete_synthetic_journey(sql, monkeypatch):
    """Transport shim exercises the real service and transactions, not remote PostgREST."""
    from types import SimpleNamespace

    from app.models.auth import CurrentUser
    from app.models.symptom_intake import IntakeAnswer, IntakeConfirm, IntakeStart
    from app.services.symptom_intake_service import SymptomIntakeService
    from tests.unit.intake.test_library import synthetic_bundle

    bundle = synthetic_bundle().model_copy(update={"version": "synthetic-service-journey-only"})
    approval = json.dumps(
        {
            "reference": "disposable synthetic test only",
            "reviewer_identity": "fixture",
            "reviewer_role": "test",
            "date": "2026-10-12",
        }
    )
    sql(
        f"SELECT set_symptom_question_eligibility('{bundle.version}','{bundle.checksum}','approved','{approval}');"
    )
    sql(
        f"UPDATE patients SET preferred_language='es-MX',timezone='America/Los_Angeles' WHERE id='{PATIENT}';"
    )
    sql(
        f"INSERT INTO chat_messages(id,patient_id,role,content,language,session_id) VALUES('{TURN}','{PATIENT}','user','Synthetic event','es-MX','default');"
    )

    class Rpc:
        def __init__(self, name, params):
            self.name, self.params = name, params

        def execute(self):
            if self.name == "symptom_intake_operation":
                statement = call_sql(
                    self.params["p_action"], self.params["p_payload"], self.params["p_patient_id"]
                )
            else:
                assert self.name == "symptom_intake_context"
                statement = f"SET ROLE service_role; SELECT symptom_intake_context('{self.params['p_patient_id']}','{self.params['p_intake_id']}');"
            return SimpleNamespace(data=json.loads(sql(statement)))

    class Table:
        def __init__(self, name):
            assert name in {"patients", "chat_messages"}
            self.name, self.filters, self.one = name, [], False

        def select(self, fields):
            self.fields = fields
            return self

        def eq(self, key, value):
            assert key in {"id", "patient_id"}
            self.filters.append(f"{key}='{value}'")
            return self

        def single(self):
            self.one = True
            return self

        def execute(self):
            statement = f"SELECT coalesce(jsonb_agg(to_jsonb(t)),'[]') FROM (SELECT {self.fields} FROM {self.name} WHERE {' AND '.join(self.filters)}) t;"
            rows = json.loads(sql(statement))
            return SimpleNamespace(data=rows[0] if self.one else rows)

    db = SimpleNamespace(rpc=lambda name, params: Rpc(name, params), table=Table)
    service = SymptomIntakeService(
        db, CurrentUser(id=PATIENT, email="synthetic@invalid.test", role="patient")
    )
    monkeypatch.setattr(service, "library", lambda version=None: bundle)
    state = await service.start(IntakeStart(source_message_id=TURN, session_id="default"))
    assert state["locale"] == "es-MX" and state["timezone"] == "America/Los_Angeles"
    while question := state["current_question"]:
        kind = question["id"]
        value = (
            "Synthetic event"
            if kind == "description"
            else {"concern": False}
            if kind == "product"
            else None
        )
        state = await service.answer(
            state["id"],
            IntakeAnswer(
                expected_revision=state["revision"],
                mutation_id=uuid4(),
                question_id=kind,
                state="answered" if value is not None else "unknown",
                value=value,
                wording=value if isinstance(value, str) else "",
                locale="es-MX",
            ),
        )
    assert state["can_review"] and not state["can_confirm"]
    assert sql("SELECT count(*) FROM symptom_reports;") == "0"
    assert sql("SELECT count(*) FROM chat_messages;") == "1"
    state = await service.preview(state["id"], state["revision"])
    assert "No sé" in state["preview"]["summary"]
    assert state["preview"]["answers"]["severity"]["value"] is None
    confirm = IntakeConfirm(
        expected_revision=state["revision"],
        confirmation_id=uuid4(),
        preview_hash=state["preview_hash"],
        consent=True,
    )
    first = await service.confirm(state["id"], confirm)
    second = await service.confirm(state["id"], confirm)
    assert first["confirmed_report_id"] == second["confirmed_report_id"]
    report = await service.report(first["confirmed_report_id"])
    assert report["severity"] is None and report["confirmed_by"] == PATIENT
    assert sql("SELECT count(*) FROM symptom_reports;") == "1"
    assert sql("SELECT count(*) FROM symptom_intake_audit WHERE action='confirm';") == "1"
    assert sql("SELECT count(*) FROM a2a_tasks;") == "0"


def test_browser_cannot_bypass_live_checks_to_read_stored_context(sql):
    v = ready(sql)
    saved = json.loads(sql(call_sql("confirm", confirmation(v))))
    prefix = f"SET ROLE authenticated; SELECT set_config('test.actor','{PATIENT}',false);"
    sql(prefix + f"SELECT preview FROM symptom_intakes WHERE id='{v['id']}';", succeeds=False)
    sql(
        prefix
        + f"SELECT confirmed_content FROM symptom_reports WHERE id='{saved['confirmed_report_id']}';",
        succeeds=False,
    )
    assert (
        json.loads(
            sql(
                prefix + f"SELECT to_jsonb(answers) FROM symptom_intakes WHERE id='{v['id']}';"
            ).splitlines()[-1]
        )["severity"]["value"]
        is None
    )
