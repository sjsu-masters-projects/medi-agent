"""Gemini on Vertex, through the Google Gen AI SDK.

Thin on purpose. `GeminiClient` already owns the SDK, the retry loop, and the Vertex
project wiring, so this only adapts it to the provider contract and enforces that the
model it is handed is actually reached this way. Duplicating the client here would give
us two places where "how Gemini is called" lives, which is the condition that let the
SDK-by-model-name defect survive as long as it did.
"""

from __future__ import annotations

from app.adk.registry import ModelSpec, Transport
from app.clients.gemini import GeminiClient
from app.services.generation_providers import ClientTextProvider


def build_genai_provider(
    spec: ModelSpec,
    *,
    timeout_seconds: float = 60.0,
    max_retries: int = 3,
) -> ClientTextProvider:
    """Build a text provider for a Gemini model reached through the Gen AI SDK."""
    if spec.transport is not Transport.VERTEX_GENAI:
        raise ValueError(
            f"{spec.key} is reached over {spec.transport.value}, not the Gen AI SDK. "
            "Building it here would send a publisher-prefixed id to an SDK that wants a "
            "bare one."
        )

    client = GeminiClient(
        model=spec.model_id,
        # Explicit rather than auto-detected. Auto-detection reads `google_project_id`,
        # so an unset project would quietly build an AI Studio client for a model the
        # registry says is served on Vertex.
        use_vertex_ai=True,
        max_retries=max_retries,
        timeout=int(timeout_seconds),
    )
    return ClientTextProvider(
        name=spec.key,
        model=spec.model_id,
        generate=client.generate,
    )
