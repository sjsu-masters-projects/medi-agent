"""Present terminal duplicate outcomes without changing stored evidence or review state."""

from collections.abc import Awaitable, Callable
from typing import Any, cast

from supabase import Client


async def attach_duplicate_status(
    db: Client,
    documents: list[dict[str, Any]],
    execute: Callable[..., Awaitable[Any]] | None = None,
) -> None:
    """Read only runs belonging to already authorized document rows, newest attempt first.

    Stored parse_status remains completed for compatibility with the ingestion schema.
    A duplicate run is a skipped extraction, not a successful empty clinical document.
    Batching avoids per-document reads and PostgREST's default response-row limit.
    """
    completed = {
        str(doc["id"]): doc
        for doc in documents
        if doc.get("id") and doc.get("parse_status") == "completed"
    }
    document_ids = list(completed)
    for start in range(0, len(document_ids), 200):
        query = (
            db.table("document_ingestion_runs")
            .select("document_id,status,attempt")
            .in_("document_id", document_ids[start : start + 200])
            .order("attempt", desc=True)
            .order("created_at", desc=True)
        )
        result = await execute(query) if execute else query.execute()
        seen: set[str] = set()
        for run in cast(list[dict[str, Any]], result.data or []):
            document_id = str(run.get("document_id", ""))
            if document_id in seen or document_id not in completed:
                continue
            seen.add(document_id)
            if run.get("status") == "duplicate":
                completed[document_id]["parse_status"] = "duplicate"
                completed[document_id]["summary_status"] = "not_required"
