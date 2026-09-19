"""The classifications that must never depend on a model.

Self-harm and medical emergencies are decided by keyword because the cost of a model
getting one wrong is not recoverable later in the turn. Both keyword sets cover English
and Mexican Spanish, including unaccented spellings, since a patient in distress is not
going to type carefully.

This module is deliberately free of framework imports. It was extracted from the triage
LangGraph module so that replacing the agent runtime cannot disturb the safety rules, and
so that every entry point — streaming, non-streaming, or whatever comes next — reaches the
same floor. A path that forgets to call it is a safety regression, which is why the
callers are covered by their own tests rather than trusting convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

IntentType = Literal[
    "symptom",
    "medication_question",
    "schedule",
    "document_question",
    "mental_health",
    "general",
]
UrgencyType = Literal["routine", "urgent", "emergency"]

EMERGENCY_KEYWORDS = frozenset(
    {
        # English
        "chest pain",
        "cannot breathe",
        "can't breathe",
        "shortness of breath",
        "passed out",
        "unconscious",
        "stroke",
        "seizure",
        "severe bleeding",
        "anaphylaxis",
        "heart attack",
        # Spanish
        "dolor de pecho",
        "no puedo respirar",
        "falta de aire",
        "infarto",
        "ataque cardiaco",
        "ataque al corazon",
        "ataque al corazón",
        "derrame cerebral",
        "embolia",
        "convulsion",
        "convulsión",
        "sangrado severo",
        "anafilaxia",
        "perdi el conocimiento",
        "perdí el conocimiento",
        "me desmaye",
        "me desmayé",
    }
)

MENTAL_HEALTH_EMERGENCY_KEYWORDS = frozenset(
    {
        # English
        "suicidal",
        "suicide",
        "kill myself",
        "want to die",
        "end my life",
        "harm myself",
        # Spanish
        "suicidio",
        "suicidarme",
        "matarme",
        "quitarme la vida",
        "hacerme dano",
        "hacerme daño",
        "quiero morir",
    }
)

ADVERSE_EFFECT_KEYWORDS = frozenset(
    {
        "side effect",
        "allergic",
        "rash",
        "swelling",
        "dizzy",
        "faint",
        "vomit",
        "nausea",
        "reaction",
    }
)


@dataclass(frozen=True)
class SafetyVerdict:
    """A classification the floor decided, with the rule that decided it.

    `safety_rule` is set only here, never by a model, so an escalation can always be
    traced back to the rule that caused it.
    """

    intent: IntentType
    urgency: UrgencyType
    reason: str
    safety_rule: str


def matches_any(text: str, keywords: frozenset[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def contains_adverse_effect_signal(text: str) -> bool:
    return matches_any(text.lower(), ADVERSE_EFFECT_KEYWORDS)


def deterministic_safety_floor(message: str) -> SafetyVerdict | None:
    """Return the forced classification for a message, or None if no rule applies.

    None is the ordinary case and hands the message to the model. A verdict means the
    model must not be consulted at all: not to confirm it, and not to phrase it.
    """
    normalized = message.lower()

    if matches_any(normalized, MENTAL_HEALTH_EMERGENCY_KEYWORDS):
        return SafetyVerdict(
            intent="mental_health",
            urgency="emergency",
            reason="Mental-health emergency keyword match",
            safety_rule="emergency_mental_health_keyword",
        )

    if matches_any(normalized, EMERGENCY_KEYWORDS):
        return SafetyVerdict(
            intent="symptom",
            urgency="emergency",
            reason="Emergency symptom keyword match",
            safety_rule="emergency_symptom_keyword",
        )

    return None
