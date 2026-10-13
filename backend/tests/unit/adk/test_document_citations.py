"""Citing the patient's own documents: written by the server, from what the tools returned."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.adk import grounding
from app.adk.tools import patient_records
from app.adk.tools.document_context import get_active_document_context
from app.adk.tools.scoping import DOCUMENT_CONTEXT_STATE_KEY, PATIENT_ID_STATE_KEY
from app.adk.tools.turn_sources import (
    TURN_SOURCES_STATE_KEY,
    document_citation,
    record_turn_sources,
)

PATIENT = "e6c098a8-fb5f-4070-a575-b0201352d8c5"
FILE = "Morgan-Ellis_Metformin-Medication-Order_2026-10-02.pdf"
DOCUMENT = {
    "id": "55bc0b62-8726-47ea-9817-4e45535e8616",
    "file_name": FILE,
    "display_title": {"en-US": "Metformin prescription", "es-MX": "Receta de metformina"},
    "document_type": "prescription",
    "summary": "A prescription for metformin.",
}
CONFIRMED = "confirmed by the care team"
PENDING = "not yet reviewed by the care team"
MEDLINEPLUS = {"source": "medlineplus", "title": "Metformin", "checked_on": "2026-10-11"}


def _item(name: str, page: Any, status: str = PENDING) -> dict[str, Any]:
    return {"details": {"name": name}, "review_status": status, "page": page}


def _line(sources: list[dict[str, Any]], reply: str, locale: str) -> str:
    return grounding.source_line(grounding.cited_sources(sources, reply), locale)


def _context(invocation: str = "inv-1", **state: Any) -> SimpleNamespace:
    return SimpleNamespace(state={PATIENT_ID_STATE_KEY: PATIENT, **state}, invocation_id=invocation)


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en-US", f"Source: Metformin prescription ({FILE}), page 1"),
        ("es-MX", f"Fuente: Receta de metformina ({FILE}), página 1"),
    ],
)
def test_a_document_is_cited_by_title_file_name_and_page(locale: str, expected: str) -> None:
    citation = document_citation(DOCUMENT, items=[_item("Metformin", 1)], selected=True)
    assert citation is not None
    assert _line([citation], "It lists metformin.", locale) == expected


@pytest.mark.parametrize(
    ("pages", "locale", "expected"),
    [
        ([3, 1], "en-US", "pages 1 and 3"),
        ([2, 1, 3, 2], "en-US", "pages 1, 2 and 3"),
        ([3, 1], "es-MX", "páginas 1 y 3"),
        ([1, 2, 3], "es-MX", "páginas 1, 2 y 3"),
    ],
)
def test_page_lists_read_naturally(pages: list[int], locale: str, expected: str) -> None:
    items = [_item(f"Item{index}", page) for index, page in enumerate(pages)]
    citation = document_citation(DOCUMENT, items=items, selected=True)
    assert citation is not None
    assert _line([citation], "Here is what it says.", locale).endswith(f"({FILE}), {expected}")


def test_without_a_title_in_the_readers_language_the_file_name_is_used() -> None:
    english_only = {**DOCUMENT, "display_title": {"en-US": "Metformin prescription"}}
    untitled = {**DOCUMENT, "display_title": {}}
    first = document_citation(english_only, items=[_item("Metformin", 1)], selected=True)
    second = document_citation(untitled, selected=True)
    assert first is not None and second is not None
    assert _line([first], "Metformina.", "es-MX") == f"Fuente: {FILE}, página 1"
    assert _line([second], "It is a prescription.", "en-US") == f"Source: {FILE}"
    assert document_citation({**DOCUMENT, "file_name": " "}, selected=True) is None


def test_rejected_and_unpaged_items_never_reach_a_citation() -> None:
    items = [
        _item("Metformin", 1, CONFIRMED),
        _item("Lisinopril", 4, "rejected"),
        _item("Aspirin", None),
        _item("Ibuprofen", True),
        _item("Glipizide", 2),
    ]
    citation = document_citation(DOCUMENT, items=items, selected=True)
    assert citation is not None
    assert [entry["page"] for entry in citation["pages"]] == [1, 2]
    assert _line([citation], "Lisinopril is on page four.", "en-US").endswith("pages 1 and 2")


def test_only_the_pages_of_items_the_reply_names_are_cited_when_it_names_any() -> None:
    items = [_item("Metformin HCl 500 mg", 1), _item("Lisinopril", 2)]
    citation = document_citation(DOCUMENT, items=items, selected=True)
    assert citation is not None
    assert _line([citation], "Tu receta dice metformina.", "es-MX").endswith("página 1")
    assert _line([citation], "It lists two medicines.", "en-US").endswith("pages 1 and 2")


def test_reference_and_document_sources_share_one_line() -> None:
    citation = document_citation(DOCUMENT, items=[_item("Metformin", 1)], selected=True)
    assert citation is not None
    assert _line([citation, MEDLINEPLUS], "Metformin lowers sugar.", "en-US") == (
        f"Sources: Metformin prescription ({FILE}), page 1; "
        "MedlinePlus: Metformin (checked Oct 11, 2026)"
    )
    assert _line([MEDLINEPLUS, citation], "La metformina baja el azúcar.", "es-MX") == (
        "Fuentes: MedlinePlus: Metformin (consultado el 11 oct 2026); "
        f"Receta de metformina ({FILE}), página 1"
    )


def test_no_document_source_without_a_document_tool() -> None:
    assert _line([], "Metformin lowers sugar.", "en-US") == ""
    assert _line([MEDLINEPLUS], "Metformin lowers sugar.", "en-US") == (
        "Source: MedlinePlus: Metformin (checked Oct 11, 2026)"
    )


def test_search_results_are_narrowed_to_the_documents_the_reply_names() -> None:
    hydration = document_citation(
        {"id": "a", "file_name": "hydration.pdf", "display_title": {"en-US": "Hydration plan"}},
        selected=False,
    )
    labs = document_citation(
        {"id": "b", "file_name": "labs.pdf", "display_title": {"en-US": "Lab results"}},
        selected=False,
    )
    found = [item for item in (hydration, labs) if item is not None]
    assert _line(found, "Your hydration plan says to drink water.", "en-US") == (
        "Source: Hydration plan (hydration.pdf)"
    )
    # Naming neither, the answer still cites every document it was given.
    assert _line(found, "Two documents mention it.", "en-US") == (
        "Sources: Hydration plan (hydration.pdf); Lab results (labs.pdf)"
    )


def test_the_same_document_is_merged_and_a_new_turn_starts_empty() -> None:
    context = _context("inv-1")
    record_turn_sources(context, [MEDLINEPLUS])
    record_turn_sources(context, [document_citation(DOCUMENT, selected=True) or {}])
    record_turn_sources(
        context,
        [document_citation(DOCUMENT, items=[_item("Metformin", 2)], selected=True) or {}],
    )
    recorded = context.state[TURN_SOURCES_STATE_KEY]["sources"]
    assert [item["source"] for item in recorded] == ["medlineplus", "document"]
    assert recorded[1]["pages"] == [{"page": 2, "name": "Metformin"}]

    context.invocation_id = "inv-2"
    record_turn_sources(context, [document_citation(DOCUMENT, selected=False) or {}])
    assert context.state[TURN_SOURCES_STATE_KEY]["invocation"] == "inv-2"
    assert len(context.state[TURN_SOURCES_STATE_KEY]["sources"]) == 1


@pytest.mark.asyncio
async def test_document_tools_record_what_they_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    # Details with no extracted items record nothing.
    monkeypatch.setattr(patient_records, "_document_facts", lambda *_: [])
    empty = _context(**{DOCUMENT_CONTEXT_STATE_KEY: DOCUMENT})
    await patient_records.get_document_details(empty)
    assert TURN_SOURCES_STATE_KEY not in empty.state

    monkeypatch.setattr(
        patient_records, "_document_facts", lambda *_: [_item("Metformin", 1, CONFIRMED)]
    )
    details = _context(**{DOCUMENT_CONTEXT_STATE_KEY: DOCUMENT})
    await patient_records.get_document_details(details)
    [cited] = details.state[TURN_SOURCES_STATE_KEY]["sources"]
    assert cited["document_id"] == DOCUMENT["id"] and cited["selected"] is True

    summary = _context(**{DOCUMENT_CONTEXT_STATE_KEY: DOCUMENT})
    get_active_document_context(summary)
    assert summary.state[TURN_SOURCES_STATE_KEY]["sources"][0]["pages"] == []

    unsummarised = _context(**{DOCUMENT_CONTEXT_STATE_KEY: {**DOCUMENT, "summary": ""}})
    get_active_document_context(unsummarised)
    assert TURN_SOURCES_STATE_KEY not in unsummarised.state

    def search(patient_id: str, words: list[str]) -> list[dict[str, Any]]:
        assert patient_id == PATIENT
        return [{**DOCUMENT, "ai_summary": "Metformin.", "created_at": "2026-10-02"}]

    monkeypatch.setattr(patient_records, "_search_documents", search)
    searched = _context()
    await patient_records.search_my_documents("metformin", "en-US", searched)
    [found] = searched.state[TURN_SOURCES_STATE_KEY]["sources"]
    assert found["selected"] is False and found["file_name"] == FILE


def test_speech_skips_a_document_source_line() -> None:
    reply = f"Tu receta dice metformina.\n\nFuente: Receta de metformina ({FILE}), página 1"
    assert grounding.without_source_lines(reply) == "Tu receta dice metformina."
    assert grounding.without_source_lines("Hi.\n\nSource: x.pdf, page 1") == "Hi."
