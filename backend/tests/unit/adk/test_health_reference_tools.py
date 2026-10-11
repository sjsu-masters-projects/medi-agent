"""Nora's reference tools and the server-side checks on replies that use them."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.adk import grounding
from app.adk.tools import health_reference as tools
from app.adk.tools.health_reference import KNOWLEDGE_SOURCES_STATE_KEY
from app.adk.tools.scoping import PATIENT_ID_STATE_KEY
from app.services.health_knowledge_service import Knowledge, Reference

PATIENT = "e6c098a8-fb5f-4070-a575-b0201352d8c5"
CHECKED = datetime(2026, 10, 10, tzinfo=UTC)


def _reference(source: str, locale: str, **kwargs: Any) -> Reference:
    values: dict[str, Any] = {
        "source": source,
        "locale": locale,
        "title": "Metformin" if source == "medlineplus" else "METFORMIN TABLET",
        "url": "https://example.nlm.nih.gov/x",
        "summary": "Metformin treats type 2 diabetes." if source == "medlineplus" else "",
        "sections": {},
        "source_version": None,
        "source_updated_on": None,
        "checked_at": CHECKED,
        "stale": False,
    }
    values.update(kwargs)
    return Reference(**values)


LABEL = _reference(
    "dailymed",
    "en-US",
    sections={
        "indications": "For type 2 diabetes.",
        "adverse_reactions": "Diarrhea, nausea.",
        "drug_interactions": "Topiramate and other carbonic anhydrase inhibitors.",
        "contraindications": "Severe kidney disease.",
    },
    source_version="7",
    source_updated_on=date(2026, 9, 28),
)
FOUND = Knowledge(
    status="found",
    subject="metformin",
    references=[_reference("medlineplus", "en-US"), LABEL],
)


class _Service:
    def __init__(self, knowledge: Knowledge) -> None:
        self.knowledge = knowledge
        self.asked: list[str] = []

    async def medication(self, name: str) -> Knowledge:
        self.asked.append(name)
        return self.knowledge

    async def condition(self, name: str, locale: str) -> Knowledge:
        self.asked.append(f"{name}|{locale}")
        return self.knowledge if locale == "en-US" else Knowledge(status="not_found")


def _context(invocation: str = "inv-1", **state: Any) -> SimpleNamespace:
    return SimpleNamespace(state={PATIENT_ID_STATE_KEY: PATIENT, **state}, invocation_id=invocation)


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> _Service:
    fake = _Service(FOUND)
    monkeypatch.setattr(tools, "_knowledge_service", lambda: fake)

    async def rows(table: str, _columns: str, patient_id: str) -> list[dict[str, Any]]:
        assert patient_id == PATIENT  # the patient comes from session scope
        if table == "medications":
            return [
                {"name": "Metformin 500 mg", "generic_name": "metformin"},
                {"name": "Topiramate 25 mg", "generic_name": None},
                {"name": "Lisinopril 10 mg", "generic_name": None},
            ]
        return [{"name": "Type 2 diabetes"}]

    monkeypatch.setattr(tools, "_patient_rows", rows)
    return fake


@pytest.mark.asyncio
async def test_no_patient_in_scope_reads_nothing(service: _Service) -> None:
    result = await tools.get_medication_information(
        "metformin", "overview", "en-US", SimpleNamespace(state={}, invocation_id="i")
    )
    assert result["status"] == "error" and service.asked == []


@pytest.mark.asyncio
async def test_a_medication_on_the_patient_list_is_joined_and_looked_up_by_its_record_name(
    service: _Service,
) -> None:
    result = await tools.get_medication_information("Metformina", "overview", "es-MX", _context())
    assert result["on_patient_list"] is True
    assert result["patient_list_name"] == "Metformin 500 mg"
    assert service.asked == ["metformin"]
    # Only an English summary is cached here, so the reply must say so in Spanish.
    assert result["language_note"]
    assert [ref["source"] for ref in result["references"]] == ["MedlinePlus"]


@pytest.mark.asyncio
async def test_a_medication_not_on_the_list_is_general_information(service: _Service) -> None:
    result = await tools.get_medication_information("ibuprofen", "overview", "en-US", _context())
    assert result["on_patient_list"] is False and service.asked == ["ibuprofen"]


@pytest.mark.asyncio
async def test_interactions_come_from_the_label_and_name_the_patients_other_medications(
    service: _Service,
) -> None:
    result = await tools.get_medication_information(
        "metformin", "interactions", "en-US", _context()
    )
    label = next(ref for ref in result["references"] if ref["source"].startswith("DailyMed"))
    assert set(label["sections"]) == {"drug_interactions", "contraindications"}
    assert label["published_on"] == "2026-09-28" and label["label_version"] == "7"
    assert result["patient_medications_named_in_label"] == ["Topiramate 25 mg"]


@pytest.mark.asyncio
async def test_no_topic_ever_returns_a_label_dosage_section(service: _Service) -> None:
    service.knowledge = Knowledge(
        status="found",
        subject="metformin",
        references=[_reference("dailymed", "en-US", sections={"dosage": "Start 850 mg daily"})],
    )
    for topic in tools.TOPIC_SECTIONS:
        result = await tools.get_medication_information("metformin", topic, "en-US", _context())
        assert "850 mg" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["not_found", "unavailable"])
async def test_a_miss_or_outage_says_so_and_records_no_source(
    service: _Service, status: str
) -> None:
    service.knowledge = Knowledge(status=status)  # type: ignore[arg-type]
    context = _context()
    result = await tools.get_medication_information("zzz", "overview", "en-US", context)
    assert result["status"] == status and result["error"] and "references" not in result
    assert KNOWLEDGE_SOURCES_STATE_KEY not in context.state


@pytest.mark.asyncio
async def test_sources_are_recorded_per_turn_and_never_carried_into_the_next(
    service: _Service,
) -> None:
    context = _context("inv-1")
    await tools.get_medication_information("metformin", "interactions", "en-US", context)
    first = context.state[KNOWLEDGE_SOURCES_STATE_KEY]
    assert first["invocation"] == "inv-1"
    assert [item["source"] for item in first["sources"]] == ["medlineplus", "dailymed"]

    context.invocation_id = "inv-2"
    await tools.get_medication_information("metformin", "overview", "en-US", context)
    second = context.state[KNOWLEDGE_SOURCES_STATE_KEY]
    assert second["invocation"] == "inv-2"
    assert [item["source"] for item in second["sources"]] == ["medlineplus"]


@pytest.mark.asyncio
async def test_a_condition_falls_back_to_english_for_a_spanish_reader(service: _Service) -> None:
    result = await tools.get_condition_information("diabetes tipo 2", "es-MX", _context())
    assert service.asked == ["diabetes tipo 2|es-MX", "diabetes tipo 2|en-US"]
    assert result["status"] == "found" and result["language_note"]
    assert result["on_patient_list"] is True


# ── server-side reply checks ───────────────────────────────────────────────


def _event(invocation: str, value: Any) -> SimpleNamespace:
    return SimpleNamespace(
        invocation_id=invocation,
        actions=SimpleNamespace(state_delta={KNOWLEDGE_SOURCES_STATE_KEY: value}),
    )


def test_only_the_current_invocations_sources_are_read() -> None:
    sources = [{"source": "medlineplus"}]
    assert (
        grounding.sources_from_event(_event("a", {"invocation": "a", "sources": sources}))
        == sources
    )
    assert (
        grounding.sources_from_event(_event("b", {"invocation": "a", "sources": sources})) is None
    )


def test_the_source_line_is_written_in_the_readers_language() -> None:
    used = [
        {"source": "medlineplus", "title": "Metformina", "checked_on": "2026-10-10"},
        {
            "source": "dailymed",
            "title": "X",
            "checked_on": "2026-10-10",
            "published_on": "2026-09-28",
        },
    ]
    assert grounding.source_line(used, "en-US") == (
        "Sources: MedlinePlus: Metformina (checked Oct 10, 2026); "
        "DailyMed, FDA drug label (published Sep 28, 2026)"
    )
    assert grounding.source_line(used, "es-MX").startswith(
        "Fuentes: MedlinePlus: Metformina (consultado el 10 oct 2026)"
    )


def test_a_model_written_source_line_is_removed_and_speech_skips_it() -> None:
    reply = "Metformin helps.\n\n**Sources:** made-up.org\nFuente: otra"
    assert grounding.without_source_lines(reply) == "Metformin helps."


def test_a_dose_not_in_the_record_or_sources_is_reported() -> None:
    record = '{"dosage": "500 mg"}'
    assert grounding.unsupported_doses("Take your 500 mg tablet.", record) == []
    assert grounding.unsupported_doses("Some people take 1000 mg.", record) == ["1000 mg"]
