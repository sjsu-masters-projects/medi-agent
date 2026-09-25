"""Cloud Run Job entry point for pending document ingestion."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.clients.supabase import get_admin_client
from app.config import settings
from app.services.document_summary_service import DocumentSummaryService
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)


def _configure_worker_logging() -> None:
    """Emit this standalone Job's lifecycle logs at Cloud Run's INFO severity."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def _log_execution(event: str, **fields: int | str) -> None:
    """Write one non-PHI, machine-readable Cloud Run execution event."""
    payload: dict[str, int | str] = {
        "event": event,
        "execution": os.getenv("CLOUD_RUN_EXECUTION", "local"),
        "task_index": os.getenv("CLOUD_RUN_TASK_INDEX", "0"),
        **fields,
    }
    logger.info("%s", json.dumps(payload, sort_keys=True, separators=(",", ":")))


class DocumentIngestionWorker:
    """Claim a bounded batch atomically, then process each claim independently."""

    def __init__(self, db: Client, *, batch_size: int = 10) -> None:
        self._db = db
        self._batch_size = max(1, min(batch_size, 100))
        self._service = IngestionService(db)
        self._summaries = DocumentSummaryService(db)

    async def process_batch(self) -> dict[str, int]:
        result = self._db.rpc(
            "claim_pending_document_ingestion", {"p_limit": self._batch_size}
        ).execute()
        claims = cast(list[dict[str, Any]], result.data or [])
        summary = {"claimed": len(claims), "completed": 0, "needs_review": 0, "failed": 0}
        for claim in claims:
            try:
                outcome = await self._service.ingest_document(
                    document_id=UUID(str(claim["document_id"])),
                    patient_id=UUID(str(claim["patient_id"])),
                    claim=claim,
                )
            except Exception:  # noqa: BLE001 - the next claimed document must still run
                summary["failed"] += 1
                logger.exception(
                    "Unhandled document ingestion failure for claim %s", claim.get("run_id")
                )
                continue
            status = str(outcome.get("status") or "failed")
            if status in {"completed", "duplicate"}:
                summary["completed"] += 1
            elif status in {"needs_ocr", "needs_evidence_review"}:
                summary["needs_review"] += 1
            else:
                summary["failed"] += 1
        summary.update(await self.process_pending_summaries())
        return summary

    async def process_pending_summaries(self) -> dict[str, int]:
        """Generate owed patient explanations from candidates that already exist.

        This runs after ingestion and is deliberately independent of it: a document
        whose explanation is owed is claimed on its own, so a provider outage retries
        here without re-reading the source or re-proposing any clinical candidate. A
        failure never changes the document's clinical result.
        """
        claims = self._summaries.claim_pending(limit=self._batch_size)
        counts = {
            "summaries_claimed": len(claims),
            "summaries_ready": 0,
            "summaries_retry_scheduled": 0,
            "summaries_failed": 0,
            "summaries_not_required": 0,
            "summaries_unhandled_failures": 0,
        }
        for claim in claims:
            try:
                outcome = await self._summaries.generate(
                    document_id=UUID(str(claim["document_id"])),
                    patient_id=UUID(str(claim["patient_id"])),
                    attempt=int(claim.get("attempt") or 1),
                )
            except Exception:  # noqa: BLE001 - an optional explanation never fails the Job
                logger.exception(
                    "Unhandled patient explanation failure for document %s",
                    claim.get("document_id"),
                )
                counts["summaries_unhandled_failures"] += 1
                continue
            if outcome.status == "ready":
                counts["summaries_ready"] += 1
            elif outcome.status == "pending":
                counts["summaries_retry_scheduled"] += 1
            elif outcome.status == "failed":
                counts["summaries_failed"] += 1
            elif outcome.status == "not_required":
                counts["summaries_not_required"] += 1
        return counts


async def main() -> int:
    _configure_worker_logging()
    _log_execution("document_ingestion_started", batch_size=settings.document_ingestion_batch_size)
    worker = DocumentIngestionWorker(
        get_admin_client(), batch_size=settings.document_ingestion_batch_size
    )
    summary = await worker.process_batch()
    _log_execution("document_ingestion_finished", **summary)
    return 1 if summary["failed"] else 0


if __name__ == "__main__":  # pragma: no cover - exercised by Cloud Run Job
    raise SystemExit(asyncio.run(main()))
