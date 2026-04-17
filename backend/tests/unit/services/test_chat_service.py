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
