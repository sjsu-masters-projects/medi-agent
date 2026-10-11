"""Document tools: patient scope, review status, and a query that cannot add filters."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.adk.tools import patient_records as tools
from app.adk.tools.scoping import DOCUMENT_CONTEXT_STATE_KEY, PATIENT_ID_STATE_KEY
from app.services.chat_service import conversation_title, normalize_session_id

PATIENT = "e6c098a8-fb5f-4070-a575-b0201352d8c5"
DOCUMENT = "55bc0b62-8726-47ea-9817-4e45535e8616"


def _context(**state: Any) -> SimpleNamespace:
    return SimpleNamespace(state={PATIENT_ID_STATE_KEY: PATIENT, **state})


def test_facts_carry_review_status_page_and_a_bounded_excerpt() -> None:
    fact = {
        "id": "f1",
        "fact_type": "obligation",
        "review_state": "pending_review",
        "value": {"description": "Tome un vaso de agua con cada comida", "secret": "x"},
    }
    citation = {"excerpt": "Tome un vaso " + "a" * 500, "location": {"page": 1, "bbox": {}}}
    entry = tools._fact_entry(fact, [citation])
    assert entry["review_status"] == "not yet reviewed by the care team"
    assert entry["page"] == 1 and len(entry["excerpt"]) == tools.EXCERPT_CHARS
    assert entry["details"] == {"description": "Tome un vaso de agua con cada comida"}


@pytest.mark.asyncio
async def test_document_details_need_a_patient_and_a_server_selected_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, str]] = []

    def facts(patient_id: str, document_id: str) -> list[dict[str, Any]]:
        seen.append((patient_id, document_id))
        return [{"type": "medication"}]

    monkeypatch.setattr(tools, "_document_facts", facts)
    assert "error" in await tools.get_document_details(SimpleNamespace(state={}))
    assert "error" in await tools.get_document_details(_context())
    result = await tools.get_document_details(
        _context(**{DOCUMENT_CONTEXT_STATE_KEY: {"id": DOCUMENT, "document_type": "other"}})
    )
    assert result["items"] == [{"type": "medication"}] and seen == [(PATIENT, DOCUMENT)]


@pytest.mark.asyncio
async def test_rejected_facts_are_never_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Facts:
        def __init__(self, _db: Any) -> None: ...

        def list_facts_for_document(self, *_: Any) -> list[dict[str, Any]]:
            return [
                {"id": "a", "fact_type": "medication", "review_state": "approved", "value": {}},
                {"id": "b", "fact_type": "medication", "review_state": "rejected", "value": {}},
            ]

    class _Query:
        def select(self, *_: Any) -> _Query:
            return self

        def in_(self, _column: str, values: list[str]) -> _Query:
            assert values == ["a"]
            return self

        def execute(self) -> SimpleNamespace:
            return SimpleNamespace(data=[])

    monkeypatch.setattr(tools, "ClinicalFactService", _Facts)
    monkeypatch.setattr(
        tools, "get_admin_client", lambda: SimpleNamespace(table=lambda _name: _Query())
    )
    items = tools._document_facts(PATIENT, DOCUMENT)
    assert [item["review_status"] for item in items] == ["confirmed by the care team"]


@pytest.mark.asyncio
async def test_a_search_query_is_reduced_to_words_so_it_cannot_add_a_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[list[str]] = []

    def search(patient_id: str, words: list[str]) -> list[dict[str, Any]]:
        assert patient_id == PATIENT
        received.append(words)
        return [
            {
                "file_name": "a.pdf",
                "display_title": {"es-MX": "Indicaciones de hidratación"},
                "document_type": "other",
                "created_at": "2026-10-10T00:00:00Z",
                "ai_summary": "**Tome** agua.",
            }
        ]

    monkeypatch.setattr(tools, "_search_documents", search)
    result = await tools.search_my_documents("hidratación),patient_id.neq.x*", "es-MX", _context())
    assert all(word.isalpha() for word in received[0])
    assert result["documents"][0]["title"] == "Indicaciones de hidratación"
    assert result["documents"][0]["summary"] == "Tome agua."
    assert (await tools.search_my_documents("!!", "en-US", _context()))["documents"] == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("day-2026-10-10", "day-2026-10-10"),
        ("chat-k3j2h1", "chat-k3j2h1"),
        ("", "default"),
        (None, "default"),
        ("../etc", "default"),
        ("x" * 65, "default"),
    ],
)
def test_conversation_ids_are_validated(raw: Any, expected: str) -> None:
    assert normalize_session_id(raw) == expected


def test_conversation_titles_are_one_line_and_cut_at_a_word() -> None:
    assert conversation_title("  What is\nmetformin for? ") == "What is metformin for?"
    long = conversation_title("word " * 40)
    assert long.endswith("…") and len(long) <= 81 and "  " not in long
