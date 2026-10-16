"""The stored shape of a fact's English display fields (LOC-003), without model code.

A fact read from a Spanish document carries ``value["display_en"]``:

    {"source_locale": "es-MX", "status": "translated", "fields": {"name": ...},
     "name_source": "rxnorm", "model": ..., "translated_at": ...}

or ``{"source_locale": "es-MX", "status": "untranslated", "reason": ...}`` when the guard
or the provider left it as printed. The printed fields beside it remain the evidence and
are never replaced. These helpers stay import-light because the fact registry uses them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

DISPLAY_KEY = "display_en"
SPANISH = "es-MX"

# Wording fields per fact type. Everything else (values, units, ranges, flags, dates,
# providers and places) is shown exactly as printed. A medication's name is handled
# separately, from its RxNorm ingredient.
TRANSLATED_FIELDS: dict[str, tuple[str, ...]] = {
    "medication": ("dosage", "frequency", "route", "instructions", "status"),
    "condition": ("name", "status", "notes"),
    "allergy": ("allergen", "reaction", "severity"),
    "obligation": ("description", "frequency", "obligation_type"),
    "lab_result": ("test_name", "specimen", "panel"),
    "vital_sign": ("name",),
    "immunization": ("vaccine",),
    "procedure": ("name", "result"),
    "appointment": ("description",),
}


def display_text(value: Any) -> str:
    """A printed scalar as stripped text; anything else is not wording."""
    if isinstance(value, bool):
        return ""
    return str(value).strip() if isinstance(value, str | int | float) else ""


def _covered(fact_type: str) -> tuple[str, ...]:
    return (*TRANSLATED_FIELDS.get(fact_type, ()), "name")


def source_value(value: Mapping[str, Any]) -> dict[str, Any]:
    """The printed fact, without its English display fields."""
    return {key: item for key, item in value.items() if key != DISPLAY_KEY}


def attach(value: dict[str, Any], record: Mapping[str, Any] | None) -> dict[str, Any]:
    """Add a display record to a grounded value, keeping only fields still printed there.

    Grounding drops a field it could not find on the page; its English goes with it.
    """
    if not record:
        return value
    fields = {
        field: text
        for field, text in cast(dict[str, str], record.get("fields") or {}).items()
        if display_text(value.get(field))
    }
    if record.get("status") == "translated" and not fields:
        return value
    stored = {key: item for key, item in record.items() if key != "fields"}
    return {**value, DISPLAY_KEY: {**stored, **({"fields": fields} if fields else {})}}


def keep_display_if_unchanged(
    before: Mapping[str, Any], after: Mapping[str, Any], fact_type: str
) -> dict[str, Any]:
    """A corrected fact keeps its English only while the printed wording is unchanged."""
    corrected = dict(after)
    record = corrected.get(DISPLAY_KEY)
    if not isinstance(record, dict) or any(
        display_text(before.get(field)) != display_text(after.get(field))
        for field in _covered(fact_type)
    ):
        corrected.pop(DISPLAY_KEY, None)
    return corrected


def source_display(fact: Mapping[str, Any]) -> dict[str, Any] | None:
    """What the clinician portal needs to gloss a fact's printed evidence in English."""
    value = cast(dict[str, Any], fact.get("value") or {})
    record = value.get(DISPLAY_KEY)
    if not isinstance(record, dict):
        return None
    fact_type = str(fact.get("fact_type") or "")
    return {
        "fact_type": fact_type,
        "source_locale": record.get("source_locale"),
        "status": record.get("status"),
        "fields": record.get("fields") or {},
        "printed": {
            key: display_text(value.get(key))
            for key in _covered(fact_type)
            if display_text(value.get(key))
        },
    }


def audit_summary(value: Mapping[str, Any]) -> dict[str, Any] | None:
    """The audit trail records that English was written, how, and for which fields."""
    record = value.get(DISPLAY_KEY)
    if not isinstance(record, dict):
        return None
    return {
        "source_locale": record.get("source_locale"),
        "status": record.get("status"),
        "reason": record.get("reason"),
        "fields": sorted(cast(dict[str, str], record.get("fields") or {})),
        "name_source": record.get("name_source"),
        "model": record.get("model"),
    }
