"""Real action-table contracts under the complete ledger and hosted-style grants.

No remote database or clinical executor is involved. The upsert matches the
conflict-ignore operation asserted by the service's unit tests.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from tests.integration.care_team_plan_harness import (
    CLINIC,
    CLINICIAN,
    OTHER,
    PATIENT,
    TEAM,
    link,
    seed_people,
)

pytest_plugins = ["tests.integration.care_team_plan_harness"]
pytestmark = pytest.mark.skipif(
    os.environ.get("CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER") != "1",
    reason="explicit opt-in disposable PostgreSQL contract check",
)

TABLES = (
    "clinical_recommendations",
    "approval_decisions",
    "action_envelopes",
    "clinical_action_audit_records",
)


def seed(sql):
    seed_people(sql)
    link(sql, TEAM, CLINICIAN, CLINIC)
    rid = str(uuid4())
    sql(f"""SET ROLE service_role;
      INSERT INTO clinical_recommendations(id,patient_id,action_type,evidence,rationale,proposer_type,state)
      VALUES('{rid}','{PATIENT}','routine_message','[{{"source":"synthetic"}}]',
        'Synthetic evidence only','system','approved');
      INSERT INTO approval_decisions(recommendation_id,reviewer_id,decision,note)
      VALUES('{rid}','{CLINICIAN}','approve','Synthetic reviewed');
      INSERT INTO clinical_action_audit_records(recommendation_id,actor_id,event_type)
      VALUES('{rid}','{CLINICIAN}','approved');""")
    return rid


def envelope_sql(rid, key="synthetic-envelope-key"):
    return f"""SET ROLE service_role;
      INSERT INTO action_envelopes(recommendation_id,idempotency_key,state)
      VALUES('{rid}','{key}','approved')
      ON CONFLICT (recommendation_id,idempotency_key) DO NOTHING RETURNING id;"""


@pytest.mark.parametrize("table", TABLES)
def test_action_tables_keep_rls_enabled(sql, table):
    assert sql(f"SELECT relrowsecurity FROM pg_class WHERE oid='public.{table}'::regclass;") == "t"


@pytest.mark.parametrize("actor,count", [(CLINICIAN, "1"), (OTHER, "0"), (PATIENT, "0")])
def test_action_rows_are_readable_only_by_assigned_clinicians(sql, actor, count):
    rid = seed(sql)
    sql(envelope_sql(rid))
    for table in TABLES:
        assert (
            sql(
                f"SET request.jwt.claim.sub='{actor}'; SET ROLE authenticated; SELECT count(*) FROM {table};"
            )
            == count
        )


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_browser_roles_cannot_insert_actions_or_audit(sql, role):
    rid = seed(sql)
    statements = (
        f"INSERT INTO action_envelopes(recommendation_id,idempotency_key) VALUES('{rid}','synthetic-browser-key')",
        f"INSERT INTO clinical_action_audit_records(recommendation_id,event_type) VALUES('{rid}','forged')",
        f"INSERT INTO approval_decisions(recommendation_id,reviewer_id,decision,note) VALUES('{rid}','{CLINICIAN}','reject','forged')",
        f"INSERT INTO clinical_recommendations(patient_id,action_type,evidence,rationale,proposer_type) VALUES('{PATIENT}','routine_message','[{{}}]','forged','system')",
    )
    for statement in statements:
        error = sql(
            f"SET request.jwt.claim.sub='{CLINICIAN}'; SET ROLE {role}; {statement};",
            succeeds=False,
        )
        assert "row-level security" in error or "permission denied" in error
    assert sql("SELECT count(*) FROM action_envelopes;") == "0"
    assert sql("SELECT count(*) FROM clinical_action_audit_records;") == "1"


def test_assigned_browser_cannot_change_or_delete_saved_actions(sql):
    rid = seed(sql)
    sql(envelope_sql(rid))
    for statement in (
        "UPDATE clinical_recommendations SET state='executed' RETURNING id",
        "UPDATE action_envelopes SET outcome='{" + '"forged":true' + "}' RETURNING id",
        "UPDATE approval_decisions SET note='forged' RETURNING id",
        "UPDATE clinical_action_audit_records SET event_type='forged' RETURNING id",
        "DELETE FROM clinical_action_audit_records RETURNING id",
    ):
        assert (
            sql(f"SET request.jwt.claim.sub='{CLINICIAN}'; SET ROLE authenticated; {statement};")
            == ""
        )
    assert sql("SELECT event_type FROM clinical_action_audit_records;") == "approved"


def test_concurrent_same_key_insert_returns_one_saved_winner(sql):
    rid = seed(sql)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: sql(envelope_sql(rid)), range(8)))
    inserted = [value for value in results if value]
    assert len(inserted) == 1
    assert sql(f"SELECT id FROM action_envelopes WHERE recommendation_id='{rid}';") == inserted[0]
    assert sql("SELECT count(*) FROM action_envelopes;") == "1"


def test_duplicate_does_not_overwrite_terminal_outcome(sql):
    rid = seed(sql)
    saved_id = sql(envelope_sql(rid))
    sql(
        f"UPDATE action_envelopes SET state='executed',outcome='{{\"saved\":true}}' WHERE id='{saved_id}';"
    )
    assert sql(envelope_sql(rid)) == ""
    assert (
        sql(
            f"SELECT state || ':' || (outcome->>'saved') FROM action_envelopes WHERE id='{saved_id}';"
        )
        == "executed:true"
    )


def test_independent_key_is_not_deduplicated_as_the_first_request(sql):
    rid = seed(sql)
    first = sql(envelope_sql(rid))
    second = sql(envelope_sql(rid, "synthetic-second-key"))
    assert first and second and first != second


def test_one_final_decision_and_foreign_keys_remain_enforced(sql):
    rid = seed(sql)
    error = sql(
        f"INSERT INTO approval_decisions(recommendation_id,reviewer_id,decision,note) VALUES('{rid}','{CLINICIAN}','reject','second');",
        succeeds=False,
    )
    assert "duplicate key" in error
    error = sql(envelope_sql(str(uuid4())), succeeds=False)
    assert "foreign key" in error
