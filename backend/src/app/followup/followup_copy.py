"""Patient-facing copy for symptom follow-up, in every supported locale.

Named `followup_copy` rather than `copy` because a module called `copy` shadows the
standard library one, which ruff refuses (A005) and which breaks in ways that are hard to
read at the import site.

Two entries that used to live here are gone with the rule-based extractor they served: a
canned follow-up question and a canned assessment, both of which described a symptom
nobody had actually read. What replaces them is `report_unavailable` — an admission.
"""

from __future__ import annotations

from app.models.enums import Language

FOLLOWUP_COPY = {
    "default": {
        "logged_prefix": (
            "Thanks for sharing this about {symptom}. I logged it for follow-up "
            "(estimated severity {severity}/10)."
        ),
        "severe_suffix": " Please contact your care team today for urgent guidance.",
        "report_unavailable": (
            "I could not record the details of this symptom just now, and I would rather "
            "tell you than note something I am unsure of. Please try again in a few "
            "minutes, and contact your care team today if this is worrying you — if it is "
            "an emergency, call 911 or go to the nearest emergency department now."
        ),
    },
    Language.EN.value: {
        "logged_prefix": (
            "Thanks for sharing this about {symptom}. I logged it for follow-up "
            "(estimated severity {severity}/10)."
        ),
        "severe_suffix": " Please contact your care team today for urgent guidance.",
        "report_unavailable": (
            "I could not record the details of this symptom just now, and I would rather "
            "tell you than note something I am unsure of. Please try again in a few "
            "minutes, and contact your care team today if this is worrying you — if it is "
            "an emergency, call 911 or go to the nearest emergency department now."
        ),
    },
    Language.ES.value: {
        "logged_prefix": (
            "Gracias por compartir lo de {symptom}. Lo registré para seguimiento "
            "(severidad aproximada {severity}/10)."
        ),
        "severe_suffix": " Es importante contactar a tu equipo clínico hoy mismo.",
        "report_unavailable": (
            "No pude registrar los detalles de este síntoma en este momento, y prefiero "
            "decírtelo en lugar de anotar algo de lo que no estoy segura. Intenta de nuevo "
            "en unos minutos y contacta hoy a tu equipo clínico si esto te preocupa — si es "
            "una emergencia, llama al 911 o acude al servicio de urgencias más cercano ahora."
        ),
    },
}
