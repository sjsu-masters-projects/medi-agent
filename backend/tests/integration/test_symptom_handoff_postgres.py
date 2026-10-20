"""Applied 071 symptom handoff on real disposable SQL; no shared environment writes."""

# ruff: noqa: F811 -- imported pytest fixtures intentionally share fixture argument names

import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.integration.test_symptom_intake_postgres import (
    CLINICIAN,
    MIGRATIONS,
    PATIENT,
    TURN,
    call_sql,
    confirmation,
    postgres,  # noqa: F401 -- shared disposable PostgreSQL fixtures
    ready,
    sql,  # noqa: F401 -- shared disposable PostgreSQL fixture
    start,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("SYMPTOM_INTAKE_TEST_POSTGRES") != "1",
    reason="local SQL opt-in required",
)


@pytest.fixture
def handoff(sql):
    # Real clinic-membership migration, with an existing synthetic clinic/assignment.
    sql(
        f"INSERT INTO clinics(id,display_name,canonical_name) VALUES('{uuid4()}','Intake QA','intake qa');"
    )
    sql(
        "UPDATE clinicians SET clinic_id=(SELECT id FROM clinics WHERE canonical_name='intake qa');"
    )
    sql((MIGRATIONS / "065_clinic_memberships.sql").read_text())
    sql((MIGRATIONS / "042_auditable_adr_assessments.sql").read_text())
    sql((MIGRATIONS / "071_confirmed_symptom_handoff.sql").read_text())
    return sql


def answer(sql, row, key, value, mode="typed"):
    return json.loads(
        sql(
            call_sql(
                "answer",
                {
                    "intake_id": row["id"],
                    "expected_revision": row["revision"],
                    "mutation_id": str(uuid4()),
                    "answer": {
                        "question_id": key,
                        "state": "answered",
                        "value": value,
                        "locale": "en-US",
                        "wording": str(value),
                        "input_mode": mode,
                    },
                },
            )
        )
    )


def with_product(sql, name):
    v = ready(sql)
    preview = v["preview"]
    v = answer(sql, v, "product", {"concern": True, "name": name})
    v = answer(sql, v, "concomitant", "Patient reports an OTC supplement; dose unknown.")
    preview["answers"] = v["answers"]
    preview["context"] = json.loads(
        sql(
            f"SELECT private.symptom_context('{PATIENT}','{json.dumps(v['answers']).replace(chr(39), chr(39) * 2)}'::jsonb);"
        )
    )
    return json.loads(
        sql(
            call_sql(
                "preview",
                {"intake_id": v["id"], "expected_revision": v["revision"], "preview": preview},
            )
        )
    )


def test_confirmation_queues_once_maps_known_product_and_notifies(handoff):
    db = handoff
    medication = str(uuid4())
    db(
        f"INSERT INTO medications(id,patient_id,name,dosage,frequency) VALUES('{medication}','{PATIENT}','Test medicine','test dose','daily');"
    )
    v = with_product(db, "test medicine")
    first = json.loads(db(call_sql("confirm", confirmation(v))))
    again = json.loads(db(call_sql("confirm", confirmation(v))))
    assert first["confirmed_report_id"] == again["confirmed_report_id"]
    report = json.loads(
        db(f"SELECT to_jsonb(r) FROM symptom_reports r WHERE id='{first['confirmed_report_id']}';")
    )
    assert report["related_medication_id"] == medication and report["flagged_for_adr"]
    assert db("SELECT count(*) FROM a2a_tasks;") == "1"
    assert db("SELECT count(*) FROM clinician_messages;") == "1"
    assert db("SELECT count(*) FROM symptom_intake_audit WHERE action='review_handoff';") == "1"
    payload = json.loads(db("SELECT input_payload FROM a2a_tasks;"))
    assert "context" not in payload["symptom_report"]["confirmed_content"]
    assert payload["naranjo_answers"] == {} and payload["adr_evidence"] == []
    assert db("SELECT status FROM a2a_tasks;") == "retrying"
    assert db("SELECT count(*) FROM adr_assessments;") == "0"  # queued, not a clinical verdict


def test_unlisted_product_preserves_name_without_creating_medication(handoff):
    db = handoff
    v = with_product(db, "Patient-named OTC product")
    saved = json.loads(db(call_sql("confirm", confirmation(v))))
    row = json.loads(
        db(f"SELECT to_jsonb(r) FROM symptom_reports r WHERE id='{saved['confirmed_report_id']}';")
    )
    assert row["related_medication_name"] == "Patient-named OTC product"
    assert row["related_medication_id"] is None and row["flagged_for_adr"] is False
    assert db("SELECT count(*) FROM medications;") == "0"
    assert db("SELECT count(*) FROM clinician_messages;") == "1"


def test_urgent_answer_alert_survives_abandonment_and_does_not_suppress_emergency(handoff):
    db = handoff
    v = start(db)
    v = answer(db, v, "severity", 10, "voice")
    assert v["review_requested"] and v["answers"]["severity"]["source_type"] == "patient_voice"
    assert db("SELECT count(*) FROM symptom_reports;") == "0"
    db(
        call_sql(
            "cancel",
            {"intake_id": v["id"], "expected_revision": v["revision"], "mutation_id": str(uuid4())},
        )
    )
    db("SELECT deliver_symptom_intake_safety_alerts(25);")
    assert db("SELECT count(*) FROM clinician_messages;") == "1"
    current = json.loads(db(call_sql("read", {"intake_id": v["id"]})))
    db(
        call_sql(
            "interrupt",
            {
                "intake_id": v["id"],
                "expected_revision": current["revision"],
                "mutation_id": str(uuid4()),
                "safety": {
                    "safety_rule": "emergency_symptom_keyword",
                    "rule_version": "triage-floor/1",
                    "response_text": "Synthetic reviewed fixture only",
                },
            },
        )
    )
    db("SELECT deliver_symptom_intake_safety_alerts(25);")
    assert db("SELECT count(*) FROM clinician_messages;") == "2"
    assert (
        db("SELECT count(*) FROM symptom_intake_safety_alerts WHERE delivery_state='delivered';")
        == "2"
    )
    assert db("SELECT count(*) FROM symptom_reports;") == "0"


def test_handoff_failure_rolls_back_confirmation_and_retry_recovers(handoff):
    db = handoff
    v = ready(db)
    request = confirmation(v)
    db("""CREATE FUNCTION fail_notice() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'synthetic notice outage'; END;$$;
        CREATE TRIGGER fail_notice BEFORE INSERT ON clinician_messages FOR EACH ROW EXECUTE FUNCTION fail_notice();""")
    db(call_sql("confirm", request), succeeds=False)
    assert db("SELECT count(*) FROM symptom_reports;") == "0"
    assert db("SELECT count(*) FROM a2a_tasks;") == "0"
    db("DROP TRIGGER fail_notice ON clinician_messages;")
    db(call_sql("confirm", request))
    assert db("SELECT count(*) FROM symptom_reports;") == "1"
    assert db("SELECT count(*) FROM a2a_tasks;") == "1"


def test_inactive_assignment_has_no_notice_and_cannot_read_report(handoff):
    db = handoff
    v = ready(db)
    db("UPDATE care_teams SET status='inactive';")
    db(call_sql("confirm", confirmation(v)))
    assert db("SELECT count(*) FROM clinician_messages;") == "0"
    db("GRANT SELECT ON care_teams,clinicians TO authenticated;")
    assert (
        db(
            f"SET ROLE authenticated; SELECT set_config('test.actor','{CLINICIAN}',false); SELECT count(*) FROM symptom_reports;"
        ).splitlines()[-1]
        == "0"
    )
    db(
        f"SET ROLE authenticated; SELECT symptom_intake_operation('{PATIENT}','read','{{}}');",
        succeeds=False,
    )


def test_new_draft_uses_source_language_instead_of_profile(handoff):
    db = handoff
    db(f"UPDATE patients SET preferred_language='en-US' WHERE id='{PATIENT}';")
    db(
        "SELECT set_symptom_question_eligibility('test-language',repeat('b',64),'approved',"
        + '\'{"reference":"synthetic fixture only","reviewer_identity":"fixture","reviewer_role":"test","date":"2026-10-17"}\');'
    )
    db(
        f"INSERT INTO chat_messages(id,patient_id,role,content,language,session_id) VALUES('{TURN}','{PATIENT}','user','Me duele la cabeza','es-MX','default');"
    )
    row = json.loads(
        db(
            call_sql(
                "start",
                {
                    "source_message_id": TURN,
                    "session_id": "default",
                    "library_version": "test-language",
                    "library_hash": "b" * 64,
                },
            )
        )
    )
    assert row["locale"] == "es-MX"


@pytest.mark.asyncio
async def test_queued_canonical_report_creates_adr_draft_and_retry_preserves_review(handoff):
    """Real worker + SQL via a local transport shim; no hosted PostgREST claim."""
    from app.services.a2a_task_service import A2ATaskService

    db = handoff
    medication = str(uuid4())
    db(
        f"INSERT INTO medications(id,patient_id,name,dosage,frequency) VALUES('{medication}','{PATIENT}','Test medicine','test dose','daily');"
    )
    v = with_product(db, "Test medicine")
    db(call_sql("confirm", confirmation(v)))
    task_id = db("SELECT id FROM a2a_tasks;")

    def literal(value):
        return "'" + str(value).replace("'", "''") + "'"

    class Query:
        def __init__(self, name):
            assert name in {"a2a_tasks", "adr_assessments"}
            self.name, self.filters, self.row = name, [], None

        def select(self, fields):
            assert fields == "*"
            return self

        def eq(self, key, value):
            assert key in {"id", "patient_id", "symptom_report_id", "status"}
            self.filters.append(f"{key}={literal(value)}")
            return self

        def limit(self, count):
            assert count == 1
            return self

        def update(self, row):
            assert self.name == "a2a_tasks"
            self.row, self.operation = row, "update"
            return self

        def insert(self, row):
            assert self.name == "adr_assessments"
            self.row, self.operation = row, "insert"
            return self

        def execute(self):
            if self.row is None:
                statement = f"SELECT * FROM {self.name} WHERE {' AND '.join(self.filters)}"
                result = db(f"SELECT coalesce(jsonb_agg(to_jsonb(t)),'[]') FROM ({statement}) t;")
            else:
                assert all(key.replace("_", "").isalpha() for key in self.row)
                columns = ",".join(self.row)
                values = f"SELECT {columns} FROM jsonb_populate_record(NULL::{self.name},{literal(json.dumps(self.row))}::jsonb)"
                if self.operation == "insert":
                    statement = f"INSERT INTO {self.name} ({columns}) {values} RETURNING *"
                else:
                    statement = f"UPDATE {self.name} SET ({columns})=({values}) WHERE {' AND '.join(self.filters)} RETURNING *"
                result = db(
                    f"WITH changed AS ({statement}) SELECT coalesce(jsonb_agg(to_jsonb(t)),'[]') FROM changed t;"
                )
            return SimpleNamespace(data=json.loads(result))

    service = A2ATaskService(SimpleNamespace(table=Query))
    result = await service.retry_task(task_id)
    assert result["status"] == "completed", result.get("error_message")
    assert result["output_payload"]["adr_assessment_id"]
    assessment = json.loads(db("SELECT to_jsonb(a) FROM adr_assessments a;"))
    assert assessment["suspect_medication_id"] == medication
    assert assessment["status"] == "draft" and assessment["naranjo_answers"] == {}
    db(f"UPDATE adr_assessments SET status='reviewed',reviewed_by='{CLINICIAN}';")
    # Requeue after a failed completion write, without resetting the reviewed assessment.
    db(
        f"UPDATE a2a_tasks SET status='retrying',completed_at=NULL,next_retry_at=clock_timestamp() WHERE id='{task_id}';"
    )
    result = await service.retry_task(task_id)
    assert result["status"] == "completed"
    assert db("SELECT count(*) FROM adr_assessments;") == "1"
    assert (
        db("SELECT status::text||':'||reviewed_by::text FROM adr_assessments;")
        == f"reviewed:{CLINICIAN}"
    )


def test_readiness_is_exact_and_not_browser_callable(handoff):
    db = handoff
    start(db)
    approval = {
        "reference": "synthetic test only",
        "reviewer_identity": "fixture",
        "reviewer_role": "test",
        "date": "2026-10-12",
    }
    args = "'synthetic-test-only',repeat('a',64),'" + json.dumps(approval) + "'::jsonb"
    checks = json.loads(db(f"SET ROLE service_role; SELECT symptom_intake_readiness({args});"))
    assert all(checks.values())
    wrong = json.loads(
        db(f"SELECT symptom_intake_readiness({args.replace("repeat('a',64)", "repeat('b',64)")});")
    )
    assert wrong["eligibility_matches"] is False
    db(f"SET ROLE authenticated; SELECT symptom_intake_readiness({args});", succeeds=False)
    db(f"SET ROLE anon; SELECT symptom_intake_readiness({args});", succeeds=False)
