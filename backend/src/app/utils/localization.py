"""Locale metadata and resource helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal, TypeVar

from app.models.enums import Language, coerce_locale

T = TypeVar("T")

LOCALE_DISPLAY_NAMES: dict[str, str] = {
    Language.EN.value: "English (US)",
    Language.ES.value: "Spanish (Mexico)",
}


def get_locale_display_name(value: object) -> str:
    locale = coerce_locale(value).value
    return LOCALE_DISPLAY_NAMES.get(locale, locale)


def resolve_locale_resource(value: object, resources: Mapping[str, T]) -> T:
    locale = coerce_locale(value).value
    base_language = locale.split("-")[0]
    candidates = (locale, base_language, Language.EN.value, "default")

    for candidate in candidates:
        if candidate in resources:
            return resources[candidate]

    raise KeyError("Locale resource map must define a default or English fallback entry.")


# Strong, common function words only: names, doses and short replies ("ok") carry no
# signal, so detection answers only when the wording clearly reads as one language.
_SPANISH = re.compile(
    r"[áéíóúñ¿¡]|\b(el|la|los|las|del|con|por|para|cada|veces|semana|tome|tomar|después|"
    r"antes|minutos|vaso|agua|su|sus|en|al|y|que|pasa|si|se|me|mi|una|un|es|puedo|tengo|"
    r"como|dosis)\b",
    re.IGNORECASE,
)
_ENGLISH = re.compile(
    r"\b(the|and|with|of|for|each|every|times|day|daily|week|weekly|take|after|before|"
    r"minutes|glass|water|your|by|mouth|at|in|on|what|why|how|is|does|do|my|it|can|if|"
    r"should|i)\b",
    re.IGNORECASE,
)


def detect_locale(*texts: str) -> Literal["en-US", "es-MX"] | None:
    """Return a locale only when the wording clearly reads as one language."""
    text = " ".join(texts)
    spanish, english = len(_SPANISH.findall(text)), len(_ENGLISH.findall(text))
    if spanish >= 2 and spanish > 2 * english:
        return "es-MX"
    if english >= 2 and english > 2 * spanish:
        return "en-US"
    return None


def written_language(text: str, declared: object) -> Language:
    """The language a message is written in, or the declared one when it is unclear."""
    detected = detect_locale(text)
    return Language(detected) if detected else coerce_locale(declared)
