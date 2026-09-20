"""Candidate-only document extraction graph."""

from __future__ import annotations

import json
import logging
import re
from typing import Annotated, Any, Literal, NotRequired, TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.agents.ingestion.prompts import (
    EXTRACT_CONTENT_SYSTEM,
    EXTRACT_CONTENT_USER,
    GENERATE_SUMMARY_SYSTEM,
    GENERATE_SUMMARY_USER,
)
from app.clients.model_router import TaskType, get_router

logger = logging.getLogger(__name__)
MIN_EMBEDDED_TEXT_CHARS = 32
_NON_WHITESPACE = re.compile(r"\S")


class IngestionState(TypedDict):
    """Ephemeral state; durable clinical writes happen only after this graph ends."""

    document_id: str
    file_url: str
    document_type: str
    mime_type: str
    patient_id: str
    raw_content: str | None
    page_texts: list[str] | None
    source_status: Literal["needs_ocr", "needs_evidence_review"] | None
    source_warnings: list[str]
    extracted_data: dict[str, Any] | None
    validated_data: dict[str, Any] | None
    validation_errors: list[str] | None
    normalized_medications: list[dict[str, Any]] | None
    # Which model actually produced the extraction, carried to the candidate write so a
    # stored fact records its own provenance. `NotRequired` so existing state literals
    # stay valid: a run that never reached the model simply has no entry.
    extraction_model: NotRequired[str | None]
    patient_summary: str | None
    summary_warning: str | None
    error: str | None
    retry_count: int
    messages: Annotated[list[Any], add_messages]


def _skip_if_error(state: IngestionState, node_name: str) -> bool:
    if not state.get("error"):
        return False
    logger.info("Skipping %s because extraction already failed", node_name)
    return True


async def receive_document(state: IngestionState) -> IngestionState:
    """Extract only embedded text; images and scans wait for a reviewed OCR capability."""
    try:
        from app.clients.supabase import get_admin_client

        file_bytes = get_admin_client().storage.from_("documents").download(state["file_url"])
        mime_type = state.get("mime_type", "").lower()
        path = state["file_url"].lower()
        if mime_type.startswith("image/") or path.endswith(
            (".jpg", ".jpeg", ".png", ".webp", ".tiff", ".heic")
        ):
            state["page_texts"] = []
            state["source_status"] = "needs_ocr"
            state["source_warnings"] = [
                "This image is stored safely and requires a reviewed OCR capability."
            ]
            return state
        if mime_type == "application/pdf" or path.endswith(".pdf"):
            import pymupdf

            document: Any = pymupdf.open(  # type: ignore[no-untyped-call]
                stream=file_bytes, filetype="pdf"
            )
            try:
                pages = [page.get_text() for page in document]
            finally:
                document.close()  # type: ignore[no-untyped-call]
            state["page_texts"] = pages
            if sum(len(_NON_WHITESPACE.findall(page)) for page in pages) < MIN_EMBEDDED_TEXT_CHARS:
                state["source_status"] = "needs_ocr"
                state["source_warnings"] = [
                    "No usable embedded text was found; no candidate was generated."
                ]
                return state
            state["raw_content"] = "\n\n".join(
                f"[Page {number}]\n{text}" for number, text in enumerate(pages, start=1)
            )
        else:
            text = file_bytes.decode("utf-8", errors="replace")
            state["page_texts"] = [text]
            if len(_NON_WHITESPACE.findall(text)) < MIN_EMBEDDED_TEXT_CHARS:
                state["source_status"] = "needs_ocr"
                state["source_warnings"] = ["No usable text was found; no candidate was generated."]
                return state
            state["raw_content"] = text
        state["source_status"] = None
        state["source_warnings"] = []
        state["error"] = None
    except Exception as exc:  # noqa: BLE001 - storage and parser errors are classified later
        logger.exception("Could not read document %s", state["document_id"])
        state["error"] = str(exc)
    return state


async def extract_content(state: IngestionState) -> IngestionState:
    if _skip_if_error(state, "extract_content"):
        return state
    try:
        response, telemetry = await get_router().generate_text_with_telemetry(
            TaskType.DOCUMENT_PARSING,
            prompt=EXTRACT_CONTENT_USER.format(raw_content=state["raw_content"] or ""),
            system_instruction=EXTRACT_CONTENT_SYSTEM,
            temperature=0.1,
            max_tokens=2048,
        )
        # Recorded from the answer rather than from configuration: the router falls back,
        # so the configured model is not necessarily the one that replied, and a
        # confidently wrong provenance stamp is worse than an absent one.
        state["extraction_model"] = telemetry.model
        state["extracted_data"] = _parse_json(response)
        state["raw_content"] = None
        state["error"] = None
    except Exception as exc:  # noqa: BLE001 - provider details remain server-side
        logger.exception("Could not extract document %s", state["document_id"])
        state["error"] = str(exc)
    return state


def _parse_json(response: str) -> dict[str, Any]:
    candidate = response.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise ValueError("Document extractor response must be a JSON object")
    return parsed


async def validate_fhir(state: IngestionState) -> IngestionState:
    if _skip_if_error(state, "validate_fhir"):
        return state
    try:
        from app.tools.fhir_builder import validate_extracted_data

        patient_id = UUID(state["patient_id"])
        document_id = UUID(state["document_id"])
        validated, errors = validate_extracted_data(
            state.get("extracted_data") or {}, patient_id=patient_id, source_document_id=document_id
        )
        state["validated_data"] = validated
        state["validation_errors"] = errors or None
        state["error"] = None
    except Exception as exc:  # noqa: BLE001
        state["error"] = str(exc)
    return state


async def normalize_medications(state: IngestionState) -> IngestionState:
    if _skip_if_error(state, "normalize_medications"):
        return state
    try:
        from app.tools.medication_normalizer import normalize_all

        state["normalized_medications"] = await normalize_all(
            (state.get("validated_data") or {}).get("medications", [])
        )
        state["error"] = None
    except Exception as exc:  # noqa: BLE001
        state["error"] = str(exc)
    return state


async def generate_summary(state: IngestionState) -> IngestionState:
    """Summary is optional and must not invalidate grounded extraction candidates."""
    if _skip_if_error(state, "generate_summary"):
        return state
    try:
        source = state.get("validated_data") or state.get("extracted_data") or {}
        state["patient_summary"] = await get_router().generate_text(
            TaskType.PATIENT_EXPLANATION,
            prompt=GENERATE_SUMMARY_USER.format(
                medications=json.dumps(source.get("medications", []), default=str),
                conditions=json.dumps(source.get("conditions", []), default=str),
                follow_up_instructions=json.dumps(
                    source.get("follow_up_instructions", []), default=str
                ),
            ),
            system_instruction=GENERATE_SUMMARY_SYSTEM,
            temperature=0.3,
            max_tokens=512,
        )
    except Exception as exc:  # noqa: BLE001 - explicitly non-blocking
        logger.warning("Optional document summary failed: %s", type(exc).__name__)
        state["summary_warning"] = type(exc).__name__
        state["patient_summary"] = None
    return state


def _route_after_receive(state: IngestionState) -> Literal["extract", "end"]:
    return "end" if state.get("source_status") else "extract"


def create_ingestion_graph() -> Any:
    """Build a graph with no canonical-write or feed-task stages."""
    graph: StateGraph[IngestionState] = StateGraph(IngestionState)
    graph.add_node("receive_document", receive_document)
    graph.add_node("extract_content", extract_content)
    graph.add_node("validate_fhir", validate_fhir)
    graph.add_node("normalize_medications", normalize_medications)
    graph.add_node("generate_summary", generate_summary)
    graph.add_edge(START, "receive_document")
    graph.add_conditional_edges(
        "receive_document", _route_after_receive, {"extract": "extract_content", "end": END}
    )
    graph.add_edge("extract_content", "validate_fhir")
    graph.add_edge("validate_fhir", "normalize_medications")
    graph.add_edge("normalize_medications", "generate_summary")
    graph.add_edge("generate_summary", END)
    return graph.compile()
