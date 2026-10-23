"""The structured evidence one assistant reply used, shaped for storage.

Everything here comes from what the grounding layer already produced during the turn: the
tools the model called, the sources those tools recorded (reference pages, labels and the
patient's own documents with pages) as narrowed by ``cited_sources``, and the care plan ids
that came back with the patient's record. Nothing is read from the reply text and nothing
is added by the model.

Each value is rebuilt field by field rather than copied, so a stored row can never carry
more than these fields: no reply text, no extracted values, no patient name. Counts and
lengths are bounded so one reply cannot grow a row without limit.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from app.adk.tools.turn_sources import DOCUMENT_SOURCE

EVIDENCE_VERSION = 1
MAX_TOOLS = 12
MAX_SOURCES = 12
MAX_PAGES = 30
MAX_PLAN_IDS = 10
RECORD_TOOL = "get_patient_context"

_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_LOCALES = ("en-US", "es-MX")


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _uuid(value: Any) -> str | None:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def tool_names_of(event: Any) -> list[str]:
    """Names of the tools an event called."""
    calls = event.get_function_calls() if hasattr(event, "get_function_calls") else []
    return [
        str(call.name)
        for call in calls or []
        if isinstance(getattr(call, "name", None), str) and _TOOL_NAME.match(call.name)
    ]


def care_plan_ids_of(event: Any) -> list[str]:
    """Care plan ids in the patient-record tool's results (the plan a medication came from)."""
    responses = event.get_function_responses() if hasattr(event, "get_function_responses") else []
    found: list[str] = []
    for item in responses or []:
        if getattr(item, "name", None) == RECORD_TOOL:
            _collect_plan_ids(getattr(item, "response", None), found, depth=0)
    return found


def _collect_plan_ids(node: Any, found: list[str], depth: int) -> None:
    if depth > 6:
        return
    if isinstance(node, dict):
        plan_id = _uuid(node.get("care_plan_id")) if node.get("care_plan_id") else None
        if plan_id and plan_id not in found:
            found.append(plan_id)
        for value in node.values():
            if isinstance(value, dict | list):
                _collect_plan_ids(value, found, depth + 1)
    elif isinstance(node, list):
        for value in node:
            _collect_plan_ids(value, found, depth + 1)


def _document(item: dict[str, Any]) -> dict[str, Any] | None:
    document_id = _uuid(item.get("document_id"))
    file_name = _text(item.get("file_name"), 200)
    if not document_id or not file_name:
        return None
    raw_titles = item.get("title")
    titles = raw_titles if isinstance(raw_titles, dict) else {}
    pages = sorted(
        {
            page
            for page in item.get("pages") or []
            if isinstance(page, int) and not isinstance(page, bool) and 1 <= page <= 10000
        }
    )[:MAX_PAGES]
    return {
        "kind": "document",
        "document_id": document_id,
        "file_name": file_name,
        "title": {loc: _text(titles[loc], 200) for loc in _LOCALES if _text(titles.get(loc), 200)},
        "pages": pages,
        "selected": bool(item.get("selected")),
    }


def _reference(item: dict[str, Any]) -> dict[str, Any] | None:
    source = _text(item.get("source"), 60)
    if not source:
        return None
    url = _text(item.get("url"), 300)
    entry: dict[str, Any] = {
        "kind": "reference",
        "source": source,
        "title": _text(item.get("title"), 200),
        "url": url if url.startswith("https://") else "",
        "language": item.get("language") if item.get("language") in _LOCALES else None,
        "checked_on": _text(item.get("checked_on"), 10) or None,
        "published_on": _text(item.get("published_on"), 10) or None,
    }
    if item.get("label_version"):
        entry["label_version"] = _text(item.get("label_version"), 60)
    return entry


def evidence_is_shown(evidence: Any) -> bool:
    """Whether a stored evidence object has anything the patient's Sources line lists."""
    if not isinstance(evidence, dict):
        return False
    return bool(evidence.get("sources")) or RECORD_TOOL in (evidence.get("tools") or [])


def build_evidence(
    *, tools: list[str], cited: list[dict[str, Any]], care_plan_ids: list[str]
) -> dict[str, Any]:
    """The bounded evidence object for one reply (empty lists when it used nothing)."""
    sources: list[dict[str, Any]] = []
    for item in cited:
        built = _document(item) if item.get("source") == DOCUMENT_SOURCE else _reference(item)
        if built and built not in sources:
            sources.append(built)
    return {
        "version": EVIDENCE_VERSION,
        "tools": list(dict.fromkeys(tools))[:MAX_TOOLS],
        "sources": sources[:MAX_SOURCES],
        "care_plan_ids": list(dict.fromkeys(care_plan_ids))[:MAX_PLAN_IDS],
    }
