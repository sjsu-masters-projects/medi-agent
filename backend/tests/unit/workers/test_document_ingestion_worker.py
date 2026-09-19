"""The durable worker continues a batch after an individual document fails."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.workers.document_ingestion import DocumentIngestionWorker


@pytest.mark.asyncio
async def test_worker_claims_once_and_counts_each_terminal_outcome() -> None:
    db = MagicMock()
    db.rpc.return_value.execute.return_value = MagicMock(
        data=[
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
    )
    worker = DocumentIngestionWorker(db, batch_size=10)
    worker._service.ingest_document = AsyncMock(
        side_effect=[{"status": "completed"}, {"status": "needs_evidence_review"}]
    )

    summary = await worker.process_batch()

    assert summary == {"claimed": 2, "completed": 1, "needs_review": 1, "failed": 0}
    db.rpc.assert_called_once_with("claim_pending_document_ingestion", {"p_limit": 10})
