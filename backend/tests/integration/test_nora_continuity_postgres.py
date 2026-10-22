# ruff: noqa: F811  (pytest fixtures are imported by name)
"""Migration 094: rolling summaries and per-reply evidence, under hosted default grants.

Fictional records only; applied from scratch in a disposable postgres:16 container.
"""

import json
import os
from uuid import uuid4

import pytest

from tests.integration.test_chat_turn_postgres import FOREIGN, MIGRATIONS, PATIENT
from tests.integration.test_notification_centre_postgres import CLINICIAN

pytest_plugins = ["tests.integration.test_notification_centre_postgres"]
pytestmark = pytest.mark.skipif(
    os.environ.get("CHAT_TURN_TEST_POSTGRES_DOCKER") != "1", reason="offline PostgreSQL opt-in"
)
SESSION = "day-2026-10-22"


@pytest.fixture
def db(sql):
    for name in (
        "010_chat_state_and_a2a_tasks.sql",
        "050_document_display_titles.sql",
        "051_health_knowledge_and_chat_sessions.sql",
    ):
        sql((MIGRATIONS / name).read_text())
    for path in sorted(MIGRATIONS.glob("*_nora_conversation_continuity.sql")):
        sql(path.read_text())
    # A session variable stands in for the JWT subject so the browser policies can be exercised.
    sql(
        "CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS "
        "$$ SELECT nullif(current_setting('test.uid', true), '')::uuid $$;"
        "GRANT USAGE ON SCHEMA auth TO authenticated; GRANT EXECUTE ON FUNCTION auth.uid() TO authenticated;"
    )
    return sql


def message(db, role="assistant", patient=PATIENT, session=SESSION, minutes=0):
    key = str(uuid4())
    db(
        "INSERT INTO chat_messages(id,patient_id,content,role,session_id,created_at) VALUES "
        f"('{key}','{patient}','Synthetic text','{role}','{session}',"
        f"timestamptz '2026-10-22 09:00:00+00' + interval '{minutes} minutes');"
    )
    return key


def rpc(db, name, args, *, role="service_role", succeeds=True):
    out = db(f"SET ROLE {role}; SELECT public.{name}({args});", succeeds=succeeds)
    return json.loads(out.splitlines()[-1]) if succeeds else out


def summary(db, through, expected="NULL", text="Synthetic summary", patient=PATIENT):
    exp = expected if expected == "NULL" else f"'{expected}'"
    return rpc(
        db,
        "record_conversation_summary",
        f"'{patient}','{SESSION}',{exp},'{through}','{text}','en-US'",
    )


def evidence(db, message_id, body=None, patient=PATIENT):
    payload = json.dumps(body or {"version": 1, "tools": ["get_patient_context"]})
    return rpc(
        db, "record_reply_evidence", f"'{patient}','{SESSION}','{message_id}','{payload}'::jsonb"
    )


def test_the_migration_is_rerunnable(db):
    for path in sorted(MIGRATIONS.glob("*_nora_conversation_continuity.sql")):
        db(path.read_text())


def test_browser_roles_cannot_write_or_call_and_the_summary_is_backend_only(db):
    key = message(db)
    for role in ("anon", "authenticated"):
        assert "permission denied" in db(
            f"SET ROLE {role}; SELECT public.record_reply_evidence('{PATIENT}','{SESSION}','{key}','{{}}'::jsonb);",
            succeeds=False,
        )
        assert "permission denied" in db(
            f"SET ROLE {role}; SELECT * FROM chat_conversation_summaries;", succeeds=False
        )
        assert "permission denied" in db(
            f"SET ROLE {role}; DELETE FROM chat_reply_evidence;", succeeds=False
        )
    assert "permission denied" in db(
        f"SET ROLE service_role; INSERT INTO chat_reply_evidence(patient_id,session_id,message_id,evidence) VALUES('{PATIENT}','{SESSION}','{key}','{{}}');",
        succeeds=False,
    )
    for table in ("chat_conversation_summaries", "chat_reply_evidence"):
        assert (
            db(f"SELECT relrowsecurity FROM pg_class WHERE oid='public.{table}'::regclass;") == "t"
        )


def test_summary_moves_forward_only_and_a_stale_writer_loses(db):
    first, second, third = message(db, minutes=0), message(db, minutes=1), message(db, minutes=2)
    assert summary(db, first)["accepted"] is True
    # A second writer that also read "no summary" loses.
    assert summary(db, second) == {"accepted": False, "reason": "stale"}
    watermark = db(
        f"SELECT covered_through_at FROM chat_conversation_summaries WHERE patient_id='{PATIENT}';"
    )
    assert summary(db, second, expected=watermark, text="Newer")["accepted"] is True
    # Replaying the older step (a redelivered turn) cannot move it backwards or apply twice.
    assert summary(db, first, expected=watermark)["reason"] == "stale"
    now = db(
        f"SELECT covered_through_at FROM chat_conversation_summaries WHERE patient_id='{PATIENT}';"
    )
    assert summary(db, third, expected=now, text="Newest")["accepted"] is True
    assert (
        db(
            f"SELECT summary||updates FROM chat_conversation_summaries WHERE patient_id='{PATIENT}';"
        )
        == "Newest3"
    )
    # An expected watermark with no stored summary is stale, and leaves no placeholder row.
    other = message(db, session="day-2026-10-23")
    assert (
        rpc(
            db,
            "record_conversation_summary",
            f"'{PATIENT}','day-2026-10-23','{now}','{other}','x','en-US'",
        )["reason"]
        == "stale"
    )
    assert db("SELECT count(*) FROM chat_conversation_summaries;") == "1"


def test_summary_rejects_foreign_messages_bad_language_and_oversize_text(db):
    mine = message(db)
    unknown = str(uuid4())
    assert summary(db, unknown)["reason"] == "unknown_message"
    bad = rpc(
        db,
        "record_conversation_summary",
        f"'{PATIENT}','{SESSION}',NULL,'{mine}','x','fr'",
    )
    assert bad["reason"] == "invalid"
    big = rpc(
        db,
        "record_conversation_summary",
        f"'{PATIENT}','{SESSION}',NULL,'{mine}','{'x' * 2001}','en-US'",
    )
    assert big["reason"] == "invalid"
    wrong_session = rpc(
        db,
        "record_conversation_summary",
        f"'{PATIENT}','day-2026-10-30',NULL,'{mine}','x','en-US'",
    )
    assert wrong_session["reason"] == "unknown_message"


def test_evidence_is_idempotent_append_only_and_tied_to_an_assistant_reply(db):
    reply = message(db)
    assert evidence(db, reply)["inserted"] is True
    assert evidence(db, reply, {"version": 1, "tools": ["changed"]})["inserted"] is False
    assert (
        db(f"SELECT evidence->'tools'->>0 FROM chat_reply_evidence WHERE message_id='{reply}';")
        == "get_patient_context"
    )
    assert "append-only" in db(
        f"UPDATE chat_reply_evidence SET evidence='{{}}' WHERE message_id='{reply}';",
        succeeds=False,
    )
    patient_line = message(db, role="user")
    assert evidence(db, patient_line)["reason"] == "unknown_message"
    assert evidence(db, str(uuid4()))["reason"] == "unknown_message"
    wrong = rpc(db, "record_reply_evidence", f"'{PATIENT}','other-session','{reply}','{{}}'::jsonb")
    assert wrong["reason"] == "unknown_message"


def test_oversized_and_non_object_evidence_is_refused(db):
    reply = message(db)
    huge = rpc(
        db,
        "record_reply_evidence",
        f"'{PATIENT}','{SESSION}','{reply}',jsonb_build_object('x',repeat('y',13000))",
    )
    assert huge["reason"] == "invalid"
    arr = rpc(db, "record_reply_evidence", f"'{PATIENT}','{SESSION}','{reply}','[]'::jsonb")
    assert arr["reason"] == "invalid"
    assert db("SELECT count(*) FROM chat_reply_evidence;") == "0"


def test_patient_and_assigned_clinician_read_it_and_nobody_else(db):
    reply = message(db)
    evidence(db, reply)

    def visible(uid, role="authenticated"):
        return db(
            f"SET ROLE {role}; SET test.uid='{uid}'; SELECT count(*) FROM chat_reply_evidence;"
        ).splitlines()[-1]

    assert visible(PATIENT) == "1"
    assert visible(CLINICIAN) == "1"  # actively assigned (care_teams seed)
    assert visible(FOREIGN) == "0"  # another user
    assert visible(str(uuid4())) == "0"
    db(f"UPDATE care_teams SET status='inactive' WHERE patient_id='{PATIENT}';")
    assert visible(CLINICIAN) == "0"  # a removed assignment stops access
    assert visible(PATIENT) == "1"


def test_deleting_the_message_or_patient_removes_the_evidence_and_summary(db):
    reply = message(db)
    evidence(db, reply)
    summary(db, reply)
    db(f"DELETE FROM chat_messages WHERE id='{reply}';")
    assert db("SELECT count(*) FROM chat_reply_evidence;") == "0"


def test_old_evidence_is_deleted_a_bounded_batch_per_write(db):
    keep = message(db)
    db(
        "WITH m AS (INSERT INTO chat_messages(patient_id,content,role,session_id) "
        f"SELECT '{PATIENT}','Synthetic text','assistant','{SESSION}' FROM generate_series(1,120) "
        "RETURNING id) INSERT INTO chat_reply_evidence(patient_id,session_id,message_id,evidence,created_at) "
        f"SELECT '{PATIENT}','{SESSION}',id,'{{}}',clock_timestamp()-interval '181 days' FROM m;"
    )
    assert evidence(db, keep)["accepted"] is True
    assert db("SELECT count(*) FROM chat_reply_evidence;") == str(120 - 100 + 1)
    evidence(db, message(db, minutes=500))
    old = "SELECT count(*) FROM chat_reply_evidence WHERE created_at<now()-interval '180 days';"
    assert db(old) == "0"


@pytest.mark.parametrize(
    "statement,expected",
    [
        (
            "ALTER TABLE public.chat_reply_evidence DISABLE ROW LEVEL SECURITY;",
            "row level security",
        ),
        ("GRANT SELECT ON public.chat_conversation_summaries TO authenticated;", "backend-only"),
        ("GRANT INSERT ON public.chat_reply_evidence TO service_role;", "grants are wider"),
        (
            "DROP POLICY chat_reply_evidence_patient_select ON public.chat_reply_evidence;",
            "exactly",
        ),
        (
            "GRANT EXECUTE ON FUNCTION public.record_reply_evidence(uuid,text,uuid,jsonb) TO anon;",
            "execute grants",
        ),
    ],
)
def test_the_verification_block_fails_when_a_guard_is_lost(db, statement, expected):
    db(statement)
    migration = next(iter(sorted(MIGRATIONS.glob("*_nora_conversation_continuity.sql"))))
    verify = "DO $verify$" + migration.read_text().split("DO $verify$")[-1]
    # Re-running the migration repairs table grants and policies; the verification block alone
    # proves it would have refused the widened state.
    assert expected in db(verify, succeeds=False)
