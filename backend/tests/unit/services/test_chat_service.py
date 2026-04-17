"""Tests for ChatService persistence and history."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import ExternalServiceError
from app.models.enums import ChatRole, Language
from app.services.chat_service import ChatService


def _response(data):
    return SimpleNamespace(data=data)


@pytest.fixture
def mock_db():
    db = MagicMock()
    table = MagicMock()
    db.table.return_value = table

    for method in ["select", "eq", "order", "limit", "lt", "insert"]:
        getattr(table, method).return_value = table

    return db


@pytest.mark.asyncio
async def test_save_message_persists_row(mock_db):
    patient_id = str(uuid4())
    saved_row = {
        "id": str(uuid4()),
        "patient_id": patient_id,
        "content": "I feel dizzy",
        "role": "user",
        "intent": None,
        "language": "en",
        "audio_url": None,
        "created_at": "2026-04-16T12:00:00Z",
    }
    mock_db.table().insert().execute.return_value = _response([saved_row])

    service = ChatService(mock_db)
    result = await service.save_message(
        patient_id,
        {
            "content": "I feel dizzy",
            "role": ChatRole.USER,
            "language": Language.EN,
        },
    )

    assert result == saved_row
    mock_db.table.assert_called_with("chat_messages")


@pytest.mark.asyncio
async def test_save_message_raises_when_insert_returns_empty(mock_db):
    mock_db.table().insert().execute.return_value = _response([])
    service = ChatService(mock_db)

    with pytest.raises(ExternalServiceError, match="Failed to save chat message"):
        await service.save_message(
            str(uuid4()),
            {"content": "test", "role": "user", "language": "en"},
        )


@pytest.mark.asyncio
async def test_get_history_supports_cursor_filter(mock_db):
    patient_id = str(uuid4())
    rows = [
        {
            "id": str(uuid4()),
            "patient_id": patient_id,
            "content": "hello",
            "role": "user",
            "intent": None,
            "language": "en",
            "audio_url": None,
            "created_at": "2026-04-16T10:00:00Z",
        }
    ]
    mock_db.table().select().eq().order().limit().lt().execute.return_value = _response(rows)

    service = ChatService(mock_db)
    history = await service.get_history(
        patient_id=patient_id,
        limit=25,
        before="2026-04-16T11:00:00Z",
    )

    assert history == rows
    mock_db.table().select().eq().order().limit().lt.assert_any_call(
        "created_at", "2026-04-16T11:00:00Z"
    )


@pytest.mark.asyncio
async def test_get_context_returns_patient_and_document_context(mock_db):
    patient_id = str(uuid4())
    document_id = str(uuid4())

    med_rows = [{"id": str(uuid4()), "name": "Metformin", "dosage": "500mg"}]
    condition_rows = [{"id": str(uuid4()), "name": "Hypertension", "status": "active"}]
    symptom_rows = [{"id": str(uuid4()), "symptom": "dizziness", "severity": 4}]
    document_rows = [
        {
            "id": document_id,
            "file_name": "labs.pdf",
            "document_type": "lab",
            "ai_summary": "A1C 8.1",
            "notes": None,
            "parse_status": "completed",
        }
    ]

    mock_db.table().execute.side_effect = [
        _response(med_rows),
        _response(condition_rows),
        _response(symptom_rows),
        _response(document_rows),
    ]

    service = ChatService(mock_db)
    context = await service.get_context(patient_id=patient_id, document_id=document_id)

    assert context["medications"] == med_rows
    assert context["conditions"] == condition_rows
    assert context["recent_symptoms"] == symptom_rows
    assert context["document"] is not None
    assert context["document"]["id"] == document_id


@pytest.mark.asyncio
async def test_save_symptom_report_returns_none_when_payload_invalid(mock_db):
    service = ChatService(mock_db)
    result = await service.save_symptom_report(str(uuid4()), {"symptom": "", "severity": 0})
    assert result is None


@pytest.mark.asyncio
async def test_notify_assigned_clinicians_creates_in_app_messages(mock_db):
    assignments = [{"clinician_id": str(uuid4())}, {"clinician_id": str(uuid4())}]
    mock_db.table().execute.side_effect = [_response(assignments), _response([])]

    service = ChatService(mock_db)
    created_count = await service.notify_assigned_clinicians(
        patient_id=str(uuid4()),
        payload={"urgency": "urgent", "intent": "symptom", "message_excerpt": "Severe dizziness"},
    )

    assert created_count == 2


@pytest.mark.asyncio
async def test_get_or_create_conversation_state_inserts_when_missing(mock_db):
    patient_id = str(uuid4())
    inserted = {
        "id": str(uuid4()),
        "patient_id": patient_id,
        "session_id": "default",
        "summary": "",
        "turn_count": 0,
    }
    mock_db.table().execute.side_effect = [_response([]), _response([inserted])]

    service = ChatService(mock_db)
    result = await service.get_or_create_conversation_state(
        patient_id=patient_id,
        options={
            "session_id": "default",
            "summary": "",
            "turn_count": 0,
        },
    )

    assert result["session_id"] == "default"
    assert result["patient_id"] == patient_id


@pytest.mark.asyncio
async def test_update_conversation_state_updates_existing_row(mock_db):
    patient_id = str(uuid4())
    updated = {
        "id": str(uuid4()),
        "patient_id": patient_id,
        "session_id": "s-1",
        "summary": "latest summary",
        "turn_count": 4,
    }
    mock_db.table().execute.side_effect = [_response([updated])]

    service = ChatService(mock_db)
    result = await service.update_conversation_state(
        patient_id=patient_id,
        updates={
            "session_id": "s-1",
            "summary": "latest summary",
            "turn_count": 4,
            "last_intent": "symptom",
            "last_urgency": "urgent",
            "last_route": "symptom",
        },
    )

    assert result["summary"] == "latest summary"
    assert result["turn_count"] == 4
