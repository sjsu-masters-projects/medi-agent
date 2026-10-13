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
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from app.agents.ingestion.prompts import GENERATE_SUMMARY_SYSTEM, summary_prompt
from app.clients.model_router import TaskType, get_router
from app.services.clinical_fact_service import ClinicalFactService
from app.services.explanation_service import normalize_patient_summary, numbers_in

logger = logging.getLogger(__name__)

SUMMARY_PROMPT_VERSION = "patient-explanation/5"
MAX_SUMMARY_ATTEMPTS = 3
SUMMARY_RETRY_DELAYS = {
    1: timedelta(minutes=2),
    2: timedelta(minutes=5),
}

# Summary lifecycle columns arrive with migration 038. The backend image reaches Cloud
# Run before migrations are applied by hand, so every write here tolerates their absence
# rather than turning a deploy window into a failed document ingestion.
_SUMMARY_LIFECYCLE_COLUMNS = (
    "summary_status",
    "summary_failure_code",
    "summary_prompt_version",
    "summary_attempts",
    "summary_last_attempt_at",
)
_SUMMARY_SCHEDULE_COLUMNS = ("summary_next_attempt_at",)
_SUMMARY_COLUMNS = _SUMMARY_LIFECYCLE_COLUMNS + _SUMMARY_SCHEDULE_COLUMNS
_MISSING_COLUMN_CODES = {"PGRST204", "42703"}
_MISSING_FUNCTION_CODES = {"PGRST202", "42883"}

_FACT_GROUPS = {
    "medication": "medications",
    "condition": "conditions",
    "allergy": "allergies",
    "obligation": "follow_up_instructions",
    "lab_result": "results",
    "vital_sign": "vital_signs",
    "immunization": "immunizations",
    "procedure": "procedures",
    "appointment": "appointments",
}
# Derived explanations of a fact that are not source text; never shown to the model as a
# number source, and never needed to check one.
_NON_SOURCE_KEYS = frozenset({"consistency"})


def unsupported_numbers(summary: str, sources: dict[str, list[Any]]) -> set[str]:
    """Numbers an explanation states that no supplied fact contains.

    A patient explanation that invents "3 months" or turns 7.8 into 7.9 is a clinical
    error, not a style problem, so it is checked deterministically before it is stored.
    """
    allowed = numbers_in(json.dumps(sources, default=str, ensure_ascii=False))
    stated = numbers_in(summary)
    # "4.0" in a fact supports "4" in prose and the other way round.
    normalized = {token.rstrip("0").rstrip(".") if "." in token else token for token in allowed}
    return {
        token
        for token in stated
        if token not in allowed
        and (token.rstrip("0").rstrip(".") if "." in token else token) not in normalized
    }


def _api_error_matches(error: APIError, codes: set[str], needles: tuple[str, ...]) -> bool:
    message = str(getattr(error, "message", error))
    code = str(getattr(error, "code", ""))
    return code in codes and any(needle in message for needle in needles)


def is_missing_summary_column_error(error: APIError) -> bool:
    """True when the summary lifecycle columns are not deployed yet."""
    return _api_error_matches(error, _MISSING_COLUMN_CODES, _SUMMARY_COLUMNS)


def is_missing_summary_schedule_column_error(error: APIError) -> bool:
    """True when migration 038 is present but the retry schedule is not yet deployed."""
    return _api_error_matches(error, _MISSING_COLUMN_CODES, _SUMMARY_SCHEDULE_COLUMNS)


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
    next_attempt_at: datetime | None = None


class DocumentSummaryService:
    """Generate and record the optional patient explanation for one document."""

    def __init__(self, db: Client, *, facts: ClinicalFactService | None = None) -> None:
        self.db = db
        self._facts = facts or ClinicalFactService(db)

    async def generate(
        self, *, document_id: UUID, patient_id: UUID, attempt: int = 1
    ) -> SummaryOutcome:
        """Summarize a document's persisted candidates and record the result."""
        sources = self._try_read_sources(document_id, patient_id)
        if sources is None:
            return self._record(
                document_id,
                self._retryable_outcome("source_unavailable", attempt=attempt),
            )

        # A completed extraction with no grounded candidate has nothing source-bound to
        # explain. Generating prose anyway would be invention, so the explanation is
        # genuinely not required rather than failed.
        if not any(sources.values()):
            return self._record(document_id, SummaryOutcome("not_required"))

        outcome = await self._request_summary(document_id, sources, attempt=attempt)
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
        self, document_id: UUID, sources: dict[str, list[Any]], *, attempt: int
    ) -> SummaryOutcome:
        """Ask the model for the explanation and classify what came back."""
        prompt = summary_prompt(sources)
        summary = ""
        for temperature in (0.2, 0.0):
            try:
                response = await get_router().generate_text(
                    TaskType.PATIENT_EXPLANATION,
                    prompt=prompt,
                    system_instruction=GENERATE_SUMMARY_SYSTEM,
                    temperature=temperature,
                    # Gemini counts reasoning tokens against this ceiling; 1024 keeps the
                    # intentionally short (<220 word) explanation to a single request.
                    max_tokens=1024,
                )
            except Exception as exc:  # noqa: BLE001 - a provider outage is operational
                logger.warning(
                    "Patient explanation provider failed for document %s: %s",
                    document_id,
                    type(exc).__name__,
                )
                # Retry from persisted candidates only. A deliberate delay prevents an
                # unavailable provider from monopolizing a small worker batch.
                return self._retryable_outcome("provider_unavailable", attempt=attempt)

            summary = normalize_patient_summary(str(response or ""))
            if not summary:
                # Repeating an identical prompt over identical candidates would reproduce
                # this, so it waits for an explicit retry instead of burning attempts.
                return SummaryOutcome("failed", failure_code="summary_empty")
            unsupported = unsupported_numbers(summary, sources)
            if not unsupported:
                return SummaryOutcome("ready", summary=summary)
            logger.warning(
                "Patient explanation for document %s stated %d unsupported number(s)",
                document_id,
                len(unsupported),
            )
        # Showing nothing is safer than showing a number the document does not contain.
        return SummaryOutcome("failed", failure_code="summary_unverified")

    @staticmethod
    def _retryable_outcome(failure_code: str, *, attempt: int) -> SummaryOutcome:
        if attempt >= MAX_SUMMARY_ATTEMPTS:
            return SummaryOutcome("failed", failure_code="attempt_limit_reached")
        delay = SUMMARY_RETRY_DELAYS[attempt]
        return SummaryOutcome(
            "pending",
            failure_code=failure_code,
            next_attempt_at=datetime.now(UTC) + delay,
        )

    def _summary_sources(self, document_id: UUID, patient_id: UUID) -> dict[str, list[Any]]:
        """Group a document's non-deleted candidate facts into the prompt's sections."""
        grouped: dict[str, list[Any]] = {section: [] for section in _FACT_GROUPS.values()}
        for fact in self._facts.list_facts_for_document(document_id, patient_id):
            section = _FACT_GROUPS.get(str(fact.get("fact_type") or ""))
            if section is None:
                continue
            value = fact.get("value")
            if isinstance(value, dict) and value:
                grouped[section].append(
                    {key: item for key, item in value.items() if key not in _NON_SOURCE_KEYS}
                )
        return grouped

    def _record(self, document_id: UUID, outcome: SummaryOutcome) -> SummaryOutcome:
        """Persist the summary lifecycle without touching clinical or source state."""
        payload: dict[str, Any] = {
            "summary_status": outcome.status,
            "summary_failure_code": outcome.failure_code,
            "summary_next_attempt_at": (
                outcome.next_attempt_at.isoformat() if outcome.next_attempt_at else None
            ),
        }
        if outcome.summary is not None:
            payload["ai_summary"] = outcome.summary
            payload["summary_prompt_version"] = SUMMARY_PROMPT_VERSION
        try:
            self.db.table("documents").update(payload).eq("id", str(document_id)).execute()
        except APIError as exc:
            if is_missing_summary_schedule_column_error(exc):
                # The Job image can reach Cloud Run before migration 039. Retain the
                # full 038 lifecycle instead of treating a missing retry timestamp as
                # though the entire explanation lifecycle were unavailable.
                payload.pop("summary_next_attempt_at")
                self.db.table("documents").update(payload).eq("id", str(document_id)).execute()
                return outcome
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
