"""Background worker that re-drives retryable A2A tasks."""

from __future__ import annotations

import asyncio
import logging

from supabase import Client

from app.services.a2a_task_service import A2ATaskService

logger = logging.getLogger(__name__)


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

    async def _run_loop(self) -> None:
        logger.info(
            "A2A retry worker started (poll=%ss, batch=%s)",
            self._poll_interval_seconds,
            self._batch_size,
        )
        while not self._stop_event.is_set():
            try:
                summary = await self._service.process_due_retries(self._batch_size)
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
                if self._service.is_transient_supabase_error(exc):
                    logger.warning(
                        "A2A retry worker transient Supabase error; will retry next cycle: %s",
                        exc,
                    )
                else:
                    logger.exception("A2A retry worker cycle failed: %s", exc)

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._poll_interval_seconds,
                )
            except TimeoutError:
                continue

        logger.info("A2A retry worker stopped")
