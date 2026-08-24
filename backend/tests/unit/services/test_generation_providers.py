"""Tests for provider-neutral generation contracts and deterministic fallback."""

from __future__ import annotations

import pytest

from app.models.generation import (
    GenerationErrorCode,
    GenerationProviderError,
    GenerationRequest,
    GenerationResponse,
    GenerationTelemetry,
)
from app.services.generation_providers import TextFallbackProvider, TextOnlyVoiceProvider


class FailingProvider:
    name = "primary"
    model = "primary-model"
    capabilities = frozenset()

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        raise GenerationProviderError(GenerationErrorCode.TIMEOUT, "timed out")


class WorkingProvider:
    name = "secondary"
    model = "secondary-model"
    capabilities = frozenset()

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        return GenerationResponse(
            text="ready",
            telemetry=GenerationTelemetry(provider=self.name, model=self.model, latency_ms=1),
        )


@pytest.mark.asyncio
async def test_text_provider_records_fallback_path() -> None:
    response = await TextFallbackProvider([FailingProvider(), WorkingProvider()]).generate(
        GenerationRequest(prompt="test")
    )

    assert response.text == "ready"
    assert response.telemetry.fallback_path == ["primary:timeout", "secondary"]


@pytest.mark.asyncio
async def test_text_only_voice_provider_returns_normalized_transcript_without_audio() -> None:
    response = await TextOnlyVoiceProvider().synthesize("  Please   review this.  ")

    assert response.transcript == "Please review this."
    assert response.audio is None
    assert response.telemetry.fallback_path == ["text_only"]
