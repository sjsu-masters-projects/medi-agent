"""Golden routing cases for deterministic triage intent and urgency mapping."""

from uuid import uuid4

import pytest

from app.agents.triage.agent import TriageAgent, TriageInput
from app.models.enums import Language


class _FailingRouter:
    def get_client(self, _task_type):
        raise RuntimeError("LLM unavailable")


GOLDEN_CASES = [
    ("I have chest pain and cannot breathe", "symptom", "emergency", "symptom"),
    ("My father passed out and is unconscious", "symptom", "emergency", "symptom"),
    ("I think I am having a stroke", "symptom", "emergency", "symptom"),
    ("I have severe bleeding", "symptom", "emergency", "symptom"),
    ("I want to kill myself", "symptom", "emergency", "symptom"),
    ("Can we book an appointment next week", "schedule", "routine", "triage"),
    ("Need to reschedule my visit", "schedule", "routine", "triage"),
    ("Can you explain this lab report", "document_question", "routine", "triage"),
    ("Explica mis resultados de laboratorio", "document_question", "routine", "triage"),
    ("Question about my medication timing", "medication_question", "routine", "triage"),
    ("I have a side effect from medicine", "medication_question", "urgent", "triage"),
    ("After this pill I got rash and swelling", "medication_question", "urgent", "triage"),
    ("I feel anxious and overwhelmed", "mental_health", "urgent", "triage"),
    ("Panic attacks are getting worse", "mental_health", "urgent", "triage"),
    ("I have dizziness and nausea", "symptom", "urgent", "symptom"),
    ("High fever since last night", "symptom", "urgent", "symptom"),
    ("Persistent headache and cough", "symptom", "urgent", "symptom"),
    ("Tengo mareos y vomito", "symptom", "urgent", "symptom"),
    ("Mi medicina me causa nausea", "medication_question", "urgent", "triage"),
    ("Necesito reagendar mi appointment", "schedule", "routine", "triage"),
    ("Just checking in with no major issues", "general", "routine", "triage"),
    ("Hello there", "general", "routine", "triage"),
    ("I need refill for my medication", "medication_question", "routine", "triage"),
    ("Swelling and faint feeling after dose", "medication_question", "urgent", "triage"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message, expected_intent, expected_urgency, expected_route",
    GOLDEN_CASES,
)
async def test_triage_golden_routing_cases(
    message: str,
    expected_intent: str,
    expected_urgency: str,
    expected_route: str,
):
    agent = TriageAgent(router=_FailingRouter())

    output = await agent.process(
        TriageInput(
            user_id=uuid4(),
            patient_id=uuid4(),
            message=message,
            language=Language.EN,
            history=[],
        )
    )

    assert output.status == "success"
    assert output.intent == expected_intent
    assert output.urgency == expected_urgency
    assert output.route == expected_route


@pytest.mark.asyncio
async def test_triage_routes_generic_question_to_attached_document_context():
    agent = TriageAgent(router=_FailingRouter())

    output = await agent.process(
        TriageInput(
            user_id=uuid4(),
            patient_id=uuid4(),
            message="Can you explain what this means?",
            language=Language.EN,
            history=[],
            document_context={
                "id": str(uuid4()),
                "file_name": "lab.pdf",
                "summary": "A1C is elevated.",
            },
        )
    )

    assert output.status == "success"
    assert output.intent == "document_question"
    assert output.urgency == "routine"
    assert output.route == "triage"
