"""Deepgram client for voice transcription (STT) and speech generation (TTS)."""

from typing import BinaryIO

from deepgram import AsyncDeepgramClient, DeepgramClient

from app.config import settings


def get_deepgram_client() -> DeepgramClient:
    """Get sync Deepgram client. Uses DEEPGRAM_API_KEY from env."""
    if not settings.deepgram_api_key:
        raise ValueError("DEEPGRAM_API_KEY not set in .env")
    return DeepgramClient(api_key=settings.deepgram_api_key)


def get_async_deepgram_client() -> AsyncDeepgramClient:
    """Get async Deepgram client. Uses DEEPGRAM_API_KEY from env."""
    if not settings.deepgram_api_key:
        raise ValueError("DEEPGRAM_API_KEY not set in .env")
    return AsyncDeepgramClient(api_key=settings.deepgram_api_key)


# Helper functions for common operations


def transcribe_audio_file(
    audio_file: BinaryIO,
    model: str = "nova-3",
    language: str = "en",
    smart_format: bool = True,
) -> str:
    """Transcribe audio file to text. Returns the transcript string."""
    client = get_deepgram_client()
    audio_data = audio_file.read()

    response = client.listen.v1.media.transcribe_file(
        request=audio_data,
        model=model,
        language=language,
        smart_format=smart_format,
    )

    return response.results.channels[0].alternatives[0].transcript  # type: ignore[no-any-return]


def generate_speech(
    text: str,
    model: str = "aura-2-asteria-en",
    encoding: str = "mp3",
) -> bytes:
    """Convert text to speech. Returns audio bytes."""
    client = get_deepgram_client()

    response = client.speak.v1.audio.generate(
        text=text,
        model=model,
        encoding=encoding,
    )

    return response.stream.getvalue()  # type: ignore[no-any-return]


async def transcribe_audio_file_async(
    audio_file: BinaryIO,
    model: str = "nova-3",
    language: str = "en",
    smart_format: bool = True,
) -> str:
    """Async transcribe audio file to text. Returns the transcript string."""
    client = get_async_deepgram_client()
    audio_data = audio_file.read()

    response = await client.listen.v1.media.transcribe_file(
        request=audio_data,
        model=model,
        language=language,
        smart_format=smart_format,
    )

    return response.results.channels[0].alternatives[0].transcript  # type: ignore[no-any-return]


async def generate_speech_async(
    text: str,
    model: str = "aura-2-asteria-en",
    encoding: str = "mp3",
) -> bytes:
    """Async convert text to speech. Returns audio bytes."""
    client = get_async_deepgram_client()

    # Deepgram async returns a generator, need to collect chunks
    response = client.speak.v1.audio.generate(
        text=text,
        model=model,
        encoding=encoding,
    )

    # Collect all audio chunks
    audio_chunks = []
    async for chunk in response:
        audio_chunks.append(chunk)

    return b"".join(audio_chunks)
