"""Stable adapters for text and voice generation providers."""

from __future__ import annotations

import time
from abc import abstractmethod
from collections.abc import Awaitable, Callable
from typing import Protocol

from app.models.generation import (
    GenerationCapability,
    GenerationErrorCode,
    GenerationProviderError,
    GenerationRequest,
    GenerationResponse,
    GenerationTelemetry,
    VoiceResponse,
)


class TextProvider(Protocol):
    name: str
    model: str
    capabilities: frozenset[GenerationCapability]

    @abstractmethod
    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        pass


class VoiceProvider(Protocol):
    name: str
    capabilities: frozenset[GenerationCapability]

    @abstractmethod
    async def synthesize(self, text: str) -> VoiceResponse:
        pass


class ClientTextProvider:
    """Wrap an existing text client while recording a uniform response envelope."""

    # This adapter normalizes plain-text responses. Structured output keeps using
    # the capability-specific client path until it has its own provider contract.
    capabilities = frozenset({GenerationCapability.TEXT})

    def __init__(self, *, name: str, model: str, generate: Callable[..., Awaitable[str]]) -> None:
        self.name = name
        self.model = model
        self._generate = generate

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        started = time.perf_counter()
        try:
            text = await self._generate(
                prompt=request.prompt,
                system_instruction=request.system_instruction,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
        except TimeoutError as exc:
            raise GenerationProviderError(
                GenerationErrorCode.TIMEOUT, "Text generation timed out"
            ) from exc
        except Exception as exc:
            raise GenerationProviderError(
                GenerationErrorCode.UNAVAILABLE, "Text generation failed"
            ) from exc
        return GenerationResponse(
            text=text,
            telemetry=GenerationTelemetry(
                provider=self.name,
                model=self.model,
                latency_ms=round((time.perf_counter() - started) * 1000),
            ),
        )


class TextFallbackProvider:
    """Try providers in order and make fallback selection visible to callers."""

    name = "fallback"
    model = "multiple"
    capabilities = frozenset({GenerationCapability.TEXT})

    def __init__(self, providers: list[TextProvider]) -> None:
        if not providers:
            raise ValueError("At least one text provider is required")
        self.providers = providers

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        failures: list[str] = []
        for provider in self.providers:
            try:
                response = await provider.generate(request)
                response.telemetry.fallback_path = failures + [provider.name]
                return response
            except GenerationProviderError as exc:
                failures.append(f"{provider.name}:{exc.code.value}")
        raise GenerationProviderError(
            GenerationErrorCode.UNAVAILABLE, "No configured text provider succeeded"
        )


class TextOnlyVoiceProvider:
    """Deterministic fallback when audio output is disabled or unavailable."""

    name = "text_only"
    capabilities = frozenset({GenerationCapability.TEXT})

    async def synthesize(self, text: str) -> VoiceResponse:
        return VoiceResponse(
            transcript=" ".join(text.split()),
            telemetry=GenerationTelemetry(
                provider=self.name,
                model="none",
                latency_ms=0,
                fallback_path=[self.name],
            ),
        )
