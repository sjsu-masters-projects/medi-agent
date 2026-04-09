"""SOAP note prompt templates for the Summarization Agent.

Model: Gemini 3.1 Pro Preview (deep reasoning required for clinical documentation).
All prompts are module-level constants — change here, applies everywhere.
"""

from __future__ import annotations

SOAP_SYSTEM_INSTRUCTION = """You are a clinical documentation specialist AI assistant embedded
in the MediAgent healthcare platform. Your role is to generate accurate, concise, and structured
SOAP (Subjective, Objective, Assessment, Plan) notes from patient data.

Guidelines:
- Use precise medical terminology appropriate for clinician review
- Be factual — only include information present in the provided data
- Highlight any medication adherence concerns or ADR flags explicitly
- Keep each section focused and clinically relevant
- Do NOT fabricate lab values, diagnoses, or medications not present in the data
- Format the Plan section with numbered action items where possible"""


def build_soap_prompt(patient_context: dict) -> str:
    """Construct the SOAP note generation prompt from aggregated patient data.

    Args:
        patient_context: Dict with keys: patient_info, medications, adherence_stats,
                         symptom_reports, chat_messages, conditions, allergies, adr_assessments

    Returns:
        Formatted prompt string ready for GeminiClient.generate_structured()
    """
    patient = patient_context.get("patient_info", {})
    medications = patient_context.get("medications", [])
    adherence = patient_context.get("adherence_stats", {})
    symptoms = patient_context.get("symptom_reports", [])
    chat_messages = patient_context.get("chat_messages", [])
    conditions = patient_context.get("conditions", [])
    allergies = patient_context.get("allergies", [])
    adr_assessments = patient_context.get("adr_assessments", [])
    lookback_days = patient_context.get("lookback_days", 30)

    # Format medications list
    med_lines = []
    for med in medications[:20]:  # cap to avoid token overflow
        med_lines.append(
            f"  - {med.get('name', 'Unknown')} {med.get('dosage', '')} "
            f"{med.get('frequency', '')} ({"active" if med.get('is_active') else "inactive"})"
        )
    meds_text = "\n".join(med_lines) if med_lines else "  No medications on file"

    # Format conditions
    conditions_text = ", ".join(
        c.get("name", c.get("icd10_code", "Unknown")) for c in conditions
    ) or "None documented"

    # Format allergies
    allergies_text = ", ".join(
        f"{a.get('allergen', 'Unknown')} ({a.get('severity', 'unknown')})" for a in allergies
    ) or "NKDA"

    # Format recent symptoms
    symptom_lines = []
    for s in symptoms[:10]:
        onset_str = f", onset: {s['onset']}" if s.get("onset") else ""
        adr_str = " [ADR flagged]" if s.get("flagged_for_adr") else ""
        symptom_lines.append(
            f"  - {s.get('symptom', 'Unknown')} — severity {s.get('severity', '?')}/10"
            f"{onset_str}{adr_str}"
        )
    symptoms_text = "\n".join(symptom_lines) if symptom_lines else "  No symptoms reported"

    # Format ADR assessments
    adr_lines = []
    for adr in adr_assessments[:5]:
        adr_lines.append(
            f"  - Naranjo score: {adr.get('naranjo_score', 'N/A')} "
            f"({adr.get('causality', 'unknown')}), "
            f"Status: {adr.get('status', 'unknown')}"
        )
    adr_text = "\n".join(adr_lines) if adr_lines else "  No active ADR assessments"

    # Format recent chat context (last 5 patient messages)
    patient_chat = [
        m for m in chat_messages if m.get("role") == "user"
    ][-5:]
    chat_text = "\n".join(
        f"  [{m.get('created_at', '')[:10]}] {m.get('content', '')[:200]}"
        for m in patient_chat
    ) or "  No recent chat messages"

    # Build the full prompt
    return f"""Generate a SOAP note for the following patient based on data from the last {lookback_days} days.

PATIENT INFORMATION:
- Name: {patient.get('first_name', 'Unknown')} {patient.get('last_name', '')}
- DOB: {patient.get('date_of_birth', 'Not on file')}
- Active Conditions: {conditions_text}
- Known Allergies: {allergies_text}

ACTIVE MEDICATIONS:
{meds_text}

ADHERENCE DATA (last {lookback_days} days):
- Overall Score: {adherence.get('overall_score', 0):.0%}
- Medication Score: {adherence.get('medication_score', 0):.0%}
- Obligation Score: {adherence.get('obligation_score', 0):.0%}
- Current Streak: {adherence.get('current_streak_days', 0)} days

RECENT SYMPTOMS:
{symptoms_text}

ADR ASSESSMENTS:
{adr_text}

PATIENT-REPORTED (Chat):
{chat_text}

Generate a clinical SOAP note with four sections: Subjective, Objective, Assessment, Plan.
Respond with valid JSON matching this schema:
{{
  "subjective": "string — patient-reported symptoms, complaints, history",
  "objective": "string — observable findings, adherence data, ADR scores, measurable data",
  "assessment": "string — clinical interpretation, differential, risk level",
  "plan": "string — numbered action items for treatment, follow-up, monitoring"
}}

JSON response:"""
