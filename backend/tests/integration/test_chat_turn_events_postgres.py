# ruff: noqa: F811  (pytest fixtures are imported by name)
"""Migration 078: queued turns, ordered events and the worker's claim, under hosted default grants.

Fictional records only. The harness applies every migration from scratch in a disposable
postgres:16 container with Supabase-style default grants.
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from tests.integration.test_chat_turn_postgres import (  # noqa: F401
    FOREIGN,
    MIGRATIONS,
    PATIENT,
    call,
    finish,
    request,
    turn_sql,
)

pytest_plugins = ["tests.integration.test_notification_centre_postgres"]
pytestmark = pytest.mark.skipif(
    os.environ.get("CHAT_TURN_TEST_POSTGRES_DOCKER") != "1", reason="offline PostgreSQL opt-in"
)


def worker(db, turn_id, action, payload=None, *, succeeds=True):
    body = json.dumps(payload or {}).replace("'", "''")
    out = db(
        f"SET ROLE service_role; SELECT chat_turn_worker_operation('{turn_id}','{action}','{body}');",
        succeeds=succeeds,
    )
    return json.loads(out) if succeeds else out


def queue(db, **changes):
    """Begin a queued turn; returns the begin result."""
    data = request(queued=True, **changes)
    result = call(db, payload=data)
    assert result["execute"] and result["turn"]["status"] == "queued"
    return data, result


def claim(db, turn, **extra):
    return worker(
        db, turn["id"], "claim", {"attempt": turn["attempt"], "timeout_seconds": 60, **extra}
    )


def events(db, turn_id):
    rows = db(
        f"SELECT coalesce(json_agg(json_build_object('seq',seq,'type',type,'payload',payload) ORDER BY seq),'[]') "
        f"FROM chat_turn_events WHERE turn_id='{turn_id}';"
    )
    return json.loads(rows)


def reason(result):
    assert result["accepted"] is False
    return result["reason"]


def expire(db):
    db("UPDATE chat_turns SET deadline_at=clock_timestamp()-interval '1 second';")


# -- schema, grants -----------------------------------------------------------------------


def test_events_are_backend_only_and_append_only(turn_sql):
    for role in ("anon", "authenticated"):
        for statement in (
            "SELECT * FROM chat_turn_events",
            "INSERT INTO chat_turn_events(turn_id,seq,type) VALUES(gen_random_uuid(),1,'draft')",
            "DELETE FROM chat_turn_events",
            "SELECT chat_turn_worker_operation(gen_random_uuid(),'claim')",
            "SELECT chat_turn_append_event(gen_random_uuid(),'draft','{}')",
        ):
            assert "permission denied" in turn_sql(f"SET ROLE {role}; {statement};", succeeds=False)
    assert "permission denied" in turn_sql(
        "SET ROLE service_role; UPDATE chat_turn_events SET type='draft';", succeeds=False
    )
    assert (
        turn_sql("SELECT relrowsecurity FROM pg_class WHERE oid='chat_turn_events'::regclass;")
        == "t"
    )


def test_functions_carry_timeouts_and_077_behaviour(turn_sql):
    configs = turn_sql(
        "SELECT string_agg(proname||':'||coalesce(array_to_string(proconfig,','),''),';' ORDER BY proname) "
        "FROM pg_proc WHERE proname IN ('chat_turn_operation','chat_turn_worker_operation');"
    )
    for name in ("chat_turn_operation", "chat_turn_worker_operation"):
        assert f"{name}:" in configs
    assert configs.count("lock_timeout=5s") == 2 and configs.count("statement_timeout=8s") == 2


def test_migration_rerun_is_safe_and_keeps_data(turn_sql):
    _, result = queue(turn_sql)
    migration = (MIGRATIONS / "078_chat_turn_events.sql").read_text()
    turn_sql(migration)
    turn_sql(migration)
    assert claim(turn_sql, result["turn"])["accepted"]
    assert turn_sql("SELECT count(*) FROM chat_turn_events;") == "1"


def test_verification_block_rejects_restored_browser_access(turn_sql):
    migration = (MIGRATIONS / "078_chat_turn_events.sql").read_text()
    broken = migration.replace(
        "DO $$\nDECLARE def text; fn text;",
        "GRANT SELECT ON public.chat_turn_events TO anon;\nDO $$\nDECLARE def text; fn text;",
    )
    assert "backend-only and append-only" in turn_sql(broken, succeeds=False)


# -- queued turns -----------------------------------------------------------------------------


def test_queued_turn_is_the_conversations_one_active_turn(turn_sql):
    data, first = queue(turn_sql)
    assert first["turn"]["via_worker"] is True and first["turn"]["dispatched_at"] is None
    assert "CHAT_TURN_BUSY" in call(turn_sql, payload=request(queued=True), succeeds=False)
    assert "CHAT_TURN_BUSY" in call(turn_sql, payload=request(), succeeds=False)
    again = call(turn_sql, payload=data)
    assert not again["execute"] and again["turn"]["status"] == "queued"
    assert turn_sql("SELECT count(*) FROM chat_messages;") == "1"
    assert call(turn_sql, payload=request(queued=True), session="other-chat")["execute"]


def test_in_process_turns_do_not_use_the_worker_columns_or_events(turn_sql):
    record = call(turn_sql, payload=request())["turn"]
    assert record["status"] == "processing" and record["via_worker"] is False
    assert call(turn_sql, "complete", finish(record))["accepted"]
    assert turn_sql("SELECT count(*) FROM chat_turn_events;") == "0"


def test_queued_turn_reconciles_at_its_deadline(turn_sql):
    _, result = queue(turn_sql)
    expire(turn_sql)
    item = call(turn_sql, "recover")["items"][0]
    assert item["status"] == "interrupted" and item["failure_code"] == "deadline"
    assert [e["type"] for e in events(turn_sql, result["turn"]["id"])] == ["interrupted"]
    assert not claim(turn_sql, result["turn"])["accepted"]


def test_recover_lists_the_queued_turn_first(turn_sql):
    _, result = queue(turn_sql)
    items = call(turn_sql, "recover")["items"]
    assert items[0]["id"] == result["turn"]["id"] and "lease" not in items[0]


def test_retry_after_interruption_requeues_with_the_next_attempt(turn_sql):
    data, result = queue(turn_sql)
    turn = result["turn"]
    claimed = claim(turn_sql, turn)
    expire(turn_sql)
    assert call(turn_sql, "recover")["items"][0]["status"] == "interrupted"
    retry = call(turn_sql, payload={**data})
    assert retry["execute"] and retry["turn"]["status"] == "queued"
    assert retry["turn"]["attempt"] == 2 and retry["turn"]["dispatched_at"] is None
    assert retry["turn"]["lease"] != claimed["turn"]["lease"]
    second = claim(turn_sql, retry["turn"])
    assert second["accepted"]
    assert [e["type"] for e in events(turn_sql, turn["id"])] == [
        "started",
        "interrupted",
        "started",
    ]


# -- claim ---------------------------------------------------------------------------------------


def test_claim_moves_queued_to_processing_with_a_new_lease(turn_sql):
    _, result = queue(turn_sql)
    turn = result["turn"]
    claimed = claim(turn_sql, turn)
    assert claimed["accepted"] and claimed["patient_id"] == PATIENT
    assert claimed["session_id"] == "chat-test" and claimed["next_seq"] == 2
    assert claimed["turn"]["status"] == "processing" and claimed["turn"]["run_count"] == 1
    assert claimed["turn"]["lease"] != turn["lease"] and "request_hash" not in claimed["turn"]
    assert claimed["user_message"]["id"] == result["user_message"]["id"]
    assert [e["type"] for e in events(turn_sql, turn["id"])] == ["started"]


def test_two_concurrent_claims_have_one_winner(turn_sql):
    _, result = queue(turn_sql)
    turn = result["turn"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: claim(turn_sql, turn), range(4)))
    winners = [r for r in results if r["accepted"]]
    assert len(winners) == 1
    assert {reason(r) for r in results if not r["accepted"]} == {"lease_active"}
    assert turn_sql("SELECT run_count FROM chat_turns;") == "1"
    assert turn_sql("SELECT count(*) FROM chat_turn_events;") == "1"


def test_a_repeated_claim_while_the_lease_is_live_is_refused_as_retryable(turn_sql):
    _, result = queue(turn_sql)
    assert claim(turn_sql, result["turn"])["accepted"]
    assert reason(claim(turn_sql, result["turn"])) == "lease_active"


@pytest.mark.parametrize("terminal", ["complete", "failed", "interrupted"])
def test_claim_after_a_terminal_state_is_a_noop(turn_sql, terminal):
    _, result = queue(turn_sql)
    lease = claim(turn_sql, result["turn"])["turn"]
    body = finish(lease) if terminal == "complete" else lease
    assert call(turn_sql, terminal, body)["accepted"]
    status = {"complete": "completed"}.get(terminal, terminal)
    assert reason(claim(turn_sql, result["turn"])) == f"status:{status}"
    assert turn_sql("SELECT status FROM chat_turns;") == status


def test_claim_after_lease_expiry_takes_over_and_fences_the_old_lease(turn_sql):
    _, result = queue(turn_sql)
    first = claim(turn_sql, result["turn"])
    expire(turn_sql)
    second = claim(turn_sql, result["turn"])
    assert second["accepted"] and second["turn"]["run_count"] == 2
    assert second["turn"]["lease"] != first["turn"]["lease"]
    assert reason(call(turn_sql, "complete", finish(first["turn"]))) == "lease_mismatch"
    assert call(turn_sql, "complete", finish(second["turn"]))["accepted"]


def test_claim_after_expiry_never_reruns_a_turn_that_started_actions(turn_sql):
    _, result = queue(turn_sql)
    lease = claim(turn_sql, result["turn"])["turn"]
    assert call(turn_sql, "actions", lease)["accepted"]
    expire(turn_sql)
    assert reason(claim(turn_sql, result["turn"])) == "action_uncertain"
    row = turn_sql("SELECT status||':'||failure_code FROM chat_turns;")
    assert row == "interrupted:action_uncertain"
    assert [e["type"] for e in events(turn_sql, result["turn"]["id"])] == ["started", "interrupted"]
    assert reason(claim(turn_sql, result["turn"])) == "status:interrupted"


def test_claim_stops_after_three_runs(turn_sql):
    _, result = queue(turn_sql)
    for _ in range(3):
        assert claim(turn_sql, result["turn"])["accepted"]
        expire(turn_sql)
    assert reason(claim(turn_sql, result["turn"])) == "attempts_exhausted"


def test_claim_refusals_for_unknown_stale_and_foreign_inputs(turn_sql):
    data, result = queue(turn_sql)
    turn = result["turn"]
    assert reason(worker(turn_sql, str(uuid4()), "claim", {"attempt": 1})) == "not_found"
    assert reason(worker(turn_sql, turn["id"], "claim", {"attempt": 2})) == "stale_attempt"
    plain = call(turn_sql, payload=request(), session="plain-chat")["turn"]
    assert reason(worker(turn_sql, plain["id"], "claim", {"attempt": 1})) == "not_worker_turn"
    expire(turn_sql)
    assert reason(claim(turn_sql, turn)) == "queue_expired"
    assert turn_sql(f"SELECT status FROM chat_turns WHERE id='{turn['id']}';") == "interrupted"


def test_claim_rereads_the_selected_document_and_fails_closed(turn_sql):
    doc = str(uuid4())
    turn_sql(
        f"INSERT INTO documents(id,patient_id,uploaded_by,uploaded_by_role,document_type,file_name,file_url,file_size_bytes,parse_status,ai_summary) VALUES('{doc}','{PATIENT}','{PATIENT}','patient','other','synthetic.pdf','synthetic',10,'completed','Synthetic summary');"
    )
    _, result = queue(turn_sql, document_id=doc)
    assert "summary" not in (turn_sql("SELECT document_context FROM chat_turns;"))
    claimed = claim(turn_sql, result["turn"])
    assert claimed["turn"]["document_context"]["summary"] == "Synthetic summary"
    call(turn_sql, "failed", claimed["turn"])
    # a changed document fails the retry's claim without running anything
    data = request(queued=True, document_id=doc)
    turn_sql(f"UPDATE documents SET ai_summary='Changed' WHERE id='{doc}';")
    _, second = queue(turn_sql, document_id=doc, client_message_id=str(uuid4()))
    expire_turn = second["turn"]["id"]
    turn_sql(f"UPDATE documents SET ai_summary='Synthetic summary two' WHERE id='{doc}';")
    assert reason(claim(turn_sql, second["turn"])) == "document_unavailable"
    assert turn_sql(f"SELECT status FROM chat_turns WHERE id='{expire_turn}';") == "failed"
    assert data["queued"]


# -- events -----------------------------------------------------------------------------------


def test_append_event_orders_by_seq_for_the_current_lease_only(turn_sql):
    _, result = queue(turn_sql)
    turn = result["turn"]
    lease = claim(turn_sql, turn)["turn"]["lease"]
    for index in range(3):
        out = worker(
            turn_sql,
            turn["id"],
            "append_event",
            {
                "lease": lease,
                "type": "draft",
                "payload": {"content": "x" * index},
                "seq": 2 + index,
            },
        )
        assert out["accepted"] and out["seq"] == 2 + index and out["next_seq"] == 3 + index
    stale = worker(
        turn_sql,
        turn["id"],
        "append_event",
        {"lease": str(uuid4()), "type": "draft", "payload": {}},
    )
    assert reason(stale) == "lease_mismatch"
    assert [e["seq"] for e in events(turn_sql, turn["id"])] == [1, 2, 3, 4]


def test_append_event_gap_duplicate_and_invalid_input(turn_sql):
    _, result = queue(turn_sql)
    turn = result["turn"]
    lease = claim(turn_sql, turn)["turn"]["lease"]
    base = {"lease": lease, "type": "draft", "payload": {"content": "a"}}
    assert worker(turn_sql, turn["id"], "append_event", {**base, "seq": 2})["accepted"]
    repeat = worker(turn_sql, turn["id"], "append_event", {**base, "seq": 2})
    assert repeat["accepted"] and repeat["duplicate"] and repeat["next_seq"] == 3
    gap = worker(turn_sql, turn["id"], "append_event", {**base, "seq": 9})
    assert reason(gap) == "seq_gap" and gap["next_seq"] == 3
    other = worker(turn_sql, turn["id"], "append_event", {**base, "type": "notice", "seq": 2})
    assert reason(other) == "seq_conflict"
    assert "CHAT_TURN_INVALID" in worker(
        turn_sql, turn["id"], "append_event", {**base, "type": "completed"}, succeeds=False
    )
    assert "CHAT_TURN_INVALID" in worker(
        turn_sql, turn["id"], "append_event", {**base, "payload": [1]}, succeeds=False
    )
    assert turn_sql("SELECT count(*) FROM chat_turn_events;") == "2"


def test_concurrent_appends_get_distinct_ordered_seq_numbers(turn_sql):
    _, result = queue(turn_sql)
    turn = result["turn"]
    lease = claim(turn_sql, turn)["turn"]["lease"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        out = list(
            pool.map(
                lambda i: worker(
                    turn_sql,
                    turn["id"],
                    "append_event",
                    {"lease": lease, "type": "draft", "payload": {"i": i}},
                ),
                range(8),
            )
        )
    assert all(row["accepted"] for row in out)
    assert [e["seq"] for e in events(turn_sql, turn["id"])] == list(range(1, 10))


def test_append_event_refused_after_the_lease_expires_or_the_turn_ends(turn_sql):
    _, result = queue(turn_sql)
    turn = result["turn"]
    lease = claim(turn_sql, turn)["turn"]
    body = {"lease": lease["lease"], "type": "draft", "payload": {}}
    expire(turn_sql)
    assert reason(worker(turn_sql, turn["id"], "append_event", body)) == "deadline_passed"
    call(turn_sql, "recover")  # reconciles to interrupted
    assert reason(worker(turn_sql, turn["id"], "append_event", body)) == "status:interrupted"


def test_terminal_events_commit_with_the_state_change_and_replace_drafts(turn_sql):
    _, result = queue(turn_sql)
    turn = result["turn"]
    lease = claim(turn_sql, turn)["turn"]
    worker(
        turn_sql,
        turn["id"],
        "append_event",
        {"lease": lease["lease"], "type": "draft", "payload": {"content": "partial"}},
    )
    worker(
        turn_sql,
        turn["id"],
        "append_event",
        {"lease": lease["lease"], "type": "notice", "payload": {"type": "appointment_proposal"}},
    )
    done = call(turn_sql, "complete", finish(lease))
    kinds = [e["type"] for e in events(turn_sql, turn["id"])]
    assert kinds == ["started", "notice", "completed"]
    completed = events(turn_sql, turn["id"])[-1]["payload"]
    assert completed["message_id"] == done["message"]["id"]


@pytest.mark.parametrize("action", ["failed", "interrupted"])
def test_failed_and_interrupted_write_their_terminal_event(turn_sql, action):
    _, result = queue(turn_sql)
    lease = claim(turn_sql, result["turn"])["turn"]
    call(turn_sql, "actions", lease)
    call(turn_sql, action, lease)
    last = events(turn_sql, result["turn"]["id"])[-1]
    assert last["type"] == action and last["payload"]["failure_code"] == "action_uncertain"


def test_prune_events_keeps_only_final_events_after_a_terminal_state(turn_sql):
    _, result = queue(turn_sql)
    turn = result["turn"]
    lease = claim(turn_sql, turn)["turn"]
    assert reason(worker(turn_sql, turn["id"], "prune_events")) == "status:processing"
    call(turn_sql, "complete", finish(lease))
    turn_sql(
        f"INSERT INTO chat_turn_events(turn_id,seq,type,payload) VALUES('{turn['id']}',10,'draft','{{}}'),('{turn['id']}',11,'draft','{{}}');"
    )
    pruned = worker(turn_sql, turn["id"], "prune_events")
    assert pruned["accepted"] and pruned["deleted"] == 2
    assert [e["type"] for e in events(turn_sql, turn["id"])] == ["started", "completed"]
    assert worker(turn_sql, turn["id"], "prune_events")["deleted"] == 0


def test_deleting_a_turn_removes_its_events(turn_sql):
    _, result = queue(turn_sql)
    claim(turn_sql, result["turn"])
    turn_sql(f"DELETE FROM chat_turns WHERE id='{result['turn']['id']}';")
    assert turn_sql("SELECT count(*) FROM chat_turn_events;") == "0"


# -- requeue and the outbox -----------------------------------------------------------------


def test_requeue_hands_the_turn_back_only_before_any_action(turn_sql):
    _, result = queue(turn_sql)
    turn = result["turn"]
    lease = claim(turn_sql, turn)["turn"]
    assert (
        reason(worker(turn_sql, turn["id"], "requeue", {"lease": str(uuid4())})) == "lease_mismatch"
    )
    assert worker(turn_sql, turn["id"], "requeue", {"lease": lease["lease"]})["accepted"]
    assert (
        turn_sql("SELECT status||':'||(dispatched_at IS NOT NULL) FROM chat_turns;")
        == "queued:true"
    )
    again = claim(turn_sql, turn)
    assert again["accepted"] and again["turn"]["run_count"] == 2
    call(turn_sql, "actions", again["turn"])
    assert (
        reason(worker(turn_sql, turn["id"], "requeue", {"lease": again["turn"]["lease"]}))
        == "actions_started"
    )


def test_the_outbox_lists_only_undispatched_queued_turns(turn_sql):
    _, result = queue(turn_sql)
    turn = result["turn"]
    young = worker(
        turn_sql, "00000000-0000-0000-0000-000000000000", "undispatched", {"min_age_seconds": 3600}
    )
    assert young["items"] == []
    listed = worker(
        turn_sql, "00000000-0000-0000-0000-000000000000", "undispatched", {"min_age_seconds": 0}
    )
    assert listed["items"] == [{"id": turn["id"], "attempt": 1}]
    assert not worker(turn_sql, turn["id"], "dispatched", {"attempt": 2})["accepted"]
    assert worker(turn_sql, turn["id"], "dispatched", {"attempt": 1})["accepted"]
    assert not worker(turn_sql, turn["id"], "dispatched", {"attempt": 1})["accepted"]
    listed = worker(
        turn_sql, "00000000-0000-0000-0000-000000000000", "undispatched", {"min_age_seconds": 0}
    )
    assert listed["items"] == []


def test_the_outbox_skips_rows_a_concurrent_sweep_holds(turn_sql):
    _, result = queue(turn_sql)
    holder = "BEGIN; SELECT id FROM chat_turns WHERE status='queued' FOR UPDATE; SELECT pg_sleep(2); COMMIT;"
    import time

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(turn_sql, holder)
        time.sleep(0.8)
        started = time.monotonic()
        listed = worker(turn_sql, str(uuid4()), "undispatched", {"min_age_seconds": 0})
        waited = time.monotonic() - started
        future.result()
    assert listed["items"] == [] and waited < 1.5
    assert result["turn"]["id"]


def test_dead_letter_and_expired_queued_turns_are_not_listed(turn_sql):
    queue(turn_sql)
    expire(turn_sql)
    assert worker(turn_sql, str(uuid4()), "undispatched", {"min_age_seconds": 0})["items"] == []


def test_unknown_worker_action_is_invalid(turn_sql):
    _, result = queue(turn_sql)
    assert "CHAT_TURN_INVALID" in worker(turn_sql, result["turn"]["id"], "nope", succeeds=False)


def test_other_patients_cannot_touch_a_worker_turn_through_the_patient_function(turn_sql):
    _, result = queue(turn_sql)
    lease = claim(turn_sql, result["turn"])["turn"]
    body = json.dumps(finish(lease)).replace("'", "''")
    out = call_as_foreign(turn_sql, body)
    assert out["accepted"] is False and out["reason"] == "not_found"
    assert turn_sql("SELECT status FROM chat_turns;") == "processing"


def call_as_foreign(db, body):
    return json.loads(
        db(
            f"SET ROLE service_role; SELECT chat_turn_operation('{FOREIGN}','chat-test','complete','{body}');"
        )
    )
