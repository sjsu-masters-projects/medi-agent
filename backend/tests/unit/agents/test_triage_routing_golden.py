"""What triage decides when no model is available.

Every case here runs against a router that raises, so nothing reaches a model.

That used to exercise a keyword cascade which guessed an intent from substrings — "medicine"
meant a medication question, "pain" meant a symptom, seven drug names stood in for the whole
pharmacopoeia — and then answered the patient in that intent's voice. The cascade is gone.
Guessing a clinical topic and then speaking confidently about it is worse than admitting the
outage, because nothing in the reply tells the patient which one they received.

What survives an outage is the deterministic safety floor, and nothing else. These tests pin
both halves: the floor still routes an emergency without consulting a model, and every other
message is told plainly that the service is unavailable.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.triage.agent import TriageAgent, TriageInput
from app.models.enums import Language
from app.safety import TRIAGE_COPY
from app.utils.localization import resolve_locale_resource


class _FailingRouter:
    """A total model outage: classification and response generation both raise."""

    def get_client(self, _task_type):
        raise RuntimeError("LLM unavailable")

    async def generate_text(self, _task_type, **_kwargs):
        raise RuntimeError("LLM unavailable")


# Decided by the floor, with no model in the path, in both locales. An outage must not
# touch these: they are the messages that can least afford to wait for a retry.
FLOOR_CASES = [
    ("I have chest pain and cannot breathe", Language.EN, "symptom", "symptom"),
    ("My father passed out and is unconscious", Language.EN, "symptom", "symptom"),
    ("I think I am having a stroke", Language.EN, "symptom", "symptom"),
    ("I have severe bleeding", Language.EN, "symptom", "symptom"),
    # Self-harm routes to mental_health because the 988 crisis copy hangs off that intent.
    ("I want to kill myself", Language.EN, "mental_health", "triage"),
    ("I am suicidal and need help", Language.EN, "mental_health", "triage"),
    ("Tengo dolor de pecho fuerte", Language.ES, "symptom", "symptom"),
    ("No puedo respirar bien", Language.ES, "symptom", "symptom"),
    ("Creo que es un infarto", Language.ES, "symptom", "symptom"),
    ("Quiero quitarme la vida", Language.ES, "mental_health", "triage"),
]

# Messages the cascade used to classify by substring. Each carries the intent it was given
# and the copy key that intent would have answered with — the exact text that must not
# appear now, since it would assert something clinical about a message nobody read.
FORMERLY_GUESSED = [
    ("Question about my medication timing", Language.EN, "fallback_medication_question"),
    ("I need refill for my medication", Language.EN, "fallback_medication_question"),
    ("Can you explain what aspirin does", Language.EN, "fallback_medication_question"),
    ("I have a side effect from medicine", Language.EN, "fallback_medication_question"),
    ("After this pill I got rash and swelling", Language.EN, "fallback_medication_question"),
    ("Swelling and faint feeling after dose", Language.EN, "fallback_medication_question"),
    ("Mi medicina me causa nausea", Language.ES, "fallback_medication_question"),
    ("Can we book an appointment next week", Language.EN, "fallback_schedule"),
    ("Need to reschedule my visit", Language.EN, "fallback_schedule"),
    ("Necesito reagendar mi appointment", Language.ES, "fallback_schedule"),
    ("Can you explain this lab report", Language.EN, "fallback_document_question"),
    ("Explica mis resultados de laboratorio", Language.ES, "fallback_document_question"),
    ("I feel anxious and overwhelmed", Language.EN, "fallback_mental_health"),
    ("Panic attacks are getting worse", Language.EN, "fallback_mental_health"),
    ("Me siento ansioso y deprimido", Language.ES, "fallback_mental_health"),
    ("I have dizziness and nausea", Language.EN, "fallback_urgent"),
    ("High fever since last night", Language.EN, "fallback_urgent"),
    ("Persistent headache and cough", Language.EN, "fallback_urgent"),
    ("Tengo mareos y vomito", Language.ES, "fallback_urgent"),
    # These two the cascade called `general`, which is the same intent an outage reports.
    # They are here so the assertion is on the *copy*, not on a label that would match
    # either way.
    ("Just checking in with no major issues", Language.EN, "fallback_general"),
    ("Hello there", Language.EN, "fallback_general"),
]


async def _run(message: str, language: Language, **kwargs) -> object:
    agent = TriageAgent(router=_FailingRouter())
    return await agent.process(
        TriageInput(
            user_id=uuid4(),
            patient_id=uuid4(),
            message=message,
            language=language,
            history=[],
            **kwargs,
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message, language, expected_intent, expected_route",
    FLOOR_CASES,
)
async def test_the_floor_still_decides_an_emergency_without_a_model(
    message: str,
    language: Language,
    expected_intent: str,
    expected_route: str,
) -> None:
    output = await _run(message, language)

    assert output.status == "success"
    assert output.intent == expected_intent
    assert output.urgency == "emergency"
    assert output.route == expected_route
    assert output.escalation_required is True
    assert "911" in output.response_text


@pytest.mark.asyncio
@pytest.mark.parametrize("message, language, formerly_answered_with", FORMERLY_GUESSED)
async def test_an_unclassifiable_message_is_told_about_the_outage(
    message: str,
    language: Language,
    formerly_answered_with: str,
) -> None:
    """The patient hears that we could not answer — not a guess dressed as an answer."""
    localized = resolve_locale_resource(language.value, TRIAGE_COPY)

    output = await _run(message, language)

    assert output.status == "success"
    assert output.response_text == localized["service_unavailable"]
    assert localized[formerly_answered_with] not in output.response_text


@pytest.mark.asyncio
@pytest.mark.parametrize("message, language, _formerly", FORMERLY_GUESSED)
async def test_an_outage_claims_no_intent_and_forces_no_escalation(
    message: str, language: Language, _formerly: str
) -> None:
    """`general`/`routine` here means "we did not classify", not a finding about the message.

    Escalation must stay false for the same reason: raising urgency on a message we never
    understood would put a patient in a queue on the strength of a substring.
    """
    output = await _run(message, language)

    assert output.intent == "general"
    assert output.urgency == "routine"
    assert output.route == "triage"
    assert output.escalation_required is False


@pytest.mark.asyncio
async def test_an_attached_document_does_not_invent_a_document_question() -> None:
    """Having a file open is not evidence of what was asked about it."""
    localized = resolve_locale_resource(Language.EN.value, TRIAGE_COPY)

    output = await _run(
        "Can you explain what this means?",
        Language.EN,
        document_context={
            "id": str(uuid4()),
            "file_name": "lab.pdf",
            "summary": "A1C is elevated.",
        },
    )

    assert output.intent == "general"
    assert output.response_text == localized["service_unavailable"]
    assert localized["fallback_document_question"] not in output.response_text


@pytest.mark.asyncio
async def test_the_outage_message_still_points_at_emergency_care() -> None:
    """An outage reaches people who are unwell but whose wording did not trip the floor."""
    output = await _run("Question about my medication timing", Language.EN)

    assert "911" in output.response_text
