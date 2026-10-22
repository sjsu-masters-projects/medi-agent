"""Clinic-admin notification variant, conflict-reply resolution and SMART team column (092).

Opt-in: ``CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER=1``. Synthetic data only.
"""

from __future__ import annotations

import json
import os

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
from tests.integration.test_care_team_notifications_postgres import centre, items
from tests.integration.test_care_team_publication_postgres import (
    blocked_pair,
    publish,
    resolve,
)

pytest_plugins = ["tests.integration.care_team_plan_harness"]

pytestmark = [
    pytest.mark.timeout(600),
    pytest.mark.skipif(
        os.environ.get("CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER") != "1",
        reason="explicit opt-in disposable Docker PostgreSQL contract check",
    ),
]


def clinic_world(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)
    sql(
        f"UPDATE clinic_memberships SET role='admin' WHERE clinician_id='{THIRD}' AND clinic_id='{CLINIC}';"
    )
    assert (
        sql(
            f"SELECT role FROM clinic_memberships WHERE clinician_id='{THIRD}' AND clinic_id='{CLINIC}'"
        )
        == "admin"
    )


def clinic_item(sql, kind="unowned_plan") -> str:
    plan = sql(f"SET ROLE service_role; SELECT private.ensure_care_plan('{TEAM}');").splitlines()[
        -1
    ]
    return sql(f"""INSERT INTO care_plan_review_items(patient_id,care_plan_id,kind,target_clinic_id)
      VALUES('{PATIENT}','{plan}','{kind}','{CLINIC}') RETURNING id;""").splitlines()[0]


def test_a_clinic_item_reaches_only_that_clinics_admins_without_patient_detail(sql):
    clinic_world(sql)
    item = clinic_item(sql)

    mine = items(sql, THIRD, "care_plan_review")

    assert [row["source_id"] for row in mine] == [item]
    row = mine[0]
    assert (
        row["patient_id"] is None and row["patient_name"] == ""[:0] or row["patient_name"] is None
    )
    assert row["metadata"]["scope"] == "clinic" and row["metadata"]["clinic_id"] == CLINIC
    assert row["clinic_id"] == CLINIC and row["actionable"] is True
    assert "Synthetic" not in json.dumps(row)
    # A provider of the same clinic and an admin-less clinic see nothing.
    assert items(sql, CLINICIAN, "care_plan_review") == []
    assert items(sql, OTHER, "care_plan_review") == []
    # It counts as an action item for the admin, and the clinic filter honours the clinic.
    assert any(r["source_id"] == item for r in centre(sql, THIRD, "action_items")["items"])
    assert centre(sql, THIRD, "summary")["action_item_count"] >= 1
    assert items_with_clinic(sql, THIRD, CLINIC) == [item]
    assert items_with_clinic(sql, THIRD, OTHER_CLINIC) == []


def items_with_clinic(sql, actor, clinic):
    rows = centre(sql, actor, "list", {"clinic_id": clinic})["items"]
    return [r["source_id"] for r in rows if r["event_type"] == "care_plan_review"]


def test_a_clinic_item_stops_being_actionable_when_resolved_and_a_non_admin_cannot_open_it(sql):
    clinic_world(sql)
    item = clinic_item(sql)
    row = items(sql, THIRD, "care_plan_review")[0]

    assert (
        "unavailable" in centre(sql, CLINICIAN, "read", {"id": row["id"]}, succeeds=False).lower()
    )
    sql(
        f"UPDATE care_plan_review_items SET status='resolved', resolved_at=now() WHERE id='{item}';"
    )

    assert items(sql, THIRD, "care_plan_review")[0]["actionable"] is False
    assert not any(r["source_id"] == item for r in centre(sql, THIRD, "action_items")["items"])


def test_a_clinician_made_admin_later_is_caught_up_and_a_demoted_admin_loses_access(sql):
    clinic_world(sql)
    item = clinic_item(sql)
    assert items(sql, CLINICIAN, "care_plan_review") == []

    sql(
        f"UPDATE clinic_memberships SET role='admin' WHERE clinician_id='{CLINICIAN}' AND clinic_id='{CLINIC}';"
    )
    assert [r["source_id"] for r in items(sql, CLINICIAN, "care_plan_review")] == [item]

    sql(
        f"UPDATE clinic_memberships SET role='provider' WHERE clinician_id='{THIRD}' AND clinic_id='{CLINIC}';"
    )
    assert items(sql, THIRD, "care_plan_review") == []


def test_a_care_team_item_is_now_an_action_item(sql):
    clinic_world(sql)
    plan = sql(
        f"SET ROLE service_role; SELECT private.ensure_care_plan('{OTHER_TEAM}');"
    ).splitlines()[-1]
    item = sql(f"""INSERT INTO care_plan_review_items(patient_id,care_plan_id,kind,target_care_team_id)
      VALUES('{PATIENT}','{plan}','unowned_plan','{OTHER_TEAM}') RETURNING id;""").splitlines()[0]

    assert [r["source_id"] for r in centre(sql, OTHER, "action_items")["items"]] == [item]
    assert centre(sql, CLINICIAN, "action_items")["items"] == []


def resolve_reply(item, actor, action, reason=None):
    r = "NULL" if reason is None else f"$r${reason}$r$"
    return f"SET ROLE service_role; SELECT public.resolve_conflict_reply('{item}','{actor}','{action}',{r});"


def asked_and_answered(sql):
    version, _, fingerprint = blocked_pair(sql)
    sql(resolve(version, CLINICIAN, fingerprint, "ask_other_team", reason="Is this intended?"))
    asked = sql(
        f"SELECT id FROM care_plan_review_items WHERE target_care_team_id='{OTHER_TEAM}' AND conflict_fingerprint='{fingerprint}'"
    )
    sql(
        f"SET ROLE service_role; SELECT public.reply_care_plan_review_item('{asked}','{OTHER}',$r$Yes, intended$r$);"
    )
    reply = sql(
        f"SELECT id FROM care_plan_review_items WHERE kind='conflict_reply' AND target_care_team_id='{TEAM}'"
    )
    return version, fingerprint, reply


def test_accepting_a_reply_closes_it_and_reports_the_blocker_that_remains(sql):
    version, fingerprint, reply = asked_and_answered(sql)

    result = json.loads(sql(resolve_reply(reply, CLINICIAN, "accept")).splitlines()[-1])

    assert result["status"] == "resolved" and result["still_blocking"] is True
    assert result["replayed"] is False and result["draft_version_id"] == version
    assert (
        sql(f"SELECT status||resolved_by FROM care_plan_review_items WHERE id='{reply}'")
        == f"resolved{CLINICIAN}"
    )
    assert (
        sql(
            "SELECT count(*) FROM care_plan_audit_events WHERE event_type='conflict_reply_resolved'"
        )
        == "1"
    )
    # Idempotent: a repeat changes and audits nothing.
    again = json.loads(sql(resolve_reply(reply, CLINICIAN, "accept")).splitlines()[-1])
    assert again["replayed"] is True
    assert (
        sql(
            "SELECT count(*) FROM care_plan_audit_events WHERE event_type='conflict_reply_resolved'"
        )
        == "1"
    )
    # Accepting does not clear the blocker.
    assert "resolve each cross-plan conflict" in sql(publish(version, CLINICIAN), succeeds=False)


def test_keeping_both_with_a_reason_clears_the_blocker_and_closes_the_reply(sql):
    version, fingerprint, reply = asked_and_answered(sql)

    assert "written reason" in sql(
        resolve_reply(reply, CLINICIAN, "keep_both", "  "), succeeds=False
    )
    result = json.loads(
        sql(
            resolve_reply(reply, CLINICIAN, "keep_both", "Confirmed with the prescriber")
        ).splitlines()[-1]
    )

    assert result["still_blocking"] is False and result["status"] == "resolved"
    assert (
        sql(
            f"SELECT count(*) FROM care_plan_conflict_resolutions WHERE fingerprint='{fingerprint}' AND resolution='keep_both'"
        )
        == "1"
    )
    assert json.loads(sql(publish(version, CLINICIAN)).splitlines()[-1])["status"] == "approved"


def test_only_the_asking_clinician_can_resolve_a_conflict_reply_and_only_a_reply(sql):
    version, fingerprint, reply = asked_and_answered(sql)
    asked = sql("SELECT id FROM care_plan_review_items WHERE kind='cross_plan_conflict'")

    for actor in (OTHER, THIRD):
        assert "review item unavailable" in sql(
            resolve_reply(reply, actor, "accept"), succeeds=False
        )
    assert "review item unavailable" in sql(
        resolve_reply(asked, CLINICIAN, "accept"), succeeds=False
    )
    assert "unsupported action" in sql(resolve_reply(reply, CLINICIAN, "dismiss"), succeeds=False)
    assert sql(f"SELECT status FROM care_plan_review_items WHERE id='{reply}'") == "open"


def test_keep_both_on_a_conflict_that_changed_is_refused_as_stale(sql):
    version, fingerprint, reply = asked_and_answered(sql)
    sql(f"UPDATE care_plan_review_items SET conflict_fingerprint='{'0' * 64}' WHERE id='{reply}';")

    assert "has changed" in sql(
        resolve_reply(reply, CLINICIAN, "keep_both", "Reason"), succeeds=False
    )
    assert sql(f"SELECT status FROM care_plan_review_items WHERE id='{reply}'") == "open"


def test_the_smart_launch_session_records_its_team_and_stays_backend_only(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    sql(f"""INSERT INTO smart_launch_sessions(state_hash,pkce_verifier_ciphertext,issuer,
      authorization_endpoint,token_endpoint,clinician_id,patient_id,requested_scopes,nonce,
      expires_at,care_team_id) VALUES('h','c','https://i.example','https://a.example',
      'https://t.example','{CLINICIAN}','{PATIENT}','s','n',now()+interval '5 minutes','{TEAM}');""")
    assert sql("SELECT care_team_id FROM smart_launch_sessions") == TEAM
    sql(f"DELETE FROM care_teams WHERE id='{TEAM}';")
    assert sql("SELECT count(*) FROM smart_launch_sessions") == "0"
    assert (
        sql(
            "SELECT has_table_privilege('authenticated','public.smart_launch_sessions','SELECT')::text"
        )
        == "false"
    )
