"""AI-003: the rolling conversation summary, written off the reply's path. Synthetic text only."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from app.adk import recap
from app.adk.recap import build_recap
from app.services import conversation_summary as cs

PATIENT = "00000000-0000-0000-0000-000000000001"
SESSION = "day-2026-10-22"
START = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)


class FakeService:
    """In-memory stand-in with the same compare-and-set rule as record_conversation_summary."""

    def __init__(self, messages: list[dict[str, Any]], stored: dict[str, Any] | None = None):
        self.messages, self.stored = messages, stored
        self.tables_read: list[str] = []
        self.writes = 0

    async def get_history(self, patient_id: str, limit: int = 50, session_id: str | None = None):
        self.tables_read.append("chat_messages")
        return self.messages[-limit:]

    async def get_conversation_summary(self, patient_id: str, session_id: str):
        self.tables_read.append("chat_conversation_summaries")
        return self.stored

    async def record_conversation_summary(
        self, patient_id, session_id, *, expected_through, through_id, summary, language
    ) -> bool:
        current = self.stored["covered_through_at"] if self.stored else None
        row = next(m for m in self.messages if m["id"] == through_id)
        if current != expected_through or (current and row["created_at"] <= current):
            return False
        self.writes += 1
        self.stored = {
            "summary": summary,
            "language": language,
            "covered_through_id": through_id,
            "covered_through_at": row["created_at"],
        }
        return True


def conversation(turns: int, size: int = 700) -> list[dict[str, Any]]:
    rows = []
    for number in range(turns):
        for offset, role in enumerate(("user", "assistant")):
            rows.append(
                {
                    "id": f"m{number}-{role}",
                    "role": role,
                    "content": f"{role} {number} " + "w" * size,
                    "created_at": (START + timedelta(minutes=2 * number + offset)).isoformat(),
                }
            )
    return rows


class Generator:
    def __init__(self, text: str = "Summary of the earlier talk about metformin."):
        self.text, self.prompts, self.fail = text, [], False

    async def __call__(self, workload, *, prompt, system_instruction, temperature):
        self.prompts.append(prompt)
        if self.fail:
            raise RuntimeError("provider said something with patient words")
        return SimpleNamespace(text=self.text)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    cs._active.clear()
    cs._running = 0
    monkeypatch.setattr(cs.settings, "conversation_summary_ai_enabled", True)


async def run(service, generate, language="en-US"):
    return await cs.refresh_summary(
        service, patient_id=PATIENT, session_id=SESSION, language=language, generate=generate
    )


@pytest.mark.asyncio
async def test_a_short_conversation_costs_no_model_call() -> None:
    service, generate = FakeService(conversation(3, size=100)), Generator()
    assert await run(service, generate) == "not_needed"
    assert generate.prompts == [] and service.writes == 0


@pytest.mark.asyncio
async def test_a_long_conversation_gets_a_summary_the_next_turn_then_reads() -> None:
    service, generate = FakeService(conversation(40)), Generator()
    assert await run(service, generate) == "updated"
    assert service.writes == 1 and len(generate.prompts) == 1
    assert "(none yet)" in generate.prompts[0] and "American English" in generate.prompts[0]
    assert len(generate.prompts[0]) < cs.INPUT_CHARS + 2000  # bounded input

    stored = service.stored
    assert stored and stored["summary"].startswith("Summary of the earlier talk")
    context = build_recap(service.messages, stored["summary"])
    assert "Summary of the earlier part of this conversation" in context
    assert "Summary of the earlier talk about metformin." in context
    assert len(context) <= recap.RECENT_CHARS + recap.SUMMARY_CHARS + 400  # within budget


@pytest.mark.asyncio
async def test_a_rewrite_folds_in_the_previous_summary_and_only_newer_messages() -> None:
    service = FakeService(conversation(40))
    assert await run(service, Generator()) == "updated"
    first = service.stored["covered_through_at"]
    # Enough new turns that the next uncovered message is about to leave the window.
    service.messages += [
        {
            **row,
            "id": row["id"] + "b",
            "created_at": (START + timedelta(hours=3, minutes=i)).isoformat(),
        }
        for i, row in enumerate(conversation(6))
    ]
    generate = Generator("Updated summary in Spanish.")
    assert await run(service, generate, language="es-MX") == "updated"
    assert "Previous summary:\nSummary of the earlier talk" in generate.prompts[0]
    assert "Mexican Spanish" in generate.prompts[0]
    assert service.stored["covered_through_at"] > first and service.stored["language"] == "es-MX"


@pytest.mark.asyncio
async def test_a_redelivered_or_concurrent_writer_loses_and_applies_nothing_twice() -> None:
    service = FakeService(conversation(40))
    stale_read = None

    class Racing(Generator):
        async def __call__(self, *args, **kwargs):
            # Another worker finishes first, from the same watermark.
            nonlocal stale_read
            stale_read = service.stored
            await service.record_conversation_summary(
                PATIENT,
                SESSION,
                expected_through=None,
                through_id=service.messages[10]["id"],
                summary="The other worker's summary.",
                language="en-US",
            )
            return await super().__call__(*args, **kwargs)

    assert await run(service, Racing()) == "stale"
    assert service.stored["summary"] == "The other worker's summary."
    assert service.writes == 1  # the loser wrote nothing


@pytest.mark.asyncio
async def test_a_failing_model_never_raises_and_keeps_the_previous_summary() -> None:
    service, generate = FakeService(conversation(40)), Generator()
    generate.fail = True
    outcome = await run(service, generate)
    assert outcome not in {"updated", "not_needed"}
    assert service.stored is None and service.writes == 0

    broken = FakeService(conversation(40))

    async def boom(*args, **kwargs):
        raise ConnectionError("database down")

    broken.get_conversation_summary = boom
    assert await run(broken, Generator()) not in {"updated"}


@pytest.mark.asyncio
async def test_a_slow_model_is_cut_off_at_the_ceiling(monkeypatch) -> None:
    monkeypatch.setattr(cs, "RUN_SECONDS", 0.05)
    service = FakeService(conversation(40))

    async def slow(*args, **kwargs):
        await asyncio.sleep(1)

    assert await run(service, slow) == "timeout"
    assert service.writes == 0


@pytest.mark.asyncio
async def test_runs_are_bounded_one_per_conversation_and_switchable(monkeypatch) -> None:
    service, generate = FakeService(conversation(40)), Generator()
    cs._active.add((PATIENT, SESSION))
    assert await run(service, generate) == "busy"
    cs._active.clear()
    cs._running = cs.MAX_CONCURRENT
    assert await run(service, generate) == "busy"
    cs._running = 0
    monkeypatch.setattr(cs.settings, "conversation_summary_ai_enabled", False)
    assert await run(service, generate) == "disabled"
    assert generate.prompts == []


@pytest.mark.asyncio
async def test_only_stored_chat_messages_and_the_summary_are_read_not_private_drafts() -> None:
    service, generate = FakeService(conversation(40)), Generator()
    service.messages.append(
        {
            "id": "draft",
            "role": "system",  # not a patient or Nora line: never part of the context
            "content": "PRIVATE-DRAFT-SENTINEL",
            "created_at": (START + timedelta(days=1)).isoformat(),
        }
    )
    await run(service, generate)
    assert set(service.tables_read) <= {"chat_messages", "chat_conversation_summaries"}
    assert "PRIVATE-DRAFT-SENTINEL" not in generate.prompts[0]
    assert "PRIVATE-DRAFT-SENTINEL" not in build_recap(service.messages, "x")


@pytest.mark.asyncio
async def test_summary_text_and_logs_stay_free_of_message_content(caplog) -> None:
    service, generate = FakeService(conversation(40)), Generator("Source: invented\n" + "s " * 2000)
    with caplog.at_level("INFO"):
        assert await run(service, generate) == "updated"
    assert len(service.stored["summary"]) <= cs.SUMMARY_STORE_CHARS + 1
    assert "Source:" not in service.stored["summary"]
    joined = " ".join(record.getMessage() for record in caplog.records)
    assert "assistant 1" not in joined and "metformin" not in joined
