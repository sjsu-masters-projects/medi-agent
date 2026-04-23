"""Simple async-safe sliding window rate limiting helpers."""

from __future__ import annotations

import asyncio
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    """Decision payload returned by the rate limiter."""

    allowed: bool
    retry_after_seconds: int = 0
    remaining: int = 0


class SlidingWindowRateLimiter:
    """In-memory sliding-window limiter keyed by arbitrary string values."""

    def __init__(self, *, limit: int, window_seconds: int) -> None:
        if limit <= 0:
            raise ValueError("limit must be greater than 0")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be greater than 0")

        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> RateLimitResult:
        """Record one event for key and return allow/deny decision."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        async with self._lock:
            events = self._events[key]

            while events and events[0] <= cutoff:
                events.popleft()

            if len(events) >= self.limit:
                retry_after = max(1, math.ceil(self.window_seconds - (now - events[0])))
                return RateLimitResult(allowed=False, retry_after_seconds=retry_after, remaining=0)

            events.append(now)
            remaining = max(0, self.limit - len(events))
            return RateLimitResult(allowed=True, retry_after_seconds=0, remaining=remaining)


# SOAP note generation is expensive (LLM + DB aggregation). Keep bursts low per clinician.
soap_note_rate_limiter = SlidingWindowRateLimiter(limit=3, window_seconds=60)
