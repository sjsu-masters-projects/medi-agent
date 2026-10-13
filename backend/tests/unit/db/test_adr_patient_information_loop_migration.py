"""Schema guarantees for the clinician-to-patient ADR information loop."""

from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "src/app/db/migrations/047_adr_patient_information_loop.sql"
).read_text()


def test_patient_requests_are_restricted_to_retrospective_questions() -> None:
    patient_safe_allowlist = (
        '\'["reappeared_on_rechallenge", "dose_response", "similar_previous_reaction"]\'::jsonb'
    )
    assert "adr_information_requests_patient_safe_questions" in MIGRATION
    assert patient_safe_allowlist in MIGRATION
    assert "Only patient-answerable retrospective questions may be requested" in MIGRATION


def test_patient_response_is_atomic_patient_scoped_and_audited() -> None:
    assert "FUNCTION public.respond_to_adr_information_request" in MIGRATION
    assert "v_request.patient_id <> p_patient_id" in MIGRATION
    assert MIGRATION.count("FOR UPDATE") >= 3
    assert "patient_information_provided" in MIGRATION
    assert "patient_actor_id" in MIGRATION
    assert "num_nonnulls(actor_id, patient_actor_id) = 1" in MIGRATION


def test_direct_write_and_rpc_access_are_service_role_only() -> None:
    assert (
        "REVOKE ALL ON TABLE public.adr_information_requests FROM anon, authenticated" in MIGRATION
    )
    assert "GRANT SELECT ON TABLE public.adr_information_requests TO authenticated" in MIGRATION
    assert "FROM PUBLIC, anon, authenticated" in MIGRATION
    assert "TO service_role" in MIGRATION


def test_patient_response_closes_notification_and_preserves_score_history() -> None:
    assert "SET is_read = true" in MIGRATION
    assert "previous_naranjo_score" in MIGRATION
    assert "resolved_naranjo_score = p_score" in MIGRATION
