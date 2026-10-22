"""Deterministic checks shared by every LOC-003 translation path.

A model can change a dose, swap a unit, flip a negation or alter a drug name while still
sounding fluent. These checks compare the source with the translation and never trust the
model's own claim. They are language-pair aware only through small equivalence tables.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

# Canonical unit for each spelling in en-US and es-MX.
_UNITS: dict[str, str] = {
    "mg": "mg",
    "miligramo": "mg",
    "miligramos": "mg",
    "milligram": "mg",
    "milligrams": "mg",
    "g": "g",
    "gramo": "g",
    "gramos": "g",
    "gram": "g",
    "grams": "g",
    "mcg": "mcg",
    "µg": "mcg",
    "μg": "mcg",
    "microgramo": "mcg",
    "microgramos": "mcg",
    "microgram": "mcg",
    "micrograms": "mcg",
    "ml": "ml",
    "mililitro": "ml",
    "mililitros": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "l": "l",
    "litro": "l",
    "litros": "l",
    "liter": "l",
    "liters": "l",
    "unit": "unit",
    "units": "unit",
    "unidad": "unit",
    "unidades": "unit",
    "ui": "unit",
    "iu": "unit",
    "%": "%",
    "tablet": "tablet",
    "tablets": "tablet",
    "tableta": "tablet",
    "tabletas": "tablet",
    "pill": "tablet",
    "pills": "tablet",
    "pastilla": "tablet",
    "pastillas": "tablet",
    "comprimido": "tablet",
    "comprimidos": "tablet",
    "capsule": "capsule",
    "capsules": "capsule",
    "cápsula": "capsule",
    "cápsulas": "capsule",
    "capsula": "capsule",
    "capsulas": "capsule",
    "drop": "drop",
    "drops": "drop",
    "gota": "drop",
    "gotas": "drop",
    "kg": "kg",
    "mmhg": "mmhg",
    "bpm": "bpm",
}

_UNIT_ALTERNATION = "|".join(sorted((re.escape(u) for u in _UNITS), key=len, reverse=True))
# 1,000 / 1.000 / 12,345.6 style, or a plain integer or decimal; then an optional unit.
_NUMBER = re.compile(
    rf"(?P<num>\d{{1,3}}(?:[.,]\d{{3}})+(?!\d)|\d+(?:[.,]\d+)?)"
    rf"(?:\s*(?P<unit>%|(?:{_UNIT_ALTERNATION})(?![\w])))?",
    re.IGNORECASE,
)
_THOUSANDS = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")

_NEGATION = re.compile(
    r"(?<![\w])(?:no|not|never|without|cannot|nunca|jamás|jamas|sin)(?![\w])|n[’']t(?![\w])",
    re.IGNORECASE,
)


def number_tokens(text: str) -> Counter[str]:
    """Count each number with its unit. Decimal commas fold; thousands separators do not.

    "2,5 ml" equals "2.5 ml" (a decimal comma). "1,000" and "1.000" stay distinct because
    the two languages read them differently, so a swap is reported as a changed number.
    """
    tokens: Counter[str] = Counter()
    for match in _NUMBER.finditer(text):
        number = match.group("num")
        if not _THOUSANDS.match(number):
            number = number.replace(",", ".")
        unit = (match.group("unit") or "").lower()
        tokens[f"{number}|{_UNITS.get(unit, unit)}"] += 1
    return tokens


def negation_present(text: str) -> bool:
    return bool(_NEGATION.search(text))


def same_language_negation_changed(source: str, target: str) -> bool:
    """Conservative check for an English original against its English back-translation.

    Never apply counts across languages: Spanish can legitimately double a negation.
    """
    return len(_NEGATION.findall(source)) != len(_NEGATION.findall(target))


def negation_flipped(source: str, target: str) -> bool:
    """True when a negation appears or disappears (counts are not compared across languages)."""
    return negation_present(source) != negation_present(target)


def changed_protected_terms(
    sources: Iterable[str], targets: Iterable[str], terms: Iterable[str]
) -> list[str]:
    """Protected names that are in the source text but missing, as whole words, in the target."""
    source_text = "\n".join(sources)
    target_text = "\n".join(targets)
    changed: list[str] = []
    for term in terms:
        if not term.strip():
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(term.strip())}(?!\w)", re.IGNORECASE)
        if pattern.search(source_text) and not pattern.search(target_text):
            changed.append(term)
    return changed


def guard_failure(source: str, target: str, protected: Iterable[str] = ()) -> str | None:
    """Return the first failing guard code, or None when the translation preserves the facts."""
    if number_tokens(source) != number_tokens(target):
        return "numbers_changed"
    if negation_flipped(source, target):
        return "negation_changed"
    if changed_protected_terms([source], [target], protected):
        return "medication_name_changed"
    return None
