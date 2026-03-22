"""Deepgram MCP Server — voice transcription (STT) and speech generation (TTS).

Tools: transcribe_audio, generate_speech, transcribe_patient_message.
Uses a shared async Deepgram client via lazy init.
"""

import base64
from io import BytesIO
from typing import Any

import structlog

from app.clients.deepgram_client import (
    generate_speech_async,
    get_async_deepgram_client,
    transcribe_audio_file_async,
)
from app.mcp.base import MCPServer

logger = structlog.get_logger(__name__)


class DeepgramServer(MCPServer):
    """MCP server for Deepgram voice operations."""

    def __init__(self) -> None:
        super().__init__(
            name="deepgram",
            description="Voice transcription (STT) and speech generation (TTS)",
        )
        self._client: Any = None

    @property
    def client(self) -> Any:  # type: ignore[no-untyped-def]
        """Lazy-load async Deepgram client."""
        if self._client is None:
            self._client = get_async_deepgram_client()
        return self._client

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "transcribe_audio",
                "description": "Transcribe audio to text. Accepts base64-encoded audio.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "audio_base64": {
                            "type": "string",
                            "description": "Base64-encoded audio data",
                        },
                        "model": {
                            "type": "string",
                            "description": "Deepgram model",
                            "default": "nova-3",
                        },
                        "language": {
                            "type": "string",
                            "description": "Language code",
                            "default": "en",
                        },
                        "smart_format": {
                            "type": "boolean",
                            "description": "Smart formatting",
                            "default": True,
                        },
                    },
                    "required": ["audio_base64"],
                },
            },
            {
                "name": "generate_speech",
                "description": "Convert text to speech. Returns base64-encoded audio.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to convert to speech"},
                        "model": {
                            "type": "string",
                            "description": "Voice model",
                            "default": "aura-2-asteria-en",
                        },
                        "encoding": {
                            "type": "string",
                            "description": "Audio format",
                            "default": "mp3",
                        },
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "transcribe_patient_message",
                "description": "Transcribe patient voice message with medical-optimised settings.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "audio_base64": {
                            "type": "string",
                            "description": "Base64-encoded audio data",
                        },
                        "patient_id": {"type": "string", "description": "Patient UUID for context"},
                    },
                    "required": ["audio_base64", "patient_id"],
                },
            },
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        match tool_name:
            case "transcribe_audio":
                return await self._transcribe_audio(
                    audio_base64=arguments["audio_base64"],
                    model=arguments.get("model", "nova-3"),
                    language=arguments.get("language", "en"),
                    smart_format=arguments.get("smart_format", True),
                )
            case "generate_speech":
                return await self._generate_speech(
                    text=arguments["text"],
                    model=arguments.get("model", "aura-2-asteria-en"),
                    encoding=arguments.get("encoding", "mp3"),
                )
            case "transcribe_patient_message":
                return await self._transcribe_audio(
                    audio_base64=arguments["audio_base64"],
                    model="nova-3",
                    language="en",
                    smart_format=True,
                    patient_id=arguments["patient_id"],
                )
        raise ValueError(f"Unknown tool: {tool_name}")

    # ── Tool implementations ────────────────────────────

    async def _transcribe_audio(
        self,
        audio_base64: str,
        model: str = "nova-3",
        language: str = "en",
        smart_format: bool = True,
        patient_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            audio_bytes = base64.b64decode(audio_base64)
            transcript = await transcribe_audio_file_async(
                audio_file=BytesIO(audio_bytes),
                model=model,
                language=language,
                smart_format=smart_format,
            )
            result: dict[str, Any] = {
                "transcript": transcript,
                "model": model,
                "language": language,
                "success": True,
            }
            if patient_id:
                result["patient_id"] = patient_id
            return result
        except Exception as e:
            logger.error("transcribe_error", model=model, error=str(e))
            result = {"transcript": "", "model": model, "success": False, "error": str(e)}
            if patient_id:
                result["patient_id"] = patient_id
            return result

    async def _generate_speech(
        self,
        text: str,
        model: str = "aura-2-asteria-en",
        encoding: str = "mp3",
    ) -> dict[str, Any]:
        try:
            audio_bytes = await generate_speech_async(text=text, model=model, encoding=encoding)
            return {
                "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
                "model": model,
                "encoding": encoding,
                "text_length": len(text),
                "audio_size": len(audio_bytes),
                "success": True,
            }
        except Exception as e:
            logger.error("tts_error", model=model, error=str(e))
            return {"audio_base64": "", "model": model, "success": False, "error": str(e)}


deepgram_server = DeepgramServer()
