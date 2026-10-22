"""Server-side checks on a reply that used reference sources or the patient's documents.

The model is told which sources it was given, but the citation the patient reads is not
left to it: the source line is written here from the tool results the turn actually
produced, and a source line the model wrote itself is removed. A reply that mentions a
dose the patient record and the sources do not contain is counted, so the check can be
measured before it is allowed to block anything.

A document is cited by its record title and file name, with the pages of the items the
tool returned. The reply narrows that and never widens it: when it names some of the
search results or some of the items, only those are cited; when it names none, every
document and page the tools returned is cited rather than none.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.adk.tools.turn_sources import DOCUMENT_SOURCE, TURN_SOURCES_STATE_KEY, fold
from app.services.health_knowledge_sources import DOSE

_SOURCE_LINE = re.compile(r"^\s*(?:\*\*)?(?:sources?|fuentes?)\s*:.*$", re.I | re.M)
_DOSE = DOSE
_MONTHS_ES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
_LABELS = {
    "en-US": {
        "lead": "Source",
        "leads": "Sources",
        "page": "page",
        "pages": "pages",
        "and": "and",
        "medlineplus": "MedlinePlus: {title} (checked {checked})",
        "dailymed": "DailyMed, FDA drug label (published {published})",
    },
    "es-MX": {
        "lead": "Fuente",
        "leads": "Fuentes",
        "page": "página",
        "pages": "páginas",
        "and": "y",
        "medlineplus": "MedlinePlus{english}: {title} (consultado el {checked})",
        "dailymed": "DailyMed, etiqueta de la FDA en inglés (publicada el {published})",
    },
}
# A word long enough to name an item: "metformin", never "500" or "mg".
_NAME_WORD = re.compile(r"[^\W\d_]{5,}")
_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,5}$")


def sources_from_event(event: Any) -> list[dict[str, Any]] | None:
    """This invocation's recorded sources, if this event's state delta carries them."""
    actions = getattr(event, "actions", None)
    delta = getattr(actions, "state_delta", None) if actions else None
    value = delta.get(TURN_SOURCES_STATE_KEY) if delta else None
    if not isinstance(value, dict):
        return None
    if value.get("invocation") != getattr(event, "invocation_id", None):
        return None
    sources = value.get("sources")
    return (
        [item for item in sources if isinstance(item, dict)] if isinstance(sources, list) else None
    )


def _day(value: str | None, locale: str) -> str:
    if not value:
        return "—"
    day = date.fromisoformat(value[:10])
    if locale == "es-MX":
        return f"{day.day} {_MONTHS_ES[day.month - 1]} {day.year}"
    return f"{day:%b} {day.day}, {day.year}"


def _folded(text: str) -> str:
    return " ".join(fold(text).split())


def _titles(item: dict[str, Any]) -> dict[str, Any]:
    titles = item.get("title")
    return titles if isinstance(titles, dict) else {}


def _names_item(folded_reply: str, name: str) -> bool:
    """Whether the reply names an item by one of its longer words, so "metformina"
    counts for "Metformin HCl 500 mg" and a dose or unit never does."""
    return any(word in folded_reply for word in _NAME_WORD.findall(fold(name)))


def _names_document(folded_reply: str, item: dict[str, Any]) -> bool:
    stem = _EXTENSION.sub("", str(item.get("file_name") or ""))
    names = [_folded(str(text)) for text in [*_titles(item).values(), stem]]
    return any(name and name in folded_reply for name in names)


def cited_sources(sources: list[dict[str, Any]], reply: str) -> list[dict[str, Any]]:
    """The sources to cite for this reply, with each document's pages as page numbers.

    Reference sources are kept as recorded. Documents found by a search are narrowed to
    the ones the reply names, and a document's pages to the items the reply names; when
    the reply names none, all of them are kept, so a grounded answer is never uncited.
    """
    folded_reply = _folded(reply)
    searched = [
        item
        for item in sources
        if item.get("source") == DOCUMENT_SOURCE and not item.get("selected")
    ]
    named = [item for item in searched if _names_document(folded_reply, item)]
    cited: list[dict[str, Any]] = []
    for item in sources:
        if item.get("source") != DOCUMENT_SOURCE:
            cited.append(item)
            continue
        if named and item in searched and item not in named:
            continue
        entries = [entry for entry in item.get("pages") or [] if isinstance(entry, dict)]
        mentioned = [
            entry for entry in entries if _names_item(folded_reply, str(entry.get("name") or ""))
        ]
        pages = sorted({int(entry["page"]) for entry in mentioned or entries})
        cited.append({**item, "pages": pages})
    return cited


def _page_list(pages: list[int], labels: dict[str, str]) -> str:
    numbers = [str(page) for page in pages]
    if len(numbers) == 1:
        return f"{labels['page']} {numbers[0]}"
    return f"{labels['pages']} {', '.join(numbers[:-1])} {labels['and']} {numbers[-1]}"


def _document_part(item: dict[str, Any], locale: str, labels: dict[str, str]) -> str:
    """ "Metformin prescription (order.pdf), page 1", or the file name without a title."""
    file_name = str(item.get("file_name") or "").strip()
    if not file_name:
        return ""
    title = str(_titles(item).get(locale) or "").strip()
    named = f"{title} ({file_name})" if title and title != file_name else file_name
    pages = [page for page in item.get("pages") or [] if isinstance(page, int)]
    return f"{named}, {_page_list(pages, labels)}" if pages else named


def source_line(sources: list[dict[str, Any]], locale: str) -> str:
    """One line naming each distinct source used, in the reply's language.

    Document sources go through ``cited_sources`` first, which turns their items into
    page numbers.
    """
    locale = "es-MX" if locale == "es-MX" else "en-US"
    labels = _LABELS[locale]
    parts: list[str] = []
    for item in sources:
        if item.get("source") == DOCUMENT_SOURCE:
            part = _document_part(item, locale, labels)
        else:
            template = labels.get(str(item.get("source")))
            if template is None:
                continue
            english = locale == "es-MX" and item.get("language") == "en-US"
            part = template.format(
                english=" (en inglés)" if english else "",
                title=str(item.get("title") or "").strip() or "—",
                checked=_day(item.get("checked_on"), locale),
                published=_day(item.get("published_on") or item.get("checked_on"), locale),
            )
        if part and part not in parts:
            parts.append(part)
    if not parts:
        return ""
    return f"{labels['lead'] if len(parts) == 1 else labels['leads']}: " + "; ".join(parts)


def without_source_lines(text: str) -> str:
    """Remove "Source(s):"/"Fuente(s):" lines: the server writes those, and speech skips
    them."""
    return re.sub(r"\n{3,}", "\n\n", _SOURCE_LINE.sub("", text)).strip()


def unsupported_doses(reply: str, *grounding: str) -> list[str]:
    """Dose-like amounts in a reply that appear in none of the grounding texts."""
    allowed = {_normal(match) for text in grounding for match in _DOSE.findall(text)}
    return [match for match in _DOSE.findall(reply) if _normal(match) not in allowed]


def _normal(dose: str) -> str:
    return re.sub(r"\s+", "", dose.casefold().replace(",", "."))


_EMPHASIS = re.compile(r"\*\*|__|`")
_BULLET = re.compile(r"^\s*[*-]\s+", re.M)
_HEADING = re.compile(r"^\s*#{1,6}\s*", re.M)


def plain_reply(text: str) -> str:
    """The chat shows plain text: drop Markdown emphasis and headings, keep bullets as •."""
    return _HEADING.sub("", _BULLET.sub("• ", _EMPHASIS.sub("", text)))


# The characters a Markdown marker is made of: two in a row are removed, so one at the end of
# the text so far may still become half of a pair.
_PAIR_CHARS = "*_"
_SOURCE_WORDS = ("source", "sources", "fuente", "fuentes")
_SOURCE_HEAD = re.compile(r"(?:\*\*)?(?:sources?|fuentes?)\s*:", re.I)
_BULLET_PENDING = re.compile(r"^\s*[*-]$")


def _line_head(head: str) -> str:
    """Whether a line's start (leading space removed, lower case) is a source line
    (``"source"``), could still become one (``"maybe"``) or cannot (``"text"``)."""
    if _SOURCE_HEAD.match(head):
        return "source"
    for prefix in ("", "**"):
        for word in _SOURCE_WORDS:
            target = prefix + word
            if target.startswith(head):
                return "maybe"
            if head.startswith(target) and not head[len(target) :].strip():
                return "maybe"
    return "text"


def _transform_line(line: str) -> str:
    return plain_reply(line)


class StreamingReplyFilter:
    """The patient-facing form of a reply, produced while it is still being written.

    ``feed`` returns only text that ``plain_reply(without_source_lines(reply))`` would also
    contain at that position: a line that is, or may still turn out to be, a source line is held
    back until it is known not to be one, Markdown marks are removed as in the final reply, and
    whitespace is released only when text follows it. So a draft, and anything spoken from it, is
    a prefix of the saved reply (apart from the source line the server appends afterwards) and
    never shows what the final cleanup would remove. The model's own source lines are dropped
    here, line by line, exactly as the final reply drops them.
    """

    def __init__(self) -> None:
        self._tail = ""  # the current, unfinished line (raw)
        self._emitted = 0  # characters of this line's cleaned text already released
        self._pending = ""  # newlines waiting for text to follow them
        self._started = False

    def _release(self, text: str) -> str:
        if not text:
            return ""
        lead = ""
        if self._started:
            newlines = self._pending.count("\n")
            lead = "\n" * min(newlines, 2)
        self._pending = ""
        self._started = True
        return lead + text

    def _line_text(self, line: str, *, complete: bool) -> str:
        """The cleaned text of this line that is safe to release now."""
        if _SOURCE_HEAD.match(line.lstrip().lower()):
            return ""
        if not complete:
            if _line_head(line.lstrip().lower()) != "text":
                return ""
            if _BULLET_PENDING.match(line):
                return ""
            line = line.rstrip(_PAIR_CHARS)
        return _transform_line(line).rstrip()

    def _drain(self, line: str, *, complete: bool) -> str:
        text = self._line_text(line, complete=complete)
        fresh = text[self._emitted :]
        if fresh:
            self._emitted = len(text)
        return self._release(fresh)

    def feed(self, delta: str) -> str:
        if not delta:
            return ""
        *lines, self._tail = (self._tail + delta).split("\n")
        out: list[str] = []
        for line in lines:
            out.append(self._drain(line, complete=True))
            self._pending += "\n"
            self._emitted = 0
        out.append(self._drain(self._tail, complete=False))
        return "".join(out)

    def finish(self) -> str:
        """The held end of the reply once it is complete."""
        tail, self._tail = self._tail, ""
        text = self._drain(tail, complete=True)
        self._emitted = 0
        return text
