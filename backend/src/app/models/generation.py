"""Provider-neutral text and voice generation contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class GenerationCapability(StrEnum):
    TEXT = "text"
    STRUCTURED_OUTPUT = "structured_output"
    STREAMING = "streaming"
    TOOL_CALLING = "tool_calling"
    AUDIO_INPUT = "audio_input"
    AUDIO_OUTPUT = "audio_output"


class GenerationErrorCode(StrEnum):
    AUTHENTICATION = "authentication"
    CONFIGURATION = "configuration"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    INVALID_RESPONSE = "invalid_response"
    UNSUPPORTED = "unsupported"


class GenerationProviderError(Exception):
    def __init__(self, code: GenerationErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class GenerationRequest(BaseModel):
    prompt: str = Field(min_length=1)
    system_instruction: str | None = None
    temperature: float = Field(default=0.2, ge=0, le=1)
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    task: str = Field(default="general", min_length=1, max_length=100)


class GenerationTelemetry(BaseModel):
    provider: str
    model: str
    latency_ms: int = Field(ge=0)
    usage: dict[str, int] = Field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    fallback_path: list[str] = Field(default_factory=list)


class GenerationResponse(BaseModel):
    text: str
    telemetry: GenerationTelemetry


class VoiceResponse(BaseModel):
    transcript: str | None = None
    audio: bytes | None = None
    mime_type: str | None = None
    telemetry: GenerationTelemetry
