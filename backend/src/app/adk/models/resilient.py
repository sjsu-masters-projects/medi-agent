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
import math
import random
import time
from collections.abc import AsyncGenerator
from contextlib import aclosing
from copy import deepcopy
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from threading import Lock
from typing import Any, ClassVar

from google.adk.models import BaseLlm
from pydantic import Field

from app.core.model_traffic import model_slot, record_attempt

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
    retry_429: bool = False
    endpoint: str = "global"
    fallback_candidate: bool = False

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
            self._record(503, 0, "circuit_open", time.monotonic())
            raise ModelCircuitOpenError(self.model)

        deadline = time.monotonic() + self.timeout_seconds
        try:
            async with asyncio.timeout_at(deadline):
                buffered = await self._attempts(llm_request, stream, deadline)
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

    def _record(self, status: int | None, retry: int, cause: str, started: float) -> None:
        record_attempt(
            model=self.model,
            endpoint=self.endpoint,
            status=status,
            retry_count=retry,
            cause=cause,
            started=started,
            fallback_candidate=self.fallback_candidate,
        )

    @staticmethod
    def _retry_delay(error: Exception) -> float:
        response = getattr(error, "response", None)
        headers = getattr(response, "headers", None) or getattr(error, "headers", {})
        if not hasattr(headers, "get"):
            headers = {}
        value = headers.get("Retry-After") or headers.get("retry-after")
        if value is not None:
            try:
                delay = float(value)
            except (ValueError, TypeError):
                try:
                    date = parsedate_to_datetime(str(value))
                    delay = (date - datetime.now(UTC)).total_seconds()
                except (ValueError, TypeError, OverflowError):
                    delay = -1
            if not math.isfinite(delay):
                return float("inf")
            if delay >= 0:
                return delay + random.uniform(0.0, 0.1)
        return random.uniform(0.2, 0.4)

    async def _attempts(self, request: Any, stream: bool, deadline: float) -> list[Any]:
        original = deepcopy(request)
        for retry in range(2 if self.retry_429 else 1):
            started = time.monotonic()
            buffered: list[Any] = []
            try:
                async with (
                    model_slot(self.model, self.endpoint),
                    aclosing(
                        self.delegate.generate_content_async(
                            request if retry == 0 else deepcopy(original), stream=stream
                        )
                    ) as responses,
                ):
                    async for response in responses:
                        buffered.append(response)
            except asyncio.CancelledError:
                expired = time.monotonic() >= deadline
                self._record(
                    504 if expired else None, retry, "deadline" if expired else "cancelled", started
                )
                raise
            except Exception as error:
                status = self._status_code(error)
                delay = self._retry_delay(error) if status == 429 else 0
                can_retry = (
                    self.retry_429
                    and retry == 0
                    and status == 429
                    and delay <= 1.0
                    and delay + 0.5 < deadline - time.monotonic()
                )
                cause = "provider_error"
                if status == 429:
                    cause = "retry_exhausted" if retry else "retry_delay_exceeds_budget"
                self._record(status, retry, "retry_429" if can_retry else cause, started)
                if not can_retry:
                    raise
                await asyncio.sleep(delay)
            else:
                self._record(200, retry, "none", started)
                return buffered
        raise AssertionError("Unreachable retry state")
