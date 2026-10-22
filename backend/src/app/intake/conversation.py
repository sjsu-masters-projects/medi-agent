"""Conservative interpretation of patient replies; never infer clinical answers."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.core.exceptions import ValidationError
from app.intake.library import Question


def normalized(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(c for c in value if not unicodedata.combining(c)).split()).strip(" .!?")


UNKNOWN = {
    "i don't know",
    "i don’t know",
    "unknown",
    "not sure",
    "i am not sure",
    "no se",
    "no estoy seguro",
    "no estoy segura",
}
DECLINED = {
    "skip",
    "skip this",
    "prefer not to answer",
    "i prefer not to answer",
    "prefiero no responder",
    "omitir",
    "saltar",
}
NUMBERS = {
    word: value
    for value, words in enumerate(
        (
            ("one", "uno", "una"),
            ("two", "dos"),
            ("three", "tres"),
            ("four", "cuatro"),
            ("five", "cinco"),
            ("six", "seis"),
            ("seven", "siete"),
            ("eight", "ocho"),
            ("nine", "nueve"),
            ("ten", "diez"),
        ),
        1,
    )
    for word in words
}


def interpret(question: Question, text: str) -> tuple[str, Any]:
    """Only explicit numbers/choices map to typed values; text stays verbatim."""
    value = normalized(text)
    if value in UNKNOWN:
        return "unknown", None
    if value in DECLINED:
        return "declined", None
    if question.answer_type == "text":
        return "answered", text.strip()
    if question.answer_type == "rating":
        number = NUMBERS.get(value)
        if number is None:
            match = re.fullmatch(r"(10|[1-9])(?:\s*(?:/|out of|de|sobre)\s*10)?", value)
            number = int(match[1]) if match else None
        if number is not None:
            return "answered", number
    elif question.answer_type == "boolean":
        if value in {"yes", "si"}:
            return "answered", True
        if value in {"no"}:
            return "answered", False
    elif question.answer_type == "product":
        if value in {"no", "none", "no concern", "ninguno", "ninguna"}:
            return "answered", {"concern": False}
        # Keep an unstructured product reply exactly as reported. It cannot create
        # a medication or imply a match; structured details remain explicitly editable.
        if value not in {"yes", "si"} and len(text.strip()) <= 300:
            return "answered", {"concern": True, "name": text.strip()}
    raise ValidationError("Please clarify this answer", code="INTAKE_REPLY_AMBIGUOUS")


def source_suggestions(text: str) -> dict[str, str | int]:
    """Quoted candidates require a separate patient acceptance; nothing is saved."""
    suggestions: dict[str, str | int] = {}
    if text.strip() and len(text) <= 1000:
        suggestions["description"] = text.strip()
    onset = re.search(r"\b(?:since|started|began|desde|empe[zóo]+)\s+([^.!?\n]{1,100})", text, re.I)
    if onset:
        suggestions["onset"] = onset[0].strip()
    rating = re.search(r"\b(10|[1-9])\s*(?:/|out of|de)\s*10\b", text, re.I)
    if rating:
        suggestions["severity"] = int(rating[1])
    return suggestions
