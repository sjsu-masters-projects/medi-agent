"""Care-handoff summary storage contract in a disposable PostgreSQL 16 (089, CON-001).

A summary belongs to one care-team link; versions and events are append-only; export needs
the approved current version; concurrent writers cannot double-approve or silently overwrite.
Opt-in: ``CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER=1``. Synthetic data only.
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

pytest_plugins = ["tests.integration.care_team_plan_harness"]

pytestmark = [
    pytest.mark.timeout(600),
    pytest.mark.skipif(
        os.environ.get("CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER") != "1",
        reason="explicit opt-in disposable Docker PostgreSQL contract check",
    ),
]

SECTIONS = json.dumps(
    [
        {
            "key": "shared_core",
            "title": "Shared record",
            "status": "available",
            "items": [
                {
                    "id": "medications-1",
                    "text": "Medication: Lisinopril",
                    "source": {"kind": "record", "table": "medications", "id": "1", "label": "x"},
                }
            ],
        }
    ]
)
DENIED = "handoff summary unavailable"


def two_teams(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    link(sql, OTHER_TEAM, OTHER, OTHER_CLINIC)


def create_sql(summary, actor=CLINICIAN, team=TEAM, patient=PATIENT, title="Handoff") -> str:
    return (
        "SET ROLE service_role; SELECT public.create_care_handoff_summary("
        f"'{actor}','{patient}','{team}','{summary}','{title}','colleague','Dr. Rivera',"
        f"$s${SECTIONS}$s$::jsonb, now());"
    )


def made(sql) -> str:
    two_teams(sql)
    summary = str(uuid4())
    sql(create_sql(summary))
    return summary


def save_sql(summary, expected, narrative="n", notes="m", actor=CLINICIAN, sections=False) -> str:
    extra = f",p_sections=>$s${SECTIONS}$s$::jsonb,p_built_at=>now()" if sections else ""
    return (
        "SET ROLE service_role; SELECT public.save_care_handoff_version("
        f"p_actor_id=>'{actor}',p_summary_id=>'{summary}',p_expected_version=>{expected},"
        f"p_narrative=>'{narrative}',p_notes=>'{notes}'{extra});"
    )


def approve_sql(summary, version, actor=CLINICIAN) -> str:
    return (
        "SET ROLE service_role; SELECT public.approve_care_handoff_summary("
        f"'{actor}','{summary}',{version});"
    )


def export_sql(summary, version, fmt="fhir", actor=CLINICIAN) -> str:
    return (
        "SET ROLE service_role; SELECT public.record_care_handoff_export("
        f"'{actor}','{summary}',{version},'{fmt}');"
    )


def read_sql(summary, actor=CLINICIAN, version="NULL") -> str:
    return (
        "SET ROLE service_role; SELECT public.read_care_handoff_summary("
        f"'{actor}','{summary}',{version});"
    )


def events(sql, summary) -> list[str]:
    out = sql(
        f"SELECT event_type || coalesce(':' || export_format, '') "
        f"FROM public.care_handoff_summary_events WHERE summary_id='{summary}' "
        "ORDER BY created_at, id;"
    )
    return out.splitlines()


def test_create_then_read_returns_the_version_history_and_audit(sql) -> None:
    summary = made(sql)
    data = json.loads(sql(read_sql(summary)).splitlines()[-1])
    assert data["status"] == "draft" and data["current_version"] == 1
    assert data["version"]["sections"][0]["key"] == "shared_core"
    assert [v["version"] for v in data["versions"]] == [1]
    assert events(sql, summary) == ["created"]


def test_creating_twice_with_the_same_id_is_a_replay_not_a_duplicate(sql) -> None:
    summary = made(sql)
    replay = json.loads(sql(create_sql(summary)).splitlines()[-1])
    assert replay["replayed"] is True
    assert sql(f"SELECT count(*) FROM care_handoff_summaries WHERE id='{summary}';") == "1"
    assert events(sql, summary) == ["created"]
    # Another clinician cannot take over the id.
    stolen = sql(create_sql(summary, actor=OTHER, team=OTHER_TEAM), succeeds=False)
    assert DENIED in stolen


@pytest.mark.parametrize("who", [OTHER, THIRD])
def test_a_clinician_without_this_link_reads_and_writes_nothing(sql, who) -> None:
    summary = made(sql)
    for statement in (
        read_sql(summary, who),
        save_sql(summary, 1, actor=who),
        approve_sql(summary, 1, who),
        export_sql(summary, 1, actor=who),
    ):
        assert DENIED in sql(statement, succeeds=False)
    listed = sql(
        f"SET ROLE service_role; SELECT public.list_care_handoff_summaries('{OTHER}','{PATIENT}');"
    ).splitlines()[-1]
    assert listed == "[]"
    assert events(sql, summary) == ["created"]


def test_a_summary_cannot_be_created_for_a_link_or_patient_the_actor_lacks(sql) -> None:
    two_teams(sql)
    assert DENIED in sql(create_sql(uuid4(), actor=CLINICIAN, team=OTHER_TEAM), succeeds=False)
    assert DENIED in sql(create_sql(uuid4(), patient=SECOND_PATIENT), succeeds=False)
    assert DENIED in sql(create_sql(uuid4(), actor=THIRD), succeeds=False)
    assert sql("SELECT count(*) FROM care_handoff_summaries;") == "0"


def test_a_link_that_ended_loses_the_summary(sql) -> None:
    summary = made(sql)
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{TEAM}';")
    assert DENIED in sql(read_sql(summary), succeeds=False)
    assert DENIED in sql(approve_sql(summary, 1), succeeds=False)


def test_saves_are_optimistic_versioned_and_a_no_change_save_is_a_no_op(sql) -> None:
    summary = made(sql)
    saved = json.loads(sql(save_sql(summary, 1)).splitlines()[-1])
    assert saved["changed"] is True and saved["current_version"] == 2
    again = json.loads(sql(save_sql(summary, 2)).splitlines()[-1])
    assert again["changed"] is False and again["current_version"] == 2
    stale = sql(save_sql(summary, 1, narrative="other"), succeeds=False)
    assert "HANDOFF_VERSION_CONFLICT" in stale
    assert (
        sql(f"SELECT count(*) FROM care_handoff_summary_versions WHERE summary_id='{summary}';")
        == "2"
    )
    assert events(sql, summary) == ["created", "edited"]
    # Sections carry forward; a refresh stores a new snapshot and is audited as such.
    carried = json.loads(sql(read_sql(summary)).splitlines()[-1])
    assert carried["version"]["sections"][0]["key"] == "shared_core"
    sql(save_sql(summary, 2, narrative="refreshed", sections=True))
    assert events(sql, summary)[-1] == "refreshed"


def test_approval_is_idempotent_and_refuses_a_stale_version(sql) -> None:
    summary = made(sql)
    first = json.loads(sql(approve_sql(summary, 1)).splitlines()[-1])
    assert first["status"] == "approved" and first["changed"] is True
    second = json.loads(sql(approve_sql(summary, 1)).splitlines()[-1])
    assert second["changed"] is False
    assert events(sql, summary) == ["created", "approved"]
    sql(save_sql(summary, 1, narrative="edit after approval"))
    assert "HANDOFF_VERSION_CONFLICT" in sql(approve_sql(summary, 1), succeeds=False)


def test_editing_after_approval_returns_the_summary_to_draft_and_blocks_export(sql) -> None:
    summary = made(sql)
    sql(approve_sql(summary, 1))
    sql(save_sql(summary, 1, narrative="changed my mind"))
    state = sql(
        "SELECT status || ':' || coalesce(approved_version::text,'-') "
        f"FROM care_handoff_summaries WHERE id='{summary}';"
    )
    assert state == "draft:-"
    assert "HANDOFF_NOT_APPROVED" in sql(export_sql(summary, 2), succeeds=False)
    assert "HANDOFF_NOT_APPROVED" in sql(export_sql(summary, 1), succeeds=False)
    assert "export" not in "".join(events(sql, summary))


def test_only_the_approved_current_version_exports_and_every_export_is_audited(sql) -> None:
    summary = made(sql)
    assert "HANDOFF_NOT_APPROVED" in sql(export_sql(summary, 1), succeeds=False)
    sql(approve_sql(summary, 1))
    assert "unsupported export format" in sql(export_sql(summary, 1, "pdf"), succeeds=False)
    exported = json.loads(sql(export_sql(summary, 1, "fhir")).splitlines()[-1])
    assert exported["version"]["version"] == 1 and exported["status"] == "approved"
    sql(export_sql(summary, 1, "print"))
    assert events(sql, summary) == ["created", "approved", "exported:fhir", "exported:print"]


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE care_handoff_summary_versions SET notes='x'",
        "DELETE FROM care_handoff_summary_versions",
        "TRUNCATE care_handoff_summary_versions",
        "UPDATE care_handoff_summary_events SET actor_id=actor_id",
        "DELETE FROM care_handoff_summary_events",
        "TRUNCATE care_handoff_summary_events",
    ],
)
def test_versions_and_events_are_append_only_for_every_role(sql, statement) -> None:
    made(sql)
    # Once shares reference versions (096), the foreign key refuses a truncate first.
    refused = sql(statement, succeeds=False)
    assert "append-only" in refused or "cannot truncate a table referenced" in refused


def test_a_patients_erasure_removes_their_summaries_but_keeps_the_event_trail(sql) -> None:
    summary = made(sql)
    sql(f"DELETE FROM patients WHERE id='{PATIENT}';")
    assert sql("SELECT count(*) FROM care_handoff_summaries;") == "0"
    assert sql("SELECT count(*) FROM care_handoff_summary_versions;") == "0"
    assert events(sql, summary) == ["created"]


def test_browser_roles_reach_nothing(sql) -> None:
    summary = made(sql)
    for role in ("anon", "authenticated"):
        for table in (
            "care_handoff_summaries",
            "care_handoff_summary_versions",
            "care_handoff_summary_events",
        ):
            assert "permission denied" in sql(
                f"SET ROLE {role}; SELECT * FROM {table};", succeeds=False
            )
        for statement in (read_sql(summary), approve_sql(summary, 1), create_sql(uuid4())):
            blocked = statement.replace("SET ROLE service_role", f"SET ROLE {role}")
            assert "permission denied" in sql(blocked, succeeds=False)
    assert (
        sql(
            "SELECT bool_and(relrowsecurity) FROM pg_class WHERE relname LIKE 'care_handoff_summar%' "
            "AND relkind='r';"
        )
        == "t"
    )


def test_the_per_patient_bound_holds(sql) -> None:
    two_teams(sql)
    sql(
        "SET ROLE service_role; DO $$ BEGIN FOR i IN 1..50 LOOP PERFORM "
        f"public.create_care_handoff_summary('{CLINICIAN}','{PATIENT}','{TEAM}',gen_random_uuid(),"
        f"'t','colleague',NULL,$s${SECTIONS}$s$::jsonb,now()); END LOOP; END $$;"
    )
    assert "too many handoff summaries" in sql(create_sql(uuid4()), succeeds=False)


def test_two_concurrent_saves_of_the_same_version_cannot_both_win(sql) -> None:
    summary = made(sql)
    first = sql.start(
        "BEGIN;" + save_sql(summary, 1, narrative="a") + "SELECT pg_sleep(1.5); COMMIT;", "first"
    )
    import time

    time.sleep(0.5)
    second = sql.start(save_sql(summary, 1, narrative="b"), "second")
    codes = sorted([finish(first)[0], finish(second)[0]])
    assert codes == [0, 3] or codes == [0, 1]
    assert sql(f"SELECT current_version FROM care_handoff_summaries WHERE id='{summary}';") == "2"
    assert events(sql, summary) == ["created", "edited"]


def test_two_concurrent_approvals_record_one_approval(sql) -> None:
    summary = made(sql)
    first = sql.start("BEGIN;" + approve_sql(summary, 1) + "SELECT pg_sleep(1.5); COMMIT;", "first")
    import time

    time.sleep(0.5)
    second = sql.start(approve_sql(summary, 1), "second")
    assert finish(first)[0] == 0 and finish(second)[0] == 0
    assert events(sql, summary) == ["created", "approved"]
