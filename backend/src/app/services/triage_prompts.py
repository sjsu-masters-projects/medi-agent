"""Render a scored triage turn: the latest message, short history and record context.

The evaluation harness scores the production Care Coordinator instruction
(`app.adk.agents.care_coordinator.prompts.CARE_COORDINATOR_INSTRUCTION`); this module only
renders the turn it is asked about, with patient text fenced as data. The stand-in
classification instruction that used to live here was retired so the benchmark measures
the prompt that ships.
"""

from __future__ import annotations

from typing import Any


def build_triage_classification_prompt(
    *,
    message: str,
    language: str,
    history: list[dict[str, Any]],
    patient_context: dict[str, Any] | None = None,
    document_context: dict[str, Any] | None = None,
    conversation_state: dict[str, Any] | None = None,
) -> str:
    """Build the classification prompt from the latest message and short history."""
    recent_history = _format_history(history)
    context_block = _format_context(
        patient_context=patient_context,
        document_context=document_context,
        conversation_state=conversation_state,
    )
    return f"""Classify the latest patient message.

Patient language: {language}
{context_block}

Recent conversation (chronological):
{recent_history}

Latest patient message:
<PATIENT_MESSAGE>
{_sanitize_patient_text(message)}
</PATIENT_MESSAGE>

Respond with JSON:
{{
  "intent": "symptom | medication_question | schedule | document_question | mental_health | general",
  "urgency": "routine | urgent | emergency",
  "reason": "brief rationale"
}}
"""


def _format_history(history: list[dict[str, Any]]) -> str:
    if not history:
        return "- No prior messages"

    lines: list[str] = []
    for item in history[-8:]:
        role = str(item.get("role", "unknown")).upper()
        content = _sanitize_patient_text(str(item.get("content", "")))
        timestamp = str(item.get("created_at") or item.get("createdAt") or "")
        lines.append(f"- [{timestamp[:16]}] {role}: {content[:240]}")

    return "\n".join(lines) if lines else "- No prior messages"


def _sanitize_patient_text(text: str) -> str:
    cleaned = text.replace("```", "'''")
    return " ".join(cleaned.split())


def _format_context(
    *,
    patient_context: dict[str, Any] | None,
    document_context: dict[str, Any] | None,
    conversation_state: dict[str, Any] | None,
) -> str:
    meds = _format_medications(patient_context or {})
    conditions = _format_conditions(patient_context or {})
    symptoms = _format_recent_symptoms(patient_context or {})
    document_summary = _format_document_context(document_context)
    convo = _format_conversation_state(conversation_state or {})

    return f"""Clinical context:
- Active medications: {meds}
- Active conditions: {conditions}
- Recent symptoms: {symptoms}
- Document context: {document_summary}
- Conversation state: {convo}"""


def _format_medications(patient_context: dict[str, Any]) -> str:
    meds = patient_context.get("medications") or []
    if not meds:
        return "none"
    names = [str(item.get("name", "")).strip() for item in meds if isinstance(item, dict)]
    cleaned = [name for name in names if name]
    return ", ".join(cleaned[:5]) if cleaned else "none"


def _format_conditions(patient_context: dict[str, Any]) -> str:
    conditions = patient_context.get("conditions") or []
    if not conditions:
        return "none"
    names = [str(item.get("name", "")).strip() for item in conditions if isinstance(item, dict)]
    cleaned = [name for name in names if name]
    return ", ".join(cleaned[:5]) if cleaned else "none"


def _format_recent_symptoms(patient_context: dict[str, Any]) -> str:
    symptoms = patient_context.get("recent_symptoms") or []
    if not symptoms:
        return "none"
    fragments: list[str] = []
    for item in symptoms[:3]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("symptom", "")).strip()
        severity = item.get("severity")
        if not name:
            continue
        fragments.append(f"{name}(sev={severity})")
    return ", ".join(fragments) if fragments else "none"


def _format_document_context(document_context: dict[str, Any] | None) -> str:
    if not document_context:
        return "none"

    title = str(document_context.get("file_name") or document_context.get("id") or "document")
    summary = _sanitize_patient_text(str(document_context.get("summary") or ""))
    if not summary:
        return f"{title}: no summary available"
    return f"{title}: {summary[:360]}"


def _format_conversation_state(conversation_state: dict[str, Any]) -> str:
    if not conversation_state:
        return "none"

    summary = _sanitize_patient_text(str(conversation_state.get("summary") or ""))
    last_intent = str(conversation_state.get("last_intent") or "unknown")
    turns = str(conversation_state.get("turn_count") or "0")
    if summary:
        return f"last_intent={last_intent}, turns={turns}, summary={summary[:240]}"
    return f"last_intent={last_intent}, turns={turns}"
