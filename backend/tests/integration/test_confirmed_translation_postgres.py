"""Atomic confirmed messages through the real clinic-authorized send RPC, locally only."""

import json
import os
from uuid import uuid4

import pytest

from tests.integration import test_care_conversation_postgres as conversation_contract
from tests.integration.test_care_conversation_postgres import (
    CLINICIAN,
    MIGRATION,
    OTHER,
    PATIENT,
    open_thread,
)

postgres = conversation_contract.postgres
source_sql = conversation_contract.sql

pytestmark = pytest.mark.skipif(
    os.environ.get("CARE_CONVERSATION_TEST_POSTGRES_DOCKER") != "1",
    reason="explicit disposable Docker PostgreSQL opt-in required",
)


@pytest.fixture
def confirmed_db(source_sql):
    sql = source_sql
    sql((MIGRATION.parent / "068_message_translations.sql").read_text())
    sql((MIGRATION.parent / "088_confirmed_message_translation.sql").read_text())
    sql(f"UPDATE patients SET preferred_language='es-MX' WHERE id='{PATIENT}';")
    thread = open_thread(sql)
    payload = {
        "conversation_id": thread["id"],
        "client_message_id": str(uuid4()),
        "body": "Take 500 mg daily",
        "confirmed_translation": {
            "text": "Toma 500 mg cada día",
            "source_locale": "en-US",
            "locale": "es-MX",
            "model_id": "synthetic-test-model",
        },
    }
    return sql, payload


def send(
    sql, payload, *, actor=CLINICIAN, role="clinician", database_role="service_role", succeeds=True
):
    encoded = json.dumps(payload).replace("'", "''")
    return sql(
        f"SET ROLE {database_role}; SELECT public.care_conversation_confirmed_operation("
        f"'{actor}','{role}','send','{encoded}'::jsonb); RESET ROLE;",
        succeeds=succeeds,
    )


def test_exact_wording_and_message_commit_together(confirmed_db):
    sql, payload = confirmed_db
    message = json.loads(send(sql, payload))
    assert message["translation"] == payload["confirmed_translation"]["text"]
    assert message["translation_guard_passed"] is True
    assert sql("SELECT count(*) FROM care_conversation_messages;") == "1"
    assert sql("SELECT clinician_confirmed FROM message_translations;") == "t"


def test_identical_retry_is_one_message_and_translation(confirmed_db):
    sql, payload = confirmed_db
    first = json.loads(send(sql, payload))
    assert json.loads(send(sql, payload))["id"] == first["id"]
    assert sql("SELECT count(*) FROM care_conversation_messages;") == "1"
    assert sql("SELECT count(*) FROM message_translations;") == "1"


def test_retry_cannot_replace_the_approved_translation(confirmed_db):
    sql, payload = confirmed_db
    send(sql, payload)
    payload["confirmed_translation"]["text"] = "Otro texto con 500 mg"
    assert "retry mismatch" in send(sql, payload, succeeds=False)
    assert sql("SELECT translated_text FROM message_translations;") == "Toma 500 mg cada día"


def test_translation_failure_rolls_back_message_and_audit(confirmed_db):
    sql, payload = confirmed_db
    before = sql("SELECT count(*) FROM care_conversation_audit_events;")
    sql("""
      CREATE FUNCTION public.synthetic_fail_translation() RETURNS trigger LANGUAGE plpgsql
      AS $$ BEGIN RAISE EXCEPTION 'synthetic translation write failure'; END $$;
      CREATE TRIGGER synthetic_fail_translation BEFORE INSERT ON message_translations
        FOR EACH ROW EXECUTE FUNCTION public.synthetic_fail_translation();
    """)
    assert "synthetic translation write failure" in send(sql, payload, succeeds=False)
    assert sql("SELECT count(*) FROM care_conversation_messages;") == "0"
    assert sql("SELECT count(*) FROM message_translations;") == "0"
    assert sql("SELECT count(*) FROM care_conversation_audit_events;") == before


@pytest.mark.parametrize("actor,role", [(PATIENT, "patient"), (OTHER, "clinician")])
def test_other_actor_cannot_confirm_this_thread(confirmed_db, actor, role):
    sql, payload = confirmed_db
    send(sql, payload, actor=actor, role=role, succeeds=False)
    assert sql("SELECT count(*) FROM care_conversation_messages;") == "0"


def test_patient_language_change_rolls_back_delivery(confirmed_db):
    sql, payload = confirmed_db
    sql(f"UPDATE patients SET preferred_language='en-US' WHERE id='{PATIENT}';")
    assert "language changed" in send(sql, payload, succeeds=False)
    assert sql("SELECT count(*) FROM care_conversation_messages;") == "0"


def test_stub_confirmation_is_rejected_in_sql(confirmed_db):
    sql, payload = confirmed_db
    payload["confirmed_translation"]["model_id"] = "offline-translation-stub"
    assert "Invalid confirmed wording" in send(sql, payload, succeeds=False)
    assert sql("SELECT count(*) FROM care_conversation_messages;") == "0"


@pytest.mark.parametrize("database_role", ["anon", "authenticated"])
def test_browser_roles_cannot_confirm(confirmed_db, database_role):
    sql, payload = confirmed_db
    assert "permission denied" in send(sql, payload, database_role=database_role, succeeds=False)


def test_migration_rerun_retains_a_confirmation(confirmed_db):
    sql, payload = confirmed_db
    send(sql, payload)
    sql((MIGRATION.parent / "088_confirmed_message_translation.sql").read_text())
    assert sql("SELECT count(*) FROM message_translations WHERE clinician_confirmed;") == "1"


def test_original_only_delivery_is_atomic_persistent_and_retry_safe(confirmed_db):
    sql, payload = confirmed_db
    payload.pop("confirmed_translation")
    payload["original_source_locale"] = "en-US"
    first = json.loads(send(sql, payload))
    assert "translation" not in first
    assert json.loads(send(sql, payload))["id"] == first["id"]
    assert sql("SELECT count(*) FROM care_conversation_messages;") == "1"
    assert sql("SELECT guard_failure_code FROM message_translations;") == "original_only"
    assert sql("SELECT guard_passed FROM message_translations;") == "f"


def test_original_only_retry_cannot_turn_a_confirmed_message_into_fallback(confirmed_db):
    sql, payload = confirmed_db
    send(sql, payload)
    payload.pop("confirmed_translation")
    payload["original_source_locale"] = "en-US"
    assert "retry mismatch" in send(sql, payload, succeeds=False)
    assert sql("SELECT clinician_confirmed FROM message_translations;") == "t"


@pytest.mark.parametrize("original_only", [False, True])
def test_automatic_writes_cannot_replace_a_delivery_decision(confirmed_db, original_only):
    sql, payload = confirmed_db
    if original_only:
        payload.pop("confirmed_translation")
        payload["original_source_locale"] = "en-US"
    send(sql, payload)
    before = sql("SELECT translated_text FROM message_translations;")
    error = sql(
        "UPDATE message_translations SET translated_text='unsafe replacement';", succeeds=False
    )
    assert "delivery wording is immutable" in error
    assert sql("SELECT translated_text FROM message_translations;") == before
