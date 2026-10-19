"""Run one queued Nora turn inside the worker service (OPS-006 phase 2).

The queue task carries only a turn id and an attempt. Everything else (the patient, the
conversation, the text, the document) is read from the database by the claim, so a forged or
stale task can never act on anything the database does not hold (rule 23). The turn then runs
through the same pipeline as the in-process path (safety floors, tools, the ``actions`` guard,
model fallback, budgets) and its lease-bound completion; the worker only adds the claim, draft
checkpoints and the answer to the queue.

Answers to Cloud Tasks (rule 5, 12):

* the turn finished, was already finished, is stale or unknown, exceeded its budget, or its
  clinical actions may have run  -> return normally (HTTP 200): the queue must not retry;
* anything transient (the claim could not reach the database, the lease is held by a live
  attempt, a failure could not be recorded, the instance is saturated)  -> raise
  :class:`TransientTaskError` (HTTP 503): the queue retries with backoff. A retry can re-claim a
  turn only when it is queued or its lease expired *and* no clinical action started.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, cast

from supabase import Client

from app.adk.chat_runtime import CareCoordinatorRuntime
from app.config import settings
from app.core.exceptions import ExternalServiceError, ServiceUnavailableError
from app.core.structured_logging import log_event, set_actor, set_turn_id
from app.models import ChatMessageCreate
from app.models.auth import CurrentUser
from app.models.enums import ChatRole, coerce_locale
from app.services.a2a_task_service import A2ATaskService
from app.services.chat_service import ChatService
from app.services.chat_turn_pipeline import (
    ProcessMessage,
    conversation_state_from_record,
    execute_turn,
)
from app.services.chat_turn_queue import TurnQueueOps
from app.services.chat_turn_service import ChatTurnService, turn_budget
from app.services.explanation_service import normalize_patient_summary

logger = logging.getLogger(__name__)

DRAFT_INTERVAL_SECONDS = 1.0  # at most one draft checkpoint per second (rule: bounded writes)
DRAFT_TICK_SECONDS = 0.25  # how often the checkpointer looks for new text
DRAFT_MAX_CHARS = 30000
MAX_DRAFT_FAILURES = 3
NOTICE_TYPES = {"a2a_task_status", "appointment_proposal", "escalation_recommended"}
RETRYABLE_REFUSALS = {"lease_active"}

_inflight = 0  # touched only on the event loop thread (rule 17)


class TransientTaskError(Exception):
    """The queue should retry this task (HTTP 503)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class DraftCheckpointer:
    """Collects the streamed draft in memory and writes it to the event log at most once a second
    from its own supervised task, so a slow database never delays the model stream.

    The checkpoint holds the whole draft so far, not a delta: a viewer that joins late needs only
    the newest one. Failures are logged and never fail the turn; after repeated failures drafting
    stops (the final reply is unaffected)."""

    def __init__(self, ops: TurnQueueOps, turn_id: str, lease: str, next_seq: int) -> None:
        self.ops, self.turn_id, self.lease, self.next_seq = ops, turn_id, lease, next_seq
        self.text, self.intent, self.urgency = "", "general", "routine"
        self.dirty = False
        self.notices: list[dict[str, Any]] = []
        self.failures = 0
        self.stopped = False
        self.appends = 0
        self._task: asyncio.Task[None] | None = None

    # The pipeline's sink (called synchronously from the event loop).
    def publish(self, event: dict[str, Any], *, origin_only: bool = False) -> None:
        kind = event.get("type")
        if kind == "assistant_start":
            self.text, self.dirty = "", True
            self.intent = str(event.get("intent") or "general")
            self.urgency = str(event.get("urgency") or "routine")
        elif kind == "assistant_chunk":
            self.text = (self.text + str(event.get("content") or ""))[:DRAFT_MAX_CHARS]
            self.dirty = True
        elif kind in NOTICE_TYPES and len(self.notices) < 20:
            self.notices.append(event)

    def start(self) -> None:
        self._task = asyncio.get_running_loop().create_task(self._run())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _append(self, kind: str, payload: dict[str, Any]) -> bool:
        try:
            result = await asyncio.wait_for(
                self.ops.call(
                    self.turn_id,
                    "append_event",
                    {"lease": self.lease, "type": kind, "payload": payload, "seq": self.next_seq},
                ),
                timeout=5,
            )
        except (TimeoutError, ExternalServiceError, ServiceUnavailableError):
            self.failures += 1
            return False
        if result.get("accepted"):
            self.next_seq = int(result.get("next_seq") or self.next_seq + 1)
            self.appends += 1
            self.failures = 0
            return True
        if result.get("reason") in {"seq_gap", "seq_conflict"}:
            self.next_seq = int(result.get("next_seq") or self.next_seq)  # resync, retry next tick
            return False
        # lease_mismatch / deadline_passed / status:*: this attempt no longer owns the turn.
        self.stopped = True
        log_event(
            logger,
            "chat_turn.draft_stopped",
            level=logging.WARNING,
            message="Draft checkpoints stopped: the lease is no longer held",
            turn_id=self.turn_id,
            reason=str(result.get("reason")),
        )
        return False

    async def flush(self) -> None:
        while self.notices and not self.stopped:
            if not await self._append("notice", self.notices[0]):
                return
            self.notices.pop(0)
        if self.dirty and not self.stopped:
            payload = {"content": self.text, "intent": self.intent, "urgency": self.urgency}
            self.dirty = False
            if not await self._append("draft", payload):
                self.dirty = True

    async def _run(self) -> None:
        last = -DRAFT_INTERVAL_SECONDS
        while not self.stopped and self.failures < MAX_DRAFT_FAILURES:
            await asyncio.sleep(DRAFT_TICK_SECONDS)
            if (self.dirty or self.notices) and time.monotonic() - last >= DRAFT_INTERVAL_SECONDS:
                last = time.monotonic()
                await self.flush()


async def _build_context(
    db: Client, service: ChatService, patient_id: str, session_id: str, claim: dict[str, Any]
) -> dict[str, Any]:
    """What the websocket handler builds once per connection, built per turn from the database."""
    chat_context = await service.get_context(patient_id=patient_id, document_id=None)
    state_record = await service.get_or_create_conversation_state(
        patient_id=patient_id,
        options={
            "session_id": session_id,
            "language": coerce_locale(claim["user_message"].get("language")),
            "document_context": None,
            "turn_count": 0,
        },
    )
    user_message = claim["user_message"]
    return {
        "patient_id": patient_id,
        "session_id": session_id,
        # The worker acts for the conversation's own patient, read from the turn row.
        "current_user": CurrentUser(id=patient_id, email="", role="patient"),
        "document_context": None,  # the turn's own snapshot is passed by execute_turn
        "patient_context": {
            "medications": chat_context.get("medications", []),
            "conditions": chat_context.get("conditions", []),
            "recent_symptoms": chat_context.get("recent_symptoms", []),
        },
        "conversation_state": conversation_state_from_record(state_record),
        "care_coordinator": CareCoordinatorRuntime(),
        "a2a_service": A2ATaskService(db),
        "incoming": ChatMessageCreate(
            content=str(user_message.get("content") or ""),
            role=ChatRole.USER,
            language=coerce_locale(user_message.get("language")),
            audio_url=user_message.get("audio_url"),
        ),
    }


async def _hand_back(ops: TurnQueueOps, turn_id: str, lease: str) -> bool:
    """Return a claimed turn to the queue before any clinical action. True when it was."""
    try:
        result = await asyncio.wait_for(
            ops.call(
                turn_id,
                "requeue",
                {"lease": lease, "timeout_seconds": settings.chat_turn_queue_seconds},
            ),
            timeout=5,
        )
    except Exception:
        return False
    return bool(result.get("accepted"))


async def run_chat_turn(
    db: Client,
    *,
    turn_id: str,
    attempt: int,
    process_message: ProcessMessage,
) -> dict[str, Any]:
    """Claim and run one turn. Returns a small outcome dict (HTTP 200) or raises
    :class:`TransientTaskError` (HTTP 503)."""
    global _inflight
    if _inflight >= settings.chat_worker_max_concurrency:
        log_event(
            logger,
            "chat_turn.worker_shed",
            level=logging.WARNING,
            message="Worker saturated; the queue will retry",
            turn_id=turn_id,
            outcome="shed",
        )
        raise TransientTaskError("saturated")
    _inflight += 1
    try:
        return await _run(db, turn_id, attempt, process_message)
    finally:
        _inflight -= 1


async def _run(
    db: Client, turn_id: str, attempt: int, process_message: ProcessMessage
) -> dict[str, Any]:
    started = time.monotonic()
    set_turn_id(turn_id)
    processing, lease_seconds = turn_budget(settings.chat_turn_timeout_seconds)
    ops = TurnQueueOps(db)
    try:
        claim = await ops.call(
            turn_id, "claim", {"attempt": attempt, "timeout_seconds": lease_seconds}
        )
    except (ExternalServiceError, ServiceUnavailableError):
        raise TransientTaskError("claim_unavailable") from None
    if not claim.get("accepted"):
        reason = str(claim.get("reason") or "unknown")
        if reason in RETRYABLE_REFUSALS:
            raise TransientTaskError(reason)
        log_event(
            logger,
            "chat_turn.worker_noop",
            message=f"Worker task is a no-op: {reason}",
            turn_id=turn_id,
            reason=reason,
            outcome="noop",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return {"outcome": "noop", "reason": reason}

    record = claim["turn"]
    document = record.get("document_context")
    if isinstance(document, dict) and "summary" in document:
        # The same plain-text cleanup a begin applies to the authorised summary.
        document["summary"] = normalize_patient_summary(str(document["summary"]))
    patient_id, session_id = str(claim["patient_id"]), str(claim["session_id"])
    set_actor(patient_id, session_id)
    service = ChatService(db)
    turns = ChatTurnService(db, patient_id, session_id)
    checkpointer = DraftCheckpointer(ops, turn_id, str(record["lease"]), int(claim["next_seq"]))
    outcome: dict[str, Any] = {}
    try:
        try:
            context = await _build_context(db, service, patient_id, session_id, claim)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Nothing ran yet: hand the turn back so the retry starts clean.
            await _hand_back(ops, turn_id, str(record["lease"]))
            raise TransientTaskError("context_unavailable") from None
        checkpointer.start()
        await execute_turn(
            publish=checkpointer.publish,
            process_message=process_message,
            service=service,
            turns=turns,
            context=context,
            request={"client_message_id": record.get("client_message_id")},
            incoming=context["incoming"],
            result={"turn": record, "user_message": claim["user_message"]},
            timeout=processing,
            outcome=outcome,
            report_failure=False,
            fail_on_cancel=False,
        )
    except asyncio.CancelledError:
        # The instance is stopping: give the turn back (never after a clinical action).
        if not await asyncio.shield(_hand_back(ops, turn_id, str(record["lease"]))):
            try:
                await asyncio.wait_for(
                    asyncio.shield(
                        turns.call(
                            "interrupted",
                            {"id": record["id"], "lease": record["lease"]},
                            trigger="worker_shutdown",
                        )
                    ),
                    3,
                )
            except BaseException:  # the deadline reconciles it
                logger.warning("Worker turn will reconcile from its saved deadline")
        raise
    finally:
        await checkpointer.stop()

    status = str(outcome.get("status") or "unknown")
    if status in {"failed", "interrupted"}:
        # Rule 21: a failure may be a completion whose confirmation was lost. Read the truth.
        try:
            rows = (await turns.call("recover", trigger="worker_verify")).get("items") or []
        except (ExternalServiceError, ServiceUnavailableError):
            raise TransientTaskError("outcome_unverified") from None
        saved = next((row for row in rows if str(row.get("id")) == str(record["id"])), None)
        if saved and saved.get("status") == "completed":
            status = "completed"
        elif outcome.get("mark_failed") is False:
            raise TransientTaskError("failure_not_recorded")
    try:
        await ops.call(turn_id, "prune_events")
    except (ExternalServiceError, ServiceUnavailableError):
        logger.warning("Draft pruning failed; the next completed turn read leaves drafts unused")
    log_event(
        logger,
        "chat_turn.worker_done",
        message=f"Worker finished the turn: {status}",
        turn_id=turn_id,
        outcome=status,
        attempt=attempt,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return cast(dict[str, Any], {"outcome": status})
