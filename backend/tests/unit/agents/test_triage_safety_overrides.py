"""Tests for triage safety overrides, fallback categorization, and 988-aware
mental-health emergency response (gaps G1, G2, G6, G8 from
.agent/specs/chat-scenario-matrix.md).
"""

from uuid import uuid4

import pytest

from app.agents.triage.agent import TriageAgent, TriageInput
from app.agents.triage.graph import categorize_llm_failure
from app.models.enums import Language


class _FailingRouter:
    def get_client(self, _task_type):
        raise RuntimeError("LLM unavailable")


class _AuthFailingRouter:
    def get_client(self, _task_type):
        raise RuntimeError(
            "Your default credentials were not found. To set up Application Default Credentials"
        )


@pytest.mark.asyncio
async def test_g6_self_harm_response_includes_988() -> None:
    agent = TriageAgent(router=_FailingRouter())

    output = await agent.process(
        TriageInput(
            user_id=uuid4(),
            patient_id=uuid4(),
            message="I want to kill myself",
            language=Language.EN,
            history=[],
        )
    )

    assert output.intent == "mental_health"
    assert output.urgency == "emergency"
    assert output.escalation_required is True
    assert "988" in (output.response_text or "")
    assert "911" in (output.response_text or "")


@pytest.mark.asyncio
async def test_g6_spanish_self_harm_uses_988_template() -> None:
    agent = TriageAgent(router=_FailingRouter())

    output = await agent.process(
        TriageInput(
            user_id=uuid4(),
            patient_id=uuid4(),
            message="Quiero quitarme la vida",
            language=Language.ES,
            history=[],
        )
    )

    assert output.intent == "mental_health"
    assert output.urgency == "emergency"
    assert "988" in (output.response_text or "")


@pytest.mark.asyncio
async def test_g2_spanish_chest_pain_classified_as_emergency_by_rule() -> None:
    agent = TriageAgent(router=_FailingRouter())

    output = await agent.process(
        TriageInput(
            user_id=uuid4(),
            patient_id=uuid4(),
            message="Tengo dolor de pecho fuerte",
            language=Language.ES,
            history=[],
        )
    )

    assert output.intent == "symptom"
    assert output.urgency == "emergency"
    assert output.escalation_required is True


@pytest.mark.asyncio
async def test_g2_spanish_cant_breathe_emergency() -> None:
    agent = TriageAgent(router=_FailingRouter())

    output = await agent.process(
        TriageInput(
            user_id=uuid4(),
            patient_id=uuid4(),
            message="No puedo respirar",
            language=Language.ES,
            history=[],
        )
    )

    assert output.urgency == "emergency"


@pytest.mark.asyncio
async def test_g8_safety_override_does_not_downgrade_emergency() -> None:
    """Adverse-effect signal must not downgrade an emergency to urgent."""
    agent = TriageAgent(router=_FailingRouter())

    # Emergency keyword + adverse-effect-style word in same message.
    output = await agent.process(
        TriageInput(
            user_id=uuid4(),
            patient_id=uuid4(),
            message="I have chest pain and severe rash",
            language=Language.EN,
            history=[],
        )
    )

    assert output.urgency == "emergency"


def test_g1_categorize_llm_failure_buckets_credentials_error() -> None:
    exc = RuntimeError(
        "Your default credentials were not found. To set up Application Default Credentials"
    )
    assert categorize_llm_failure(exc) == "auth_error"


def test_g1_categorize_llm_failure_buckets_timeout() -> None:
    class FakeTimeoutError(Exception):
        pass

    FakeTimeoutError.__name__ = "TimeoutError"  # bucket-rule matches name suffix
    assert categorize_llm_failure(FakeTimeoutError("deadline exceeded")) == "timeout"


def test_g1_categorize_llm_failure_buckets_quota() -> None:
    assert categorize_llm_failure(RuntimeError("429 quota exceeded")) == "quota_exceeded"


def test_g1_categorize_llm_failure_buckets_unknown() -> None:
    assert categorize_llm_failure(RuntimeError("totally novel issue")) == "unknown_error"
