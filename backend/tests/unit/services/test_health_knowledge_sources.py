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


@pytest.mark.parametrize(
    ("asked", "candidate"),
    [
        ("losartan", "valsartan"),
        ("hydralazine hydrochloride", "Metformin hydrochloride"),
        ("losartan potassium", "Potassium chloride"),
        ("metformin extended release", "Metoprolol succinate extended release"),
    ],
)
def test_look_alike_and_salt_names_do_not_match(asked: str, candidate: str) -> None:
    assert not sources.names_match(asked, [candidate])


@pytest.mark.asyncio
async def test_a_combination_product_resolves_to_nothing_rather_than_one_ingredient() -> None:
    related = {
        "relatedGroup": {
            "conceptGroup": [
                {
                    "tty": "IN",
                    "conceptProperties": [
                        {"rxcui": "6809", "name": "metformin"},
                        {"rxcui": "593411", "name": "sitagliptin"},
                    ],
                }
            ]
        }
    }
    client = _client(
        {"approximateTerm.json": _approximate("729717", "Janumet"), "related.json": related}
    )
    async with client:
        assert await sources.resolve_ingredient(client, "Janumet") is None


@pytest.mark.asyncio
async def test_a_condition_topic_must_match_the_name_asked_about() -> None:
    unrelated = SEARCH.replace("diabetestype2", "kidneydisease").replace(
        '&lt;span class="qt0"&gt;Diabetes&lt;/span&gt; tipo 2', "Enfermedades renales"
    )
    client = _client({"wsearch.nlm.nih.gov": unrelated})
    async with client:
        assert await sources.medlineplus_condition(client, "diabetes tipo 2", "es-MX") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("body", ["<html>maintenance</html>", '{"approximateGroup": 3}'])
async def test_a_malformed_response_is_an_outage_not_a_crash(body: str) -> None:
    client = _client({"approximateTerm.json": body})
    async with client:
        with pytest.raises(SourceUnavailableError):
            await sources.resolve_ingredient(client, "metformin")


def test_dose_sentences_are_removed_from_reference_text() -> None:
    text = "It treats diabetes. Take 500 mg twice daily.\nTalk to your pharmacist."
    assert sources.strip_doses(text) == "It treats diabetes.\nTalk to your pharmacist."


# ── Condition topics: best of several, qualifier retry, the twin page in the other language

_EN = "https://medlineplus.gov"
_ES = "https://medlineplus.gov/spanish"


def _doc(url: str, title: str, *alt_titles: str, rank: int = 0) -> str:
    """One search-result document in the web service's shape (public topic names only)."""
    alts = "".join(f'<content name="altTitle">{alt}</content>' for alt in alt_titles)
    return (
        f'<document rank="{rank}" url="{url}">'
        f'<content name="title">{title}</content>{alts}'
        f'<content name="FullSummary">&lt;p&gt;Summary of {title}.&lt;/p&gt;</content>'
        "</document>"
    )


def _results(*documents: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?><nlmSearchResult>'
        f'<list num="{len(documents)}" start="0" per="10">{"".join(documents)}</list>'
        "</nlmSearchResult>"
    )


def _topic_client(
    english: dict[str, str],
    spanish: dict[str, str] | None = None,
    pages: dict[str, str] | None = None,
) -> tuple[httpx.AsyncClient, list[tuple[str, str]]]:
    """Serve search results by (index, term) and page heads by path; record each request."""
    asked: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "wsearch.nlm.nih.gov":
            database = request.url.params["db"]
            term = request.url.params["term"]
            asked.append((database, term))
            by_term = (spanish or {}) if database == "healthTopicsSpanish" else english
            return httpx.Response(200, text=by_term.get(term.casefold(), _results()))
        asked.append(("page", request.url.path))
        page = (pages or {}).get(request.url.path)
        return httpx.Response(206, text=page) if page is not None else httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), asked


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("asked", "documents", "expected"),
    [
        (
            "high cholesterol",
            [
                _doc(
                    f"{_EN}/highcholesterolinchildrenandteens.html",
                    "High Cholesterol in Children and Teens",
                ),
                _doc(f"{_EN}/cholesterol.html", "Cholesterol", "Hypercholesterolemia", rank=1),
                _doc(f"{_EN}/howtolowercholesterol.html", "How to Lower Cholesterol", rank=2),
            ],
            "Cholesterol",
        ),
        (
            "high blood pressure",
            [
                _doc(
                    f"{_EN}/howtopreventhighbloodpressure.html",
                    "How to Prevent High Blood Pressure",
                    "High Blood Pressure Prevention",
                ),
                _doc(
                    f"{_EN}/highbloodpressure.html",
                    "High Blood Pressure",
                    "Hypertension",
                    "Essential hypertension",
                    rank=1,
                ),
            ],
            "High Blood Pressure",
        ),
        (
            "type 2 diabetes",
            [
                _doc(f"{_EN}/diabetes.html", "Diabetes", "Diabetes Mellitus"),
                _doc(f"{_EN}/diabetestype1.html", "Diabetes Type 1", "Type 1 Diabetes", rank=1),
                _doc(f"{_EN}/diabetestype2.html", "Diabetes Type 2", "Type 2 Diabetes", rank=2),
            ],
            "Diabetes Type 2",
        ),
    ],
)
async def test_the_general_topic_that_names_the_condition_wins_over_the_top_hit(
    asked: str, documents: list[str], expected: str
) -> None:
    client, requests = _topic_client({asked: _results(*documents)})
    async with client:
        text = await sources.medlineplus_condition(client, asked, "en-US")
    assert text is not None
    assert text.title == expected
    assert text.summary == f"Summary of {expected}."
    assert requests == [("healthTopics", asked)]  # one search, no retry


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("asked", "first", "simpler", "expected"),
    [
        ("mild persistent asthma", _results(), "asthma", "Asthma"),
        ("episodic migraine", _results(_doc(f"{_EN}/pain.html", "Pain")), "migraine", "Migraine"),
        (
            "osteoarthritis of the knee",
            _results(
                _doc(f"{_EN}/arthritis.html", "Arthritis", "Joint inflammation"),
                _doc(f"{_EN}/kneereplacement.html", "Knee Replacement", rank=1),
            ),
            "osteoarthritis",
            "Osteoarthritis",
        ),
    ],
)
async def test_qualifiers_are_dropped_for_one_retry_when_nothing_matches(
    asked: str, first: str, simpler: str, expected: str
) -> None:
    assert sources.without_qualifiers(asked) == simpler
    client, requests = _topic_client(
        {asked: first, simpler: _results(_doc(f"{_EN}/{simpler}.html", expected))}
    )
    async with client:
        text = await sources.medlineplus_condition(client, asked, "en-US")
    assert text is not None and text.title == expected
    assert requests == [("healthTopics", asked), ("healthTopics", simpler)]


@pytest.mark.asyncio
async def test_an_unrelated_top_hit_is_still_rejected() -> None:
    """ "Pain" shares no word with "episodic migraine"; it must never be cached under it."""
    client, requests = _topic_client(
        {"episodic migraine": _results(_doc(f"{_EN}/pain.html", "Pain"))},
        {"episodic migraine": _results(_doc(f"{_ES}/pain.html", "Dolor"))},
    )
    async with client:
        assert await sources.medlineplus_condition(client, "episodic migraine", "en-US") is None
    assert ("healthTopics", "migraine") in requests


ECZEMA = _doc(
    f"{_EN}/eczema.html",
    '&lt;span class="qt0"&gt;Eczema&lt;/span&gt;',
    "Atopic Dermatitis",
    "Dermatitis",
)
ECCEMA = _doc(f"{_ES}/eczema.html", "Eccema", "Dermatitis")


@pytest.mark.asyncio
async def test_spanish_is_the_english_topics_own_spanish_page() -> None:
    """The Spanish index is never searched with the English condition name."""
    client, requests = _topic_client(
        {"atopic dermatitis": _results(ECZEMA)},
        {"eczema": _results(_doc(f"{_ES}/foodallergy.html", "Alergia a los alimentos"), ECCEMA)},
    )
    async with client:
        english = await sources.medlineplus_condition(client, "atopic dermatitis", "en-US")
        spanish = await sources.medlineplus_condition(client, "atopic dermatitis", "es-MX")
    assert english is not None and english.title == "Eczema"
    assert spanish is not None
    assert spanish.title == "Eccema"
    assert spanish.url == f"{_ES}/eczema.html"
    assert spanish.summary == "Summary of Eccema."
    assert ("healthTopicsSpanish", "atopic dermatitis") not in requests


@pytest.mark.asyncio
async def test_the_spanish_page_title_finds_the_twin_when_the_english_title_does_not() -> None:
    head = "<html><head><title>Eccema | Dermatitis | MedlinePlus en español</title></head>"
    client, requests = _topic_client(
        {"atopic dermatitis": _results(ECZEMA)},
        {"eccema": _results(ECCEMA)},
        pages={"/spanish/eczema.html": head},
    )
    async with client:
        spanish = await sources.medlineplus_condition(client, "atopic dermatitis", "es-MX")
    assert spanish is not None and spanish.title == "Eccema"
    assert requests == [
        ("healthTopics", "atopic dermatitis"),
        ("healthTopicsSpanish", "Eczema"),
        ("page", "/spanish/eczema.html"),
        ("healthTopicsSpanish", "Eccema"),
    ]


@pytest.mark.asyncio
async def test_no_spanish_twin_is_a_miss_never_english_text_under_spanish() -> None:
    client, requests = _topic_client(
        {"atopic dermatitis": _results(ECZEMA)},
        # The Spanish index answers, but not with the twin page's URL; the page is missing.
        {"eczema": _results(_doc(f"{_ES}/skinconditions.html", "Enfermedades de la piel"))},
    )
    async with client:
        assert await sources.medlineplus_condition(client, "atopic dermatitis", "es-MX") is None
    assert requests[-1] == ("page", "/spanish/eczema.html")


@pytest.mark.asyncio
async def test_a_spanish_stored_name_resolves_in_spanish_and_its_english_twin() -> None:
    english_hits = _results(
        _doc(f"{_EN}/diabetestype1.html", "Diabetes Type 1", "Type 1 Diabetes"),
        _doc(f"{_EN}/diabetestype2.html", "Diabetes Type 2", "Type 2 Diabetes", rank=1),
    )
    spanish_hits = _results(
        _doc(f"{_ES}/diabetestype2.html", "Diabetes tipo 2", "Diabetes Mellitus Estable"),
        _doc(f"{_ES}/diabetes.html", "Diabetes", "Diabetes tipo II", rank=1),
    )
    client, requests = _topic_client(
        # The English index does not know "tipo": its diabetes topics only share words.
        {"diabetes tipo 2": english_hits},
        {"diabetes tipo 2": spanish_hits},
    )
    async with client:
        spanish = await sources.medlineplus_condition(client, "diabetes tipo 2", "es-MX")
        english = await sources.medlineplus_condition(client, "diabetes tipo 2", "en-US")
    assert spanish is not None and spanish.title == "Diabetes tipo 2"
    assert spanish.url == f"{_ES}/diabetestype2.html"
    assert english is not None and english.title == "Diabetes Type 2"
    assert english.url == f"{_EN}/diabetestype2.html"
    # en-US: English (no match), Spanish (match), then the twin from the English index.
    assert requests[-3:] == [
        ("healthTopics", "diabetes tipo 2"),
        ("healthTopicsSpanish", "diabetes tipo 2"),
        ("healthTopics", "Diabetes tipo 2"),
    ]


@pytest.mark.asyncio
async def test_a_spanish_page_in_the_english_results_is_not_an_english_topic() -> None:
    client, _requests = _topic_client({"eczema": _results(_doc(f"{_ES}/eczema.html", "Eczema"))})
    async with client:
        assert await sources.medlineplus_condition(client, "eczema", "en-US") is None


@pytest.mark.asyncio
async def test_an_outage_while_finding_the_twin_is_unavailable_not_a_miss() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("db") == "healthTopics":
            return httpx.Response(200, text=_results(ECZEMA))
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceUnavailableError):
            await sources.medlineplus_condition(client, "atopic dermatitis", "es-MX")
