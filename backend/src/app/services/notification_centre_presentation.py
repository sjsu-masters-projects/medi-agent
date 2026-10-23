"""Deterministic bilingual copy and allowlisted destinations, never model-written alerts."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from app.models.notification_centre import CentreItem

# These explain a saved transition; no copy asserts an automated clinical decision.
_COPY: dict[str, tuple[str, str, str, str]] = {
    "legacy_update": (
        "Earlier notification",
        "From the previous inbox; not a new task.",
        "Notificación anterior",
        "De tu buzón anterior; no es una tarea nueva.",
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
    # UX-006: a clinician cancelled a booked visit (event_type appointment_changed, status
    # cancelled). LOC-001 project-scope interface wording review recorded October 22.
    "appointment_cancelled": (
        "Appointment cancelled",
        "Your clinician cancelled this visit. See the reason in Visits.",
        "Cita cancelada",
        "Tu profesional clínico canceló esta cita. Consulta el motivo en Citas.",
    ),
    "appointment_response": (
        "Patient responded to an appointment",
        "Review the saved patient response.",
        "El paciente respondió a una cita",
        "Revisa la respuesta guardada del paciente.",
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
        "Documento del paciente pendiente de revisión",
        "El procesamiento y la revisión clínica son pasos distintos. Abre el documento correspondiente.",
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
        "Dificultad con el plan de atención reportada",
        "Un paciente reportó una dificultad con una actividad. Esto no confirma una reacción adversa a un medicamento.",
    ),
    "adr_review": (
        "Medication-safety review needed",
        "A candidate finding needs clinician review; it is not a confirmed diagnosis.",
        "Se necesita una revisión de seguridad de medicamentos",
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
        "El paciente respondió al seguimiento de seguridad de medicamentos",
        "Un paciente envió respuestas a preguntas de seguimiento. Revisa la evidencia "
        "actualizada; esto no es una decisión clínica.",
    ),
    # PAT-002-C follow-up. History only; the Spanish is a draft pending LOC-001 review.
    "symptom_report_reviewed": (
        "Your care team reviewed your symptom report",
        "See your symptom report.",
        "Tu equipo de atención revisó tu reporte de síntomas",
        "Consulta tu reporte de síntomas.",
    ),
    # MED-002 follow-up (099). Patient only; the question itself is on Today. The Spanish is a
    # draft pending LOC-001 review.
    "medication_confirmation_asked": (
        "Your care team asked about one of your medicines",
        "Open Today to answer. Your answer does not change any medicine or reminder.",
        "Tu equipo de atención te preguntó sobre uno de tus medicamentos",
        "Abre Hoy para responder. Tu respuesta no cambia ningún medicamento ni recordatorio.",
    ),
    "critical_result": (
        "Critical test result reported",
        "A patient's document reports a result the laboratory marked critical. Open the document to review it.",
        "Resultado crítico de laboratorio reportado",
        "Un documento del paciente informa un resultado que el laboratorio marcó como crítico. Ábrelo para revisarlo.",
    ),
    "care_plan_review": (
        "Care-team work item",
        "A care-plan item needs your care team. Open the patient to see it.",
        "Tarea del equipo de atención",
        "Un elemento del plan de atención requiere la atención de tu equipo. Abre el expediente del paciente para verlo.",
    ),
    # Clinician-only news; the name comes from the event, never stored clinical text. The
    # Spanish pair is an unapproved draft (LOC-001): no patient ever receives it.
    "handoff_shared": (
        "A colleague shared a handoff summary",
        "Open the approved summary. It is read-only; sharing does not give access to the record.",
        "Un colega compartió un resumen de entrega",
        "Abre el resumen aprobado. Es de solo lectura; compartirlo no da acceso al expediente.",
    ),
    "safety_flag": (
        "Patient safety flag needs review",
        "An automated flag was saved. Review the original conversation; this is not a clinical decision.",
        "Aviso de seguridad del paciente pendiente de revisión",
        "Se guardó un aviso automático. Revisa la conversación original; esto no es una decisión clínica.",
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

_SOURCE_LABELS = {
    "care_conversation_messages": "Private care-team conversation",
    "appointments": "Appointment record",
    "care_plan_versions": "Care-plan version",
    "care_plan_review_items": "Care-team work item",
    "documents": "Document workflow",
    "adherence_logs": "Patient-recorded activity response",
    "adr_assessments": "ADR review candidate",
    "adr_information_requests": "ADR information request",
    "symptom_reports": "Confirmed patient symptom report",
    "clinician_messages": "Earlier operational notice",
    "notifications": "Reminder or earlier notification",
    "care_handoff_shares": "Shared handoff summary",
}


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


# What a care-team work item asks (clinician-only; fixed wording, never record content).
_REVIEW_COPY = {
    "unowned_plan": (
        "A care plan has no care team",
        "A care team that ended left approved activities in this patient's Today. Adopt the plan "
        "or retire items. Nothing was removed.",
    ),
    "unassigned_legacy_plan": (
        "A care plan needs an owner",
        "An older care plan could not be assigned to one care team. Adopt it or retire items. "
        "Nothing was removed.",
    ),
    "cross_plan_conflict": (
        "Another care team asks about a conflict",
        "Another care team's plan has an instruction that conflicts with yours. Open the patient "
        "to read the question and reply.",
    ),
    "conflict_acknowledged": (
        "A conflict with your plan was acknowledged",
        "Another care team kept both instructions for a medicine on your plan and recorded a "
        "reason. Open the patient to read it.",
    ),
    "conflict_published_without": (
        "A conflicting item was left out of another plan",
        "Another care team published its plan without an item that conflicts with yours.",
    ),
    "conflict_reply": (
        "Your question about a conflict was answered",
        "The other care team replied. Open the patient to read the reply.",
    ),
    "unowned_clinical_record": (
        "A reviewed record needs a care team",
        "A reviewed record could not be assigned to one care team. Take it up from the patient's "
        "page if it is yours.",
    ),
}


# Clinic-level work for a clinic's admins. Never names a patient; fixed wording only.
_CLINIC_REVIEW_COPY = {
    "unowned_plan": (
        "A care plan at your clinic has no care team",
        "A care team that ended left approved activities in a patient's Today. Open the "
        "clinic review page to see who can adopt it. Nothing was removed.",
    ),
    "unassigned_legacy_plan": (
        "A care plan at your clinic needs an owner",
        "An older care plan could not be assigned to one care team. Open the clinic review "
        "page. Nothing was removed.",
    ),
}
_CLINIC_REVIEW_DEFAULT = (
    "Clinic care-plan work item",
    "A care-plan item at your clinic needs attention. Open the clinic review page.",
)


def _is_clinic_scope(row: dict[str, Any]) -> bool:
    return row.get("event_type") == "care_plan_review" and _metadata(row).get("scope") == "clinic"


def _review_link(row: dict[str, Any], role: str) -> Destination:
    if _is_clinic_scope(row):
        clinic = _identifier(_metadata(row).get("clinic_id")) or _identifier(row.get("clinic_id"))
        item = _identifier(row.get("source_id"))
        link = f"/care-plan-reviews?clinic={clinic}&item={item}" if clinic and item else None
        return (link, "Open clinic review", "Abrir revisión de la clínica")
    patient, item = _identifier(row.get("patient_id")), _identifier(row.get("source_id"))
    link = f"/patients/{patient}?tab=care-plan&review={item}" if patient and item else None
    return (link, "Open care-team item", "Abrir tarea del equipo")


def _plan_link(row: dict[str, Any], role: str) -> Destination:
    if row.get("event_type") == "care_plan_review":
        return _review_link(row, role)
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
    if row.get("source_type") == "symptom_reports":
        link = f"/patients/{patient}?tab=symptoms#symptom-{source}" if patient and source else None
        return (link, "Review reported product", "Revisar producto reportado")
    if row["event_type"] == "critical_result":
        if _metadata(row).get("source_accessible") is False:
            # Shared safety information; the document itself belongs to another care team.
            return (f"/patients/{patient}" if patient else None, "Open patient", "Abrir paciente")
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
    if row["event_type"] == "symptom_report_reviewed":
        # Patient-only: the report the review is about (the history detail screen).
        report = _identifier(row.get("source_id"))
        return (
            f"/symptoms/{report}" if report and role == "patient" else None,
            "View report",
            "Ver reporte",
        )
    if row["event_type"] == "medication_confirmation_asked":
        # Patient-only: the question card is on Today.
        return ("/today" if role == "patient" else None, "Open Today", "Abrir Hoy")
    if row["event_type"] == "handoff_shared":
        share = _identifier(row.get("source_id"))
        link = f"/handoff-shared/{share}" if share else "/handoff-shared"
        return (link, "Open shared summary", "Abrir resumen compartido")
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


def _review_notice_copy(row: dict[str, Any], spanish: bool) -> tuple[str, str]:
    """Who reviewed which report, from the saved event: no answers, no clinical content."""
    meta = _metadata(row)
    name, specialty = _name(meta.get("clinician_name")), _name(meta.get("specialty"))
    title = _name(meta.get("report_title"))
    who = f"Dr. {name}" if name else ("Tu equipo de atención" if spanish else "Your care team")
    if specialty:
        who += f" ({specialty})"
    if spanish:
        return (
            f"{who} revisó tu reporte de síntomas",
            f"Tu reporte: \u201c{title}\u201d." if title else "Consulta tu reporte de síntomas.",
        )
    return (
        f"{who} reviewed your symptom report",
        f"Your report: \u201c{title}\u201d." if title else "See your symptom report.",
    )


def _question_notice_copy(row: dict[str, Any], spanish: bool) -> tuple[str, str]:
    """Who asked, from the saved event. The medicine and question stay on the Today card."""
    name = _name(_metadata(row).get("clinician_name"))
    body = _COPY["medication_confirmation_asked"][3 if spanish else 1]
    if spanish:
        who = f"Dr. {name}" if name else "Tu equipo de atención"
        return (f"{who} te preguntó sobre uno de tus medicamentos", body)
    who = f"Dr. {name}" if name else "Your care team"
    return (f"{who} asked about one of your medicines", body)


def _display_copy(row: dict[str, Any], role: str, spanish: bool) -> tuple[str, str]:
    kind = str(row["event_type"])
    if kind == "safety_flag" and row.get("source_type") == "symptom_reports":
        # Clinician-only source, so no patient notification or generated translation.
        return (
            "Patient-reported product needs review",
            "A confirmed symptom report names a product not uniquely linked to the recorded "
            "medication list. Review identity before linking or adding. This is not a confirmed ADR.",
        )
    if kind == "critical_result" and _metadata(row).get("source_accessible") is False:
        # The result is safety information for every team; the document is another team's.
        return (
            "Critical test result reported",
            "A result the laboratory marked critical was reported for this patient. The "
            "document is held by another care team of this patient. Check on the patient.",
        )
    if kind == "symptom_report_reviewed":
        return _review_notice_copy(row, spanish)
    if kind == "medication_confirmation_asked":
        return _question_notice_copy(row, spanish)
    if kind == "handoff_shared" and _name(_metadata(row).get("actor_name")):
        author = _name(_metadata(row).get("actor_name"))
        return (f"{author} shared a handoff summary", _COPY["handoff_shared"][1])
    if kind == "care_plan_review" and _is_clinic_scope(row):
        return _CLINIC_REVIEW_COPY.get(
            str(_metadata(row).get("review_kind")), _CLINIC_REVIEW_DEFAULT
        )
    if kind == "care_plan_review":
        review = _REVIEW_COPY.get(str(_metadata(row).get("review_kind")))
        if review:
            return review
    if kind == "appointment_changed" and _metadata(row).get("status") == "cancelled":
        kind = "appointment_cancelled"
    copy = _COPY.get(
        kind,
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
        patient_name=(
            _name(row.get("patient_name"))
            if role == "clinician" and not _is_clinic_scope(row)
            else None
        ),
        clinic_name=_name(row.get("clinic_name")),
        clinic_id=_identifier(row.get("clinic_id")) if role == "clinician" else None,
        source_label=_SOURCE_LABELS.get(str(row.get("source_type")))
        if role == "clinician"
        else None,
        state_checked_at=datetime.now(UTC) if role == "clinician" else None,
    )
