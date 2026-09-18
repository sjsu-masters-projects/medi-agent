"""Cloud Run Job entry point for pending document ingestion."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.clients.supabase import get_admin_client
from app.config import settings
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)


class DocumentIngestionWorker:
    """Claim a bounded batch atomically, then process each claim independently."""

    def __init__(self, db: Client, *, batch_size: int = 10) -> None:
        self._db = db
        self._batch_size = max(1, min(batch_size, 100))
        self._service = IngestionService(db)

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
        return summary


async def main() -> int:
    worker = DocumentIngestionWorker(
        get_admin_client(), batch_size=settings.document_ingestion_batch_size
    )
    summary = await worker.process_batch()
    logger.info("Document ingestion batch finished: %s", summary)
    return 1 if summary["failed"] else 0


if __name__ == "__main__":  # pragma: no cover - exercised by Cloud Run Job
    raise SystemExit(asyncio.run(main()))
