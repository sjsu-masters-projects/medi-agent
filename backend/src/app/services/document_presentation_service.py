"""Reuse validated explanations after the caller has authorized the source document."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from supabase import Client

from app.services.explanation_service import ExplanationService, StructuredExplanation

# Bump when the presentation prompt or validation contract changes.
PRESENTATION_VERSION = 1
_inflight: dict[tuple[UUID, str, str, int], asyncio.Task[tuple[StructuredExplanation, bool]]] = {}


class DocumentPresentationService:
    """A saved derivative; source authorization stays on every endpoint request."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def read_or_present(
        self, document_id: UUID, source: str, locale: str
    ) -> tuple[StructuredExplanation, bool]:
        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        key = (document_id, source_hash, locale, PRESENTATION_VERSION)
        task = _inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._load(document_id, source, locale, source_hash))
            _inflight[key] = task

            def finished(done: asyncio.Task[tuple[StructuredExplanation, bool]]) -> None:
                if _inflight.get(key) is done:
                    del _inflight[key]
                # A closed client can leave no waiter; consume, without logging source text.
                if not done.cancelled():
                    done.exception()

            task.add_done_callback(finished)
        # Closing the modal must not discard work already running on the server.
        return await asyncio.shield(task)

    async def _load(
        self, document_id: UUID, source: str, locale: str, source_hash: str
    ) -> tuple[StructuredExplanation, bool]:
        rows = (
            self.db.table("document_explanation_presentations")
            .select("payload")
            .eq("document_id", str(document_id))
            .eq("language", locale)
            .eq("source_hash", source_hash)
            .eq("presentation_version", PRESENTATION_VERSION)
            .execute()
            .data
        )
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            try:
                saved = StructuredExplanation.model_validate(rows[0]["payload"])
                if saved.matches_source(source, locale):
                    return saved, True
            except (ValueError, KeyError, TypeError):
                pass
        presentation = await ExplanationService().present(source, locale)
        payload: dict[str, Any] = {
            "document_id": str(document_id),
            "language": locale,
            "source_hash": source_hash,
            "presentation_version": PRESENTATION_VERSION,
            "payload": presentation.model_dump(),
            "generated_at": datetime.now(UTC).isoformat(),
        }
        # Failure is visible rather than claiming that this result has been saved.
        self.db.table("document_explanation_presentations").upsert(
            payload, on_conflict="document_id,language"
        ).execute()
        return presentation, False
