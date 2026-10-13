"""The sources a chat turn actually used, recorded by the tools that returned them.

The citation the patient reads is written by the server, never by the model. Every tool
that returns something an answer can rest on (a reference page, a label, one of the
patient's own documents) records it here, and the runtime reads this turn's record from
the event's state delta when it writes the reply's source line.

A document citation names the document by its record title and file name, both already
shown to the patient in Records, and the pages of the extracted items the tool returned.
It never carries anything the patient cannot already see.
"""

from __future__ import annotations

import unicodedata
from typing import Any

TURN_SOURCES_STATE_KEY = "knowledge_sources"
"""Sources used in the current turn, tagged with its invocation so an earlier turn's are
never read as this turn's. A plain key because ``temp:`` keys never appear in an event's
state delta, which is where the runtime reads them."""

DOCUMENT_SOURCE = "document"


def fold(text: str) -> str:
    """Case- and accent-insensitive text, so "hidratación" finds "Hidratacion"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _one_line(value: Any) -> str:
    return " ".join(str(value or "").split())


def document_citation(
    document: dict[str, Any], *, items: list[dict[str, Any]] | None = None, selected: bool
) -> dict[str, Any] | None:
    """A citation for one of the patient's documents, or None without a file name.

    ``document`` is a row or the server-selected context: ``id``, ``file_name`` and
    ``display_title`` (the LOC-001 record titles by locale). ``items`` are the extracted
    items a tool returned; only reviewed or pending ones are ever returned, and an item
    with any other status is ignored here too. ``selected`` says whether this is the
    document the conversation is focused on, rather than a search result.
    """
    file_name = _one_line(document.get("file_name"))
    if not file_name:
        return None
    raw_titles = document.get("display_title")
    titles = raw_titles if isinstance(raw_titles, dict) else {}
    pages: list[dict[str, Any]] = []
    for item in items or []:
        page = item.get("page")
        if item.get("review_status") not in _CITABLE_STATUSES:
            continue
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            continue
        details = item.get("details")
        name = _one_line(details.get("name")) if isinstance(details, dict) else ""
        entry = {"page": page, "name": name}
        if entry not in pages:
            pages.append(entry)
    return {
        "source": DOCUMENT_SOURCE,
        "document_id": str(document.get("id") or ""),
        "file_name": file_name,
        "title": {
            locale: _one_line(titles.get(locale))
            for locale in ("en-US", "es-MX")
            if _one_line(titles.get(locale))
        },
        "pages": pages,
        "selected": selected,
    }


# The review statuses a document tool returns to the model (see ``patient_records``);
# rejected and deleted items never reach it, and never reach a citation.
_CITABLE_STATUSES = frozenset({"confirmed by the care team", "not yet reviewed by the care team"})


def record_turn_sources(tool_context: Any, used: list[dict[str, Any]]) -> None:
    """Add sources to this invocation's record; the same document is merged, not repeated."""
    state = getattr(tool_context, "state", None)
    if state is None or not used:
        return
    invocation = str(getattr(tool_context, "invocation_id", "") or "")
    current = state.get(TURN_SOURCES_STATE_KEY)
    sources: list[dict[str, Any]] = []
    if isinstance(current, dict) and current.get("invocation") == invocation:
        sources = [dict(item) for item in current.get("sources") or [] if isinstance(item, dict)]
    for item in used:
        same = next(
            (
                existing
                for existing in sources
                if item.get("source") == DOCUMENT_SOURCE
                and existing.get("source") == DOCUMENT_SOURCE
                and existing.get("document_id") == item.get("document_id")
                and existing.get("file_name") == item.get("file_name")
            ),
            None,
        )
        if same is not None:
            pages = list(same.get("pages") or [])
            pages.extend(page for page in item.get("pages") or [] if page not in pages)
            same.update(
                pages=pages,
                selected=bool(same.get("selected")) or bool(item.get("selected")),
                title=same.get("title") or item.get("title") or {},
            )
        elif item not in sources:
            sources.append(item)
    state[TURN_SOURCES_STATE_KEY] = {"invocation": invocation, "sources": sources}
