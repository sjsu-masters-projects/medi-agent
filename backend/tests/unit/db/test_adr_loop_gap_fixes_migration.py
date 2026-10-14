"""Text-level guarantees of the ADR information-loop lifecycle migration (PV-001-C)."""

import re
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "src/app/db/migrations"
MIGRATION = (MIGRATIONS / "063_adr_information_loop_lifecycle.sql").read_text()


def _function(name: str) -> str:
    start = MIGRATION.index(f"CREATE OR REPLACE FUNCTION {name}(")
    return MIGRATION[start : MIGRATION.index("$$;", start)]


def test_it_is_the_only_lifecycle_migration_and_follows_the_ledger() -> None:
    assert [p.name for p in MIGRATIONS.glob("*_adr_information_loop_lifecycle.sql")] == [
        "063_adr_information_loop_lifecycle.sql"
    ]
    assert (MIGRATIONS / "062_chat_message_attachments.sql").exists()


def test_allowlists_are_supersets_with_the_new_type_and_source() -> None:
    event_types = MIGRATION.split("ADD CONSTRAINT notification_events_event_type_check")[1]
    event_types = event_types.split("DROP CONSTRAINT")[0]
    for kind in ("critical_result", "legacy_update", "adr_information_requested"):
        assert f"'{kind}'" in event_types
    assert "'adr_information_answered'" in event_types
    sources = MIGRATION.split("ADD CONSTRAINT notification_events_source_type_check")[1]
    assert "'adr_assessments','clinician_messages','adr_information_requests'" in sources
    assert "'adr_information_requests') THEN RETURN NULL" in _function(
        "private.notification_source"
    )


def test_actionability_follows_the_request_with_rule_l_and_a_history_only_alert() -> None:
    body = _function("private.notification_actionable")
    assert "IF e.source_type='adr_information_requests' THEN RETURN s->>'status'='pending'" in body
    assert "r.status='pending' AND r.created_at<=e.created_at" in body
    assert "WHEN 'adr_information_answered' THEN RETURN false" in body
    # The 059 critical-result branch is carried forward unchanged.
    assert (
        "WHEN 'critical_result' THEN RETURN p_role='clinician' AND s->>'review_status' IS DISTINCT FROM 'rejected'"
        in body
    )


def test_capture_uses_one_key_per_request_event_and_assessments_emit_review_only() -> None:
    body = _function("private.capture_notification_source")
    assert "v_key:='adr_information_requests:'||v_id||':requested'" in body
    assert "v_key:='adr_information_requests:'||v_id||':answered'" in body
    assert "TG_OP='INSERT' AND s->>'status'='pending'" in body
    assert "o->>'status'='pending' AND s->>'status'='answered'" in body
    assessment = body.split("WHEN 'adr_assessments' THEN")[1].split(
        "WHEN 'adr_information_requests'"
    )[0]
    assert "adr_information_requested" not in assessment
    assert "v_kind:='adr_review'" in assessment
    assert "'information_request_id',v_id" in body
    assert (
        "CREATE TRIGGER notification_capture AFTER INSERT OR UPDATE ON public.adr_information_requests"
        in MIGRATION
    )


def test_review_no_longer_writes_the_legacy_notification() -> None:
    assert "INSERT INTO public.notifications" not in _function("public.review_adr_assessment")


def test_respond_marks_the_request_receipt_read_with_read_audit() -> None:
    body = _function("public.respond_to_adr_information_request")
    assert "PERFORM private.notification_prepare(p_patient_id, 'patient')" in body
    assert "SET read_at = clock_timestamp()" in body
    assert "AND r.read_at IS NULL" in body
    assert "INSERT INTO public.notification_read_audit(receipt_id, actor_id, action)" in body
    assert "e.source_type = 'adr_information_requests' AND e.source_id = p_request_id" in body
    # Kept from 047: zero legacy rows is fine.
    assert "dedupe_key = 'adr-information-request:' || p_request_id::text" in body


def test_audit_cannot_be_deleted_directly_and_rpcs_are_service_role_only() -> None:
    assert re.search(
        r"REVOKE DELETE, TRUNCATE ON public\.adr_assessment_audit_events, "
        r"public\.medwatch_draft_audit_events\s+FROM PUBLIC, anon, authenticated, service_role",
        MIGRATION,
    )
    for rpc in (
        "public.review_adr_assessment(uuid, uuid, text, text, jsonb)",
        "public.respond_to_adr_information_request(\n  uuid, uuid, jsonb, jsonb, jsonb, jsonb, smallint, text\n)",
    ):
        assert f"REVOKE ALL ON FUNCTION {rpc}" in MIGRATION
        assert f"GRANT EXECUTE ON FUNCTION {rpc}" in MIGRATION
    assert (
        "private.capture_notification_source() FROM PUBLIC, anon, authenticated, service_role"
        in (MIGRATION)
    )
    assert "GRANT EXECUTE ON FUNCTION private.capture_notification_source" not in MIGRATION
    assert "GRANT DELETE" not in MIGRATION


def test_patient_audit_reference_cascades_and_clinician_references_stay_restrict() -> None:
    assert re.search(
        r"ADD CONSTRAINT adr_assessment_audit_events_patient_actor_id_fkey FOREIGN KEY \(patient_actor_id\)"
        r"\s+REFERENCES public\.patients\(id\) ON DELETE CASCADE",
        MIGRATION,
    )
    assert "ON DELETE SET NULL" not in MIGRATION
    # Only the two allowlists and the patient reference are recreated; every clinician
    # reference (requested_by, actor_id, created_by, approved_by) keeps 046 to 048 RESTRICT.
    assert re.findall(r"DROP CONSTRAINT (\w+)", MIGRATION) == [
        "notification_events_event_type_check",
        "notification_events_source_type_check",
        "adr_assessment_audit_events_patient_actor_id_fkey",
    ]


def test_verification_block_fails_closed_on_each_guarantee() -> None:
    block = MIGRATION[MIGRATION.rindex("DO $$") :]
    assert "c.confdeltype NOT IN ('c', 'n')" in block
    assert "has_table_privilege(r.role, t.name, 'DELETE')" in block
    assert "has_table_privilege(r.role, t.name, 'TRUNCATE')" in block
    assert "tgname = 'notification_capture'" in block
    assert "position('INSERT INTO public.notifications' IN pg_catalog.pg_get_functiondef(" in block
    assert "has_function_privilege(r.role, f.name, 'EXECUTE')" in block
    assert block.count("RAISE EXCEPTION") == 5


def test_no_remote_or_destructive_statements() -> None:
    lowered = MIGRATION.lower()
    for forbidden in ("drop table", "truncate public.", "delete from", "alter type"):
        assert forbidden not in lowered
