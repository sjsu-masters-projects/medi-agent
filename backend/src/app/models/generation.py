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
    # The request itself was refused, typically a schema the endpoint will not accept.
    # Distinct from UNAVAILABLE so a dialect problem is never read as a capacity problem.
    INVALID_REQUEST = "invalid_request"
    # The answer ran out of token budget. A budget we chose is not a model's mistake,
    # so evaluation reports this separately instead of scoring it as a wrong answer.
    TRUNCATED = "truncated"
    UNSUPPORTED = "unsupported"


class GenerationProviderError(Exception):
    def __init__(self, code: GenerationErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


MAX_OUTPUT_TOKENS = 32_768
"""Ceiling for one response, sized for a reasoning model rather than a plain one.

Vertex counts thought tokens against the same budget as the answer, so a limit chosen for
a model that does not think truncates one that does — sometimes before it has emitted a
single visible character.
"""


class GenerationRequest(BaseModel):
    prompt: str = Field(min_length=1)
    system_instruction: str | None = None
    temperature: float = Field(default=0.2, ge=0, le=1)
    # The ceiling has to clear a reasoning model's thinking plus its answer: Vertex counts
    # thought tokens against the same budget, so a cap sized for a plain model truncates a
    # thinking one before it writes anything.
    max_tokens: int = Field(default=1024, ge=1, le=MAX_OUTPUT_TOKENS)
    task: str = Field(default="general", min_length=1, max_length=100)
    # JSON Schema the caller wants the answer to satisfy. Providers with native
    # structured output enforce it; the others leave validation to the caller.
    response_schema: dict[str, Any] | None = None


class GenerationTelemetry(BaseModel):
    provider: str
    model: str
    latency_ms: int = Field(ge=0)
    usage: dict[str, int] = Field(default_factory=dict)
    # Attempts beyond the first. Latency already includes the waits, so a retried call
    # is slow in the numbers the way it is slow for the person waiting on it.
    retries: int = Field(default=0, ge=0)
    # The provider's own word for why generation stopped, kept verbatim. Truncation has
    # to be read from here: inferring it from unparseable output charges a token budget
    # we set to the model as if it were a content mistake.
    finish_reason: str | None = None
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


class ProviderTrial(BaseModel):
    """One provider's answer to a shared request.

    A failed trial is recorded, not discarded. Reliability is one of the axes the
    evaluation compares providers on, so "this provider was unavailable" is a result
    worth keeping rather than an error to propagate.
    """

    provider: str
    model: str
    ok: bool
    text: str | None = None
    error_code: GenerationErrorCode | None = None
    latency_ms: int = Field(default=0, ge=0)
    telemetry: GenerationTelemetry | None = None


class ProviderComparison(BaseModel):
    """Every provider's answer to one request, for side-by-side evaluation.

    The prompt is deliberately absent. Comparisons run over clinical scenario text,
    and this object is meant to be logged, stored, and attached to evaluation records;
    carrying the prompt through all of that would spread the scenario content further
    than it needs to go. `prompt_digest` is enough to prove two trials answered the
    same input.
    """

    task: str
    prompt_digest: str = Field(min_length=1, max_length=64)
    trials: list[ProviderTrial]

    @property
    def succeeded(self) -> list[ProviderTrial]:
        return [trial for trial in self.trials if trial.ok]
