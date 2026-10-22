"""Sharing an approved care-handoff summary with a named colleague (096, CON-001).

The author of an APPROVED version shares that exact version with a clinician who holds an
active link to the patient, or who is an active member of the author's clinic. The recipient
sees only the shared content; revoking removes access immediately; the notification is
captured exactly once. Opt-in: ``CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER=1``. Synthetic data only.
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
    finish,
    link,
    seed_people,
)
from tests.integration.test_care_handoff_summaries_postgres import (
    create_sql,
    events,
    save_sql,
)

pytest_plugins = ["tests.integration.care_team_plan_harness"]

pytestmark = [
    pytest.mark.timeout(600),
    pytest.mark.skipif(
        os.environ.get("CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER") != "1",
        reason="explicit opt-in disposable Docker PostgreSQL contract check",
    ),
]

FOURTH = "00000000-0000-0000-0000-000000000006"  # member of the OTHER clinic, never linked
DENIED = "handoff summary unavailable"
NOT_ALLOWED = "HANDOFF_RECIPIENT_NOT_ALLOWED"
NOT_APPROVED = "HANDOFF_NOT_APPROVED"
SERVICE = "SET ROLE service_role; "


def last(out: str):
    return json.loads(out.splitlines()[-1])


def world(sql) -> str:
    """Author CLINICIAN (Cedar Grove, linked); OTHER linked at Birch; THIRD a Cedar member
    with no link; FOURTH a Birch member with no link. One approved version 1."""
    seed_people(sql)
    sql(
        f"INSERT INTO auth.users VALUES ('{FOURTH}');"
        "INSERT INTO clinicians(id,email,first_name,last_name,specialty,clinic_name,clinic_id) "
        f"VALUES ('{FOURTH}','c4@synthetic.invalid','Farah','Quinn','Neurology','Birch Clinic',"
        f"'{OTHER_CLINIC}');"
    )
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)
    summary = str(uuid4())
    sql(create_sql(summary))
    sql(f"{SERVICE}SELECT public.approve_care_handoff_summary('{CLINICIAN}','{summary}',1);")
    return summary


def share_sql(summary, recipient, version=1, actor=CLINICIAN) -> str:
    return (
        f"{SERVICE}SELECT public.share_care_handoff_summary("
        f"'{actor}','{summary}',{version},'{recipient}');"
    )


def revoke_sql(share, actor=CLINICIAN) -> str:
    return f"{SERVICE}SELECT public.revoke_care_handoff_share('{actor}','{share}');"


def read_shared_sql(share, actor) -> str:
    return f"{SERVICE}SELECT public.read_shared_care_handoff('{actor}','{share}');"


def shared_export_sql(share, actor, fmt="print") -> str:
    return f"{SERVICE}SELECT public.record_shared_care_handoff_export('{actor}','{share}','{fmt}');"


def mine_sql(actor) -> str:
    return f"{SERVICE}SELECT public.list_care_handoff_shared_with_me('{actor}');"


def candidates(sql, summary, actor=CLINICIAN, query="NULL"):
    q = query if query == "NULL" else f"'{query}'"
    return last(
        sql(
            f"{SERVICE}SELECT public.list_care_handoff_share_candidates('{actor}','{summary}',{q});"
        )
    )


def shared(sql, summary, recipient, version=1) -> str:
    return last(sql(share_sql(summary, recipient, version)))["id"]


def centre(sql, actor, action="list"):
    out = sql(
        f"{SERVICE}SELECT public.notification_centre_operation("
        f"'{actor}','clinician','{action}','{{}}'::jsonb);"
    )
    return last(out)


def handoff_items(sql, actor):
    return [i for i in centre(sql, actor)["items"] if i["event_type"] == "handoff_shared"]


def share_events(sql, summary) -> list[str]:
    return [e for e in events(sql, summary) if e not in {"created", "approved"}]


# ── who may receive ──────────────────────────────────────────────────────────────────────────


def test_the_picker_offers_linked_clinicians_and_the_authors_clinic_only(sql) -> None:
    summary = world(sql)
    rows = {r["clinician_id"]: r for r in candidates(sql, summary)}
    assert set(rows) == {OTHER, THIRD}  # not the author, not an unlinked outsider (FOURTH)
    assert rows[OTHER]["bases"] == ["care_team"]
    assert rows[OTHER]["clinics"] == [{"id": OTHER_CLINIC, "name": "Birch Clinic"}]
    assert rows[OTHER]["specialty"] == "Orthopaedics"
    assert rows[THIRD]["bases"] == ["clinic_member"]
    assert rows[THIRD]["clinics"] == [{"id": CLINIC, "name": "Cedar Grove"}]
    only = candidates(sql, summary, query="tess")
    assert [r["clinician_id"] for r in only] == [THIRD]
    assert [r["clinician_id"] for r in candidates(sql, summary, query="birch")] == [OTHER]
    assert candidates(sql, summary, query="%") == []


def test_a_clinician_in_both_groups_is_listed_once_with_both_reasons(sql) -> None:
    summary = world(sql)
    link(sql, "00000000-0000-0000-0000-000000000024", THIRD, CLINIC)
    rows = [r for r in candidates(sql, summary) if r["clinician_id"] == THIRD]
    assert len(rows) == 1 and rows[0]["bases"] == ["care_team", "clinic_member"]


def test_only_the_author_sees_candidates_or_shares(sql) -> None:
    summary = world(sql)
    for who in (OTHER, THIRD, FOURTH):
        assert DENIED in sql(
            f"{SERVICE}SELECT public.list_care_handoff_share_candidates('{who}','{summary}',NULL);",
            succeeds=False,
        )
        assert DENIED in sql(
            f"{SERVICE}SELECT public.list_care_handoff_shares('{who}','{summary}');",
            succeeds=False,
        )


# ── sharing ──────────────────────────────────────────────────────────────────────────────────


def test_a_draft_or_edited_summary_cannot_be_shared(sql) -> None:
    summary = world(sql)
    sql(save_sql(summary, 1, narrative="edited after approval"))
    assert NOT_APPROVED in sql(share_sql(summary, THIRD, 1), succeeds=False)
    assert NOT_APPROVED in sql(share_sql(summary, THIRD, 2), succeeds=False)
    assert sql("SELECT count(*) FROM care_handoff_shares;") == "0"


def test_the_recipient_must_be_allowed_and_only_the_author_may_share(sql) -> None:
    summary = world(sql)
    assert NOT_ALLOWED in sql(share_sql(summary, FOURTH), succeeds=False)
    assert NOT_ALLOWED in sql(share_sql(summary, CLINICIAN), succeeds=False)
    assert NOT_ALLOWED in sql(share_sql(summary, str(uuid4())), succeeds=False)
    # A linked colleague (not the author) cannot re-share it, nor can an outsider.
    for who in (OTHER, THIRD, FOURTH):
        assert DENIED in sql(share_sql(summary, THIRD, actor=who), succeeds=False)
    assert sql("SELECT count(*) FROM care_handoff_shares;") == "0"
    assert share_events(sql, summary) == []


def test_sharing_is_idempotent_and_notifies_exactly_once(sql) -> None:
    summary = world(sql)
    first = last(sql(share_sql(summary, THIRD)))
    again = last(sql(share_sql(summary, THIRD)))
    assert first["replayed"] is False and again["replayed"] is True
    assert first["id"] == again["id"]
    assert sql("SELECT count(*) FROM care_handoff_shares;") == "1"
    assert share_events(sql, summary) == ["shared"]
    assert sql("SELECT count(*) FROM notification_events WHERE event_type='handoff_shared';") == "1"
    assert sql("SELECT count(*) FROM notification_pending_deliveries;") == "1"
    assert len(handoff_items(sql, THIRD)) == 1
    assert len(handoff_items(sql, THIRD)) == 1  # opening the centre again adds nothing
    assert sql("SELECT count(*) FROM notification_receipts;") == "1"


def test_two_concurrent_shares_to_one_recipient_make_one_share_and_one_notification(sql) -> None:
    summary = world(sql)
    first = sql.start("BEGIN;" + share_sql(summary, THIRD) + "SELECT pg_sleep(1.5); COMMIT;", "a")
    time.sleep(0.5)
    second = sql.start(share_sql(summary, THIRD), "b")
    assert finish(first)[0] == 0 and finish(second)[0] == 0
    assert sql("SELECT count(*) FROM care_handoff_shares;") == "1"
    assert share_events(sql, summary) == ["shared"]
    assert sql("SELECT count(*) FROM notification_events WHERE event_type='handoff_shared';") == "1"


def test_an_edit_in_flight_wins_over_a_share_that_waits_behind_it(sql) -> None:
    summary = world(sql)
    edit = sql.start(
        "BEGIN;" + save_sql(summary, 1, narrative="late edit") + "SELECT pg_sleep(1.5); COMMIT;",
        "edit",
    )
    time.sleep(0.5)
    share = sql.start(share_sql(summary, THIRD), "share")
    assert finish(edit)[0] == 0
    code, _out, err = finish(share)
    assert code != 0 and NOT_APPROVED in err
    assert sql("SELECT count(*) FROM care_handoff_shares;") == "0"


def test_the_number_of_active_shares_per_summary_is_bounded(sql) -> None:
    summary = world(sql)
    sql(f"""
      INSERT INTO auth.users SELECT gen_random_uuid() FROM generate_series(1,50);
      INSERT INTO clinicians(id,email,first_name,last_name,specialty,clinic_name,clinic_id)
        SELECT u.id, 'bulk' || row_number() OVER () || '@synthetic.invalid', 'Bulk',
          'Member' || row_number() OVER (), 'General', 'Cedar Grove', '{CLINIC}'
        FROM auth.users u WHERE u.id NOT IN ('{CLINICIAN}','{OTHER}','{THIRD}','{FOURTH}',
          '{PATIENT}','00000000-0000-0000-0000-000000000005');
    """)
    ids = sql(
        "SELECT clinician_id FROM private.handoff_share_candidates('" + summary + "') "
        f"WHERE clinician_id NOT IN ('{OTHER}','{THIRD}') ORDER BY 1;"
    ).splitlines()
    assert len(ids) >= 48
    for recipient in ids[:48]:
        shared(sql, summary, recipient)
    shared(sql, summary, OTHER)
    shared(sql, summary, THIRD)
    assert "too many shares" in sql(share_sql(summary, ids[48]), succeeds=False)


# ── what the recipient sees ──────────────────────────────────────────────────────────────────


def test_an_unlinked_recipient_reads_only_the_shared_content(sql) -> None:
    summary = world(sql)
    sql(save_sql(summary, 1, narrative="n", notes="for you"))
    sql(f"{SERVICE}SELECT public.approve_care_handoff_summary('{CLINICIAN}','{summary}',2);")
    share = shared(sql, summary, THIRD, 2)
    data = last(sql(read_shared_sql(share, THIRD)))
    assert data["version"] == 2 and data["narrative"] == "n" and data["notes"] == "for you"
    assert data["sections"][0]["key"] == "shared_core"
    assert data["patient_name"] == "Synthetic Patient"
    assert data["author_name"] == "Elena Park" and data["author_clinic"] == "Cedar Grove"
    assert data["approved_by_name"] == "Elena Park" and data["newer"] is None
    # No team, event trail, version list or record link comes with it.
    assert not {"care_team_id", "events", "versions", "recipient_id"} & set(data)
    # ... and sharing gave THIRD no access to the patient or to the summary itself.
    assert sql(f"SELECT private.clinician_patient_links('{THIRD}','{PATIENT}');") == "{}"
    for statement in (
        f"public.list_care_handoff_summaries('{THIRD}','{PATIENT}')",
        f"public.read_care_handoff_summary('{THIRD}','{summary}',NULL)",
        f"public.approve_care_handoff_summary('{THIRD}','{summary}',2)",
        f"public.record_care_handoff_export('{THIRD}','{summary}',2,'print')",
        f"public.save_care_handoff_version(p_actor_id=>'{THIRD}',p_summary_id=>'{summary}',"
        "p_expected_version=>2,p_narrative=>'x',p_notes=>'y')",
    ):
        assert "unavailable" in sql(f"{SERVICE}SELECT {statement};", succeeds=False)


def test_a_share_is_readable_by_its_recipient_alone(sql) -> None:
    summary = world(sql)
    share = shared(sql, summary, THIRD)
    for who in (CLINICIAN, OTHER, FOURTH):
        assert DENIED in sql(read_shared_sql(share, who), succeeds=False)
        assert DENIED in sql(shared_export_sql(share, who), succeeds=False)
    assert DENIED in sql(read_shared_sql(str(uuid4()), THIRD), succeeds=False)
    assert last(sql(mine_sql(OTHER))) == []
    assert [r["share_id"] for r in last(sql(mine_sql(THIRD)))] == [share]


def test_the_share_stays_on_its_version_and_a_newer_one_shows_only_if_shared(sql) -> None:
    summary = world(sql)
    v1 = shared(sql, summary, THIRD, 1)
    shared(sql, summary, OTHER, 1)
    sql(save_sql(summary, 1, narrative="second version"))
    sql(f"{SERVICE}SELECT public.approve_care_handoff_summary('{CLINICIAN}','{summary}',2);")
    # The edit did not touch the share: THIRD still reads version 1, unchanged.
    old = last(sql(read_shared_sql(v1, THIRD)))
    assert old["version"] == 1 and old["narrative"] is None and old["newer"] is None
    v2 = shared(sql, summary, THIRD, 2)
    old = last(sql(read_shared_sql(v1, THIRD)))
    assert old["newer"] == {"share_id": v2, "version": 2}
    assert last(sql(read_shared_sql(v2, THIRD)))["narrative"] == "second version"
    # OTHER was never given version 2: nothing says a newer version exists.
    listed = last(sql(mine_sql(OTHER)))
    assert [(r["version"], r["newer"]) for r in listed] == [(1, None)]
    assert {r["version"]: r["newer"] for r in last(sql(mine_sql(THIRD)))} == {
        1: {"share_id": v2, "version": 2},
        2: None,
    }


def test_the_recipient_sees_the_title_and_approval_as_they_were_shared(sql) -> None:
    summary = world(sql)
    share = shared(sql, summary, THIRD)
    sql(
        save_sql(summary, 1, narrative="x").replace(
            "p_notes=>'m'", "p_notes=>'m',p_title=>'Renamed'"
        )
    )
    data = last(sql(read_shared_sql(share, THIRD)))
    assert data["title"] == "Handoff"  # as at sharing time
    assert data["approved_at"] is not None


# ── revoking ─────────────────────────────────────────────────────────────────────────────────


def test_revoking_removes_access_and_the_notification_at_once(sql) -> None:
    summary = world(sql)
    share = shared(sql, summary, THIRD)
    assert len(handoff_items(sql, THIRD)) == 1
    assert centre(sql, THIRD, "summary")["unread_count"] == 1
    assert DENIED in sql(revoke_sql(share, THIRD), succeeds=False)  # not the author's to revoke
    assert DENIED in sql(revoke_sql(share, OTHER), succeeds=False)
    revoked = last(sql(revoke_sql(share)))
    assert revoked["replayed"] is False and revoked["revoked_at"] is not None
    assert last(sql(revoke_sql(share)))["replayed"] is True
    assert DENIED in sql(read_shared_sql(share, THIRD), succeeds=False)
    assert DENIED in sql(shared_export_sql(share, THIRD), succeeds=False)
    assert last(sql(mine_sql(THIRD))) == []
    assert handoff_items(sql, THIRD) == []
    assert centre(sql, THIRD, "summary")["unread_count"] == 0
    assert share_events(sql, summary) == ["shared", "share_revoked"]


def test_sharing_again_after_a_revoke_is_a_new_grant_with_its_own_notification(sql) -> None:
    summary = world(sql)
    share = shared(sql, summary, THIRD)
    assert len(handoff_items(sql, THIRD)) == 1
    sql(revoke_sql(share))
    again = last(sql(share_sql(summary, THIRD)))
    assert again["id"] == share and again["replayed"] is False and again["revoked_at"] is None
    items = handoff_items(sql, THIRD)
    assert len(items) == 1 and items[0]["metadata"]["generation"] == 2
    assert sql("SELECT count(*) FROM notification_events WHERE event_type='handoff_shared';") == "2"
    assert last(sql(read_shared_sql(share, THIRD)))["version"] == 1
    assert share_events(sql, summary) == ["shared", "share_revoked", "shared", "shared_viewed"]


def test_leaving_the_clinic_or_the_link_ending_ends_access(sql) -> None:
    summary = world(sql)
    via_clinic = shared(sql, summary, THIRD)
    via_link = shared(sql, summary, OTHER)
    sql(f"UPDATE clinic_memberships SET status='inactive' WHERE clinician_id='{THIRD}';")
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{OTHER_TEAM}';")
    assert DENIED in sql(read_shared_sql(via_clinic, THIRD), succeeds=False)
    assert DENIED in sql(read_shared_sql(via_link, OTHER), succeeds=False)
    assert handoff_items(sql, THIRD) == [] and handoff_items(sql, OTHER) == []
    # The share itself was not revoked; access returns only if eligibility does.
    sql(f"UPDATE clinic_memberships SET status='active' WHERE clinician_id='{THIRD}';")
    assert last(sql(read_shared_sql(via_clinic, THIRD)))["version"] == 1


# ── audit ────────────────────────────────────────────────────────────────────────────────────


def test_opening_and_exporting_a_shared_summary_are_audited(sql) -> None:
    summary = world(sql)
    share = shared(sql, summary, THIRD)
    sql(read_shared_sql(share, THIRD))
    sql(read_shared_sql(share, THIRD))  # a refresh inside ten minutes adds no second entry
    assert "unsupported export format" in sql(
        shared_export_sql(share, THIRD, "pdf"), succeeds=False
    )
    sql(shared_export_sql(share, THIRD, "print"))
    sql(shared_export_sql(share, THIRD, "fhir"))
    assert share_events(sql, summary) == [
        "shared",
        "shared_viewed",
        "shared_exported:print",
        "shared_exported:fhir",
    ]
    actors = sql(
        "SELECT DISTINCT actor_id FROM care_handoff_summary_events "
        "WHERE event_type LIKE 'shared_%';"
    )
    assert actors == THIRD


def test_the_authors_audit_names_each_recipient(sql) -> None:
    summary = world(sql)
    share = shared(sql, summary, OTHER)
    sql(revoke_sql(share))
    data = last(
        sql(f"{SERVICE}SELECT public.read_care_handoff_summary('{CLINICIAN}','{summary}',NULL);")
    )
    named = [
        (e["event_type"], e["recipient_name"])
        for e in data["events"]
        if e["event_type"].startswith("share")
    ]
    assert sorted(named) == [("share_revoked", "Omar Reyes"), ("shared", "Omar Reyes")]


# ── notification centre ──────────────────────────────────────────────────────────────────────


def test_the_item_reaches_the_recipient_only_and_is_news_not_work(sql) -> None:
    summary = world(sql)
    share = shared(sql, summary, THIRD)
    for who in (CLINICIAN, OTHER, FOURTH):
        assert handoff_items(sql, who) == []
    item = handoff_items(sql, THIRD)[0]
    assert item["source_id"] == share and item["actionable"] is False
    assert item["metadata"]["actor_name"] == "Elena Park" and item["metadata"]["version"] == 1
    assert item["patient_name"] == "Synthetic Patient"
    # The patient's other items stay out of an unlinked recipient's centre.
    assert {i["event_type"] for i in centre(sql, THIRD)["items"]} == {"handoff_shared"}
    assert centre(sql, THIRD, "action_items")["items"] == []


def test_a_linked_recipient_gets_the_item_too_without_new_record_access(sql) -> None:
    summary = world(sql)
    shared(sql, summary, OTHER)
    assert len(handoff_items(sql, OTHER)) == 1
    assert DENIED in sql(
        f"{SERVICE}SELECT public.read_care_handoff_summary('{OTHER}','{summary}',NULL);",
        succeeds=False,
    )


# ── storage guards ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE care_handoff_shares SET recipient_id=author_id",
        "UPDATE care_handoff_shares SET version=1, title='other'",
        "UPDATE care_handoff_shares SET generation=generation+1",
        "DELETE FROM care_handoff_shares",
        "TRUNCATE care_handoff_shares",
    ],
)
def test_a_share_changes_only_by_revoke_or_reshare(sql, statement) -> None:
    summary = world(sql)
    shared(sql, summary, THIRD)
    assert "change only by revoke" in sql(statement, succeeds=False)


def test_erasing_the_patient_or_a_recipient_removes_shares_but_keeps_the_trail(sql) -> None:
    summary = world(sql)
    shared(sql, summary, THIRD)
    shared(sql, summary, OTHER)
    sql(f"DELETE FROM auth.users WHERE id='{OTHER}';")
    assert sql("SELECT count(*) FROM care_handoff_shares;") == "1"
    sql(f"DELETE FROM patients WHERE id='{PATIENT}';")
    assert sql("SELECT count(*) FROM care_handoff_shares;") == "0"
    assert share_events(sql, summary) == ["shared", "shared"]


def test_browser_roles_reach_nothing(sql) -> None:
    summary = world(sql)
    share = shared(sql, summary, THIRD)
    for role in ("anon", "authenticated"):
        assert "permission denied" in sql(
            f"SET ROLE {role}; SELECT * FROM care_handoff_shares;", succeeds=False
        )
        for statement in (
            share_sql(summary, THIRD),
            revoke_sql(share),
            read_shared_sql(share, THIRD),
            shared_export_sql(share, THIRD),
            mine_sql(THIRD),
            f"{SERVICE}SELECT public.list_care_handoff_share_candidates('{CLINICIAN}','{summary}',NULL);",
        ):
            assert "permission denied" in sql(
                statement.replace("SET ROLE service_role", f"SET ROLE {role}"), succeeds=False
            )
    assert sql("SELECT relrowsecurity FROM pg_class WHERE relname='care_handoff_shares';") == "t"


def test_the_ledger_helpers_keep_their_old_behaviour_for_every_other_source(sql) -> None:
    summary = world(sql)
    shared(sql, summary, THIRD)
    # An unlinked clinician is not addressable for ownership questions, whatever the source.
    assert (
        sql(
            f"SELECT private.notification_owner_sees('adherence_logs', gen_random_uuid(), 'x',"
            f"'{THIRD}', '{PATIENT}');"
        )
        == "f"
    )
    assert (
        sql(
            f"SELECT private.notification_owner_sees('adherence_logs', gen_random_uuid(), 'x',"
            f"'{CLINICIAN}', '{PATIENT}');"
        )
        == "t"
    )
    assert sql("SELECT private.notification_source('documents', gen_random_uuid()) IS NULL;") == "t"
    assert (
        sql(f"SELECT '{PATIENT}' = ANY (private.notification_scope('{CLINICIAN}','clinician'));")
        == "t"
    )
    assert (
        sql(f"SELECT '{PATIENT}' = ANY (private.notification_scope('{FOURTH}','clinician'));")
        == "f"
    )
