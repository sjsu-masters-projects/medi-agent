"""Deterministic bilingual copy and allowlisted destinations, never model-written alerts."""

from collections.abc import Callable
from typing import Any, cast
from uuid import UUID

from app.models.notification_centre import CentreItem

# These explain a saved transition; no copy asserts an automated clinical decision.
_COPY: dict[str, tuple[str, str, str, str]] = {
    "legacy_update": (
        "Earlier notification",
        "From the previous inbox; not a new task.",
        "Notificación anterior",
        "De tu buzón anterior.",
    ),
    "message_received": (
        "New care-team message",
        "Open the conversation to read it.",
        "Nuevo mensaje del equipo de atención",
        "Abre la conversación para leerlo.",
    ),
    "appointment_offered": (
        "Appointment offered",
        "Choose a time in Visits.",
        "Propuesta de cita",
        "Elige un horario en Citas.",
    ),
    "appointment_changed": (
        "Appointment updated",
        "See the current time in Visits.",
        "Cita actualizada",
        "Consulta el horario actual en Citas.",
    ),
    "appointment_response": (
        "Patient responded to an appointment",
        "Review the saved patient response.",
        "Respuesta a la cita",
        "Revisa la respuesta guardada.",
    ),
    "appointment_reminder": (
        "Appointment reminder",
        "Time and place are in Visits.",
        "Recordatorio de cita",
        "El horario y el lugar están en Citas.",
    ),
    "care_plan_published": (
        "Your care plan was updated",
        "Your care team approved changes. See Today.",
        "Tu plan de cuidado se actualizó",
        "Tu equipo de atención aprobó cambios. Consulta Hoy.",
    ),
    "care_plan_draft": (
        "Care-plan draft ready for review",
        "This draft is not published. Review sources, wording and blockers.",
        "Borrador del plan listo para revisión",
        "Este borrador no está publicado. Revisa las fuentes, el texto y los bloqueos.",
    ),
    "document_review": (
        "Patient document awaiting review",
        "Parsing and clinical review are separate. Open the exact document.",
        "Documento pendiente de revisión",
        "El procesamiento y la revisión clínica son pasos distintos.",
    ),
    "document_processed": (
        "Document processing completed",
        "See it in Records.",
        "Documento procesado",
        "Consúltalo en Registros.",
    ),
    "document_failed": (
        "Document needs attention",
        "Processing didn't finish. Open it for next steps.",
        "El documento necesita atención",
        "El procesamiento no terminó. Ábrelo para ver los siguientes pasos.",
    ),
    "document_reviewed": (
        "Document review updated",
        "Your care team reviewed it. See Records.",
        "Revisión del documento actualizada",
        "Tu equipo de atención lo revisó. Consulta Registros.",
    ),
    "barrier_reported": (
        "Care-plan barrier reported",
        "A patient reported difficulty with an activity. This is not a confirmed adverse drug reaction.",
        "Dificultad reportada",
        "Se reportó una dificultad con una actividad. Esto no confirma una reacción adversa a un medicamento.",
    ),
    "adr_review": (
        "Medication-safety review needed",
        "A candidate finding needs clinician review; it is not a confirmed diagnosis.",
        "Revisión de seguridad pendiente",
        "Un hallazgo candidato necesita revisión clínica; no es un diagnóstico confirmado.",
    ),
    "adr_information_requested": (
        "Your care team requested information",
        "Answer a few questions in the app about a symptom you already reported. "
        "Describe only what already happened.",
        "Tu equipo de atención solicita información",
        "Responde en la app unas preguntas sobre un síntoma que ya reportaste. "
        "Describe solo lo que ya pasó.",
    ),
    # Clinician-only; the patient's answers stay in the assessment. No clinical content.
    "adr_information_answered": (
        "Patient answered medication-safety follow-up",
        "A patient sent answers to follow-up questions. Review the updated evidence; "
        "this is not a clinical decision.",
        "El paciente respondió el seguimiento de seguridad",
        "Un paciente envió respuestas a preguntas de seguimiento. Revisa la evidencia "
        "actualizada; esto no es una decisión clínica.",
    ),
    "critical_result": (
        "Critical test result reported",
        "A patient's document reports a result the laboratory marked critical. Open the document to review it.",
        "Resultado crítico reportado",
        "Un documento informa un resultado que el laboratorio marcó como crítico. Ábrelo para revisarlo.",
    ),
    "safety_flag": (
        "Patient safety flag needs review",
        "An automated flag was saved. Review the original conversation; this is not a clinical decision.",
        "Aviso de seguridad para revisión",
        "Se guardó un aviso automático. Requiere revisión; no es una decisión clínica.",
    ),
    "med_reminder": (
        "Medication reminder",
        "It's on your Today list.",
        "Recordatorio de medicamento",
        "Está en tu lista de Hoy.",
    ),
    "obligation_reminder": (
        "Care-plan reminder",
        "It's on your Today list.",
        "Recordatorio del plan de cuidado",
        "Está en tu lista de Hoy.",
    ),
}

# Fixed (en-US, es-MX) wording per patient-answerable question key. Stored values are
# never echoed: anything outside this allowlist is dropped.
_QUESTION_WORDING: dict[str, tuple[str, str]] = {
    "reappeared_on_rechallenge": (
        "Whether the symptom came back after restarting this medicine",
        "Si el síntoma volvió después de reiniciar este medicamento",
    ),
    "dose_response": (
        "Whether the symptom changed after a dose change your clinician directed",
        "Si el síntoma cambió después de un cambio de dosis indicado por tu profesional de salud",
    ),
    "similar_previous_reaction": (
        "Whether you have had a similar reaction to this medicine before",
        "Si has tenido antes una reacción similar a este medicamento",
    ),
}
_MAX_LISTED_QUESTIONS = 3


def _identifier(value: Any) -> str | None:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def _name(value: Any) -> str | None:
    if not isinstance(value, str) or _identifier(value):
        return None
    return " ".join(value.split())[:160] or None


Destination = tuple[str | None, str, str]


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], row["metadata"]) if isinstance(row.get("metadata"), dict) else {}


def _message_link(row: dict[str, Any], role: str) -> Destination:
    thread = _identifier(_metadata(row).get("conversation_id")) or _identifier(row.get("source_id"))
    root = "/chat?view=care-team&conversation=" if role == "patient" else "/messages?conversation="
    return (root + thread if thread else None, "Open conversation", "Abrir conversación")


def _appointment_link(row: dict[str, Any], role: str) -> Destination:
    appointment = _identifier(_metadata(row).get("appointment_id")) or _identifier(
        row.get("source_id")
    )
    root = "/visits?appointmentId=" if role == "patient" else "/appointments?appointmentId="
    return (root + appointment if appointment else None, "View appointment", "Ver cita")


def _document_link(row: dict[str, Any], role: str) -> Destination:
    source, patient = _identifier(row.get("source_id")), _identifier(row.get("patient_id"))
    link = None
    if source and (role == "patient" or patient):
        link = (
            f"/records?document={source}"
            if role == "patient"
            else f"/patients/{patient}?tab=documents#document-{source}"
        )
    return (link, "Open document", "Abrir documento")


def _plan_link(row: dict[str, Any], role: str) -> Destination:
    patient = _identifier(row.get("patient_id"))
    link = (
        "/today?view=care-plan"
        if role == "patient"
        else (f"/patients/{patient}?tab=care-plan" if patient else None)
    )
    return (link, "Open care plan", "Abrir plan de cuidado")


def _reminder_link(row: dict[str, Any], role: str) -> Destination:
    target = _identifier(_metadata(row).get("target_id")) or _identifier(row.get("source_id"))
    return (f"/today?activity={target}" if target else "/today", "Open Today", "Abrir Hoy")


def _safety_link(row: dict[str, Any], role: str) -> Destination:
    patient, source = _identifier(row.get("patient_id")), _identifier(row.get("source_id"))
    if row["event_type"] == "critical_result":
        link = (
            f"/patients/{patient}?tab=documents#document-{source}" if patient and source else None
        )
        return (link, "Open document", "Abrir documento")
    if row["event_type"] == "safety_flag":
        link = f"/patients/{patient}?tab=chat" if patient else None
    else:
        # A request-sourced alert names its assessment; otherwise the source is one.
        assessment = _identifier(_metadata(row).get("adr_assessment_id")) or source
        link = f"/medwatch?assessment={assessment}" if assessment else None
    return (link, "Review source", "Revisar fuente")


def _follow_up_link(row: dict[str, Any], role: str) -> Destination:
    patient = _identifier(row.get("patient_id"))
    target = _identifier(_metadata(row).get("target_id")) or _identifier(row.get("source_id"))
    link = f"/patients/{patient}?tab=adherence&activity={target}" if patient and target else None
    return (link, "View reported barrier", "Ver dificultad reportada")


_LINKS: dict[str, Callable[[dict[str, Any], str], Destination]] = {
    "messages": _message_link,
    "appointments": _appointment_link,
    "documents": _document_link,
    "care_plans": _plan_link,
    "reminders": _reminder_link,
    "safety": _safety_link,
}


def destination(row: dict[str, Any], role: str) -> Destination:
    if row["event_type"] == "adr_information_requested" and role == "patient":
        # Since 063 the source is the request itself; earlier items name the assessment.
        # The follow-up view resolves either.
        source = _identifier(row.get("source_id"))
        parameter = (
            "request" if row.get("source_type") == "adr_information_requests" else "assessment"
        )
        link = f"/chat?view=follow-up&{parameter}={source}" if source else "/chat?view=follow-up"
        return (link, "Answer questions", "Responder preguntas")
    return _LINKS.get(str(row["category"]), _follow_up_link)(row, role)


def _questions(row: dict[str, Any], spanish: bool) -> str:
    requested = _metadata(row).get("requested_information")
    if not isinstance(requested, list):
        return ""
    keys: list[str] = []
    for value in requested:
        if isinstance(value, str) and value in _QUESTION_WORDING and value not in keys:
            keys.append(value)
            if len(keys) == _MAX_LISTED_QUESTIONS:
                break
    if not keys:
        return ""
    heading = "Tu equipo de atención pregunta sobre:" if spanish else "Your care team asks about:"
    lines = ["• " + _QUESTION_WORDING[key][int(spanish)] for key in keys]
    return "\n\n" + heading + "\n" + "\n".join(lines)


def _display_copy(row: dict[str, Any], role: str, spanish: bool) -> tuple[str, str]:
    copy = _COPY.get(
        str(row["event_type"]),
        (
            "Update available",
            "Open the source to review the saved update.",
            "Actualización disponible",
            "Abre la fuente para revisar la actualización guardada.",
        ),
    )
    title, body = copy[2:] if spanish else copy[:2]
    if row["event_type"] == "adr_information_requested":
        body += _questions(row, spanish)
    if row["event_type"] == "message_received":
        name = _name(row.get("actor_name" if role == "patient" else "patient_name"))
        if name:
            title = f"Nuevo mensaje de {name}" if spanish else f"New message from {name}"
        # Clinicians already see the patient and clinic on the row's context line.
        body = (_name(row.get("clinic_name")) or body) if role == "patient" else ""
    return title, body


def present_item(row: dict[str, Any], role: str, locale: str) -> CentreItem:
    spanish = role == "patient" and locale == "es-MX"
    title, body = _display_copy(row, role, spanish)
    link, english_action, spanish_action = destination(row, role)
    actionable = bool(row.get("actionable", True))
    return CentreItem(
        id=row["id"],
        event_type=row["event_type"],
        category=row["category"],
        title=title,
        body=body,
        created_at=row["created_at"],
        is_read=bool(row.get("is_read")),
        # History keeps its exact-source link; only the call to act is dropped.
        action_url=link,
        action_label=(
            (spanish_action if spanish else english_action)
            if actionable
            else ("Ver" if spanish else "View")
        ),
        actionable=actionable,
        can_acknowledge=actionable and role == "clinician" and bool(row.get("can_acknowledge")),
        patient_name=_name(row.get("patient_name")) if role == "clinician" else None,
        clinic_name=_name(row.get("clinic_name")),
    )
