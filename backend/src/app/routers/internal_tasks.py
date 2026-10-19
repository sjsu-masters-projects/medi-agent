"""Task endpoint of the worker service (``WORKER_MODE=true`` only).

Mounted by the worker app and nowhere else. Cloud Tasks calls it with an OIDC token that
:func:`require_cloud_tasks_oidc` verifies. The response tells the queue what to do:

* 200  the task is done with (finished, already finished, stale, unknown, over budget, or its
  clinical actions may have run): do not retry;
* 503  transient (database unreachable, the lease is held by a live attempt, saturated): retry
  with the queue's backoff.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from supabase import Client

from app.core.structured_logging import log_event, set_task_id
from app.core.task_auth import require_cloud_tasks_oidc
from app.db.connection import get_db
from app.routers import chat
from app.services.chat_turn_worker import TransientTaskError, run_chat_turn

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/chat-turn", dependencies=[Depends(require_cloud_tasks_oidc)])
async def run_chat_turn_task(
    request: Request,
    db: Client = Depends(get_db),
    task_name: str | None = Header(default=None, alias="X-CloudTasks-TaskName"),
    retry_count: int | None = Header(default=None, alias="X-CloudTasks-TaskRetryCount"),
) -> JSONResponse:
    set_task_id(task_name)
    try:
        body: Any = await request.json()
        turn_id = str(UUID(str(body["turn_id"])))
        attempt = int(body["attempt"])
        if not 1 <= attempt <= 3:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        # Authenticated but unusable: a retry would fail the same way, so end the task.
        log_event(
            logger,
            "chat_turn.worker_noop",
            level=logging.ERROR,
            message="Worker task body is invalid; dropping it",
            reason="invalid_task",
            outcome="noop",
        )
        return JSONResponse({"outcome": "noop", "reason": "invalid_task"})
    log_event(
        logger,
        "chat_turn.worker_task",
        message="Worker task received",
        turn_id=turn_id,
        attempt=attempt,
        retry_count=retry_count,
    )
    try:
        outcome = await run_chat_turn(
            db,
            turn_id=turn_id,
            attempt=attempt,
            process_message=chat._process_chat_message,
        )
    except TransientTaskError as exc:
        log_event(
            logger,
            "chat_turn.worker_retry",
            level=logging.WARNING,
            message=f"Worker asks the queue to retry: {exc.reason}",
            turn_id=turn_id,
            reason=exc.reason,
            outcome="retry",
            http_status=503,
        )
        return JSONResponse(
            {"outcome": "retry", "reason": exc.reason},
            status_code=503,
            headers={"Retry-After": "5"},
        )
    return JSONResponse(outcome)
