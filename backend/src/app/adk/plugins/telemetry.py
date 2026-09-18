"""Record what each agent's model call cost and how it ended.

WS1 stopped the legacy router discarding its telemetry; this is the same fact collected
from the agent runtime, written to the same table (`model_invocation_events`, migration
035) through the same service. The questions it answers are the ones the routing table was
chosen on and then stopped being measured: which agent is slow, which model actually
answered, how often an answer is truncated, and what it costs.

Two details decide whether the numbers are real:

**Only the final response is recorded.** Under SSE streaming `after_model_callback` fires
for every partial chunk. Recording each one would write a row per token-chunk, flooding
the table and making latency meaningless.

**The SDK's token field names are not the service's.** `prompt_token_count`,
`candidates_token_count` and `thoughts_token_count` are mapped explicitly here; assuming
they matched would have written `NULL` into every token column without failing anything.
"""

from __future__ import annotations

import time
from typing import Any

from google.adk.plugins import BasePlugin

from app.models.generation import GenerationTelemetry
from app.services.model_telemetry_service import schedule_generation_record

_UNKNOWN = "unknown"


def _usage(llm_response: Any) -> dict[str, int]:
    """Map the SDK's usage metadata onto the names the telemetry table stores.

    Thinking is billed inside the completion total, so `thoughts_token_count` is kept
    separate rather than folded into the output count — a reasoning model given the same
    budget as a plain one has less of it left for the answer, and that is only visible if
    the two are recorded apart.
    """
    metadata = getattr(llm_response, "usage_metadata", None)
    if metadata is None:
        return {}
    mapped = {
        "input_tokens": getattr(metadata, "prompt_token_count", None),
        "output_tokens": getattr(metadata, "candidates_token_count", None),
        "reasoning_tokens": getattr(metadata, "thoughts_token_count", None),
    }
    return {key: value for key, value in mapped.items() if isinstance(value, int)}


def _finish_reason(llm_response: Any) -> str | None:
    """`LlmResponse` exposes this directly, not nested under `.candidates`.

    The client's helper of the same name reads the nested shape, so reusing it here would
    return `None` for every call and quietly lose the truncation signal.
    """
    reason = getattr(llm_response, "finish_reason", None)
    if reason is None:
        return None
    return str(getattr(reason, "name", reason))


class TelemetryPlugin(BasePlugin):
    """Time each model call and record how it ended."""

    def __init__(self) -> None:
        super().__init__(name="telemetry")
        # Keyed per in-flight call rather than held in session state: a start time is
        # scaffolding for one request, not something that belongs in durable state.
        self._started: dict[str, float] = {}

    @staticmethod
    def _key(callback_context: Any) -> str:
        invocation = getattr(callback_context, "invocation_id", None) or _UNKNOWN
        agent = getattr(callback_context, "agent_name", None) or _UNKNOWN
        return f"{invocation}:{agent}"

    async def before_model_callback(self, *, callback_context: Any, llm_request: Any) -> None:
        """Start the clock. Returning None lets the request proceed untouched."""
        self._started[self._key(callback_context)] = time.perf_counter()
        return None

    async def after_model_callback(self, *, callback_context: Any, llm_response: Any) -> None:
        """Record the finished call. Returning None leaves the response unmodified."""
        if getattr(llm_response, "partial", False):
            # A streaming chunk, not an answer. The final response arrives separately.
            return None

        self._record(
            callback_context,
            model=getattr(llm_response, "model_version", None),
            succeeded=not getattr(llm_response, "error_code", None),
            finish_reason=_finish_reason(llm_response),
            error_code=getattr(llm_response, "error_code", None),
            usage=_usage(llm_response),
        )
        return None

    async def on_model_error_callback(
        self, *, callback_context: Any, llm_request: Any, error: Exception
    ) -> None:
        """A call that never returned is still a fact about the model's reliability.

        Recorded with the error's type rather than its message: an exception string can
        carry prompt fragments, and this table must never become another place a record
        leaks from.
        """
        self._record(
            callback_context,
            model=getattr(llm_request, "model", None),
            succeeded=False,
            finish_reason=None,
            error_code=type(error).__name__,
            usage={},
        )
        return None

    def _record(
        self,
        callback_context: Any,
        *,
        model: str | None,
        succeeded: bool,
        finish_reason: str | None,
        error_code: str | None,
        usage: dict[str, int],
    ) -> None:
        key = self._key(callback_context)
        started = self._started.pop(key, None)
        latency_ms = 0 if started is None else round((time.perf_counter() - started) * 1000)

        agent = str(getattr(callback_context, "agent_name", None) or _UNKNOWN)
        telemetry = GenerationTelemetry(
            provider="adk",
            model=str(model or _UNKNOWN),
            latency_ms=latency_ms,
            usage=usage,
            finish_reason=finish_reason,
        )
        # Scheduled, not awaited: this runs on every model call, and a stalled database
        # must not spend a patient's latency budget on bookkeeping.
        schedule_generation_record(
            workload=agent,
            telemetry=telemetry,
            succeeded=succeeded,
            error_code=error_code,
        )
