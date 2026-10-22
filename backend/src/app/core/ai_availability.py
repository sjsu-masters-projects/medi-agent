"""Bounded model availability counters (AI-003).

Every provider attempt is counted per workload, model, outcome and route (primary or
fallback), with a fixed latency histogram, in memory, and flushed to
``ai_availability_buckets`` (migration 090) at most once every ``flush_seconds`` from one
supervised background task with its own one-thread pool. Nothing is stored per request and
nothing identifies a patient: only the registry workload, the configured model id, a closed
outcome vocabulary and numbers. Memory is bounded by ``MAX_KEYS``; a key past it is counted as
dropped. A failed flush keeps its counts for the next one (up to the same bound); a flush whose
acknowledgement is lost may be applied twice, so counts are approximate.

The read side (``summarize``) merges the buckets of a rolling window and computes percentiles
from the histogram's bin edges, so a reported latency is the upper edge of the bin it falls in.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from typing import Any

from app.config import settings
from app.core.db_pools import run_telemetry_db
from app.core.structured_logging import log_event

logger = logging.getLogger(__name__)

# Upper edges (ms) of the first nine bins; the tenth holds everything slower.
BIN_EDGES_MS = (250, 500, 1000, 2000, 4000, 8000, 12000, 20000, 40000)
MAX_KEYS = 300
MAX_ROWS_PER_FLUSH = 200
OUTCOMES = (
    "success",
    "timeout",
    "rate_limited",
    "server_error",
    "client_error",
    "circuit_open",
    "cancelled",
    "other",
)
FLUSH_TIMEOUT_SECONDS = 5.0

Key = tuple[str, str, str, bool]


def classify_outcome(status: int | None, cause: str) -> str:
    """Map a transport attempt to the closed outcome vocabulary."""
    if cause == "circuit_open":
        return "circuit_open"
    if cause in {"deadline", "cancelled_or_deadline"} or status == 504:
        return "timeout"
    if cause == "cancelled":
        return "cancelled"
    if status == 200 or (cause == "none" and status is None):
        return "success"
    if status == 429:
        return "rate_limited"
    if status is not None and 500 <= status <= 599:
        return "server_error"
    if status is not None and 400 <= status <= 499:
        return "client_error"
    return "other"


def _bin(latency_ms: int) -> int:
    for index, edge in enumerate(BIN_EDGES_MS):
        if latency_ms < edge:
            return index
    return len(BIN_EDGES_MS)


def _safe(value: str, limit: int) -> str:
    cleaned = "".join(c for c in value if c.isalnum() or c in "._/:-")[:limit]
    return cleaned or "unknown"


class AvailabilityRecorder:
    """Process-local counters; touched only on the event loop thread."""

    def __init__(self) -> None:
        self._counts: dict[Key, list[Any]] = {}
        self.dropped = 0
        self._last_flush = time.monotonic()
        self._task: asyncio.Task[None] | None = None

    def record(
        self, *, workload: str, model: str, outcome: str, fallback: bool, latency_ms: int
    ) -> None:
        key = (_safe(workload.lower(), 40), _safe(model, 80), outcome, bool(fallback))
        entry = self._counts.get(key)
        if entry is None:
            if len(self._counts) >= MAX_KEYS:
                self.dropped += 1
                return
            entry = self._counts[key] = [0, 0, [0] * (len(BIN_EDGES_MS) + 1)]
        latency = max(0, int(latency_ms))
        entry[0] += 1
        entry[1] += latency
        entry[2][_bin(latency)] += 1
        self._maybe_flush()

    def _maybe_flush(self) -> None:
        if not settings.ai_availability_enabled or self._task is not None:
            return
        if time.monotonic() - self._last_flush < settings.ai_availability_flush_seconds:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # a synchronous caller: the next attempt on a loop flushes
        self._task = loop.create_task(self._flush_supervised())

    def _take(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key in list(self._counts)[:MAX_ROWS_PER_FLUSH]:
            attempts, total, bins = self._counts.pop(key)
            workload, model, outcome, fallback = key
            rows.append(
                {
                    "workload": workload,
                    "model": model,
                    "outcome": outcome,
                    "fallback": fallback,
                    "attempts": attempts,
                    "latency_sum_ms": total,
                    "bins": bins,
                }
            )
        return rows

    def _restore(self, rows: Iterable[dict[str, Any]]) -> None:
        for row in rows:
            key = (row["workload"], row["model"], row["outcome"], row["fallback"])
            entry = self._counts.get(key)
            if entry is None:
                if len(self._counts) >= MAX_KEYS:
                    self.dropped += row["attempts"]
                    continue
                self._counts[key] = [row["attempts"], row["latency_sum_ms"], list(row["bins"])]
                continue
            entry[0] += row["attempts"]
            entry[1] += row["latency_sum_ms"]
            entry[2] = [a + b for a, b in zip(entry[2], row["bins"], strict=True)]

    async def _flush_supervised(self) -> None:
        try:
            await self.flush()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # telemetry must never reach a turn
            log_event(
                logger,
                "ai_availability.flush_failed",
                level=logging.WARNING,
                message="Availability counters could not be flushed",
                outcome=type(exc).__name__,
            )
        finally:
            self._task = None
            self._last_flush = time.monotonic()

    async def flush(self) -> bool:
        """Write the counters taken so far. On any failure they are kept for the next flush."""
        rows = self._take()
        if self.dropped:
            logger.info("ai_availability dropped=%d (key bound reached)", self.dropped)
            self.dropped = 0
        if not rows:
            return True
        from app.clients.supabase import get_admin_client

        client = get_admin_client()
        try:
            await asyncio.wait_for(
                run_telemetry_db(
                    lambda: client.rpc("record_ai_availability", {"p_rows": rows}).execute()
                ),
                timeout=FLUSH_TIMEOUT_SECONDS,
            )
        except BaseException:
            self._restore(rows)
            raise
        return True


recorder = AvailabilityRecorder()


# -- reading -----------------------------------------------------------------------------------


def _percentile(bins: list[int], fraction: float) -> int | None:
    total = sum(bins)
    if total == 0:
        return None
    target = max(1, int(-(-total * fraction // 1)))
    seen = 0
    for index, count in enumerate(bins):
        seen += count
        if seen >= target:
            return BIN_EDGES_MS[index] if index < len(BIN_EDGES_MS) else BIN_EDGES_MS[-1] * 2
    return None


def summarize(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge bucket rows into one entry per workload and model for the window."""
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        workload, model = str(row["workload"]), str(row["model"])
        entry = merged.setdefault(
            (workload, model),
            {
                "workload": workload,
                "model": model,
                "attempts": 0,
                "outcomes": dict.fromkeys(OUTCOMES, 0),
                "fallback_attempts": 0,
                "latency_sum_ms": 0,
                "bins": [0] * (len(BIN_EDGES_MS) + 1),
            },
        )
        attempts = int(row.get("attempts") or 0)
        outcome = str(row.get("outcome"))
        entry["attempts"] += attempts
        if outcome in entry["outcomes"]:
            entry["outcomes"][outcome] += attempts
        if row.get("fallback"):
            entry["fallback_attempts"] += attempts
        entry["latency_sum_ms"] += int(row.get("latency_sum_ms") or 0)
        bins = row.get("latency_bins") or []
        for index, count in enumerate(bins[: len(entry["bins"])]):
            entry["bins"][index] += int(count)
    result = []
    for entry in sorted(merged.values(), key=lambda e: (e["workload"], e["model"])):
        bins = entry.pop("bins")
        total = entry["attempts"]
        entry["latency_ms"] = {
            "p50": _percentile(bins, 0.5),
            "p95": _percentile(bins, 0.95),
            "p99": _percentile(bins, 0.99),
            "mean": round(entry["latency_sum_ms"] / total) if total else None,
        }
        entry.pop("latency_sum_ms")
        entry["success_rate"] = round(entry["outcomes"]["success"] / total, 4) if total else None
        result.append(entry)
    return result
