"""The queue side of a worker-run Nora turn: Cloud Tasks dispatch, the outbox sweep and the
database operations the worker and the API share (``chat_turn_worker_operation``).

The turn row is the outbox (rule 6). ``begin`` writes the queued turn in one transaction;
only afterwards does :meth:`TurnDispatcher.dispatch` create the Cloud Tasks task, named from
the turn id and attempt, so a repeated enqueue is a no-op (rule 4: ``ALREADY_EXISTS`` counts as
dispatched). A turn whose task creation failed keeps ``dispatched_at`` NULL and
:meth:`TurnDispatcher.sweep` creates it again; the sweep is a bounded, supervised call made by
the cron endpoint and once at API startup, never a free-running loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from app.config import settings
from app.core.db_pools import run_chat_turn_db, run_dispatch
from app.core.exceptions import ExternalServiceError
from app.core.structured_logging import current_request_id, log_event

logger = logging.getLogger(__name__)

TASK_PATH = "/internal/tasks/chat-turn"
RPC_TIMEOUT_SECONDS = 10  # one database call (client budget; the function itself stops at 8 s)
ENQUEUE_TIMEOUT_SECONDS = 10  # one Cloud Tasks call
# Task dispatch deadline = the worker's database lease + this margin. The nesting (rule 11):
# Cloud Run request timeout (300) > task dispatch deadline > lease > processing budget > model
# call > database statement.
DISPATCH_MARGIN_SECONDS = 30
SWEEP_MIN_AGE_SECONDS = 15  # let the original request finish enqueueing before the sweep acts
SWEEP_BATCH = 25


def task_id(turn_id: str, attempt: int) -> str:
    """Deterministic and valid as a Cloud Tasks id; one task per turn attempt."""
    return f"chat-turn-{UUID(str(turn_id))}-a{int(attempt)}"


class TurnQueueOps:
    """Typed calls to ``chat_turn_worker_operation``. Every call is bounded and logged."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def call(
        self, turn_id: str | None, action: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            response = await asyncio.wait_for(
                run_chat_turn_db(
                    self.db.rpc(
                        "chat_turn_worker_operation",
                        {
                            "p_turn": turn_id or "00000000-0000-0000-0000-000000000000",
                            "p_action": action,
                            "p_payload": payload or {},
                        },
                    ).execute
                ),
                timeout=RPC_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            outcome = "timeout"
            error: str | None = "timeout"
        except APIError as exc:
            outcome = str(getattr(exc, "code", None) or "unknown")
            error = outcome
        else:
            outcome, error = "ok", None
        if error is not None:
            log_event(
                logger,
                "chat_turn.queue_rpc_failed",
                level=logging.WARNING,
                message=f"Chat turn queue RPC {action} failed",
                operation=action,
                turn_id=turn_id,
                outcome=outcome,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            raise ExternalServiceError("Chat", "Chat turn queue is unavailable.")
        if not isinstance(response.data, dict):
            raise ExternalServiceError("Chat", "Chat turn queue is unavailable.")
        data = cast(dict[str, Any], response.data)
        if action not in {"append_event"}:  # drafts are too frequent to log one by one
            log_event(
                logger,
                f"chat_turn.queue_{action}",
                message=f"Chat turn {action}",
                operation=action,
                turn_id=turn_id,
                accepted=data.get("accepted") if "accepted" in data else None,
                reason=data.get("reason"),
                outcome="accepted" if data.get("accepted", True) else "refused",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        return data


class TurnDispatcher:
    """Create the Cloud Tasks task for a queued turn, and re-create the ones that were missed."""

    def __init__(self, db: Client) -> None:
        self.ops = TurnQueueOps(db)

    # -- configuration -------------------------------------------------------------------
    @staticmethod
    def project() -> str:
        return (settings.cloud_tasks_project or settings.google_project_id).strip()

    @classmethod
    def configured(cls) -> bool:
        return all(
            (
                cls.project(),
                settings.cloud_tasks_location.strip(),
                settings.cloud_tasks_queue.strip(),
                settings.chat_worker_url.strip(),
                settings.chat_worker_invoker_sa.strip(),
            )
        )

    @staticmethod
    def audience() -> str:
        return (settings.chat_worker_oidc_audience or settings.chat_worker_url).strip()

    @staticmethod
    def dispatch_deadline_seconds() -> int:
        from app.services.chat_turn_service import turn_budget

        _, lease = turn_budget(settings.chat_turn_timeout_seconds)
        return max(15, min(1800, lease + DISPATCH_MARGIN_SECONDS))

    # -- one task --------------------------------------------------------------------------
    def build_task(self, turn_id: str, attempt: int) -> dict[str, Any]:
        parent = (
            f"projects/{self.project()}/locations/{settings.cloud_tasks_location.strip()}"
            f"/queues/{settings.cloud_tasks_queue.strip()}"
        )
        headers = {"Content-Type": "application/json"}
        request_id = current_request_id()
        if request_id and len(request_id) == 32:
            # The worker adopts this as its request id, so one id follows the turn end to end.
            headers["X-Cloud-Trace-Context"] = f"{request_id}/1;o=1"
        return {
            "name": f"{parent}/tasks/{task_id(turn_id, attempt)}",
            "dispatch_deadline": timedelta(seconds=self.dispatch_deadline_seconds()),
            "http_request": {
                "http_method": "POST",
                "url": settings.chat_worker_url.strip().rstrip("/") + TASK_PATH,
                "headers": headers,
                # Identity of the work only; the worker re-reads everything else (rule 23).
                "body": json.dumps(
                    {"turn_id": str(UUID(str(turn_id))), "attempt": int(attempt)}
                ).encode(),
                "oidc_token": {
                    "service_account_email": settings.chat_worker_invoker_sa.strip(),
                    "audience": self.audience(),
                },
            },
        }

    def _create(self, turn_id: str, attempt: int) -> str:
        """Blocking; runs on the dispatch pool. Returns 'created' or 'exists'."""
        from google.api_core import exceptions as gax

        client = _client()
        parent = client.queue_path(
            self.project(),
            settings.cloud_tasks_location.strip(),
            settings.cloud_tasks_queue.strip(),
        )
        try:
            client.create_task(
                request={"parent": parent, "task": self.build_task(turn_id, attempt)},
                timeout=ENQUEUE_TIMEOUT_SECONDS,
            )
        except gax.AlreadyExists:
            return "exists"
        return "created"

    async def dispatch(self, turn_id: str, attempt: int) -> bool:
        """Enqueue after the turn's transaction committed. Never raises: a failure leaves the
        turn queued and undispatched for the sweep. True when the queue holds the task."""
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(
                run_dispatch(lambda: self._create(turn_id, attempt)),
                timeout=ENQUEUE_TIMEOUT_SECONDS + 2,
            )
        except Exception as exc:  # the type only; messages can carry request detail
            log_event(
                logger,
                "chat_turn.dispatch_failed",
                level=logging.WARNING,
                message="Chat turn task was not created; the sweep will retry",
                operation="dispatch",
                turn_id=turn_id,
                attempt=attempt,
                outcome=type(exc).__name__,
                category="saturated" if type(exc).__name__ == "PoolSaturatedError" else None,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            return False
        log_event(
            logger,
            "chat_turn.dispatched",
            message="Chat turn task accepted by the queue",
            operation="dispatch",
            turn_id=turn_id,
            attempt=attempt,
            outcome=result,
            queue=settings.cloud_tasks_queue,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        try:
            await self.ops.call(turn_id, "dispatched", {"attempt": attempt})
        except Exception:  # the task exists; the sweep's repeat is a no-op and marks it
            logger.warning("Chat turn dispatch mark failed; the sweep will mark it")
        return True

    # -- the outbox sweep ----------------------------------------------------------------
    async def sweep(
        self, *, limit: int = SWEEP_BATCH, min_age_seconds: int = SWEEP_MIN_AGE_SECONDS
    ) -> dict[str, int]:
        """Re-enqueue queued turns whose task was never accepted. Bounded and idempotent."""
        if not self.configured():
            log_event(
                logger,
                "chat_turn.sweep_skipped",
                level=logging.WARNING,
                message="Chat turn sweep skipped: the worker queue is not configured",
                outcome="not_configured",
            )
            return {"examined": 0, "dispatched": 0, "failed": 0}
        listed = await self.ops.call(
            None, "undispatched", {"limit": limit, "min_age_seconds": min_age_seconds}
        )
        items = [row for row in listed.get("items") or [] if isinstance(row, dict)]
        dispatched = 0
        for row in items:
            if await self.dispatch(str(row["id"]), int(row["attempt"])):
                dispatched += 1
        log_event(
            logger,
            "chat_turn.sweep",
            message=f"Chat turn sweep: {dispatched}/{len(items)} dispatched",
            operation="sweep",
            outcome=f"{dispatched}_of_{len(items)}",
        )
        return {"examined": len(items), "dispatched": dispatched, "failed": len(items) - dispatched}


_client_lock = threading.Lock()
_client_singleton: Any = None


def _client() -> Any:
    """One Cloud Tasks client per process (rule 17: created under a lock, used by the dispatch
    pool's threads; the client is thread-safe)."""
    global _client_singleton
    with _client_lock:
        if _client_singleton is None:
            from google.cloud import tasks_v2

            _client_singleton = tasks_v2.CloudTasksClient()
        return _client_singleton


async def submit_turn(
    db: Client,
    *,
    patient_id: str,
    session_id: str,
    request: dict[str, Any],
    language: str,
    on_saved: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Begin a worker turn and hand it to the queue. The send path of the socket and of
    ``POST /chat/turns``.

    1. ``begin`` writes the user message and the QUEUED turn (the outbox row) in ONE database
       transaction, idempotent by ``client_message_id``: a repeated send returns the same turn.
    2. Only after that commit is the task created, named from the turn id and attempt, so
       a repeated enqueue is a no-op. If creation fails the turn stays queued and undispatched
       and the sweep creates the task; the send itself still succeeds.

    ``on_saved`` runs right after the begin commit and BEFORE the enqueue, so the patient sees
    their saved message without waiting for Cloud Tasks (measured 1.6 s on October 19). It
    also runs for a repeated send. A failure in it is logged and never blocks the enqueue:
    the outbox row already guarantees dispatch (rule 6).

    Returns the ``begin`` result plus ``dispatched`` (the queue holds the task). Raises what
    ``begin`` raises (busy, conflict, invalid) so callers report it exactly as before.
    """
    from app.services.chat_service import ChatService, conversation_title
    from app.services.chat_turn_service import ChatTurnService

    turns = ChatTurnService(db, patient_id, session_id)
    result = await turns.begin(
        {**request, "language": language}, settings.chat_turn_queue_seconds, queued=True
    )
    result["dispatched"] = False
    record = result.get("turn") or {}
    if on_saved is not None:
        try:
            await on_saved(result)
        except Exception as exc:  # showing the message must never stop the turn
            logger.warning("Chat turn saved-state notice failed: %s", type(exc).__name__)
    if result.get("execute") and result.get("user_message"):
        try:  # label the conversation now so an unfinished first turn is findable
            await ChatService(db).set_conversation_title(
                patient_id,
                session_id,
                conversation_title(str(result["user_message"].get("content") or "")),
            )
        except Exception as exc:  # a missing label must never fail the turn
            logger.warning("Nora conversation title was not saved: %s", type(exc).__name__)
        result["dispatched"] = await TurnDispatcher(db).dispatch(
            str(record["id"]), int(record.get("attempt") or 1)
        )
    return result
