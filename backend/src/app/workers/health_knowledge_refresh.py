"""Cloud Run Job entry point for the weekly medication and condition reference refresh.

Cloud Scheduler runs this Job once a week over OAuth, the same way it runs document
ingestion, so no shared secret is placed in a scheduler payload. Each run is recorded in
``cron_job_runs``; logs carry counts only.
"""

from __future__ import annotations

import asyncio

from app.clients.supabase import get_admin_client
from app.services.cron_service import CronService
from app.workers.document_ingestion import _configure_worker_logging, _log_execution

REFRESH_LIMIT = 150


async def main() -> int:
    _configure_worker_logging()
    _log_execution("health_knowledge_refresh_started", limit=REFRESH_LIMIT)
    result = await CronService(get_admin_client()).run_health_knowledge_refresh(limit=REFRESH_LIMIT)
    summary = result["summary"]
    _log_execution("health_knowledge_refresh_finished", **summary)
    return 1 if summary.get("subjects_failed") else 0


if __name__ == "__main__":  # pragma: no cover - exercised by Cloud Run Job
    raise SystemExit(asyncio.run(main()))
