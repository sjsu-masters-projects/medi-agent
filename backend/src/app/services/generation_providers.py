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
    VoiceSynthesisRequest,
    VoiceTranscriptionRequest,
)


class TextProvider(Protocol):
    name: str
    model: str
    capabilities: frozenset[GenerationCapability]

    @abstractmethod
    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        pass


class VoiceProvider(Protocol):
    """Both directions of voice, because a voice product needs both.

    Transcription and synthesis are separate capabilities, not a single "voice"
    feature: a provider may serve one and not the other, and the deterministic text
    fallback serves neither ear. A provider declares what it can do in `capabilities`
    and raises `UNSUPPORTED` for the rest, so a caller never has to guess from the
    provider's name which half it got.
    """

    name: str
    capabilities: frozenset[GenerationCapability]

    @abstractmethod
    async def transcribe(self, request: VoiceTranscriptionRequest) -> VoiceResponse:
        pass

    @abstractmethod
    async def synthesize(self, request: VoiceSynthesisRequest) -> VoiceResponse:
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


class DeepgramVoiceProvider:
    """Wrap the Deepgram client in the provider-neutral voice contract.

    The client functions are injected rather than imported here so a test can exercise
    the contract — telemetry, error mapping, locale-driven model choice — without a
    Deepgram key or a network call.
    """

    name = "deepgram"
    capabilities = frozenset({GenerationCapability.AUDIO_INPUT, GenerationCapability.AUDIO_OUTPUT})

    def __init__(
        self,
        *,
        transcribe: Callable[..., Awaitable[str]],
        synthesize: Callable[..., Awaitable[bytes]],
        stt_model: str,
        tts_model_for: Callable[[str], str],
        audio_mime_type: str = "audio/mpeg",
    ) -> None:
        self._transcribe = transcribe
        self._synthesize = synthesize
        self._stt_model = stt_model
        self._tts_model_for = tts_model_for
        self._audio_mime_type = audio_mime_type

    async def transcribe(self, request: VoiceTranscriptionRequest) -> VoiceResponse:
        model = request.model or self._stt_model
        started = time.perf_counter()
        try:
            transcript = await self._transcribe(
                request.audio,
                model=model,
                language=request.language,
                smart_format=True,
            )
        except Exception as exc:
            raise _voice_error(exc, "Voice transcription failed") from exc
        return VoiceResponse(
            transcript=transcript.strip(),
            telemetry=_voice_telemetry(self.name, model, started),
        )

    async def synthesize(self, request: VoiceSynthesisRequest) -> VoiceResponse:
        model = request.model or self._tts_model_for(request.language)
        started = time.perf_counter()
        try:
            audio = await self._synthesize(
                request.text,
                model=model,
                encoding=request.encoding,
            )
        except Exception as exc:
            raise _voice_error(exc, "Speech synthesis failed") from exc
        return VoiceResponse(
            audio=audio,
            mime_type=self._audio_mime_type,
            telemetry=_voice_telemetry(self.name, model, started),
        )


class TextOnlyVoiceProvider:
    """Deterministic fallback when audio output is disabled or unavailable.

    It answers synthesis with the same words as text and refuses transcription, because
    there is no honest text-only answer to "what did the patient say".
    """

    name = "text_only"
    capabilities = frozenset({GenerationCapability.TEXT})

    async def transcribe(self, request: VoiceTranscriptionRequest) -> VoiceResponse:
        raise GenerationProviderError(
            GenerationErrorCode.UNSUPPORTED, "Text-only voice cannot transcribe audio"
        )

    async def synthesize(self, request: VoiceSynthesisRequest) -> VoiceResponse:
        return VoiceResponse(
            transcript=" ".join(request.text.split()),
            telemetry=GenerationTelemetry(
                provider=self.name,
                model="none",
                latency_ms=0,
                fallback_path=[self.name],
            ),
        )


class VoiceFallbackProvider:
    """Try voice providers in order and make the selection visible to callers.

    A provider that cannot do the requested direction answers `UNSUPPORTED` and is
    stepped over silently, so refusing a direction never reads as an outage.
    """

    name = "fallback"
    capabilities = frozenset(
        {
            GenerationCapability.TEXT,
            GenerationCapability.AUDIO_INPUT,
            GenerationCapability.AUDIO_OUTPUT,
        }
    )

    def __init__(self, providers: list[VoiceProvider]) -> None:
        if not providers:
            raise ValueError("At least one voice provider is required")
        self.providers = providers

    async def transcribe(self, request: VoiceTranscriptionRequest) -> VoiceResponse:
        return await self._attempt(
            lambda provider: provider.transcribe(request),
            "No configured voice provider could transcribe audio",
        )

    async def synthesize(self, request: VoiceSynthesisRequest) -> VoiceResponse:
        return await self._attempt(
            lambda provider: provider.synthesize(request),
            "No configured voice provider could produce speech",
        )

    async def _attempt(
        self,
        call: Callable[[VoiceProvider], Awaitable[VoiceResponse]],
        exhausted: str,
    ) -> VoiceResponse:
        failures: list[str] = []
        for provider in self.providers:
            try:
                response = await call(provider)
            except GenerationProviderError as exc:
                # A provider that does not serve this direction is not a failure worth
                # reporting to the next one; anything else is, so the path shows it.
                if exc.code is not GenerationErrorCode.UNSUPPORTED:
                    failures.append(f"{provider.name}:{exc.code.value}")
                continue
            response.telemetry.fallback_path = failures + [provider.name]
            return response
        raise GenerationProviderError(GenerationErrorCode.UNAVAILABLE, exhausted)


def _voice_telemetry(provider: str, model: str, started: float) -> GenerationTelemetry:
    return GenerationTelemetry(
        provider=provider,
        model=model,
        latency_ms=round((time.perf_counter() - started) * 1000),
    )


def _voice_error(exc: Exception, message: str) -> GenerationProviderError:
    """Map a client failure onto the shared error taxonomy.

    A missing credential is a configuration fault, not an outage: reporting it as
    `UNAVAILABLE` would send a caller into retry and fallback for something no retry
    can fix.
    """
    if isinstance(exc, GenerationProviderError):
        return exc
    if isinstance(exc, TimeoutError):
        return GenerationProviderError(GenerationErrorCode.TIMEOUT, message)
    if isinstance(exc, ValueError):
        return GenerationProviderError(GenerationErrorCode.CONFIGURATION, message)
    return GenerationProviderError(GenerationErrorCode.UNAVAILABLE, message)
