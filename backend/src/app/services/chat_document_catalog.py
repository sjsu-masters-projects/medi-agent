"""Deterministic, patient-facing replies for document-catalog questions.

Document availability is a portal fact, not a clinical inference.  Answering a clear
catalog question without a model keeps the response aligned with the Documents screen
and avoids sending file metadata to a provider that does not need it.
"""

from __future__ import annotations

import re
from typing import Any

from app.models.enums import Language

_CATALOG_PATTERNS = (
    re.compile(
        r"\b(?:what|which)\s+(?:documents?|docs?|records?|files?)\s+"
        r"(?:do|can|will)?\s*(?:you|i)?\s*(?:have|see|access)\b"
    ),
    re.compile(r"\b(?:list|show)\s+(?:me\s+)?(?:my\s+)?(?:documents?|docs?|records?|files?)\b"),
    re.compile(
        r"\b(?:my\s+)?(?:documents?|docs?|records?|files?)\s+"
        r"(?:available|in\s+(?:my\s+)?(?:portal|account))\b"
    ),
    re.compile(
        r"\b(?:qué|que|cuáles|cuales)\s+(?:documentos?|archivos?|registros?|expediente)\s+"
        r"(?:tengo|tienes|puedo\s+ver)\b"
    ),
    re.compile(
        r"\b(?:lista|muestra)\s+(?:me\s+)?(?:mis\s+)?"
        r"(?:documentos?|archivos?|registros?|expediente)\b"
    ),
    re.compile(r"\b(?:mis\s+)?(?:documentos?|archivos?|registros?|expediente)\s+disponibles\b"),
)


def is_document_catalog_question(message: str) -> bool:
    """Return whether a message clearly asks which portal documents are available."""
    normalized = " ".join(message.casefold().split())
    return any(pattern.search(normalized) for pattern in _CATALOG_PATTERNS)


def build_document_catalog_reply(documents: list[dict[str, Any]], language: Language) -> str:
    """Build a concise reply from metadata already authorized for this patient."""
    if not documents:
        return _empty_catalog_reply(language)

    document_lines = "\n".join(
        f"• {_document_name(document)} ({_document_type(document)})" for document in documents
    )
    return (
        _catalog_intro(len(documents), language)
        + "\n"
        + document_lines
        + "\n\n"
        + _catalog_footer(language)
    )


def _document_name(document: dict[str, Any]) -> str:
    name = " ".join(str(document.get("file_name") or "").split())
    return name or "Untitled document"


def _document_type(document: dict[str, Any]) -> str:
    raw_type = " ".join(str(document.get("document_type") or "other").replace("_", " ").split())
    return raw_type.capitalize()


def _catalog_intro(count: int, language: Language) -> str:
    if language is Language.ES:
        return f"Puedo ver {count} documento{'s' if count != 1 else ''} disponible{'s' if count != 1 else ''} para ti en MediAgent:"
    return f"I can see {count} document{'s' if count != 1 else ''} available to you in MediAgent:"


def _catalog_footer(language: Language) -> str:
    if language is Language.ES:
        return "Puedes abrir cualquiera desde la pestaña Documentos. Esta lista incluye los documentos guardados en MediAgent; puede que tu clínica tenga otros registros fuera del portal."
    return "You can open any of these from the Documents tab. This list covers documents stored in MediAgent; your clinic may have other records outside the portal."


def _empty_catalog_reply(language: Language) -> str:
    if language is Language.ES:
        return "No veo documentos disponibles para ti en MediAgent todavía. Puedes revisar la pestaña Documentos o subir uno desde allí."
    return "I do not see any documents available to you in MediAgent yet. You can check the Documents tab or upload one there."
