"""Operator-run, disposable PostgreSQL contract tests for LOC-003 migrations 080-082.

What these pin down, against the real migration bytes:

* 080 — the cleanup triggers do what the foreign key a polymorphic ``source_table`` cannot
  express would have done, the retention rule removes only what it claims to, and no
  browser role can run it.
* 081 — a verified item must carry its guard outcome, and a row approved before the
  migration is not rewritten by it.
* 082 — a fact records the model that translated it, and an evidence gloss can be stored as
  a translation while the widened check still rejects anything else.

No remote database, network or model call is involved.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import pytest

from tests.integration.supabase_roles import create_roles_sql

pytestmark = pytest.mark.skipif(
    os.environ.get("LOC003_TEST_POSTGRES") != "1",
    reason="disposable PostgreSQL contract check is explicitly opt-in",
)
MIGRATIONS = Path(__file__).resolve().parents[2] / "src/app/db/migrations"

PATIENT = "00000000-0000-0000-0000-0000000000a1"
CLINICIAN = "00000000-0000-0000-0000-0000000000a2"
CONVERSATION = "00000000-0000-0000-0000-0000000000a3"
MESSAGE = "00000000-0000-0000-0000-0000000000a4"
CHAT_MESSAGE = "00000000-0000-0000-0000-0000000000a5"
PLAN = "00000000-0000-0000-0000-0000000000a6"
ITEM = "00000000-0000-0000-0000-0000000000a7"
FACT = "00000000-0000-0000-0000-0000000000a8"
EXCERPT = "00000000-0000-0000-0000-0000000000a9"

CARE_TABLE = "care_team_conversation_messages"


@pytest.fixture
def sql(tmp_path: Path):
    """An isolated cluster carrying only what 080 and 081 touch."""
    programs = {name: shutil.which(name) for name in ("initdb", "pg_ctl", "psql")}
    docker_mode = os.environ.get("LOC003_TEST_POSTGRES_DOCKER") == "1"
    docker = shutil.which("docker")
    if docker_mode and not docker:
        pytest.fail("docker is required for the opt-in container check")
    if not docker_mode and not all(programs.values()):
        pytest.fail("initdb, pg_ctl and psql are required for this local check")
    data = tmp_path / "data"
    container = None
    # macOS limits Unix socket paths to 103 bytes; pytest's tmp_path is longer.
    sockets = tempfile.TemporaryDirectory(prefix="loc003-pg-", dir="/tmp")
    if docker_mode:
        container = f"mediagent-loc003-test-{uuid4().hex}"
        subprocess.run(
            [
                docker,
                "run",
                "--detach",
                "--pull=never",
                "--network=none",
                "--name",
                container,
                "--env",
                "POSTGRES_HOST_AUTH_METHOD=trust",
                "postgres:16",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        try:
            readiness = (
                'test "$(head -n 1 /var/lib/postgresql/data/postmaster.pid)" = 1 '
                "&& pg_isready -U postgres"
            )
            for _ in range(100):
                ready = subprocess.run(
                    [docker, "exec", container, "sh", "-c", readiness],
                    capture_output=True,
                    timeout=5,
                )
                if ready.returncode == 0:
                    break
                time.sleep(0.1)
            else:
                pytest.fail("Disposable PostgreSQL container did not become ready")
        except BaseException:
            subprocess.run([docker, "rm", "--force", container], check=True, capture_output=True)
            sockets.cleanup()
            raise
        command = [docker, "exec", "--interactive", container, "psql", "-U", "postgres"]
    else:
        # The superuser is named postgres so the local cluster matches the container one,
        # and LC_ALL is pinned because PostgreSQL 18 on macOS refuses to start without a
        # valid locale ("postmaster became multithreaded during startup").
        environment = {**os.environ, "LC_ALL": "C"}
        initialization = subprocess.run(
            [programs["initdb"], "-D", str(data), "-A", "trust", "-U", "postgres"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        if initialization.returncode:
            sockets.cleanup()
            pytest.fail(f"Disposable PostgreSQL initialization failed: {initialization.stderr}")
        subprocess.run(
            [
                programs["pg_ctl"],
                "-D",
                str(data),
                "-l",
                str(tmp_path / "server.log"),
                "-o",
                f"-k {sockets.name} -h ''",
                "-w",
                "start",
            ],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        command = [programs["psql"], "-h", sockets.name, "-U", "postgres"]
    command += ["-X", "-d", "postgres", "-At", "-q", "-v", "ON_ERROR_STOP=1"]

    def execute(statement: str, *, succeeds: bool = True) -> str:
        result = subprocess.run(
            command,
            input=f"SET statement_timeout='8s';\n{statement}",
            capture_output=True,
            text=True,
            timeout=12,
        )
        assert (result.returncode == 0) is succeeds, result.stderr
        return result.stdout.strip() if succeeds else result.stderr

    try:
        execute(create_roles_sql(service_role_bypasses_rls=False))
        # The two source tables and the care-plan item table, reduced to the columns these
        # migrations touch. The migrations themselves are never rewritten.
        execute("""
          CREATE SCHEMA auth;
          CREATE TABLE auth.users(id uuid PRIMARY KEY);
          CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT null::uuid $$;
          CREATE SCHEMA private;
          REVOKE ALL ON SCHEMA private FROM PUBLIC, anon, authenticated;
          CREATE TABLE public.care_conversation_messages(
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id uuid NOT NULL,
            body text NOT NULL);
          CREATE TABLE public.chat_messages(
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            patient_id uuid NOT NULL,
            content text NOT NULL);
          CREATE TABLE public.care_plan_items(
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            plan_version_id uuid NOT NULL,
            wording jsonb,
            wording_verified boolean NOT NULL DEFAULT false);
          CREATE TABLE public.clinical_facts(
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            patient_id uuid NOT NULL,
            fact_type text,
            value jsonb,
            display_locale text,
            display_value jsonb);
        """)
        execute((MIGRATIONS / "068_message_translations.sql").read_text())
        execute((MIGRATIONS / "080_message_translation_integrity.sql").read_text())
        execute((MIGRATIONS / "081_care_plan_wording_verification.sql").read_text())
        execute((MIGRATIONS / "082_loc003_display_provenance.sql").read_text())
        execute(f"""
          INSERT INTO public.care_conversation_messages(id, conversation_id, body)
            VALUES ('{MESSAGE}', '{CONVERSATION}', 'Tomo 500 mg cada dia');
          INSERT INTO public.chat_messages(id, patient_id, content)
            VALUES ('{CHAT_MESSAGE}', '{PATIENT}', 'Me siento mejor');
          INSERT INTO public.care_plan_items(id, plan_version_id) VALUES ('{ITEM}', '{PLAN}');
          INSERT INTO public.clinical_facts(id, patient_id, fact_type, value)
            VALUES ('{FACT}', '{PATIENT}', 'obligation', '{{"description": "Tome agua"}}'::jsonb);
        """)
        yield execute
    finally:
        if container:
            subprocess.run(
                [docker, "rm", "--force", container], check=True, capture_output=True, timeout=15
            )
        else:
            subprocess.run(
                [programs["pg_ctl"], "-D", str(data), "-m", "immediate", "-w", "stop"],
                check=False,
                capture_output=True,
            )
        sockets.cleanup()


def translation(
    sql,
    source_table: str = CARE_TABLE,
    message_id: str = MESSAGE,
    *,
    guard_failure_code: str | None = None,
    age: str = "0 minutes",
) -> None:
    code = "NULL" if guard_failure_code is None else f"'{guard_failure_code}'"
    sql(f"""
      INSERT INTO public.message_translations(
        source_table, source_message_id, source_locale, target_locale,
        translated_text, guard_passed, guard_failure_code, translated_at)
      VALUES ('{source_table}', '{message_id}', 'es-MX', 'en-US',
        'I take 500 mg every day', {guard_failure_code is None}, {code},
        now() - interval '{age}');
    """)


def count(sql, where: str = "true") -> int:
    return int(sql(f"SELECT count(*) FROM public.message_translations WHERE {where}"))


def purge(sql, max_age: str = "7 days") -> dict:
    return json.loads(
        sql(f"SET ROLE service_role; SELECT public.purge_message_translations('{max_age}');")
    )


# ── 080: the cleanup triggers stand in for the foreign key ────────────────


def test_deleting_a_care_team_message_deletes_its_translations(sql) -> None:
    translation(sql)
    sql(f"DELETE FROM public.care_conversation_messages WHERE id = '{MESSAGE}'")
    assert count(sql) == 0


def test_deleting_a_chat_message_deletes_its_translations(sql) -> None:
    translation(sql, "chat_messages", CHAT_MESSAGE)
    sql(f"DELETE FROM public.chat_messages WHERE id = '{CHAT_MESSAGE}'")
    assert count(sql) == 0


def test_only_that_messages_translations_go(sql) -> None:
    """The stored label and the physical table name differ; the trigger must not confuse them."""
    translation(sql)
    translation(sql, "chat_messages", CHAT_MESSAGE)
    sql(f"DELETE FROM public.care_conversation_messages WHERE id = '{MESSAGE}'")
    assert count(sql) == 1
    assert sql("SELECT source_table FROM public.message_translations") == "chat_messages"


def test_a_chat_message_id_matching_a_care_message_id_is_not_collateral(sql) -> None:
    other = "00000000-0000-0000-0000-0000000000b1"
    sql(f"""
      INSERT INTO public.care_conversation_messages(id, conversation_id, body)
        VALUES ('{other}', '{CONVERSATION}', 'Hola');
      INSERT INTO public.chat_messages(id, patient_id, content)
        VALUES ('{other}', '{PATIENT}', 'Hola');
    """)
    translation(sql, "chat_messages", other)
    sql(f"DELETE FROM public.care_conversation_messages WHERE id = '{other}'")
    assert count(sql) == 1


def test_every_target_language_of_the_message_goes(sql) -> None:
    translation(sql)
    sql(f"""
      INSERT INTO public.message_translations(
        source_table, source_message_id, source_locale, target_locale, translated_text)
      VALUES ('{CARE_TABLE}', '{MESSAGE}', 'en-US', 'es-MX', 'Toma 500 mg cada dia');
    """)
    assert count(sql) == 2
    sql(f"DELETE FROM public.care_conversation_messages WHERE id = '{MESSAGE}'")
    assert count(sql) == 0


# ── 080: the retention rule ───────────────────────────────────────────────


def test_an_orphan_from_before_the_triggers_is_removed(sql) -> None:
    orphan = "00000000-0000-0000-0000-0000000000c1"
    translation(sql, message_id=orphan)
    assert purge(sql)["orphans_removed"] == 1
    assert count(sql) == 0


def test_an_expired_failure_marker_is_removed(sql) -> None:
    translation(sql, guard_failure_code="model_error", age="8 days")
    assert purge(sql)["expired_failure_markers_removed"] == 1
    assert count(sql) == 0


def test_a_fresh_failure_marker_is_kept_so_the_retry_rule_still_holds(sql) -> None:
    translation(sql, guard_failure_code="model_error", age="30 minutes")
    assert purge(sql) == {"orphans_removed": 0, "expired_failure_markers_removed": 0}
    assert count(sql) == 1


def test_a_successful_translation_is_kept_however_old(sql) -> None:
    """Re-translating a reopened message would spend a model call to reproduce this text."""
    translation(sql, age="400 days")
    assert purge(sql) == {"orphans_removed": 0, "expired_failure_markers_removed": 0}
    assert count(sql) == 1


def test_a_guard_failure_that_is_not_a_model_error_is_not_retry_state(sql) -> None:
    translation(sql, guard_failure_code="numbers_changed", age="400 days")
    assert purge(sql)["expired_failure_markers_removed"] == 0
    assert count(sql) == 1


def test_the_failure_marker_age_boundary_is_the_callers(sql) -> None:
    translation(sql, guard_failure_code="model_error", age="2 days")
    assert purge(sql, "7 days")["expired_failure_markers_removed"] == 0
    assert purge(sql, "1 day")["expired_failure_markers_removed"] == 1


def test_the_purge_is_safe_to_run_twice(sql) -> None:
    translation(sql, guard_failure_code="model_error", age="8 days")
    purge(sql)
    assert purge(sql) == {"orphans_removed": 0, "expired_failure_markers_removed": 0}


# ── Retention is backend only ─────────────────────────────────────────────
@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_a_browser_role_cannot_purge(sql, role: str) -> None:
    error = sql(f"SET ROLE {role}; SELECT public.purge_message_translations();", succeeds=False)
    assert "permission denied" in error


def test_service_role_can_purge(sql) -> None:
    assert purge(sql) == {"orphans_removed": 0, "expired_failure_markers_removed": 0}


# ── 081: a verification must carry its guard outcome ──────────────────────

RECORD = (
    '{"verified_at": "2026-10-19T00:00:00+00:00", "checks": {"numbers_match": true}, '
    '"checks_passed": true}'
)


def test_marking_wording_verified_without_a_record_is_rejected(sql) -> None:
    error = sql(
        f"UPDATE public.care_plan_items SET wording_verified = true WHERE id = '{ITEM}'",
        succeeds=False,
    )
    assert "Verified wording requires a verification record" in error


def test_marking_it_verified_with_a_record_is_accepted(sql) -> None:
    sql(f"""UPDATE public.care_plan_items
            SET wording_verified = true, wording_verification = '{RECORD}'
            WHERE id = '{ITEM}'""")
    assert sql(f"SELECT wording_verified FROM public.care_plan_items WHERE id = '{ITEM}'") == ("t")


def test_clearing_the_flag_may_clear_the_record(sql) -> None:
    """A re-translation drops both, because the record describes text that is now gone."""
    sql(f"""UPDATE public.care_plan_items
            SET wording_verified = true, wording_verification = '{RECORD}'
            WHERE id = '{ITEM}'""")
    sql(f"""UPDATE public.care_plan_items
            SET wording_verified = false, wording_verification = NULL
            WHERE id = '{ITEM}'""")
    assert count(sql) == 0


def test_a_record_must_be_an_object(sql) -> None:
    error = sql(
        f"""UPDATE public.care_plan_items SET wording_verification = '"checked"'
            WHERE id = '{ITEM}'""",
        succeeds=False,
    )
    assert "wording_verification_check" in error


def test_a_cached_back_translation_must_be_an_object(sql) -> None:
    error = sql(
        f"UPDATE public.care_plan_items SET back_translation = '[]' WHERE id = '{ITEM}'",
        succeeds=False,
    )
    assert "back_translation_check" in error


def test_a_row_approved_before_the_migration_is_not_rewritten(sql) -> None:
    """NOT VALID: the constraint governs new writes and leaves published history alone."""
    legacy = "00000000-0000-0000-0000-0000000000d1"
    sql(f"""
      ALTER TABLE public.care_plan_items
        DISABLE TRIGGER care_plan_items_wording_verification_present;
      INSERT INTO public.care_plan_items(id, plan_version_id, wording_verified)
        VALUES ('{legacy}', '{PLAN}', true);
    """)
    sql((MIGRATIONS / "081_care_plan_wording_verification.sql").read_text())
    assert (
        sql(
            f"""SELECT wording_verification IS NULL FROM public.care_plan_items
            WHERE id = '{legacy}'"""
        )
        == "t"
    )


def test_legacy_verified_wording_allows_cache_updates_but_not_unrecorded_edits(sql) -> None:
    legacy = "00000000-0000-0000-0000-0000000000d2"
    sql(f"""
      ALTER TABLE public.care_plan_items DISABLE TRIGGER care_plan_items_wording_verification_present;
      INSERT INTO public.care_plan_items(id,plan_version_id,wording_verified)
        VALUES ('{legacy}','{PLAN}',true);
    """)
    sql((MIGRATIONS / "081_care_plan_wording_verification.sql").read_text())
    sql(
        f"UPDATE public.care_plan_items SET back_translation='{{\"cached\":true}}' WHERE id='{legacy}';"
    )
    assert (
        sql(f"SELECT wording_verification IS NULL FROM public.care_plan_items WHERE id='{legacy}';")
        == "t"
    )
    error = sql(
        f'UPDATE public.care_plan_items SET wording=\'{{"en-US":{{"title":"Changed"}}}}\' WHERE id=\'{legacy}\';',
        succeeds=False,
    )
    assert "requires a verification record" in error


def test_the_verification_migration_can_be_applied_twice(sql) -> None:
    sql((MIGRATIONS / "081_care_plan_wording_verification.sql").read_text())
    sql((MIGRATIONS / "081_care_plan_wording_verification.sql").read_text())
    assert (
        sql("""SELECT count(*) FROM pg_trigger
                  WHERE tgname = 'care_plan_items_wording_verification_present' AND NOT tgisinternal""")
        == "1"
    )


def test_the_integrity_migration_can_be_applied_twice(sql) -> None:
    sql((MIGRATIONS / "080_message_translation_integrity.sql").read_text())
    translation(sql)
    sql(f"DELETE FROM public.care_conversation_messages WHERE id = '{MESSAGE}'")
    assert count(sql) == 0


# ── 082: display provenance and the gloss store ───────────────────────────


def test_a_fact_records_the_model_that_translated_it(sql) -> None:
    sql(f"""UPDATE public.clinical_facts
            SET display_locale = 'es-MX',
                display_value = '{{"description": "Drink water"}}'::jsonb,
                display_model_id = 'gemini-test'
            WHERE id = '{FACT}'""")
    assert (
        sql(f"SELECT display_model_id FROM public.clinical_facts WHERE id = '{FACT}'")
        == "gemini-test"
    )


def test_an_untranslated_fact_records_no_model(sql) -> None:
    sql(f"UPDATE public.clinical_facts SET display_locale = 'es-MX' WHERE id = '{FACT}'")
    assert (
        sql(
            f"""SELECT display_value IS NULL AND display_model_id IS NULL
            FROM public.clinical_facts WHERE id = '{FACT}'"""
        )
        == "t"
    )


def test_an_evidence_gloss_can_be_stored_as_a_translation(sql) -> None:
    """Item 2: a gloss is the same record this table holds, not a second table."""
    sql(f"""
      INSERT INTO public.message_translations(
        source_table, source_message_id, source_locale, target_locale,
        translated_text, guard_passed, model_id)
      VALUES ('evidence_excerpt', '{EXCERPT}', 'es-MX', 'en-US',
        'Take 1 tablet', true, 'gemini-test');
    """)
    assert count(sql, "source_table = 'evidence_excerpt'") == 1


def test_the_widened_check_still_rejects_an_unknown_source(sql) -> None:
    error = sql(
        f"""INSERT INTO public.message_translations(
              source_table, source_message_id, source_locale, target_locale, translated_text)
            VALUES ('soap_notes', '{EXCERPT}', 'es-MX', 'en-US', 'x')""",
        succeeds=False,
    )
    assert "source_table" in error


def test_the_retention_sweep_leaves_glosses_alone(sql) -> None:
    """A gloss has no source message to be orphaned from; it must survive the sweep."""
    sql(f"""
      INSERT INTO public.message_translations(
        source_table, source_message_id, source_locale, target_locale, translated_text)
      VALUES ('evidence_excerpt', '{EXCERPT}', 'es-MX', 'en-US', 'Take 1 tablet');
    """)
    assert purge(sql) == {"orphans_removed": 0, "expired_failure_markers_removed": 0}
    assert count(sql, "source_table = 'evidence_excerpt'") == 1


def test_one_gloss_per_excerpt_and_language(sql) -> None:
    """The same printed sentence is glossed once, however many citations quote it."""
    insert = f"""INSERT INTO public.message_translations(
        source_table, source_message_id, source_locale, target_locale, translated_text)
      VALUES ('evidence_excerpt', '{EXCERPT}', 'es-MX', 'en-US', 'Take 1 tablet')"""
    sql(insert)
    assert "duplicate key" in sql(insert, succeeds=False)


def test_the_provenance_migration_can_be_applied_twice(sql) -> None:
    sql((MIGRATIONS / "082_loc003_display_provenance.sql").read_text())
    sql((MIGRATIONS / "082_loc003_display_provenance.sql").read_text())
    assert (
        sql("""SELECT count(*) FROM pg_constraint
                  WHERE conrelid = 'public.message_translations'::regclass
                    AND conname = 'message_translations_source_table_check'""")
        == "1"
    )
