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

import re
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
        "efecto secundario",
        "efectos secundarios",
        "reacción",
        "reaccion",
        "sarpullido",
        "erupción",
        "erupcion",
        "hinchazón",
        "hinchazon",
        "mareo",
        "náusea",
        "vómit",
        "alérgic",
        "alergic",
    }
)

# Only explicit, local denials suppress an emergency phrase. The expression must end
# immediately before the matched phrase (apart from a small set of harmless fillers), so
# text such as "no nausea, but chest pain" or "not sure whether this is chest pain" still
# escalates. This is intentionally narrower than general language negation: a false
# negative here is more dangerous than an unnecessary escalation.
_NEGATED_SIGNAL_PREFIX = re.compile(
    r"(?:\b(?:"
    r"do not have|don't have|does not have|doesn't have|did not have|didn't have|"
    r"not having|denies having|deny having|denied having|denies|deny|denied|"
    r"no tengo|no tiene|no presento|no presenta|niego tener|niega tener|niego|niega|"
    r"without|sin|no|not"
    r")\s+(?:any\s+|currently\s+|ningun\s+|ninguna\s+|ningún\s+|ninguna\s+)?$)"
)
_NEGATED_LIST_START = re.compile(
    r"\b(?:"
    r"do not have|don't have|does not have|doesn't have|did not have|didn't have|"
    r"denies having|deny having|denied having|denies|deny|denied|"
    r"no tengo|no tiene|no presento|no presenta|niego tener|niega tener|niego|niega|"
    r"without|sin|no"
    r")\b"
)
_NEGATED_LIST_CONTINUATION = re.compile(r"(?:,\s*)?(?:or|nor|ni)\s*$")
_CLAUSE_BREAK = re.compile(r"[.!?;]|\b(?:but|however|although|though|yet|except|pero|aunque)\b")

# Educational wording is local to a clause, never a turn-wide opt-out. Report verbs
# keep ambiguous mixed questions conservative, even when introduced as education/QA.
_ADVERSE_CLAUSE_BREAK = re.compile(
    r"[.!?;:\n]|\b(?:but|however|although|though|yet|except|pero|aunque)\b"
)
_EDUCATIONAL_PREFIX = re.compile(
    r"^\s*[¿\"']?(?:please\s+)?(?:"
    r"what (?:is|are|does|do)\b|(?:can you )?explain\b|define\b|"
    r"is (?:it|that|this) (?:automatically|always)\b|"
    r"(?:can|could) (?:a |an |the )?(?:medicine|medication|drug)\b|"
    r"(?:por favor\s+)?(?:explica|explícame|explicame|explique|define)\b|"
    r"qu[eé] (?:es|son|significa|significan)\b|"
    r"(?:es|eso es) (?:autom[aá]ticamente|siempre)\b|"
    r"(?:puede|podr[ií]a) (?:un |el )?(?:medicamento|f[aá]rmaco)\b"
    r")"
)
_ADVERSE_REPORT_LANGUAGE = re.compile(
    r"\b(?:have|has|had|got|getting|developed|developing|experiencing|feel|feeling|"
    r"noticed|suffer|suffering|having|tengo|tiene|tenemos|tuve|tuvo|siento|sent[ií]|"
    r"presento|presenta|not[eé]|apareci[oó]|dio|estoy|est[aá]|"
    r"my|our|mi|mis|me|she|he|they|now|today|ahora|hoy|started|began|"
    r"worsening|spreading|empez[oó]|empeorando)\b|"
    r"\b(?:this|that|esta|este)\s+(?:rash|reaction|nausea|reacci[oó]n|erupci[oó]n)\b"
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


def matches_any_unnegated(text: str, keywords: frozenset[str]) -> bool:
    """Whether any keyword occurs without a clear denial immediately before it.

    Every occurrence is checked. A historical denial followed by a current positive
    report ("no chest pain yesterday, but chest pain now") must still escalate.
    """
    for keyword in keywords:
        offset = 0
        while (index := text.find(keyword, offset)) >= 0:
            if not _is_negated_signal(text, index):
                return True
            offset = index + len(keyword)
    return False


def _is_negated_signal(text: str, index: int) -> bool:
    prefix = text[:index]
    if _NEGATED_SIGNAL_PREFIX.search(prefix) is not None:
        return True

    # A denial commonly governs a short list: "I do not have trouble breathing,
    # swelling, or chest pain." Extend the denial only when the target is introduced by
    # an explicit list conjunction and no sentence or contrast boundary intervenes. This
    # does not suppress "no nausea, but chest pain" or a comma-spliced positive report.
    if _NEGATED_LIST_CONTINUATION.search(prefix) is None:
        return False
    starts = list(_NEGATED_LIST_START.finditer(prefix))
    if not starts:
        return False
    tail = prefix[starts[-1].end() :]
    return _CLAUSE_BREAK.search(tail) is None


def contains_adverse_effect_signal(text: str) -> bool:
    """Detect reported or ambiguous adverse signals, not explicit term education.

    Check every mention independently. Neither general intent nor a disclaimer grants
    an exemption, and this filtering never applies to emergency/self-harm rules.
    """
    for clause in _ADVERSE_CLAUSE_BREAK.split(text.lower()):
        educational = (
            _EDUCATIONAL_PREFIX.search(clause) is not None
            and _ADVERSE_REPORT_LANGUAGE.search(clause) is None
        )
        for keyword in ADVERSE_EFFECT_KEYWORDS:
            for match in re.finditer(r"\b" + re.escape(keyword), clause):
                if not educational and not _is_negated_adverse_signal(clause, match.start()):
                    return True
    return False


def _is_negated_adverse_signal(clause: str, index: int) -> bool:
    prefix = clause[:index]
    without_article = re.sub(r"\b(?:a|an|un|una)\s+$", "", prefix)
    if _NEGATED_SIGNAL_PREFIX.search(without_article) is not None:
        return True
    if not _is_negated_signal(clause, index):
        return False
    starts = list(_NEGATED_LIST_START.finditer(prefix))
    # A fresh report inside a denial's list ends its scope ("no rash or I feel dizzy").
    return bool(starts) and _ADVERSE_REPORT_LANGUAGE.search(prefix[starts[-1].end() :]) is None


def deterministic_safety_floor(message: str) -> SafetyVerdict | None:
    """Return the forced classification for a message, or None if no rule applies.

    None is the ordinary case and hands the message to the model. A verdict means the
    model must not be consulted at all: not to confirm it, and not to phrase it.
    """
    normalized = message.lower()

    if matches_any_unnegated(normalized, MENTAL_HEALTH_EMERGENCY_KEYWORDS):
        return SafetyVerdict(
            intent="mental_health",
            urgency="emergency",
            reason="Mental-health emergency keyword match",
            safety_rule="emergency_mental_health_keyword",
        )

    if matches_any_unnegated(normalized, EMERGENCY_KEYWORDS):
        return SafetyVerdict(
            intent="symptom",
            urgency="emergency",
            reason="Emergency symptom keyword match",
            safety_rule="emergency_symptom_keyword",
        )

    return None
