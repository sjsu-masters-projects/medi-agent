"""Drug knowledge retrieval for medication-grounded chat responses."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, cast

from supabase import Client

from app.config import settings
from app.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)

Embedder = Callable[[str], Awaitable[list[float]]]

MEDICATION_RAG_KEYWORDS = frozenset(
    {
        "adverse reaction",
        "dose",
        "dosis",
        "drug",
        "efecto secundario",
        "medication",
        "medicament",
        "medicamento",
        "medicina",
        "medicine",
        "pastilla",
        "pill",
        "reaction",
        "reaccion",
        "reacción",
        "side effect",
    }
)

DAILYMED_LABEL_SECTIONS: tuple[tuple[str, str], ...] = (
    ("warnings", "Warnings"),
    ("adverse_reactions", "Adverse reactions"),
    ("indications", "Indications and usage"),
    ("dosage", "Dosage and administration"),
)


class GoogleEmbeddingClient:
    """Generate text embeddings using the Google Gen AI SDK."""

    def __init__(self) -> None:
        self._client: Any | None = None

    async def embed_text(self, text: str) -> list[float]:
        return await asyncio.to_thread(self._embed_text_sync, text)

    def _embed_text_sync(self, text: str) -> list[float]:
        if not settings.google_api_key and not settings.google_project_id:
            raise ExternalServiceError(
                "Google Embeddings", "GOOGLE_API_KEY or GOOGLE_PROJECT_ID is required"
            )

        client = self._get_client()
        genai_types = importlib.import_module("google.genai.types")
        config = genai_types.EmbedContentConfig(
            output_dimensionality=settings.rag_embedding_dimensions
        )
        response = client.models.embed_content(
            model=settings.google_embedding_model,
            contents=text,
            config=config,
        )
        embeddings = getattr(response, "embeddings", None) or []
        if not embeddings:
            raise ExternalServiceError("Google Embeddings", "empty embedding response")

        values = getattr(embeddings[0], "values", None)
        if not values:
            raise ExternalServiceError("Google Embeddings", "missing embedding values")

        return [float(value) for value in values]

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        genai = importlib.import_module("google.genai")
        if settings.google_project_id:
            self._client = genai.Client(
                vertexai=True,
                project=settings.google_project_id,
                location="global",
            )
        else:
            self._client = genai.Client(api_key=settings.google_api_key)
        return self._client


class DrugKnowledgeService:
    """Ingest and retrieve cited medication knowledge chunks."""

    def __init__(self, db: Client, embedder: Embedder | None = None) -> None:
        self.db = db
        self.embedder = embedder or GoogleEmbeddingClient().embed_text

    async def ingest_dailymed_label(
        self,
        label: Mapping[str, Any],
        *,
        drug_name: str,
        generic_name: str | None = None,
        rxcui: str | None = None,
    ) -> int:
        """Chunk, embed, and upsert a curated DailyMed label."""
        chunks = self.build_dailymed_label_chunks(
            label,
            drug_name=drug_name,
            generic_name=generic_name,
            rxcui=rxcui,
        )
        if not chunks:
            return 0

        rows: list[dict[str, Any]] = []
        for chunk in chunks:
            embedding = await self.embedder(str(chunk["chunk_text"]))
            rows.append({**chunk, "embedding": _format_vector(embedding)})

        result = await self._execute(
            self.db.table("drug_knowledge_chunks").upsert(
                rows,
                on_conflict="source,source_id,section,chunk_hash",
            )
        )
        return len([row for row in (result.data or []) if isinstance(row, dict)]) or len(rows)

    def build_dailymed_label_chunks(
        self,
        label: Mapping[str, Any],
        *,
        drug_name: str,
        generic_name: str | None = None,
        rxcui: str | None = None,
    ) -> list[dict[str, Any]]:
        source_id = str(label.get("setid") or rxcui or drug_name).strip()
        source_title = str(label.get("title") or f"{drug_name} drug label").strip()
        normalized_drug_name = drug_name.strip()
        if not normalized_drug_name or not source_id:
            return []

        resolved_generic = generic_name or _clean_optional_string(label.get("generic_name"))
        source_url = f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={source_id}"
        metadata = {
            "brand_name": _clean_optional_string(label.get("brand_name")),
            "manufacturer": _clean_optional_string(label.get("manufacturer")),
        }

        chunks: list[dict[str, Any]] = []
        for key, section in DAILYMED_LABEL_SECTIONS:
            section_text = _normalize_text(label.get(key))
            if len(section_text) < 20:
                continue
            for chunk_text in _chunk_text(section_text):
                chunks.append(
                    {
                        "drug_name": normalized_drug_name,
                        "generic_name": resolved_generic,
                        "rxcui": rxcui,
                        "source": "dailymed",
                        "source_id": source_id,
                        "source_title": source_title,
                        "source_url": source_url,
                        "section": section,
                        "chunk_text": chunk_text,
                        "chunk_hash": hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                        "metadata": metadata,
                    }
                )
        return chunks

    async def retrieve_for_patient_message(
        self,
        *,
        message: str,
        medications: Sequence[Mapping[str, Any]],
        match_count: int = 5,
    ) -> dict[str, Any]:
        """Retrieve cited medication chunks for a patient medication question."""
        if not should_retrieve_drug_knowledge(message, medications):
            return _empty_context("not_applicable")

        query_text = _build_query_text(message, medications)
        try:
            embedding = await self.embedder(query_text)
            result = await self._execute(
                self.db.rpc(
                    "match_drug_knowledge_chunks",
                    {
                        "query_embedding": _format_vector(embedding),
                        "p_match_count": match_count,
                        "p_drug_names": _medication_names(medications) or None,
                        "p_rxcuis": _medication_rxcuis(medications) or None,
                        "p_min_similarity": settings.rag_min_similarity,
                    },
                )
            )
        except Exception as exc:
            logger.warning("Drug knowledge retrieval failed; using safe fallback: %s", exc)
            return _empty_context("weak")

        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        if not rows:
            return _empty_context("weak")

        chunks = [_chunk_context(row, index) for index, row in enumerate(rows, start=1)]
        return {
            "status": "grounded",
            "query": message.strip(),
            "chunks": chunks,
            "citations": [_citation_context(chunk) for chunk in chunks],
        }

    async def _execute(self, query: Any) -> Any:
        return await asyncio.to_thread(query.execute)


def should_retrieve_drug_knowledge(
    message: str,
    medications: Sequence[Mapping[str, Any]],
) -> bool:
    normalized = message.lower()
    if any(keyword in normalized for keyword in MEDICATION_RAG_KEYWORDS):
        return True

    return any(name.lower() in normalized for name in _medication_names(medications))


def _empty_context(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "chunks": [],
        "citations": [],
    }


def _chunk_context(row: Mapping[str, Any], index: int) -> dict[str, Any]:
    return {
        "citation_id": index,
        "drug_name": str(row.get("drug_name") or ""),
        "generic_name": _clean_optional_string(row.get("generic_name")),
        "rxcui": _clean_optional_string(row.get("rxcui")),
        "source": str(row.get("source") or ""),
        "source_id": str(row.get("source_id") or ""),
        "source_title": str(row.get("source_title") or ""),
        "source_url": _clean_optional_string(row.get("source_url")),
        "section": str(row.get("section") or ""),
        "chunk_text": _normalize_text(row.get("chunk_text")),
        "similarity": float(row.get("similarity") or 0.0),
    }


def _citation_context(chunk: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "citation_id": chunk.get("citation_id"),
        "title": chunk.get("source_title"),
        "source": chunk.get("source"),
        "url": chunk.get("source_url"),
        "section": chunk.get("section"),
    }


def _build_query_text(message: str, medications: Sequence[Mapping[str, Any]]) -> str:
    names = ", ".join(_medication_names(medications)[:5])
    if not names:
        return message.strip()
    return f"{message.strip()}\nActive medications: {names}"


def _medication_names(medications: Sequence[Mapping[str, Any]]) -> list[str]:
    names: list[str] = []
    for item in medications:
        for key in ("name", "generic_name"):
            value = _clean_optional_string(item.get(key))
            if value and value not in names:
                names.append(value)
    return names


def _medication_rxcuis(medications: Sequence[Mapping[str, Any]]) -> list[str]:
    rxcuis: list[str] = []
    for item in medications:
        value = _clean_optional_string(item.get("rxcui"))
        if value and value not in rxcuis:
            rxcuis.append(value)
    return rxcuis


def _chunk_text(text: str, max_chars: int = 1200) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining.strip())
            break

        split_at = remaining.rfind(". ", 0, max_chars)
        if split_at < max_chars // 2:
            split_at = max_chars
        chunk = remaining[: split_at + 1].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at + 1 :].strip()
    return chunks


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_normalize_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_normalize_text(item) for item in value.values())
    return " ".join(str(value).split())


def _clean_optional_string(value: Any) -> str | None:
    cleaned = _normalize_text(value)
    return cleaned or None


def _format_vector(values: Sequence[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def format_drug_knowledge_for_prompt(context: Mapping[str, Any] | None) -> str:
    """Format retrieved medication chunks for the triage response prompt."""
    if not context:
        return "none"

    status = str(context.get("status") or "weak")
    chunks = cast(Sequence[Mapping[str, Any]], context.get("chunks") or [])
    if status != "grounded" or not chunks:
        return (
            "No reliable medication knowledge chunks were retrieved. Use a safe fallback and "
            "ask the patient to contact their care team for medication-specific guidance."
        )

    lines: list[str] = []
    for chunk in chunks[:5]:
        citation_id = chunk.get("citation_id")
        title = str(chunk.get("source_title") or "Drug label")
        section = str(chunk.get("section") or "Label section")
        text = _normalize_text(chunk.get("chunk_text"))[:700]
        lines.append(f"[{citation_id}] {title} — {section}: {text}")
    return "\n".join(lines)
