"""The deterministic safety floor, and the guarantee that a model cannot lower it.

Self-harm and medical emergencies are decided by keyword before the model is asked.
The regression these tests exist to prevent is the one this code was written to fix:
the emergency rules used to live only in the LLM-failure fallback, so a healthy model
that misread "crushing chest pain" as small talk had nothing behind it.
"""

from __future__ import annotations

import pytest

from app.agents.triage.graph import (
    TriageClassificationResult,
    _deterministic_safety_floor,
    classify_intent,
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

SELF_HARM_EN = [
    "I want to die",
    "I have been thinking about suicide",
    "I want to kill myself tonight",
]

SELF_HARM_ES = [
    "quiero quitarme la vida",
    "he pensado en suicidarme",
    "quiero matarme",
]

ORDINARY = [
    "I would like to schedule a follow-up next week",
    "quiero una cita para la próxima semana",
    "what does troponin mean on my discharge summary",
    "hola, buenos días",
    "",
]


@pytest.mark.parametrize("message", EMERGENCY_EN + EMERGENCY_ES)
def test_medical_emergencies_are_decided_without_the_model(message: str):
    result = _deterministic_safety_floor(message)

    assert result is not None
    assert result.urgency == "emergency"
    assert result.intent == "symptom"
    assert result.safety_rule == "emergency_symptom_keyword"


@pytest.mark.parametrize("message", SELF_HARM_EN + SELF_HARM_ES)
def test_self_harm_is_decided_without_the_model(message: str):
    result = _deterministic_safety_floor(message)

    assert result is not None
    assert result.urgency == "emergency"
    assert result.intent == "mental_health"
    assert result.safety_rule == "emergency_mental_health_keyword"


@pytest.mark.parametrize("message", ORDINARY)
def test_ordinary_messages_are_left_to_the_model(message: str):
    """The floor must be narrow. Escalating everything would make it meaningless."""
    assert _deterministic_safety_floor(message) is None


def test_self_harm_outranks_a_co_occurring_medical_emergency():
    """Both sets match here; the mental-health response is the one that must win."""
    result = _deterministic_safety_floor("I have chest pain and I want to kill myself")

    assert result is not None
    assert result.intent == "mental_health"


@pytest.mark.parametrize(
    "message",
    ["TENGO DOLOR DE PECHO", "I Can'T BrEaThe", "CHEST PAIN"],
)
def test_matching_is_case_insensitive(message: str):
    assert _deterministic_safety_floor(message) is not None


@pytest.mark.parametrize(
    "message",
    ["tuvo una convulsion", "me desmaye", "perdi el conocimiento"],
)
def test_unaccented_spanish_still_matches(message: str):
    """A patient in distress will not stop to type accents."""
    assert _deterministic_safety_floor(message) is not None


class _ConfidentlyWrongRouter:
    """A model that answers, and answers wrongly — the case the floor exists for."""

    def __init__(self) -> None:
        self.was_called = False


@pytest.mark.asyncio
async def test_a_confident_model_is_never_consulted_for_an_emergency(monkeypatch):
    """Regression: emergency rules used to run only when the model failed."""
    import app.agents.triage.graph as graph

    called = False

    async def _never(*_args, **_kwargs):
        nonlocal called
        called = True
        return TriageClassificationResult(intent="general", urgency="routine", reason="chit-chat")

    monkeypatch.setattr(graph, "_classify_with_llm", _never)

    state = await classify_intent(
        {"message": "I'm having crushing chest pain", "language": "en-US"},  # type: ignore[arg-type]
        router=None,  # type: ignore[arg-type]
    )

    assert called is False, "the model must not get a say once the floor has fired"
    assert state["urgency"] == "emergency"
    assert state["escalation_required"] is True
    assert state["safety_rule"] == "emergency_symptom_keyword"


@pytest.mark.asyncio
async def test_the_model_still_decides_an_ordinary_message(monkeypatch):
    import app.agents.triage.graph as graph

    async def _classify(*_args, **_kwargs):
        return TriageClassificationResult(
            intent="schedule", urgency="routine", reason="scheduling request"
        )

    monkeypatch.setattr(graph, "_classify_with_llm", _classify)

    state = await classify_intent(
        {"message": "can I move my appointment to Friday", "language": "en-US"},  # type: ignore[arg-type]
        router=None,  # type: ignore[arg-type]
    )

    assert state["intent"] == "schedule"
    assert state["urgency"] == "routine"
    assert state["safety_rule"] is None


@pytest.mark.asyncio
async def test_the_floor_still_applies_when_the_model_is_unavailable(monkeypatch):
    """Losing the model must not lose the floor either."""
    import app.agents.triage.graph as graph

    async def _fails(*_args, **_kwargs):
        return None

    monkeypatch.setattr(graph, "_classify_with_llm", _fails)

    state = await classify_intent(
        {"message": "quiero quitarme la vida", "language": "es-MX"},  # type: ignore[arg-type]
        router=None,  # type: ignore[arg-type]
    )

    assert state["urgency"] == "emergency"
    assert state["intent"] == "mental_health"
