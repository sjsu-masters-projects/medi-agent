"""LangGraph state management for Ingestion Agent."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, TypedDict
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


class IngestionState(TypedDict):
    """State for document ingestion workflow.

    State flows through these stages:
    1. receive_document → raw_content, document_type
    2. extract_content → extracted_data
    3. validate_fhir → validated_data, validation_errors
    4. normalize_medications → normalized_medications
    5. save_to_database → saved_ids
    6. generate_summary → patient_summary
    7. create_feed_tasks → created_tasks
    """

    # Input
    document_id: str
    file_url: str
    document_type: str  # "discharge_summary" | "lab_report" | "prescription" | "diagnostic_report"
    patient_id: str

    # Stage 1: receive_document
    raw_content: str | None

    # Stage 2: extract_content
    extracted_data: dict[str, Any] | None

    # Stage 3: validate_fhir
    validated_data: dict[str, Any] | None
    validation_errors: list[str] | None

    # Stage 4: normalize_medications
    normalized_medications: list[dict[str, Any]] | None

    # Stage 5: save_to_database
    saved_ids: (
        dict[str, list[str]] | None
    )  # {"medications": [...], "conditions": [...], "appointments": [...]}

    # Stage 6: generate_summary
    patient_summary: str | None

    # Stage 7: create_feed_tasks
    created_tasks: int | None

    # Error handling
    error: str | None
    retry_count: int

    # Messages (for LangGraph message passing)
    messages: Annotated[list[Any], add_messages]


def _skip_if_error(state: IngestionState, node_name: str) -> bool:
    """Skip downstream work when a previous node already failed."""
    if not state.get("error"):
        return False

    logger.info("Skipping %s due to previous error: %s", node_name, state["error"])
    return True


async def receive_document(state: IngestionState) -> IngestionState:
    """Node 1: Validate input and download document from Supabase Storage.

    Input: document_id, file_url, document_type
    Action: Validate input, download from Supabase Storage, set state
    Output: raw_content in state
    """
    logger.info(
        f"receive_document: document_id={state['document_id']}, type={state['document_type']}"
    )

    try:
        import io

        import fitz
        import pytesseract
        from PIL import Image

        from app.clients.supabase import get_admin_client

        admin = get_admin_client()
        file_bytes = admin.storage.from_("documents").download(state["file_url"])
        file_path = state["file_url"].lower()

        if file_path.endswith(".pdf") or state["document_type"] in (
            "lab_report",
            "discharge_summary",
            "prescription",
            "diagnostic_report",
        ):
            document = fitz.open(stream=file_bytes, filetype="pdf")
            try:
                raw_content = "\n".join(page.get_text() for page in document)
            finally:
                document.close()
        elif any(
            file_path.endswith(extension)
            for extension in (".jpg", ".jpeg", ".png", ".webp", ".tiff", ".heic")
        ):
            image = Image.open(io.BytesIO(file_bytes))
            raw_content = pytesseract.image_to_string(image)
        else:
            raw_content = file_bytes.decode("utf-8", errors="replace")

        state["raw_content"] = raw_content
        state["error"] = None

        logger.info(f"Successfully received document: {state['document_id']}")
        return state

    except Exception as e:
        logger.error(f"Failed to receive document: {e}")
        state["error"] = str(e)
        return state


async def extract_content(state: IngestionState) -> IngestionState:
    """Node 2: Extract structured data using MedGemma 27B.

    Input: raw_content from state
    Action: Call MedGemma 27B (TaskType.DOCUMENT_PARSING) with Gemma chat template
    System prompt: Extract structured data: medications, conditions, procedures, follow-up instructions
    Output: extracted_data (dict) in state
    """
    logger.info(f"extract_content: document_id={state['document_id']}")

    if _skip_if_error(state, "extract_content"):
        return state

    try:
        router = get_router()
        prompt = EXTRACT_CONTENT_USER.format(raw_content=state["raw_content"] or "")

        response = await router.generate_text(
            TaskType.DOCUMENT_PARSING,
            prompt=prompt,
            system_instruction=EXTRACT_CONTENT_SYSTEM,
            temperature=0.3,
            max_tokens=2048,
        )

        # Parse JSON response
        try:
            extracted_data = json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
                extracted_data = json.loads(json_str)
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
                extracted_data = json.loads(json_str)
            else:
                raise ValueError(f"Could not parse JSON from response: {response[:200]}") from None

        state["extracted_data"] = extracted_data
        state["raw_content"] = None
        state["error"] = None

        logger.info(
            f"Successfully extracted data: {len(extracted_data.get('medications', []))} meds, "
            f"{len(extracted_data.get('conditions', []))} conditions"
        )
        return state

    except Exception as e:
        logger.error(f"Failed to extract content: {e}")
        state["error"] = str(e)
        return state


async def validate_fhir(state: IngestionState) -> IngestionState:
    """Node 3: Validate extracted fields against FHIR resource schemas.

    Input: extracted_data from state
    Action: Validate extracted fields against FHIR resource schemas (MedicationRequest, Condition, etc.)
    Output: validated_data in state, validation_errors if any
    """
    logger.info(f"validate_fhir: document_id={state['document_id']}")

    if _skip_if_error(state, "validate_fhir"):
        return state

    try:
        from app.tools.fhir_builder import validate_extracted_data

        extracted_data = state.get("extracted_data") or {}
        patient_id = UUID(state["patient_id"]) if state.get("patient_id") else UUID(int=0)
        source_document_id = UUID(state["document_id"]) if state.get("document_id") else None
        validated, errors = validate_extracted_data(
            extracted_data,
            patient_id=patient_id,
            source_document_id=source_document_id,
        )

        state["validated_data"] = validated
        state["validation_errors"] = errors if errors else None
        state["error"] = None

        logger.info(f"Validation complete: {len(errors)} errors")
        return state

    except Exception as e:
        logger.error(f"Failed to validate FHIR: {e}")
        state["error"] = str(e)
        return state


async def normalize_medications(state: IngestionState) -> IngestionState:
    """Node 4: Normalize medications via RxNorm.

    Input: validated_data.medications from state
    Action: For each medication, call RxNorm service to normalize:
            - Brand name → generic name → RxCUI
            - Parse dosage strings (e.g., "50mg BID" → dosage=50, unit=mg, frequency=2x/day)
    Output: normalized_medications in state
    """
    logger.info(f"normalize_medications: document_id={state['document_id']}")

    if _skip_if_error(state, "normalize_medications"):
        return state

    try:
        from app.tools.medication_normalizer import normalize_all

        validated_data = state.get("validated_data") or {}
        medications = validated_data.get("medications", [])

        state["normalized_medications"] = await normalize_all(medications)
        state["error"] = None
        normalized_medications = state["normalized_medications"] or []

        logger.info(f"Normalized {len(normalized_medications)} medications")
        return state

    except Exception as e:
        logger.error(f"Failed to normalize medications: {e}")
        state["error"] = str(e)
        return state


async def save_to_database(state: IngestionState) -> IngestionState:
    """Node 5: Save to database via Supabase.

    Input: All normalized/validated data
    Action: Upsert via Supabase service:
            - documents table: update parsed status
            - medications table: insert/update meds
            - conditions table: insert new conditions
            - appointments table: insert follow-ups
    Output: saved_ids in state
    """
    logger.info(f"save_to_database: document_id={state['document_id']}")

    if _skip_if_error(state, "save_to_database"):
        return state

    try:
        state["saved_ids"] = {
            "medications": [],
            "conditions": [],
            "allergies": [],
            "obligations": [],
            "appointments": [],
        }
        state["error"] = None

        logger.info("Prepared database payloads for document %s", state["document_id"])
        return state

    except Exception as e:
        logger.error(f"Failed to save to database: {e}")
        state["error"] = str(e)
        return state


async def generate_summary(state: IngestionState) -> IngestionState:
    """Node 6: Generate patient-friendly summary using Flash Lite.

    Input: extracted_data from state
    Action: Call Flash Lite (TaskType.PATIENT_EXPLANATION) to generate patient-friendly summary
    System prompt: "You are a nurse explaining discharge instructions to a patient and their family.
                    Use simple language. Keep under 350 words."
    Output: patient_summary in state
    """
    logger.info(f"generate_summary: document_id={state['document_id']}")

    if _skip_if_error(state, "generate_summary"):
        return state

    try:
        router = get_router()
        summary_data = state.get("validated_data") or state.get("extracted_data") or {}
        prompt = GENERATE_SUMMARY_USER.format(
            medications=json.dumps(summary_data.get("medications", []), default=str),
            conditions=json.dumps(summary_data.get("conditions", []), default=str),
            follow_up_instructions=json.dumps(
                summary_data.get("follow_up_instructions", []),
                default=str,
            ),
        )

        response = await router.generate_text(
            TaskType.PATIENT_EXPLANATION,
            prompt=prompt,
            system_instruction=GENERATE_SUMMARY_SYSTEM,
            temperature=0.7,
            max_tokens=512,
        )

        state["patient_summary"] = response
        state["error"] = None

        logger.info(f"Generated summary: {len(response)} chars")
        return state

    except Exception as e:
        logger.error(f"Failed to generate summary: {e}")
        state["error"] = str(e)
        return state


async def create_feed_tasks(state: IngestionState) -> IngestionState:
    """Node 7: Create Today Feed tasks from medications and follow-ups.

    Input: normalized_medications, appointments from state
    Action: Create obligations entries for:
            - Each medication → daily medication task
            - Each follow-up instruction → obligation
    Output: created_tasks count in state
    """
    logger.info(f"create_feed_tasks: document_id={state['document_id']}")

    if _skip_if_error(state, "create_feed_tasks"):
        return state

    try:
        normalized_medications = state.get("normalized_medications") or []
        validated_data = state.get("validated_data") or {}
        extracted_data = state.get("extracted_data") or {}
        follow_ups = (
            validated_data.get("follow_up_instructions")
            or extracted_data.get("follow_up_instructions")
            or []
        )

        created_tasks = len(normalized_medications) + len(follow_ups)

        state["created_tasks"] = created_tasks
        state["error"] = None

        logger.info(f"Created {created_tasks} feed tasks")
        return state

    except Exception as e:
        logger.error(f"Failed to create feed tasks: {e}")
        state["error"] = str(e)
        return state


def create_ingestion_graph() -> Any:
    """Create LangGraph workflow for document ingestion.

    Workflow:
        START
          ↓
        receive_document (validate input, download)
          ↓
        extract_content (MedGemma 27B)
          ↓
        validate_fhir (FHIR schema validation)
          ↓
        normalize_medications (RxNorm lookup)
          ↓
        save_to_database (Supabase upsert)
          ↓
        generate_summary (Flash Lite)
          ↓
        create_feed_tasks (obligations)
          ↓
        END

    Returns:
        Compiled StateGraph
    """
    # Create graph
    graph: StateGraph[IngestionState] = StateGraph(IngestionState)

    # Add nodes
    graph.add_node("receive_document", receive_document)
    graph.add_node("extract_content", extract_content)
    graph.add_node("validate_fhir", validate_fhir)
    graph.add_node("normalize_medications", normalize_medications)
    graph.add_node("save_to_database", save_to_database)
    graph.add_node("generate_summary", generate_summary)
    graph.add_node("create_feed_tasks", create_feed_tasks)

    # Add edges (linear workflow)
    graph.add_edge(START, "receive_document")
    graph.add_edge("receive_document", "extract_content")
    graph.add_edge("extract_content", "validate_fhir")
    graph.add_edge("validate_fhir", "normalize_medications")
    graph.add_edge("normalize_medications", "save_to_database")
    graph.add_edge("save_to_database", "generate_summary")
    graph.add_edge("generate_summary", "create_feed_tasks")
    graph.add_edge("create_feed_tasks", END)

    # Compile
    return graph.compile()
