"""Fetch public reference text from RxNorm, DailyMed and MedlinePlus.

Each function makes a few small requests to a National Library of Medicine service and
returns plain data, ``None`` when the source has nothing, or raises ``SourceUnavailableError``
when it does not answer, so a network failure is never cached as "not found". Nothing
here is cached and nothing here sees patient data: callers pass a medication or condition
name, never a record. ``health_knowledge_service`` owns caching and freshness.
"""

from __future__ import annotations

import asyncio
import difflib
import functools
import hashlib
import html
import json
import logging
import re
import unicodedata
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, ParamSpec, TypeVar
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)

RXNAV = "https://rxnav.nlm.nih.gov/REST"
DAILYMED = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
MEDLINEPLUS_CONNECT = "https://connect.medlineplus.gov/service"
MEDLINEPLUS_SEARCH = "https://wsearch.nlm.nih.gov/ws/query"
MEDLINEPLUS = "https://medlineplus.gov"
RXNORM_SYSTEM = "2.16.840.1.113883.6.88"
REQUEST_TIMEOUT = httpx.Timeout(6.0, connect=3.0)

SUMMARY_LIMIT = 6000
SECTION_LIMIT = 6000
MAX_RESPONSE_BYTES = 3_000_000
NAME_SIMILARITY = 0.85
TOPIC_SEARCH_HITS = 10
PAGE_HEAD_BYTES = 32_768

# MedlinePlus health topics: each language has its own search index, and a topic's page
# in one language has a twin at the same slug in the other.
_TOPIC_DATABASES = {"en-US": "healthTopics", "es-MX": "healthTopicsSpanish"}
_TOPIC_PATHS = {"en-US": "/", "es-MX": "/spanish/"}
_TOPIC_URL = re.compile(r"https://medlineplus\.gov/(spanish/)?([a-z0-9]+)\.html")
_PAGE_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
# Joining words never decide whether a topic matches a condition name.
_FILLER = frozenset(
    "a an and at by for in of on or the to with con de del el en la las los para por su"
    " sus un una y".split()
)
# Severity, course and side qualifiers (English, and Spanish unaccented), and "of the
# knee"-style body sites. They are dropped for one retry, only when the name as written
# matches no general topic.
_QUALIFIERS = frozenset(
    """mild moderate severe persistent intermittent episodic chronic acute recurrent
    seasonal left right bilateral leve moderada moderado grave severa severo persistente
    intermitente episodica episodico cronica cronico aguda agudo recurrente estacional
    izquierda izquierdo derecha derecho""".split()
)
_BODY_SITE = re.compile(
    r"\b(?:of|in)\s+(?:the\s+)?(?:(?:left|right|both)\s+)?"
    r"(?:knee|hip|shoulder|hand|foot|feet|ankle|wrist|elbow|neck|back|spine)s?\b",
    re.I,
)
# Title words (unaccented) for a narrower audience, a how-to, a treatment or a test. A
# topic with one is chosen only when no general topic matches, unless the name says it.
_NARROWING = frozenset(
    """children child kids teens teen infants infant babies baby newborns newborn pregnancy
    women men older seniors how prevent prevention lower medicines tests screening diet
    surgery ninos adolescentes bebes embarazo mujer mujeres hombres mayores como prevenir
    prevencion bajar medicinas medicamentos pruebas dieta cirugia""".split()
)

# FDA label sections by LOINC code. Dosage is deliberately absent: a label's dose ranges
# are not this patient's prescription, and Nora must never present them as one. The
# Medication Guide (42230-3) is left out for the same reason: its "how should I take"
# part carries doses.
LABEL_SECTIONS: dict[str, tuple[str, ...]] = {
    "boxed_warning": ("34066-1",),
    "indications": ("34067-9",),
    "contraindications": ("34070-3",),
    "warnings": ("43685-7", "34071-1"),
    "adverse_reactions": ("34084-4",),
    "drug_interactions": ("34073-7",),
    "patient_counseling": ("34076-0", "88436-1"),
}
_HL7 = {"h": "urn:hl7-org:v3"}
_TAG = re.compile(r"<[^>]+>")
_BLOCK_END = re.compile(r"</?(?:p|h[1-6]|li|ul|ol|div)\b[^>]*>|<br\s*/?>", re.I)
DOSE = re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:mg|mcg|µg|g|ml|mL|units?|unidades|ui|iu)\b", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
P = ParamSpec("P")
R = TypeVar("R")


class SourceUnavailableError(RuntimeError):
    """A reference service did not answer; try again later rather than record a miss."""


def _shape_checked(
    fetch: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[R]]:
    """A response that is not the documented shape is an outage, never a miss or a crash.

    A maintenance page served with 200, truncated JSON or unexpected types would otherwise
    raise out of a chat tool and end the turn.
    """

    @functools.wraps(fetch)
    async def checked(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await fetch(*args, **kwargs)
        except SourceUnavailableError:
            raise
        except (ValueError, KeyError, TypeError, AttributeError, ElementTree.ParseError) as error:
            logger.warning(
                "Reference source returned an unexpected shape: %s", type(error).__name__
            )
            raise SourceUnavailableError(fetch.__name__) from error

    return checked


def strip_doses(text: str) -> str:
    """Drop sentences that state an amount: reference doses are never this patient's."""
    kept = (
        sentence
        for line in text.splitlines()
        for sentence in [" ".join(s for s in _SENTENCE.split(line) if not DOSE.search(s))]
        if sentence.strip()
    )
    return "\n".join(kept)


@dataclass(frozen=True)
class Ingredient:
    rxcui: str
    name: str


@dataclass(frozen=True)
class SourceText:
    """One source's text about one subject in one language."""

    title: str
    url: str | None
    summary: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    version: str | None = None
    updated_on: date | None = None

    @property
    def content_hash(self) -> str:
        payload = json.dumps(
            [self.title, self.url, self.summary, self.sections, self.version], sort_keys=True
        )
        return hashlib.sha256(payload.encode()).hexdigest()


def plain_text(markup: str) -> str:
    """HTML or highlighted search markup to readable text, keeping paragraph breaks."""
    text = _BLOCK_END.sub("\n", markup)
    text = html.unescape(_TAG.sub("", text))
    # Search results run a heading question into its answer: "What is it?It is ...".
    text = re.sub(r"\?(?=[A-ZÁÉÍÓÚÑ¿])", "?\n", text)
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


async def _get(
    client: httpx.AsyncClient, url: str, *, headers: Mapping[str, str] | None = None, **params: Any
) -> httpx.Response:
    host = httpx.URL(url).host
    try:
        response = await client.get(
            url, params=params or None, headers=headers, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise httpx.DecodingError("response larger than the reference size limit")
        return response
    except httpx.HTTPError as error:
        # Only the host is logged: the query is a drug or condition name, never patient
        # data, but a log line has no reason to carry it.
        logger.warning("Reference source request failed: %s %s", host, type(error).__name__)
        raise SourceUnavailableError(host) from error


@_shape_checked
async def resolve_ingredient(client: httpx.AsyncClient, name: str) -> Ingredient | None:
    """Resolve a name as written ("Metformina 500 mg", "Tylenol") to its RxNorm ingredient.

    A combination product ("Janumet") resolves to nothing for now: answering with one of
    its ingredients would describe only part of what the patient takes.
    """
    response = await _get(
        client, f"{RXNAV}/approximateTerm.json", term=name, maxEntries=8, option=1
    )
    candidates = response.json().get("approximateGroup", {}).get("candidate") or []
    rxcui = next((str(c["rxcui"]) for c in candidates if c.get("rxcui")), None)
    if rxcui is None:
        return None
    names = [str(c.get("name") or "") for c in candidates if str(c.get("rxcui")) == rxcui]
    if not names_match(name, names):
        # Approximate matching always finds something: "hydration" comes back as chloral
        # hydrate. A match must share a word with what was asked about.
        return None
    related = await _get(client, f"{RXNAV}/rxcui/{rxcui}/related.json", tty="IN")
    ingredients = {
        str(concept["rxcui"]): str(concept["name"])
        for group in related.json().get("relatedGroup", {}).get("conceptGroup") or []
        for concept in group.get("conceptProperties") or []
        if concept.get("rxcui") and concept.get("name")
    }
    if len(ingredients) != 1:
        return None
    ((ingredient_rxcui, ingredient_name),) = ingredients.items()
    return Ingredient(rxcui=ingredient_rxcui, name=ingredient_name)


# Salt, form and release words name no ingredient and appear across unrelated drugs
# ("metformin hydrochloride", "hydralazine hydrochloride"), so they never make a match.
_NON_INGREDIENT_WORDS = frozenset(
    """tablet tablets tableta tabletas capsule capsules capsula capsulas cápsula cápsulas
    oral solution solución injection inyección extended release delayed liberación
    prolongada retardada hydrochloride clorhidrato sodium sódico sodica sódica potassium
    potásico potasica potásica calcium calcio magnesium magnesio sulfate sulfato succinate
    succinato tartrate tartrato maleate maleato besylate besilato mesylate mesilato
    citrate citrato acetate acetato phosphate fosfato chloride cloruro medicine medicina
    medicamento medication drug pill pills pastilla pastillas""".split()
)


def _words(text: str) -> set[str]:
    words = re.findall(r"[^\W\d_]{4,}", text.casefold())
    return {word for word in words if word not in _NON_INGREDIENT_WORDS}


def names_match(query: str, candidate_names: list[str]) -> bool:
    """True when a meaningful word asked about is (nearly) a word of a candidate name.

    Similar enough for "metformina"/"metformin" and a transposed letter; not for
    "losartan"/"valsartan" or "hydration"/"hydrate".
    """
    asked = _words(query)
    found = set().union(*(_words(name) for name in candidate_names)) if candidate_names else set()
    return any(
        difflib.SequenceMatcher(None, left, right).ratio() >= NAME_SIMILARITY
        for left in asked
        for right in found
    )


@_shape_checked
async def medlineplus_medication(
    client: httpx.AsyncClient, rxcui: str, locale: str
) -> SourceText | None:
    """The MedlinePlus drug page summary for an RxNorm concept, in English or Spanish."""
    query: dict[str, Any] = {
        "mainSearchCriteria.v.cs": RXNORM_SYSTEM,
        "mainSearchCriteria.v.c": rxcui,
        "knowledgeResponseType": "application/json",
        "informationRecipient.languageCode.c": "es" if locale == "es-MX" else "en",
    }
    response = await _get(client, MEDLINEPLUS_CONNECT, **query)
    entries = response.json().get("feed", {}).get("entry") or []
    # The drug's own page comes first; later entries are broader topics.
    for entry in entries:
        links = entry.get("link") or [{}]
        url = _strip_tracking(str(links[0].get("href") or ""))
        summary = plain_text(str(entry.get("summary", {}).get("_value") or ""))
        title = str(entry.get("title", {}).get("_value") or "").strip()
        if title and summary:
            return SourceText(title=title, url=url or None, summary=summary[:SUMMARY_LIMIT])
    return None


@_shape_checked
async def medlineplus_condition(
    client: httpx.AsyncClient, name: str, locale: str
) -> SourceText | None:
    """The MedlinePlus health topic for a condition name, in English or Spanish.

    The name is looked up in the English topic index first and, when nothing there
    matches, in the Spanish index, because records can hold either language. The other
    language's page is then MedlinePlus's own twin of the topic found (``/<slug>.html`` and
    ``/spanish/<slug>.html``), read from that language's index; it is never a translation.
    No twin is a miss: English text is never returned as the Spanish topic.
    """
    wanted = "es-MX" if locale == "es-MX" else "en-US"
    found_in = "en-US"
    topic = await _matching_topic(client, name, found_in)
    if topic is None:
        found_in = "es-MX"
        topic = await _matching_topic(client, name, found_in)
    if topic is not None and found_in != wanted:
        topic = await _twin_topic(client, topic, wanted)
    if topic is None:
        return None
    return SourceText(title=topic.title, url=topic.url, summary=topic.summary[:SUMMARY_LIMIT])


@dataclass(frozen=True)
class _Topic:
    """One health topic from a MedlinePlus search result."""

    rank: int
    url: str
    slug: str
    title: str
    alt_titles: tuple[str, ...]
    summary: str


async def _search_topics(client: httpx.AsyncClient, locale: str, term: str) -> list[_Topic]:
    """Up to ``TOPIC_SEARCH_HITS`` topics of one language's index, best ranked first."""
    response = await _get(
        client,
        MEDLINEPLUS_SEARCH,
        db=_TOPIC_DATABASES[locale],
        term=term,
        retmax=TOPIC_SEARCH_HITS,
    )
    root = ElementTree.fromstring(response.content)
    topics: list[_Topic] = []
    for position, document in enumerate(root.findall("./list/document")):
        address = _TOPIC_URL.fullmatch(document.get("url") or "")
        # A page outside this language's topic path is not a topic of this index.
        if address is None or bool(address[1]) != (locale == "es-MX"):
            continue
        fields: dict[str, list[str]] = {}
        for content in document.findall("content"):
            key = content.get("name") or ""
            if key:
                fields.setdefault(key, []).append(plain_text(content.text or ""))
        title = next(iter(fields.get("title", [])), "").strip()
        summary = next(iter(fields.get("FullSummary", [])), "").strip()
        if not title or not summary:
            continue
        rank = document.get("rank") or ""
        topics.append(
            _Topic(
                rank=int(rank) if rank.isdigit() else position,
                url=address[0],
                slug=address[2],
                title=title,
                alt_titles=tuple(alt for alt in fields.get("altTitle", []) if alt),
                summary=summary,
            )
        )
    return sorted(topics, key=lambda topic: topic.rank)


async def _matching_topic(client: httpx.AsyncClient, name: str, locale: str) -> _Topic | None:
    """The topic of one index that best matches a name, retrying once without qualifiers.

    The index requires every word, so "mild persistent asthma" finds nothing and
    "episodic migraine" finds only "Pain"; the retry asks for "asthma" and "migraine". It
    runs only when the name as written has no acceptable general topic.
    """
    topic, general = best_topic(await _search_topics(client, locale, name), name)
    if general:
        return topic
    simpler = without_qualifiers(name)
    if simpler and simpler.casefold() != " ".join(name.casefold().split()):
        retry, retry_general = best_topic(await _search_topics(client, locale, simpler), simpler)
        if retry is not None and (retry_general or topic is None):
            return retry
    return topic


async def _twin_topic(client: httpx.AsyncClient, topic: _Topic, locale: str) -> _Topic | None:
    """The same topic's page in the other language, read from that language's index.

    The index is searched with the topic's own title, and then with the twin page's title
    (read from the page head only), and a result counts only when its URL is the twin's.
    """
    url = f"{MEDLINEPLUS}{_TOPIC_PATHS[locale]}{topic.slug}.html"
    twin = await _topic_at(client, locale, topic.title, url)
    if twin is None:
        title = await _page_title(client, url)
        if title and title != topic.title:
            twin = await _topic_at(client, locale, title, url)
    return twin


async def _topic_at(client: httpx.AsyncClient, locale: str, term: str, url: str) -> _Topic | None:
    found = await _search_topics(client, locale, term)
    return next((topic for topic in found if topic.url == url), None)


async def _page_title(client: httpx.AsyncClient, url: str) -> str | None:
    """A topic page's own name, from its ``<title>``: "Eccema | Dermatitis | ..." -> "Eccema".

    Only the head of the page is requested; its body text is never used. A page that does
    not exist is a miss, not an outage.
    """
    try:
        response = await _get(client, url, headers={"Range": f"bytes=0-{PAGE_HEAD_BYTES - 1}"})
    except SourceUnavailableError as error:
        cause = error.__cause__
        if isinstance(cause, httpx.HTTPStatusError) and cause.response.status_code == 404:
            return None
        raise
    found = _PAGE_TITLE.search(response.text)
    if found is None:
        return None
    title = re.split(r"\s+\|\s+|:", html.unescape(found[1]), maxsplit=1)[0]
    return " ".join(title.split()) or None


def without_qualifiers(name: str) -> str:
    """A condition name without its severity, course, side and body-site qualifiers."""
    text = _BODY_SITE.sub(" ", name)
    words = (word for word in text.split() if _unaccented(word).strip(",.;") not in _QUALIFIERS)
    return " ".join(words)


def best_topic(topics: list[_Topic], name: str) -> tuple[_Topic | None, bool]:
    """The best acceptable topic for a name, and whether it is a general topic.

    A topic is acceptable when its title or an alternate title is the name itself, holds
    every meaningful word of it, or is a broader topic named within it that covers at
    least half of its words ("Cholesterol" for "high cholesterol"). A topic sharing only
    a word ("Knee Replacement" for "osteoarthritis of the knee", "Diabetes" for "diabetes
    tipo 2") is never accepted, so a loosely related topic is never cached under the name.
    Among acceptable topics a general one wins over one for a narrower audience or a
    how-to ("High Blood Pressure" over "How to Prevent High Blood Pressure").
    """
    asked = set(_terms(name))
    scored = [(key, topic) for topic in topics if (key := _topic_key(topic, asked))[0]]
    if not scored:
        return None, False
    key, topic = max(scored, key=lambda pair: pair[0])
    return topic, key[1]


def _topic_key(topic: _Topic, asked: set[str]) -> tuple[bool, bool, int, int, int, bool, int]:
    labels = [topic.title, *topic.alt_titles]
    tier, covered, is_title = max(
        (*_label_match(asked, label), index == 0) for index, label in enumerate(labels)
    )
    words = {word for label in labels for word in _terms(label)}
    union = sum(1 for want in asked if any(_same_word(want, word) for word in words))
    narrow = bool((set(_terms(topic.title)) & _NARROWING) - asked)
    return (tier >= 2, not narrow, tier, covered, union, is_title, -topic.rank)


def _label_match(asked: set[str], label: str) -> tuple[int, int]:
    """How well one title names what was asked: a tier from 0 to 4, and words covered.

    4 the same words; 3 every asked word; 2 a broader label naming at least half of what
    was asked; 1 some shared word; 0 nothing.
    """
    words = set(_terms(label))
    covered = {want for want in asked if any(_same_word(want, word) for word in words)}
    if not covered:
        return 0, 0
    used = {word for word in words if any(_same_word(want, word) for want in asked)}
    if covered == asked:
        return (4 if used == words else 3), len(covered)
    if used == words and 2 * len(covered) >= len(asked):
        return 2, len(covered)
    return 1, len(covered)


def _terms(text: str) -> list[str]:
    """Lower-case, unaccented words of a name, without joining words such as "of" or "de"."""
    return [word for word in re.findall(r"[^\W_]+", _unaccented(text)) if word not in _FILLER]


def _unaccented(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _same_word(left: str, right: str) -> bool:
    """Equal, or nearly so for longer words ("anemia"/"anaemia"); numbers must be equal."""
    if left == right:
        return True
    if left.isdigit() or right.isdigit() or min(len(left), len(right)) < 4:
        return False
    return difflib.SequenceMatcher(None, left, right).ratio() >= NAME_SIMILARITY


@_shape_checked
async def dailymed_label(client: httpx.AsyncClient, ingredient: Ingredient) -> SourceText | None:
    """The newest single-ingredient FDA label for an ingredient, as plain sections."""
    listing = await _get(client, f"{DAILYMED}/spls.json", rxcui=ingredient.rxcui, pagesize=50)
    rows = listing.json().get("data") or []
    choice = _choose_label(rows, ingredient.name)
    if choice is None:
        return None
    setid = str(choice["setid"])
    document = await _get(client, f"{DAILYMED}/spls/{setid}.xml")
    root = ElementTree.fromstring(document.content)
    sections = label_sections(root)
    if not sections:
        return None
    return SourceText(
        title=str(choice.get("title") or ingredient.name).strip()[:300],
        url=f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}",
        sections=sections,
        version=str(choice.get("spl_version") or "") or None,
        updated_on=_published_on(str(choice.get("published_date") or "")),
    )


def _choose_label(rows: list[dict[str, Any]], ingredient: str) -> dict[str, Any] | None:
    """Prefer a label for the ingredient alone; DailyMed lists combinations too."""
    wanted = ingredient.upper()
    # DailyMed lists the most recently published first.
    single = [
        row
        for row in rows
        if row.get("setid")
        and wanted in str(row.get("title") or "").upper()
        and " AND " not in str(row.get("title") or "").upper()
    ]
    tablets = [row for row in single if " TABLET" in str(row.get("title") or "").upper()]
    candidates = tablets or single
    return candidates[0] if candidates else None


def label_sections(root: ElementTree.Element) -> dict[str, str]:
    """Plain text of the label sections Nora may cite, keyed by ``LABEL_SECTIONS``."""
    by_code = {code: key for key, codes in LABEL_SECTIONS.items() for code in codes}
    sections: dict[str, str] = {}
    for section in root.iter("{urn:hl7-org:v3}section"):
        code = section.find("h:code", _HL7)
        key = by_code.get(code.get("code", "") if code is not None else "")
        if key is None or key in sections:
            continue
        title = section.find("h:title", _HL7)
        parts = [
            " ".join(" ".join(child.itertext()).split())
            for child in section
            if child is not title and child.tag != "{urn:hl7-org:v3}code"
        ]
        text = "\n".join(part for part in parts if part)
        if text:
            sections[key] = text[:SECTION_LIMIT]
    return sections


def _published_on(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%b %d, %Y").date()
    except ValueError:
        return None


def _strip_tracking(url: str) -> str:
    return url.split("?utm_source", 1)[0]


Fetched = SourceText | None | SourceUnavailableError
"""A found text, a genuine miss, or a source that did not answer."""


async def gather_medication(
    client: httpx.AsyncClient, ingredient: Ingredient
) -> dict[tuple[str, str], Fetched]:
    """Every source for one ingredient, fetched together: ``(source, locale) -> result``."""
    results = await asyncio.gather(
        medlineplus_medication(client, ingredient.rxcui, "en-US"),
        medlineplus_medication(client, ingredient.rxcui, "es-MX"),
        dailymed_label(client, ingredient),
        return_exceptions=True,
    )
    keys = (("medlineplus", "en-US"), ("medlineplus", "es-MX"), ("dailymed", "en-US"))
    fetched: dict[tuple[str, str], Fetched] = {}
    for key, result in zip(keys, results, strict=True):
        if isinstance(result, BaseException) and not isinstance(result, SourceUnavailableError):
            raise result
        fetched[key] = result
    return fetched
