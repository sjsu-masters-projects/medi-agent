"""Every answerable Naranjo question has a place to be answered (PV-001-D, migration 100).

Patients may be asked the two new retrospective questions; an assigned clinician on the owning
team records the five clinical ones with evidence and audit; a patient answer and a clinician
answer saved at the same time cannot overwrite each other. Runs on the full ledger. Opt-in:
``CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER=1``. Synthetic data only.
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
    link,
    seed_people,
)

pytest_plugins = ["tests.integration.care_team_plan_harness"]

pytestmark = [
    pytest.mark.timeout(600),
    pytest.mark.skipif(
        os.environ.get("CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER") != "1",
        reason="explicit opt-in disposable Docker PostgreSQL contract check",
    ),
]

MEDICATION = "00000000-0000-0000-0000-0000000000e2"
ALL_PATIENT = [
    "event_after_drug",
    "improved_on_dechallenge",
    "reappeared_on_rechallenge",
    "dose_response",
    "similar_previous_reaction",
]


def two_teams(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)


def assessment(sql, *, answers=None, evidence=None, status="draft") -> str:
    key, symptom = str(uuid4()), str(uuid4())
    sql(f"""
      SET session_replication_role = replica;
      INSERT INTO medications(id,patient_id,name,dosage,frequency,route)
        VALUES('{MEDICATION}','{PATIENT}','M','1','daily','oral') ON CONFLICT DO NOTHING;
      INSERT INTO symptom_reports(id,patient_id,symptom,severity) VALUES('{symptom}','{PATIENT}','nausea',3);
      INSERT INTO adr_assessments(id,patient_id,symptom_report_id,suspect_medication_id,
          suspect_medication_name,naranjo_score,causality,status,naranjo_answers,evidence,naranjo_assessment)
        VALUES('{key}','{PATIENT}','{symptom}','{MEDICATION}','M',0,'Doubtful','{status}',
          '{json.dumps(answers or {})}'::jsonb,'{json.dumps(evidence or [])}'::jsonb,
          '{{"missing_questions":{json.dumps(ALL_PATIENT)}}}'::jsonb);""")
    return key


def record(key, actor, answers, merged, *, score=2, causality="Possible", team=None):
    team_arg = f",p_care_team_id=>'{team}'" if team else ""
    return (
        "SET ROLE service_role; SELECT row_to_json(r) FROM public.record_adr_clinician_answers("
        f"p_assessment_id=>'{key}',p_actor_id=>'{actor}',"
        f"p_answers=>$a${json.dumps(answers)}$a$::jsonb,"
        f"p_naranjo_answers=>$m${json.dumps(merged)}$m$::jsonb,"
        f"p_naranjo_assessment=>'{{\"score\":{score}}}'::jsonb,"
        f"p_score=>{score}::smallint,p_causality=>'{causality}'{team_arg}) r;"
    )


ALT_NO = {"question": "alternative_causes", "answer": "no", "basis": "Chart reviewed."}


def row(sql, statement) -> dict:
    return json.loads(sql(statement).splitlines()[-1])


def test_a_request_may_carry_all_five_patient_questions(sql):
    two_teams(sql)
    key = assessment(sql)
    sql(
        "SET ROLE service_role; SELECT 1 FROM public.review_adr_assessment("
        f"p_assessment_id=>'{key}',p_actor_id=>'{CLINICIAN}',p_action=>'request_information',"
        f"p_note=>'When did it start?',p_requested_information=>'{json.dumps(ALL_PATIENT)}'::jsonb);"
    )
    assert (
        json.loads(
            sql(
                f"SELECT requested_information FROM adr_information_requests WHERE adr_assessment_id='{key}'"
            )
        )
        == ALL_PATIENT
    )


def test_a_clinical_question_still_cannot_be_asked_of_a_patient(sql):
    two_teams(sql)
    key = assessment(sql)
    error = sql(
        "SET ROLE service_role; SELECT 1 FROM public.review_adr_assessment("
        f"p_assessment_id=>'{key}',p_actor_id=>'{CLINICIAN}',p_action=>'request_information',"
        "p_note=>'x',p_requested_information=>'[\"objective_evidence\"]'::jsonb);",
        succeeds=False,
    )
    assert "patient-answerable" in error
    insert = sql(
        f"""INSERT INTO adr_information_requests(adr_assessment_id,patient_id,requested_by,
          requested_information,patient_message,baseline_naranjo_score,baseline_causality)
          VALUES('{key}','{PATIENT}','{CLINICIAN}','["alternative_causes"]','x',0,'Doubtful');""",
        succeeds=False,
    )
    assert "adr_information_requests_patient_safe_questions" in insert


def test_clinician_answers_are_saved_with_evidence_and_one_audit_event(sql):
    two_teams(sql)
    key = assessment(sql, answers={"dose_response": "yes"})

    saved = row(
        sql,
        record(
            key, CLINICIAN, [ALT_NO], {"dose_response": "yes", "alternative_causes": "no"}, score=3
        ),
    )

    assert saved["naranjo_answers"] == {"dose_response": "yes", "alternative_causes": "no"}
    assert saved["naranjo_score"] == 3 and saved["status"] == "draft"
    entry = saved["evidence"][-1]
    assert entry["source"] == "clinician_entry" and entry["evidence"] == "Chart reviewed."
    assert entry["recorded_by"] == CLINICIAN and entry["care_team_id"] == TEAM
    # Recording answers is not a review: the case stays open and untaken.
    assert saved["reviewed_by"] is None and saved["reviewed_by_care_team_id"] is None
    audit = json.loads(
        sql(f"""SELECT json_agg(json_build_object('t',event_type,'a',actor_id,'d',event_data))
          FROM adr_assessment_audit_events WHERE adr_assessment_id='{key}'""")
    )
    assert len(audit) == 1 and audit[0]["t"] == "clinician_naranjo_answers_recorded"
    assert audit[0]["a"] == CLINICIAN
    data = audit[0]["d"]
    assert data["questions"] == ["alternative_causes"] and data["answers"] == {
        "alternative_causes": "no"
    }
    assert data["previous_answers"] == {} and data["previous_naranjo_score"] == 0
    assert data["naranjo_score"] == 3 and "Chart reviewed." not in json.dumps(data)


def test_a_recorded_answer_can_be_replaced_and_both_entries_are_kept(sql):
    two_teams(sql)
    key = assessment(sql)
    sql(record(key, CLINICIAN, [ALT_NO], {"alternative_causes": "no"}))
    changed = {"question": "alternative_causes", "answer": "yes", "basis": "New lab finding."}

    saved = row(
        sql,
        record(
            key, CLINICIAN, [changed], {"alternative_causes": "yes"}, score=-1, causality="Doubtful"
        ),
    )

    assert saved["naranjo_answers"] == {"alternative_causes": "yes"}
    assert [e["answer"] for e in saved["evidence"]] == ["no", "yes"]
    last = json.loads(
        sql(f"""SELECT event_data FROM adr_assessment_audit_events WHERE adr_assessment_id='{key}'
          ORDER BY created_at DESC, id DESC LIMIT 1""")
    )
    assert last["previous_answers"] == {"alternative_causes": "no"}


@pytest.mark.parametrize(
    "answers",
    [
        [{"question": "dose_response", "answer": "yes", "basis": "Patient question."}],
        [{"question": "objective_evidence", "answer": "yes"}],
        [{"question": "objective_evidence", "answer": "maybe", "basis": "x"}],
        [ALT_NO, ALT_NO],
        [],
    ],
)
def test_invalid_clinician_payloads_change_nothing(sql, answers):
    two_teams(sql)
    key = assessment(sql)
    merged = {a["question"]: a["answer"] for a in answers}

    error = sql(record(key, CLINICIAN, answers, merged), succeeds=False)

    assert "clinician-answerable" in error or "Invalid clinician" in error
    assert (
        sql(f"SELECT naranjo_answers::text||evidence::text FROM adr_assessments WHERE id='{key}'")
        == "{}[]"
    )


def test_a_stale_payload_is_refused_with_40001(sql):
    two_teams(sql)
    key = assessment(sql, answers={"dose_response": "yes"})

    # Built before the patient's dose-response answer arrived: it would drop it.
    error = sql(record(key, CLINICIAN, [ALT_NO], {"alternative_causes": "no"}), succeeds=False)

    assert "changed" in error
    assert (
        sql(f"SELECT naranjo_answers::text FROM adr_assessments WHERE id='{key}'")
        == '{"dose_response": "yes"}'
    )


def test_unassigned_other_team_and_closed_cases_are_refused(sql):
    two_teams(sql)
    key = assessment(sql)
    assert "not assigned" in sql(
        record(key, THIRD, [ALT_NO], {"alternative_causes": "no"}), succeeds=False
    )
    # Once the first team took the case up, the second team cannot add answers.
    sql(
        "SET ROLE service_role; SELECT 1 FROM public.review_adr_assessment("
        f"p_assessment_id=>'{key}',p_actor_id=>'{CLINICIAN}',p_action=>'request_information',"
        "p_note=>'x',p_requested_information=>'[\"dose_response\"]'::jsonb);"
    )
    assert "unavailable" in sql(
        record(key, OTHER, [ALT_NO], {"alternative_causes": "no"}), succeeds=False
    )
    closed = assessment(sql, status="reviewed")
    sql(
        f"UPDATE adr_assessments SET reviewed_by='{CLINICIAN}', reviewed_by_care_team_id='{TEAM}' WHERE id='{closed}'"
    )
    assert "already been completed" in sql(
        record(closed, CLINICIAN, [ALT_NO], {"alternative_causes": "no"}), succeeds=False
    )


def test_browser_roles_cannot_record_answers(sql):
    signature = (
        "public.record_adr_clinician_answers(uuid, uuid, jsonb, jsonb, jsonb, smallint, text, uuid)"
    )
    assert (
        sql(
            f"SELECT has_function_privilege('anon','{signature}','EXECUTE')::text||"
            f"has_function_privilege('authenticated','{signature}','EXECUTE')::text||"
            f"has_function_privilege('service_role','{signature}','EXECUTE')::text"
        )
        == "falsefalsetrue"
    )


def _pending_request(sql, key, questions=("dose_response",)):
    sql(
        "SET ROLE service_role; SELECT 1 FROM public.review_adr_assessment("
        f"p_assessment_id=>'{key}',p_actor_id=>'{CLINICIAN}',p_action=>'request_information',"
        f"p_note=>'x',p_requested_information=>'{json.dumps(list(questions))}'::jsonb);"
    )
    return sql(
        f"SELECT id FROM adr_information_requests WHERE adr_assessment_id='{key}' AND status='pending'"
    )


def respond(request_id, answers, evidence, *, score=1):
    responses = [{"question": "dose_response", "answer": "yes", "evidence": "It changed."}]
    return f"""SET ROLE service_role; SELECT id FROM respond_to_adr_information_request('{request_id}','{PATIENT}',
      $r${json.dumps(responses)}$r$::jsonb,$n${json.dumps(answers)}$n$::jsonb,'{{"score":{score}}}'::jsonb,
      $e${json.dumps(evidence)}$e$::jsonb,{score}::smallint,'Possible');"""


PATIENT_ENTRY = {"question": "dose_response", "answer": "yes", "source": "patient_follow_up"}


def test_a_patient_answer_built_before_a_clinician_answer_is_refused(sql):
    two_teams(sql)
    key = assessment(sql)
    request_id = _pending_request(sql, key)
    # The clinician records an answer after the patient's backend read the assessment.
    sql(record(key, CLINICIAN, [ALT_NO], {"alternative_causes": "no"}))

    stale = sql(respond(request_id, {"dose_response": "yes"}, [PATIENT_ENTRY]), succeeds=False)

    assert "changed" in stale
    assert sql(f"SELECT status FROM adr_information_requests WHERE id='{request_id}'") == "pending"
    # Rebuilt on the current answers and evidence, the same answer is accepted.
    current = json.loads(sql(f"SELECT evidence FROM adr_assessments WHERE id='{key}'"))
    sql(
        respond(
            request_id,
            {"alternative_causes": "no", "dose_response": "yes"},
            [*current, PATIENT_ENTRY],
            score=3,
        )
    )
    assert json.loads(sql(f"SELECT naranjo_answers FROM adr_assessments WHERE id='{key}'")) == {
        "alternative_causes": "no",
        "dose_response": "yes",
    }


def test_patient_answers_to_the_new_questions_are_saved(sql):
    two_teams(sql)
    key = assessment(sql)
    request_id = _pending_request(
        sql, key, questions=("event_after_drug", "improved_on_dechallenge")
    )
    responses = [
        {"question": "event_after_drug", "answer": "yes", "evidence": "Two days after starting."},
        {"question": "improved_on_dechallenge", "answer": "do_not_know"},
    ]
    sql(f"""SET ROLE service_role; SELECT id FROM respond_to_adr_information_request('{request_id}','{PATIENT}',
      $r${json.dumps(responses)}$r$::jsonb,
      '{{"event_after_drug":"yes","improved_on_dechallenge":"do_not_know"}}'::jsonb,'{{"score":2}}'::jsonb,
      '[{{"question":"event_after_drug","answer":"yes","source":"patient_follow_up"}}]'::jsonb,2::smallint,'Possible');""")
    assert sql(f"SELECT status FROM adr_information_requests WHERE id='{request_id}'") == "answered"
    assert sql(f"SELECT naranjo_score FROM adr_assessments WHERE id='{key}'") == "2"
