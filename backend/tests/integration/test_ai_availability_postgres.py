"""Migration 090: bounded model availability counters, under hosted default grants.

Synthetic counters only. The harness applies the base schema in a disposable postgres:16
container with Supabase-style default grants; 090 is applied by name.
"""

import json
import os

import pytest

from tests.integration.test_notification_centre_postgres import MIGRATIONS

pytest_plugins = ["tests.integration.test_notification_centre_postgres"]
pytestmark = pytest.mark.skipif(
    os.environ.get("CHAT_TURN_TEST_POSTGRES_DOCKER") != "1", reason="offline PostgreSQL opt-in"
)

BINS = [0, 3, 0, 0, 0, 0, 0, 0, 0, 0]


@pytest.fixture
def db(sql):
    for path in sorted(MIGRATIONS.glob("*_ai_availability_rollup.sql")):
        sql(path.read_text())
    return sql


def row(**changes):
    base = {
        "workload": "reply",
        "model": "gemini-3.8-flash",
        "outcome": "success",
        "fallback": False,
        "attempts": 3,
        "latency_sum_ms": 900,
        "bins": BINS,
    }
    return {**base, **changes}


def record(db, rows, *, role="service_role", succeeds=True):
    body = json.dumps(rows).replace("'", "''")
    out = db(
        f"SET ROLE {role}; SELECT public.record_ai_availability('{body}'::jsonb);",
        succeeds=succeeds,
    )
    return json.loads(out.splitlines()[-1]) if succeeds else out


def rows(db, where=""):
    out = db(
        "SELECT coalesce(json_agg(t ORDER BY workload,model,outcome,fallback),'[]') FROM "
        f"(SELECT workload,model,outcome,fallback,attempts,latency_sum_ms,latency_bins "
        f"FROM public.ai_availability_buckets {where}) t;"
    )
    return json.loads(out)


def test_the_migration_is_rerunnable(db):
    for path in sorted(MIGRATIONS.glob("*_ai_availability_rollup.sql")):
        db(path.read_text())


def test_counts_accumulate_in_one_row_per_key_and_hour(db):
    assert record(db, [row()])["applied"] == 1
    record(db, [row(attempts=2, latency_sum_ms=500, bins=[0, 0, 2, 0, 0, 0, 0, 0, 0, 0])])
    record(db, [row(outcome="rate_limited", attempts=1, bins=[1, 0, 0, 0, 0, 0, 0, 0, 0, 0])])
    record(db, [row(fallback=True, attempts=1)])
    result = rows(db)
    success = next(r for r in result if r["outcome"] == "success" and not r["fallback"])
    assert success["attempts"] == 5 and success["latency_sum_ms"] == 1400
    assert success["latency_bins"] == [0, 3, 2, 0, 0, 0, 0, 0, 0, 0]
    assert len(result) == 3


def test_invalid_rows_are_counted_as_overflow_not_stored(db):
    out = record(
        db,
        [
            row(workload="Reply; DROP TABLE x"),
            row(model="has space"),
            row(outcome="made_up"),
            row(outcome="success"),
        ],
    )
    assert out["applied"] == 1 and out["dropped"] == 9
    overflow = rows(db, "WHERE outcome='overflow'")
    assert overflow[0]["attempts"] == 9 and overflow[0]["workload"] == "overflow"


def test_a_non_array_or_oversized_call_is_refused(db):
    assert record(db, {"x": 1})["accepted"] is False
    assert record(db, [row()] * 201)["accepted"] is False


def test_keys_per_hour_are_capped(db):
    batch = [row(model=f"m{i}") for i in range(200)]
    record(db, batch)
    record(db, [row(model=f"n{i}") for i in range(200)])
    record(db, [row(model="late")])
    count = int(
        db("SELECT count(*) FROM public.ai_availability_buckets WHERE outcome<>'overflow';")
    )
    assert count == 400
    assert not rows(db, "WHERE model='late'")
    assert rows(db, "WHERE outcome='overflow'")[0]["attempts"] == 3


def test_old_buckets_are_pruned_a_batch_at_a_time(db):
    db(
        "INSERT INTO public.ai_availability_buckets(bucket_start,workload,model,outcome,attempts) "
        "SELECT now()-interval '20 days'+(g||' minutes')::interval,'reply','m','success',1 "
        "FROM generate_series(1,250) g;"
    )
    record(db, [row()])
    old = int(
        db(
            "SELECT count(*) FROM public.ai_availability_buckets WHERE bucket_start<now()-interval '14 days';"
        )
    )
    assert old == 50  # one call deletes at most 200
    record(db, [row()])
    old = int(
        db(
            "SELECT count(*) FROM public.ai_availability_buckets WHERE bucket_start<now()-interval '14 days';"
        )
    )
    assert old == 0


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_browser_roles_reach_neither_the_table_nor_the_function(db, role):
    assert "permission denied" in db(
        f"SET ROLE {role}; SELECT * FROM public.ai_availability_buckets;", succeeds=False
    )
    assert "permission denied" in db(
        f"SET ROLE {role}; SELECT public.record_ai_availability('[]'::jsonb);", succeeds=False
    )


def test_the_service_role_can_read_but_not_write_the_table_directly(db):
    record(db, [row()])
    assert db(
        "SET ROLE service_role; SELECT count(*) FROM public.ai_availability_buckets;"
    ).endswith("1")
    for statement in (
        "INSERT INTO public.ai_availability_buckets(bucket_start,workload,model,outcome) VALUES(now(),'a','b','success')",
        "UPDATE public.ai_availability_buckets SET attempts=0",
        "DELETE FROM public.ai_availability_buckets",
    ):
        assert "permission denied" in db(f"SET ROLE service_role; {statement};", succeeds=False)


def test_row_level_security_is_enabled(db):
    assert (
        db(
            "SELECT relrowsecurity FROM pg_class WHERE oid='public.ai_availability_buckets'::regclass;"
        )
        == "t"
    )
