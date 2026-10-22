"""AI-003: evidence is staged with the reply and saved after it, without ever changing the turn."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.enums import ChatRole
from app.services import chat_turn_pipeline as pipeline
from app.services.chat_service import ChatService
from app.services.chat_turn_execution import TurnChatService

PATIENT = "00000000-0000-0000-0000-000000000001"
EVIDENCE = {"version": 1, "tools": [], "sources": [], "care_plan_ids": []}


async def _staged() -> TurnChatService:
    staged = TurnChatService(ChatService(MagicMock()), MagicMock(), {"id": "user-message"})
    await staged.save_message(
        PATIENT,
        {"content": "Hi", "role": ChatRole.ASSISTANT, "session_id": "s", "evidence": EVIDENCE},
    )
    return staged


@pytest.mark.asyncio
async def test_evidence_is_held_beside_the_staged_reply_not_inside_it() -> None:
    staged = await _staged()
    assert staged.evidence == EVIDENCE
    assert staged.reply is not None and "evidence" not in staged.reply


@pytest.mark.asyncio
async def test_a_failed_evidence_save_never_fails_the_turn_and_the_summary_is_still_scheduled(
    monkeypatch,
) -> None:
    staged = await _staged()
    service = MagicMock()
    service.db = MagicMock()
    monkeypatch.setattr(
        ChatService, "record_reply_evidence", AsyncMock(side_effect=RuntimeError("db down"))
    )
    scheduled = MagicMock()
    monkeypatch.setattr(pipeline, "schedule_refresh", scheduled)
    context = {"patient_id": PATIENT, "session_id": "s"}
    incoming = SimpleNamespace(language=SimpleNamespace(value="es-MX"))

    await pipeline._after_completion(service, staged, {"id": "reply-1"}, context, incoming)

    scheduled.assert_called_once()
    assert scheduled.call_args.kwargs["language"] == "es-MX"


@pytest.mark.asyncio
async def test_evidence_is_saved_for_the_saved_reply_id(monkeypatch) -> None:
    staged = await _staged()
    record = AsyncMock(return_value=True)
    monkeypatch.setattr(ChatService, "record_reply_evidence", record)
    monkeypatch.setattr(pipeline, "schedule_refresh", MagicMock(side_effect=RuntimeError))
    service = MagicMock()

    await pipeline._after_completion(
        service,
        staged,
        {"id": "reply-1"},
        {"patient_id": PATIENT, "session_id": "s"},
        SimpleNamespace(language="en-US"),
    )

    record.assert_awaited_once_with(PATIENT, "s", "reply-1", EVIDENCE)
