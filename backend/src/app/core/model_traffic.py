"""Transport-neutral model admission, scoped to one process and event loop."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from weakref import WeakKeyDictionary

from app.config import settings
from app.core.ai_availability import classify_outcome
from app.core.ai_availability import recorder as availability

logger = logging.getLogger(__name__)


@dataclass
class _Gate:
    slots: asyncio.Semaphore
    background_slots: asyncio.Semaphore
    starts: asyncio.Lock = field(default_factory=asyncio.Lock)
    next_start: float = 0.0


_gates: WeakKeyDictionary[asyncio.AbstractEventLoop, dict[tuple[str, str], _Gate]] = (
    WeakKeyDictionary()
)


class ModelAdmissionError(RuntimeError):
    """No model slot opened within the admission wait: the call is shed, not queued."""

    status_code = 503

    def __init__(self, model: str) -> None:
        super().__init__(f"Model {model} had no free slot in time")


_workload: ContextVar[str] = ContextVar("model_workload", default="unknown")


@contextmanager
def use_workload(name: str) -> Iterator[None]:
    """Label every attempt made inside this block (including background calls) with a workload."""
    token = _workload.set(name)
    try:
        yield
    finally:
        _workload.reset(token)


async def _admit(gate: _Gate, background: bool) -> list[asyncio.Semaphore]:
    """Take the slots, spacing starts. Returns what must be released."""
    held: list[asyncio.Semaphore] = []
    try:
        if background:
            await gate.background_slots.acquire()
            held.append(gate.background_slots)
        await gate.slots.acquire()
        held.append(gate.slots)
        async with gate.starts:
            await asyncio.sleep(max(0.0, gate.next_start - time.monotonic()))
            gate.next_start = time.monotonic() + settings.model_min_start_interval_seconds
    except BaseException:
        for semaphore in held:
            semaphore.release()
        raise
    return held


@asynccontextmanager
async def model_slot(model: str, endpoint: str, *, background: bool = False) -> AsyncIterator[None]:
    """Bound in-flight calls and space starts, including retries; cancellation frees slots.

    An interactive call waits at most ``model_admission_wait_seconds`` for a slot (OPS-006
    rule 14) and is then shed with :class:`ModelAdmissionError`, which the route treats as a
    retriable 503 (fallback model, then the reviewed unavailable reply). Background calls keep
    waiting: their callers own longer deadlines. The caller's deadline still bounds both.
    """
    pool = _gates.setdefault(asyncio.get_running_loop(), {})
    gate = pool.setdefault(
        (model, endpoint),
        _Gate(
            asyncio.Semaphore(settings.model_max_concurrency),
            asyncio.Semaphore(max(1, settings.model_max_concurrency - 1)),
        ),
    )
    try:
        if background:
            held = await _admit(gate, background)
        else:
            async with asyncio.timeout(settings.model_admission_wait_seconds):
                held = await _admit(gate, background)
    except TimeoutError:
        log_admission_shed(model)
        raise ModelAdmissionError(model) from None
    try:
        yield
    finally:
        for semaphore in held:
            semaphore.release()


def log_admission_shed(model: str) -> None:
    logger.warning("model_admission_shed model=%s", model, extra={"model_admission_shed": model})


def record_attempt(
    *,
    model: str,
    endpoint: str,
    status: int | None,
    retry_count: int,
    cause: str,
    started: float,
    fallback_candidate: bool = False,
    workload: str = "unknown",
) -> None:
    """Allowlisted metadata only: no exception text, prompt, identifiers or URL."""
    if workload == "unknown":
        workload = _workload.get()
    latency = round((time.monotonic() - started) * 1000)
    if settings.ai_availability_enabled:
        # Bounded in-memory counters (AI-003); the attempt is never delayed by them.
        availability.record(
            workload=workload,
            model=model,
            outcome=classify_outcome(status, cause),
            fallback=fallback_candidate,
            latency_ms=latency,
        )
    logger.info(
        "model_attempt model=%s endpoint=%s status=%s retry_count=%d "
        "fallback_cause=%s fallback_candidate=%s latency_ms=%d",
        model,
        endpoint,
        status,
        retry_count,
        cause,
        fallback_candidate,
        round((time.monotonic() - started) * 1000),
        extra={
            "model_attempt": {
                "model": model,
                "endpoint": endpoint,
                "status": status,
                "retry_count": retry_count,
                "fallback_cause": cause,
                "fallback_candidate": fallback_candidate,
                "workload": workload,
                "outcome": classify_outcome(status, cause),
                "latency_ms": latency,
            }
        },
    )
