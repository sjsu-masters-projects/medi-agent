"""Reviewed ADR work and MedWatch drafts always have an owner (migration 087).

The care team is written in the same transaction as the review or the draft; a clinician with
several links must name one; rows that predate ownership are assigned only when unambiguous,
and otherwise stay visible to nobody with a review item. Care-team work items reach the
notification centre of the team they are addressed to. Opt-in:
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
    THIRD_TEAM,
    finish,
    link,
    seed_people,
)
from tests.integration.test_care_team_notifications_postgres import centre, items

pytest_plugins = ["tests.integration.care_team_plan_harness"]

pytestmark = [
    pytest.mark.timeout(600),
    pytest.mark.skipif(
        os.environ.get("CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER") != "1",
        reason="explicit opt-in disposable Docker PostgreSQL contract check",
    ),
]

SYMPTOM = "00000000-0000-0000-0000-0000000000e1"
MEDICATION = "00000000-0000-0000-0000-0000000000e2"


def two_teams(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)


def assessment(sql, *, reviewed_by=None, team=None, status="draft", symptom=None) -> str:
    key = str(uuid4())
    symptom = symptom or str(uuid4())
    reviewed = f"'{reviewed_by}'" if reviewed_by else "NULL"
    owner = f"'{team}'" if team else "NULL"
    sql(f"""
      SET session_replication_role = replica;
      INSERT INTO medications(id,patient_id,name,dosage,frequency,route)
        VALUES('{MEDICATION}','{PATIENT}','M','1','daily','oral') ON CONFLICT DO NOTHING;
      INSERT INTO symptom_reports(id,patient_id,symptom,severity) VALUES('{symptom}','{PATIENT}','rash',3);
      INSERT INTO adr_assessments(id,patient_id,symptom_report_id,suspect_medication_id,
          suspect_medication_name,naranjo_score,causality,status,reviewed_by,reviewed_by_care_team_id,reviewed_at,
          naranjo_assessment)
        VALUES('{key}','{PATIENT}','{symptom}','{MEDICATION}','M',3,'Possible','{status}',{reviewed},{owner},
          CASE WHEN {reviewed} IS NULL THEN NULL ELSE now() END,'{{"missing_questions":["dose_response"]}}');""")
    return key


def review(assessment_id, actor, *, team=None, action="mark_reviewed", note="Reviewed"):
    team_arg = f",p_care_team_id=>'{team}'" if team else ""
    if action == "request_information":
        team_arg += ",p_requested_information=>'[\"dose_response\"]'::jsonb"
    return (
        "SET ROLE service_role; SELECT row_to_json(r) FROM public.review_adr_assessment("
        f"p_assessment_id=>'{assessment_id}',p_actor_id=>'{actor}',p_action=>'{action}',"
        f"p_note=>$n${note}$n${team_arg}) r;"
    )


def owner_of(sql, assessment_id) -> str:
    return sql(
        f"SELECT coalesce(reviewed_by_care_team_id::text,'-') FROM adr_assessments WHERE id='{assessment_id}'"
    )


def test_a_review_writes_the_owner_in_the_same_call(sql):
    two_teams(sql)
    key = assessment(sql)

    row = json.loads(sql(review(key, CLINICIAN)).splitlines()[-1])

    assert row["reviewed_by"] == CLINICIAN and row["reviewed_by_care_team_id"] == TEAM
    assert owner_of(sql, key) == TEAM


def test_a_clinician_with_two_links_must_name_the_team_and_nothing_changes_without(sql):
    seed_people(sql, second_clinic_for_clinician=True)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, CLINICIAN, OTHER_CLINIC)
    key = assessment(sql)

    error = sql(review(key, CLINICIAN), succeeds=False)

    assert "CARE_TEAM_REQUIRED" in error
    assert (
        sql(f"SELECT status||coalesce(reviewed_by::text,'-') FROM adr_assessments WHERE id='{key}'")
        == "draft-"
    )
    json.loads(sql(review(key, CLINICIAN, team=OTHER_TEAM)).splitlines()[-1])
    assert owner_of(sql, key) == OTHER_TEAM


def test_a_team_that_is_not_the_clinicians_is_refused(sql):
    two_teams(sql)
    key = assessment(sql)

    assert "not assigned" in sql(review(key, CLINICIAN, team=OTHER_TEAM), succeeds=False)
    assert "not assigned" in sql(review(key, THIRD), succeeds=False)
    assert owner_of(sql, key) == "-"


def test_once_a_team_took_it_up_the_other_team_cannot_continue_it(sql):
    two_teams(sql)
    key = assessment(sql)
    sql(review(key, CLINICIAN, action="request_information", note="Please describe"))

    error = sql(review(key, OTHER), succeeds=False)

    assert "unavailable" in error
    assert owner_of(sql, key) == TEAM


def test_a_review_or_draft_cannot_commit_without_an_owner_by_any_path(sql):
    two_teams(sql)
    key = assessment(sql)

    error = sql(
        f"UPDATE adr_assessments SET reviewed_by='{CLINICIAN}', reviewed_at=now(), last_review_action='mark_reviewed' WHERE id='{key}';",
        succeeds=False,
    )

    assert "needs its care team" in error
    assert sql(f"SELECT reviewed_by IS NULL FROM adr_assessments WHERE id='{key}'") == "t"
    error = sql(
        f"""INSERT INTO medwatch_drafts(adr_assessment_id,patient_id,form_data) VALUES('{key}','{PATIENT}','{{}}');""",
        succeeds=False,
    )
    assert "needs its care team" in error or "violates" in error


def test_the_ownerless_signatures_are_gone_from_the_data_api_schema(sql):
    assert (
        sql(
            "SELECT to_regprocedure('public.review_adr_assessment(uuid,uuid,text,text,jsonb)') IS NULL"
        )
        == "t"
    )
    assert (
        sql(
            "SELECT to_regprocedure('public.create_medwatch_draft(uuid,uuid,jsonb,jsonb,text,uuid)') IS NULL"
        )
        == "t"
    )
    for role in ("anon", "authenticated"):
        error = sql(
            f"SET ROLE {role}; SELECT * FROM public.review_adr_assessment('{uuid4()}','{CLINICIAN}','dismiss');",
            succeeds=False,
        )
        assert "permission denied" in error


def medwatch(assessment_id, actor, *, team=None):
    form = json.dumps({"form_version": "fda-3500-2025-09", "section_a": {"identifier": "AB-CDEF"}})
    team_arg = f",p_care_team_id=>'{team}'" if team else ""
    return (
        "SET ROLE service_role; SELECT row_to_json(r) FROM public.create_medwatch_draft("
        f"p_assessment_id=>'{assessment_id}',p_actor_id=>'{actor}',p_form_data=>$f${form}$f$::jsonb,"
        f"p_source_evidence=>'[]'::jsonb,p_reportability_rationale=>'Serious reaction',"
        f"p_draft_id=>'{uuid4()}'{team_arg}) r;"
    )


def test_a_medwatch_draft_and_its_assessment_get_the_owner_with_the_draft(sql):
    two_teams(sql)
    key = assessment(sql)

    row = json.loads(sql(medwatch(key, OTHER)).splitlines()[-1])

    assert row["care_team_id"] == OTHER_TEAM
    assert owner_of(sql, key) == OTHER_TEAM

    # The first team's session sees neither; the owner's sees both.
    def count(clinician, table):
        return sql(
            f"SET ROLE authenticated; SET request.jwt.claim.sub='{clinician}'; SELECT count(*) FROM {table};"
        ).splitlines()[-1]

    assert (count(CLINICIAN, "medwatch_drafts"), count(OTHER, "medwatch_drafts")) == ("0", "1")
    assert (count(CLINICIAN, "adr_assessments"), count(OTHER, "adr_assessments")) == ("0", "1")


def test_medwatch_creation_with_two_links_requires_a_team_and_leaves_nothing_behind(sql):
    seed_people(sql, second_clinic_for_clinician=True)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, CLINICIAN, OTHER_CLINIC)
    key = assessment(sql)

    assert "CARE_TEAM_REQUIRED" in sql(medwatch(key, CLINICIAN), succeeds=False)
    assert sql("SELECT count(*) FROM medwatch_drafts") == "0"
    assert sql(f"SELECT status FROM adr_assessments WHERE id='{key}'") == "draft"


@pytest.mark.before_clinical_record_owner
def test_backfill_assigns_the_unambiguous_and_surfaces_the_rest_without_guessing(sql):
    seed_people(sql, second_clinic_for_clinician=True)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, CLINICIAN, OTHER_CLINIC)  # CLINICIAN has two links: ambiguous
    link(sql, THIRD_TEAM, THIRD, CLINIC)  # THIRD has one
    ambiguous = assessment(sql, reviewed_by=CLINICIAN, status="reviewed")
    single = assessment(sql, reviewed_by=THIRD, status="reviewed")
    pending = assessment(sql)

    sql.apply_plan_migrations()

    assert owner_of(sql, single) == THIRD_TEAM
    assert owner_of(sql, ambiguous) == "-"
    assert owner_of(sql, pending) == "-"
    # The ambiguous record is asked of every active team, and visible to nobody meanwhile.
    asked = sql(f"""SELECT string_agg(target_care_team_id::text, ',' ORDER BY target_care_team_id)
      FROM care_plan_review_items WHERE kind='unowned_clinical_record'
        AND summary->>'record_id'='{ambiguous}'""")
    assert asked == ",".join(sorted([TEAM, OTHER_TEAM, THIRD_TEAM]))
    assert (
        sql(f"""SELECT count(*) FROM care_plan_review_items WHERE kind='unowned_clinical_record'
      AND summary->>'record_id' IN ('{single}','{pending}')""")
        == "0"
    )
    for clinician in (CLINICIAN, THIRD):
        seen = sql(
            f"SET ROLE authenticated; SET request.jwt.claim.sub='{clinician}'; SELECT id FROM adr_assessments ORDER BY id;"
        ).splitlines()[-1:]
        assert ambiguous not in seen
    # The item reached the notification centre of each addressed clinician.
    assert items(sql, THIRD, "care_plan_review")
    assert all(
        row["metadata"]["review_kind"] == "unowned_clinical_record"
        for row in items(sql, THIRD, "care_plan_review")
    )


def assign(record_id, actor, team, record="adr_assessment"):
    return f"SET ROLE service_role; SELECT public.assign_clinical_record_owner('{record}','{record_id}','{actor}','{team}');"


def test_concurrent_assignment_of_an_unowned_record_has_exactly_one_winner(sql):
    two_teams(sql)
    key = assessment(sql, reviewed_by=CLINICIAN, status="reviewed")
    sql(f"UPDATE adr_assessments SET reviewed_by_care_team_id=NULL WHERE id='{key}';")
    processes = [
        sql.start(assign(key, CLINICIAN, TEAM), "assign-a"),
        sql.start(assign(key, OTHER, OTHER_TEAM), "assign-b"),
    ]

    results = [finish(p) for p in processes]

    assert sorted(r[0] == 0 for r in results) == [False, True]
    assert "taken by someone else" in next(r for r in results if r[0] != 0)[2]
    assert owner_of(sql, key) in (TEAM, OTHER_TEAM)
    assert (
        sql(
            "SELECT count(*) FROM care_plan_ownership_events WHERE event_type='clinical_record_assigned'"
        )
        == "1"
    )


def test_assignment_is_refused_to_a_stranger(sql):
    two_teams(sql)
    key = assessment(sql, reviewed_by=CLINICIAN, status="reviewed")
    sql(f"UPDATE adr_assessments SET reviewed_by_care_team_id=NULL WHERE id='{key}';")

    assert "unavailable" in sql(assign(key, THIRD, TEAM), succeeds=False)
    assert owner_of(sql, key) == "-"


# ── Care-team work items in the notification centre ────────────────────────────────────────


def new_item(sql, team, kind="cross_plan_conflict"):
    plan = sql(f"SET ROLE service_role; SELECT private.ensure_care_plan('{TEAM}');").splitlines()[
        -1
    ]
    return sql(f"""INSERT INTO care_plan_review_items(patient_id,care_plan_id,kind,target_care_team_id,summary)
      VALUES('{PATIENT}','{plan}','{kind}','{team}','{{"secret":"conflict wording"}}') RETURNING id;""").splitlines()[
        0
    ]


def test_a_review_item_reaches_only_the_addressed_teams_centre(sql):
    two_teams(sql)
    item = new_item(sql, OTHER_TEAM)

    mine = items(sql, CLINICIAN, "care_plan_review")
    theirs = items(sql, OTHER, "care_plan_review")

    assert mine == []
    assert [row["source_id"] for row in theirs] == [item]
    assert theirs[0]["actionable"] is True
    assert theirs[0]["metadata"] == {
        "review_kind": "cross_plan_conflict",
        "care_plan_id": theirs[0]["metadata"]["care_plan_id"],
    }
    assert "conflict wording" not in json.dumps(theirs)
    assert items(sql, THIRD, "care_plan_review") == []


def test_the_item_stops_asking_for_action_once_resolved_and_a_stranger_cannot_open_it(sql):
    two_teams(sql)
    item = new_item(sql, OTHER_TEAM)
    row = items(sql, OTHER, "care_plan_review")[0]

    sql(
        f"UPDATE care_plan_review_items SET status='resolved', resolved_at=now() WHERE id='{item}';"
    )

    assert items(sql, OTHER, "care_plan_review")[0]["actionable"] is False
    error = centre(sql, CLINICIAN, "read", {"item_id": row["id"]}, succeeds=False)
    assert "unavailable" in error.lower() or "not" in error.lower()


def test_a_team_that_ended_gets_no_centre_item(sql):
    two_teams(sql)
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{OTHER_TEAM}';")

    new_item(sql, OTHER_TEAM)

    assert items(sql, OTHER, "care_plan_review") == []
