"""MCP servers for AI agent tool access.

- Supabase: Patient data queries (medications, conditions, allergies, adherence)
- Deepgram: Voice transcription (STT) and speech generation (TTS)
"""

from app.mcp.deepgram_server import deepgram_server
from app.mcp.supabase_server import supabase_server

__all__ = [
    "supabase_server",
    "deepgram_server",
]
