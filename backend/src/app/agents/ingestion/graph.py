"""LangGraph state management for Ingestion Agent."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

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
    saved_ids: dict[str, list[str]] | None  # {"medications": [...], "conditions": [...], "appointments": [...]}

    # Stage 6: generate_summary
    patient_summary: str | None

    # Stage 7: create_feed_tasks
    created_tasks: int | None

    # Error handling
    error: str | None
    retry_count: int

    # Messages (for LangGraph message passing)
    messages: Annotated[list[Any], add_messages]


async def receive_document(state: IngestionState) -> IngestionState:
    """Node 1: Validate input and download document from Supabase Storage.

    Input: document_id, file_url, document_type
    Action: Validate input, download from Supabase Storage, set state
    Output: raw_content in state
    """
    logger.info(f"receive_document: document_id={state['document_id']}, type={state['document_type']}")

    try:
        # TODO: Download from Supabase Storage using file_url
        # For now, placeholder
        state["raw_content"] = f"[Document content from {state['file_url']}]"
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

    try:
        router = get_router()
        client = router.get_client(TaskType.DOCUMENT_PARSING)

        system_instruction = """You are a medical document parser. Extract structured data from the document.

Extract the following information:
- medications: list of medications with name, dosage, frequency, instructions
- conditions: list of medical conditions/diagnoses
- procedures: list of procedures performed
- follow_up_instructions: list of follow-up instructions with timing
- appointments: list of scheduled appointments

Output as JSON with these exact keys."""

        prompt = f"""Extract structured medical data from this document:

{state['raw_content']}

Output as JSON."""

        response = await client.generate(
            prompt=prompt,
            system_instruction=system_instruction,
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
        state["error"] = None

        logger.info(f"Successfully extracted data: {len(extracted_data.get('medications', []))} meds, "
                   f"{len(extracted_data.get('conditions', []))} conditions")
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

    try:
        # TODO: Implement FHIR validation using fhir.resources
        # For now, pass through with basic validation
        extracted_data = state.get("extracted_data", {})
        validation_errors = []

        # Basic validation
        if not extracted_data.get("medications"):
            validation_errors.append("No medications found")

        state["validated_data"] = extracted_data
        state["validation_errors"] = validation_errors if validation_errors else None
        state["error"] = None

        logger.info(f"Validation complete: {len(validation_errors)} errors")
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

    try:
        validated_data = state.get("validated_data", {})
        medications = validated_data.get("medications", [])

        normalized_medications = []
        for med in medications:
            # TODO: Call RxNorm service for normalization
            # For now, pass through with basic structure
            normalized_med = {
                "name": med.get("name", ""),
                "generic_name": med.get("name", ""),  # TODO: lookup via RxNorm
                "rxcui": None,  # TODO: lookup via RxNorm
                "dosage": med.get("dosage", ""),
                "frequency": med.get("frequency", ""),
                "instructions": med.get("instructions", ""),
            }
            normalized_medications.append(normalized_med)

        state["normalized_medications"] = normalized_medications
        state["error"] = None

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

    try:
        # TODO: Implement Supabase upserts
        # For now, placeholder
        saved_ids = {
            "medications": [],
            "conditions": [],
            "appointments": [],
        }

        state["saved_ids"] = saved_ids
        state["error"] = None

        logger.info(f"Saved to database: {saved_ids}")
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

    try:
        router = get_router()
        client = router.get_client(TaskType.PATIENT_EXPLANATION)

        extracted_data = state.get("extracted_data", {})

        system_instruction = """You are a nurse explaining medical information to a patient and their family.
Use simple language that anyone can understand. Keep under 350 words.
Be warm, supportive, and clear."""

        prompt = f"""Explain this medical information to the patient in simple terms:

Medications: {json.dumps(extracted_data.get('medications', []), indent=2)}
Conditions: {json.dumps(extracted_data.get('conditions', []), indent=2)}
Follow-up Instructions: {json.dumps(extracted_data.get('follow_up_instructions', []), indent=2)}

Create a friendly, easy-to-understand summary."""

        response = await client.generate(
            prompt=prompt,
            system_instruction=system_instruction,
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

    try:
        # TODO: Create obligations in database
        # For now, count what would be created
        normalized_medications = state.get("normalized_medications", [])
        extracted_data = state.get("extracted_data", {})
        follow_ups = extracted_data.get("follow_up_instructions", []) if extracted_data else []

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

