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
