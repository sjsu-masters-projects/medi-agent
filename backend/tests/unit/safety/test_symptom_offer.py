import pytest

from app.safety.symptom_offer import symptom_offer_eligible


@pytest.mark.parametrize(
    "message",
    [
        "What medications am I taking?",
        "what medications am I having?",
        "When is my appointment?",
        "Hello",
        "hola, buenos días",
        "¿Qué medicamentos estoy tomando?",
        "¿Cuándo es mi próxima cita?",
        "I do not have a headache today",
        "What is a headache?",
        "When is my pain clinic appointment?",
    ],
)
def test_information_and_greetings_never_offer(message):
    assert symptom_offer_eligible(message) is False
    # A mislabelled model route cannot turn an information question into an offer.
    assert symptom_offer_eligible(message, route="symptom") is False


@pytest.mark.parametrize(
    "message",
    [
        "I've had a headache since I started metformin",
        "me siento mareado desde ayer",
        "My stomach hurts after dinner",
        "Tengo sarpullido desde que empecé la pastilla nueva",
        "I think this could be a side effect, I feel nauseous",
        "I have a headache since metformin, is that normal?",
    ],
)
def test_reportable_symptoms_and_side_effects_offer(message):
    assert symptom_offer_eligible(message) is True


def test_model_symptom_route_offers_only_for_a_non_question_message():
    assert symptom_offer_eligible("Not feeling right today", route="symptom") is True
    assert symptom_offer_eligible("Not feeling right today") is False


@pytest.mark.parametrize(
    "message",
    [
        "I have chest pain and trouble breathing",
        "Tengo dolor en el pecho y no puedo respirar",
        "I want to kill myself",
        "Quiero morir",
    ],
)
def test_emergencies_keep_reviewed_escalation_and_never_offer(message):
    assert symptom_offer_eligible(message, route="symptom") is False
    assert symptom_offer_eligible(message) is False


def test_an_emergency_model_urgency_never_offers():
    assert symptom_offer_eligible("I feel dizzy", urgency="emergency") is False
