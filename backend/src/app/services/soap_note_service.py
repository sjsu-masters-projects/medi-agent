"""Generate a clinician-facing SOAP note from a patient's recent record.

Four database reads, one structured model call, one insert. It was a four-node state
graph with a conditional edge, which is the same sequence with a framework holding it —
and that framework is being removed, so the sequence is written out here instead.

**This module invents nothing when the model fails**, and it never did. A failed
generation returns no note and writes no row; the endpoint reports the failure. That is
worth stating plainly because the triage and follow-up paths both had to be corrected for
exactly the opposite behaviour, and it would be easy to assume this one shared it.

SOAP uses the registry's structured background-generation path. Its configured Pro model
is retained without a model fallback. The timeout and output ceiling are operational
limits, not measured SOAP performance or clinical qualification.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from app.adk.background_generation import generate_for_workload
from app.adk.registry import Workload, route_for
from app.core.llm_failures import categorize_llm_failure
from app.intake.preview import testimony_only
from app.models.dashboard import SoapNote
from app.models.generation import GenerationErrorCode, GenerationProviderError, GenerationResponse
from app.services.acting_care_team import acting_care_team
from app.services.care_plan_activity_scope import ActivityScope
from app.services.care_team_access import CareTeamAccessService, PatientAccess
from app.services.soap_note_prompts import SOAP_SYSTEM_INSTRUCTION, build_soap_prompt

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 30
MAX_CHAT_MESSAGES = 20
MAX_ADR_ASSESSMENTS = 5
SOAP_RETRYABLE_ERRORS = frozenset(
    {
        GenerationErrorCode.RATE_LIMITED,
        GenerationErrorCode.UNAVAILABLE,
        GenerationErrorCode.TRUNCATED,
    }
)


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


# Medications are logged as "taken" and activities as "completed"; both are done.
# Counting only "completed" reported every medication as 0% adherent.
DONE_STATUSES = frozenset({"completed", "taken"})


def calculate_adherence_stats(logs: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise adherence logs into the four figures the prompt reports."""
    if not logs:
        # Counts let the prompt say "no logs recorded" instead of reporting 0% adherence.
        return {
            "overall_score": 0.0,
            "medication_score": 0.0,
            "obligation_score": 0.0,
            "current_streak_days": 0,
            "log_count": 0,
            "medication_log_count": 0,
            "obligation_log_count": 0,
        }

    total = len(logs)
    completed = sum(1 for log in logs if log.get("status") in DONE_STATUSES)
    med_logs = [log for log in logs if log.get("target_type") == "medication"]
    obl_logs = [log for log in logs if log.get("target_type") == "obligation"]

    med_completed = sum(1 for log in med_logs if log.get("status") in DONE_STATUSES)
    obl_completed = sum(1 for log in obl_logs if log.get("status") in DONE_STATUSES)

    return {
        "overall_score": completed / total if total else 0.0,
        "medication_score": med_completed / len(med_logs) if med_logs else 0.0,
        "obligation_score": obl_completed / len(obl_logs) if obl_logs else 0.0,
        "current_streak_days": calculate_current_streak_days(logs),
        "log_count": total,
        "medication_log_count": len(med_logs),
        "obligation_log_count": len(obl_logs),
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
            log.get("status") in DONE_STATUSES
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

    async def gather(
        self, patient_id: str, lookback_days: int, *, access: PatientAccess
    ) -> dict[str, Any]:
        """Read everything the note is written from. No model is involved here.

        ``access`` is the writing clinician's links to the patient. The model sees only what
        that clinician may read: conditions the patient marked sensitive for another team are
        left out (the prompt says only that some are private), reviewed ADR assessments of
        another team are left out, and adherence to another team's plan activities is not
        counted. Medications and allergies are shared and always included.
        """
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
            .select("status, target_type, target_id, logged_at")
            .eq("patient_id", patient_id)
            .gte("logged_at", cutoff)
        )

        symptoms = await _execute(
            self.db.table("symptom_reports")
            .select("*")
            .eq("confirmation_state", "patient_confirmed")
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
            .limit(MAX_ADR_ASSESSMENTS * 4)
        )
        visible_conditions, some_private = access.split_conditions(
            cast(list[dict[str, Any]], conditions.data or [])
        )
        visible_logs = await asyncio.to_thread(
            ActivityScope(self.db, patient_id, access).keep,
            cast(list[dict[str, Any]], logs.data or []),
        )
        visible_adrs = [
            row for row in cast(list[dict[str, Any]], adrs.data or []) if access.can_see_adr(row)
        ][:MAX_ADR_ASSESSMENTS]

        return {
            "patient_info": cast(dict[str, Any], patient_row.data or {}),
            "medications": cast(list[dict[str, Any]], meds.data or []),
            "adherence_stats": calculate_adherence_stats(visible_logs),
            "symptom_reports": [
                testimony_only(row) for row in cast(list[dict[str, Any]], symptoms.data or [])
            ],
            # Reversed so the prompt reads the conversation in the order it happened.
            "chat_messages": list(reversed(cast(list[dict[str, Any]], chats.data or []))),
            "conditions": visible_conditions,
            "some_conditions_private": some_private,
            "allergies": cast(list[dict[str, Any]], allergies.data or []),
            "adr_assessments": visible_adrs,
            "lookback_days": lookback_days,
        }

    async def compose(self, patient_context: dict[str, Any]) -> SoapNote | None:
        """Ask the model to document the record, or return None if it could not."""
        try:
            response = await self._generate_with_one_transient_retry(patient_context)
            note = SoapNote.model_validate_json(response.text)
            if not all(
                value.strip()
                for value in (note.subjective, note.objective, note.assessment, note.plan)
            ):
                return None
            return note
        except Exception as exc:
            logger.error(
                "SOAP note generation failed: %s",
                type(exc).__name__,
                extra={"failure_reason": categorize_llm_failure(exc)},
            )
            return None

    async def _generate_with_one_transient_retry(
        self, patient_context: dict[str, Any]
    ) -> GenerationResponse:
        """Retry one normalized transient/truncation failure, never invalid content."""
        prompt = build_soap_prompt(patient_context)
        for attempt in range(2):
            try:
                return await generate_for_workload(
                    Workload.SOAP,
                    prompt=prompt,
                    response_schema=SoapNote.model_json_schema(),
                    system_instruction=SOAP_SYSTEM_INSTRUCTION,
                    temperature=0.3,
                )
            except GenerationProviderError as exc:
                if attempt == 0 and exc.code in SOAP_RETRYABLE_ERRORS:
                    logger.warning(
                        "Retrying SOAP generation after a recoverable provider failure",
                        extra={"failure_reason": exc.code.value},
                    )
                    continue
                raise
        raise AssertionError("SOAP retry loop exhausted without returning or raising")

    async def store(
        self, *, patient_id: str, clinician_id: str, note: SoapNote, care_team_id: str
    ) -> dict[str, Any] | None:
        """Write the note, owned by the writing clinician's care team, and return the row."""
        row = {
            "patient_id": patient_id,
            "clinician_id": clinician_id,
            "care_team_id": care_team_id,
            "subjective": note.subjective,
            "objective": note.objective,
            "assessment": note.assessment,
            "plan": note.plan,
            "model_used": route_for(Workload.SOAP).primary.model_id,
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
        care_team_id: UUID | str | None = None,
    ) -> SoapNoteResult:
        """Gather, document, store. A failure at the model step writes nothing.

        The note belongs to the clinician's exact link to the patient. A clinician with two
        links must name one (``CARE_TEAM_REQUIRED``); one without a link is denied.
        """
        patient = str(patient_id)
        clinician = str(clinician_id)

        access = await asyncio.to_thread(
            CareTeamAccessService(self.db).for_patient, clinician, patient
        )
        team = acting_care_team(access, care_team_id)
        patient_context = await self.gather(patient, lookback_days, access=access)
        note = await self.compose(patient_context)

        if note is None:
            return SoapNoteResult(status="error", error="SOAP note generation failed")

        stored = await self.store(
            patient_id=patient, clinician_id=clinician, note=note, care_team_id=team
        )
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
