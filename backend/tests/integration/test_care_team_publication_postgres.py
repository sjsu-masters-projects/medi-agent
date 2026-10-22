"""Cross-plan checks and atomic publication in a disposable PostgreSQL 16 (migration 085).

Publishing one care team's plan never changes another's activities. Duplicates, conflicting
instructions and stop-versus-continue block until the clinician who owns the draft resolves
them; an acknowledgement is bound to both instructions; retries are idempotent; and a patient's
publications are serialized. Opt-in: ``CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER=1``.
Synthetic data only.
"""

from __future__ import annotations

import json
import os
import time
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
from tests.integration.test_care_team_records_postgres import document, fact

pytest_plugins = ["tests.integration.care_team_plan_harness"]

pytestmark = [
    # The first test builds the template databases for the module.
    pytest.mark.timeout(600),
    pytest.mark.skipif(
        os.environ.get("CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER") != "1",
        reason="explicit opt-in disposable Docker PostgreSQL contract check",
    ),
]


BLOCKED = "resolve each cross-plan conflict before publication"  # raised with SQLSTATE CP001


def teams(sql, third=False):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)
    if third:
        link(sql, THIRD_TEAM, THIRD, CLINIC)


def draft(sql, team, clinician, *, items, number=1):
    """A draft of the team's plan whose items are publishable (evidence, both languages)."""
    plan = sql(f"SET ROLE service_role; SELECT private.ensure_care_plan('{team}');").splitlines()[
        -1
    ]
    version = sql(f"""INSERT INTO care_plan_versions(patient_id,care_plan_id,version_number,status)
      VALUES('{PATIENT}','{plan}',{number},'draft') RETURNING id;""").splitlines()[0]
    ids = [add_item(sql, version, team, clinician, **spec) for spec in items]
    return plan, version, ids


def med(
    name="Ibuprofen",
    dosage="200 mg",
    frequency="daily",
    instructions="Take one tablet with food",
    route="oral",
    **extra,
):
    return {
        "name": name,
        "dosage": dosage,
        "frequency": frequency,
        "instructions": instructions,
        "route": route,
        **extra,
    }


def add_item(
    sql,
    version,
    team,
    clinician,
    *,
    name=None,
    dosage="200 mg",
    frequency="daily",
    instructions="Take one tablet with food",
    route="oral",
    category="medication",
    title=None,
    stop=False,
    removed=False,
    target=None,
    decision="create",
    ingredient=None,
) -> str:
    doc = document(sql, by=clinician, role="clinician", team=team)
    source = fact(sql, doc, value=json.dumps({"name": name or title or "x"}))
    item = str(uuid4())
    title = title or (f"{name} {dosage}" if category == "medication" else "Walk")
    medication = {}
    if category == "medication":
        medication = {
            "name": name,
            "dosage": dosage,
            "frequency": frequency,
            "route": route,
            "decision": decision,
        }
        if target:
            medication["target_id"] = target
        if ingredient:
            medication["ingredient_rxcui"] = ingredient
    conflict = {"kind": "medication_stop_source"} if stop else {}
    wording = {
        "en-US": {"title": title, "instructions": instructions, "frequency": frequency},
        "es-MX": {
            "title": f"{title} (es)",
            "instructions": f"{instructions} (es)",
            "frequency": f"{frequency} (es)",
        },
    }
    sql(f"""INSERT INTO care_plan_items(id,plan_version_id,source_fact_id,category,title,
        instructions,frequency,medication,conflict,source_locale,wording,wording_origin,
        wording_verified,confidence_score,is_removed)
      VALUES('{item}','{version}','{source}','{category}',$t${title}$t$,$t${instructions}$t$,
        $t${frequency}$t$,$m${json.dumps(medication)}$m$,$c${json.dumps(conflict)}$c$,'en-US',
        $w${json.dumps(wording)}$w$,'{{}}',true,0.99,{str(removed).lower()});""")
    return item


def publish(version, actor, *, key=None, excluded=(), note="Reviewed and approved"):
    ids = ",".join(f"'{i}'" for i in excluded)
    key = key or str(uuid4())
    return (
        f"SET ROLE service_role; SELECT public.publish_care_plan_version("
        f"'{version}','{actor}','{note}','{key}',ARRAY[{ids}]::uuid[]);"
    )


def published(sql, version, actor, **kw) -> dict:
    return json.loads(sql(publish(version, actor, **kw)).splitlines()[-1])


def review(sql, version, actor) -> dict:
    return json.loads(
        sql(
            f"SET ROLE service_role; SELECT public.care_plan_cross_plan_review('{version}','{actor}');"
        ).splitlines()[-1]
    )


def resolve(version, actor, fingerprint, resolution, reason="Both prescribers agreed on this"):
    return (
        f"SET ROLE service_role; SELECT public.record_cross_plan_resolution("
        f"'{version}','{actor}','{fingerprint}','{resolution}',$r${reason}$r$);"
    )


def active_meds(sql) -> list[tuple[str, ...]]:
    rows = sql(
        "SELECT name||'|'||dosage||'|'||coalesce(prescribed_by_care_team_id::text,'-') FROM medications WHERE is_active ORDER BY name, dosage, prescribed_by_care_team_id"
    )
    return [tuple(line.split("|")) for line in rows.splitlines() if line]


def conflicts_of(error: str) -> list[dict]:
    assert "resolve each cross-plan conflict" in error, error
    detail = next(line for line in error.splitlines() if line.startswith("DETAIL:"))
    return json.loads(detail.removeprefix("DETAIL:").strip())


# ── Publication of one plan ────────────────────────────────────────────────────────────────


def test_publication_projects_for_the_owning_team_and_records_the_lineage(sql):
    teams(sql)
    plan, version, (item,) = draft(
        sql, TEAM, CLINICIAN, items=[{"name": "Lisinopril", "dosage": "10 mg"}]
    )

    result = published(sql, version, CLINICIAN)

    assert result["status"] == "approved" and result["care_plan_id"] == plan
    assert result["interaction_coverage"] == "not_checked" and result["replayed"] is False
    assert active_meds(sql) == [("Lisinopril", "10 mg", TEAM)]
    assert (
        sql(f"SELECT status||approved_by FROM care_plan_versions WHERE id='{version}'")
        == f"approved{CLINICIAN}"
    )
    assert sql("SELECT recorded_by->>'specialty' FROM medications") == "Cardiology"
    assert sql(f"SELECT projection_type FROM care_plan_items WHERE id='{item}'") == "medication"


def test_publishing_one_plan_never_deactivates_another_plans_activities(sql):
    teams(sql)
    _, mine, _ = draft(
        sql,
        TEAM,
        CLINICIAN,
        items=[
            {"name": "Lisinopril", "dosage": "10 mg"},
            {"category": "movement", "instructions": "Walk 20 minutes", "frequency": "daily"},
        ],
    )
    _, theirs, _ = draft(sql, OTHER_TEAM, OTHER, items=[{"name": "Naproxen", "dosage": "500 mg"}])
    published(sql, mine, CLINICIAN)
    published(sql, theirs, OTHER)
    before = sql(
        "SELECT string_agg(id::text||is_active::text, ',' ORDER BY id) FROM (SELECT id,is_active FROM medications UNION ALL SELECT id,is_active FROM obligations) x"
    )

    # The cardiology team publishes a revised plan: its previous version is superseded and
    # only its own projections are replaced; orthopaedics is untouched.
    _, revised, _ = draft(
        sql,
        TEAM,
        CLINICIAN,
        number=2,
        items=[
            {
                "name": "Lisinopril",
                "dosage": "20 mg",
                "target": sql("SELECT id FROM medications WHERE name='Lisinopril'"),
                "decision": "update",
            }
        ],
    )
    published(sql, revised, CLINICIAN)

    assert ("Naproxen", "500 mg", OTHER_TEAM) in active_meds(sql)
    assert sql(f"SELECT status FROM care_plan_versions WHERE id='{theirs}'") == "approved"
    assert sql("SELECT dosage FROM medications WHERE name='Lisinopril'") == "20 mg"
    assert before != sql(
        "SELECT string_agg(id::text||is_active::text, ',' ORDER BY id) FROM (SELECT id,is_active FROM medications UNION ALL SELECT id,is_active FROM obligations) x"
    )
    # The walk activity belonged to the superseded cardiology version and is replaced there only.
    assert sql(f"SELECT status FROM care_plan_versions WHERE id='{mine}'") == "superseded"


def test_same_clinician_at_two_clinics_publishes_two_plans_attributed_to_each_link(sql):
    seed_people(sql, second_clinic_for_clinician=True)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, CLINICIAN, OTHER_CLINIC)
    _, one, _ = draft(sql, TEAM, CLINICIAN, items=[{"name": "Lisinopril", "dosage": "10 mg"}])
    _, two, _ = draft(sql, OTHER_TEAM, CLINICIAN, items=[{"name": "Warfarin", "dosage": "5 mg"}])

    published(sql, one, CLINICIAN)
    published(sql, two, CLINICIAN)

    assert active_meds(sql) == [("Lisinopril", "10 mg", TEAM), ("Warfarin", "5 mg", OTHER_TEAM)]
    assert (
        sql("SELECT recorded_by->>'clinic_name' FROM medications WHERE name='Warfarin'")
        == "Birch Clinic"
    )


def test_only_the_owner_of_a_plan_may_publish_it(sql):
    teams(sql, third=True)
    _, version, _ = draft(sql, TEAM, CLINICIAN, items=[{"name": "Lisinopril"}])

    for actor in (OTHER, THIRD):  # assigned to the patient, but not this plan's owner
        assert "care plan unavailable" in sql(publish(version, actor), succeeds=False)
    assert sql(f"SELECT status FROM care_plan_versions WHERE id='{version}'") == "draft"
    assert active_meds(sql) == []


def test_a_revoked_link_cannot_publish_and_a_plan_without_an_owner_cannot_either(sql):
    teams(sql)
    _, version, _ = draft(sql, TEAM, CLINICIAN, items=[{"name": "Lisinopril"}])
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{TEAM}';")

    assert "care plan unavailable" in sql(publish(version, CLINICIAN), succeeds=False)
    assert active_meds(sql) == []


def test_the_pre_existing_approval_entry_point_publishes_through_the_same_checks(sql):
    teams(sql)
    _, version, _ = draft(sql, TEAM, CLINICIAN, items=[{"name": "Lisinopril"}])

    result = sql(
        f"SET ROLE service_role; SELECT public.approve_care_plan_version('{version}','{CLINICIAN}','ok');"
    )

    assert '"status": "approved"' in result
    assert active_meds(sql) == [("Lisinopril", "200 mg", TEAM)]


# ── Cross-plan conflicts ───────────────────────────────────────────────────────────────────


def approved_ibuprofen(sql, **spec):
    _, version, (item,) = draft(sql, OTHER_TEAM, OTHER, items=[{"name": "Ibuprofen", **spec}])
    published(sql, version, OTHER)
    return version, item


@pytest.mark.parametrize(
    "mine,other,kind,basis",
    [
        ({"name": "Ibuprofen"}, {}, "duplicate_medication", "recorded_name"),
        ({"name": "IBUPROFEN  "}, {}, "duplicate_medication", "recorded_name"),
        ({"name": "Ibuprofen", "dosage": "400 mg"}, {}, "regimen_difference", "recorded_name"),
        (
            {"name": "Ibuprofen", "frequency": "twice daily"},
            {},
            "regimen_difference",
            "recorded_name",
        ),
        (
            {"name": "Ibuprofen", "instructions": "Take two tablets"},
            {},
            "regimen_difference",
            "recorded_name",
        ),
        (
            {"name": "Advil", "ingredient": "5640"},
            {"ingredient": "5640"},
            "duplicate_medication",
            "recorded_ingredient",
        ),
    ],
)
def test_duplicates_and_conflicting_instructions_block_publication(sql, mine, other, kind, basis):
    teams(sql)
    approved_ibuprofen(sql, **other)
    _, version, _ = draft(sql, TEAM, CLINICIAN, items=[mine])

    error = sql(publish(version, CLINICIAN), succeeds=False)

    (blocker,) = conflicts_of(error)
    assert blocker["kind"] == kind
    assert sql(f"SELECT status FROM care_plan_versions WHERE id='{version}'") == "draft"
    assert active_meds(sql) == [("Ibuprofen", other.get("dosage", "200 mg"), OTHER_TEAM)]
    shown = review(sql, version, CLINICIAN)["conflicts"][0]
    assert shown["identity_basis"] == basis and shown["severity"] == "blocker"


def test_different_medications_do_not_conflict_and_brand_names_are_not_assumed_equal(sql):
    teams(sql)
    approved_ibuprofen(sql)
    _, version, _ = draft(sql, TEAM, CLINICIAN, items=[{"name": "Advil"}, {"name": "Lisinopril"}])

    assert review(sql, version, CLINICIAN)["conflicts"] == []
    assert published(sql, version, CLINICIAN)["status"] == "approved"


def test_a_draft_that_stops_a_medicine_another_plan_keeps_is_blocked(sql):
    teams(sql)
    approved_ibuprofen(sql)
    _, stops, _ = draft(
        sql,
        TEAM,
        CLINICIAN,
        items=[{"name": "Ibuprofen", "stop": True, "removed": True}, {"name": "Lisinopril"}],
    )

    (blocker,) = conflicts_of(sql(publish(stops, CLINICIAN), succeeds=False))

    assert blocker["kind"] == "stop_continue"
    assert active_meds(sql) == [("Ibuprofen", "200 mg", OTHER_TEAM)]


def test_a_draft_that_continues_a_medicine_another_plan_has_stopped_is_blocked(sql):
    teams(sql)
    _, other_stop, _ = draft(
        sql,
        OTHER_TEAM,
        OTHER,
        items=[{"name": "Warfarin", "stop": True, "removed": True}, {"name": "Aspirin"}],
    )
    published(sql, other_stop, OTHER)
    _, continues, _ = draft(sql, TEAM, CLINICIAN, items=[{"name": "Warfarin"}])

    (blocker,) = conflicts_of(sql(publish(continues, CLINICIAN), succeeds=False))

    assert blocker["kind"] == "stop_continue"


def test_a_conflict_with_a_shared_list_entry_with_no_plan_blocks_a_second_copy(sql):
    teams(sql)
    sql(f"""INSERT INTO medications(patient_id,name,dosage,frequency,route,instructions,is_active,prescribed_by_care_team_id)
      VALUES('{PATIENT}','Ibuprofen','200 mg','daily','oral','Take one tablet with food',true,'{OTHER_TEAM}');""")
    _, version, _ = draft(sql, TEAM, CLINICIAN, items=[{"name": "Ibuprofen"}])

    (blocker,) = conflicts_of(sql(publish(version, CLINICIAN), succeeds=False))

    assert blocker["kind"] == "duplicate_medication"
    shown = review(sql, version, CLINICIAN)["conflicts"][0]
    assert shown["shared_list_entry_id"] and shown["theirs"]["shared_list"] is True


def test_updating_the_shared_list_entry_is_adoption_not_conflict(sql):
    teams(sql)
    sql(f"""INSERT INTO medications(id,patient_id,name,dosage,frequency,route,is_active)
      VALUES('00000000-0000-0000-0000-0000000000d1','{PATIENT}','Ibuprofen','200 mg','daily','oral',true);""")
    _, version, _ = draft(
        sql,
        TEAM,
        CLINICIAN,
        items=[
            {
                "name": "Ibuprofen",
                "target": "00000000-0000-0000-0000-0000000000d1",
                "decision": "update",
            }
        ],
    )

    assert review(sql, version, CLINICIAN)["conflicts"] == []
    assert published(sql, version, CLINICIAN)["status"] == "approved"


def test_a_plan_cannot_update_a_medication_another_plans_activity_owns(sql):
    teams(sql)
    approved_ibuprofen(sql)
    owned = sql("SELECT id FROM medications WHERE name='Ibuprofen'")
    _, version, _ = draft(
        sql,
        TEAM,
        CLINICIAN,
        items=[{"name": "Ibuprofen", "target": owned, "decision": "update", "dosage": "800 mg"}],
    )
    (blocker,) = conflicts_of(sql(publish(version, CLINICIAN), succeeds=False))
    sql(resolve(version, CLINICIAN, blocker["fingerprint"], "keep_both"))

    error = sql(publish(version, CLINICIAN), succeeds=False)

    assert "belongs to another care plan" in error
    assert sql(f"SELECT dosage FROM medications WHERE id='{owned}'") == "200 mg"


def test_non_medication_overlap_warns_without_blocking_and_reveals_no_wording(sql):
    teams(sql)
    _, theirs, _ = draft(
        sql,
        OTHER_TEAM,
        OTHER,
        items=[{"category": "movement", "instructions": "Walk 20 minutes", "frequency": "daily"}],
    )
    published(sql, theirs, OTHER)
    _, mine, _ = draft(
        sql,
        TEAM,
        CLINICIAN,
        items=[{"category": "movement", "instructions": "walk  20 MINUTES", "frequency": "daily"}],
    )

    shown = review(sql, mine, CLINICIAN)["conflicts"][0]
    assert shown["severity"] == "warning" and shown["kind"] == "schedule_overlap"
    assert "Walk" not in json.dumps(shown["theirs"]) and shown["theirs"] == {"category": "movement"}
    result = published(sql, mine, CLINICIAN)
    assert result["status"] == "approved" and result["warnings"][0]["kind"] == "schedule_overlap"


def test_the_review_shows_both_instructions_and_only_plan_metadata(sql):
    teams(sql)
    approved_ibuprofen(sql, dosage="400 mg")
    _, version, _ = draft(sql, TEAM, CLINICIAN, items=[{"name": "Ibuprofen", "dosage": "200 mg"}])

    data = review(sql, version, CLINICIAN)
    conflict = data["conflicts"][0]

    assert data["interaction_coverage"] == "not_checked"
    assert conflict["ours"]["dosage"] == "200 mg" and conflict["theirs"]["dosage"] == "400 mg"
    other = conflict["other_plan"]
    assert set(other) == {
        "care_plan_id",
        "ownership_state",
        "specialty",
        "clinician_name",
        "clinic_name",
        "approved_at",
    }
    assert other["clinician_name"] == "Omar Reyes" and other["clinic_name"] == "Birch Clinic"
    assert "source" not in json.dumps(conflict).lower().replace("source_", "")
    # Only the plan's own owner may ask.
    assert "care plan unavailable" in sql(
        f"SET ROLE service_role; SELECT public.care_plan_cross_plan_review('{version}','{OTHER}');",
        succeeds=False,
    )


# ── Resolutions ────────────────────────────────────────────────────────────────────────────


def blocked_pair(sql):
    teams(sql, third=True)
    approved_ibuprofen(sql)
    _, version, (item,) = draft(
        sql, TEAM, CLINICIAN, items=[{"name": "Ibuprofen"}, {"name": "Lisinopril"}][:1]
    )
    (blocker,) = conflicts_of(sql(publish(version, CLINICIAN), succeeds=False))
    return version, item, blocker["fingerprint"]


def test_keep_both_with_a_reason_publishes_both_and_tells_the_other_team(sql):
    version, item, fingerprint = blocked_pair(sql)

    sql(resolve(version, CLINICIAN, fingerprint, "keep_both"))
    result = published(sql, version, CLINICIAN)

    assert result["acknowledged_fingerprints"] == [fingerprint]
    assert active_meds(sql) == [("Ibuprofen", "200 mg", TEAM), ("Ibuprofen", "200 mg", OTHER_TEAM)]
    items = sql(f"""SELECT kind||':'||request_note FROM care_plan_review_items
      WHERE conflict_fingerprint='{fingerprint}' AND target_care_team_id='{OTHER_TEAM}'""")
    assert items == "conflict_acknowledged:Both prescribers agreed on this"
    # The patient's other activities are exactly as they were.
    assert (
        sql(f"SELECT is_active FROM medications WHERE prescribed_by_care_team_id='{OTHER_TEAM}'")
        == "t"
    )


def test_keep_both_needs_a_written_reason(sql):
    version, _, fingerprint = blocked_pair(sql)

    assert "written reason" in sql(
        resolve(version, CLINICIAN, fingerprint, "keep_both", reason="   "), succeeds=False
    )
    assert "written reason" in sql(
        resolve(version, CLINICIAN, fingerprint, "ask_other_team", reason=""), succeeds=False
    )
    assert active_meds(sql) == [("Ibuprofen", "200 mg", OTHER_TEAM)]


def test_an_acknowledgement_goes_stale_when_either_instruction_changes(sql):
    version, item, fingerprint = blocked_pair(sql)
    sql(resolve(version, CLINICIAN, fingerprint, "keep_both"))

    # This plan edits its own instruction ...
    sql(
        f"UPDATE care_plan_items SET instructions=$i$Take one tablet with a full meal$i$, wording=jsonb_set(jsonb_set(wording,'{{en-US,instructions}}','\"Take one tablet with a full meal\"'),'{{es-MX,instructions}}','\"x (es)\"') WHERE id='{item}';"
    )
    assert BLOCKED in sql(publish(version, CLINICIAN), succeeds=False)
    assert "has changed" in sql(
        resolve(version, CLINICIAN, fingerprint, "keep_both"), succeeds=False
    )

    # ... and a fresh review gives a new fingerprint that needs its own reason.
    fresh = review(sql, version, CLINICIAN)["conflicts"][0]["fingerprint"]
    assert fresh != fingerprint
    assert review(sql, version, CLINICIAN)["conflicts"][0]["acknowledged"] is False


def test_an_acknowledgement_goes_stale_when_the_other_teams_instruction_changes(sql):
    version, _, fingerprint = blocked_pair(sql)
    sql(resolve(version, CLINICIAN, fingerprint, "keep_both"))

    # The other team publishes a revised dose; the comparison and fingerprint change.
    other_item = sql("SELECT id FROM medications WHERE name='Ibuprofen'")
    _, revised, _ = draft(
        sql,
        OTHER_TEAM,
        OTHER,
        number=2,
        items=[
            {"name": "Ibuprofen", "dosage": "400 mg", "target": other_item, "decision": "update"}
        ],
    )
    published(sql, revised, OTHER)

    assert BLOCKED in sql(publish(version, CLINICIAN), succeeds=False)
    assert review(sql, version, CLINICIAN)["conflicts"][0]["acknowledged"] is False


def test_asking_the_other_team_creates_a_review_item_and_stays_blocked(sql):
    version, _, fingerprint = blocked_pair(sql)

    result = json.loads(
        sql(
            resolve(
                version,
                CLINICIAN,
                fingerprint,
                "ask_other_team",
                reason="Is this combination intended?",
            )
        ).splitlines()[-1]
    )

    assert result["review_items"] == 1
    item = sql(f"""SELECT id||'|'||kind||'|'||(summary->'theirs'->>'dosage')||'|'||(summary->'ours'->>'name')
      FROM care_plan_review_items WHERE target_care_team_id='{OTHER_TEAM}' AND conflict_fingerprint='{fingerprint}'""")
    item_id, kind, dose, name = item.split("|")
    assert kind == "cross_plan_conflict" and name == "Ibuprofen"
    assert BLOCKED in sql(publish(version, CLINICIAN), succeeds=False)  # still blocked
    # A repeat is a no-op.
    again = json.loads(
        sql(
            resolve(
                version,
                CLINICIAN,
                fingerprint,
                "ask_other_team",
                reason="Is this combination intended?",
            )
        ).splitlines()[-1]
    )
    assert again["replayed"] is True

    # The other team replies: the asker hears back, and the blocker is still theirs to resolve.
    reply = sql(
        f"SET ROLE service_role; SELECT public.reply_care_plan_review_item('{item_id}','{OTHER}',$r$Yes, intended$r$);"
    )
    assert '"status": "resolved"' in reply
    assert (
        sql(
            f"SELECT request_note FROM care_plan_review_items WHERE kind='conflict_reply' AND target_care_team_id='{TEAM}'"
        )
        == "Yes, intended"
    )
    assert BLOCKED in sql(publish(version, CLINICIAN), succeeds=False)


def test_only_the_addressed_team_can_reply_and_a_third_team_is_not_told(sql):
    version, _, fingerprint = blocked_pair(sql)
    sql(resolve(version, CLINICIAN, fingerprint, "ask_other_team", reason="Is this intended?"))
    item_id = sql(
        f"SELECT id FROM care_plan_review_items WHERE target_care_team_id='{OTHER_TEAM}' AND conflict_fingerprint='{fingerprint}'"
    )

    for actor in (THIRD, CLINICIAN):
        assert "review item unavailable" in sql(
            f"SET ROLE service_role; SELECT public.reply_care_plan_review_item('{item_id}','{actor}','x');",
            succeeds=False,
        )
    assert (
        sql(
            f"SELECT count(*) FROM care_plan_review_items WHERE target_care_team_id='{THIRD_TEAM}' AND conflict_fingerprint='{fingerprint}'"
        )
        == "0"
    )


def test_publish_without_the_item_carries_it_forward_pending_and_tells_the_other_team(sql):
    teams(sql, third=True)
    approved_ibuprofen(sql)
    _, version, (clash, fine) = draft(
        sql,
        TEAM,
        CLINICIAN,
        items=[{"name": "Ibuprofen"}, {"name": "Lisinopril", "dosage": "10 mg"}],
    )

    result = published(sql, version, CLINICIAN, excluded=[clash])

    assert result["published_item_count"] == 1 and result["excluded_item_ids"] == [clash]
    assert active_meds(sql) == [("Ibuprofen", "200 mg", OTHER_TEAM), ("Lisinopril", "10 mg", TEAM)]
    next_draft = result["next_draft_version_id"]
    assert (
        sql(f"SELECT status||version_number FROM care_plan_versions WHERE id='{next_draft}'")
        == "draft2"
    )
    carried = sql(
        f"SELECT title||'|'||is_removed::text||'|'||coalesce(blocker_reason,'-') FROM care_plan_items WHERE plan_version_id='{next_draft}'"
    )
    assert carried == "Ibuprofen 200 mg|false|-"
    assert sql(f"SELECT is_removed FROM care_plan_items WHERE id='{clash}'") == "t"
    assert (
        sql(
            f"SELECT count(*) FROM care_plan_review_items WHERE kind='conflict_published_without' AND target_care_team_id='{OTHER_TEAM}'"
        )
        == "1"
    )
    assert (
        sql(
            f"SELECT count(*) FROM care_plan_review_items WHERE kind='conflict_published_without' AND target_care_team_id='{THIRD_TEAM}'"
        )
        == "0"
    )
    # The carried item still blocks the next publication until it is resolved.
    assert BLOCKED in sql(publish(next_draft, CLINICIAN), succeeds=False)


def test_nothing_to_publish_is_not_a_publication(sql):
    teams(sql)
    _, version, (only,) = draft(sql, TEAM, CLINICIAN, items=[{"name": "Lisinopril"}])

    assert "needs evidence-backed items" in sql(
        publish(version, CLINICIAN, excluded=[only]), succeeds=False
    )
    assert sql(f"SELECT status FROM care_plan_versions WHERE id='{version}'") == "draft"
    assert sql(f"SELECT is_removed FROM care_plan_items WHERE id='{only}'") == "f"


def test_exclusions_must_be_items_of_this_draft(sql):
    teams(sql)
    _, version, _ = draft(sql, TEAM, CLINICIAN, items=[{"name": "Lisinopril"}])

    assert "choose items of this draft" in sql(
        publish(version, CLINICIAN, excluded=[str(uuid4())]), succeeds=False
    )


# ── Idempotency and concurrency ────────────────────────────────────────────────────────────


def test_a_retry_with_the_same_key_returns_the_same_result_and_changes_nothing(sql):
    teams(sql)
    _, version, _ = draft(sql, TEAM, CLINICIAN, items=[{"name": "Lisinopril"}])
    key = str(uuid4())

    first = published(sql, version, CLINICIAN, key=key)
    again = published(sql, version, CLINICIAN, key=key)

    assert again["replayed"] is True
    assert {k: v for k, v in again.items() if k != "replayed"} == {
        k: v for k, v in first.items() if k != "replayed"
    }
    assert sql("SELECT count(*) FROM medications") == "1"
    assert (
        sql(
            f"SELECT count(*) FROM care_plan_audit_events WHERE plan_version_id='{version}' AND event_type='approved_and_published'"
        )
        == "1"
    )


def test_a_key_cannot_be_reused_for_a_different_request(sql):
    teams(sql)
    _, version, (a, b) = draft(
        sql, TEAM, CLINICIAN, items=[{"name": "Lisinopril"}, {"name": "Atorvastatin"}]
    )
    key = str(uuid4())
    published(sql, version, CLINICIAN, key=key, excluded=[b])

    assert "different request" in sql(publish(version, CLINICIAN, key=key), succeeds=False)
    assert "different request" in sql(
        publish(version, CLINICIAN, key=key, excluded=[a]), succeeds=False
    )
    assert "care plan unavailable" in sql(
        publish(version, OTHER, key=key, excluded=[b]), succeeds=False
    )
    assert sql("SELECT count(*) FROM care_plan_publications") == "1"


def test_a_published_version_cannot_be_published_again_under_a_new_key(sql):
    teams(sql)
    _, version, _ = draft(sql, TEAM, CLINICIAN, items=[{"name": "Lisinopril"}])
    published(sql, version, CLINICIAN)

    assert "not eligible for approval" in sql(publish(version, CLINICIAN), succeeds=False)
    assert sql("SELECT count(*) FROM medications") == "1"


def test_concurrent_publication_by_two_plans_is_serialized_and_rechecked(sql):
    # Two teams each hold a draft for the same medicine. Run together, one publishes and the
    # other must see the first's committed state and be blocked.
    teams(sql)
    _, first, _ = draft(sql, TEAM, CLINICIAN, items=[{"name": "Ibuprofen"}])
    _, second, _ = draft(sql, OTHER_TEAM, OTHER, items=[{"name": "Ibuprofen"}])
    slow = (
        "BEGIN; "
        + publish(first, CLINICIAN).replace("SET ROLE service_role; ", "SET ROLE service_role; ")
        + " SELECT pg_sleep(1.5); COMMIT;"
    )
    a = sql.start(slow, "publish-a")
    time.sleep(0.5)
    b = sql.start(publish(second, OTHER), "publish-b")

    result_a, result_b = finish(a), finish(b)

    assert result_a[0] == 0, result_a[2]
    assert result_b[0] != 0 and BLOCKED in result_b[2]
    assert active_meds(sql) == [("Ibuprofen", "200 mg", TEAM)]
    assert sql(f"SELECT status FROM care_plan_versions WHERE id='{second}'") == "draft"


def test_concurrent_retries_of_one_publication_publish_once(sql):
    teams(sql)
    _, version, _ = draft(sql, TEAM, CLINICIAN, items=[{"name": "Lisinopril"}])
    key = str(uuid4())
    processes = [sql.start(publish(version, CLINICIAN, key=key), f"retry-{n}") for n in range(3)]

    results = [finish(p) for p in processes]

    assert all(r[0] == 0 for r in results), results
    assert sorted(json.loads(r[1].splitlines()[-1])["replayed"] for r in results) == [
        False,
        True,
        True,
    ]
    assert sql("SELECT count(*) FROM medications") == "1"


# ── Conversations: another team's plan detail does not travel through a thread ─────────────


def opened_thread(sql, recipient):
    payload = json.dumps({"recipient_id": recipient})
    return json.loads(
        sql(
            f"SET ROLE service_role; SELECT care_conversation_operation('{PATIENT}','patient','open','{payload}');"
        ).splitlines()[-1]
    )["id"]


def attach(thread, item):
    payload = json.dumps(
        {
            "conversation_id": thread,
            "body": "About this",
            "client_message_id": str(uuid4()),
            "care_plan_item_id": item,
        }
    )
    return f"SET ROLE service_role; SELECT public.care_conversation_activity_operation('{PATIENT}','patient','send','{payload}');"


def test_a_patient_attaches_only_an_activity_of_the_conversations_own_team(sql):
    teams(sql)
    _, mine, (my_item,) = draft(sql, TEAM, CLINICIAN, items=[{"name": "Lisinopril"}])
    _, theirs, (their_item,) = draft(sql, OTHER_TEAM, OTHER, items=[{"name": "Naproxen"}])
    published(sql, mine, CLINICIAN)
    published(sql, theirs, OTHER)
    thread = opened_thread(sql, CLINICIAN)

    refused = sql(attach(thread, their_item), succeeds=False)
    accepted = json.loads(sql(attach(thread, my_item)).splitlines()[-1])

    assert "Activity context unavailable" in refused
    assert accepted["activity_context"]["title"] == "Lisinopril 200 mg"
    assert sql("SELECT count(*) FROM care_conversation_messages") == "1"


def test_activity_detail_on_an_old_message_is_hidden_from_the_wrong_team(sql):
    teams(sql)
    _, theirs, (their_item,) = draft(sql, OTHER_TEAM, OTHER, items=[{"name": "Naproxen"}])
    published(sql, theirs, OTHER)
    thread = opened_thread(sql, CLINICIAN)
    # Written before ownership existed: attach by hand, as a legacy row would be.
    message = sql(f"""INSERT INTO care_conversation_messages(conversation_id,sender_id,sender_role,
      sender_name,body,client_message_id,care_plan_item_id,created_at)
      VALUES('{thread}','{PATIENT}','patient','Synthetic Patient','hello','{uuid4()}','{their_item}',now()) RETURNING id;""").splitlines()[
        0
    ]

    rendered = json.loads(sql(f"SELECT private.care_conversation_message('{message}');"))

    assert rendered["activity_context"] == {"unavailable": True}
    assert "Naproxen" not in json.dumps(rendered)


def test_a_clinician_cannot_open_another_teams_activity_for_review(sql):
    teams(sql)
    _, theirs, (their_item,) = draft(sql, OTHER_TEAM, OTHER, items=[{"name": "Naproxen"}])
    published(sql, theirs, OTHER)
    thread = opened_thread(sql, CLINICIAN)
    message = sql(f"""INSERT INTO care_conversation_messages(conversation_id,sender_id,sender_role,
      sender_name,body,client_message_id,care_plan_item_id,created_at)
      VALUES('{thread}','{PATIENT}','patient','Synthetic Patient','hello','{uuid4()}','{their_item}',now()) RETURNING id;""").splitlines()[
        0
    ]
    payload = json.dumps({"conversation_id": thread, "message_id": message})

    error = sql(
        f"SET ROLE service_role; SELECT public.care_conversation_activity_operation('{CLINICIAN}','clinician','review','{payload}');",
        succeeds=False,
    )

    assert "Activity context unavailable" in error
    assert sql("SELECT count(*) FROM care_plan_versions WHERE status='draft'") == "0"


def test_review_opens_a_draft_on_the_plan_that_owns_the_activity(sql):
    teams(sql)
    my_plan, mine, (my_item,) = draft(sql, TEAM, CLINICIAN, items=[{"name": "Lisinopril"}])
    _, theirs, _ = draft(sql, OTHER_TEAM, OTHER, items=[{"name": "Naproxen"}])
    published(sql, mine, CLINICIAN)
    published(sql, theirs, OTHER)
    thread = opened_thread(sql, CLINICIAN)
    message = json.loads(sql(attach(thread, my_item)).splitlines()[-1])["id"]
    payload = json.dumps({"conversation_id": thread, "message_id": message})

    opened = json.loads(
        sql(
            f"SET ROLE service_role; SELECT public.care_conversation_activity_operation('{CLINICIAN}','clinician','review','{payload}');"
        ).splitlines()[-1]
    )

    assert (
        sql(f"SELECT care_plan_id FROM care_plan_versions WHERE id='{opened['plan_id']}'")
        == my_plan
    )
    assert (
        sql(f"SELECT version_number FROM care_plan_versions WHERE id='{opened['plan_id']}'") == "2"
    )
    assert sql("SELECT count(*) FROM care_plan_versions WHERE status='draft'") == "1"
