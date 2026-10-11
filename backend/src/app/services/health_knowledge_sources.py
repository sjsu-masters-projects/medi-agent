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
import hashlib
import html
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)

RXNAV = "https://rxnav.nlm.nih.gov/REST"
DAILYMED = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
MEDLINEPLUS_CONNECT = "https://connect.medlineplus.gov/service"
MEDLINEPLUS_SEARCH = "https://wsearch.nlm.nih.gov/ws/query"
RXNORM_SYSTEM = "2.16.840.1.113883.6.88"
REQUEST_TIMEOUT = httpx.Timeout(6.0, connect=3.0)

SUMMARY_LIMIT = 6000
SECTION_LIMIT = 6000

# FDA label sections by LOINC code. Dosage is deliberately absent: a label's dose ranges
# are not this patient's prescription, and Nora must never present them as one.
LABEL_SECTIONS: dict[str, tuple[str, ...]] = {
    "boxed_warning": ("34066-1",),
    "indications": ("34067-9",),
    "contraindications": ("34070-3",),
    "warnings": ("43685-7", "34071-1"),
    "adverse_reactions": ("34084-4",),
    "drug_interactions": ("34073-7",),
    "patient_counseling": ("34076-0", "88436-1"),
    "patient_information": ("42230-3",),
}
_HL7 = {"h": "urn:hl7-org:v3"}
_TAG = re.compile(r"<[^>]+>")
_BLOCK_END = re.compile(r"</?(?:p|h[1-6]|li|ul|ol|div)\b[^>]*>|<br\s*/?>", re.I)


class SourceUnavailableError(RuntimeError):
    """A reference service did not answer; try again later rather than record a miss."""


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


async def _get(client: httpx.AsyncClient, url: str, **params: Any) -> httpx.Response:
    host = httpx.URL(url).host
    try:
        response = await client.get(url, params=params or None, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response
    except httpx.HTTPError as error:
        # Only the host is logged: the query is a drug or condition name, never patient
        # data, but a log line has no reason to carry it.
        logger.warning("Reference source request failed: %s %s", host, type(error).__name__)
        raise SourceUnavailableError(host) from error


async def resolve_ingredient(client: httpx.AsyncClient, name: str) -> Ingredient | None:
    """Resolve a name as written ("Metformina 500 mg", "Tylenol") to its RxNorm ingredient."""
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
    for group in related.json().get("relatedGroup", {}).get("conceptGroup") or []:
        for concept in group.get("conceptProperties") or []:
            if concept.get("rxcui") and concept.get("name"):
                return Ingredient(rxcui=str(concept["rxcui"]), name=str(concept["name"]))
    return None


_UNIT_WORDS = {"tablet", "tablets", "tableta", "tabletas", "capsule", "capsula", "oral"}


def _words(text: str) -> set[str]:
    words = re.findall(r"[^\W\d_]{4,}", text.casefold())
    return {word for word in words if word not in _UNIT_WORDS}


def names_match(query: str, candidate_names: list[str]) -> bool:
    asked = _words(query)
    found = set().union(*(_words(name) for name in candidate_names)) if candidate_names else set()
    return any(
        difflib.SequenceMatcher(None, left, right).ratio() >= 0.8
        for left in asked
        for right in found
    )


async def medlineplus_medication(
    client: httpx.AsyncClient, rxcui: str, locale: str
) -> SourceText | None:
    """The MedlinePlus drug page summary for an RxNorm concept, in English or Spanish."""
    response = await _get(
        client,
        MEDLINEPLUS_CONNECT,
        **{
            "mainSearchCriteria.v.cs": RXNORM_SYSTEM,
            "mainSearchCriteria.v.c": rxcui,
            "knowledgeResponseType": "application/json",
            "informationRecipient.languageCode.c": "es" if locale == "es-MX" else "en",
        },
    )
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


async def medlineplus_condition(
    client: httpx.AsyncClient, name: str, locale: str
) -> SourceText | None:
    """The best-matching MedlinePlus health topic for a condition name."""
    database = "healthTopicsSpanish" if locale == "es-MX" else "healthTopics"
    response = await _get(client, MEDLINEPLUS_SEARCH, db=database, term=name, retmax=1)
    try:
        root = ElementTree.fromstring(response.content)
    except ElementTree.ParseError:
        return None
    document = root.find("./list/document")
    if document is None:
        return None
    fields: dict[str, str] = {}
    for content in document.findall("content"):
        key = content.get("name") or ""
        if key and key not in fields:
            fields[key] = plain_text(content.text or "")
    title = fields.get("title", "").strip()
    summary = fields.get("FullSummary", "").strip()
    if not title or not summary:
        return None
    return SourceText(title=title, url=document.get("url"), summary=summary[:SUMMARY_LIMIT])


async def dailymed_label(client: httpx.AsyncClient, ingredient: Ingredient) -> SourceText | None:
    """The newest single-ingredient FDA label for an ingredient, as plain sections."""
    listing = await _get(client, f"{DAILYMED}/spls.json", rxcui=ingredient.rxcui, pagesize=50)
    rows = listing.json().get("data") or []
    choice = _choose_label(rows, ingredient.name)
    if choice is None:
        return None
    setid = str(choice["setid"])
    document = await _get(client, f"{DAILYMED}/spls/{setid}.xml")
    try:
        root = ElementTree.fromstring(document.content)
    except ElementTree.ParseError:
        return None
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
