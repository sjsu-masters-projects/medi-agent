"""Deterministic bilingual copy and allowlisted destinations, never model-written alerts."""

from collections.abc import Callable
from typing import Any, cast
from uuid import UUID

from app.models.notification_centre import CentreItem

# These explain a saved transition; no copy asserts an automated clinical decision.
_COPY: dict[str, tuple[str, str, str, str]] = {
    "legacy_update": (
        "Earlier notification",
        "Historical notification retained from the previous inbox. It is not a new review task.",
        "Notificación anterior",
        "Notificación conservada del buzón anterior. No es una nueva tarea de revisión.",
    ),
    "message_received": (
        "New care-team message",
        "Open your private conversation to read the message.",
        "Nuevo mensaje del equipo de atención",
        "Abre tu conversación privada para leer el mensaje.",
    ),
    "appointment_offered": (
        "Appointment offered",
        "Review the proposed time and respond in Visits.",
        "Propuesta de cita",
        "Revisa el horario propuesto y responde en Citas.",
    ),
    "appointment_changed": (
        "Appointment updated",
        "Review the current time and status in Visits.",
        "Cita actualizada",
        "Revisa el horario y el estado actual en Citas.",
    ),
    "appointment_response": (
        "Patient responded to an appointment",
        "Review the saved patient response.",
        "Respuesta a la cita",
        "Revisa la respuesta guardada.",
    ),
    "appointment_reminder": (
        "Appointment reminder",
        "Open Visits for the current time and location.",
        "Recordatorio de cita",
        "Abre Citas para consultar el horario y el lugar actual.",
    ),
    "care_plan_published": (
        "Your care plan was updated",
        "Your care team approved an updated plan. Review it in Today.",
        "Tu plan de cuidado se actualizó",
        "Tu equipo de atención aprobó un plan actualizado. Revísalo en Hoy.",
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
        "Open Records to see the document and its separate review status.",
        "Documento procesado",
        "Abre Registros para ver el documento y el estado de su revisión.",
    ),
    "document_failed": (
        "Document needs attention",
        "Processing did not finish. Open the document for available recovery steps.",
        "El documento necesita atención",
        "El procesamiento no se completó. Abre el documento para ver las opciones disponibles.",
    ),
    "document_reviewed": (
        "Document review updated",
        "Your care team recorded a review decision. See its status in Records.",
        "Revisión del documento actualizada",
        "Tu equipo de atención registró una decisión. Consulta el estado en Registros.",
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
        "Contact the requesting clinician through Care team messages.",
        "Tu equipo de atención solicita información",
        "Contacta al profesional que hizo la solicitud en Mensajes del equipo de atención.",
    ),
    "safety_flag": (
        "Patient safety flag needs review",
        "An automated flag was saved. Review the original conversation; this is not a clinical decision.",
        "Aviso de seguridad para revisión",
        "Se guardó un aviso automático. Requiere revisión; no es una decisión clínica.",
    ),
    "med_reminder": (
        "Medication reminder",
        "Open Today to see your approved activity and current status.",
        "Recordatorio de medicamento",
        "Abre Hoy para ver la actividad aprobada y su estado actual.",
    ),
    "obligation_reminder": (
        "Care-plan reminder",
        "Open Today to see your approved activity and current status.",
        "Recordatorio del plan de cuidado",
        "Abre Hoy para ver la actividad aprobada y su estado actual.",
    ),
}


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
    if row["event_type"] == "safety_flag":
        link = f"/patients/{patient}?tab=chat" if patient else None
    else:
        link = f"/medwatch?assessment={source}" if source else None
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
        clinician = _identifier(_metadata(row).get("clinician_id"))
        link = (
            f"/chat?view=care-team&recipient={clinician}" if clinician else "/chat?view=care-team"
        )
        return (link, "Contact care team", "Contactar al equipo de atención")
    return _LINKS.get(str(row["category"]), _follow_up_link)(row, role)


def _questions(row: dict[str, Any], spanish: bool) -> str:
    questions = _metadata(row).get("requested_information")
    if not isinstance(questions, list):
        return ""
    reviewed = [q for q in questions[:20] if isinstance(q, str) and 0 < len(q) <= 200]
    if not reviewed:
        return ""
    heading = (
        "Preguntas de tu profesional de salud (texto original):"
        if spanish
        else "Questions from your clinician (shown as written):"
    )
    return "\n\n" + heading + "\n" + "\n".join(reviewed)


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
        body = _name(row.get("clinic_name")) or body
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
        action_url=link if actionable else None,
        action_label=spanish_action if spanish else english_action,
        actionable=actionable,
        can_acknowledge=actionable and role == "clinician" and bool(row.get("can_acknowledge")),
        patient_name=_name(row.get("patient_name")) if role == "clinician" else None,
        clinic_name=_name(row.get("clinic_name")),
    )
