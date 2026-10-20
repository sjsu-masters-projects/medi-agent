"""Actual migrations, hosted-style grants and concurrent turn claims; fictional records only."""

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from tests.integration.test_notification_centre_postgres import FOREIGN, MIGRATIONS, PATIENT

pytest_plugins = ["tests.integration.test_notification_centre_postgres"]
pytestmark = pytest.mark.skipif(
    os.environ.get("CHAT_TURN_TEST_POSTGRES_DOCKER") != "1", reason="offline PostgreSQL opt-in"
)


@pytest.fixture
def turn_sql(sql):
    for name in (
        "010_chat_state_and_a2a_tasks.sql",
        "050_document_display_titles.sql",
        "051_health_knowledge_and_chat_sessions.sql",
        "062_chat_message_attachments.sql",
        "072_nora_turn_recovery.sql",
        "073_nora_turn_begin_validation.sql",
        "074_nora_late_completion.sql",
        "077_chat_turn_rejection_reason.sql",
        "078_chat_turn_events.sql",
    ):
        sql((MIGRATIONS / name).read_text())
    return sql


def call(db, action="begin", payload=None, *, session="chat-test", succeeds=True):
    body = json.dumps(payload or {}).replace("'", "''")
    result = db(
        f"SET ROLE service_role; SELECT chat_turn_operation('{PATIENT}','{session}','{action}','{body}');",
        succeeds=succeeds,
    )
    return json.loads(result) if succeeds else result


def request(**changes):
    data = {
        "client_message_id": str(uuid4()),
        "content": "Synthetic question",
        "language": "en-US",
        "document_id": None,
        "timeout_seconds": 30,
    }
    data.update(changes)
    data["request_hash"] = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    return data


def finish(record):
    return {
        "id": record["id"],
        "lease": record["lease"],
        "message_id": str(uuid4()),
        "content": "Synthetic reply",
        "language": "en-US",
        "intent": "general",
    }


def test_browser_cannot_read_write_or_invoke(turn_sql):
    for role in ("anon", "authenticated"):
        for statement in (
            "SELECT * FROM chat_turns",
            "DELETE FROM chat_turns",
            f"SELECT chat_turn_operation('{PATIENT}','chat-test','recover')",
        ):
            assert "permission denied" in turn_sql(f"SET ROLE {role}; {statement};", succeeds=False)
    assert turn_sql("SELECT relrowsecurity FROM pg_class WHERE oid='chat_turns'::regclass;") == "t"


def test_saved_message_and_claim_are_atomic_and_duplicate_safe(turn_sql):
    data = request()
    first = call(turn_sql, payload=data)
    again = call(turn_sql, payload=data)
    assert first["execute"] and not again["execute"]
    assert first["user_message"]["id"] == again["user_message"]["id"]
    assert turn_sql("SELECT count(*) FROM chat_messages;") == "1"
    assert "CHAT_TURN_BUSY" in call(turn_sql, payload=request(), succeeds=False)


def test_migration_rerun_preserves_turns_and_repairs_browser_grants(turn_sql):
    data = request()
    first = call(turn_sql, payload=data)
    turn_sql(
        "ALTER TABLE chat_turns DISABLE ROW LEVEL SECURITY; GRANT ALL ON chat_turns TO anon,authenticated; GRANT EXECUTE ON FUNCTION chat_turn_operation(uuid,text,text,jsonb) TO anon;"
    )
    migration = (MIGRATIONS / "072_nora_turn_recovery.sql").read_text()
    turn_sql(migration)
    turn_sql(migration)
    assert call(turn_sql, payload=data)["user_message"]["id"] == first["user_message"]["id"]
    assert turn_sql("SELECT relrowsecurity FROM pg_class WHERE oid='chat_turns'::regclass;") == "t"
    assert turn_sql("SELECT has_table_privilege('anon','chat_turns','SELECT');") == "f"
    assert (
        turn_sql(
            "SELECT has_function_privilege('authenticated','chat_turn_operation(uuid,text,text,jsonb)','EXECUTE');"
        )
        == "f"
    )


@pytest.mark.parametrize(
    "statement,expected",
    [
        (
            "GRANT SELECT ON public.chat_turns TO anon;",
            "chat_turns must not be open to a browser role",
        ),
        (
            "ALTER TABLE public.chat_turns DISABLE ROW LEVEL SECURITY;",
            "chat_turns must have row level security enabled",
        ),
        (
            "GRANT EXECUTE ON FUNCTION public.chat_turn_operation(uuid,text,text,jsonb) TO authenticated;",
            "chat_turn_operation must be executable by the service role only",
        ),
    ],
)
def test_final_verification_rejects_accidentally_restored_browser_access(
    turn_sql, statement, expected
):
    migration = (MIGRATIONS / "072_nora_turn_recovery.sql").read_text()
    migration = migration.replace(
        "-- Fail closed if hosted default grants",
        statement + "\n-- Fail closed if hosted default grants",
    )
    assert expected in turn_sql(migration, succeeds=False)


def test_three_attempt_limit_never_creates_another_user_message(turn_sql):
    data = request()
    for attempt in range(1, 4):
        claimed = call(turn_sql, payload=data)
        assert claimed["execute"] and claimed["turn"]["attempt"] == attempt
        call(turn_sql, "failed", claimed["turn"])
    exhausted = call(turn_sql, payload=data)
    assert not exhausted["execute"] and exhausted["turn"]["attempt"] == 3
    assert turn_sql("SELECT count(*) FROM chat_messages;") == "1"


def test_malformed_privileged_source_rows_fail_closed_in_recovery_and_replay(turn_sql):
    data = request()
    call(turn_sql, payload=data)
    turn_sql(
        f"UPDATE chat_messages SET patient_id='{FOREIGN}',content='Foreign synthetic content';"
    )
    assert call(turn_sql, "recover")["items"] == []
    assert "CHAT_TURN_UNAVAILABLE" in call(turn_sql, payload=data, succeeds=False)


def test_conflicting_reuse_does_not_change_saved_message(turn_sql):
    data = request()
    call(turn_sql, payload=data)
    assert "CHAT_TURN_CONFLICT" in call(
        turn_sql, payload={**data, "request_hash": "b" * 64}, succeeds=False
    )
    assert turn_sql("SELECT content FROM chat_messages;") == "Synthetic question"


def test_completion_is_atomic_and_replayed_without_another_message(turn_sql):
    data = request()
    record = call(turn_sql, payload=data)["turn"]
    assert call(turn_sql, "complete", finish(record))["accepted"]
    replay = call(turn_sql, payload=data)
    assert not replay["execute"] and replay["assistant_message"]["content"] == "Synthetic reply"
    assert not call(turn_sql, "complete", finish(record))["accepted"]
    assert turn_sql("SELECT count(*) FROM chat_messages;") == "2"


def test_dismissal_is_scoped_and_cannot_hide_active_or_completed_work(turn_sql):
    data = request()
    record = call(turn_sql, payload=data)["turn"]
    assert not call(turn_sql, "dismiss", data)["accepted"]
    call(turn_sql, "interrupted", record)
    assert not call(turn_sql, "dismiss", data, session="other-session")["accepted"]
    assert call(turn_sql, "dismiss", data)["accepted"]
    assert call(turn_sql, "recover")["items"] == []
    assert not call(turn_sql, payload=data)["execute"]
    assert turn_sql("SELECT count(*) FROM chat_messages;") == "1"


def test_recovery_discovers_a_reply_completed_by_another_connection(turn_sql):
    record = call(turn_sql, payload=request())["turn"]
    call(turn_sql, "complete", finish(record))
    recovered = call(turn_sql, "recover")["items"]
    assert recovered[0]["status"] == "completed"
    assert "lease" not in recovered[0] and "request_hash" not in recovered[0]


def test_recovery_expires_lease_and_retries_the_same_user_message(turn_sql):
    data = request()
    original = call(turn_sql, payload=data)
    turn_sql("UPDATE chat_turns SET deadline_at=clock_timestamp()-interval '1 second';")
    assert call(turn_sql, "recover")["items"][0]["status"] == "interrupted"
    retry = call(turn_sql, payload=data)
    assert retry["execute"] and retry["turn"]["lease"] != original["turn"]["lease"]
    assert retry["user_message"]["id"] == original["user_message"]["id"]
    assert not call(turn_sql, "complete", finish(original["turn"]))["accepted"]


def test_uncertain_actions_are_never_reexecuted(turn_sql):
    data = request()
    record = call(turn_sql, payload=data)["turn"]
    assert call(turn_sql, "actions", record)["accepted"]
    call(turn_sql, "interrupted", record)
    assert not call(turn_sql, payload=data)["execute"]
    assert call(turn_sql, "recover")["items"][0]["failure_code"] == "action_uncertain"


def test_two_workers_cannot_execute_the_same_turn(turn_sql):
    data = request()
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: call(turn_sql, payload=data), range(2)))
    assert sum(bool(row["execute"]) for row in results) == 1
    assert turn_sql("SELECT count(*) FROM chat_turns;") == "1"


def test_document_is_authorized_and_bound_to_the_turn(turn_sql):
    doc = str(uuid4())
    turn_sql(
        f"INSERT INTO documents(id,patient_id,uploaded_by,uploaded_by_role,document_type,file_name,file_url,file_size_bytes,parse_status,ai_summary) VALUES('{doc}','{PATIENT}','{PATIENT}','patient','other','synthetic.pdf','synthetic',10,'completed','Synthetic summary');"
    )
    data = request(document_id=doc)
    record = call(turn_sql, payload=data)["turn"]
    assert record["document_context"]["id"] == doc
    assert "file_url" not in record["document_context"]
    assert record["document_context"]["summary"] == "Synthetic summary"
    assert turn_sql("SELECT document_context ? 'summary' FROM chat_turns;") == "f"
    call(turn_sql, "failed", record)
    turn_sql(f"UPDATE documents SET ai_summary='Changed synthetic summary' WHERE id='{doc}';")
    assert "CHAT_DOCUMENT_CHANGED" in call(turn_sql, payload=data, succeeds=False)
    turn_sql(f"DELETE FROM documents WHERE id='{doc}';")
    assert turn_sql("SELECT document_context ? 'summary' FROM chat_turns;") == "f"
    assert "CHAT_DOCUMENT_UNAVAILABLE" in call(
        turn_sql, payload=request(document_id=str(uuid4())), succeeds=False
    )


def test_another_patient_cannot_recover_or_finish_this_turn(turn_sql):
    record = call(turn_sql, payload=request())["turn"]
    result = turn_sql(
        f"SET ROLE service_role; SELECT chat_turn_operation('{FOREIGN}','chat-test','recover');"
    )
    assert json.loads(result)["items"] == []
    payload = json.dumps(finish(record))
    result = turn_sql(
        f"SET ROLE service_role; SELECT chat_turn_operation('{FOREIGN}','chat-test','complete','{payload}');"
    )
    assert not json.loads(result)["accepted"]
    assert turn_sql("SELECT count(*) FROM chat_messages;") == "1"


def test_foreign_unprocessed_and_deleted_documents_never_fall_back_to_general_chat(turn_sql):
    document = str(uuid4())
    turn_sql(
        f"INSERT INTO documents(id,patient_id,uploaded_by,uploaded_by_role,document_type,file_name,file_url,file_size_bytes,parse_status,ai_summary) VALUES('{document}','{FOREIGN}','{FOREIGN}','patient','other','synthetic.pdf','synthetic',10,'completed','Synthetic summary');"
    )
    assert "CHAT_DOCUMENT_UNAVAILABLE" in call(
        turn_sql, payload=request(document_id=document), succeeds=False
    )
    turn_sql(
        f"UPDATE documents SET patient_id='{PATIENT}',parse_status='processing' WHERE id='{document}';"
    )
    assert "CHAT_DOCUMENT_UNAVAILABLE" in call(
        turn_sql, payload=request(document_id=document), succeeds=False
    )
    turn_sql(f"DELETE FROM documents WHERE id='{document}';")
    assert "CHAT_DOCUMENT_UNAVAILABLE" in call(
        turn_sql, payload=request(document_id=document), succeeds=False
    )
    assert turn_sql("SELECT count(*) FROM chat_messages;") == "0"


@pytest.mark.parametrize("field", ["content", "language", "client_message_id"])
def test_begin_rejects_null_fields_explicitly(turn_sql, field):
    data = request()
    data[field] = None
    assert "CHAT_TURN_INVALID" in call(turn_sql, payload=data, succeeds=False)
    assert turn_sql("SELECT count(*) FROM chat_messages;") == "0"


def test_completed_turn_without_its_reply_replays_as_reply_unavailable(turn_sql):
    data = request()
    record = call(turn_sql, payload=data)["turn"]
    reply = call(turn_sql, "complete", finish(record))["message"]
    turn_sql(f"DELETE FROM chat_messages WHERE id='{reply['id']}';")
    replay = call(turn_sql, payload=data)
    assert replay["reply_unavailable"] and not replay["execute"]
    assert "assistant_message" not in replay


def test_073_is_re_runnable_and_keeps_grants(turn_sql):
    migration = (MIGRATIONS / "073_nora_turn_begin_validation.sql").read_text()
    turn_sql(migration)
    turn_sql(migration)
    assert (
        turn_sql(
            "SELECT has_function_privilege('anon','chat_turn_operation(uuid,text,text,jsonb)','EXECUTE');"
        )
        == "f"
    )


def expire(turn_sql):
    turn_sql("UPDATE chat_turns SET deadline_at=clock_timestamp()-interval '1 second';")


@pytest.mark.parametrize("asked,expected", [(70, 70), (1, 10), (500, 120), (None, 45)])
def test_deadline_is_the_requested_lease_clamped_to_ten_through_one_twenty_seconds(
    turn_sql, asked, expected
):
    data = request()
    if asked is None:
        del data["timeout_seconds"]
    else:
        data["timeout_seconds"] = asked
    data["request_hash"] = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    call(turn_sql, payload=data)
    seconds = float(
        turn_sql("SELECT extract(epoch FROM deadline_at - created_at) FROM chat_turns;")
    )
    assert expected - 1 <= seconds <= expected + 1


def test_finished_reply_just_past_the_deadline_is_kept_once(turn_sql):
    data = request()
    record = call(turn_sql, payload=data)["turn"]
    expire(turn_sql)
    result = call(turn_sql, "complete", finish(record))
    assert result["accepted"] and result["late"]
    assert turn_sql("SELECT status||'|'||coalesce(failure_code,'-') FROM chat_turns;") == (
        "completed|-"
    )
    assert turn_sql("SELECT count(*) FROM chat_messages WHERE role='assistant';") == "1"
    replay = call(turn_sql, payload=data)
    assert not replay["execute"] and replay["assistant_message"]["content"] == "Synthetic reply"
    # A second completion for the same lease cannot add another reply.
    assert not call(turn_sql, "complete", finish(record))["accepted"]
    assert turn_sql("SELECT count(*) FROM chat_messages WHERE role='assistant';") == "1"


def test_timely_completion_is_not_marked_late(turn_sql):
    record = call(turn_sql, payload=request())["turn"]
    assert call(turn_sql, "complete", finish(record))["late"] is False


def test_late_completion_after_the_socket_was_lost_keeps_the_reply(turn_sql):
    record = call(turn_sql, payload=request())["turn"]
    call(turn_sql, "interrupted", record)
    assert call(turn_sql, "complete", finish(record))["accepted"]


def test_late_completion_is_refused_once_the_turn_was_retried_dismissed_or_failed(turn_sql):
    data = request()
    original = call(turn_sql, payload=data)["turn"]
    expire(turn_sql)
    assert call(turn_sql, payload=data)["execute"]  # retried: the old lease is gone
    assert not call(turn_sql, "complete", finish(original))["accepted"]

    dismissed = request()
    record = call(turn_sql, "begin", dismissed, session="dismissed")["turn"]
    call(turn_sql, "interrupted", record, session="dismissed")
    call(turn_sql, "dismiss", dismissed, session="dismissed")
    assert not call(turn_sql, "complete", finish(record), session="dismissed")["accepted"]

    failed = request()
    record = call(turn_sql, "begin", failed, session="failed")["turn"]
    call(turn_sql, "failed", record, session="failed")
    assert not call(turn_sql, "complete", finish(record), session="failed")["accepted"]


def test_a_lapsed_lease_still_cannot_start_a_clinical_action(turn_sql):
    record = call(turn_sql, payload=request())["turn"]
    expire(turn_sql)
    assert not call(turn_sql, "actions", record)["accepted"]
    assert turn_sql("SELECT actions_started FROM chat_turns;") == "f"


def test_reply_after_an_uncertain_action_is_still_kept(turn_sql):
    record = call(turn_sql, payload=request())["turn"]
    assert call(turn_sql, "actions", record)["accepted"]
    expire(turn_sql)
    assert call(turn_sql, "complete", finish(record))["accepted"]
    assert turn_sql("SELECT status FROM chat_turns;") == "completed"


def test_074_is_re_runnable_and_keeps_grants(turn_sql):
    migration = (MIGRATIONS / "074_nora_late_completion.sql").read_text()
    turn_sql(migration)
    turn_sql(migration)
    for role in ("anon", "authenticated"):
        assert (
            turn_sql(
                f"SELECT has_function_privilege('{role}','chat_turn_operation(uuid,text,text,jsonb)','EXECUTE');"
            )
            == "f"
        )
    record = call(turn_sql, payload=request())["turn"]
    expire(turn_sql)
    assert call(turn_sql, "complete", finish(record))["late"]


# -- 077: a refused operation says why -------------------------------------------------


def reason(result):
    assert result["accepted"] is False
    return result["reason"]


def test_a_refusal_for_an_unknown_turn_is_not_found(turn_sql):
    record = call(turn_sql, payload=request())["turn"]
    unknown = {**record, "id": str(uuid4())}
    for action in ("actions", "complete", "failed", "interrupted"):
        assert reason(call(turn_sql, action, finish(unknown))) == "not_found"


def test_a_refusal_for_another_patients_turn_is_not_found_and_leaks_nothing(turn_sql):
    record = call(turn_sql, payload=request())["turn"]
    other = call(turn_sql, "actions", record, session="chat-test")  # own turn: accepted
    assert other["accepted"]
    body = json.dumps(record).replace("'", "''")
    foreign = json.loads(
        turn_sql(
            f"SET ROLE service_role; SELECT chat_turn_operation('{FOREIGN}','chat-test','actions','{body}');"
        )
    )
    assert reason(foreign) == "not_found"
    assert set(foreign) == {"accepted", "reason"}


def test_a_refusal_in_another_conversation_is_session_mismatch(turn_sql):
    record = call(turn_sql, payload=request())["turn"]
    result = call(turn_sql, "actions", record, session="a-different-conversation")
    assert reason(result) == "session_mismatch"
    assert turn_sql("SELECT status FROM chat_turns;") == "processing"


def test_a_replaced_lease_is_lease_mismatch(turn_sql):
    data = request()
    original = call(turn_sql, payload=data)["turn"]
    expire(turn_sql)
    assert call(turn_sql, payload=data)["execute"]  # the retry takes a new lease
    assert reason(call(turn_sql, "actions", original)) == "lease_mismatch"
    assert reason(call(turn_sql, "complete", finish(original))) == "lease_mismatch"


def test_a_lapsed_lease_is_deadline_passed(turn_sql):
    record = call(turn_sql, payload=request())["turn"]
    expire(turn_sql)
    assert reason(call(turn_sql, "actions", record)) == "deadline_passed"


def test_other_statuses_are_named(turn_sql):
    failed = call(turn_sql, "begin", request(), session="s-failed")["turn"]
    call(turn_sql, "failed", failed, session="s-failed")
    assert reason(call(turn_sql, "actions", failed, session="s-failed")) == "status:failed"

    done_data = request()
    done = call(turn_sql, "begin", done_data, session="s-done")["turn"]
    call(turn_sql, "complete", finish(done), session="s-done")
    assert reason(call(turn_sql, "actions", done, session="s-done")) == "status:completed"
    assert reason(call(turn_sql, "complete", finish(done), session="s-done")) == (
        "status:completed"
    )

    interrupted = call(turn_sql, "begin", request(), session="s-int")["turn"]
    call(turn_sql, "interrupted", interrupted, session="s-int")
    assert reason(call(turn_sql, "actions", interrupted, session="s-int")) == ("status:interrupted")


def test_a_refusal_changes_nothing(turn_sql):
    record = call(turn_sql, payload=request())["turn"]
    before = turn_sql("SELECT status||attempt||lease||updated_at FROM chat_turns;")
    call(turn_sql, "actions", {**record, "id": str(uuid4())})
    call(turn_sql, "actions", record, session="elsewhere")
    assert turn_sql("SELECT status||attempt||lease||updated_at FROM chat_turns;") == before


# -- candidate causes of CHAT_TURN_EXPIRED that must NOT refuse a live lease -------------


def test_a_second_socket_recovering_or_dismissing_does_not_disturb_a_running_turn(turn_sql):
    data = request()
    record = call(turn_sql, payload=data)["turn"]
    for _ in range(3):
        assert call(turn_sql, "recover")["items"][0]["status"] == "processing"
        assert not call(turn_sql, "dismiss", data)["accepted"]  # running work cannot be hidden
    assert call(turn_sql, "actions", record)["accepted"]
    assert call(turn_sql, "complete", finish(record))["accepted"]


def test_a_second_begin_with_the_same_message_id_keeps_the_running_lease(turn_sql):
    data = request()
    record = call(turn_sql, payload=data)["turn"]
    again = call(turn_sql, payload=data)
    assert not again["execute"]
    assert turn_sql("SELECT lease::text FROM chat_turns;") == record["lease"]
    assert call(turn_sql, "actions", record)["accepted"]


def test_a_begin_with_a_different_message_id_is_busy_and_keeps_the_lease(turn_sql):
    record = call(turn_sql, payload=request())["turn"]
    assert "CHAT_TURN_BUSY" in call(turn_sql, payload=request(), succeeds=False)
    assert call(turn_sql, "complete", finish(record))["accepted"]


def test_failing_then_completing_the_same_lease_is_the_only_refused_order(turn_sql):
    # The model-fallback path: a failure marker followed by a finished reply on one lease.
    record = call(turn_sql, payload=request())["turn"]
    call(turn_sql, "interrupted", record)  # a timeout wrapper's interruption
    assert call(turn_sql, "complete", finish(record))["accepted"]  # 074: the reply is kept
    again = call(turn_sql, payload=request(), session="fresh")["turn"]
    call(turn_sql, "failed", again, session="fresh")  # a hard failure is final
    assert reason(call(turn_sql, "complete", finish(again), session="fresh")) == ("status:failed")


def test_077_is_re_runnable_and_keeps_grants(turn_sql):
    migration = (MIGRATIONS / "077_chat_turn_rejection_reason.sql").read_text()
    turn_sql(migration)
    turn_sql(migration)
    for role in ("anon", "authenticated"):
        assert (
            turn_sql(
                f"SELECT has_function_privilege('{role}','chat_turn_operation(uuid,text,text,jsonb)','EXECUTE');"
            )
            == "f"
        )
    record = call(turn_sql, payload=request())["turn"]
    assert reason(call(turn_sql, "actions", {**record, "id": str(uuid4())})) == "not_found"


def test_a_caller_never_waits_on_the_conversation_lock_without_bound(turn_sql):
    """lock_timeout (5 s) is set by the function itself, below the backend's 10 s budget."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    holder_sql = (
        "BEGIN; SELECT pg_advisory_xact_lock(hashtextextended('chat_turn:'||"
        f"'{PATIENT}'||':chat-test',0)); SELECT pg_sleep(9); COMMIT;"
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        holder = pool.submit(turn_sql, holder_sql)
        time.sleep(1.5)
        started = time.monotonic()
        output = call(turn_sql, "recover", succeeds=False)
        waited = time.monotonic() - started
        holder.result()
    assert "lock timeout" in output and 4 <= waited < 8
    assert call(turn_sql, "recover")["items"] == []  # and it works again afterwards
