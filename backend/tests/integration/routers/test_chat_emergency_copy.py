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

Both supported locales are covered. For a long time only `en-US` was, which is the same
shape of gap as the original defect: the half of the safety copy under test was the half
that happened to be safe. An `es-MX` patient in an emergency must read the reviewed
Spanish copy, not an English fallback at the moment they are least able to use one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
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
from app.models.enums import Language
from app.routers.chat import _send_safety_turn
from app.safety import TRIAGE_COPY
from app.safety.intake_gate import evaluate_intake_safety

EN_COPY = TRIAGE_COPY[Language.EN.value]
ES_COPY = TRIAGE_COPY[Language.ES.value]


@pytest.mark.asyncio
async def test_disconnect_during_direction_still_records_pending_alert():
    from app.models.chat import ChatMessageCreate

    socket = MagicMock()
    socket.send_json = AsyncMock(side_effect=RuntimeError("websocket is not connected"))
    service = MagicMock()
    service.record_safely = AsyncMock(return_value={"delivery_state": "pending"})
    service.deliver_safely = AsyncMock()
    incoming = ChatMessageCreate(content="I have crushing chest pain", language=Language.EN)
    with pytest.raises(RuntimeError, match="websocket is not connected"):
        await _send_safety_turn(
            socket,
            service,
            {
                "patient_id": str(uuid4()),
                "incoming": incoming,
                "decision": evaluate_intake_safety(incoming.content, incoming.language.value),
            },
        )
    service.record_safely.assert_awaited_once()
    service.deliver_safely.assert_not_awaited()


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
    router's shared safety gate runs for real and bypasses this runner on emergency
    input. The plugin has separate focused coverage; stub models reject any accidental
    runtime invocation here.
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

    async def _history(_self, patient_id, limit=50, before=None, session_id=None):
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

    async def _record_safety(_self, patient_id, payload):
        user = await _save_message(
            _self,
            patient_id,
            {
                "content": payload["content"],
                "role": "user",
                "language": payload["language"],
            },
        )
        assistant = await _save_message(
            _self,
            patient_id,
            {
                "content": payload["response_text"],
                "role": "assistant",
                "language": payload["language"],
            },
        )
        return {
            "alert_id": payload["turn_id"],
            "user_message": user,
            "assistant_message": assistant,
            "delivery_state": "pending",
        }

    async def _deliver_safety(_self, options=None):
        return [{"delivery_state": "delivered", "clinicians_notified": 1}]

    monkeypatch.setattr("app.routers.chat.ChatSafetyService.record_turn", _record_safety)
    monkeypatch.setattr("app.routers.chat.ChatSafetyService.deliver_pending", _deliver_safety)


def _bland_symptom_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    """A symptom worker that answers safely for a routine symptom and fatally for an emergency."""

    async def _analyse(**_kwargs):
        return SymptomAnalysis(
            status="success",
            response_text="Thanks, I logged your symptom for follow-up.",
            symptom_report={"symptom": "chest pain", "severity": 9, "flagged_for_adr": False},
            flagged_for_adr=False,
        )

    monkeypatch.setattr("app.followup.analyse_symptom", _analyse)


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


def _urgent_symptom_classification(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _process_stream(_self, **_kwargs):
        yield {
            "type": "classification",
            "intent": "symptom",
            "urgency": "urgent",
            "route": "symptom",
            "escalation_required": True,
            "classification_reason": "stubbed urgent classification",
        }
        yield {"type": "complete", "response_text": "", "fallback_used": False}

    monkeypatch.setattr(CareCoordinatorRuntime, "process_stream", _process_stream)


def _run_turn(client, patient_id, message: str, language: str = "en") -> dict[str, Any]:
    with client.websocket_connect(
        f"/ws/chat/{patient_id}", subprotocols=["bearer", "test-token"]
    ) as websocket:
        assert websocket.receive_json()["type"] == "chat_history"
        websocket.send_json({"type": "user_message", "content": message, "language": language})
        start = None
        for _ in range(20):
            event = websocket.receive_json()
            if event["type"] == "assistant_start":
                start = event
            if event["type"] == "assistant_complete":
                assert start is not None
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
    assert result["complete"]["message"]["content"] == EN_COPY["emergency_response"]


@pytest.mark.parametrize(
    "message,locale",
    [
        ("I have crushing chest pain", "en-US"),
        ("Tengo dolor de pecho", "es-MX"),
        ("I want to kill myself", "en-US"),
        ("quiero morir", "es-MX"),
        ("List my documents, but I cannot breathe", "en-US"),
        ("No chest pain yesterday, but chest pain now", "en-US"),
    ],
)
def test_safety_interrupts_before_retrieval_models_reports_or_adr(
    client,
    override_db,
    patient_id,
    monkeypatch,
    message,
    locale,
):
    _patch_chat_runtime(monkeypatch, patient_id)
    forbidden = [
        "app.followup.analyse_symptom",
        "app.routers.chat.ChatService.save_symptom_report",
        "app.routers.chat.ChatService.get_document_catalog",
        "app.services.a2a_task_service.A2ATaskService.run_symptom_to_pharmacovigilance",
        "app.routers.chat.CareCoordinatorRuntime.process_stream",
    ]
    mocks = []
    for name in forbidden:
        mock = AsyncMock(side_effect=AssertionError("Ordinary intake must not run"))
        monkeypatch.setattr(name, mock)
        mocks.append(mock)
    result = _run_turn(client, patient_id, message, locale)
    assert result["complete"]["urgency"] == "emergency"
    assert result["complete"]["safety_rule_version"] == "triage-floor/1"
    for mock in mocks:
        mock.assert_not_called()


@pytest.mark.parametrize("failure", ["persistence", "delivery"])
@pytest.mark.parametrize(
    "locale,message,copy_key",
    [
        ("en-US", "I have chest pain", "emergency_response"),
        ("es-MX", "quiero morir", "mental_health_emergency_response"),
    ],
)
def test_direction_survives_persistence_and_alert_failures(
    client,
    override_db,
    patient_id,
    monkeypatch,
    failure,
    locale,
    message,
    copy_key,
):
    _patch_chat_runtime(monkeypatch, patient_id)
    method = "record_turn" if failure == "persistence" else "deliver_pending"
    failed = AsyncMock(side_effect=RuntimeError("Synthetic database outage"))
    monkeypatch.setattr(f"app.routers.chat.ChatSafetyService.{method}", failed)
    with client.websocket_connect(
        f"/ws/chat/{patient_id}", subprotocols=["bearer", "test-token"]
    ) as socket:
        assert socket.receive_json()["type"] == "chat_history"
        socket.send_json({"type": "user_message", "content": message, "language": locale})
        assert socket.receive_json()["type"] == "assistant_start"
        chunks = []
        complete = None
        saved = False
        while True:
            event = socket.receive_json()
            assert event["type"] != "error"
            if event["type"] == "assistant_chunk":
                chunks.append(event["content"])
            elif event["type"] == "user_message_saved":
                saved = True
            elif event["type"] == "assistant_complete":
                complete = event
            elif event["type"] == "escalation_recommended":
                break
        assert "".join(chunks) == TRIAGE_COPY[locale][copy_key]
        assert complete["message"]["content"] == TRIAGE_COPY[locale][copy_key]
        assert event["clinicians_notified"] == 0
        assert event["delivery_state"] == ("unavailable" if failure == "persistence" else "pending")
        assert saved is (failure != "persistence")
        assert complete["persistence_status"] == (
            "uncertain" if failure == "persistence" else "saved"
        )
        socket.send_json({"type": "ping"})
        assert socket.receive_json()["type"] == "pong"


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

    assert result["complete"]["message"]["content"] == EN_COPY["mental_health_emergency_response"]


def test_routine_symptom_cannot_auto_save_when_intake_unavailable(
    client, override_db, patient_id, monkeypatch
) -> None:
    """An unavailable intake neither offers a note nor falls back to the retired direct save."""
    _patch_chat_runtime(monkeypatch, patient_id)
    _bland_symptom_worker(monkeypatch)
    _routine_symptom_classification(monkeypatch)
    monkeypatch.setattr("app.routers.chat.settings.symptom_intake_enabled", False)

    result = _run_turn(client, patient_id, "I have a mild headache today")

    assert result["start"]["urgency"] != "emergency"
    assert not result["complete"]["message"].get("attachments")


@pytest.mark.parametrize(
    ("message", "language", "offered"),
    [
        ("I have a mild headache today", "en-US", True),
        ("Me siento mareado desde ayer", "es-MX", True),
        ("What medications am I taking?", "en-US", False),
        ("¿Cuándo es mi próxima cita?", "es-MX", False),
    ],
)
def test_only_a_reportable_symptom_gets_a_note_offer(
    client, override_db, patient_id, monkeypatch, message: str, language: str, offered: bool
) -> None:
    _patch_chat_runtime(monkeypatch, patient_id)
    _bland_symptom_worker(monkeypatch)
    _routine_symptom_classification(monkeypatch)
    monkeypatch.setattr("app.routers.chat.settings.symptom_intake_enabled", True)

    result = _run_turn(client, patient_id, message, language=language)

    attachments = result["complete"]["message"].get("attachments") or []
    assert [item["type"] for item in attachments] == (["symptom_intake_offer"] if offered else [])
    if offered and language == "es-MX":
        assert "equipo de atención" in result["complete"]["message"]["content"]


@pytest.mark.parametrize("message", ["I have crushing chest pain", "quiero morir"])
def test_an_emergency_never_gets_a_note_offer(
    client, override_db, patient_id, monkeypatch, message: str
) -> None:
    _patch_chat_runtime(monkeypatch, patient_id)
    _bland_symptom_worker(monkeypatch)
    monkeypatch.setattr("app.routers.chat.settings.symptom_intake_enabled", True)

    result = _run_turn(client, patient_id, message)

    assert result["start"]["urgency"] == "emergency"
    assert not result["complete"]["message"].get("attachments")


@pytest.mark.parametrize(
    "message",
    [
        "Tengo un dolor de pecho muy fuerte",
        "Creo que estoy teniendo un infarto",
        "No puedo respirar",
        # Unaccented, because a patient in distress does not type carefully.
        "me desmaye hace un momento",
    ],
)
def test_a_spanish_medical_emergency_reads_the_reviewed_spanish_copy(
    client, override_db, patient_id, monkeypatch, message: str
) -> None:
    _patch_chat_runtime(monkeypatch, patient_id)
    _bland_symptom_worker(monkeypatch)

    result = _run_turn(client, patient_id, message, language="es-MX")

    assert result["start"]["urgency"] == "emergency"
    content = result["complete"]["message"]["content"]
    assert content == ES_COPY["emergency_response"]
    # An emergency is the worst moment to answer in a language the patient does not read.
    assert content != EN_COPY["emergency_response"]


def test_spanish_self_harm_keeps_the_crisis_line(
    client, override_db, patient_id, monkeypatch
) -> None:
    _patch_chat_runtime(monkeypatch, patient_id)
    _bland_symptom_worker(monkeypatch)

    result = _run_turn(client, patient_id, "quiero morir", language="es-MX")

    assert result["complete"]["message"]["content"] == ES_COPY["mental_health_emergency_response"]


def test_the_symptom_worker_cannot_replace_a_spanish_emergency_answer(
    client, override_db, patient_id, monkeypatch
) -> None:
    """The original defect, in the locale that never had a test for it."""
    _patch_chat_runtime(monkeypatch, patient_id)
    _bland_symptom_worker(monkeypatch)

    result = _run_turn(client, patient_id, "Tengo un dolor de pecho muy fuerte", language="es-MX")

    assert "logged your symptom" not in result["complete"]["message"]["content"]


def test_a_spanish_emergency_is_still_escalated_to_the_care_team(
    client, override_db, patient_id, monkeypatch
) -> None:
    _patch_chat_runtime(monkeypatch, patient_id)
    _bland_symptom_worker(monkeypatch)

    result = _run_turn(client, patient_id, "Creo que estoy teniendo un infarto", language="es-MX")

    assert result["start"]["urgency"] == "emergency"


def test_non_emergency_offers_a_note_without_starting_a_draft_or_report(
    client, override_db, patient_id, monkeypatch
):
    _patch_chat_runtime(monkeypatch, patient_id)
    _routine_symptom_classification(monkeypatch)
    monkeypatch.setattr("app.routers.chat.settings.symptom_intake_enabled", True)
    start = AsyncMock(side_effect=AssertionError("An offer must not open a draft"))
    save = AsyncMock(side_effect=AssertionError("No direct report save"))
    monkeypatch.setattr("app.services.symptom_intake_service.SymptomIntakeService.start", start)
    monkeypatch.setattr("app.routers.chat.ChatService.save_symptom_report", save)
    result = _run_turn(client, patient_id, "I have a mild headache today")
    message = result["complete"]["message"]
    assert "Nothing is shared" in message["content"]
    assert message["attachments"][0]["type"] == "symptom_intake_offer"
    start.assert_not_awaited()
    save.assert_not_awaited()


def test_urgent_symptom_keeps_care_team_escalation_alongside_the_offer(
    client, override_db, patient_id, monkeypatch
) -> None:
    _patch_chat_runtime(monkeypatch, patient_id)
    _urgent_symptom_classification(monkeypatch)
    monkeypatch.setattr("app.routers.chat.settings.symptom_intake_enabled", True)

    result = _run_turn(client, patient_id, "I have severe dizziness")

    assert result["start"]["urgency"] == "urgent"
    assert result["complete"]["escalation_required"] is True
