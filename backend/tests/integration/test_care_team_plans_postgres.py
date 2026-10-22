"""Care-team plan ownership contracts in a disposable PostgreSQL 16 (PLAN-002, migration 080).

Covers the lineage move (backfill, ambiguity, identity preservation), per-plan versions and
drafts, the end of a care team, adoption and retirement, append-only audit, and grants.
Opt-in: ``CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER=1``. Synthetic data only.
"""

from __future__ import annotations

import os

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

VERSION = "00000000-0000-0000-0000-0000000000a1"
VERSION_2 = "00000000-0000-0000-0000-0000000000a2"
ITEM = "00000000-0000-0000-0000-0000000000b1"
ITEM_2 = "00000000-0000-0000-0000-0000000000b2"
MEDICATION = "00000000-0000-0000-0000-0000000000c1"
OBLIGATION = "00000000-0000-0000-0000-0000000000c2"


def seed_legacy_lineage(sql, *, approver: str, patient: str = PATIENT, projected_team: str | None):
    """A pre-080 approved version with one medication and one obligation projection."""
    team = f"'{projected_team}'" if projected_team else "NULL"
    sql(f"""
      SET session_replication_role = replica;
      INSERT INTO care_plan_versions(id,patient_id,version_number,status,approved_by,approved_at)
        VALUES('{VERSION}','{patient}',1,'superseded','{approver}',now() - interval '2 days'),
              ('{VERSION_2}','{patient}',2,'approved','{approver}',now());
      INSERT INTO care_plan_items(id,plan_version_id,category,title,instructions,frequency,
          medication,projection_type,projection_id)
        VALUES('{ITEM}','{VERSION_2}','medication','Lisinopril 10 mg','Take one tablet','daily',
          '{{"name":"Lisinopril","dosage":"10 mg","frequency":"daily","route":"oral"}}',
          'medication','{MEDICATION}'),
          ('{ITEM_2}','{VERSION_2}','movement','Walk','Walk 20 minutes','daily','{{}}',
          'obligation','{OBLIGATION}');
      INSERT INTO medications(id,patient_id,name,dosage,frequency,route,is_active,
          care_plan_item_id,prescribed_by_care_team_id)
        VALUES('{MEDICATION}','{patient}','Lisinopril','10 mg','daily','oral',true,'{ITEM}',{team});
      INSERT INTO obligations(id,patient_id,obligation_type,description,frequency,is_active,
          care_plan_item_id,set_by_care_team_id)
        VALUES('{OBLIGATION}','{patient}','exercise','Walk','daily',true,'{ITEM_2}',{team});
    """)


def plans(sql, patient: str = PATIENT) -> list[tuple[str, ...]]:
    rows = sql(f"""SELECT coalesce(care_team_id::text,'-'), ownership_state, origin
      FROM care_plans WHERE patient_id='{patient}' ORDER BY created_at, id""")
    return [tuple(line.split("|")) for line in rows.splitlines() if line]


# ── Lineage move ───────────────────────────────────────────────────────────────────────────


@pytest.mark.before_care_team_plans
def test_single_link_approver_owns_the_legacy_plan_and_nothing_is_rewritten(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    seed_legacy_lineage(sql, approver=CLINICIAN, projected_team=None)
    before = sql("SELECT id||status||version_number FROM care_plan_versions ORDER BY id")

    sql.apply_plan_migrations()

    assert plans(sql) == [(TEAM, "owned", "native")]
    assert sql("SELECT id||status||version_number FROM care_plan_versions ORDER BY id") == before
    # Item and projection identities, and their link, are exactly as they were.
    assert sql(f"SELECT projection_id FROM care_plan_items WHERE id='{ITEM}'") == MEDICATION
    assert sql(f"SELECT care_plan_item_id FROM medications WHERE id='{MEDICATION}'") == ITEM
    assert sql(f"SELECT care_plan_item_id FROM obligations WHERE id='{OBLIGATION}'") == ITEM_2
    assert sql("SELECT count(*) FROM care_plan_versions WHERE care_plan_id IS NULL") == "0"
    assert sql(
        "SELECT event_type||':'||(event_data->>'basis') FROM care_plan_ownership_events"
    ) == ("backfill_assigned:approver_single_link")


@pytest.mark.before_care_team_plans
def test_approver_with_two_links_uses_the_link_the_activities_were_projected_for(sql):
    seed_people(sql, second_clinic_for_clinician=True)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, CLINICIAN, OTHER_CLINIC)
    seed_legacy_lineage(sql, approver=CLINICIAN, projected_team=OTHER_TEAM)

    sql.apply_plan_migrations()

    assert plans(sql) == [(OTHER_TEAM, "owned", "native")]
    assert sql("SELECT event_data->>'basis' FROM care_plan_ownership_events") == (
        "projected_for_one_link"
    )


@pytest.mark.before_care_team_plans
def test_ambiguous_legacy_plan_is_left_unassigned_and_surfaces_a_review_item(sql):
    seed_people(sql, second_clinic_for_clinician=True)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, CLINICIAN, OTHER_CLINIC)
    link(sql, THIRD_TEAM, THIRD, CLINIC)
    # No recorded projection team: two of this clinician's links fit, so nothing is guessed.
    seed_legacy_lineage(sql, approver=CLINICIAN, projected_team=None)

    sql.apply_plan_migrations()

    assert plans(sql) == [("-", "unassigned_legacy", "legacy")]
    items = sql("""SELECT kind||':'||target_care_team_id FROM care_plan_review_items
      WHERE target_care_team_id IS NOT NULL ORDER BY target_care_team_id""").splitlines()
    assert items == [f"unassigned_legacy_plan:{t}" for t in (TEAM, OTHER_TEAM, THIRD_TEAM)]
    # The plan stays readable to nobody by guess: Today still serves its activities.
    assert sql(f"SELECT is_active FROM medications WHERE id='{MEDICATION}'") == "t"
    assert sql("SELECT event_type FROM care_plan_ownership_events") == "backfill_unassigned"


@pytest.mark.before_care_team_plans
def test_only_care_team_is_the_owner_when_nobody_approved(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    sql(f"""SET session_replication_role = replica;
      INSERT INTO care_plan_versions(id,patient_id,version_number,status)
        VALUES('{VERSION}','{PATIENT}',1,'draft');""")

    sql.apply_plan_migrations()

    assert plans(sql) == [(TEAM, "owned", "native")]
    assert sql("SELECT event_data->>'basis' FROM care_plan_ownership_events") == (
        "patient_single_care_team"
    )


@pytest.mark.before_care_team_plans
def test_legacy_plan_of_an_ended_link_is_unowned_and_keeps_its_activities(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC, status="inactive")
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)
    seed_legacy_lineage(sql, approver=CLINICIAN, projected_team=TEAM)

    sql.apply_plan_migrations()

    assert plans(sql) == [("-", "unowned", "native")]
    assert sql(f"SELECT is_active FROM medications WHERE id='{MEDICATION}'") == "t"
    # The remaining team and the ended link's clinic admins are told; admins see no patient.
    assert (
        sql(f"""SELECT count(*) FROM care_plan_review_items
      WHERE kind='unowned_plan' AND target_care_team_id='{OTHER_TEAM}'""")
        == "1"
    )
    assert (
        sql(f"""SELECT count(*) FROM care_plan_review_items
      WHERE kind='unowned_plan' AND target_clinic_id='{CLINIC}'""")
        == "1"
    )


@pytest.mark.before_care_team_plans
def test_patients_without_plans_get_none_and_open_requests_without_an_owner_close(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC, patient=SECOND_PATIENT)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC, patient=SECOND_PATIENT)
    sql(f"""INSERT INTO care_plan_generation_requests(patient_id,source_watermark)
      VALUES('{SECOND_PATIENT}',now());""")

    sql.apply_plan_migrations()

    assert sql("SELECT count(*) FROM care_plans") == "0"
    assert sql("SELECT status||':'||failure_code FROM care_plan_generation_requests") == (
        "failed:owner_unassigned"
    )


# ── Per-plan versions and drafts ───────────────────────────────────────────────────────────


def new_plan(sql, team):
    return sql(f"SET ROLE service_role; SELECT private.ensure_care_plan('{team}');").splitlines()[
        -1
    ]


def add_draft(sql, plan, number=1, patient=PATIENT):
    return sql(f"""INSERT INTO care_plan_versions(patient_id,care_plan_id,version_number,status)
      VALUES('{patient}','{plan}',{number},'draft') RETURNING id;""").splitlines()[0]


def test_two_clinicians_at_two_clinics_hold_independent_concurrent_drafts(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)
    first, second = new_plan(sql, TEAM), new_plan(sql, OTHER_TEAM)
    assert first != second

    a = add_draft(sql, first)
    b = add_draft(sql, second)

    assert a != b
    # Both plans number their own versions from 1.
    assert sql(f"SELECT version_number FROM care_plan_versions WHERE id IN ('{a}','{b}')") == "1\n1"
    # A plan never holds a second open draft ...
    error = sql(
        f"""INSERT INTO care_plan_versions(patient_id,care_plan_id,version_number,status)
        VALUES('{PATIENT}','{first}',2,'draft');""",
        succeeds=False,
    )
    assert "care_plan_versions_one_open_draft" in error
    # ... and a version cannot be attached to another patient's plan.
    error = sql(
        f"""INSERT INTO care_plan_versions(patient_id,care_plan_id,version_number,status)
        VALUES('{SECOND_PATIENT}','{first}',9,'draft');""",
        succeeds=False,
    )
    assert "different patients" in error


def test_same_clinician_at_two_clinics_has_two_separate_plans(sql):
    seed_people(sql, second_clinic_for_clinician=True)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, CLINICIAN, OTHER_CLINIC)

    one, two = new_plan(sql, TEAM), new_plan(sql, OTHER_TEAM)

    assert one != two
    assert new_plan(sql, TEAM) == one  # idempotent
    assert sql(f"SELECT count(*) FROM care_plans WHERE patient_id='{PATIENT}'") == "2"
    assert sql(f"SELECT clinic_id FROM care_teams WHERE id='{TEAM}'") != sql(
        f"SELECT clinic_id FROM care_teams WHERE id='{OTHER_TEAM}'"
    )


def test_a_version_cannot_move_between_plans(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)
    first, second = new_plan(sql, TEAM), new_plan(sql, OTHER_TEAM)
    version = add_draft(sql, first)

    error = sql(
        f"UPDATE care_plan_versions SET care_plan_id='{second}' WHERE id='{version}';",
        succeeds=False,
    )

    assert "cannot move between plans" in error


# ── When a care team ends ──────────────────────────────────────────────────────────────────


def approved_plan(sql, team, *, number=1, approver=CLINICIAN):
    """An approved version with one medication and one obligation projection for the plan."""
    plan = new_plan(sql, team)
    version = add_draft(sql, plan, number)
    sql(f"""
      SET session_replication_role = replica;
      INSERT INTO care_plan_items(id,plan_version_id,category,title,instructions,frequency,
          medication,projection_type,projection_id)
        VALUES('{ITEM}','{version}','medication','Lisinopril 10 mg','Take one','daily',
          '{{"name":"Lisinopril"}}','medication','{MEDICATION}'),
          ('{ITEM_2}','{version}','movement','Walk','Walk 20 minutes','daily','{{}}',
          'obligation','{OBLIGATION}');
      INSERT INTO medications(id,patient_id,name,dosage,frequency,route,is_active,
          care_plan_item_id,prescribed_by_care_team_id)
        VALUES('{MEDICATION}','{PATIENT}','Lisinopril','10 mg','daily','oral',true,'{ITEM}','{team}');
      INSERT INTO obligations(id,patient_id,obligation_type,description,frequency,is_active,
          care_plan_item_id,set_by_care_team_id)
        VALUES('{OBLIGATION}','{PATIENT}','exercise','Walk','daily',true,'{ITEM_2}','{team}');
      UPDATE care_plan_versions SET status='approved', approved_by='{approver}',
        approved_at=now() WHERE id='{version}';
    """)
    return plan, version


def test_ending_a_link_makes_the_plan_unowned_and_changes_no_activity_or_medication(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)
    plan, _ = approved_plan(sql, TEAM)

    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{TEAM}';")

    assert (
        sql(
            f"SELECT ownership_state||':'||coalesce(care_team_id::text,'-') FROM care_plans WHERE id='{plan}'"
        )
        == "unowned:-"
    )
    assert (
        sql(f"SELECT owner_snapshot->>'clinician_name' FROM care_plans WHERE id='{plan}'")
        == "Elena Park"
    )
    assert (
        sql(
            "SELECT string_agg(is_active::text,',') FROM (SELECT is_active FROM medications UNION ALL SELECT is_active FROM obligations) x"
        )
        == "true,true"
    )
    assert sql(f"SELECT status FROM care_plan_versions WHERE care_plan_id='{plan}'") == "approved"
    assert (
        sql(f"""SELECT count(*) FROM care_plan_review_items WHERE care_plan_id='{plan}'
      AND kind='unowned_plan' AND target_care_team_id='{OTHER_TEAM}' AND status='open'""")
        == "1"
    )
    assert (
        sql(f"""SELECT count(*) FROM care_plan_review_items WHERE care_plan_id='{plan}'
      AND target_clinic_id='{CLINIC}' AND status='open'""")
        == "1"
    )
    assert (
        sql(
            f"SELECT event_type FROM care_plan_ownership_events WHERE care_plan_id='{plan}' ORDER BY created_at DESC LIMIT 1"
        )
        == "team_ended"
    )


def test_no_remaining_team_still_keeps_the_activities_and_tells_only_the_clinic(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    plan, _ = approved_plan(sql, TEAM)

    sql(f"UPDATE care_teams SET status='transferred' WHERE id='{TEAM}';")

    assert sql(f"SELECT ownership_state FROM care_plans WHERE id='{plan}'") == "unowned"
    assert sql("SELECT count(*) FROM medications WHERE is_active") == "1"
    assert (
        sql(
            f"SELECT count(*) FROM care_plan_review_items WHERE care_plan_id='{plan}' AND target_care_team_id IS NOT NULL"
        )
        == "0"
    )
    assert (
        sql(
            f"SELECT count(*) FROM care_plan_review_items WHERE care_plan_id='{plan}' AND target_clinic_id='{CLINIC}'"
        )
        == "1"
    )


def test_deleting_a_clinician_account_hands_the_plan_over_without_losing_the_name(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)
    plan, _ = approved_plan(sql, TEAM, approver=OTHER)

    sql(f"DELETE FROM clinicians WHERE id='{CLINICIAN}';")

    assert sql(f"SELECT ownership_state FROM care_plans WHERE id='{plan}'") == "unowned"
    assert (
        sql(f"SELECT owner_snapshot->>'clinician_name' FROM care_plans WHERE id='{plan}'")
        == "Elena Park"
    )
    assert sql("SELECT count(*) FROM medications WHERE is_active") == "1"


def test_deleting_the_patient_is_not_blocked_by_plan_ownership(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)
    new_plan(sql, TEAM)
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{TEAM}';")

    # Plan, ownership and review-item rows add no blocker (approved versions already protect
    # their items in the existing schema, so this patient has none).
    sql(f"DELETE FROM patients WHERE id='{PATIENT}';")

    assert sql("SELECT count(*) FROM care_plans") == "0"
    assert sql("SELECT count(*) FROM care_plan_review_items") == "0"


# ── Adoption and retirement ────────────────────────────────────────────────────────────────


def adopt(sql, plan, actor, team, note="Taking over this plan"):
    return f"SET ROLE service_role; SELECT public.adopt_care_plan('{plan}','{actor}','{team}','{note}');"


def unowned_with_two_candidates(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)
    link(sql, THIRD_TEAM, THIRD, CLINIC)
    plan, _ = approved_plan(sql, TEAM)
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{TEAM}';")
    return plan


def test_adoption_makes_the_plan_theirs_and_closes_the_review_items(sql):
    plan = unowned_with_two_candidates(sql)

    result = sql(adopt(sql, plan, OTHER, OTHER_TEAM)).splitlines()[-1]

    assert '"status": "adopted"' in result
    assert (
        sql(
            f"SELECT ownership_state||':'||care_team_id||':'||origin FROM care_plans WHERE id='{plan}'"
        )
        == f"owned:{OTHER_TEAM}:adopted"
    )
    assert (
        sql(
            f"SELECT count(*) FROM care_plan_review_items WHERE care_plan_id='{plan}' AND status='open'"
        )
        == "0"
    )
    assert (
        sql(
            f"SELECT actor_id FROM care_plan_ownership_events WHERE care_plan_id='{plan}' AND event_type='plan_adopted'"
        )
        == OTHER
    )
    # Activities, and their link to the same item, are unchanged.
    assert sql(f"SELECT care_plan_item_id FROM medications WHERE id='{MEDICATION}'") == ITEM


def test_adoption_by_a_stranger_or_an_ended_link_is_refused_neutrally(sql):
    plan = unowned_with_two_candidates(sql)
    seed = (
        "INSERT INTO auth.users VALUES('00000000-0000-0000-0000-0000000000f1');"
        + f"INSERT INTO clinicians(id,email,first_name,last_name,specialty,clinic_id) VALUES('00000000-0000-0000-0000-0000000000f1','x@synthetic.invalid','No','Link','Derm','{CLINIC}');"
    )
    sql(seed)

    stranger = sql(
        adopt(sql, plan, "00000000-0000-0000-0000-0000000000f1", OTHER_TEAM), succeeds=False
    )
    ended = sql(adopt(sql, plan, CLINICIAN, TEAM), succeeds=False)
    wrong_actor = sql(adopt(sql, plan, THIRD, OTHER_TEAM), succeeds=False)

    for error in (stranger, ended, wrong_actor):
        assert "care plan unavailable" in error
    assert sql(f"SELECT ownership_state FROM care_plans WHERE id='{plan}'") == "unowned"


def test_adoption_requires_a_note(sql):
    plan = unowned_with_two_candidates(sql)

    assert "note is required" in sql(adopt(sql, plan, OTHER, OTHER_TEAM, note="  "), succeeds=False)


def test_concurrent_adoption_has_exactly_one_winner_and_a_replay_is_safe(sql):
    plan = unowned_with_two_candidates(sql)
    processes = [
        sql.start(adopt(sql, plan, OTHER, OTHER_TEAM), "adopt-a"),
        sql.start(adopt(sql, plan, THIRD, THIRD_TEAM), "adopt-b"),
    ]

    results = [finish(p) for p in processes]

    winners = [r for r in results if r[0] == 0]
    losers = [r for r in results if r[0] != 0]
    assert len(winners) == 1 and len(losers) == 1
    assert "adopted by someone else" in losers[0][2]
    owner = sql(f"SELECT care_team_id FROM care_plans WHERE id='{plan}'")
    assert owner in (OTHER_TEAM, THIRD_TEAM)
    assert (
        sql(
            f"SELECT count(*) FROM care_plan_ownership_events WHERE care_plan_id='{plan}' AND event_type='plan_adopted'"
        )
        == "1"
    )
    # The winner repeating the call gets the same result; nothing is audited twice.
    actor = OTHER if owner == OTHER_TEAM else THIRD
    again = sql(adopt(sql, plan, actor, owner)).splitlines()[-1]
    assert '"replayed": true' in again
    assert (
        sql(
            f"SELECT count(*) FROM care_plan_ownership_events WHERE care_plan_id='{plan}' AND event_type='plan_adopted'"
        )
        == "1"
    )


def test_an_adopted_plan_can_coexist_with_the_adopters_own_plan(sql):
    plan = unowned_with_two_candidates(sql)
    own = new_plan(sql, OTHER_TEAM)

    sql(adopt(sql, plan, OTHER, OTHER_TEAM))

    assert own != plan
    assert sql(f"SELECT count(*) FROM care_plans WHERE care_team_id='{OTHER_TEAM}'") == "2"


def retire(sql, plan, actor, team, items, reason="Duplicate of my own order"):
    ids = ",".join(f"'{i}'" for i in items)
    return f"SET ROLE service_role; SELECT public.retire_care_plan_items('{plan}','{actor}','{team}',ARRAY[{ids}]::uuid[],'{reason}');"


def test_retiring_items_turns_off_only_those_activities_and_is_audited(sql):
    plan = unowned_with_two_candidates(sql)

    result = sql(retire(sql, plan, THIRD, THIRD_TEAM, [ITEM_2])).splitlines()[-1]

    assert '"retired": 1' in result and '"remaining": 1' in result
    assert sql(f"SELECT is_active FROM obligations WHERE id='{OBLIGATION}'") == "f"
    assert sql(f"SELECT is_active FROM medications WHERE id='{MEDICATION}'") == "t"
    assert (
        sql(f"SELECT retired_by FROM care_plan_item_retirements WHERE item_id='{ITEM_2}'") == THIRD
    )
    assert (
        sql(
            f"SELECT count(*) FROM care_plan_review_items WHERE care_plan_id='{plan}' AND status='open'"
        )
        != "0"
    )

    sql(retire(sql, plan, THIRD, THIRD_TEAM, [ITEM], reason="Stopped by the prescriber"))
    assert (
        sql(
            f"SELECT count(*) FROM care_plan_review_items WHERE care_plan_id='{plan}' AND status='open'"
        )
        == "0"
    )


def test_another_teams_owned_plan_cannot_be_retired_from(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)
    plan, _ = approved_plan(sql, TEAM)

    error = sql(retire(sql, plan, OTHER, OTHER_TEAM, [ITEM]), succeeds=False)

    assert "care plan unavailable" in error
    assert sql(f"SELECT is_active FROM medications WHERE id='{MEDICATION}'") == "t"


def test_retirement_needs_a_reason(sql):
    plan = unowned_with_two_candidates(sql)

    assert "reason is required" in sql(
        retire(sql, plan, THIRD, THIRD_TEAM, [ITEM], reason=" "), succeeds=False
    )


# ── Audit and grants ───────────────────────────────────────────────────────────────────────


def test_ownership_trail_is_append_only_for_every_role(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    new_plan(sql, TEAM)

    for statement in (
        "UPDATE care_plan_ownership_events SET event_type='x'",
        "DELETE FROM care_plan_ownership_events",
        "TRUNCATE care_plan_ownership_events",
    ):
        assert "append-only" in sql(statement, succeeds=False)
    for role in ("service_role", "authenticated", "anon"):
        error = sql(
            f"SET ROLE {role}; UPDATE care_plan_ownership_events SET event_type='x';",
            succeeds=False,
        )
        assert "permission denied" in error


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_browser_roles_cannot_touch_the_new_tables_or_functions(sql, role):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    for table in (
        "care_plans",
        "care_plan_ownership_events",
        "care_plan_review_items",
        "care_plan_item_retirements",
    ):
        assert "permission denied" in sql(
            f"SET ROLE {role}; SELECT count(*) FROM {table};", succeeds=False
        )
    for call in (
        f"public.adopt_care_plan('{TEAM}','{OTHER}','{TEAM}','x')",
        "private.ensure_care_plan('" + TEAM + "')",
        f"public.request_care_plan_generation_for_plan('{TEAM}', now())",
    ):
        assert "permission denied" in sql(f"SET ROLE {role}; SELECT {call};", succeeds=False)


def test_clinician_direct_reads_of_plan_rows_follow_the_owning_link(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)
    mine, _ = approved_plan(sql, TEAM)
    sql(
        f"INSERT INTO care_plan_versions(patient_id,care_plan_id,version_number,status) VALUES('{PATIENT}','{new_plan(sql, OTHER_TEAM)}',1,'draft');"
    )

    def visible(clinician):
        return sql(f"""SET ROLE authenticated; SET request.jwt.claim.sub='{clinician}';
          SELECT count(*) FROM care_plan_versions;""").splitlines()[-1]

    # Each clinician reads their own plan's versions and nobody else's, though both are
    # assigned to the same patient.
    assert visible(CLINICIAN) == "1"
    assert visible(OTHER) == "1"
    assert (
        sql(f"""SET ROLE authenticated; SET request.jwt.claim.sub='{OTHER}';
      SELECT count(*) FROM care_plan_items;""").splitlines()[-1]
        == "0"
    )
    assert mine
