"""Model Router — routes LLM tasks to the optimal model.

Based on MedGemma 27B vs Gemini Flash Lite vs Gemini Pro benchmarks
(2026-03-21, 4 runs, 5 clinical scenarios, Gemma chat template).

Routing Decision (data-backed):
- MedGemma 27B: Document parsing, ADR detection, drug interactions, triage classification
- Gemini Flash Lite: Patient-facing chat, voice pipeline, lab explanations
- Gemini Pro: SOAP notes, MedWatch forms, nightly pharmacovigilance batch
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

from app.clients.gemini import GeminiClient
from app.clients.medgemma import MedGemmaClient
from app.config import settings

if TYPE_CHECKING:
    from app.clients.gemini import GeminiClient as GeminiClientType
    from app.clients.medgemma import MedGemmaClient as MedGemmaClientType

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Task types for model routing."""

    # MedGemma 27B tasks (clinical extraction, high correctness)
    DOCUMENT_PARSING = "document_parsing"
    ADR_DETECTION = "adr_detection"
    DRUG_INTERACTION = "drug_interaction"
    TRIAGE_CLASSIFICATION = "triage_classification"
    LAB_INTERPRETATION = "lab_interpretation"

    # Flash Lite tasks (patient-facing, speed + warmth)
    CHAT_RESPONSE = "chat_response"
    VOICE_RESPONSE = "voice_response"
    PATIENT_EXPLANATION = "patient_explanation"
    GENERAL_QA = "general_qa"

    # Pro tasks (deep reasoning, batch/background)
    SOAP_NOTE = "soap_note"
    MEDWATCH_DRAFT = "medwatch_draft"
    PHARMACOVIGILANCE_SCAN = "pharmacovigilance_scan"
    COMPLEX_ANALYSIS = "complex_analysis"


# Route mapping: TaskType → model name
TASK_MODEL_MAP = {
    # MedGemma 27B
    TaskType.DOCUMENT_PARSING: "medgemma",
    TaskType.ADR_DETECTION: "medgemma",
    TaskType.DRUG_INTERACTION: "medgemma",
    TaskType.TRIAGE_CLASSIFICATION: "medgemma",
    TaskType.LAB_INTERPRETATION: "medgemma",
    # Flash Lite
    TaskType.CHAT_RESPONSE: "flash",
    TaskType.VOICE_RESPONSE: "flash",
    TaskType.PATIENT_EXPLANATION: "flash",
    TaskType.GENERAL_QA: "flash",
    # Pro
    TaskType.SOAP_NOTE: "pro",
    TaskType.MEDWATCH_DRAFT: "pro",
    TaskType.PHARMACOVIGILANCE_SCAN: "pro",
    TaskType.COMPLEX_ANALYSIS: "pro",
}


class ModelRouter:
    """Routes LLM tasks to the optimal model based on task type.

    Maintains singleton instances of each client for connection pooling.
    Includes fallback logic: if primary model fails, try Flash as default.

    Example:
        router = ModelRouter()
        client = router.get_client(TaskType.DOCUMENT_PARSING)
        response = await client.generate(prompt="Extract medications from...")
    """

    def __init__(self) -> None:
        """Initialize model router with lazy client instantiation."""
        self._medgemma_client: MedGemmaClientType | None = None
        self._flash_client: GeminiClientType | None = None
        self._pro_client: GeminiClientType | None = None

    @property
    def medgemma_client(self) -> MedGemmaClientType:
        """Get or create MedGemma 27B client."""
        if self._medgemma_client is None:
            self._medgemma_client = MedGemmaClient(
                model=settings.medgemma_model,
            )
            logger.info(f"Initialized MedGemma client: {settings.medgemma_model}")
        return self._medgemma_client

    @property
    def flash_client(self) -> GeminiClientType:
        """Get or create Gemini Flash Lite client."""
        if self._flash_client is None:
            self._flash_client = GeminiClient(
                model=settings.gemini_flash_model,
                use_vertex_ai=True,
                timeout=90,
            )
            logger.info(f"Initialized Gemini Flash client: {settings.gemini_flash_model}")
        return self._flash_client

    @property
    def pro_client(self) -> GeminiClientType:
        """Get or create Gemini Pro client."""
        if self._pro_client is None:
            self._pro_client = GeminiClient(
                model=settings.gemini_pro_model,
                use_vertex_ai=True,
                timeout=120,
            )
            logger.info(f"Initialized Gemini Pro client: {settings.gemini_pro_model}")
        return self._pro_client

    def get_client(
        self, task_type: TaskType
    ) -> MedGemmaClientType | GeminiClientType:
        """Get the appropriate LLM client for the given task type.

        Args:
            task_type: The type of task to route

        Returns:
            The appropriate client instance (MedGemma, Flash, or Pro)

        Raises:
            ValueError: If task_type is not recognized
        """
        model_name = TASK_MODEL_MAP.get(task_type)

        if model_name is None:
            raise ValueError(f"Unknown task type: {task_type}")

        if model_name == "medgemma":
            return self.medgemma_client
        elif model_name == "flash":
            return self.flash_client
        elif model_name == "pro":
            return self.pro_client
        else:
            raise ValueError(f"Unknown model name: {model_name}")

    def get_client_with_fallback(
        self, task_type: TaskType
    ) -> MedGemmaClientType | GeminiClientType:
        """Get client with fallback to Flash if primary fails.

        Args:
            task_type: The type of task to route

        Returns:
            Primary client, or Flash client if primary initialization fails
        """
        try:
            return self.get_client(task_type)
        except Exception as e:
            logger.error(
                f"Failed to get primary client for {task_type}: {e}. "
                f"Falling back to Flash Lite."
            )
            return self.flash_client


# Global singleton instance
_router: ModelRouter | None = None


def get_router() -> ModelRouter:
    """Get the global ModelRouter singleton.

    Returns:
        The global ModelRouter instance
    """
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router
