"""The optional patient explanation fails, and recovers, without clinical side effects."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from postgrest.exceptions import APIError

from app.services.document_summary_service import (
    SUMMARY_PROMPT_VERSION,
    DocumentSummaryService,
)

DOCUMENT_ID = UUID("11111111-1111-1111-1111-111111111111")
PATIENT_ID = UUID("22222222-2222-2222-2222-222222222222")


def _facts(*rows: dict) -> MagicMock:
    facts = MagicMock()
    facts.list_facts_for_document.return_value = list(rows)
    return facts


def _db() -> MagicMock:
    db = MagicMock()
    table = MagicMock()
    db.table.return_value = table
    table.update.return_value = table
    table.eq.return_value = table
    return db


def _written(db: MagicMock) -> dict:
    return db.table.return_value.update.call_args.args[0]


def _candidate_facts() -> list[dict]:
    return [
        {"fact_type": "medication", "value": {"name": "Lisinopril", "dose": "10 mg"}},
        {"fact_type": "condition", "value": {"name": "Hypertension"}},
    ]


@pytest.mark.asyncio
async def test_ready_summary_records_text_and_prompt_version() -> None:
    db = _db()
    service = DocumentSummaryService(db, facts=_facts(*_candidate_facts()))
    router = MagicMock()
    router.generate_text = AsyncMock(return_value="Lisinopril 10 mg helps your blood pressure.")

    with patch("app.services.document_summary_service.get_router", return_value=router):
        outcome = await service.generate(document_id=DOCUMENT_ID, patient_id=PATIENT_ID)

    assert outcome.status == "ready"
    written = _written(db)
    assert written["summary_status"] == "ready"
    assert written["summary_failure_code"] is None
    assert written["ai_summary"] == "Lisinopril 10 mg helps your blood pressure."
    assert written["summary_prompt_version"] == SUMMARY_PROMPT_VERSION
    # The explanation is not clinical truth: it may not touch parse state or candidates.
    assert "parse_status" not in written
    assert "parsed" not in written


@pytest.mark.asyncio
async def test_provider_outage_stays_retryable_with_a_recorded_reason() -> None:
    db = _db()
    service = DocumentSummaryService(db, facts=_facts(*_candidate_facts()))
    router = MagicMock()
    router.generate_text = AsyncMock(side_effect=RuntimeError("GenerationProviderError"))

    with patch("app.services.document_summary_service.get_router", return_value=router):
        outcome = await service.generate(document_id=DOCUMENT_ID, patient_id=PATIENT_ID)

    # Pending, not failed: the next worker run retries it from the same candidates.
    assert outcome.status == "pending"
    assert outcome.failure_code == "provider_unavailable"
    assert outcome.next_attempt_at is not None
    written = _written(db)
    assert written["summary_status"] == "pending"
    assert written["summary_failure_code"] == "provider_unavailable"
    assert written["summary_next_attempt_at"] == outcome.next_attempt_at.isoformat()


@pytest.mark.asyncio
async def test_third_provider_outage_exposes_a_terminal_retry_state() -> None:
    db = _db()
    service = DocumentSummaryService(db, facts=_facts(*_candidate_facts()))
    router = MagicMock()
    router.generate_text = AsyncMock(side_effect=RuntimeError("GenerationProviderError"))

    with patch("app.services.document_summary_service.get_router", return_value=router):
        outcome = await service.generate(
            document_id=DOCUMENT_ID,
            patient_id=PATIENT_ID,
            attempt=3,
        )

    assert outcome.status == "failed"
    assert outcome.failure_code == "attempt_limit_reached"
    assert outcome.next_attempt_at is None
    written = _written(db)
    assert written["summary_status"] == "failed"
    assert written["summary_next_attempt_at"] is None


@pytest.mark.asyncio
async def test_empty_model_output_fails_rather_than_burning_attempts() -> None:
    db = _db()
    service = DocumentSummaryService(db, facts=_facts(*_candidate_facts()))
    router = MagicMock()
    router.generate_text = AsyncMock(return_value="   ")

    with patch("app.services.document_summary_service.get_router", return_value=router):
        outcome = await service.generate(document_id=DOCUMENT_ID, patient_id=PATIENT_ID)

    assert outcome.status == "failed"
    assert outcome.failure_code == "summary_empty"
    # Nothing usable came back, so no explanation text is written at all.
    assert _written(db) == {
        "summary_status": "failed",
        "summary_failure_code": "summary_empty",
        "summary_next_attempt_at": None,
    }


@pytest.mark.asyncio
async def test_document_without_candidates_is_never_summarized() -> None:
    db = _db()
    service = DocumentSummaryService(db, facts=_facts())
    router = MagicMock()
    router.generate_text = AsyncMock(return_value="invented prose")

    with patch("app.services.document_summary_service.get_router", return_value=router):
        outcome = await service.generate(document_id=DOCUMENT_ID, patient_id=PATIENT_ID)

    # Nothing source-bound to explain, so nothing is generated. Writing prose here would
    # be invention, which is the one outcome a patient-facing summary must never have.
    assert outcome.status == "not_required"
    router.generate_text.assert_not_awaited()
    assert _written(db)["summary_status"] == "not_required"


@pytest.mark.asyncio
async def test_unreadable_candidates_are_operational_not_clinical() -> None:
    db = _db()
    facts = MagicMock()
    facts.list_facts_for_document.side_effect = RuntimeError("connection reset")
    service = DocumentSummaryService(db, facts=facts)

    outcome = await service.generate(document_id=DOCUMENT_ID, patient_id=PATIENT_ID)

    assert outcome.status == "pending"
    assert outcome.failure_code == "source_unavailable"


@pytest.mark.asyncio
async def test_summary_survives_a_deploy_before_its_migration() -> None:
    """The image reaches Cloud Run before migration 038 is applied by hand."""
    db = _db()
    table = db.table.return_value
    table.execute.side_effect = [
        APIError({"code": "PGRST204", "message": "Could not find the 'summary_status' column"}),
        MagicMock(data=[]),
    ]
    service = DocumentSummaryService(db, facts=_facts(*_candidate_facts()))
    router = MagicMock()
    router.generate_text = AsyncMock(return_value="Your blood pressure medicine.")

    with patch("app.services.document_summary_service.get_router", return_value=router):
        outcome = await service.generate(document_id=DOCUMENT_ID, patient_id=PATIENT_ID)

    assert outcome.status == "ready"
    # The explanation text is still saved; only the lifecycle columns are skipped.
    assert table.update.call_args.args[0] == {"ai_summary": "Your blood pressure medicine."}


def test_claim_returns_nothing_until_its_function_is_deployed() -> None:
    db = MagicMock()
    db.rpc.return_value.execute.side_effect = APIError(
        {
            "code": "PGRST202",
            "message": "Could not find the function public.claim_pending_document_summary",
        }
    )

    assert DocumentSummaryService(db, facts=MagicMock()).claim_pending(limit=10) == []


@pytest.mark.asyncio
async def test_retry_schedule_degrades_without_losing_the_summary_lifecycle() -> None:
    db = _db()
    table = db.table.return_value
    table.execute.side_effect = [
        APIError(
            {
                "code": "PGRST204",
                "message": "Could not find the 'summary_next_attempt_at' column",
            }
        ),
        MagicMock(data=[]),
    ]
    service = DocumentSummaryService(db, facts=_facts(*_candidate_facts()))
    router = MagicMock()
    router.generate_text = AsyncMock(return_value="Your blood pressure medicine.")

    with patch("app.services.document_summary_service.get_router", return_value=router):
        outcome = await service.generate(document_id=DOCUMENT_ID, patient_id=PATIENT_ID)

    assert outcome.status == "ready"
    assert table.update.call_args.args[0] == {
        "summary_status": "ready",
        "summary_failure_code": None,
        "ai_summary": "Your blood pressure medicine.",
        "summary_prompt_version": SUMMARY_PROMPT_VERSION,
    }


def test_unrelated_database_errors_are_not_swallowed() -> None:
    db = MagicMock()
    db.rpc.return_value.execute.side_effect = APIError(
        {"code": "42501", "message": "permission denied for function"}
    )

    with pytest.raises(APIError):
        DocumentSummaryService(db, facts=MagicMock()).claim_pending(limit=10)
