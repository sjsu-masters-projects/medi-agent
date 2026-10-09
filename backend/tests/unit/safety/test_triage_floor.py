"""The deterministic safety rules, tested independently of any agent runtime.

These live outside `tests/unit/agents/` on purpose. The agent framework is being
replaced; these rules are not, and a test that survives the migration untouched is the
point of extracting them.
"""

from __future__ import annotations

import pytest

from app.safety import (
    apply_safety_override,
    contains_adverse_effect_signal,
    deterministic_safety_floor,
    is_escalation,
)

EMERGENCY_EN = [
    "I'm having crushing chest pain right now",
    "I can't breathe",
    "I think my father is having a heart attack",
    "she had a seizure a minute ago",
    "there is severe bleeding and it won't stop",
]

EMERGENCY_ES = [
    "tengo dolor de pecho muy fuerte",
    "no puedo respirar",
    "creo que es un infarto",
    "tuvo una convulsión hace un minuto",
    "me desmayé en la cocina",
]

SELF_HARM_EN = ["I want to die", "I have been thinking about suicide", "I want to kill myself"]
SELF_HARM_ES = ["quiero quitarme la vida", "he pensado en suicidarme", "quiero matarme"]

ORDINARY = [
    "I would like to schedule a follow-up next week",
    "quiero una cita para la próxima semana",
    "what does troponin mean on my discharge summary",
    "hola, buenos días",
    "",
]

NEGATED_EMERGENCY_EN = [
    "I do not have chest pain",
    "I don't have any chest pain",
    "No chest pain, just a dry cough",
    "The cough occurs without shortness of breath",
    "She denies having chest pain",
    "I am not suicidal",
    ("I developed a dry cough. I do not have trouble breathing, facial swelling, or chest pain."),
]

NEGATED_EMERGENCY_ES = [
    "No tengo dolor de pecho",
    "Solo tengo tos, sin falta de aire",
    "Niega dolor de pecho",
    "No quiero morir",
    "Tengo tos, pero no tengo dificultad para respirar, hinchazón ni dolor de pecho",
]


class TestTheFloor:
    @pytest.mark.parametrize("message", EMERGENCY_EN + EMERGENCY_ES)
    def test_medical_emergencies_are_decided_by_rule(self, message: str) -> None:
        verdict = deterministic_safety_floor(message)

        assert verdict is not None
        assert verdict.urgency == "emergency"
        assert verdict.safety_rule == "emergency_symptom_keyword"

    @pytest.mark.parametrize("message", SELF_HARM_EN + SELF_HARM_ES)
    def test_self_harm_routes_to_mental_health_not_generic_symptom(self, message: str) -> None:
        """The 988 crisis copy hangs off the mental_health intent, so this matters."""
        verdict = deterministic_safety_floor(message)

        assert verdict is not None
        assert verdict.intent == "mental_health"
        assert verdict.urgency == "emergency"

    @pytest.mark.parametrize("message", ORDINARY)
    def test_ordinary_messages_are_left_to_the_model(self, message: str) -> None:
        assert deterministic_safety_floor(message) is None

    @pytest.mark.parametrize("message", NEGATED_EMERGENCY_EN + NEGATED_EMERGENCY_ES)
    def test_explicitly_negated_emergency_phrases_are_left_to_the_model(self, message: str) -> None:
        assert deterministic_safety_floor(message) is None

    @pytest.mark.parametrize(
        "message",
        [
            "No nausea, but I have chest pain now",
            "I do not have chest pain, but I can't breathe",
            "I am not sure whether this is chest pain",
            "Not only chest pain but shortness of breath too",
            "No tuve dolor de cabeza, pero tengo dolor de pecho",
            "I do not have nausea, but I have chest pain",
        ],
    )
    def test_a_nearby_negation_never_hides_a_positive_emergency(self, message: str) -> None:
        verdict = deterministic_safety_floor(message)

        assert verdict is not None
        assert verdict.urgency == "emergency"

    def test_self_harm_outranks_a_co_occurring_medical_emergency(self) -> None:
        verdict = deterministic_safety_floor("I have chest pain and I want to kill myself")

        assert verdict is not None
        assert verdict.intent == "mental_health"

    @pytest.mark.parametrize(
        "message",
        ["TENGO DOLOR DE PECHO", "Me Desmaye En La Cocina", "NO PUEDO RESPIRAR"],
    )
    def test_case_and_missing_accents_still_match(self, message: str) -> None:
        """A patient in distress does not type carefully."""
        assert deterministic_safety_floor(message) is not None


class TestEscalationIsMonotonic:
    def test_the_floor_can_force_emergency_over_a_model_verdict(self) -> None:
        """The old override could only reach `urgent`, so this case was unreachable."""
        intent, urgency, _ = apply_safety_override(
            intent="general",
            urgency="routine",
            reason="model said small talk",
            message="I am having crushing chest pain",
        )

        assert urgency == "emergency"
        assert intent == "symptom"

    def test_an_adverse_effect_signal_raises_routine_to_urgent(self) -> None:
        _, urgency, reason = apply_safety_override(
            intent="medication_question",
            urgency="routine",
            reason="medication keyword",
            message="I got a rash after my new medication",
        )

        assert urgency == "urgent"
        assert "side-effect" in reason

    def test_an_emergency_is_never_downgraded(self) -> None:
        _, urgency, _ = apply_safety_override(
            intent="symptom",
            urgency="emergency",
            reason="floor",
            message="I feel a little dizzy",
        )

        assert urgency == "emergency"

    def test_an_ordinary_message_passes_through_unchanged(self) -> None:
        result = apply_safety_override(
            intent="schedule",
            urgency="routine",
            reason="scheduling keyword",
            message="can I move my appointment to Tuesday",
        )

        assert result == ("schedule", "routine", "scheduling keyword")

    @pytest.mark.parametrize(
        ("current", "proposed", "expected"),
        [
            ("routine", "urgent", True),
            ("urgent", "emergency", True),
            ("emergency", "urgent", False),
            ("urgent", "routine", False),
            ("urgent", "urgent", False),
        ],
    )
    def test_escalation_ranking(self, current: str, proposed: str, expected: bool) -> None:
        assert is_escalation(current, proposed) is expected


def test_adverse_effect_detection_is_case_insensitive() -> None:
    assert contains_adverse_effect_signal("I had a REACTION to it")
    assert not contains_adverse_effect_signal("can I book an appointment")


EDUCATIONAL_MESSAGES = [
    (
        "Synthetic QA educational question only; I am not reporting symptoms. Is a "
        "patient-reported barrier automatically a confirmed adverse drug reaction? "
        "Explain briefly in plain English. Do not change my care plan or medications."
    ),
    (
        "Pregunta educativa: ¿una barrera para seguir el plan de cuidado significa "
        "que ya se confirmó una reacción adversa a un medicamento? No tengo síntomas. "
        "Explícalo brevemente en español sencillo; no cambies mi plan ni mis medicamentos."
    ),
    "Is a patient-reported barrier automatically an adverse drug reaction?",
    "¿Una barrera significa una reacción adversa?",
    (
        "Synthetic QA only, not a symptom report: explain in plain English what a "
        "patient-reported barrier means. Is it automatically a confirmed adverse drug "
        "reaction? Do not change my care plan or medication."
    ),
    "What is an adverse drug reaction?",
    "Explain rash and nausea as possible side effects.",
    "Could a medication cause a rash or nausea?",
    "What does allergic reaction mean? Is it always a confirmed side effect?",
    "¿Qué es una reacción adversa a un medicamento?",
    "Explica qué significa un efecto secundario y una erupción.",
    "¿Podría un medicamento causar mareos o náuseas?",
    "¿Que significa una reaccion adversa?",
    (
        "Solo QA sintética, no es un reporte de síntomas: explica qué significa una "
        "barrera reportada por el paciente. ¿Es automáticamente una reacción adversa "
        "confirmada? No cambies mi plan ni mi medicamento."
    ),
    "I do not have a rash or nausea.",
    "No tengo sarpullido ni náuseas.",
    "No nausea, no rash. Explain what a side effect means.",
    "Sin mareos ni náuseas. ¿Qué es una reacción adversa?",
    "What is a fraction?",  # No substring match inside another word.
]

ADVERSE_REPORTS = [
    "Is a patient-reported barrier a reaction? I have a rash now",
    "Is a patient-reported barrier my reaction after this dose?",
    "¿Una barrera significa una reacción? Tengo una erupción ahora",
    "¿Una barrera significa mi reacción al medicamento?",
    "I had a reaction to it",
    "I feel dizzy",
    "Tengo una reacción al medicamento",
    "Me dio sarpullido después del medicamento",
    "Tengo mareos y náuseas",
    "Tengo hinchazon y vomitos",
    "Mi madre tiene una erupción",
    "Synthetic QA only, not a symptom report: I got a rash after my medication",
    "Educational question: I am having nausea after my dose",
    "Solo QA sintética, no es un reporte de síntomas: tengo una reacción",
    "What is a side effect? I have a rash now",
    "I have a rash now. What is a side effect?",
    "Explain nausea, but I feel dizzy now",
    "Explain nausea and I have a rash now",
    "Could a medication cause nausea, and I have a rash now?",
    "What does the rash I developed mean?",
    "Explain my rash",
    "Explain this rash",
    "Explain nausea, she is dizzy",
    "Could a medication cause a rash, the rash is spreading?",
    "Explica mi reacción al medicamento",
    "¿Qué significa esta erupción?",
    "Explica náuseas, empezaron hoy",
    "¿Qué significa una reacción? Tengo una erupción ahora",
    "Explica los efectos secundarios y tengo mareos ahora",
    "¿Podría un medicamento causar náuseas? Pero tengo sarpullido ahora",
    "I do not have nausea, but I have a rash",
    "No rash yesterday; rash today",
    "No reaction yesterday, but a reaction now",
    "No tuve reacción ayer, pero tengo una reacción hoy",
    "I do not have a rash or I feel dizzy",
    "No tengo náuseas, pero tengo mareos",
    "No tengo sarpullido ni siento mareos ahora",
    "Not only a rash but nausea too",
    "I am not sure whether this is a reaction",
    "No estoy seguro si es una reacción",
    "Synthetic QA only: rash",
    "Solo QA: reacción",
]


@pytest.mark.parametrize("message", EDUCATIONAL_MESSAGES)
@pytest.mark.parametrize("intent", ["general", "medication_question", "symptom"])
def test_explicit_education_and_denials_do_not_force_urgent(message: str, intent: str) -> None:
    assert not contains_adverse_effect_signal(message)
    assert apply_safety_override(
        intent=intent, urgency="routine", reason="Educational question", message=message
    ) == (intent, "routine", "Educational question")


@pytest.mark.parametrize("message", ADVERSE_REPORTS)
def test_reports_and_ambiguous_mentions_still_force_urgent(message: str) -> None:
    assert contains_adverse_effect_signal(message)
    assert (
        apply_safety_override(
            intent="general", urgency="routine", reason="Educational question", message=message
        )[1]
        == "urgent"
    )


@pytest.mark.parametrize("message", EDUCATIONAL_MESSAGES)
@pytest.mark.parametrize("urgency", ["urgent", "emergency"])
def test_education_never_lowers_model_urgency(message: str, urgency: str) -> None:
    assert apply_safety_override(
        intent="general", urgency=urgency, reason="Model concern", message=message
    ) == ("general", urgency, "Model concern")


@pytest.mark.parametrize("signal", EMERGENCY_EN + EMERGENCY_ES + SELF_HARM_EN + SELF_HARM_ES)
def test_education_and_qa_disclaimers_never_hide_emergencies(signal: str) -> None:
    message = f"Synthetic QA only: explain adverse reactions. {signal}"
    assert (
        apply_safety_override(
            intent="general", urgency="routine", reason="Educational question", message=message
        )[1]
        == "emergency"
    )
