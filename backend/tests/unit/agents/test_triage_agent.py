"""Unit tests for TriageAgent rule-based fallback behavior."""

from uuid import uuid4

import pytest

from app.agents.triage.agent import TriageAgent, TriageInput
from app.models.enums import Language


class _FailingRouter:
    def get_client(self, _task_type):
        raise RuntimeError("LLM unavailable")


@pytest.mark.asyncio
async def test_triage_agent_fallback_detects_emergency_keywords():
    agent = TriageAgent(router=_FailingRouter())

    output = await agent.process(
        TriageInput(
            user_id=uuid4(),
            patient_id=uuid4(),
            message="I have chest pain and cannot breathe right now",
            language=Language.EN,
        )
    )

    assert output.status == "success"
    assert output.intent == "symptom"
    assert output.urgency == "emergency"
    assert output.escalation_required is True
    assert output.response_text is not None
    assert "911" in output.response_text


@pytest.mark.asyncio
async def test_triage_agent_fallback_returns_spanish_urgent_guidance():
    agent = TriageAgent(router=_FailingRouter())

    output = await agent.process(
        TriageInput(
            user_id=uuid4(),
            patient_id=uuid4(),
            message="Tengo mareos y vomito despues de tomar la medicina",
            language=Language.ES,
        )
    )

    assert output.status == "success"
    assert output.intent == "medication_question"
    assert output.urgency == "urgent"
    assert output.escalation_required is True
    assert output.response_text is not None
    assert "equipo clínico" in output.response_text.lower()
