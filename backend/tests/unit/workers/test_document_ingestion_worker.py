"""The durable worker continues a batch after an individual document fails."""

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.services.document_summary_service import SummaryOutcome
from app.workers import document_ingestion
from app.workers.document_ingestion import DocumentIngestionWorker

INGESTION_CLAIMS = [
    {
        "document_id": "00000000-0000-0000-0000-000000000001",
        "patient_id": "00000000-0000-0000-0000-000000000002",
        "run_id": "first",
    },
    {
        "document_id": "00000000-0000-0000-0000-000000000003",
        "patient_id": "00000000-0000-0000-0000-000000000004",
        "run_id": "second",
    },
]
SUMMARY_CLAIMS = [
    {
        "document_id": "00000000-0000-0000-0000-000000000005",
        "patient_id": "00000000-0000-0000-0000-000000000006",
        "attempt": 2,
    }
]


def _db(*, summary_claims: list[dict] | None = None) -> MagicMock:
    """Answer each claim function with its own rows, as the database does."""
    db = MagicMock()
    responses = {
        "claim_pending_document_ingestion": MagicMock(data=list(INGESTION_CLAIMS)),
        "claim_pending_document_summary": MagicMock(
            data=list(SUMMARY_CLAIMS if summary_claims is None else summary_claims)
        ),
    }
    db.rpc.side_effect = lambda name, _params: MagicMock(
        execute=MagicMock(return_value=responses[name])
    )
    return db


@pytest.mark.asyncio
async def test_worker_claims_once_and_counts_each_terminal_outcome() -> None:
    db = _db(summary_claims=[])
    worker = DocumentIngestionWorker(db, batch_size=10)
    worker._service.ingest_document = AsyncMock(
        side_effect=[{"status": "completed"}, {"status": "needs_evidence_review"}]
    )

    summary = await worker.process_batch()

    assert summary["claimed"] == 2
    assert summary["completed"] == 1
    assert summary["needs_review"] == 1
    assert summary["failed"] == 0
    assert db.rpc.call_args_list[0].args == ("claim_pending_document_ingestion", {"p_limit": 10})


@pytest.mark.asyncio
async def test_owed_explanations_are_claimed_separately_from_ingestion() -> None:
    db = _db()
    worker = DocumentIngestionWorker(db, batch_size=10)
    worker._service.ingest_document = AsyncMock(
        side_effect=[{"status": "completed"}, {"status": "completed"}]
    )
    worker._summaries.generate = AsyncMock(return_value=SummaryOutcome("ready", summary="Text."))

    summary = await worker.process_batch()

    assert summary["summaries_claimed"] == 1
    assert summary["summaries_ready"] == 1
    # A second claim call, not a re-ingestion: the explanation is rebuilt from candidates
    # that already exist, so no source is re-read and no candidate is proposed twice.
    assert [call.args[0] for call in db.rpc.call_args_list] == [
        "claim_pending_document_ingestion",
        "claim_pending_document_summary",
    ]
    assert worker._service.ingest_document.await_count == 2
    worker._summaries.generate.assert_awaited_once_with(
        document_id=UUID("00000000-0000-0000-0000-000000000005"),
        patient_id=UUID("00000000-0000-0000-0000-000000000006"),
        attempt=2,
    )


@pytest.mark.asyncio
async def test_a_failed_explanation_never_fails_the_job() -> None:
    db = _db()
    worker = DocumentIngestionWorker(db, batch_size=10)
    worker._service.ingest_document = AsyncMock(
        side_effect=[{"status": "completed"}, {"status": "completed"}]
    )
    worker._summaries.generate = AsyncMock(side_effect=RuntimeError("provider down"))

    summary = await worker.process_batch()

    assert summary["summaries_claimed"] == 1
    assert summary["summaries_ready"] == 0
    # `failed` drives the Job's exit code and counts clinical ingestion only.
    assert summary["failed"] == 0
    assert summary["completed"] == 2


@pytest.mark.asyncio
async def test_worker_counts_each_patient_explanation_outcome() -> None:
    worker = DocumentIngestionWorker(_db(), batch_size=10)
    worker._summaries.generate = AsyncMock(
        side_effect=[
            SummaryOutcome("ready", summary="Text."),
            SummaryOutcome("pending", failure_code="provider_unavailable"),
            SummaryOutcome("failed", failure_code="summary_empty"),
            SummaryOutcome("not_required"),
        ]
    )
    worker._summaries.claim_pending = MagicMock(
        return_value=[
            {
                "document_id": f"00000000-0000-0000-0000-00000000000{index}",
                "patient_id": "00000000-0000-0000-0000-000000000010",
            }
            for index in range(1, 5)
        ]
    )

    counts = await worker.process_pending_summaries()

    assert counts == {
        "summaries_claimed": 4,
        "summaries_ready": 1,
        "summaries_retry_scheduled": 1,
        "summaries_failed": 1,
        "summaries_not_required": 1,
        "summaries_unhandled_failures": 0,
    }


@pytest.mark.asyncio
async def test_main_emits_non_phi_execution_lifecycle_logs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    batch = MagicMock()
    batch.process_batch = AsyncMock(
        return_value={
            "claimed": 0,
            "completed": 0,
            "needs_review": 0,
            "failed": 0,
            "summaries_claimed": 1,
            "summaries_ready": 1,
        }
    )
    monkeypatch.setattr(
        document_ingestion, "DocumentIngestionWorker", MagicMock(return_value=batch)
    )
    monkeypatch.setattr(document_ingestion, "get_admin_client", MagicMock())
    monkeypatch.setenv("CLOUD_RUN_EXECUTION", "test-execution")
    monkeypatch.setenv("CLOUD_RUN_TASK_INDEX", "0")

    with caplog.at_level("INFO"):
        assert await document_ingestion.main() == 0

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.getMessage().startswith("{")
    ]
    assert events == [
        {
            "batch_size": document_ingestion.settings.document_ingestion_batch_size,
            "event": "document_ingestion_started",
            "execution": "test-execution",
            "task_index": "0",
        },
        {
            "claimed": 0,
            "completed": 0,
            "event": "document_ingestion_finished",
            "execution": "test-execution",
            "failed": 0,
            "needs_review": 0,
            "summaries_claimed": 1,
            "summaries_ready": 1,
            "task_index": "0",
        },
    ]
