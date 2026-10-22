"""Decide, deterministically, whether a chat turn may offer a private symptom note.

The offer is only a question ("Would you like me to note this for your care team?").
It never starts a draft, and it never replaces emergency direction: any message the
reviewed safety floor classifies (emergency, self-harm, medication error) is excluded
before anything else is considered. A medication-list, appointment or greeting question
is never offered, even when the language model labelled the turn a symptom.

No match is not clinical clearance; it only means Nora does not ask to open a note.
"""

from __future__ import annotations

import re

from app.safety.triage_floor import deterministic_safety_floor, is_negated_signal

_SYMPTOM_TERMS = re.compile(
    r"\b(?:"
    r"headaches?|migraines?|head (?:hurts|is pounding)|dizz(?:y|iness)|light-?headed|"
    r"nause(?:a|ous)|vomit(?:ing)?|threw up|rash|hives|itch(?:y|ing)|cough(?:ing)?|"
    r"fever|chills|fatigue|exhausted|tired|diarrhea|constipat(?:ed|ion)|cramps?|"
    r"heartburn|bloat(?:ed|ing)|swollen|swelling|numb(?:ness)?|tingling|"
    r"blurr?y vision|trouble sleeping|can'?t sleep|insomnia|shak(?:y|ing)|tremors?|"
    r"weak(?:ness)?|sweating|pain|aches?|achy|sore|hurts?|side effects?|"
    r"dolor(?:es)? de (?:cabeza|est[oó]mago|garganta|espalda)|dolor|"
    r"mareo|maread[oa]|n[aá]useas?|v[oó]mitos?|vomit(?:ando|[eé])|sarpullido|"
    r"erupci[oó]n|comez[oó]n|picaz[oó]n|tos|fiebre|escalofr[ií]os|cansancio|"
    r"cansad[oa]|fatiga|diarrea|estre[nñ]imiento|calambres?|acidez|hinchaz[oó]n|"
    r"hinchad[oa]|entumec(?:imiento|ido)|hormigueo|visi[oó]n borrosa|insomnio|"
    r"temblor(?:es)?|d[eé]bil|debilidad|sudoraci[oó]n|efectos? secundarios?|"
    r"me duele|me duelen|malestar|feel(?:ing)? (?:sick|unwell|off|bad|terrible)|"
    r"not feeling (?:well|right|good)|me siento (?:mal|enferm[oa])|no me siento bien"
    r")\b"
)
# The patient is reporting their own experience, in either supported language.
_REPORT_CUES = re.compile(
    r"\b(?:i|i['’]?ve|i['’]?m|ive|im|my|me|since i|after i|"
    r"tengo|tuve|siento|me siento|me duele|me duelen|estoy|he tenido|me dio|me da|"
    r"me sali[oó]|mi|mis|desde que|despu[eé]s de)\b"
)
_QUESTION_START = re.compile(
    r"^\s*[¿\"']?(?:what|when|where|which|who|how|why|can you|could you|do i|does|is|are|"
    r"show|list|tell me|remind me|qu[eé]|cu[aá]ndo|d[oó]nde|cu[aá]l(?:es)?|qui[eé]n|"
    r"c[oó]mo|por qu[eé]|puedes|puede|mu[eé]strame|dime)\b"
)


def _denied(clause: str, index: int) -> bool:
    """Whether the term is denied ("I don't have a headache"), articles included."""
    head = re.sub(r"\b(?:a|an|any|un|una)\s+$", "", clause[:index])
    return is_negated_signal(head + clause[index:], len(head))


def _clauses(text: str) -> list[str]:
    return [clause for clause in re.split(r"[.!?;¿\n]+", text) if clause.strip()]


def reports_symptom(message: str) -> bool:
    """A first-person, un-negated symptom or possible side effect in the message."""
    text = message.lower()
    for clause in _clauses(text):
        # A question is only a report when it also speaks about the patient's own body.
        if _REPORT_CUES.search(clause) is None:
            continue
        for match in _SYMPTOM_TERMS.finditer(clause):
            if _denied(clause, match.start()):
                continue
            if _QUESTION_START.search(clause) and not re.search(
                r"\b(?:i|i['’]?ve|i['’]?m|ive|im|tengo|tuve|siento|me siento|he tenido|me duele|me duelen)\b",
                clause,
            ):
                continue
            return True
    return False


def mentions_symptom(message: str) -> bool:
    """Any un-negated symptom wording, whoever it is about."""
    text = message.lower()
    return any(
        not _denied(clause, match.start())
        for clause in _clauses(text)
        for match in _SYMPTOM_TERMS.finditer(clause)
    )


def is_information_question(message: str) -> bool:
    """A request for facts (medications, appointments, results), not a report."""
    text = message.strip().lower()
    return (text.endswith("?") or _QUESTION_START.search(text) is not None) and not reports_symptom(
        text
    )


def symptom_offer_eligible(
    message: str, *, route: str = "triage", urgency: str = "routine"
) -> bool:
    """True only for a reportable, non-emergency symptom or possible side effect.

    The deterministic report detector decides first. The model's `symptom` route can
    add an offer only when the message names a symptom and is not an information question, and an
    emergency (or any reviewed safety-floor match) can never receive one.
    """
    if urgency == "emergency" or deterministic_safety_floor(message) is not None:
        return False
    if reports_symptom(message):
        return True
    return route == "symptom" and mentions_symptom(message) and not is_information_question(message)
