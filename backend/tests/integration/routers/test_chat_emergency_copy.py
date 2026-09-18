"""The words an emergency patient reads must survive the whole turn.

This is a regression test for a defect that reached production. The deterministic floor
classified "crushing chest pain" as an emergency correctly — the classification event said
`urgency: emergency`, escalation fired, and the care team was notified. But the floor
labels a medical emergency `intent="symptom"`, which routes the turn into the symptom
branch, where the symptom worker's reply replaced the reviewed 911 copy. The patient was
shown "I logged your symptom for follow-up" and was never told to call 911.

Self-harm was never affected, because it classifies as `mental_health` and never enters
that branch. Both are covered here, because the contrast is the mechanism: the bug was
invisible precisely where the copy happened to be safe.

These assert on the text the patient actually receives, not on the classification. The
classification was already right when this shipped, and being right there is what made the
defect hard to see.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.models import BaseLlm

from app.adk.agents.care_coordinator import (
    COORDINATOR_AGENT_NAME,
    RESPONDER_AGENT_NAME,
    TOOL_ALLOWLIST,
)
from app.adk.chat_runtime import APP_NAME, CareCoordinatorRuntime
from app.adk.runner import build_runner
from app.db.connection import get_db
from app.followup import SymptomAnalysis
from app.main import app
from app.models.auth import CurrentUser


@pytest.fixture
def patient_id():
    return uuid4()


@pytest.fixture
def override_db():
    db = MagicMock()
    table = MagicMock()
    db.table.return_value = table
    for method in ["select", "eq", "single", "insert", "order", "limit", "lt", "update"]:
        getattr(table, method).return_value = table
    table.execute.return_value = MagicMock(data=[])

    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.clear()


class _NeverCalled(BaseLlm):
    """Any use of this is a failure: the floor must answer without a model."""

    async def generate_content_async(self, llm_request: Any, stream: bool = False) -> Any:
        raise AssertionError("The safety floor must decide without consulting a model")
        yield  # pragma: no cover - unreachable, but makes this an async generator


def _stub_agent_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the runtime a runner built from stub models.

    The real one resolves Application Default Credentials and builds a Vertex client the
    moment it is first used. A test that reaches for those passes or fails on whether the
    machine running it happens to be logged in, which is not a property of this code. The
    emergency plugin still runs for real; only the models behind it are stubs, and they
    raise if anything reaches them.
    """
    runner = build_runner(
        app_name=APP_NAME,
        agent=SequentialAgent(
            name="pipeline",
            sub_agents=[
                LlmAgent(name=COORDINATOR_AGENT_NAME, model=_NeverCalled(model="stub-a")),
                LlmAgent(name=RESPONDER_AGENT_NAME, model=_NeverCalled(model="stub-b")),
            ],
        ),
        tool_allowlist=TOOL_ALLOWLIST,
    )
    monkeypatch.setattr("app.adk.chat_runtime.get_chat_runner", lambda: runner)


def _patch_chat_runtime(monkeypatch: pytest.MonkeyPatch, patient_id: Any) -> None:
    _stub_agent_runtime(monkeypatch)
    monkeypatch.setattr(
        "app.routers.chat.decode_access_token",
        lambda _token: CurrentUser(id=patient_id, email="patient@test.com", role="patient"),
    )

    async def _history(_self, patient_id, limit=50, before=None):
        return []

    async def _context(_self, patient_id, document_id=None):
        return {"medications": [], "conditions": [], "recent_symptoms": [], "document": None}

    async def _state(_self, patient_id, options):
        return {
            "patient_id": patient_id,
            "session_id": "default",
            "turn_count": 0,
            "last_intent": "general",
            "last_urgency": "routine",
            "last_route": "triage",
            "summary": "",
            "document_context": None,
        }

    async def _update(_self, patient_id, updates):
        return {"patient_id": patient_id, **updates}

    async def _save_message(_self, patient_id, data):
        return {
            "id": str(uuid4()),
            "patient_id": patient_id,
            "content": str(data.get("content", "")),
            "role": str(data.get("role", "user")),
            "intent": data.get("intent"),
            "language": str(data.get("language", "en")),
            "audio_url": data.get("audio_url"),
            "created_at": datetime.now(UTC).isoformat(),
        }

    async def _clinician_messages(_self, patient_id, limit=20):
        return []

    async def _notify(_self, patient_id, payload):
        return 0

    async def _save_symptom(_self, patient_id, report):
        return {"id": str(uuid4()), **report}

    async def _teams(_self, patient_id):
        return []

    for name, replacement in [
        ("get_history", _history),
        ("get_context", _context),
        ("get_or_create_conversation_state", _state),
        ("update_conversation_state", _update),
        ("save_message", _save_message),
        ("get_recent_clinician_messages", _clinician_messages),
        ("notify_assigned_clinicians", _notify),
        ("save_symptom_report", _save_symptom),
    ]:
        monkeypatch.setattr(f"app.routers.chat.ChatService.{name}", replacement)
    monkeypatch.setattr("app.services.chat_service.ChatService._fetch_active_care_teams", _teams)


def _bland_symptom_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    """A symptom worker that answers safely for a routine symptom and fatally for an emergency."""

    async def _analyse(**_kwargs):
        return SymptomAnalysis(
            status="success",
            response_text="Thanks, I logged your symptom for follow-up.",
            symptom_report={"symptom": "chest pain", "severity": 9, "flagged_for_adr": False},
            flagged_for_adr=False,
        )

    monkeypatch.setattr("app.routers.chat.analyse_symptom", _analyse)


def _routine_symptom_classification(monkeypatch: pytest.MonkeyPatch) -> None:
    """Classify a non-emergency onto the symptom route without consulting a model.

    The emergency cases in this module reach the floor, which answers before any model is
    consulted — the property they exist to prove. A message that does *not* trip the floor
    has no such shortcut, so leaving it unstubbed would send the test at a live endpoint,
    which hangs the suite and makes the result depend on whether the machine running it
    happens to hold credentials.
    """

    async def _process_stream(_self, **_kwargs):
        yield {
            "type": "classification",
            "intent": "symptom",
            "urgency": "urgent",
            "route": "symptom",
            "escalation_required": False,
            "classification_reason": "stubbed classification",
        }
        yield {"type": "complete", "response_text": "", "fallback_used": False}

    monkeypatch.setattr(CareCoordinatorRuntime, "process_stream", _process_stream)


def _run_turn(client, patient_id, message: str) -> dict[str, Any]:
    with client.websocket_connect(
        f"/ws/chat/{patient_id}", subprotocols=["bearer", "test-token"]
    ) as websocket:
        assert websocket.receive_json()["type"] == "chat_history"
        websocket.send_json({"type": "user_message", "content": message, "language": "en"})
        assert websocket.receive_json()["type"] == "user_message_saved"

        start = websocket.receive_json()
        assert start["type"] == "assistant_start"

        for _ in range(20):
            event = websocket.receive_json()
            if event["type"] == "assistant_complete":
                return {"start": start, "complete": event}

    raise AssertionError("The turn never completed")


@pytest.mark.parametrize(
    "message",
    [
        "I have crushing chest pain",
        "I think I am having a stroke",
        "I cannot breathe",
    ],
)
def test_a_medical_emergency_still_tells_the_patient_to_call_911(
    client, override_db, patient_id, monkeypatch, message: str
) -> None:
    """The defect: correct classification, and the 911 copy replaced before it was shown."""
    _patch_chat_runtime(monkeypatch, patient_id)
    _bland_symptom_worker(monkeypatch)

    result = _run_turn(client, patient_id, message)

    assert result["start"]["urgency"] == "emergency"
    assert "911" in result["complete"]["message"]["content"]


def test_the_symptom_worker_cannot_replace_an_emergency_answer(
    client, override_db, patient_id, monkeypatch
) -> None:
    """Stated separately from the 911 check, because this is the mechanism, not the symptom."""
    _patch_chat_runtime(monkeypatch, patient_id)
    _bland_symptom_worker(monkeypatch)

    result = _run_turn(client, patient_id, "I have crushing chest pain")

    assert "I logged your symptom" not in result["complete"]["message"]["content"]


def test_an_emergency_is_still_escalated_to_the_care_team(
    client, override_db, patient_id, monkeypatch
) -> None:
    """Protecting the copy must not cost the escalation that was already working."""
    _patch_chat_runtime(monkeypatch, patient_id)
    _bland_symptom_worker(monkeypatch)

    result = _run_turn(client, patient_id, "I have crushing chest pain")

    assert result["complete"]["escalation_required"] is True


def test_self_harm_keeps_the_crisis_line(client, override_db, patient_id, monkeypatch) -> None:
    """Never affected, because it routes to triage rather than the symptom branch."""
    _patch_chat_runtime(monkeypatch, patient_id)
    _bland_symptom_worker(monkeypatch)

    result = _run_turn(client, patient_id, "I want to kill myself")

    assert "988" in result["complete"]["message"]["content"]


def test_a_routine_symptom_is_still_answered_by_the_symptom_worker(
    client, override_db, patient_id, monkeypatch
) -> None:
    """The guard must be narrow: only an emergency withholds the worker's reply."""
    _patch_chat_runtime(monkeypatch, patient_id)
    _bland_symptom_worker(monkeypatch)
    _routine_symptom_classification(monkeypatch)

    result = _run_turn(client, patient_id, "I have a mild headache today")

    assert result["start"]["urgency"] != "emergency"
    assert "I logged your symptom" in result["complete"]["message"]["content"]
