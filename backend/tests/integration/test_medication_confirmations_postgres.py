"""Patient medication-confirmation storage contract in a disposable PostgreSQL 16 (094, MED-002).

A clinician asks one question about one imported medication; the patient answers once; the
answer is evidence for the clinician and changes no clinical record. Ownership, idempotency,
expiry on the database clock, immutability, grants and concurrency are checked against the
real migrations. Opt-in: ``CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER=1``. Synthetic data only.
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
    SECOND_PATIENT,
    TEAM,
    THIRD,
    finish,
    link,
    seed_people,
)
from tests.integration.test_care_team_records_postgres import document, fact

pytest_plugins = ["tests.integration.care_team_plan_harness"]

pytestmark = [
    pytest.mark.timeout(600),
    pytest.mark.skipif(
        os.environ.get("CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER") != "1",
        reason="explicit opt-in disposable Docker PostgreSQL contract check",
    ),
]

DENIED = "confirmation unavailable"
MED = '{"name":"Metformin","dosage":"500 mg","frequency":"twice daily"}'


def world(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)


def med_fact(sql, *, doc=None, patient=PATIENT, kind="medication", team=TEAM) -> str:
    doc = doc or document(sql, by=CLINICIAN, role="clinician", team=team, patient=patient)
    return fact(sql, doc, kind=kind, patient=patient, value=MED)


def q(value) -> str:
    return "NULL" if value is None else "'" + str(value).replace("'", "''") + "'"


def create_sql(
    fid,
    *,
    actor=CLINICIAN,
    patient=PATIENT,
    team=TEAM,
    request=None,
    subject="imported",
    medication=None,
    name="Metformin",
    dosage="500 mg",
    frequency="twice daily",
    ttl=14,
) -> str:
    request = request or uuid4()
    return (
        f"SELECT public.create_medication_confirmation('{actor}','{patient}','{team}',"
        f"'{request}','{fid}','{subject}',{q(medication)},{q(name)},{q(dosage)},"
        f"{q(frequency)},{ttl});"
    )


def create(sql, fid, **kw):
    return json.loads(sql(create_sql(fid, **kw)).splitlines()[-1])


def answer_sql(request, answer, note=None, patient=PATIENT) -> str:
    return f"SELECT public.answer_medication_confirmation('{patient}','{request}',{q(answer)},{q(note)});"


def answer(sql, request, value, note=None, patient=PATIENT):
    return json.loads(sql(answer_sql(request, value, note, patient)).splitlines()[-1])


def fact_list(sql, fid, actor=CLINICIAN, patient=PATIENT):
    out = sql(f"SELECT public.list_fact_medication_confirmations('{actor}','{patient}','{fid}');")
    return json.loads(out.splitlines()[-1])


def fingerprint(sql) -> str:
    return sql("""SELECT md5(
      coalesce((SELECT jsonb_agg(to_jsonb(m) ORDER BY m.id) FROM medications m)::text,'')
      || coalesce((SELECT jsonb_agg(to_jsonb(f) ORDER BY f.id) FROM clinical_facts f)::text,'')
      || coalesce((SELECT jsonb_agg(to_jsonb(e) ORDER BY e.id)
          FROM clinical_fact_reconciliation_events e)::text,''));""")


def test_a_clinician_asks_and_the_request_carries_only_the_question(sql):
    world(sql)
    fid = med_fact(sql)

    made = create(sql, fid)

    assert made["status"] == "open" and made["replayed"] is False
    assert (made["medication_name"], made["dosage"], made["frequency"]) == (
        "Metformin",
        "500 mg",
        "twice daily",
    )
    assert made["care_team_id"] == TEAM and made["requested_by"] == CLINICIAN
    assert made["clinician_name"] == "Elena Park" and made["clinic_name"] == "Cedar Grove"
    assert made["answer"] is None
    assert (
        sql("SELECT count(*) FROM medication_confirmation_events WHERE event_type='requested'")
        == "1"
    )


def test_a_repeated_request_id_and_a_second_ask_return_the_open_request(sql):
    world(sql)
    fid = med_fact(sql)
    first = create(sql, fid)

    same_id = create(sql, fid, request=first["id"])
    other_id = create(sql, fid)

    assert same_id["id"] == other_id["id"] == first["id"]
    assert same_id["replayed"] is True and other_id["replayed"] is True
    assert sql("SELECT count(*) FROM medication_confirmation_requests") == "1"
    assert sql("SELECT count(*) FROM medication_confirmation_events") == "1"


def test_only_the_asking_teams_clinician_can_ask_or_read(sql):
    world(sql)
    fid = med_fact(sql)
    # A clinician of the other team, an unlinked clinician and a wrong team id are all refused.
    assert DENIED in sql(create_sql(fid, actor=OTHER, team=OTHER_TEAM), succeeds=False)
    assert DENIED in sql(create_sql(fid, actor=THIRD), succeeds=False)
    assert DENIED in sql(create_sql(fid, actor=CLINICIAN, team=OTHER_TEAM), succeeds=False)
    created = create(sql, fid)
    assert DENIED in sql(
        f"SELECT public.list_fact_medication_confirmations('{THIRD}','{PATIENT}','{fid}');",
        succeeds=False,
    )
    assert fact_list(sql, fid)[0]["id"] == created["id"]
    assert sql("SELECT count(*) FROM medication_confirmation_requests") == "1"


def test_a_fact_from_another_teams_document_or_patient_or_type_is_refused(sql):
    world(sql)
    hidden = med_fact(sql, doc=document(sql, by=OTHER, role="clinician", team=OTHER_TEAM))
    assert DENIED in sql(create_sql(hidden), succeeds=False)
    assert DENIED in sql(
        f"SELECT public.list_fact_medication_confirmations('{CLINICIAN}','{PATIENT}','{hidden}');",
        succeeds=False,
    )
    allergy = med_fact(sql, kind="allergy")
    assert DENIED in sql(create_sql(allergy), succeeds=False)
    # A fact of another patient never matches the asked-about patient.
    second_team = "00000000-0000-0000-0000-000000000031"
    link(sql, second_team, CLINICIAN, CLINIC, SECOND_PATIENT)
    elsewhere = med_fact(sql, patient=SECOND_PATIENT, team=second_team)
    assert DENIED in sql(create_sql(elsewhere), succeeds=False)
    assert sql("SELECT count(*) FROM medication_confirmation_requests") == "0"


def test_an_approved_question_must_name_this_patients_medication(sql):
    world(sql)
    fid = med_fact(sql)
    mine, theirs = str(uuid4()), str(uuid4())
    sql(f"""INSERT INTO medications(id,patient_id,name,dosage,frequency) VALUES
      ('{mine}','{PATIENT}','Metformin ER','1000 mg','once daily'),
      ('{theirs}','{SECOND_PATIENT}','Other','5 mg','daily');""")

    assert "invalid confirmation request" in sql(
        create_sql(fid, subject="approved", medication=theirs), succeeds=False
    )
    assert "invalid confirmation request" in sql(
        create_sql(fid, subject="approved", medication=None), succeeds=False
    )
    made = create(sql, fid, subject="approved", medication=mine, name="Metformin ER")
    assert made["subject_kind"] == "approved"


def test_the_patient_answers_once_and_the_clinician_reads_it_as_evidence(sql):
    world(sql)
    fid = med_fact(sql)
    made = create(sql, fid)
    before = fingerprint(sql)

    seen = json.loads(
        sql(f"SELECT public.list_patient_medication_confirmations('{PATIENT}');").splitlines()[-1]
    )
    assert [row["id"] for row in seen] == [made["id"]]
    assert "requested_by" not in seen[0] and "patient_id" not in seen[0]

    done = answer(sql, made["id"], "changed", "  Now 250 mg at night ")
    assert done["status"] == "answered" and done["answer"] == "changed"
    assert done["answer_note"] == "Now 250 mg at night" and done["replayed"] is False

    evidence = fact_list(sql, fid)[0]
    assert evidence["status"] == "answered" and evidence["answer_note"] == "Now 250 mg at night"
    # Testimony only: no medication, fact, reconciliation event or plan changed.
    assert fingerprint(sql) == before
    assert (
        sql("SELECT count(*) FROM medication_confirmation_events WHERE event_type='answered'")
        == "1"
    )
    assert (
        sql("SELECT answer FROM medication_confirmation_events WHERE event_type='answered'")
        == "changed"
    )


def test_the_same_answer_again_is_a_replay_and_a_different_one_is_a_conflict(sql):
    world(sql)
    made = create(sql, med_fact(sql))
    answer(sql, made["id"], "yes")

    again = answer(sql, made["id"], "yes")
    assert again["replayed"] is True and again["answer"] == "yes"
    assert "MEDCONFIRM_ALREADY_ANSWERED" in sql(answer_sql(made["id"], "stopped"), succeeds=False)
    assert sql("SELECT answer FROM medication_confirmation_requests") == "yes"
    assert (
        sql("SELECT count(*) FROM medication_confirmation_events WHERE event_type='answered'")
        == "1"
    )


def test_answers_are_validated(sql):
    world(sql)
    made = create(sql, med_fact(sql))
    assert "invalid confirmation answer" in sql(answer_sql(made["id"], "maybe"), succeeds=False)
    assert "invalid confirmation answer" in sql(answer_sql(made["id"], "changed"), succeeds=False)
    assert "invalid confirmation answer" in sql(
        answer_sql(made["id"], "changed", "  "), succeeds=False
    )
    assert "invalid confirmation answer" in sql(
        answer_sql(made["id"], "changed", "x" * 501), succeeds=False
    )
    assert sql("SELECT status FROM medication_confirmation_requests") == "open"
    assert answer(sql, made["id"], "unsure")["answer"] == "unsure"


def test_only_the_asked_patient_can_answer_and_only_while_the_link_is_active(sql):
    world(sql)
    made = create(sql, med_fact(sql))
    assert DENIED in sql(answer_sql(made["id"], "yes", patient=SECOND_PATIENT), succeeds=False)
    assert DENIED in sql(answer_sql(made["id"], "yes", patient=CLINICIAN), succeeds=False)
    assert DENIED in sql(answer_sql(uuid4(), "yes"), succeeds=False)
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{TEAM}';")
    assert DENIED in sql(answer_sql(made["id"], "yes"), succeeds=False)
    listed = sql(f"SELECT public.list_patient_medication_confirmations('{PATIENT}');")
    assert json.loads(listed.splitlines()[-1]) == []
    assert sql("SELECT status FROM medication_confirmation_requests") == "open"


def test_an_unanswered_request_expires_on_the_database_clock_and_frees_the_slot(sql):
    world(sql)
    fid = med_fact(sql)
    made = create(sql, fid)
    sql(f"""SET session_replication_role = replica;
      UPDATE medication_confirmation_requests
         SET created_at = clock_timestamp() - interval '20 days',
             expires_at = clock_timestamp() - interval '6 days' WHERE id='{made["id"]}';""")

    assert fact_list(sql, fid)[0]["status"] == "expired"
    listed = sql(f"SELECT public.list_patient_medication_confirmations('{PATIENT}');")
    assert json.loads(listed.splitlines()[-1]) == []
    assert "MEDCONFIRM_EXPIRED" in sql(answer_sql(made["id"], "yes"), succeeds=False)

    fresh = create(sql, fid)
    assert fresh["id"] != made["id"] and fresh["status"] == "open" and fresh["replayed"] is False
    assert (
        sql(f"SELECT status FROM medication_confirmation_requests WHERE id='{made['id']}'")
        == "expired"
    )
    assert answer(sql, fresh["id"], "yes")["status"] == "answered"


def test_an_answered_question_leaves_the_patients_list_after_a_week(sql):
    world(sql)
    made = create(sql, med_fact(sql))
    answer(sql, made["id"], "yes")

    def listed():
        out = sql(f"SELECT public.list_patient_medication_confirmations('{PATIENT}');")
        return [row["id"] for row in json.loads(out.splitlines()[-1])]

    assert listed() == [made["id"]]
    sql(f"""SET session_replication_role = replica;
      UPDATE medication_confirmation_requests SET answered_at = clock_timestamp() - interval '8 days'
       WHERE id='{made["id"]}';""")
    assert listed() == []


def test_the_open_question_limit_is_ten_per_patient(sql):
    world(sql)
    for _ in range(10):
        create(sql, med_fact(sql))
    assert "too many open confirmation requests" in sql(create_sql(med_fact(sql)), succeeds=False)
    assert sql("SELECT count(*) FROM medication_confirmation_requests") == "10"


def test_written_records_cannot_be_rewritten_or_erased_through_sql(sql):
    world(sql)
    made = create(sql, med_fact(sql))
    answer(sql, made["id"], "yes")
    for statement in (
        "UPDATE medication_confirmation_requests SET answer='stopped'",
        "UPDATE medication_confirmation_requests SET medication_name='Other'",
        "UPDATE medication_confirmation_requests SET status='open', answer=NULL, answered_at=NULL",
        "DELETE FROM medication_confirmation_events",
        "UPDATE medication_confirmation_events SET answer='no'".replace("'no'", "'yes'"),
        "TRUNCATE medication_confirmation_events",
    ):
        assert "immutable" in sql(statement, succeeds=False), statement
    assert sql("SELECT answer FROM medication_confirmation_requests") == "yes"


def test_erasing_the_patient_removes_their_requests_but_not_the_audit_trail(sql):
    world(sql)
    fid = str(uuid4())
    sql(f"""INSERT INTO clinical_facts(id,patient_id,fact_type,subject_type,value,review_state)
      VALUES('{fid}','{PATIENT}','medication','patient','{MED}','pending_review');""")
    made = create(sql, fid)
    answer(sql, made["id"], "yes")
    sql(f"DELETE FROM patients WHERE id='{PATIENT}';")
    assert sql("SELECT count(*) FROM medication_confirmation_requests") == "0"
    assert sql("SELECT count(*) FROM medication_confirmation_events") == "2"


def test_browser_roles_reach_nothing(sql):
    world(sql)
    made = create(sql, med_fact(sql))
    for role in ("anon", "authenticated"):
        assert "permission denied" in sql(
            f"SET ROLE {role}; SELECT * FROM medication_confirmation_requests;", succeeds=False
        )
        assert "permission denied" in sql(
            f"SET ROLE {role}; SELECT * FROM medication_confirmation_events;", succeeds=False
        )
        assert "permission denied" in sql(
            f"SET ROLE {role}; " + answer_sql(made["id"], "yes"), succeeds=False
        )
        assert "permission denied" in sql(
            f"SET ROLE {role}; " + create_sql(uuid4()), succeeds=False
        )
        assert "permission denied" in sql(
            f"SET ROLE {role}; SELECT public.list_patient_medication_confirmations('{PATIENT}');",
            succeeds=False,
        )
    # The backend's own role can use the functions.
    assert answer_ok_as_service(sql, made["id"])


def answer_ok_as_service(sql, request) -> bool:
    out = sql("SET ROLE service_role; " + answer_sql(request, "yes"))
    return json.loads(out.splitlines()[-1])["answer"] == "yes"


def test_concurrent_answers_have_exactly_one_winner(sql):
    world(sql)
    made = create(sql, med_fact(sql))
    first = sql.start(answer_sql(made["id"], "yes"), "first")
    second = sql.start(answer_sql(made["id"], "stopped"), "second")
    results = [finish(first), finish(second)]

    codes = sorted(code for code, _out, _err in results)
    assert codes == [0, 3], results
    loser = next(err for code, _out, err in results if code != 0)
    assert "MEDCONFIRM_ALREADY_ANSWERED" in loser
    assert (
        sql("SELECT count(*) FROM medication_confirmation_events WHERE event_type='answered'")
        == "1"
    )


def test_concurrent_asks_for_one_fact_create_one_request(sql):
    world(sql)
    fid = med_fact(sql)
    first = sql.start(create_sql(fid), "first")
    second = sql.start(create_sql(fid), "second")
    results = [finish(first), finish(second)]

    assert [code for code, _out, _err in results] == [0, 0], results
    assert sql("SELECT count(*) FROM medication_confirmation_requests") == "1"
    ids = {json.loads(out.splitlines()[-1])["id"] for _code, out, _err in results}
    assert len(ids) == 1
