"""Server-side checks on a reply that used reference sources.

The model is told which sources it was given, but the citation the patient reads is not
left to it: the source line is written here from the tool results the turn actually
produced, and a source line the model wrote itself is removed. A reply that mentions a
dose the patient record and the sources do not contain is counted, so the check can be
measured before it is allowed to block anything.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.adk.tools.health_reference import KNOWLEDGE_SOURCES_STATE_KEY

_SOURCE_LINE = re.compile(r"^\s*(?:\*\*)?(?:sources?|fuentes?)\s*:.*$", re.I | re.M)
_DOSE = re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:mg|mcg|µg|g|ml|mL|units?|unidades|ui|iu)\b", re.I)
_MONTHS_ES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
_LABELS = {
    "en-US": {
        "lead": "Sources",
        "medlineplus": "MedlinePlus: {title} (checked {checked})",
        "dailymed": "DailyMed, FDA drug label (published {published})",
    },
    "es-MX": {
        "lead": "Fuentes",
        "medlineplus": "MedlinePlus: {title} (consultado el {checked})",
        "dailymed": "DailyMed, etiqueta de la FDA en inglés (publicada el {published})",
    },
}


def sources_from_event(event: Any) -> list[dict[str, Any]] | None:
    """This invocation's recorded sources, if this event's state delta carries them."""
    actions = getattr(event, "actions", None)
    delta = getattr(actions, "state_delta", None) if actions else None
    value = delta.get(KNOWLEDGE_SOURCES_STATE_KEY) if delta else None
    if not isinstance(value, dict):
        return None
    if value.get("invocation") != getattr(event, "invocation_id", None):
        return None
    sources = value.get("sources")
    return (
        [item for item in sources if isinstance(item, dict)] if isinstance(sources, list) else None
    )


def _day(value: str | None, locale: str) -> str:
    if not value:
        return "—"
    day = date.fromisoformat(value[:10])
    if locale == "es-MX":
        return f"{day.day} {_MONTHS_ES[day.month - 1]} {day.year}"
    return f"{day:%b} {day.day}, {day.year}"


def source_line(sources: list[dict[str, Any]], locale: str) -> str:
    """One line naming each distinct source used, in the reply's language."""
    labels = _LABELS["es-MX" if locale == "es-MX" else "en-US"]
    parts: list[str] = []
    for item in sources:
        template = labels.get(str(item.get("source")))
        if template is None:
            continue
        part = template.format(
            title=str(item.get("title") or "").strip() or "—",
            checked=_day(item.get("checked_on"), locale),
            published=_day(item.get("published_on") or item.get("checked_on"), locale),
        )
        if part not in parts:
            parts.append(part)
    return f"{labels['lead']}: " + "; ".join(parts) if parts else ""


def without_source_lines(text: str) -> str:
    """Remove "Sources:"/"Fuentes:" lines: the server writes those, and speech skips them."""
    return re.sub(r"\n{3,}", "\n\n", _SOURCE_LINE.sub("", text)).strip()


def unsupported_doses(reply: str, *grounding: str) -> list[str]:
    """Dose-like amounts in a reply that appear in none of the grounding texts."""
    allowed = {_normal(match) for text in grounding for match in _DOSE.findall(text)}
    return [match for match in _DOSE.findall(reply) if _normal(match) not in allowed]


def _normal(dose: str) -> str:
    return re.sub(r"\s+", "", dose.casefold().replace(",", "."))
