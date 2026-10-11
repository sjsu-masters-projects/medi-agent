"""Cloud Run Job entry point for the weekly medication and condition reference refresh.

Cloud Scheduler runs this Job once a week over OAuth, the same way it runs document
ingestion, so no shared secret is placed in a scheduler payload. Each run is recorded in
``cron_job_runs`` and logged as one ``scheduled_job.started`` and one
``scheduled_job.finished`` line by ``CronService``; logs carry counts only.
"""

from __future__ import annotations

import asyncio

from app.clients.supabase import get_admin_client
from app.core.job_logging import JobRunLog
from app.services.cron_service import CronJobAlreadyRunningError, CronService
from app.workers.document_ingestion import _configure_worker_logging

JOB_NAME = "health_knowledge_refresh"
REFRESH_LIMIT = 150


async def main() -> int:
    """Exit 0 on success or when another run is in progress, 1 on any failure."""
    _configure_worker_logging()
    try:
        service = CronService(get_admin_client())
    except Exception as exc:  # noqa: BLE001 - no run can be recorded without a client
        JobRunLog(JOB_NAME).finished("failed", {}, error=exc, reason="run_not_recorded")
        return 1
    try:
        result = await service.run_health_knowledge_refresh(limit=REFRESH_LIMIT)
    except CronJobAlreadyRunningError:
        return 0  # Logged as skipped by the service.
    except Exception:  # noqa: BLE001 - logged as failed by the service
        return 1
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":  # pragma: no cover - exercised by Cloud Run Job
    raise SystemExit(asyncio.run(main()))
