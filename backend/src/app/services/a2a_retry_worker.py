"""Background worker that re-drives retryable A2A tasks."""

from __future__ import annotations

import asyncio
import logging

from supabase import Client

from app.services.a2a_task_service import A2ATaskService

logger = logging.getLogger(__name__)

# Ceiling on the failure backoff: five minutes between attempts during a sustained
# outage, which is quiet enough for the logs and prompt enough on recovery.
_MAX_BACKOFF_SECONDS = 300


class A2ARetryWorker:
    """Poll and process A2A tasks scheduled for retry."""

    def __init__(
        self, db: Client, *, poll_interval_seconds: int = 15, batch_size: int = 25
    ) -> None:
        self._service = A2ATaskService(db)
        self._poll_interval_seconds = max(1, poll_interval_seconds)
        self._batch_size = max(1, min(batch_size, 200))
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="a2a-retry-worker")

    async def stop(self) -> None:
        self._stop_event.set()
        if not self._task:
            return
        await self._task
        self._task = None

    def _backoff_seconds(self, consecutive_failures: int) -> int:
        """Poll interval doubled per consecutive failure, capped.

        The cap keeps recovery prompt: once the dependency returns, the worker resumes
        within `_MAX_BACKOFF_SECONDS` rather than after an ever-growing sleep.
        """
        exponent = min(consecutive_failures - 1, 10)
        return int(min(self._poll_interval_seconds * (2**exponent), _MAX_BACKOFF_SECONDS))

    async def _run_loop(self) -> None:
        logger.info(
            "A2A retry worker started (poll=%ss, batch=%s)",
            self._poll_interval_seconds,
            self._batch_size,
        )
        consecutive_failures = 0
        while not self._stop_event.is_set():
            try:
                summary = await self._service.process_due_retries(self._batch_size)
                consecutive_failures = 0
                if summary["scanned"] > 0:
                    logger.info(
                        "A2A retry batch processed: scanned=%s completed=%s rescheduled=%s "
                        "dead_lettered=%s failed=%s",
                        summary["scanned"],
                        summary["completed"],
                        summary["rescheduled"],
                        summary["dead_lettered"],
                        summary["failed"],
                    )
            except Exception as exc:
                consecutive_failures += 1
                # A database outage fails every cycle. At a fixed poll interval that is a
                # traceback every few seconds for as long as the outage lasts, which
                # buries the incident in its own logs and keeps hammering the dependency.
                # Log the detail once, then thin out while the failure persists.
                if consecutive_failures == 1:
                    if self._service.is_transient_supabase_error(exc):
                        logger.warning(
                            "A2A retry worker transient Supabase error; backing off: %s",
                            exc,
                        )
                    else:
                        logger.exception("A2A retry worker cycle failed: %s", exc)
                else:
                    logger.warning(
                        "A2A retry worker still failing (%s consecutive); next attempt in %ss: %s",
                        consecutive_failures,
                        self._backoff_seconds(consecutive_failures),
                        exc,
                    )

            delay = (
                self._poll_interval_seconds
                if consecutive_failures == 0
                else self._backoff_seconds(consecutive_failures)
            )
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
            except TimeoutError:
                continue

        logger.info("A2A retry worker stopped")
