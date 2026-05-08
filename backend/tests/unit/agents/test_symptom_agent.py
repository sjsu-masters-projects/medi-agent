"""Unit tests for SymptomAgent fallback behavior."""

from uuid import uuid4

import pytest

from app.agents.symptom.agent import SymptomAgent, SymptomInput
from app.models.enums import Language


class _FailingRouter:
    def get_client(self, _task_type):
        raise RuntimeError("LLM unavailable")


@pytest.mark.asyncio
async def test_symptom_agent_fallback_extracts_symptom_and_flags_adr_signal():
    agent = SymptomAgent(router=_FailingRouter())

    output = await agent.process(
        SymptomInput(
            user_id=uuid4(),
            patient_id=uuid4(),
            language=Language.EN,
            message="I feel dizzy after taking my new medication",
            patient_context={
                "medications": [{"name": "Metformin"}],
                "conditions": [],
                "recent_symptoms": [],
            },
        )
    )

    assert output.status == "success"
    assert output.symptom_report is not None
    assert output.symptom_report["symptom"] == "dizziness"
    assert output.flagged_for_adr is True
    assert output.response_text is not None


@pytest.mark.asyncio
async def test_symptom_agent_fallback_supports_spanish_response():
    agent = SymptomAgent(router=_FailingRouter())

    output = await agent.process(
        SymptomInput(
            user_id=uuid4(),
            patient_id=uuid4(),
            language=Language.ES,
            message="Tengo dolor fuerte en el pecho",
            patient_context={
                "medications": [],
                "conditions": [],
                "recent_symptoms": [],
            },
        )
    )

    assert output.status == "success"
    assert output.response_text is not None
    assert "gracias" in output.response_text.lower()


GOLDEN_SYMPTOM_CASES = [
    ("I feel dizzy after taking my new medication", Language.EN, "dizziness", 4, True),
    ("Severe dizziness after medicine", Language.EN, "dizziness", 8, True),
    ("I have nausea after my medication", Language.EN, "nausea", 4, True),
    ("I have been vomiting since yesterday", Language.EN, "nausea", 4, False),
    ("High fever since last night", Language.EN, "fever", 4, False),
    ("Worst headache pain today", Language.EN, "pain", 8, False),
    ("Bad knee pain for three days", Language.EN, "pain", 6, False),
    ("Tengo dolor fuerte en el pecho", Language.ES, "reported symptom", 4, False),
    ("Tengo vomito despues de la medicina", Language.ES, "nausea", 4, False),
    ("Just feeling unwell", Language.EN, "reported symptom", 4, False),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message, language, expected_symptom, expected_severity, expected_adr",
    GOLDEN_SYMPTOM_CASES,
)
async def test_symptom_agent_golden_fallback_cases(
    message: str,
    language: Language,
    expected_symptom: str,
    expected_severity: int,
    expected_adr: bool,
):
    agent = SymptomAgent(router=_FailingRouter())

    output = await agent.process(
        SymptomInput(
            user_id=uuid4(),
            patient_id=uuid4(),
            language=language,
            message=message,
            patient_context={"medications": [{"name": "Metformin"}]},
        )
    )

    assert output.status == "success"
    assert output.symptom_report is not None
    assert output.symptom_report["symptom"] == expected_symptom
    assert output.symptom_report["severity"] == expected_severity
    assert output.flagged_for_adr is expected_adr
