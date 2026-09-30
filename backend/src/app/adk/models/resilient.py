"""Bound ADK model calls and stop repeatedly calling an unhealthy provider.

ADK's ``FallbackModel`` handles provider HTTP failures, but it deliberately does not
invent a deadline. A provider that accepts a request and then produces no event can
therefore hold a patient turn open indefinitely. It also cannot fall back after a
streaming model has yielded anything, because joining two providers' partial answers
would corrupt the response.

``ResilientLlm`` closes both gaps at the model boundary:

* every attempt has a hard wall-clock deadline;
* responses are buffered until that attempt completes, so a timeout can still move to
  the declared fallback without exposing half an answer;
* managed open-weight models can use a short process-local circuit breaker, turning a
  burst of 429s into immediate fallback instead of repeating the same failed request.

The wrapper raises errors carrying ordinary retriable HTTP status codes. That keeps the
fallback policy in ADK's supported ``FallbackModel`` rather than duplicating its request
snapshot and rollback logic here.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import aclosing
from threading import Lock
from typing import Any, ClassVar

from google.adk.models import BaseLlm
from pydantic import Field

_RETRIABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class ModelAttemptDeadlineError(TimeoutError):
    """A model attempt exceeded its patient-facing wall-clock deadline."""

    status_code = 504

    def __init__(self, model: str, timeout_seconds: float) -> None:
        super().__init__(f"Model {model} exceeded its {timeout_seconds:g}s deadline")


class ModelCircuitOpenError(RuntimeError):
    """The provider recently failed and should be skipped during its cooldown."""

    status_code = 503

    def __init__(self, model: str) -> None:
        super().__init__(f"Model {model} is temporarily bypassed after a provider failure")


class ResilientLlm(BaseLlm):
    """Wrap one ADK model with a deadline and an optional shared circuit breaker."""

    delegate: BaseLlm
    timeout_seconds: float = Field(gt=0)
    circuit_breaker: bool = False
    cooldown_seconds: float = Field(default=60.0, gt=0)

    _open_until: ClassVar[dict[str, float]] = {}
    _circuit_lock: ClassVar[Lock] = Lock()

    @property
    def capabilities(self) -> Any:
        return self.delegate.capabilities

    @classmethod
    def reset_circuits(cls) -> None:
        """Clear process-local cooldowns. Used by tests and runner resets."""
        with cls._circuit_lock:
            cls._open_until.clear()

    def _is_open(self) -> bool:
        if not self.circuit_breaker:
            return False
        now = time.monotonic()
        with self._circuit_lock:
            open_until = self._open_until.get(self.model, 0.0)
            if open_until <= now:
                self._open_until.pop(self.model, None)
                return False
            return True

    def _open_circuit(self) -> None:
        if not self.circuit_breaker:
            return
        with self._circuit_lock:
            self._open_until[self.model] = time.monotonic() + self.cooldown_seconds

    def _close_circuit(self) -> None:
        if not self.circuit_breaker:
            return
        with self._circuit_lock:
            self._open_until.pop(self.model, None)

    @staticmethod
    def _status_code(error: BaseException) -> int | None:
        for candidate in (
            getattr(error, "status_code", None),
            getattr(error, "code", None),
            getattr(getattr(error, "response", None), "status_code", None),
        ):
            if isinstance(candidate, int):
                return candidate
        return None

    async def generate_content_async(
        self, llm_request: Any, stream: bool = False
    ) -> AsyncGenerator[Any, None]:
        """Return one complete attempt or a retriable failure—never a partial answer."""
        if self._is_open():
            raise ModelCircuitOpenError(self.model)

        buffered: list[Any] = []
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with aclosing(
                    self.delegate.generate_content_async(llm_request, stream=stream)
                ) as responses:
                    async for response in responses:
                        buffered.append(response)
        except TimeoutError as error:
            self._open_circuit()
            raise ModelAttemptDeadlineError(self.model, self.timeout_seconds) from error
        except Exception as error:
            if self._status_code(error) in _RETRIABLE_STATUS_CODES:
                self._open_circuit()
            raise

        self._close_circuit()
        for response in buffered:
            yield response
