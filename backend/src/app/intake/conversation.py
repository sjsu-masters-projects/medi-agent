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
# Plain replies meaning "no product concern". Anything else that opens with a negation asks
# again: a sentence such as "no, but maybe ibuprofen" must never become a product name.
NO_CONCERN = {
    "no",
    "nope",
    "nah",
    "none",
    "nothing",
    "not really",
    "no concern",
    "no concerns",
    "no thanks",
    "no thank you",
    "no i'm not",
    "no im not",
    "i'm not",
    "im not",
    "not concerned",
    "i'm not concerned",
    "im not concerned",
    "no medicine",
    "no medicines",
    "ninguno",
    "ninguna",
    "nada",
    "no gracias",
    "no me preocupa",
    "no me preocupa nada",
    "no estoy preocupado",
    "no estoy preocupada",
    "no ninguno",
    "no ninguna",
    "no nada",
}
HEDGED_NEGATION = re.compile(
    r"^(no|not|nope|nah|i don't|i dont|i do not|creo que no|no creo|tal vez no|maybe not)\b(?!-)"
)
AFFIRMATION_PREFIX = re.compile(r"^\s*(?:yes|yeah|yep|s[ií])\s*[,:;.-]?\s+", re.IGNORECASE)
NO_OTHER_PRODUCTS = NO_CONCERN | {"no other", "no others", "ningun otro", "ninguna otra"}
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
        plain = _without_punctuation(value)
        if plain in NO_CONCERN:
            return "answered", {"concern": False}
        if HEDGED_NEGATION.match(plain):
            raise ValidationError("Please clarify this answer", code="INTAKE_REPLY_AMBIGUOUS")
        # Keep an unstructured product reply as reported, without a leading "yes". It cannot
        # create a medication or imply a match; structured details remain explicitly editable.
        name = AFFIRMATION_PREFIX.sub("", text.strip()).strip()
        if plain not in {"yes", "yeah", "yep", "si"} and name and len(name) <= 300:
            return "answered", {"concern": True, "name": name}
    raise ValidationError("Please clarify this answer", code="INTAKE_REPLY_AMBIGUOUS")


def _without_punctuation(value: str) -> str:
    return " ".join(value.replace("’", "'").replace(",", " ").split())


def reports_no_other_products(text: Any) -> bool:
    """True for a plain "none" reply, so a report does not claim products that were not named."""
    return isinstance(text, str) and _without_punctuation(normalized(text)) in NO_OTHER_PRODUCTS


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
