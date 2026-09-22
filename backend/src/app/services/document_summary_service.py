"""Patient-explanation lifecycle, owned separately from clinical ingestion.

The explanation is an optional convenience built from candidates that already exist.
It is not a safety boundary: it never creates, changes, or deletes a clinical fact,
never touches `parse_status`, and never re-reads the stored source artifact. That
separation is what lets a provider outage be retried cheaply — the retry re-reads
persisted candidates instead of re-running OCR and re-proposing the same facts.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from app.agents.ingestion.prompts import GENERATE_SUMMARY_SYSTEM, GENERATE_SUMMARY_USER
from app.clients.model_router import TaskType, get_router
from app.services.clinical_fact_service import ClinicalFactService
from app.services.explanation_service import normalize_patient_summary

logger = logging.getLogger(__name__)

SUMMARY_PROMPT_VERSION = "patient-explanation/1"
MAX_SUMMARY_ATTEMPTS = 3

# Summary lifecycle columns arrive with migration 038. The backend image reaches Cloud
# Run before migrations are applied by hand, so every write here tolerates their absence
# rather than turning a deploy window into a failed document ingestion.
_SUMMARY_COLUMNS = (
    "summary_status",
    "summary_failure_code",
    "summary_prompt_version",
    "summary_attempts",
    "summary_last_attempt_at",
)
_MISSING_COLUMN_CODES = {"PGRST204", "42703"}
_MISSING_FUNCTION_CODES = {"PGRST202", "42883"}

_FACT_GROUPS = {
    "medication": "medications",
    "condition": "conditions",
    "obligation": "follow_up_instructions",
}


def _api_error_matches(error: APIError, codes: set[str], needles: tuple[str, ...]) -> bool:
    message = str(getattr(error, "message", error))
    code = str(getattr(error, "code", ""))
    return code in codes and any(needle in message for needle in needles)


def is_missing_summary_column_error(error: APIError) -> bool:
    """True when the summary lifecycle columns are not deployed yet."""
    return _api_error_matches(error, _MISSING_COLUMN_CODES, _SUMMARY_COLUMNS)


def is_missing_summary_function_error(error: APIError) -> bool:
    """True when the summary claim/retry functions are not deployed yet."""
    return _api_error_matches(
        error,
        _MISSING_FUNCTION_CODES,
        ("claim_pending_document_summary", "enqueue_document_summary_retry"),
    )


@dataclass(frozen=True)
class SummaryOutcome:
    """The terminal state of one summary attempt."""

    status: str
    failure_code: str | None = None
    summary: str | None = None


class DocumentSummaryService:
    """Generate and record the optional patient explanation for one document."""

    def __init__(self, db: Client, *, facts: ClinicalFactService | None = None) -> None:
        self.db = db
        self._facts = facts or ClinicalFactService(db)

    async def generate(self, *, document_id: UUID, patient_id: UUID) -> SummaryOutcome:
        """Summarize a document's persisted candidates and record the result."""
        sources = self._try_read_sources(document_id, patient_id)
        if sources is None:
            return self._record(
                document_id, SummaryOutcome("pending", failure_code="source_unavailable")
            )

        # A completed extraction with no grounded candidate has nothing source-bound to
        # explain. Generating prose anyway would be invention, so the explanation is
        # genuinely not required rather than failed.
        if not any(sources.values()):
            return self._record(document_id, SummaryOutcome("not_required"))

        outcome = await self._request_summary(document_id, sources)
        return self._record(document_id, outcome)

    def _try_read_sources(self, document_id: UUID, patient_id: UUID) -> dict[str, list[Any]] | None:
        """Read a document's candidates, or None when the read itself is the failure."""
        try:
            return self._summary_sources(document_id, patient_id)
        except Exception as exc:  # noqa: BLE001 - an unreadable candidate set is operational
            logger.warning(
                "Could not read candidates for document summary %s: %s",
                document_id,
                type(exc).__name__,
            )
            return None

    async def _request_summary(
        self, document_id: UUID, sources: dict[str, list[Any]]
    ) -> SummaryOutcome:
        """Ask the model for the explanation and classify what came back."""
        try:
            response = await get_router().generate_text(
                TaskType.PATIENT_EXPLANATION,
                prompt=GENERATE_SUMMARY_USER.format(
                    medications=json.dumps(sources["medications"], default=str),
                    conditions=json.dumps(sources["conditions"], default=str),
                    follow_up_instructions=json.dumps(
                        sources["follow_up_instructions"], default=str
                    ),
                ),
                system_instruction=GENERATE_SUMMARY_SYSTEM,
                temperature=0.2,
                # Gemini counts reasoning tokens against this ceiling; 1024 keeps the
                # intentionally short (<180 word) explanation to a single request.
                max_tokens=1024,
            )
        except Exception as exc:  # noqa: BLE001 - a provider outage is operational, not clinical
            logger.warning(
                "Patient explanation provider failed for document %s: %s",
                document_id,
                type(exc).__name__,
            )
            # Left pending so the next worker run retries without re-reading the source.
            # The claim function caps automatic attempts and then marks the row failed.
            return SummaryOutcome("pending", failure_code="provider_unavailable")

        summary = normalize_patient_summary(str(response or ""))
        if not summary:
            # Repeating an identical prompt over identical candidates would reproduce
            # this, so it waits for an explicit retry instead of burning attempts.
            return SummaryOutcome("failed", failure_code="summary_empty")
        return SummaryOutcome("ready", summary=summary)

    def _summary_sources(self, document_id: UUID, patient_id: UUID) -> dict[str, list[Any]]:
        """Group a document's non-deleted candidate facts into the prompt's sections."""
        grouped: dict[str, list[Any]] = {
            "medications": [],
            "conditions": [],
            "follow_up_instructions": [],
        }
        for fact in self._facts.list_facts_for_document(document_id, patient_id):
            section = _FACT_GROUPS.get(str(fact.get("fact_type") or ""))
            if section is None:
                continue
            value = fact.get("value")
            if isinstance(value, dict) and value:
                grouped[section].append(value)
        return grouped

    def _record(self, document_id: UUID, outcome: SummaryOutcome) -> SummaryOutcome:
        """Persist the summary lifecycle without touching clinical or source state."""
        payload: dict[str, Any] = {
            "summary_status": outcome.status,
            "summary_failure_code": outcome.failure_code,
        }
        if outcome.summary is not None:
            payload["ai_summary"] = outcome.summary
            payload["summary_prompt_version"] = SUMMARY_PROMPT_VERSION
        try:
            self.db.table("documents").update(payload).eq("id", str(document_id)).execute()
        except APIError as exc:
            if not is_missing_summary_column_error(exc):
                raise
            logger.warning(
                "Summary lifecycle columns are not deployed; recorded text only for %s",
                document_id,
            )
            if outcome.summary is not None:
                self.db.table("documents").update({"ai_summary": outcome.summary}).eq(
                    "id", str(document_id)
                ).execute()
        return outcome

    def claim_pending(self, *, limit: int) -> list[dict[str, Any]]:
        """Claim a bounded batch of documents whose explanation is still owed."""
        try:
            result = self.db.rpc(
                "claim_pending_document_summary", {"p_limit": max(1, min(limit, 100))}
            ).execute()
        except APIError as exc:
            if not is_missing_summary_function_error(exc):
                raise
            logger.warning("Document summary claim function is not deployed yet")
            return []
        return cast(list[dict[str, Any]], result.data or [])
