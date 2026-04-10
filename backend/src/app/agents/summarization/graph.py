"""LangGraph state machine for the Summarization Agent.

Graph nodes (in order):
  gather_patient_data  → Fetch all relevant patient data from Supabase
  prepare_context      → Transform raw DB data into structured LLM prompt context
  generate_soap_note   → Call Gemini 3.1 Pro Preview via GeminiClient
  store_soap_note      → Upsert the SOAP note into the soap_notes table

Each node is a pure async function that receives and returns a typed state dict.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from app.agents.summarization.prompts import SOAP_SYSTEM_INSTRUCTION, build_soap_prompt
from app.clients.gemini import GeminiClient
from app.config import settings
from app.models.dashboard import SoapNote

logger = logging.getLogger(__name__)


# ── State schema ─────────────────────────────────────────────────────────────


class SummarizationState(TypedDict, total=False):
    """LangGraph state — passed between nodes in the summarization graph."""

    # Inputs
    patient_id: str
    clinician_id: str
    lookback_days: int

    # Gathered data
    patient_info: dict[str, Any]
    medications: list[dict[str, Any]]
    adherence_stats: dict[str, Any]
    symptom_reports: list[dict[str, Any]]
    chat_messages: list[dict[str, Any]]
    conditions: list[dict[str, Any]]
    allergies: list[dict[str, Any]]
    adr_assessments: list[dict[str, Any]]

    # Processing outputs
    patient_context: dict[str, Any]
    soap_note: dict[str, Any]

    # Final output
    stored_note_id: str
    error: str | None


# ── Node functions ────────────────────────────────────────────────────────────


async def gather_patient_data(state: SummarizationState, db: Any) -> SummarizationState:
    """Node 1: Fetch all patient data from Supabase.

    Fetches: patient profile, medications, adherence logs, symptom reports,
    chat messages, conditions, allergies, ADR assessments.
    """
    patient_id = state["patient_id"]
    lookback_days = state.get("lookback_days", 30)
    cutoff = (datetime.now(UTC) - timedelta(days=lookback_days)).isoformat()

    logger.info("Gathering patient data for summarization")

    # Patient profile
    patient_row = await _execute(
        db.table("patients")
        .select("id, first_name, last_name, email, date_of_birth")
        .eq("id", patient_id)
        .single()
    )
    patient_info = cast(dict[str, Any], patient_row.data or {})

    # Active medications
    meds = await _execute(
        db.table("medications").select("*").eq("patient_id", patient_id).eq("is_active", True)
    )
    medications = cast(list[dict[str, Any]], meds.data or [])

    # Adherence stats (last lookback_days)
    logs = await _execute(
        db.table("adherence_logs")
        .select("status, target_type, logged_at")
        .eq("patient_id", patient_id)
        .gte("logged_at", cutoff)
    )
    log_data = cast(list[dict[str, Any]], logs.data or [])
    adherence_stats = _calculate_adherence_stats(log_data)

    # Symptom reports
    symptoms = await _execute(
        db.table("symptom_reports")
        .select("*")
        .eq("patient_id", patient_id)
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
    )
    symptom_reports = cast(list[dict[str, Any]], symptoms.data or [])

    # Chat messages (last 20)
    chats = await _execute(
        db.table("chat_messages")
        .select("role, content, created_at")
        .eq("patient_id", patient_id)
        .order("created_at", desc=True)
        .limit(20)
    )
    # Prompt context should be chronological for coherent summarization.
    chat_messages = list(reversed(cast(list[dict[str, Any]], chats.data or [])))

    # Conditions
    conds = await _execute(db.table("conditions").select("*").eq("patient_id", patient_id))
    conditions = cast(list[dict[str, Any]], conds.data or [])

    # Allergies
    allergies_res = await _execute(db.table("allergies").select("*").eq("patient_id", patient_id))
    allergies = cast(list[dict[str, Any]], allergies_res.data or [])

    # ADR assessments
    adrs = await _execute(
        db.table("adr_assessments")
        .select("*")
        .eq("patient_id", patient_id)
        .order("created_at", desc=True)
        .limit(5)
    )
    adr_assessments = cast(list[dict[str, Any]], adrs.data or [])

    return {
        **state,
        "patient_info": patient_info,
        "medications": medications,
        "adherence_stats": adherence_stats,
        "symptom_reports": symptom_reports,
        "chat_messages": chat_messages,
        "conditions": conditions,
        "allergies": allergies,
        "adr_assessments": adr_assessments,
    }


async def prepare_context(state: SummarizationState) -> SummarizationState:
    """Node 2: Transform raw DB data into structured prompt context dict."""
    patient_context = {
        "patient_info": state.get("patient_info", {}),
        "medications": state.get("medications", []),
        "adherence_stats": state.get("adherence_stats", {}),
        "symptom_reports": state.get("symptom_reports", []),
        "chat_messages": state.get("chat_messages", []),
        "conditions": state.get("conditions", []),
        "allergies": state.get("allergies", []),
        "adr_assessments": state.get("adr_assessments", []),
        "lookback_days": state.get("lookback_days", 30),
    }

    return {**state, "patient_context": patient_context}


async def generate_soap_note(state: SummarizationState) -> SummarizationState:
    """Node 3: Call Gemini Pro to generate the SOAP note.

    Uses GeminiClient with Gemini 3.1 Pro Preview for deep clinical reasoning.
    Falls back to error state if LLM call fails — does NOT raise.
    """
    try:
        client = GeminiClient(
            model=settings.gemini_pro_model,
            max_retries=2,
            timeout=90,
        )

        prompt = build_soap_prompt(state["patient_context"])
        soap_note = await client.generate_structured(
            prompt=prompt,
            response_model=SoapNote,
            system_instruction=SOAP_SYSTEM_INSTRUCTION,
            temperature=0.3,  # low temperature for clinical consistency
        )

        logger.info("SOAP note generated successfully")

        return {**state, "soap_note": soap_note.model_dump(), "error": None}

    except Exception as exc:
        logger.error("SOAP note generation failed: %s", exc)
        return {
            **state,
            "soap_note": {},
            "error": f"LLM generation failed: {exc}",
        }


async def store_soap_note(state: SummarizationState, db: Any) -> SummarizationState:
    """Node 4: Upsert the SOAP note into the soap_notes table.

    No-op if the LLM step failed, allowing graph to terminate cleanly.
    """
    if state.get("error"):
        return state

    soap = state["soap_note"]
    row = {
        "patient_id": state["patient_id"],
        "clinician_id": state["clinician_id"],
        "subjective": soap.get("subjective", ""),
        "objective": soap.get("objective", ""),
        "assessment": soap.get("assessment", ""),
        "plan": soap.get("plan", ""),
        "model_used": settings.gemini_pro_model,
        "generated_at": datetime.now(UTC).isoformat(),
    }

    result = await _execute(db.table("soap_notes").insert(row))
    inserted = cast(list[dict[str, Any]], result.data or [])
    note_id = inserted[0]["id"] if inserted else "unknown"

    logger.info("SOAP note stored (note_id=%s)", note_id)

    stored_note = inserted[0] if inserted else {**row, "id": note_id}

    return {**state, "stored_note_id": note_id, "soap_note": stored_note}


# ── Graph builder ─────────────────────────────────────────────────────────────


def build_summarization_graph(db: Any) -> Any:
    """Compile and return the LangGraph summarization workflow.

    The `db` (Supabase client) is bound via closure so nodes stay pure functions
    from LangGraph's perspective.

    Args:
        db: Supabase Client injected at build time

    Returns:
        Compiled LangGraph runnable
    """

    # Wrappers bind the db dependency (Dependency Inversion — nodes stay pure)
    async def _gather(state: SummarizationState) -> SummarizationState:
        return await gather_patient_data(state, db)

    async def _store(state: SummarizationState) -> SummarizationState:
        return await store_soap_note(state, db)

    workflow: StateGraph[SummarizationState] = StateGraph(SummarizationState)

    workflow.add_node("gather_patient_data", _gather)
    workflow.add_node("prepare_context", prepare_context)
    workflow.add_node("generate_soap_note", generate_soap_note)
    workflow.add_node("store_soap_note", _store)

    # Linear pipeline — no branching needed for MVP
    workflow.add_edge(START, "gather_patient_data")
    workflow.add_edge("gather_patient_data", "prepare_context")
    workflow.add_edge("prepare_context", "generate_soap_note")
    workflow.add_conditional_edges(
        "generate_soap_note",
        _next_node_after_generation,
        {"store_soap_note": "store_soap_note", END: END},
    )
    workflow.add_edge("store_soap_note", END)

    return workflow.compile()


# ── Private helpers ───────────────────────────────────────────────────────────


def _calculate_adherence_stats(logs: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate adherence stats from raw log rows (reused from AdherenceService logic)."""
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
    current_streak_days = _calculate_current_streak_days(logs)

    return {
        "overall_score": completed / total if total else 0.0,
        "medication_score": med_completed / len(med_logs) if med_logs else 0.0,
        "obligation_score": obl_completed / len(obl_logs) if obl_logs else 0.0,
        "current_streak_days": current_streak_days,
    }


def _next_node_after_generation(state: SummarizationState) -> str:
    """Route to store node only when generation succeeded."""
    if state.get("error"):
        return END
    return "store_soap_note"


def _calculate_current_streak_days(logs: list[dict[str, Any]]) -> int:
    """Calculate consecutive-day streak from the most recent logged day."""
    by_day_completed: dict[str, bool] = {}
    for log in logs:
        logged_at = log.get("logged_at")
        if not isinstance(logged_at, str) or len(logged_at) < 10:
            continue
        day = logged_at[:10]
        completed = log.get("status") == "completed"
        by_day_completed[day] = by_day_completed.get(day, False) or completed

    if not by_day_completed:
        return 0

    latest_day = datetime.fromisoformat(max(by_day_completed)).date()
    streak = 0
    cursor = latest_day

    while by_day_completed.get(cursor.isoformat(), False):
        streak += 1
        cursor -= timedelta(days=1)

    return streak


async def _execute(query: Any) -> Any:
    """Run blocking Supabase execute() off the event loop."""
    return await asyncio.to_thread(query.execute)
