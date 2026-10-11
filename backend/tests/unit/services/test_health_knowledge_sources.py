"""Reference fetchers: resolution guard, label choice, section parsing, failure outcomes.

Responses are small copies of the real NLM response shapes, served by a mock transport,
so nothing here touches the network.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import httpx
import pytest

from app.services import health_knowledge_sources as sources
from app.services.health_knowledge_sources import Ingredient, SourceUnavailableError

SPL = """<?xml version="1.0"?>
<document xmlns="urn:hl7-org:v3">
  <title>METFORMIN HYDROCHLORIDE TABLETS</title>
  <component><structuredBody>
    <component><section><code code="34066-1"/><title>WARNING: LACTIC ACIDOSIS</title>
      <text><paragraph>Lactic acidosis can occur.</paragraph></text></section></component>
    <component><section><code code="34067-9"/><title>1 INDICATIONS AND USAGE</title>
      <text><paragraph>Used to improve blood sugar control in type 2 diabetes.</paragraph></text>
    </section></component>
    <component><section><code code="34068-7"/><title>2 DOSAGE AND ADMINISTRATION</title>
      <component><section><code code="42229-5"/><title>2.1 Adult Dosage</title>
        <text><paragraph>Start 500 mg twice daily.</paragraph></text></section></component>
    </section></component>
    <component><section><code code="43685-7"/><title>5 WARNINGS AND PRECAUTIONS</title>
      <component><section><code code="42229-5"/><title>5.2 Vitamin B12 Deficiency</title>
        <text><paragraph>Measure vitamin B12.</paragraph></text></section></component>
    </section></component>
    <component><section><code code="34073-7"/><title>7 DRUG INTERACTIONS</title>
      <text><paragraph>Carbonic anhydrase inhibitors such as topiramate.</paragraph></text>
    </section></component>
  </structuredBody></component>
</document>"""

SEARCH = """<?xml version="1.0" encoding="UTF-8"?>
<nlmSearchResult><list num="1" start="0" per="1">
  <document rank="0" url="https://medlineplus.gov/spanish/diabetestype2.html">
    <content name="title">&lt;span class="qt0"&gt;Diabetes&lt;/span&gt; tipo 2</content>
    <content name="FullSummary">¿Qué es la diabetes tipo 2?&lt;p&gt;Es una enfermedad.&lt;/p&gt;</content>
  </document>
</list></nlmSearchResult>"""


def _client(routes: dict[str, Any]) -> httpx.AsyncClient:
    """Serve canned responses by path; a value of an int is an HTTP error status."""

    def handler(request: httpx.Request) -> httpx.Response:
        for prefix, body in routes.items():
            if request.url.path.endswith(prefix) or prefix in str(request.url):
                if isinstance(body, int):
                    return httpx.Response(body)
                if isinstance(body, str):
                    return httpx.Response(200, text=body)
                return httpx.Response(200, json=body)
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _approximate(rxcui: str, *names: str) -> dict[str, Any]:
    return {
        "approximateGroup": {
            "candidate": [{"rxcui": rxcui, "name": name, "score": "9"} for name in names]
        }
    }


RELATED_METFORMIN = {
    "relatedGroup": {
        "conceptGroup": [
            {"tty": "IN", "conceptProperties": [{"rxcui": "6809", "name": "metformin"}]}
        ]
    }
}


@pytest.mark.asyncio
@pytest.mark.parametrize("asked", ["Metformina 500 mg", "metformin", "METFORMINA tableta"])
async def test_a_spanish_or_dosed_name_resolves_to_its_ingredient(asked: str) -> None:
    client = _client(
        {
            "approximateTerm.json": _approximate("6809", "Metformina", None),
            "related.json": RELATED_METFORMIN,
        }
    )
    async with client:
        assert await sources.resolve_ingredient(client, asked) == Ingredient("6809", "metformin")


@pytest.mark.asyncio
async def test_an_approximate_match_sharing_no_word_is_rejected() -> None:
    """Approximate matching always finds something; "hydration" came back as chloral hydrate."""
    client = _client(
        {"approximateTerm.json": _approximate("2344", "Chloral Hydrate", "chloral hydrate")}
    )
    async with client:
        assert await sources.resolve_ingredient(client, "hydration") is None


@pytest.mark.asyncio
async def test_no_candidate_is_a_miss_not_an_outage() -> None:
    client = _client({"approximateTerm.json": {"approximateGroup": {}}})
    async with client:
        assert await sources.resolve_ingredient(client, "zzzz") is None


@pytest.mark.asyncio
async def test_a_failing_source_raises_rather_than_reporting_a_miss() -> None:
    client = _client({"approximateTerm.json": 503})
    async with client:
        with pytest.raises(SourceUnavailableError):
            await sources.resolve_ingredient(client, "metformin")


def test_label_choice_skips_combinations_and_prefers_tablets() -> None:
    rows = [
        {"setid": "a", "title": "DAPAGLIFLOZIN AND METFORMIN HYDROCHLORIDE TABLET"},
        {"setid": "b", "title": "METFORMIN HYDROCHLORIDE SOLUTION"},
        {"setid": "c", "title": "METFORMIN HYDROCHLORIDE TABLET, FILM COATED"},
    ]
    assert sources._choose_label(rows, "metformin")["setid"] == "c"
    assert sources._choose_label(rows[:2], "metformin")["setid"] == "b"
    assert sources._choose_label(rows[:1], "metformin") is None


@pytest.mark.asyncio
async def test_label_sections_are_parsed_by_code_and_dosage_is_never_kept() -> None:
    listing = {
        "data": [
            {
                "setid": "s1",
                "title": "METFORMIN HYDROCHLORIDE TABLET [ACME]",
                "spl_version": 7,
                "published_date": "Sep 28, 2026",
            }
        ]
    }
    client = _client({"spls.json": listing, "spls/s1.xml": SPL})
    async with client:
        label = await sources.dailymed_label(client, Ingredient("6809", "metformin"))
    assert label is not None
    assert set(label.sections) == {
        "boxed_warning",
        "indications",
        "warnings",
        "drug_interactions",
    }
    assert "Vitamin B12" in label.sections["warnings"]  # subsections are included
    assert "500 mg" not in json.dumps(label.sections)
    assert label.version == "7" and label.updated_on == date(2026, 9, 28)
    assert label.url == "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=s1"


@pytest.mark.asyncio
async def test_medlineplus_drug_page_is_plain_text_without_tracking() -> None:
    feed = {
        "feed": {
            "entry": [
                {
                    "title": {"_value": "Metformina"},
                    "link": [
                        {
                            "href": "https://medlineplus.gov/spanish/druginfo/meds/a696005-es.html"
                            "?utm_source=mplusconnect&utm_medium=service"
                        }
                    ],
                    "summary": {"_value": "<p>La metformina se usa &amp; ayuda.</p>"},
                }
            ]
        }
    }
    client = _client({"connect.medlineplus.gov": feed})
    async with client:
        text = await sources.medlineplus_medication(client, "6809", "es-MX")
    assert text is not None
    assert text.summary == "La metformina se usa & ayuda."
    assert text.url == "https://medlineplus.gov/spanish/druginfo/meds/a696005-es.html"


@pytest.mark.asyncio
async def test_condition_search_strips_highlighting_and_separates_the_heading() -> None:
    client = _client({"wsearch.nlm.nih.gov": SEARCH})
    async with client:
        text = await sources.medlineplus_condition(client, "diabetes tipo 2", "es-MX")
    assert text is not None
    assert text.title == "Diabetes tipo 2"
    assert text.summary == "¿Qué es la diabetes tipo 2?\nEs una enfermedad."


@pytest.mark.asyncio
async def test_gathering_keeps_an_outage_apart_from_a_miss() -> None:
    client = _client({"connect.medlineplus.gov": {"feed": {"entry": []}}, "spls.json": 500})
    async with client:
        fetched = await sources.gather_medication(client, Ingredient("6809", "metformin"))
    assert fetched[("medlineplus", "en-US")] is None
    assert fetched[("medlineplus", "es-MX")] is None
    assert isinstance(fetched[("dailymed", "en-US")], SourceUnavailableError)
