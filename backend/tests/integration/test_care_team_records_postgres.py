"""Shared clinical core and care-team-owned records in a disposable PostgreSQL 16 (085).

Documents are owned by one care team or are in every team's queue ("Not sure") until one
clinician claims the whole document. Conditions the patient marks sensitive reach only their
recording team, and everyone else is told some are private. Opt-in:
``CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER=1``. Synthetic data only.
"""

from __future__ import annotations

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
    THIRD_TEAM,
    finish,
    link,
    seed_people,
)

pytest_plugins = ["tests.integration.care_team_plan_harness"]

pytestmark = [
    # The first test builds the template databases for the module.
    pytest.mark.timeout(600),
    pytest.mark.skipif(
        os.environ.get("CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER") != "1",
        reason="explicit opt-in disposable Docker PostgreSQL contract check",
    ),
]


def two_teams(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)


def document(
    sql,
    *,
    by=PATIENT,
    role="patient",
    team: str | None = None,
    state: str | None = None,
    patient=PATIENT,
    parse="completed",
    review=None,
    name=None,
) -> str:
    """Insert a document the way the backend does and return its id."""
    doc = str(uuid4())
    columns = [
        "id",
        "patient_id",
        "uploaded_by",
        "uploaded_by_role",
        "document_type",
        "file_name",
        "file_url",
        "file_path",
        "file_size_bytes",
        "parse_status",
    ]
    values = [
        f"'{doc}'",
        f"'{patient}'",
        f"'{by}'",
        f"'{role}'",
        "'other'",
        f"'{name or doc}.pdf'",
        "'x'",
        f"'{patient}/{name or doc}.pdf'",
        "10",
        f"'{parse}'",
    ]
    if team:
        columns.append("care_team_id")
        values.append(f"'{team}'")
    if state:
        columns.append("routing_state")
        values.append(f"'{state}'")
    if review:
        columns.append("review_status")
        values.append(f"'{review}'")
    sql(f"INSERT INTO documents({','.join(columns)}) VALUES({','.join(values)});")
    return doc


def routing(sql, doc) -> str:
    return sql(
        f"SELECT routing_state||':'||coalesce(care_team_id::text,'-') FROM documents WHERE id='{doc}'"
    )


def links(sql, clinician, patient=PATIENT) -> str:
    return f"private.clinician_patient_links('{clinician}','{patient}')"


def visible(sql, doc, clinician, patient=PATIENT) -> bool:
    return (
        sql(f"""SELECT private.document_visible_to_links(d.routing_state, d.care_team_id,
      {links(sql, clinician, patient)}) FROM documents d WHERE d.id='{doc}'""")
        == "t"
    )


def fact(
    sql,
    doc: str,
    *,
    kind="medication",
    state="pending_review",
    patient=PATIENT,
    value='{"name":"Lisinopril"}',
) -> str:
    """A fact with one citation whose provenance is the document."""
    fid, pid = str(uuid4()), str(uuid4())
    sql(f"""
      INSERT INTO source_provenances(id,artifact_type,source_system,source_reference,document_id)
        VALUES('{pid}','document','test','doc','{doc}');
      INSERT INTO clinical_facts(id,patient_id,fact_type,subject_type,value,review_state)
        VALUES('{fid}','{patient}','{kind}','patient','{value}','{state}');
      INSERT INTO evidence_citations(fact_id,provenance_id,excerpt) VALUES('{fid}','{pid}','x');
    """)
    return fid


def fact_visible(sql, fid, clinician) -> bool:
    return sql(f"SELECT private.fact_visible_to_links('{fid}', {links(sql, clinician)})") == "t"


# ── Upload routing ─────────────────────────────────────────────────────────────────────────


def test_patient_upload_to_a_named_team_belongs_to_that_team_alone(sql):
    two_teams(sql)

    doc = document(sql, team=OTHER_TEAM)

    assert routing(sql, doc) == f"routed:{OTHER_TEAM}"
    assert visible(sql, doc, OTHER) and not visible(sql, doc, CLINICIAN)
    assert (
        sql(f"SELECT event_type FROM document_routing_events WHERE document_id='{doc}'")
        == "routed_on_upload"
    )


def test_not_sure_is_in_every_active_teams_queue_but_no_strangers(sql):
    two_teams(sql)

    doc = document(sql, state="unrouted")

    assert routing(sql, doc) == "unrouted:-"
    assert visible(sql, doc, CLINICIAN) and visible(sql, doc, OTHER)
    assert not visible(sql, doc, THIRD)  # a clinician with no link sees nothing
    assert (
        sql(f"SELECT event_type FROM document_routing_events WHERE document_id='{doc}'")
        == "left_unrouted"
    )


def test_a_patient_cannot_route_to_a_team_that_is_not_theirs_or_has_ended(sql):
    two_teams(sql)
    link(sql, THIRD_TEAM, THIRD, CLINIC, patient=SECOND_PATIENT)
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{OTHER_TEAM}';")

    for team in (THIRD_TEAM, OTHER_TEAM):
        error = sql(
            f"""INSERT INTO documents(patient_id,uploaded_by,uploaded_by_role,document_type,
          file_name,file_url,file_size_bytes,care_team_id)
          VALUES('{PATIENT}','{PATIENT}','patient','other','a.pdf','x',10,'{team}');""",
            succeeds=False,
        )
        assert "choose one of your own care teams" in error


def test_a_clinician_upload_belongs_to_their_own_team_and_cannot_be_unrouted(sql):
    two_teams(sql)

    mine = document(sql, by=CLINICIAN, role="clinician")  # one link: worked out
    assert routing(sql, mine) == f"routed:{TEAM}"
    stolen = sql(
        f"""INSERT INTO documents(patient_id,uploaded_by,uploaded_by_role,document_type,
      file_name,file_url,file_size_bytes,care_team_id)
      VALUES('{PATIENT}','{CLINICIAN}','clinician','other','a.pdf','x',10,'{OTHER_TEAM}');""",
        succeeds=False,
    )
    assert "choose one of your own care teams" in stolen
    unrouted = sql(
        f"""INSERT INTO documents(patient_id,uploaded_by,uploaded_by_role,document_type,
      file_name,file_url,file_size_bytes,routing_state)
      VALUES('{PATIENT}','{CLINICIAN}','clinician','other','a.pdf','x',10,'unrouted');""",
        succeeds=False,
    )
    assert "belongs to the clinician" in unrouted


def test_same_clinician_at_two_clinics_must_choose_the_team_for_an_upload(sql):
    seed_people(sql, second_clinic_for_clinician=True)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, CLINICIAN, OTHER_CLINIC)

    error = sql(
        f"""INSERT INTO documents(patient_id,uploaded_by,uploaded_by_role,document_type,
      file_name,file_url,file_size_bytes)
      VALUES('{PATIENT}','{CLINICIAN}','clinician','other','a.pdf','x',10);""",
        succeeds=False,
    )
    assert "choose which care team" in error
    doc = document(sql, by=CLINICIAN, role="clinician", team=OTHER_TEAM)
    assert routing(sql, doc) == f"routed:{OTHER_TEAM}"


def test_a_patient_with_one_team_and_no_choice_is_routed_to_it_and_with_none_is_unrouted(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    assert routing(sql, document(sql)) == f"routed:{TEAM}"
    assert routing(sql, document(sql, by=SECOND_PATIENT, patient=SECOND_PATIENT)) == "unrouted:-"


def test_routing_cannot_change_outside_the_claim_function(sql):
    two_teams(sql)
    doc = document(sql, state="unrouted")

    error = sql(
        f"UPDATE documents SET care_team_id='{TEAM}', routing_state='routed' WHERE id='{doc}';",
        succeeds=False,
    )

    assert "only through routing or claiming" in error
    assert routing(sql, doc) == "unrouted:-"


# ── Claim ──────────────────────────────────────────────────────────────────────────────────


def claim(doc, actor, team):
    return f"SET ROLE service_role; SELECT public.claim_document('{doc}','{actor}','{team}');"


def test_claim_moves_the_whole_document_to_the_claimant_and_out_of_other_queues(sql):
    two_teams(sql)
    doc = document(sql, state="unrouted")

    result = sql(claim(doc, OTHER, OTHER_TEAM)).splitlines()[-1]

    assert '"status": "claimed"' in result
    assert routing(sql, doc) == f"routed:{OTHER_TEAM}"
    assert not visible(sql, doc, CLINICIAN) and visible(sql, doc, OTHER)
    assert (
        sql(
            f"SELECT actor_id||':'||to_care_team_id FROM document_routing_events WHERE document_id='{doc}' AND event_type='claimed'"
        )
        == f"{OTHER}:{OTHER_TEAM}"
    )


def test_concurrent_claims_have_exactly_one_winner(sql):
    two_teams(sql)
    doc = document(sql, state="unrouted")
    processes = [
        sql.start(claim(doc, CLINICIAN, TEAM), "claim-a"),
        sql.start(claim(doc, OTHER, OTHER_TEAM), "claim-b"),
    ]

    results = [finish(p) for p in processes]

    assert sorted(r[0] for r in results) == [0, 3] or sum(r[0] == 0 for r in results) == 1
    loser = next(r for r in results if r[0] != 0)
    assert "claimed by someone else" in loser[2]
    owner = routing(sql, doc).split(":")[1]
    assert owner in (TEAM, OTHER_TEAM)
    assert (
        sql(
            f"SELECT count(*) FROM document_routing_events WHERE document_id='{doc}' AND event_type='claimed'"
        )
        == "1"
    )
    winner = CLINICIAN if owner == TEAM else OTHER
    assert '"replayed": true' in sql(claim(doc, winner, owner)).splitlines()[-1]
    assert (
        sql(
            f"SELECT count(*) FROM document_routing_events WHERE document_id='{doc}' AND event_type='claimed'"
        )
        == "1"
    )


def test_claim_is_refused_neutrally_for_strangers_ended_links_and_routed_documents(sql):
    two_teams(sql)
    unrouted = document(sql, state="unrouted")
    routed = document(sql, team=TEAM)
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{OTHER_TEAM}';")

    assert "document unavailable" in sql(claim(unrouted, THIRD, THIRD_TEAM), succeeds=False)
    assert "document unavailable" in sql(claim(unrouted, OTHER, OTHER_TEAM), succeeds=False)
    assert "document unavailable" in sql(claim(unrouted, CLINICIAN, OTHER_TEAM), succeeds=False)
    assert "claimed by someone else" in sql(claim(routed, CLINICIAN, TEAM), succeeds=False)
    assert routing(sql, unrouted) == "unrouted:-"


def test_claim_wakes_drafting_for_the_claimants_plan_only(sql):
    two_teams(sql)
    doc = document(sql, state="unrouted", review="approved")
    fact(sql, doc)

    sql(claim(doc, OTHER, OTHER_TEAM))

    assert sql("SELECT count(*) FROM care_plan_generation_requests") == "1"
    assert (
        sql(
            "SELECT p.care_team_id FROM care_plan_generation_requests r JOIN care_plans p ON p.id=r.care_plan_id"
        )
        == OTHER_TEAM
    )
    assert sql(f"SELECT count(*) FROM care_plans WHERE care_team_id='{TEAM}'") == "0"


def test_an_unrouted_document_wakes_no_plan_when_approved(sql):
    two_teams(sql)
    doc = document(sql, state="unrouted")
    fact(sql, doc)

    sql(f"UPDATE documents SET review_status='approved' WHERE id='{doc}';")

    assert sql("SELECT count(*) FROM care_plan_generation_requests") == "0"


def test_a_routed_document_wakes_only_its_own_plan_when_approved(sql):
    two_teams(sql)
    doc = document(sql, team=TEAM)
    fact(sql, doc)

    sql(f"UPDATE documents SET review_status='approved' WHERE id='{doc}';")

    assert (
        sql(
            "SELECT p.care_team_id FROM care_plan_generation_requests r JOIN care_plans p ON p.id=r.care_plan_id"
        )
        == TEAM
    )


def test_deleting_the_owning_link_leaves_the_document_hidden_not_exposed(sql):
    two_teams(sql)
    doc = document(sql, team=OTHER_TEAM)

    sql(f"DELETE FROM care_teams WHERE id='{OTHER_TEAM}';")

    assert routing(sql, doc) == "routed:-"
    assert not visible(sql, doc, CLINICIAN) and not visible(sql, doc, OTHER)


@pytest.mark.before_owned_records
def test_backfill_routes_only_what_is_unambiguous_and_creates_no_notification(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    second_patient_doc, ambiguous, clinician_doc = str(uuid4()), str(uuid4()), str(uuid4())
    link(sql, OTHER_TEAM, CLINICIAN, CLINIC, patient=SECOND_PATIENT)
    link(sql, THIRD_TEAM, OTHER, OTHER_CLINIC, patient=SECOND_PATIENT)
    for doc, patient, by, role in (
        (second_patient_doc, PATIENT, PATIENT, "patient"),
        (ambiguous, SECOND_PATIENT, SECOND_PATIENT, "patient"),
        (clinician_doc, SECOND_PATIENT, CLINICIAN, "clinician"),
    ):
        sql(f"""INSERT INTO documents(id,patient_id,uploaded_by,uploaded_by_role,document_type,
          file_name,file_url,file_size_bytes) VALUES('{doc}','{patient}','{by}','{role}','other','a','x',1);""")
    before = sql("SELECT count(*) FROM notification_events")

    sql.apply_plan_migrations()

    assert routing(sql, second_patient_doc) == f"routed:{TEAM}"
    assert routing(sql, ambiguous) == "unrouted:-"
    assert routing(sql, clinician_doc) == f"routed:{OTHER_TEAM}"
    assert sql("SELECT count(*) FROM notification_events") == before
    assert (
        sql("SELECT count(*) FROM document_routing_events WHERE event_type='backfill_unrouted'")
        == "1"
    )


# ── Facts follow their sources ─────────────────────────────────────────────────────────────


def test_a_fact_from_another_teams_document_is_hidden_and_unrouted_facts_are_shared(sql):
    two_teams(sql)
    mine, theirs, open_doc = (
        document(sql, team=TEAM),
        document(sql, team=OTHER_TEAM),
        document(sql, state="unrouted"),
    )
    mine_fact, their_fact, open_fact = fact(sql, mine), fact(sql, theirs), fact(sql, open_doc)

    assert fact_visible(sql, mine_fact, CLINICIAN) and not fact_visible(sql, mine_fact, OTHER)
    assert fact_visible(sql, their_fact, OTHER) and not fact_visible(sql, their_fact, CLINICIAN)
    assert fact_visible(sql, open_fact, CLINICIAN) and fact_visible(sql, open_fact, OTHER)
    assert not fact_visible(sql, mine_fact, THIRD)


def test_a_fact_citing_a_hidden_document_is_hidden_even_with_a_visible_source(sql):
    two_teams(sql)
    mine, theirs = document(sql, team=TEAM), document(sql, team=OTHER_TEAM)
    shared = fact(sql, mine)
    provenance = str(uuid4())
    sql(f"""INSERT INTO source_provenances(id,artifact_type,source_system,source_reference,document_id)
      VALUES('{provenance}','document','test','doc','{theirs}');
      INSERT INTO evidence_citations(fact_id,provenance_id,excerpt) VALUES('{shared}','{provenance}','x');""")

    assert not fact_visible(sql, shared, CLINICIAN)


def test_non_document_sources_follow_their_team_and_default_to_as_shared_as_before(sql):
    two_teams(sql)
    fid, pid = str(uuid4()), str(uuid4())
    sql(f"""INSERT INTO source_provenances(id,artifact_type,source_system,source_reference,care_team_id)
      VALUES('{pid}','clinician_entry','portal','clinician:{CLINICIAN}:care-plan-entry','{TEAM}');
      INSERT INTO clinical_facts(id,patient_id,fact_type,subject_type,value)
        VALUES('{fid}','{PATIENT}','obligation','patient','{{}}');
      INSERT INTO evidence_citations(fact_id,provenance_id,excerpt) VALUES('{fid}','{pid}','x');""")

    assert fact_visible(sql, fid, CLINICIAN) and not fact_visible(sql, fid, OTHER)
    sql(f"UPDATE source_provenances SET care_team_id=NULL WHERE id='{pid}';")
    assert fact_visible(sql, fid, OTHER)


def test_plan_drafting_sources_are_only_facts_routed_to_that_plans_team(sql):
    two_teams(sql)
    mine, theirs, open_doc = (
        document(sql, by=CLINICIAN, role="clinician", team=TEAM),
        document(sql, by=OTHER, role="clinician", team=OTHER_TEAM),
        document(sql, state="unrouted", review="approved"),
    )
    mine_fact, their_fact, _ = fact(sql, mine), fact(sql, theirs), fact(sql, open_doc)
    plan = sql(f"SELECT private.ensure_care_plan('{TEAM}')")
    other_plan = sql(f"SELECT private.ensure_care_plan('{OTHER_TEAM}')")

    assert (
        sql(f"SELECT string_agg(x::text, ',') FROM public.care_plan_source_fact_ids('{plan}') x")
        == mine_fact
    )
    assert (
        sql(
            f"SELECT string_agg(x::text, ',') FROM public.care_plan_source_fact_ids('{other_plan}') x"
        )
        == their_fact
    )


def test_unowned_and_adopted_plans_draft_from_nothing(sql):
    two_teams(sql)
    mine = document(sql, by=CLINICIAN, role="clinician", team=TEAM)
    fact(sql, mine)
    plan = sql(f"SELECT private.ensure_care_plan('{TEAM}')")
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{TEAM}';")

    assert sql(f"SELECT count(*) FROM public.care_plan_source_fact_ids('{plan}')") == "0"
    sql(
        f"SET ROLE service_role; SELECT public.adopt_care_plan('{plan}','{OTHER}','{OTHER_TEAM}','taking over');"
    )
    assert sql(f"SELECT count(*) FROM public.care_plan_source_fact_ids('{plan}')") == "0"


# ── Shared core: medications, allergies, sensitive conditions ──────────────────────────────


def shared_core(sql):
    two_teams(sql)
    link(sql, THIRD_TEAM, THIRD, CLINIC)
    sql(f"""
      INSERT INTO medications(patient_id,name,dosage,frequency,route,is_active,prescribed_by_care_team_id)
        VALUES('{PATIENT}','Lisinopril','10 mg','daily','oral',true,'{TEAM}'),
              ('{PATIENT}','Stopped drug','5 mg','daily','oral',false,'{TEAM}');
      INSERT INTO allergies(patient_id,allergen,severity,recorded_by_care_team_id)
        VALUES('{PATIENT}','Penicillin','severe','{OTHER_TEAM}');
      INSERT INTO conditions(patient_id,name,status,recorded_by_care_team_id)
        VALUES('{PATIENT}','Hypertension','active','{TEAM}'),
              ('{PATIENT}','Anxiety','active','{OTHER_TEAM}');
    """)


def summary(sql, clinician):
    import json

    raw = sql(
        f"SET ROLE service_role; SELECT public.shared_clinical_summary('{clinician}','{PATIENT}');"
    ).splitlines()[-1]
    return json.loads(raw)


def condition_id(sql, name):
    return sql(f"SELECT id FROM conditions WHERE name='{name}'")


def set_sensitive(sql, condition, value=True, patient=PATIENT):
    return f"SET ROLE service_role; SELECT public.set_condition_sensitivity('{patient}','{condition}',{str(value).lower()});"


def test_every_team_sees_active_medications_and_allergies_with_the_recording_team(sql):
    shared_core(sql)

    for clinician in (CLINICIAN, OTHER, THIRD):
        data = summary(sql, clinician)
        assert [m["name"] for m in data["medications"]] == ["Lisinopril"]
        assert data["medications"][0]["recorded_by"]["clinician_name"] == "Elena Park"
        assert data["medications"][0]["recorded_by"]["clinic_name"] == "Cedar Grove"
        assert data["allergies"][0]["allergen"] == "Penicillin"
        assert data["allergies"][0]["recorded_by"]["specialty"]
        assert len(data["care_teams"]) == 3
    assert [t["is_mine"] for t in summary(sql, THIRD)["care_teams"]].count(True) == 1


def test_a_sensitive_condition_reaches_only_its_recording_team_with_an_explicit_marker(sql):
    shared_core(sql)
    sql(set_sensitive(sql, condition_id(sql, "Anxiety")))

    owner, other, third = summary(sql, OTHER), summary(sql, CLINICIAN), summary(sql, THIRD)

    assert sorted(c["name"] for c in owner["conditions"]) == ["Anxiety", "Hypertension"]
    assert owner["some_conditions_private"] is False
    for data in (other, third):
        assert [c["name"] for c in data["conditions"]] == ["Hypertension"]
        assert data["some_conditions_private"] is True


def test_sensitive_with_an_unknown_recorder_is_visible_to_no_clinician(sql):
    shared_core(sql)
    sql("UPDATE conditions SET recorded_by_care_team_id=NULL WHERE name='Anxiety';")
    sql(set_sensitive(sql, condition_id(sql, "Anxiety")))

    for clinician in (CLINICIAN, OTHER, THIRD):
        data = summary(sql, clinician)
        assert "Anxiety" not in [c["name"] for c in data["conditions"]]
        assert data["some_conditions_private"] is True


def test_unmarking_restores_sharing_and_every_change_is_audited_without_names(sql):
    shared_core(sql)
    anxiety = condition_id(sql, "Anxiety")
    sql(set_sensitive(sql, anxiety))
    sql(set_sensitive(sql, anxiety))  # repeat: no second event
    sql(set_sensitive(sql, anxiety, False))

    assert summary(sql, CLINICIAN)["some_conditions_private"] is False
    assert "Anxiety" in [c["name"] for c in summary(sql, CLINICIAN)["conditions"]]
    assert (
        sql(
            f"SELECT string_agg(is_sensitive::text, ',' ORDER BY created_at) FROM condition_sensitivity_events WHERE condition_id='{anxiety}'"
        )
        == "true,false"
    )
    assert (
        sql(
            "SELECT count(*) FROM condition_sensitivity_events WHERE row_to_json(condition_sensitivity_events)::text ILIKE '%anxiety%'"
        )
        == "0"
    )


def test_a_patient_marks_only_their_own_conditions(sql):
    shared_core(sql)
    sql(
        f"""INSERT INTO conditions(patient_id,name,status) VALUES('{SECOND_PATIENT}','Asthma','active');"""
    )

    error = sql(set_sensitive(sql, condition_id(sql, "Asthma")), succeeds=False)

    assert "condition unavailable" in error
    missing = sql(set_sensitive(sql, str(uuid4())), succeeds=False)
    assert "condition unavailable" in missing  # same answer: nothing to probe
    assert sql("SELECT is_sensitive FROM conditions WHERE name='Asthma'") == "f"


def test_a_clinician_without_a_link_gets_no_summary(sql):
    shared_core(sql)
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{TEAM}';")

    assert "patient unavailable" in sql(
        f"SET ROLE service_role; SELECT public.shared_clinical_summary('{CLINICIAN}','{PATIENT}');",
        succeeds=False,
    )


def test_reconciliation_records_the_reviewing_team_and_the_label_survives_the_link(sql):
    two_teams(sql)
    doc = document(sql, team=TEAM)
    fid = fact(sql, doc, kind="condition", value='{"name":"Migraine"}')

    sql(f"""SET ROLE service_role; SELECT public.apply_clinical_fact_reconciliation(
      '{fid}','{CLINICIAN}','add',NULL,'{{"name":"Migraine"}}'::jsonb,'["name"]'::jsonb,NULL,'{uuid4()}');""")

    assert sql("SELECT recorded_by_care_team_id FROM conditions WHERE name='Migraine'") == TEAM
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{TEAM}';")
    assert (
        sql("SELECT recorded_by->>'clinician_name' FROM conditions WHERE name='Migraine'")
        == "Elena Park"
    )


def test_reconciliation_by_a_clinician_with_two_links_uses_the_facts_own_team(sql):
    seed_people(sql, second_clinic_for_clinician=True)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, CLINICIAN, OTHER_CLINIC)
    doc = document(sql, by=CLINICIAN, role="clinician", team=OTHER_TEAM)
    fid = fact(sql, doc, kind="allergy", value='{"allergen":"Latex"}')
    undetermined = fact(
        sql, document(sql, state="unrouted"), kind="allergy", value='{"allergen":"Nuts"}'
    )

    for fact_id, allergen in ((fid, "Latex"), (undetermined, "Nuts")):
        sql(f"""SET ROLE service_role; SELECT public.apply_clinical_fact_reconciliation(
          '{fact_id}','{CLINICIAN}','add',NULL,'{{"allergen":"{allergen}"}}'::jsonb,'["allergen"]'::jsonb,NULL,'{uuid4()}');""")

    assert (
        sql("SELECT recorded_by_care_team_id FROM allergies WHERE allergen='Latex'") == OTHER_TEAM
    )
    # Two links and an unrouted source: the recording team is unknown, never a guess.
    assert (
        sql(
            "SELECT coalesce(recorded_by_care_team_id::text,'-') FROM allergies WHERE allergen='Nuts'"
        )
        == "-"
    )


# ── Storage and browser roles ──────────────────────────────────────────────────────────────


def test_a_clinician_reads_a_stored_file_only_when_its_document_is_theirs(sql):
    two_teams(sql)
    mine, theirs, open_doc = (
        document(sql, team=TEAM, name="mine"),
        document(sql, team=OTHER_TEAM, name="theirs"),
        document(sql, state="unrouted", name="open"),
    )
    for name in ("mine", "theirs", "open", "stray"):
        sql(
            f"INSERT INTO storage.objects(bucket_id,name) VALUES('documents','{PATIENT}/{name}.pdf');"
        )

    names = sql(f"""SET ROLE authenticated; SET request.jwt.claim.sub='{CLINICIAN}';
      SELECT string_agg(name, ',' ORDER BY name) FROM storage.objects WHERE bucket_id='documents';""")

    assert names.splitlines()[-1] == f"{PATIENT}/mine.pdf,{PATIENT}/open.pdf"
    assert mine and theirs and open_doc


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_browser_roles_reach_none_of_the_new_objects_or_the_owned_tables(sql, role):
    two_teams(sql)
    document(sql, team=TEAM)
    for relation in ("document_routing_events", "condition_sensitivity_events"):
        assert "permission denied" in sql(
            f"SET ROLE {role}; SELECT count(*) FROM {relation};", succeeds=False
        )
    for call in (
        f"public.claim_document('{uuid4()}','{CLINICIAN}','{TEAM}')",
        f"public.set_condition_sensitivity('{PATIENT}','{uuid4()}',true)",
        f"public.shared_clinical_summary('{CLINICIAN}','{PATIENT}')",
        f"public.care_plan_source_fact_ids('{uuid4()}')",
    ):
        assert "permission denied" in sql(f"SET ROLE {role}; SELECT {call};", succeeds=False)


def as_clinician(clinician, statement):
    return f"SET ROLE authenticated; SET request.jwt.claim.sub='{clinician}'; {statement}"


def test_a_clinician_session_reads_documents_and_their_facts_only_when_owned(sql):
    two_teams(sql)
    mine, theirs, open_doc = (
        document(sql, team=TEAM, name="a"),
        document(sql, team=OTHER_TEAM, name="b"),
        document(sql, state="unrouted", name="c"),
    )
    mine_fact, their_fact, open_fact = fact(sql, mine), fact(sql, theirs), fact(sql, open_doc)

    docs = sql(
        as_clinician(
            CLINICIAN, "SELECT string_agg(id::text, ',' ORDER BY file_name) FROM documents;"
        )
    ).splitlines()[-1]
    facts = sql(
        as_clinician(CLINICIAN, "SELECT string_agg(id::text, ',' ORDER BY id) FROM clinical_facts;")
    ).splitlines()[-1]
    citations = sql(
        as_clinician(CLINICIAN, "SELECT count(*) FROM evidence_citations;")
    ).splitlines()[-1]
    provenances = sql(
        as_clinician(CLINICIAN, "SELECT count(*) FROM source_provenances;")
    ).splitlines()[-1]

    assert docs == f"{mine},{open_doc}"
    assert sorted(facts.split(",")) == sorted([mine_fact, open_fact])
    assert their_fact not in facts
    assert citations == "2" and provenances == "2"
    # A clinician with no link reads nothing at all.
    assert sql(as_clinician(THIRD, "SELECT count(*) FROM documents;")).splitlines()[-1] == "0"


def test_a_clinician_session_never_reads_another_teams_soap_note(sql):
    two_teams(sql)
    sql(f"""INSERT INTO soap_notes(patient_id,clinician_id,care_team_id,subjective,objective,assessment,plan)
      VALUES('{PATIENT}','{OTHER}','{OTHER_TEAM}','s','o','a','p'),
            ('{PATIENT}','{CLINICIAN}','{TEAM}','s','o','a','p'),
            ('{PATIENT}','{OTHER}',NULL,'legacy','o','a','p');""")

    assert (
        sql(
            as_clinician(
                CLINICIAN, "SELECT string_agg(subjective, ',' ORDER BY subjective) FROM soap_notes;"
            )
        ).splitlines()[-1]
        == "s"
    )
    assert (
        sql(
            as_clinician(
                OTHER, "SELECT string_agg(subjective, ',' ORDER BY subjective) FROM soap_notes;"
            )
        ).splitlines()[-1]
        == "legacy,s"
    )


def test_a_clinician_session_never_reads_a_sensitive_condition_it_did_not_record(sql):
    shared_core(sql)
    sql(set_sensitive(sql, condition_id(sql, "Anxiety")))

    mine = sql(
        as_clinician(CLINICIAN, "SELECT string_agg(name, ',' ORDER BY name) FROM conditions;")
    ).splitlines()[-1]
    owner = sql(
        as_clinician(OTHER, "SELECT string_agg(name, ',' ORDER BY name) FROM conditions;")
    ).splitlines()[-1]

    assert mine == "Hypertension"
    assert owner == "Anxiety,Hypertension"
    assert "permission denied" in sql(
        as_clinician(CLINICIAN, "UPDATE conditions SET is_sensitive=false;"), succeeds=False
    )
    assert "permission denied" in sql(
        as_clinician(
            CLINICIAN,
            f"INSERT INTO conditions(patient_id,name,recorded_by_care_team_id) VALUES('{PATIENT}','x','{OTHER_TEAM}');",
        ),
        succeeds=False,
    )


def test_a_clinician_session_reads_reviewed_adr_work_only_for_its_own_team(sql):
    two_teams(sql)
    symptom, symptom_2, medication = str(uuid4()), str(uuid4()), str(uuid4())
    sql(f"""
      SET session_replication_role = replica;
      INSERT INTO medications(id,patient_id,name,dosage,frequency,route) VALUES('{medication}','{PATIENT}','M','1','daily','oral');
      INSERT INTO symptom_reports(id,patient_id,symptom,severity) VALUES('{symptom}','{PATIENT}','rash',3),('{symptom_2}','{PATIENT}','itch',3);
      INSERT INTO adr_assessments(patient_id,symptom_report_id,suspect_medication_id,suspect_medication_name,naranjo_score,causality,status,reviewed_by,reviewed_by_care_team_id)
        VALUES('{PATIENT}','{symptom}','{medication}','M',3,'Possible','draft',NULL,NULL),
              ('{PATIENT}','{symptom_2}','{medication}','M',4,'Possible','reviewed','{OTHER}','{OTHER_TEAM}');""")

    assert (
        sql(as_clinician(CLINICIAN, "SELECT count(*) FROM adr_assessments;")).splitlines()[-1]
        == "1"
    )
    assert sql(as_clinician(OTHER, "SELECT count(*) FROM adr_assessments;")).splitlines()[-1] == "2"
