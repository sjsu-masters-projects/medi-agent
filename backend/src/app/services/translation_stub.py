"""Deterministic offline stand-in for the translation model (LOC-003).

Every LOC-003 path — care-plan second-language drafting, the clinician's back-translation,
fact display fields and message translation — needs a live Vertex AI model. When that model
is unreachable, as on a laptop or in CI, the translated-wording paths cannot be exercised at
all, so a reviewer cannot check the English-first display rules, the guards, the attestation
or the untranslated markers.

This module answers those calls locally instead. It is not a translator: it substitutes a
small bilingual glossary word by word and leaves everything else as written. That is
deliberate, because it makes the stub safe by construction for the things the guards check —
numbers, units, doses, medication names and negations all fall through untouched — while the
text still visibly changes language, which is what the display rules are read against.

It is off unless ``translation_stub_enabled`` is set, and it refuses to run in production.
Stubbed output is marked as such in its telemetry (``model_id`` ``offline-translation-stub``)
so a translation produced this way is never mistaken for a reviewed one, and must never be
approved as patient-facing wording.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping

from app.config import settings
from app.models.generation import GenerationResponse, GenerationTelemetry

#: Recorded as the model that produced a stubbed translation.
STUB_MODEL_ID = "offline-translation-stub"
STUB_PROVIDER = "offline-stub"

# A deliberately small en-US → es-MX glossary of the words this project's care-plan wording,
# facts and messages are actually written with. Anything absent is left exactly as written,
# which is why numbers, units and drug names survive unchanged.
_EN_TO_ES: dict[str, str] = {
    "a": "una",
    "after": "después de",
    "and": "y",
    "appointment": "cita",
    "as": "según",
    "at": "a las",
    "before": "antes de",
    "bedtime": "la hora de dormir",
    "blood": "sangre",
    "breakfast": "el desayuno",
    "by": "por",
    "capsule": "cápsula",
    "capsules": "cápsulas",
    "daily": "al día",
    "day": "día",
    "days": "días",
    "dinner": "la cena",
    "dose": "dosis",
    "drink": "toma",
    "each": "cada",
    "evening": "la noche",
    "every": "cada",
    "feet": "pies",
    "glass": "vaso",
    "glasses": "vasos",
    "in": "en",
    "injection": "inyección",
    "meals": "las comidas",
    "measure": "mide",
    "message": "mensaje",
    "morning": "la mañana",
    "mouth": "boca",
    "needed": "necesario",
    "night": "la noche",
    "nurse": "enfermera",
    "of": "de",
    "once": "una vez",
    "or": "o",
    "pressure": "presión",
    "record": "registra",
    "results": "resultados",
    "sugar": "azúcar",
    "take": "toma",
    "tablet": "tableta",
    "tablets": "tabletas",
    "test": "prueba",
    "the": "el",
    "three": "tres",
    "times": "veces",
    "twice": "dos veces",
    "visit": "visita",
    "walk": "camina",
    "water": "agua",
    "week": "semana",
    "weekly": "a la semana",
    "weight": "peso",
    "with": "con",
    "your": "tu",
    # Negations map to a negation, so the negation guard sees one on both sides.
    "no": "no",
    "not": "no",
    "never": "nunca",
    "without": "sin",
}

_ES_TO_EN: dict[str, str] = {
    "cada": "every",
    "cápsula": "capsule",
    "cápsulas": "capsules",
    "cita": "appointment",
    "comidas": "meals",
    "con": "with",
    "de": "of",
    "después": "after",
    "día": "day",
    "días": "days",
    "dos": "two",
    "dosis": "dose",
    "el": "the",
    "en": "in",
    "enfermera": "nurse",
    "inyección": "injection",
    "la": "the",
    "mensaje": "message",
    "mide": "measure",
    "nunca": "never",
    "no": "not",
    "o": "or",
    "peso": "weight",
    "pies": "feet",
    "por": "by",
    "presión": "pressure",
    "prueba": "test",
    "registra": "record",
    "resultados": "results",
    "sangre": "blood",
    "semana": "week",
    "sin": "without",
    "tableta": "tablet",
    "tabletas": "tablets",
    "toma": "take",
    "tres": "three",
    "tu": "your",
    "una": "a",
    "vaso": "glass",
    "vasos": "glasses",
    "veces": "times",
    "vez": "once",
    "visita": "visit",
    "y": "and",
    "agua": "water",
    "azúcar": "sugar",
    "camina": "walk",
    "al": "a",
    "antes": "before",
    "boca": "mouth",
    "cambios": "changes",
    "cena": "dinner",
    "desayuno": "breakfast",
    "dormir": "sleep",
    "hora": "time",
    "las": "the",
    "los": "the",
    "mañana": "morning",
    "necesario": "needed",
    "noche": "night",
    "según": "as",
    "un": "a",
}

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def stub_enabled() -> bool:
    """Whether translation calls are answered locally rather than by the model.

    Production never stubs a translation, whatever the setting says: unreviewed machine
    wording standing in for a translation is a clinical-safety problem, not a convenience.
    """
    return bool(getattr(settings, "translation_stub_enabled", False)) and not settings.is_production


def translate_text(text: str, target_locale: str) -> str:
    """Substitute the glossary word by word; everything else is left exactly as written.

    Numbers, units, doses, drug names and punctuation are not words in the glossary, so they
    pass through unchanged and the deterministic guards pass by construction.
    """
    glossary = _EN_TO_ES if target_locale == "es-MX" else _ES_TO_EN

    def replace(match: re.Match[str]) -> str:
        word = match.group(0)
        mapped = glossary.get(word.lower())
        if mapped is None:
            return word
        return mapped.capitalize() if word[:1].isupper() else mapped

    return _WORD.sub(replace, text)


def translate_fields(fields: Mapping[str, str], target_locale: str) -> dict[str, str]:
    """Translate every field of a wording or fact payload into ``target_locale``."""
    return {key: translate_text(value, target_locale) for key, value in fields.items()}


def stub_response(text: str) -> GenerationResponse:
    """Wrap stubbed JSON as a provider response, marked as stub-produced."""
    return GenerationResponse(
        text=text,
        telemetry=GenerationTelemetry(provider=STUB_PROVIDER, model=STUB_MODEL_ID, latency_ms=0),
    )


async def generate_or_stub(
    *,
    stub: Callable[[], str],
    generate: Callable[[], Awaitable[GenerationResponse]],
) -> GenerationResponse:
    """Answer a translation call from the stub when it is on, otherwise run ``generate``.

    Callers pass ``stub`` as a closure over the structured input they already hold, so the
    stub never parses a prompt and cannot drift from the schema the caller validates.
    """
    if stub_enabled():
        return stub_response(stub())
    return await generate()
