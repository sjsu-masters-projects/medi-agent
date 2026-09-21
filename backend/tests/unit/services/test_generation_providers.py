"""Tests for provider-neutral generation contracts and deterministic fallback."""

from __future__ import annotations

import pytest

from app.models.generation import (
    GenerationErrorCode,
    GenerationProviderError,
    GenerationRequest,
    GenerationResponse,
    GenerationTelemetry,
    VoiceSynthesisRequest,
    VoiceTranscriptionRequest,
)
from app.services.generation_providers import (
    DeepgramVoiceProvider,
    TextFallbackProvider,
    TextOnlyVoiceProvider,
    VoiceFallbackProvider,
)


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
    response = await TextOnlyVoiceProvider().synthesize(
        VoiceSynthesisRequest(text="  Please   review this.  ")
    )

    assert response.transcript == "Please review this."
    assert response.audio is None
    assert response.telemetry.fallback_path == ["text_only"]


@pytest.mark.asyncio
async def test_text_only_voice_provider_refuses_to_transcribe() -> None:
    """There is no honest text-only answer to "what did the patient say"."""
    with pytest.raises(GenerationProviderError) as caught:
        await TextOnlyVoiceProvider().transcribe(
            VoiceTranscriptionRequest(audio=b"abc", mime_type="audio/webm")
        )

    assert caught.value.code is GenerationErrorCode.UNSUPPORTED


def _deepgram(
    *,
    transcribe: object = None,
    synthesize: object = None,
    tts_models: dict[str, str] | None = None,
) -> DeepgramVoiceProvider:
    async def _default_transcribe(audio: bytes, **_: object) -> str:
        return "  heard this  "

    async def _default_synthesize(text: str, **_: object) -> bytes:
        return b"audio-bytes"

    models = tts_models or {"en-US": "aura-en", "es-MX": "aura-es"}
    return DeepgramVoiceProvider(
        transcribe=transcribe or _default_transcribe,  # type: ignore[arg-type]
        synthesize=synthesize or _default_synthesize,  # type: ignore[arg-type]
        stt_model="nova-3",
        tts_model_for=lambda language: models[language],
    )


@pytest.mark.asyncio
async def test_deepgram_provider_records_model_and_latency_on_transcription() -> None:
    response = await _deepgram().transcribe(
        VoiceTranscriptionRequest(audio=b"abc", mime_type="audio/webm", language="es-MX")
    )

    assert response.transcript == "heard this"
    assert response.telemetry.provider == "deepgram"
    assert response.telemetry.model == "nova-3"
    assert response.telemetry.latency_ms >= 0


@pytest.mark.asyncio
async def test_synthesis_voice_follows_the_patients_locale() -> None:
    """A bilingual product cannot answer a Spanish patient in an English voice."""
    response = await _deepgram().synthesize(
        VoiceSynthesisRequest(text="Tome su medicamento.", language="es-MX")
    )

    assert response.audio == b"audio-bytes"
    assert response.mime_type == "audio/mpeg"
    assert response.telemetry.model == "aura-es"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (TimeoutError("slow"), GenerationErrorCode.TIMEOUT),
        # A missing key is a configuration fault. Reporting it as an outage would send
        # the caller into retries that cannot possibly fix it.
        (ValueError("DEEPGRAM_API_KEY not set in .env"), GenerationErrorCode.CONFIGURATION),
        (RuntimeError("502 from upstream"), GenerationErrorCode.UNAVAILABLE),
    ],
)
async def test_client_failures_map_onto_the_shared_error_taxonomy(
    raised: Exception, expected: GenerationErrorCode
) -> None:
    async def _fail(*_: object, **__: object) -> str:
        raise raised

    with pytest.raises(GenerationProviderError) as caught:
        await _deepgram(transcribe=_fail).transcribe(
            VoiceTranscriptionRequest(audio=b"abc", mime_type="audio/webm")
        )

    assert caught.value.code is expected


@pytest.mark.asyncio
async def test_speech_outage_degrades_to_the_words_instead_of_raising() -> None:
    async def _fail(*_: object, **__: object) -> bytes:
        raise RuntimeError("deepgram down")

    chain = VoiceFallbackProvider([_deepgram(synthesize=_fail), TextOnlyVoiceProvider()])

    response = await chain.synthesize(VoiceSynthesisRequest(text="Take  your  medicine."))

    # The guarantee: audio is gone, the reviewed wording is not.
    assert response.audio is None
    assert response.transcript == "Take your medicine."
    assert response.telemetry.fallback_path == ["deepgram:unavailable", "text_only"]


@pytest.mark.asyncio
async def test_a_provider_that_cannot_hear_is_stepped_over_not_blamed() -> None:
    chain = VoiceFallbackProvider([TextOnlyVoiceProvider(), _deepgram()])

    response = await chain.transcribe(
        VoiceTranscriptionRequest(audio=b"abc", mime_type="audio/webm")
    )

    # `text_only` refused the direction, which is not a failure worth recording.
    assert response.transcript == "heard this"
    assert response.telemetry.fallback_path == ["deepgram"]


@pytest.mark.asyncio
async def test_transcription_fails_loudly_when_nothing_can_hear() -> None:
    """Synthesis may degrade to text; transcription may not invent one."""
    chain = VoiceFallbackProvider([TextOnlyVoiceProvider()])

    with pytest.raises(GenerationProviderError) as caught:
        await chain.transcribe(VoiceTranscriptionRequest(audio=b"abc", mime_type="audio/webm"))

    assert caught.value.code is GenerationErrorCode.UNAVAILABLE
