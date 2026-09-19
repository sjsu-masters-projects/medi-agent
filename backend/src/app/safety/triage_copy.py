"""Patient-facing safety copy, in every supported locale.

This sits beside the deterministic rules rather than in an agent package, for the same
reason the rules do: the agent runtime is being replaced, and the words a patient is shown
in an emergency must not be deleted along with it. It previously lived inside the LangGraph
triage module, which WS8 removes — so the emergency and self-harm responses would have gone
with it.

`resolve_locale_resource` falls back locale -> base language -> English -> `default`, so a
map only needs `default` to be present. Both supported locales are spelled out in full
here anyway: an emergency is the worst possible moment to fall back to a language the
patient does not read.
"""

from __future__ import annotations

from app.models.enums import Language

TRIAGE_COPY = {
    "default": {
        "emergency_response": (
            "This may be an emergency. Please call 911 now or go to the nearest emergency "
            "department immediately. If possible, notify your care team as well."
        ),
        "mental_health_emergency_response": (
            "If you are in immediate danger, call 911 now. If you are thinking about hurting "
            "yourself or feeling unsafe, call or text 988 (Suicide and Crisis Lifeline) right "
            "away — they are available 24/7. You are not alone, and help is available."
        ),
        "fallback_general": (
            "Thanks for sharing this. I am here to help and can continue tracking your symptoms."
        ),
        "fallback_medication_question": (
            "I can help track your medication-related concerns. If symptoms worsen, please "
            "contact your care team right away."
        ),
        "fallback_document_question": (
            "I can help explain the attached record in plain language. I will stick to what is "
            "available in your record and suggest questions for your care team when details are unclear."
        ),
        "fallback_schedule": (
            "I can help you prepare scheduling questions. For appointment changes, please confirm "
            "directly with your clinic."
        ),
        "fallback_mental_health": (
            "I am sorry you are feeling this way. If you might hurt yourself or feel unsafe, call "
            "988 or emergency services now. Otherwise, contact your care team today for support."
        ),
        "fallback_urgent": (
            "Thank you for sharing this. Please contact your care team today for timely "
            "clinical guidance."
        ),
        "fallback_non_clinical": (
            "I am focused on health support. For medication, symptoms, records, or appointments, "
            "I can give more specific help."
        ),
        "service_unavailable": (
            "I am having trouble answering right now, and I would rather tell you that than "
            "guess. Please try again in a few minutes. If something feels urgent, contact your "
            "care team today — and if this is an emergency, call 911 or go to the nearest "
            "emergency department now."
        ),
    },
    Language.EN.value: {
        "emergency_response": (
            "This may be an emergency. Please call 911 now or go to the nearest emergency "
            "department immediately. If possible, notify your care team as well."
        ),
        "mental_health_emergency_response": (
            "If you are in immediate danger, call 911 now. If you are thinking about hurting "
            "yourself or feeling unsafe, call or text 988 (Suicide and Crisis Lifeline) right "
            "away — they are available 24/7. You are not alone, and help is available."
        ),
        "fallback_general": (
            "Thanks for sharing this. I am here to help and can continue tracking your symptoms."
        ),
        "fallback_medication_question": (
            "I can help track your medication-related concerns. If symptoms worsen, please "
            "contact your care team right away."
        ),
        "fallback_document_question": (
            "I can help explain the attached record in plain language. I will stick to what is "
            "available in your record and suggest questions for your care team when details are unclear."
        ),
        "fallback_schedule": (
            "I can help you prepare scheduling questions. For appointment changes, please confirm "
            "directly with your clinic."
        ),
        "fallback_mental_health": (
            "I am sorry you are feeling this way. If you might hurt yourself or feel unsafe, call "
            "988 or emergency services now. Otherwise, contact your care team today for support."
        ),
        "fallback_urgent": (
            "Thank you for sharing this. Please contact your care team today for timely "
            "clinical guidance."
        ),
        "fallback_non_clinical": (
            "I am focused on health support. For medication, symptoms, records, or appointments, "
            "I can give more specific help."
        ),
        "service_unavailable": (
            "I am having trouble answering right now, and I would rather tell you that than "
            "guess. Please try again in a few minutes. If something feels urgent, contact your "
            "care team today — and if this is an emergency, call 911 or go to the nearest "
            "emergency department now."
        ),
    },
    Language.ES.value: {
        "emergency_response": (
            "Esto podría ser una emergencia. Llama al 911 ahora o acude al servicio de "
            "urgencias más cercano de inmediato. Si puedes, avisa también a tu equipo clínico."
        ),
        "mental_health_emergency_response": (
            "Si estás en peligro inmediato, llama al 911 ahora. Si tienes pensamientos de "
            "hacerte daño o no te sientes a salvo, llama o envía un mensaje al 988 (Línea de "
            "Prevención del Suicidio y Crisis) de inmediato — están disponibles 24/7. No estás "
            "solo y hay ayuda disponible."
        ),
        "fallback_general": (
            "Gracias por el mensaje. Estoy aquí para ayudarte y puedo seguir dando seguimiento a tus síntomas."
        ),
        "fallback_medication_question": (
            "Puedo ayudarte a revisar tus síntomas relacionados con medicamentos. Si notas "
            "empeoramiento, contacta a tu equipo clínico de inmediato."
        ),
        "fallback_document_question": (
            "Puedo ayudarte a explicar el documento adjunto en lenguaje sencillo. Me basaré en "
            "la información disponible y sugeriré preguntas para tu equipo clínico si algo no queda claro."
        ),
        "fallback_schedule": (
            "Puedo ayudarte a preparar preguntas sobre citas. Para cambiar una cita, confirma "
            "directamente con tu clínica."
        ),
        "fallback_mental_health": (
            "Siento que te estés sintiendo así. Si podrías hacerte daño o no te sientes a salvo, "
            "llama al 988 o a emergencias ahora. Si no, contacta a tu equipo clínico hoy para recibir apoyo."
        ),
        "fallback_urgent": (
            "Gracias por compartir esto. Es importante que hables con tu equipo clínico hoy "
            "mismo para una evaluación oportuna."
        ),
        "fallback_non_clinical": (
            "Estoy enfocada en apoyo de salud. Si tienes preguntas sobre medicamentos, síntomas, "
            "documentos o citas, puedo ayudarte mejor."
        ),
        "service_unavailable": (
            "En este momento tengo problemas para responder, y prefiero decírtelo en lugar de "
            "adivinar. Por favor intenta de nuevo en unos minutos. Si algo te preocupa, contacta "
            "hoy a tu equipo clínico — y si es una emergencia, llama al 911 o acude al servicio "
            "de urgencias más cercano ahora."
        ),
    },
}
