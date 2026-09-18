"""How TriageAgent behaves when part of the model path is unavailable.

There are two different failures here and they must not produce the same answer:

* **Classification failed** — nothing is known about the message, so the patient is told
  the service is unavailable. This used to fall through to a keyword cascade that assigned
  an intent and answered in its voice; `test_triage_routing_golden.py` covers that removal.
* **Classification succeeded, response generation failed** — the intent *is* known, so the
  localized fallback copy for that intent is honest and still ships. This is the path those
  strings actually serve now.
"""

from uuid import uuid4

import pytest

from app.agents.triage.agent import TriageAgent, TriageInput
from app.agents.triage.graph import TriageClassificationResult
from app.models.enums import Language
from app.safety import TRIAGE_COPY
from app.utils.localization import resolve_locale_resource


class _FailingRouter:
    """A total outage: nothing can be classified and nothing can be generated."""

    def get_client(self, _task_type):
        raise RuntimeError("LLM unavailable")

    async def generate_text(self, _task_type, **_kwargs):
        raise RuntimeError("LLM unavailable")


class _ClassifiesButCannotRespond:
    """Classification returns a real intent; only response generation fails.

    This separates the two failures. The fallback copy below is safe precisely because the
    intent behind it was decided rather than guessed.
    """

    def __init__(self, intent: str, urgency: str) -> None:
        self._intent = intent
        self._urgency = urgency

    def get_client(self, _task_type):
        return self

    async def generate_structured(self, **_kwargs) -> TriageClassificationResult:
        return TriageClassificationResult(
            intent=self._intent,
            urgency=self._urgency,
            reason="Classified by the stubbed model",
        )

    async def generate_text(self, _task_type, **_kwargs):
        raise RuntimeError("response generation unavailable")


async def _run(router, message: str, language: Language, **kwargs):
    return await TriageAgent(router=router).process(
        TriageInput(
            user_id=uuid4(),
            patient_id=uuid4(),
            message=message,
            language=language,
            **kwargs,
        )
    )


@pytest.mark.asyncio
async def test_triage_agent_fallback_detects_emergency_keywords():
    output = await _run(
        _FailingRouter(),
        "I have chest pain and cannot breathe right now",
        Language.EN,
    )

    assert output.status == "success"
    assert output.intent == "symptom"
    assert output.urgency == "emergency"
    assert output.escalation_required is True
    assert output.response_text is not None
    assert "911" in output.response_text


@pytest.mark.asyncio
async def test_a_failed_classification_reports_the_outage():
    """No intent was decided, so nothing may be said about the message itself."""
    localized = resolve_locale_resource(Language.EN.value, TRIAGE_COPY)

    output = await _run(_FailingRouter(), "Question about my medication timing", Language.EN)

    assert output.status == "success"
    assert output.response_text == localized["service_unavailable"]
    assert (
        output.metadata["classification_reason"] == "Model unavailable; no classification was made"
    )


@pytest.mark.asyncio
async def test_a_failed_classification_reports_the_outage_in_spanish():
    localized = resolve_locale_resource(Language.ES.value, TRIAGE_COPY)

    output = await _run(_FailingRouter(), "Tengo una pregunta sobre mi medicina", Language.ES)

    assert output.response_text == localized["service_unavailable"]


@pytest.mark.asyncio
async def test_triage_agent_fallback_returns_spanish_urgent_guidance():
    output = await _run(
        _ClassifiesButCannotRespond("medication_question", "urgent"),
        "Tengo mareos y vomito despues de tomar la medicina",
        Language.ES,
    )

    assert output.status == "success"
    assert output.intent == "medication_question"
    assert output.urgency == "urgent"
    assert output.escalation_required is True
    assert output.response_text is not None
    assert "equipo clínico" in output.response_text.lower()


@pytest.mark.asyncio
async def test_triage_agent_fallback_returns_document_guidance():
    output = await _run(
        _ClassifiesButCannotRespond("document_question", "routine"),
        "Can you explain this report?",
        Language.EN,
        document_context={
            "id": str(uuid4()),
            "file_name": "discharge.pdf",
            "summary": "Follow up with primary care.",
        },
    )

    assert output.status == "success"
    assert output.intent == "document_question"
    assert output.urgency == "routine"
    assert output.escalation_required is False
    assert output.response_text is not None
    assert "attached record" in output.response_text


@pytest.mark.asyncio
async def test_triage_agent_fallback_returns_mental_health_guidance():
    output = await _run(
        _ClassifiesButCannotRespond("mental_health", "urgent"),
        "I feel hopeless and overwhelmed",
        Language.EN,
    )

    assert output.status == "success"
    assert output.intent == "mental_health"
    assert output.urgency == "urgent"
    assert output.escalation_required is True
    assert output.response_text is not None
    assert "988" in output.response_text


@pytest.mark.asyncio
async def test_triage_agent_fallback_handles_non_clinical_math_query():
    output = await _run(
        _ClassifiesButCannotRespond("general", "routine"),
        "2 + 2 = ?",
        Language.EN,
    )

    assert output.status == "success"
    assert output.intent == "general"
    assert output.urgency == "routine"
    assert output.response_text is not None
    assert "focused on health support" in output.response_text
