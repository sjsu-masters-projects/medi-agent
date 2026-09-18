"""Model Router — routes LLM tasks to a model client.

This is the legacy routing path, kept working while the agent runtime in `app.adk`
replaces it. New routing decisions belong in `app.adk.registry`, which records a
fallback, a latency budget, and a deterministic path for each workload; this map can
express none of those.

Every task that once routed to MedGemma now routes to Flash. That model was measured and
dropped (`.agent/specs/eval-harness-protocol-2026-09.md` §14), and in practice it had
already stopped running: its client raised unless a Vertex endpoint was configured, and
the default was empty. Document parsing was therefore already served by Flash through the
fallback path, while triage classification raised on every call and degraded to keyword
rules without ever recording that it had.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

from app.clients.gemini import GeminiClient
from app.config import settings
from app.models.generation import GenerationRequest, GenerationTelemetry
from app.services.generation_providers import ClientTextProvider, TextFallbackProvider, TextProvider
from app.services.model_telemetry_service import schedule_generation_record

if TYPE_CHECKING:
    from app.clients.gemini import GeminiClient as GeminiClientType

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Task types for model routing."""

    # Clinical extraction and classification
    DOCUMENT_PARSING = "document_parsing"
    ADR_DETECTION = "adr_detection"
    DRUG_INTERACTION = "drug_interaction"
    TRIAGE_CLASSIFICATION = "triage_classification"
    LAB_INTERPRETATION = "lab_interpretation"

    # Patient-facing, speed and warmth
    CHAT_RESPONSE = "chat_response"
    VOICE_RESPONSE = "voice_response"
    PATIENT_EXPLANATION = "patient_explanation"
    GENERAL_QA = "general_qa"

    # Deep reasoning, batch/background
    SOAP_NOTE = "soap_note"
    MEDWATCH_DRAFT = "medwatch_draft"
    PHARMACOVIGILANCE_SCAN = "pharmacovigilance_scan"
    COMPLEX_ANALYSIS = "complex_analysis"


# Route mapping: TaskType → model name
TASK_MODEL_MAP = {
    # Clinical tasks. These named MedGemma until it was measured and dropped.
    TaskType.DOCUMENT_PARSING: "flash",
    TaskType.ADR_DETECTION: "flash",
    TaskType.DRUG_INTERACTION: "flash",
    TaskType.TRIAGE_CLASSIFICATION: "flash",
    TaskType.LAB_INTERPRETATION: "flash",
    # Patient-facing
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
    """Routes LLM tasks to a model client based on task type.

    Maintains singleton instances of each client for connection pooling.
    Includes fallback logic: if the primary model fails, try Flash as default.

    Example:
        router = ModelRouter()
        client = router.get_client(TaskType.DOCUMENT_PARSING)
        response = await client.generate(prompt="Extract medications from...")
    """

    def __init__(self) -> None:
        """Initialize model router with lazy client instantiation."""
        self._flash_client: GeminiClientType | None = None
        self._pro_client: GeminiClientType | None = None
        self._text_providers: dict[TaskType, TextProvider] = {}
        self._text_providers_by_model: dict[str, TextProvider] = {}

    @property
    def flash_client(self) -> GeminiClientType:
        """Get or create the Gemini Flash client."""
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
        """Get or create the Gemini Pro client."""
        if self._pro_client is None:
            self._pro_client = GeminiClient(
                model=settings.gemini_pro_model,
                use_vertex_ai=True,
                timeout=120,
            )
            logger.info(f"Initialized Gemini Pro client: {settings.gemini_pro_model}")
        return self._pro_client

    def get_client(self, task_type: TaskType) -> GeminiClientType:
        """Get the appropriate LLM client for the given task type.

        Args:
            task_type: The type of task to route

        Returns:
            The appropriate client instance (Flash or Pro)

        Raises:
            ValueError: If task_type is not recognized
        """
        model_name = TASK_MODEL_MAP.get(task_type)

        if model_name is None:
            raise ValueError(f"Unknown task type: {task_type}")

        if model_name == "flash":
            return self.flash_client
        elif model_name == "pro":
            return self.pro_client
        else:
            raise ValueError(f"Unknown model name: {model_name}")

    def get_client_with_fallback(self, task_type: TaskType) -> GeminiClientType:
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
                f"Failed to get primary client for {task_type}: {e}. Falling back to Flash."
            )
            return self.flash_client

    def get_text_provider(self, task_type: TaskType) -> TextProvider:
        """Return the provider-neutral adapter for a text-only generation task.

        Structured output and streaming continue to use ``get_client`` until
        their capability-specific provider contracts are introduced.
        """
        if task_type in self._text_providers:
            return self._text_providers[task_type]

        client = self.get_client(task_type)
        model_name = TASK_MODEL_MAP.get(task_type)
        if model_name is None:
            raise ValueError(f"Unknown task type: {task_type}")
        provider = ClientTextProvider(
            name=model_name,
            model=str(getattr(client, "model_name", model_name)),
            generate=cast(Any, client.generate),
        )
        self._text_providers[task_type] = provider
        return provider

    def client_for_model(self, model_name: str) -> GeminiClientType:
        """Return a client by model name, independent of task routing.

        `get_client` answers "what should run this task", which is the right question
        in production and the wrong one for evaluation: TASK_MODEL_MAP binds each task
        to exactly one model, so it cannot express "run this same prompt on both".
        """
        if model_name == "flash":
            return self.flash_client
        if model_name == "pro":
            return self.pro_client
        raise ValueError(f"Unknown model name: {model_name}")

    def get_text_provider_for_model(self, model_name: str) -> TextProvider:
        """Return the provider-neutral adapter for a named model.

        Comparison needs to address a model directly. Initialization failure is left to
        the caller rather than falling back to Flash: silently substituting a provider
        would put another model's output under this one's name and quietly corrupt the
        comparison.
        """
        if model_name in self._text_providers_by_model:
            return self._text_providers_by_model[model_name]

        client = self.client_for_model(model_name)
        provider = ClientTextProvider(
            name=model_name,
            model=str(getattr(client, "model_name", model_name)),
            generate=cast(Any, client.generate),
        )
        self._text_providers_by_model[model_name] = provider
        return provider

    def get_text_provider_with_fallback(self, task_type: TaskType) -> TextProvider:
        """Return a text provider with Flash as the transparent fallback."""
        try:
            primary = self.get_text_provider(task_type)
        except Exception as exc:
            if TASK_MODEL_MAP.get(task_type) == "flash":
                raise
            logger.warning(
                "Primary text provider is unavailable for %s; using Flash: %s",
                task_type,
                exc,
            )
            return self.get_text_provider(TaskType.CHAT_RESPONSE)
        if TASK_MODEL_MAP.get(task_type) == "flash":
            return primary
        try:
            fallback = self.get_text_provider(TaskType.CHAT_RESPONSE)
        except Exception as exc:
            logger.warning("Text fallback provider is unavailable: %s", exc)
            return primary
        return TextFallbackProvider([primary, fallback])

    async def generate_text(
        self,
        task_type: TaskType,
        *,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        """Generate plain text through the provider contract and return text only."""
        text, _telemetry = await self.generate_text_with_telemetry(
            task_type,
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return text

    async def generate_text_with_telemetry(
        self,
        task_type: TaskType,
        *,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> tuple[str, GenerationTelemetry]:
        """Generate text and return which model produced it, alongside the text.

        `generate_text` throws the envelope away, which is right for a caller that only
        needs prose. It is wrong for a caller that then writes a durable record: document
        ingestion stores extraction candidates with no note of which model produced them,
        so after a model swap there is no way to tell which candidates came from which
        model, and therefore no way to re-review or retire them selectively.

        Reading the configured model name at the write site instead would be a guess: the
        router falls back, so the configured model is not necessarily the one that
        answered. A confidently wrong provenance stamp is worse than an absent one.
        """
        response = await self.get_text_provider_with_fallback(task_type).generate(
            GenerationRequest(
                prompt=prompt,
                system_instruction=system_instruction,
                temperature=temperature,
                max_tokens=max_tokens,
                task=task_type.value,
            )
        )
        # The envelope beside the text used to be discarded here, which is why nothing
        # could say what a workload costs or how often it is truncated. Scheduled rather
        # than awaited: this runs on every turn, and a stalled database must not spend a
        # patient's latency budget on bookkeeping.
        #
        # `task_type.value` is the legacy routing key, not a `Workload`. The column records
        # whichever key the caller routed on, and this call site goes away with the rest of
        # the legacy router — the service is the part the agent runtime will reuse.
        schedule_generation_record(workload=task_type.value, telemetry=response.telemetry)
        return response.text, response.telemetry


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
