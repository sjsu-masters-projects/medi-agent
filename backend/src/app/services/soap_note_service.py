"""Generate a clinician-facing SOAP note from a patient's recent record.

Four database reads, one structured model call, one insert. It was a four-node state
graph with a conditional edge, which is the same sequence with a framework holding it —
and that framework is being removed, so the sequence is written out here instead.

**This module invents nothing when the model fails**, and it never did. A failed
generation returns no note and writes no row; the endpoint reports the failure. That is
worth stating plainly because the triage and follow-up paths both had to be corrected for
exactly the opposite behaviour, and it would be easy to assume this one shared it.

SOAP has no entry in `app/adk/registry.py`. The registry records a primary, a fallback, a
measured latency budget and a deterministic path per workload, and none of those numbers
have been measured for this model on this task. Rather than invent them, this keeps the
configured Pro model it has always used. Adding a routed workload here is a decision that
should follow a measurement, not precede one.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from app.clients.gemini import GeminiClient
from app.config import settings
from app.core.llm_failures import categorize_llm_failure
from app.models.dashboard import SoapNote
from app.services.soap_note_prompts import SOAP_SYSTEM_INSTRUCTION, build_soap_prompt

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 30
MAX_CHAT_MESSAGES = 20
MAX_ADR_ASSESSMENTS = 5


@dataclass(frozen=True)
class SoapNoteResult:
    """A generated note, or the reason there isn't one.

    `soap_note_id` is set only when a row was actually written, so a caller cannot report
    a stored note that was never stored.
    """

    status: str
    soap_note: dict[str, Any] | None = None
    soap_note_id: str | None = None
    error: str | None = None


async def _execute(query: Any) -> Any:
    """Run a blocking Supabase `execute()` off the event loop."""
    return await asyncio.to_thread(query.execute)


def calculate_adherence_stats(logs: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise adherence logs into the four figures the prompt reports."""
    if not logs:
        return {
            "overall_score": 0.0,
            "medication_score": 0.0,
            "obligation_score": 0.0,
            "current_streak_days": 0,
        }

    total = len(logs)
    completed = sum(1 for log in logs if log.get("status") == "completed")
    med_logs = [log for log in logs if log.get("target_type") == "medication"]
    obl_logs = [log for log in logs if log.get("target_type") == "obligation"]

    med_completed = sum(1 for log in med_logs if log.get("status") == "completed")
    obl_completed = sum(1 for log in obl_logs if log.get("status") == "completed")

    return {
        "overall_score": completed / total if total else 0.0,
        "medication_score": med_completed / len(med_logs) if med_logs else 0.0,
        "obligation_score": obl_completed / len(obl_logs) if obl_logs else 0.0,
        "current_streak_days": calculate_current_streak_days(logs),
    }


def calculate_current_streak_days(logs: list[dict[str, Any]]) -> int:
    """Consecutive days with at least one completion, counting back from the last one."""
    by_day_completed: dict[str, bool] = {}
    for log in logs:
        logged_at = log.get("logged_at")
        if not isinstance(logged_at, str) or len(logged_at) < 10:
            continue
        day = logged_at[:10]
        by_day_completed[day] = by_day_completed.get(day, False) or (
            log.get("status") == "completed"
        )

    if not by_day_completed:
        return 0

    cursor = datetime.fromisoformat(max(by_day_completed)).date()
    streak = 0
    while by_day_completed.get(cursor.isoformat(), False):
        streak += 1
        cursor -= timedelta(days=1)

    return streak


class SoapNoteService:
    """Assemble a patient's recent record and ask a model to document it."""

    def __init__(self, db: Any) -> None:
        self.db = db

    async def gather(self, patient_id: str, lookback_days: int) -> dict[str, Any]:
        """Read everything the note is written from. No model is involved here."""
        cutoff = (datetime.now(UTC) - timedelta(days=lookback_days)).isoformat()

        patient_row = await _execute(
            self.db.table("patients")
            .select("id, first_name, last_name, email, date_of_birth")
            .eq("id", patient_id)
            .single()
        )

        meds = await _execute(
            self.db.table("medications")
            .select("*")
            .eq("patient_id", patient_id)
            .eq("is_active", True)
        )

        logs = await _execute(
            self.db.table("adherence_logs")
            .select("status, target_type, logged_at")
            .eq("patient_id", patient_id)
            .gte("logged_at", cutoff)
        )

        symptoms = await _execute(
            self.db.table("symptom_reports")
            .select("*")
            .eq("patient_id", patient_id)
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
        )

        chats = await _execute(
            self.db.table("chat_messages")
            .select("role, content, created_at")
            .eq("patient_id", patient_id)
            .order("created_at", desc=True)
            .limit(MAX_CHAT_MESSAGES)
        )

        conditions = await _execute(
            self.db.table("conditions").select("*").eq("patient_id", patient_id)
        )
        allergies = await _execute(
            self.db.table("allergies").select("*").eq("patient_id", patient_id)
        )
        adrs = await _execute(
            self.db.table("adr_assessments")
            .select("*")
            .eq("patient_id", patient_id)
            .order("created_at", desc=True)
            .limit(MAX_ADR_ASSESSMENTS)
        )

        return {
            "patient_info": cast(dict[str, Any], patient_row.data or {}),
            "medications": cast(list[dict[str, Any]], meds.data or []),
            "adherence_stats": calculate_adherence_stats(
                cast(list[dict[str, Any]], logs.data or [])
            ),
            "symptom_reports": cast(list[dict[str, Any]], symptoms.data or []),
            # Reversed so the prompt reads the conversation in the order it happened.
            "chat_messages": list(reversed(cast(list[dict[str, Any]], chats.data or []))),
            "conditions": cast(list[dict[str, Any]], conditions.data or []),
            "allergies": cast(list[dict[str, Any]], allergies.data or []),
            "adr_assessments": cast(list[dict[str, Any]], adrs.data or []),
            "lookback_days": lookback_days,
        }

    async def compose(self, patient_context: dict[str, Any]) -> SoapNote | None:
        """Ask the model to document the record, or return None if it could not."""
        try:
            client = GeminiClient(model=settings.gemini_pro_model, max_retries=2, timeout=90)
            return await client.generate_structured(
                prompt=build_soap_prompt(patient_context),
                response_model=SoapNote,
                system_instruction=SOAP_SYSTEM_INSTRUCTION,
                # Low, for clinical consistency rather than variety. Note that Gemini 3.x
                # ignores this; it is kept because the configured model here is a 3.1 Pro
                # preview and the intent should stay legible if that changes.
                temperature=0.3,
            )
        except Exception as exc:
            logger.error(
                "SOAP note generation failed: %s",
                exc,
                extra={"failure_reason": categorize_llm_failure(exc)},
            )
            return None

    async def store(
        self, *, patient_id: str, clinician_id: str, note: SoapNote
    ) -> dict[str, Any] | None:
        """Write the note and return the stored row, or None if nothing came back."""
        row = {
            "patient_id": patient_id,
            "clinician_id": clinician_id,
            "subjective": note.subjective,
            "objective": note.objective,
            "assessment": note.assessment,
            "plan": note.plan,
            "model_used": settings.gemini_pro_model,
            "generated_at": datetime.now(UTC).isoformat(),
        }

        result = await _execute(self.db.table("soap_notes").insert(row))
        inserted = cast(list[dict[str, Any]], result.data or [])
        return inserted[0] if inserted else None

    async def generate(
        self,
        *,
        patient_id: UUID | str,
        clinician_id: UUID | str,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> SoapNoteResult:
        """Gather, document, store. A failure at the model step writes nothing."""
        patient = str(patient_id)
        clinician = str(clinician_id)

        patient_context = await self.gather(patient, lookback_days)
        note = await self.compose(patient_context)

        if note is None:
            return SoapNoteResult(status="error", error="SOAP note generation failed")

        stored = await self.store(patient_id=patient, clinician_id=clinician, note=note)
        if stored is None:
            # The note exists but nothing was persisted. Reported rather than returned as
            # a success, because a clinician who is shown a note assumes it was filed.
            logger.error("SOAP note was generated but the insert returned no row")
            return SoapNoteResult(status="error", error="SOAP note could not be stored")

        logger.info("SOAP note stored")
        return SoapNoteResult(
            status="success",
            soap_note=stored,
            soap_note_id=str(stored.get("id") or "") or None,
        )
