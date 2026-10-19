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

_MENTAL_HEALTH_CRISIS_PATTERNS = (
    re.compile(r"\bi can(?:not|['’]?t) go on\b(?:\s+(?:anymore|like this))?(?=\s*(?:[.!?]|$))"),
    re.compile(r"\b(?:ya\s+)?no puedo m[aá]s\b(?:\s+con esto)?(?=\s*(?:[.!?]|$))"),
)

# These patterns describe a medication error or an unsafe requested dose change. They
# intentionally require concrete dose/taking language: general education such as "what
# is an overdose?" must not be turned into a report about the patient.
_BASE_MEDICATION_ERROR_PATTERNS = (
    re.compile(
        r"\b(?:i\s+)?(?:accidentally|mistakenly)\s+(?:took|take|taken)\b.{0,80}\b(?:twice|again|two doses?)\b"
    ),
    re.compile(
        r"\b(?:i\s+)?(?:took|take|taken)\b.{0,80}\b(?:twice|again|two doses?)\b.{0,40}\b(?:accidentally|by mistake|in error)\b"
    ),
    re.compile(
        r"\b(?:i\s+)?(?:took|take|taken|had)\b.{0,50}\b(?:an?\s+)?(?:extra|double)\s+dose\b"
    ),
    re.compile(
        r"\b(?:double|doubling)\s+(?:my\s+|the\s+)?(?:prescribed\s+)?(?:dose|insulin|medication|medicine)\b"
    ),
    re.compile(r"\b(?:i|we|he|she|they)\b.{0,40}\b(?:overdosed|had an overdose)\b"),
    re.compile(r"\b(?:i\s+)?(?:took|take|taken)\b.{0,40}\b(?:an?\s+)?overdose\b"),
    re.compile(
        r"\b(?:accidentalmente|por error|sin querer)\s+(?:me\s+)?(?:tom[eé]|tome|tomar)\b.{0,80}\b(?:dos veces|otra vez|dos dosis)\b"
    ),
    re.compile(
        r"\b(?:me\s+)?(?:tom[eé]|tome)\b.{0,80}\b(?:dos veces|otra vez|dos dosis)\b.{0,40}\b(?:por error|sin querer|accidentalmente)\b"
    ),
    re.compile(
        r"\b(?:me\s+)?(?:tom[eé]|tome|tomar)\b.{0,50}\b(?:una\s+)?dosis\s+(?:extra|doble)\b"
    ),
    re.compile(r"\b(?:duplicar|dupliqu[eé])\s+(?:mi\s+|la\s+)?(?:dosis|insulina|medicamento)\b"),
    re.compile(
        r"\b(?:yo\s+)?(?:tuve|tuvo|tuvimos|sufr[ií]|tom[eé]|tome)\b.{0,50}"
        r"\b(?:una\s+)?(?:sobredosis|sobredosificaci[oó]n)\b"
    ),
)

# More ways a patient reports too much medicine or a self-directed dose change. "Twice"
# alone is not an error ("twice a day" is a normal schedule), so it is excluded when a
# schedule word follows.
_SCHEDULE_AFTER = r"(?!\s+(?:a|per|each|every)\s+(?:day|week|night)|\s+daily|\s+al\s+d[ií]a|\s+por\s+d[ií]a|\s+diari)"
_MEDICATION_ERROR_PATTERNS = _BASE_MEDICATION_ERROR_PATTERNS + (
    re.compile(
        r"\b(?:took|taken|take|swallowed|injected|had)\b.{0,60}\b(?:too many|too much|"
        r"extra (?:pills?|tablets?|capsules?|doses?|units?)|two (?:pills|tablets|capsules|doses)|"
        r"more than (?:prescribed|i should|directed|my dose|the dose|i was told)|"
        r"twice" + _SCHEDULE_AFTER + r")"
    ),
    re.compile(
        r"\b(?:forgot|already)\b.{0,60}\b(?:took|taken)\b|"
        r"\b(?:took|taken)\b.{0,60}\bagain\b.{0,40}\b(?:forgot|already|by mistake|accidentally)\b"
    ),
    re.compile(
        r"\b(?:doubled|increased|raised|reduced|lowered|halved|changed|adjusted)\s+"
        r"(?:my|the)\s+(?:\w+\s+)?(?:dose|dosage)\b"
    ),
    re.compile(
        r"\b(?:stopped|quit|stop)\s+taking\b.{0,60}\b(?:on my own|by myself|"
        r"without (?:asking|telling|talking|checking))"
    ),
    re.compile(
        r"\b(?:tom[eé]|tome|tomado|inyect[eé])\b.{0,60}\b(?:de m[aá]s|demasiad[oa]s?|el doble|"
        r"(?:pastillas?|tabletas?|c[aá]psulas?|dosis) extra|dos (?:pastillas|tabletas|c[aá]psulas)|"
        r"m[aá]s de lo (?:indicado|recetado|prescrito)|dos veces" + _SCHEDULE_AFTER + r")"
    ),
    re.compile(
        r"\b(?:ya (?:me )?(?:lo )?(?:tom[eé]|tome)|olvid[eé]\b.{0,40}\bya\b.{0,20}\btom[eé])\b"
    ),
    re.compile(
        r"\b(?:aument[eé]|sub[ií]|redu[jc]e?|baj[eé]|cambi[eé]|ajust[eé]|dupliqu[eé])\s+"
        r"(?:mi|la)\s+(?:\w+\s+)?dosis\b"
    ),
    re.compile(
        r"\bdej[eé] de tomar\b.{0,60}\b(?:por mi cuenta|sin (?:consultar|avisar|preguntar|decirle))"
    ),
)

_HELD_OR_STOPPED_MEDICATION_PATTERNS = (
    re.compile(
        r"\b(?:care team|doctor|clinician|pharmacist|document|paper)\b.{0,100}"
        r"\b(?:told|said|says|instructed)?\b.{0,40}\b(?:hold|stop|stopped|not take|discontinue)\b"
        r".{0,120}\b(?:i\s+)?(?:took|take|taken|continued taking)\b"
    ),
    re.compile(
        r"\b(?:i\s+)?(?:took|take|taken|continued taking|still taking|kept taking)\b.{0,120}"
        r"\b(?:even though|although|after|despite)\b.{0,80}"
        r"\b(?:told|said|instructed|hold|stop|stopped|not take|discontinue)\b"
    ),
    re.compile(
        r"\b(?:equipo de atenci[oó]n|m[eé]dico|farmac[eé]utico|documento|informe)\b.{0,120}"
        r"\b(?:indic[oó]|dijo|dice)?\b.{0,40}\b(?:pausar|suspender|dejar de tomar|no tomar|detener)\b"
        r".{0,120}\b(?:me\s+)?(?:tom[eé]|tome|tomado|segu[ií] tomando)\b"
    ),
    re.compile(
        r"\b(?:me\s+)?(?:tom[eé]|tome|tomado|segu[ií] tomando)\b.{0,120}"
        r"\b(?:aunque|a pesar de|despu[eé]s de)\b.{0,80}"
        r"\b(?:indic[oó]|dijo|pausar|suspender|dejar de tomar|no tomar|detener)\b"
    ),
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
    r"is (?:a|an) (?:patient[ -]reported )?barrier\b|"
    r"(?:can|could) (?:a |an |the )?(?:medicine|medication|drug)\b|"
    r"(?:por favor\s+)?(?:explica|explícame|explicame|explique|define)\b|"
    r"qu[eé] (?:es|son|significa|significan)\b|"
    r"(?:es|eso es) (?:autom[aá]ticamente|siempre)\b|"
    r"(?:una|la) barrera (?:para seguir el plan de cuidado )?(?:significa|es)\b|"
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


_NOT_REALIZED = re.compile(
    r"\b(?:didn['’]?t|did not|no)\s+(?:realize|realise|know|notice|remember|sab[ií]a|me di cuenta|record[eé])\b"
)
_NEGATED_ACTION = re.compile(
    r"(?:\bnot|n['’]t|\bnever|\bno|\bnunca|\bjam[aá]s|\bni)\s+(?:\w+\s+){0,2}"
    r"(?:took|taken|take|had|swallowed|injected|doubl\w*|increas\w*|rais\w*|reduc\w*|"
    r"chang\w*|overdos\w*|tom[eé]|tome|tomado|tomar|inyect\w*|dupl\w*|aument\w*|"
    r"cambi\w*|sobredosis|dej[eé]|stopped|quit)"
)
_NEGATED_HELD_TAKING = re.compile(
    r"(?:n['’]t|\bnever|\bnunca|\bdid not|\bno)\s+(?:\w+\s+){0,2}"
    r"(?:took|taken|continued|still|kept|tom[eé]|tome|tomado|segu[ií])"
)
_DEFINITION_QUESTION = re.compile(
    r"^\s*(?:what|why|how)\s+(?:is|does|are|do)\b|^\s*(?:¿)?(?:qu[eé]|por qu[eé]|c[oó]mo)\s+(?:es|significa|son)\b"
)


def _first_person_reports(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    """Whether a sentence carries an affirmed (not denied, not definitional) match."""
    for sentence in re.split(r"[.!?;¿\n]+", _NOT_REALIZED.sub("", text)):
        if _DEFINITION_QUESTION.search(sentence):
            continue
        for pattern in patterns:
            for match in pattern.finditer(sentence):
                context = sentence[max(0, match.start() - 30) : match.end()]
                if _NEGATED_ACTION.search(context) is None:
                    return True
    return False


def contains_medication_error_signal(text: str) -> bool:
    """Detect a concrete unsafe dose or a medication taken after hold/stop advice.

    Denials ("I didn't take it twice") and definitions ("what is an overdose?") never
    trip it; everything affirmed or asked as a plan ("can I double my dose?") does.
    """
    normalized = _NOT_REALIZED.sub("", text.lower())
    if _first_person_reports(normalized, _MEDICATION_ERROR_PATTERNS):
        return True
    return any(
        (match := pattern.search(normalized)) is not None
        and _NEGATED_HELD_TAKING.search(match.group(0)) is None
        for pattern in _HELD_OR_STOPPED_MEDICATION_PATTERNS
    )


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

    mental_health_crisis = matches_any_unnegated(
        normalized, MENTAL_HEALTH_EMERGENCY_KEYWORDS
    ) or any(pattern.search(normalized) for pattern in _MENTAL_HEALTH_CRISIS_PATTERNS)
    if mental_health_crisis:
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

    if contains_medication_error_signal(normalized):
        return SafetyVerdict(
            intent="medication_question",
            urgency="urgent",
            reason="Medication dose or hold/stop error requires same-day review",
            safety_rule="urgent_medication_error",
        )

    return None
