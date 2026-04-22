"""Locale metadata and resource helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar

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
