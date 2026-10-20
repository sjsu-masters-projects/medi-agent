"""Text-level guarantees of the LOC-003 translation schema migrations (079-081)."""

from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "src/app/db/migrations"
INTEGRITY = (MIGRATIONS / "080_message_translation_integrity.sql").read_text()
VERIFICATION = (MIGRATIONS / "081_care_plan_wording_verification.sql").read_text()


def _code(source: str) -> str:
    return "\n".join(line.split("--", 1)[0] for line in source.splitlines())


INTEGRITY_CODE = _code(INTEGRITY)
VERIFICATION_CODE = _code(VERIFICATION)


class TestDuplicatePrefixIsResolved:
    def test_english_display_facts_moved_off_the_shared_067_prefix(self) -> None:
        """Item 10: 067 holds one migration again, so a new collision there fails CI."""
        assert [path.name for path in MIGRATIONS.glob("067_*.sql")] == [
            "067_clinic_lists_and_roles.sql"
        ]
        assert (MIGRATIONS / "079_english_display_facts.sql").exists()

    def test_the_renumbered_file_is_re_runnable_because_the_ledger_keys_on_the_name(self) -> None:
        renumbered = (MIGRATIONS / "079_english_display_facts.sql").read_text()
        assert "ADD COLUMN IF NOT EXISTS display_locale" in renumbered
        assert "ADD COLUMN IF NOT EXISTS display_value" in renumbered

    def test_the_validator_no_longer_grandfathers_067(self) -> None:
        from scripts import validate_migrations

        assert 67 not in validate_migrations.LEGACY_SHARED_SEQUENCES


class TestMessageTranslationIntegrity:
    def test_both_source_tables_clean_up_their_translations(self) -> None:
        """Item 9: the trigger pair is what a polymorphic foreign key cannot be."""
        for table, label in (
            ("public.care_conversation_messages", "care_team_conversation_messages"),
            ("public.chat_messages", "chat_messages"),
        ):
            assert f"AFTER DELETE ON {table}" in INTEGRITY_CODE
            assert f"private.delete_message_translations('{label}')" in INTEGRITY_CODE

    def test_triggers_are_replaceable_so_the_migration_can_be_re_run(self) -> None:
        assert INTEGRITY_CODE.count("DROP TRIGGER IF EXISTS message_translations_cleanup") == 2
        assert "CREATE OR REPLACE FUNCTION private.delete_message_translations()" in INTEGRITY_CODE
        assert "CREATE OR REPLACE FUNCTION public.purge_message_translations(" in INTEGRITY_CODE

    def test_the_retention_rule_removes_orphans_and_expired_failure_markers(self) -> None:
        assert "guard_failure_code = 'model_error'" in INTEGRITY_CODE
        assert "p_failure_marker_max_age" in INTEGRITY_CODE
        assert "'orphans_removed'" in INTEGRITY_CODE
        assert "'expired_failure_markers_removed'" in INTEGRITY_CODE

    def test_the_retention_rule_keeps_successful_translations(self) -> None:
        """A kept translation costs nothing; re-translating a reopened message costs a call."""
        assert "guard_passed = true" not in INTEGRITY_CODE.lower()
        assert "A successful translation is kept" in INTEGRITY

    def test_functions_are_definer_scoped_and_backend_only(self) -> None:
        assert INTEGRITY_CODE.count("SECURITY DEFINER SET search_path = ''") == 2
        assert (
            "REVOKE ALL ON FUNCTION private.delete_message_translations() "
            "FROM PUBLIC, anon, authenticated;" in INTEGRITY_CODE
        )
        assert (
            "REVOKE ALL ON FUNCTION public.purge_message_translations(interval) "
            "FROM PUBLIC, anon, authenticated;" in INTEGRITY_CODE
        )
        assert (
            "GRANT EXECUTE ON FUNCTION public.purge_message_translations(interval) TO service_role;"
            in INTEGRITY_CODE
        )

    def test_it_fails_closed_on_missing_triggers_or_browser_grants(self) -> None:
        assert INTEGRITY_CODE.count("RAISE EXCEPTION") == 3
        assert "has_function_privilege('anon'" in INTEGRITY_CODE
        assert "has_function_privilege('authenticated'" in INTEGRITY_CODE

    def test_it_runs_outside_an_explicit_transaction(self) -> None:
        for transaction in ("BEGIN;", "COMMIT;", "ROLLBACK;"):
            assert transaction not in INTEGRITY_CODE


class TestCarePlanWordingVerification:
    def test_both_columns_are_added_idempotently_as_objects(self) -> None:
        assert "ADD COLUMN IF NOT EXISTS back_translation jsonb" in VERIFICATION_CODE
        assert "ADD COLUMN IF NOT EXISTS wording_verification jsonb" in VERIFICATION_CODE
        assert VERIFICATION_CODE.count("jsonb_typeof") == 2

    def test_a_verified_item_must_carry_its_guard_outcome(self) -> None:
        assert "CHECK (NOT wording_verified OR wording_verification IS NOT NULL)" in (
            VERIFICATION_CODE
        )

    def test_the_constraint_does_not_rewrite_already_approved_rows(self) -> None:
        assert "NOT VALID" in VERIFICATION_CODE
        assert "IF NOT EXISTS (" in VERIFICATION_CODE

    def test_the_columns_say_they_are_not_trusted_at_publication(self) -> None:
        assert "publication re-runs the guards and never trusts this record" in VERIFICATION
        assert "fingerprint matches" in VERIFICATION

    def test_it_adds_no_table_and_so_no_new_grants(self) -> None:
        assert "CREATE TABLE" not in VERIFICATION_CODE
        assert "GRANT" not in VERIFICATION_CODE
