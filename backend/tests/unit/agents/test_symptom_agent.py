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
