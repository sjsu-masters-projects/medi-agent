"""Transport-neutral model admission, scoped to one process and event loop."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from weakref import WeakKeyDictionary

from app.config import settings

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


@asynccontextmanager
async def model_slot(model: str, endpoint: str, *, background: bool = False) -> AsyncIterator[None]:
    """Bound in-flight calls and space starts, including retries; cancellation frees slots.

    The caller owns the wall-clock deadline, including this admission wait. Keys
    include endpoint so independent serving pools do not block one another.
    """
    pool = _gates.setdefault(asyncio.get_running_loop(), {})
    gate = pool.setdefault(
        (model, endpoint),
        _Gate(
            asyncio.Semaphore(settings.model_max_concurrency),
            asyncio.Semaphore(max(1, settings.model_max_concurrency - 1)),
        ),
    )
    # Acquire background admission first: waiting jobs must not occupy shared slots.
    if background:
        await gate.background_slots.acquire()
    try:
        async with gate.slots:
            async with gate.starts:
                await asyncio.sleep(max(0.0, gate.next_start - time.monotonic()))
                gate.next_start = time.monotonic() + settings.model_min_start_interval_seconds
            yield
    finally:
        if background:
            gate.background_slots.release()


def record_attempt(
    *,
    model: str,
    endpoint: str,
    status: int | None,
    retry_count: int,
    cause: str,
    started: float,
    fallback_candidate: bool = False,
) -> None:
    """Allowlisted metadata only: no exception text, prompt, identifiers or URL."""
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
                "latency_ms": round((time.monotonic() - started) * 1000),
            }
        },
    )
