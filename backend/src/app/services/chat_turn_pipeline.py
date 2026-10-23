"""One Nora turn, independent of how it is delivered.

``execute_turn`` is the turn itself: history, the safety floors, tools, the ``actions`` guard,
model fallback and budgets (all inside the injected ``process_message``), then the lease-bound
save. It publishes to a ``publish`` callable and never looks at a socket, so the same code runs
in the API process (events go to the in-process runner's viewers) and in the worker service
(events go to ``chat_turn_events``).
"""

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

from app.adk.evidence import evidence_is_shown
from app.core.exceptions import ValidationError
from app.core.structured_logging import log_event, set_turn_id
from app.models import ChatMessage
from app.services.chat_service import ChatService, ConversationStateConflictError
from app.services.chat_turn_execution import TurnChatService, TurnEmitter
from app.services.chat_turn_service import ChatTurnService, TurnExecution, public_turn
from app.services.conversation_summary import schedule_refresh

logger = logging.getLogger(__name__)
_STATE_REFRESH_ATTEMPTS = 3

# publish(event, origin_only=False): one turn event for viewers (or the event log).
Publish = Callable[..., None]
ProcessMessage = Callable[[Any, ChatService, dict[str, Any]], Awaitable[dict[str, Any]]]


def failure_label(exc: BaseException) -> str:
    """Exception type plus a safe machine code, never message text that could hold PHI."""
    code = getattr(exc, "code", None)
    if isinstance(exc, ValidationError):
        code = exc.message
    cause = type(exc.__cause__).__name__ if exc.__cause__ else ""
    parts = [type(exc).__name__]
    if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_]{1,40}", code):
        parts.append(code)
    if cause:
        parts.append(f"cause={cause}")
    return "/".join(parts)


def serialize_chat_message(message: dict[str, Any]) -> dict[str, Any]:
    return ChatMessage.model_validate(message).model_dump(mode="json")


async def refresh_conversation_state(
    service: ChatService,
    patient_id: str,
    pending: dict[str, Any],
    version: str | None,
) -> bool:
    """Persist turn_count/title/summary after a saved reply; the reply is never lost.

    A concurrent writer (a second tab, a document dismissal) changes `updated_at`, which
    used to skip this refresh silently. On conflict it re-reads the row and retries, never
    lowering the turn count the other writer saved.
    """
    updates = dict(pending)
    for _attempt in range(_STATE_REFRESH_ATTEMPTS):
        try:
            async with asyncio.timeout(5):
                await service.update_conversation_state(
                    patient_id, updates, expected_updated_at=version
                )
            return True
        except ConversationStateConflictError:
            try:
                async with asyncio.timeout(5):
                    fresh = await service.get_or_create_conversation_state(
                        patient_id, {"session_id": updates.get("session_id")}
                    )
            except Exception as exc:
                logger.warning("Conversation state re-read failed: %s", failure_label(exc))
                return False
            version = str(fresh.get("updated_at") or "") or None
            updates["turn_count"] = max(
                int(updates.get("turn_count") or 0), int(fresh.get("turn_count") or 0) + 1
            )
        except Exception as exc:
            logger.warning(
                "Saved chat reply retained; conversation metadata refresh failed: %s",
                "timeout" if isinstance(exc, TimeoutError) else failure_label(exc),
            )
            return False
    logger.warning("Saved chat reply retained; conversation metadata kept conflicting")
    return False


def turn_error_message(code: str) -> str:
    """Plain, fixed wording per turn failure code; never provider or exception text."""
    if code == "CHAT_TURN_BUSY":
        return "A reply is already in progress in this conversation. Recovering it now."
    if code == "CHAT_TURN_EXPIRED":
        return "This reply took too long and was not kept. Your message is saved: try again."
    return "Chat recovery is required."


async def report_turn_failure(
    exc: BaseException,
    *,
    service: ChatService,
    turns: ChatTurnService,
    context: dict[str, Any],
    request: dict[str, Any],
    emit_error: Callable[[dict[str, Any]], Awaitable[Any]],
    emit_shared: Callable[[dict[str, Any]], Awaitable[Any]],
) -> None:
    """Explicit error to the requesting socket, then the saved truth to every viewer."""
    code = exc.message if isinstance(exc, ValidationError) else "CHAT_TURN_UNAVAILABLE"
    log_event(
        logger,
        "chat_turn.not_completed",
        level=logging.WARNING,
        message=f"Durable chat turn did not complete: {failure_label(exc)}",
        category=type(exc).__name__,
        failure_category=type(exc).__name__,
        outcome=code,
    )
    await emit_error(
        {
            "type": "error",
            "code": code,
            "client_message_id": request.get("client_message_id"),
            "message": turn_error_message(code),
        }
    )
    try:
        recovered = await turns.call("recover", trigger="failure_report")
        finished = any(
            row.get("client_message_id") == request.get("client_message_id")
            and row.get("status") == "completed"
            for row in recovered["items"]
        )
        if finished:
            # The reply was committed although its confirmation was lost (for example a
            # timed-out completion call): deliver it from the saved history.
            history = await service.get_history(
                str(context["patient_id"]), session_id=context["session_id"], with_evidence=True
            )
            await emit_shared(
                {
                    "type": "chat_history",
                    "messages": [serialize_chat_message(row) for row in history],
                }
            )
        await emit_shared(
            {"type": "chat_turns", "turns": [public_turn(row) for row in recovered["items"]]}
        )
    except Exception as recover_exc:
        logger.warning("Saved chat status temporarily unavailable: %s", failure_label(recover_exc))


async def _after_completion(
    service: ChatService,
    staged: TurnChatService,
    saved: dict[str, Any],
    context: dict[str, Any],
    incoming: Any,
) -> None:
    """Work that follows a delivered reply: its evidence, then the conversation summary.

    Neither is allowed to change the turn's outcome. The reply is already saved and shown; a
    failure here is logged by class only and the next turn simply has less context or the
    evidence row is missing."""
    patient_id, session_id = str(context["patient_id"]), str(context["session_id"])
    try:
        if staged.evidence:
            async with asyncio.timeout(5):
                await ChatService(service.db).record_reply_evidence(
                    patient_id, session_id, str(saved["id"]), staged.evidence
                )
    except Exception as exc:
        log_event(
            logger,
            "chat_turn.evidence_not_saved",
            level=logging.WARNING,
            message=f"Reply evidence was not saved: {failure_label(exc)}",
            outcome="timeout" if isinstance(exc, TimeoutError) else type(exc).__name__,
        )
    try:
        schedule_refresh(
            service,
            patient_id=patient_id,
            session_id=session_id,
            language=str(getattr(incoming.language, "value", incoming.language)),
        )
    except Exception as exc:
        logger.warning("Conversation summary not scheduled: %s", failure_label(exc))


def conversation_state_from_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "turn_count": int(record.get("turn_count") or 0),
        "last_intent": str(record.get("last_intent") or "general"),
        "last_urgency": str(record.get("last_urgency") or "routine"),
        "last_route": str(record.get("last_route") or "triage"),
        "summary": str(record.get("summary") or ""),
    }


async def execute_turn(
    *,
    publish: Publish,
    process_message: ProcessMessage,
    service: ChatService,
    turns: ChatTurnService,
    context: dict[str, Any],
    request: dict[str, Any],
    incoming: Any,
    result: dict[str, Any],
    timeout: int,
    outcome: dict[str, Any] | None = None,
    report_failure: bool = True,
    fail_on_cancel: bool = True,
) -> dict[str, Any]:
    """The turn itself. Owned by the server: it never looks at, or waits for, a socket.

    ``outcome`` (optional) receives ``status`` (completed, failed, interrupted, cancelled) and
    ``mark_failed`` False when even marking the failure was impossible (the database was
    unreachable): the worker then answers 5xx so the queue retries. ``report_failure`` False
    skips the socket-style error and recovery events (the worker's terminal state is an event
    row written by the database in the same transaction as the state change)."""
    record = result["turn"]
    set_turn_id(record["id"])  # this task's own context; the socket's is untouched
    started_at = time.monotonic()
    execution = TurnExecution(turns, record)
    staged = TurnChatService(service, execution, result["user_message"])

    outcome = outcome if outcome is not None else {}

    async def send(event: dict[str, Any]) -> bool:
        publish(event)
        return True

    async def send_origin(event: dict[str, Any]) -> None:
        publish(event, origin_only=True)

    emitter = TurnEmitter(send)
    try:
        await send(
            {
                "type": "chat_turn",
                "turn": public_turn({**record, "user_message": result["user_message"]}),
            }
        )
        async with asyncio.timeout(timeout):
            history = await service.get_history(
                str(context["patient_id"]), session_id=context["session_id"]
            )
            history = [
                row for row in history if str(row["id"]) != str(result["user_message"]["id"])
            ]
            state = await process_message(
                emitter,
                staged,
                {
                    **context,
                    "incoming": incoming,
                    "document_context": record.get("document_context"),
                    "conversation_history": history,
                },
            )
        # Saved outside the processing budget: a finished reply gets its own save call and the
        # lease's save grace, so a slow model cannot leave no time to keep what it produced.
        saved = await staged.complete()
        if staged.pending_state:
            await refresh_conversation_state(
                service,
                str(context["patient_id"]),
                staged.pending_state,
                staged.pending_state_version,
            )
        event = emitter.complete_event or {"type": "assistant_complete"}
        await send(
            {
                **event,
                "message": serialize_chat_message(
                    {**saved, "has_evidence": evidence_is_shown(staged.evidence)}
                ),
            }
        )
        await send({"type": "chat_turn", "turn": public_turn({**record, "status": "completed"})})
        log_event(
            logger,
            "chat_turn.finished",
            message="Chat turn finished",
            outcome="completed",
            duration_ms=int((time.monotonic() - started_at) * 1000),
        )
        outcome["status"] = "completed"
        await _after_completion(service, staged, saved, context, incoming)
        return state
    except asyncio.CancelledError:
        outcome["status"] = "cancelled"
        if not fail_on_cancel:
            raise  # the worker hands the turn back to the queue instead of failing it
        # Only server shutdown (after the drain window) cancels a turn, never a socket.
        try:
            await asyncio.wait_for(
                asyncio.shield(execution.fail(interrupted=True, trigger="shutdown_cancel")), 3
            )
        except BaseException as exc:
            logger.warning(
                "Cancelled chat turn will reconcile from its saved deadline: %s",
                failure_label(exc),
            )
        raise
    except Exception as exc:
        outcome["status"] = "interrupted" if isinstance(exc, TimeoutError) else "failed"
        outcome["mark_failed"] = True
        try:
            await execution.fail(
                interrupted=isinstance(exc, TimeoutError),
                trigger="processing_timeout"
                if isinstance(exc, TimeoutError)
                else "execution_error",
                category=type(exc).__name__,
            )
        except Exception as fail_exc:
            outcome["mark_failed"] = False
            logger.warning(
                "Chat turn will reconcile from its saved deadline: %s", failure_label(fail_exc)
            )
        if not report_failure:
            return cast(dict[str, Any], context["conversation_state"])
        await report_turn_failure(
            exc,
            service=service,
            turns=turns,
            context=context,
            request=request,
            emit_error=send_origin,
            emit_shared=send,
        )
        return cast(dict[str, Any], context["conversation_state"])
