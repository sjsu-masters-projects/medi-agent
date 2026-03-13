"""Client modules for external services."""

from app.clients.deepgram_client import (
    generate_speech_async,
    get_async_deepgram_client,
    transcribe_audio_file_async,
)
from app.clients.supabase import get_admin_client

__all__ = [
    "get_admin_client",
    "get_async_deepgram_client",
    "transcribe_audio_file_async",
    "generate_speech_async",
]
