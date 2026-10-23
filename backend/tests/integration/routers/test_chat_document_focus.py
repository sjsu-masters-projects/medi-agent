"""A conversation's document focus: attached, dismissed, restored and unavailable.

"Ask about this document" opens a conversation focused on one document. That focus is
saved with the conversation so reopening it keeps the document, which is exactly why a
dismissal has to be saved too: before, the next connection restored the document the
patient had just closed, and every later turn wrote it back.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.adk.chat_runtime import CareCoordinatorRuntime
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser

SESSION = "chat-focus-test"


def _document(document_id: str, name: str = "lab.pdf") -> dict[str, Any]:
    return {
        "id": document_id,
        "file_name": name,
        "document_type": "lab_report",
        "summary": "Synthetic summary.",
        "parse_status": "completed",
    }


class _FakeChatStore:
    """One patient's conversation row and documents, shared across connections."""

    def __init__(self, patient_id: str, documents: dict[str, dict[str, Any]]) -> None:
        self.patient_id = patient_id
        self.documents = documents
        self.state: dict[str, Any] | None = None
        self.focus_writes: list[dict[str, Any] | None] = []
        self.state_updates: list[dict[str, Any]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = self

        async def _get_history(_self, patient_id, limit=50, before=None, session_id=None, **_kw):
            return []

        async def _get_recent_clinician_messages(_self, patient_id, limit=20):
            return []

        async def _get_context(_self, patient_id, document_id=None):
            assert patient_id == store.patient_id
            return {
                "medications": [],
                "conditions": [],
                "recent_symptoms": [],
                "care_teams": [],
                "document": store.documents.get(document_id) if document_id else None,
            }

        async def _get_document_context(_self, patient_id, document_id):
            assert patient_id == store.patient_id
            return store.documents.get(document_id)

        async def _get_or_create_state(_self, patient_id, options):
            if store.state is None:
                store.state = {
                    "patient_id": patient_id,
                    "session_id": options["session_id"],
                    "turn_count": 0,
                    "summary": "",
                    "document_context": options.get("document_context"),
                }
            return dict(store.state)

        async def _update_state(_self, patient_id, updates, expected_updated_at=None):
            store.state_updates.append(dict(updates))
            assert store.state is not None
            store.state.update(updates)
            return dict(store.state)

        async def _set_document_context(_self, patient_id, session_id, document_context):
            assert patient_id == store.patient_id
            store.focus_writes.append(document_context)
            if store.state is not None:
                store.state["document_context"] = document_context

        async def _save_message(_self, patient_id, data):
            return {
                "id": str(uuid4()),
                "patient_id": patient_id,
                "content": data["content"],
                "role": data["role"],
                "intent": data.get("intent"),
                "language": data["language"],
                "audio_url": None,
                "created_at": "2026-10-11T00:00:00Z",
            }

        async def _set_title(_self, patient_id, session_id, title):
            return None

        async def _stream(_self, **_kwargs):
            yield {
                "type": "classification",
                "intent": "general",
                "urgency": "routine",
                "route": "triage",
                "escalation_required": False,
            }
            yield {"type": "complete", "response_text": "Synthetic reply."}

        prefix = "app.routers.chat.ChatService."
        monkeypatch.setattr(prefix + "get_history", _get_history)
        monkeypatch.setattr(
            prefix + "get_recent_clinician_messages", _get_recent_clinician_messages
        )
        monkeypatch.setattr(prefix + "get_context", _get_context)
        monkeypatch.setattr(prefix + "get_document_context", _get_document_context)
        monkeypatch.setattr(prefix + "get_or_create_conversation_state", _get_or_create_state)
        monkeypatch.setattr(prefix + "update_conversation_state", _update_state)
        monkeypatch.setattr(prefix + "set_document_context", _set_document_context)
        monkeypatch.setattr(prefix + "save_message", _save_message)
        monkeypatch.setattr(prefix + "set_conversation_title", _set_title)
        monkeypatch.setattr(CareCoordinatorRuntime, "process_stream", _stream)


@pytest.fixture
def patient_id():
    return uuid4()


@pytest.fixture
def connect(client, patient_id, monkeypatch):
    token_user = CurrentUser(id=patient_id, email="patient@test.com", role="patient")
    monkeypatch.setattr("app.routers.chat.decode_access_token", lambda _token: token_user)

    # A zero-argument factory: FastAPI reads an override's signature, and the MagicMock
    # class itself would expose *args/**kwargs as required query parameters.
    def _db() -> MagicMock:
        return MagicMock()

    app.dependency_overrides[get_db] = _db

    def _connect(query: str = ""):
        suffix = f"&{query}" if query else ""
        return client.websocket_connect(
            f"/ws/chat/{patient_id}?session_id={SESSION}{suffix}",
            subprotocols=["bearer", "test-token"],
        )

    yield _connect
    app.dependency_overrides.clear()


def _opening_events(websocket) -> list[dict[str, Any]]:
    """Everything sent before the first reply to a ping: the connection's opening state."""
    websocket.send_json({"type": "ping"})
    events: list[dict[str, Any]] = []
    while True:
        event = websocket.receive_json()
        if event["type"] == "pong":
            return events
        events.append(event)


def _types(events: list[dict[str, Any]]) -> list[str]:
    return [event["type"] for event in events]


def _send_turn(websocket) -> None:
    websocket.send_json(
        {"type": "user_message", "content": "What does this mean?", "language": "en"}
    )
    while websocket.receive_json()["type"] != "assistant_complete":
        pass


def test_legacy_connection_against_new_code_does_not_use_durable_store(
    connect, patient_id, monkeypatch
):
    store = _FakeChatStore(str(patient_id), {})
    store.install(monkeypatch)

    def forbidden(*args, **kwargs):
        raise AssertionError("Legacy connections must not call the durable store")

    monkeypatch.setattr("app.routers.chat.ChatTurnService", forbidden)
    with connect() as socket:
        assert "chat_turns" not in _types(_opening_events(socket))
        _send_turn(socket)


def test_dismissal_clears_the_saved_focus_and_it_is_not_restored(connect, patient_id, monkeypatch):
    document_id = str(uuid4())
    store = _FakeChatStore(str(patient_id), {document_id: _document(document_id)})
    store.install(monkeypatch)

    with connect(f"context=doc:{document_id}") as websocket:
        events = _opening_events(websocket)
        assert _types(events) == ["chat_history", "chat_context_loaded"]
        _send_turn(websocket)

    # Reopening the conversation keeps its document.
    with connect() as websocket:
        events = _opening_events(websocket)
        assert _types(events) == ["chat_history", "chat_context_loaded"]
        assert events[1]["document"]["id"] == document_id

    with connect("context=none") as websocket:
        assert _types(_opening_events(websocket)) == ["chat_history"]
    assert store.focus_writes == [None]
    assert store.state is not None and store.state["document_context"] is None

    # Neither a later connection nor a later turn brings it back.
    with connect() as websocket:
        assert _types(_opening_events(websocket)) == ["chat_history"]
        _send_turn(websocket)
    assert store.state["document_context"] is None
    assert all("document_context" not in update for update in store.state_updates)


def test_a_dismissal_with_nothing_saved_writes_nothing(connect, patient_id, monkeypatch):
    store = _FakeChatStore(str(patient_id), {})
    store.install(monkeypatch)

    with connect("context=none") as websocket:
        assert _types(_opening_events(websocket)) == ["chat_history"]
    assert store.focus_writes == []


def test_a_new_document_question_still_attaches_its_document(connect, patient_id, monkeypatch):
    first, second = str(uuid4()), str(uuid4())
    store = _FakeChatStore(
        str(patient_id), {first: _document(first), second: _document(second, "visit.pdf")}
    )
    store.install(monkeypatch)
    with connect(f"context=doc:{first}") as websocket:
        _opening_events(websocket)
    with connect("context=none") as websocket:
        _opening_events(websocket)

    with connect(f"context=doc:{second}") as websocket:
        events = _opening_events(websocket)
    assert _types(events) == ["chat_history", "chat_context_loaded"]
    assert events[1]["document"]["file_name"] == "visit.pdf"
    assert store.state is not None and store.state["document_context"]["id"] == second


def test_a_requested_document_that_cannot_be_read_is_reported(connect, patient_id, monkeypatch):
    # Deleted, or another patient's: the patient-scoped read finds nothing either way.
    store = _FakeChatStore(str(patient_id), {})
    store.install(monkeypatch)

    with connect(f"context=doc:{uuid4()}") as websocket:
        events = _opening_events(websocket)
    assert events[1:] == [{"type": "chat_context_unavailable", "context_type": "document"}]


def test_a_saved_document_that_was_deleted_is_reported_and_cleared(
    connect, patient_id, monkeypatch
):
    document_id = str(uuid4())
    store = _FakeChatStore(str(patient_id), {document_id: _document(document_id)})
    store.install(monkeypatch)
    with connect(f"context=doc:{document_id}") as websocket:
        _opening_events(websocket)

    del store.documents[document_id]
    with connect() as websocket:
        events = _opening_events(websocket)
    assert _types(events) == ["chat_history", "chat_context_unavailable"]
    assert store.state is not None and store.state["document_context"] is None

    # Reported once: with the focus cleared, the next connection is a plain conversation.
    with connect() as websocket:
        assert _types(_opening_events(websocket)) == ["chat_history"]
