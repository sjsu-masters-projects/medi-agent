"""Chat routes."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, WebSocketException
from starlette import status
from starlette.websockets import WebSocketState
from supabase import Client

from app.adk.chat_runtime import CareCoordinatorRuntime
from app.config import settings
from app.core import authorization_reasons as reasons
from app.core.exceptions import AuthorizationError, ValidationError
from app.core.llm_failures import categorize_llm_failure
from app.core.observability import record_chat_fallback
from app.core.security import decode_access_token, get_current_user
from app.core.structured_logging import log_event, set_actor, set_turn_id
from app.db.connection import get_db
from app.followup import analyse_symptom
from app.followup.service import EMERGENCY_THRESHOLD
from app.models import ChatMessage, ChatMessageCreate
from app.models.auth import CurrentUser
from app.models.chat import ChatConversation
from app.models.enums import ChatRole, Language
from app.safety import TRIAGE_COPY
from app.services.a2a_task_service import A2ATaskService
from app.services.chat_document_catalog import (
    build_document_catalog_reply,
    is_document_catalog_question,
)
from app.services.chat_service import (
    ChatService,
    ConversationStateConflictError,
    conversation_title,
    normalize_session_id,
)
from app.services.chat_turn_execution import TurnChatService, TurnEmitter
from app.services.chat_turn_runner import TurnRun, TurnViewer, turn_runner
from app.services.chat_turn_service import (
    ChatTurnService,
    TurnExecution,
    public_turn,
    turn_budget,
)
from app.utils.localization import resolve_locale_resource, written_language

router = APIRouter()
logger = logging.getLogger(__name__)
_STATE_REFRESH_ATTEMPTS = 3

# The outermost fallback: triage itself could not be reached. Every other tier is
# localized through TRIAGE_COPY, so this one is too — a patient who wrote in Spanish
# should not be answered in English at the moment the assistant is least useful.
OUTER_FALLBACK_COPY: dict[str, dict[str, str]] = {
    "default": {
        "outer_fallback": (
            "I'm having trouble reaching my care assistant right now. Your message is "
            "saved. Please try again in a moment, and contact your care team directly "
            "if this is urgent."
        )
    },
    Language.EN.value: {
        "outer_fallback": (
            "I'm having trouble reaching my care assistant right now. Your message is "
            "saved. Please try again in a moment, and contact your care team directly "
            "if this is urgent."
        )
    },
    Language.ES.value: {
        "outer_fallback": (
            "Estoy teniendo problemas para comunicarme con mi asistente de salud en este "
            "momento. Tu mensaje quedó guardado. Vuelve a intentarlo en un momento y "
            "contacta directamente a tu equipo clínico si esto es urgente."
        )
    },
}


def _get_service(db: Client = Depends(get_db)) -> ChatService:
    return ChatService(db)


def _serialize_chat_message(message: dict[str, Any]) -> dict[str, Any]:
    return ChatMessage.model_validate(message).model_dump(mode="json")


def _chunk_text(text: str, chunk_size: int = 140) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []
    return [
        normalized[index : index + chunk_size] for index in range(0, len(normalized), chunk_size)
    ]


DOCUMENT_CONTEXT_DISMISSED = "none"
"""`?context=none`: the patient dismissed this conversation's document."""


def _extract_document_context_id(websocket: WebSocket) -> str | None:
    context = str(websocket.query_params.get("context", "")).strip()
    if context.startswith("doc:"):
        return context[4:].strip() or None

    document_id = str(websocket.query_params.get("document_id", "")).strip()
    return document_id or None


def _document_context_dismissed(websocket: WebSocket) -> bool:
    return str(websocket.query_params.get("context", "")).strip() == DOCUMENT_CONTEXT_DISMISSED


async def _resolve_document_focus(
    service: ChatService,
    *,
    patient_id: str,
    session_id: str,
    dismissed: bool,
    requested_document_id: str | None,
    requested_document: dict[str, Any] | None,
    saved_document: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, bool]:
    """The document this conversation is focused on, and whether a document went missing.

    The saved focus is what lets a reopened conversation keep its document, so a dismissal
    has to clear it there too; otherwise the next connection restored the document the
    patient had just closed. A saved document is read again on every connection, so one
    that was deleted (or never was the patient's) is reported rather than answered from.
    """
    if dismissed:
        if saved_document is not None:
            await service.set_document_context(patient_id, session_id, None)
            logger.info("Chat document focus cleared", extra={"chat_document_focus": "dismissed"})
        return None, False

    if requested_document_id:
        if requested_document is None:
            if saved_document is not None:
                await service.set_document_context(patient_id, session_id, None)
            logger.info(
                "Chat document focus unavailable", extra={"chat_document_focus": "unavailable"}
            )
            return None, True
        if saved_document != requested_document:
            await service.set_document_context(patient_id, session_id, requested_document)
        return requested_document, False

    if saved_document is None:
        return None, False

    saved_id = str(saved_document.get("id") or "").strip()
    current = await service.get_document_context(patient_id, saved_id) if saved_id else None
    if current is None:
        await service.set_document_context(patient_id, session_id, None)
        logger.info("Chat document focus unavailable", extra={"chat_document_focus": "unavailable"})
        return None, True
    return current, False


def _build_conversation_state(
    conversation_history: list[dict[str, Any]],
    *,
    prior_state: dict[str, Any],
    last_intent: str,
    last_urgency: str,
    last_route: str,
) -> dict[str, Any]:
    recent_lines: list[str] = []
    for item in conversation_history[-6:]:
        role = str(item.get("role", "unknown"))
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        recent_lines.append(f"{role}: {content[:120]}")

    previous_summary = str(prior_state.get("summary") or "").strip()
    recent_summary = " | ".join(recent_lines)
    summary = recent_summary or previous_summary

    return {
        "turn_count": int(prior_state.get("turn_count") or 0) + 1,
        "last_intent": last_intent,
        "last_urgency": last_urgency,
        "last_route": last_route,
        "summary": summary[:2000],
    }


def _read_session_id(websocket: WebSocket) -> str:
    return normalize_session_id(websocket.query_params.get("session_id"))


def _conversation_state_from_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "turn_count": int(record.get("turn_count") or 0),
        "last_intent": str(record.get("last_intent") or "general"),
        "last_urgency": str(record.get("last_urgency") or "routine"),
        "last_route": str(record.get("last_route") or "triage"),
        "summary": str(record.get("summary") or ""),
    }


def _build_appointment_proposal(
    *,
    patient_id: UUID,
    message: str,
    patient_context: dict[str, Any],
) -> dict[str, Any] | None:
    care_teams = [item for item in patient_context.get("care_teams", []) if isinstance(item, dict)]
    if not care_teams:
        return None

    care_team = care_teams[0]
    raw_clinician = care_team.get("clinicians")
    clinician: dict[str, Any] = raw_clinician if isinstance(raw_clinician, dict) else {}
    clinician_name = " ".join(
        part
        for part in [
            str(clinician.get("first_name") or "").strip(),
            str(clinician.get("last_name") or "").strip(),
        ]
        if part
    )
    return {
        "proposal_id": f"chat-schedule:{patient_id}",
        "patient_id": str(patient_id),
        "care_team_id": care_team.get("id"),
        "clinician_name": clinician_name or None,
        "reason": message[:240],
        "next_step": "Confirm a date and time with your clinic before this becomes an appointment.",
    }


async def _emit_a2a_task_events(websocket: WebSocket, events: list[dict[str, Any]]) -> None:
    for event in events:
        await websocket.send_json(
            {
                "type": "a2a_task_status",
                "task_id": event.get("task_id"),
                "target_agent": event.get("target_agent"),
                "status": event.get("status"),
            }
        )


def _closed_websocket_error(error: BaseException) -> bool:
    """Recognize Starlette's error for a send racing a client disconnect."""
    return isinstance(error, RuntimeError) and (
        "close message has been sent" in str(error)
        or "websocket is not connected" in str(error).lower()
    )


def _failure_label(exc: BaseException) -> str:
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


async def _refresh_conversation_state(
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
                logger.warning("Conversation state re-read failed: %s", _failure_label(exc))
                return False
            version = str(fresh.get("updated_at") or "") or None
            updates["turn_count"] = max(
                int(updates.get("turn_count") or 0), int(fresh.get("turn_count") or 0) + 1
            )
        except Exception as exc:
            logger.warning(
                "Saved chat reply retained; conversation metadata refresh failed: %s",
                "timeout" if isinstance(exc, TimeoutError) else _failure_label(exc),
            )
            return False
    logger.warning("Saved chat reply retained; conversation metadata kept conflicting")
    return False


async def _send_terminal_event(websocket: WebSocket, payload: dict[str, Any]) -> bool:
    """Best-effort terminal send that never sends again after the socket closes."""
    if websocket.application_state is not WebSocketState.CONNECTED:
        return False
    try:
        await websocket.send_json(payload)
    except (WebSocketDisconnect, RuntimeError):
        logger.info("Chat websocket closed before its terminal event could be delivered")
        return False
    return True


async def _send_document_catalog_reply(
    *,
    websocket: WebSocket,
    service: ChatService,
    patient_id: str,
    incoming: ChatMessageCreate,
    session_id: str,
    document_context: dict[str, Any] | None,
    conversation_history: list[dict[str, Any]],
    conversation_state: dict[str, Any],
) -> dict[str, Any]:
    """Persist and emit the deterministic answer to a portal-document catalog question."""
    documents = await service.get_document_catalog(patient_id)
    content = build_document_catalog_reply(documents, incoming.language)
    await websocket.send_json(
        {"type": "assistant_start", "intent": "document_catalog", "urgency": "routine"}
    )
    for chunk in _chunk_text(content):
        await websocket.send_json({"type": "assistant_chunk", "content": chunk})

    assistant_message = await service.save_message(
        patient_id=patient_id,
        data={
            "content": content,
            "role": ChatRole.ASSISTANT,
            "intent": "document_catalog",
            "language": incoming.language,
            "session_id": session_id,
        },
    )
    assistant_payload = _serialize_chat_message(assistant_message)
    conversation_history.append(assistant_payload)
    next_state = _build_conversation_state(
        conversation_history,
        prior_state=conversation_state,
        last_intent="document_catalog",
        last_urgency="routine",
        last_route="triage",
    )
    await _persist_conversation_state_with_retry(
        service,
        patient_id=patient_id,
        session_id=session_id,
        language=incoming.language,
        document_context=document_context,
        conversation_history=conversation_history,
        fallback_state=next_state,
        last_intent="document_catalog",
        last_urgency="routine",
        last_route="triage",
    )
    await websocket.send_json(
        {
            "type": "assistant_complete",
            "message": assistant_payload,
            "intent": "document_catalog",
            "urgency": "routine",
            "escalation_required": False,
        }
    )
    return next_state


async def _persist_conversation_state_with_retry(
    service: ChatService,
    *,
    patient_id: str,
    session_id: str,
    language: Language,
    document_context: dict[str, Any] | None,
    conversation_history: list[dict[str, Any]],
    fallback_state: dict[str, Any],
    last_intent: str,
    last_urgency: str,
    last_route: str,
    max_attempts: int = 3,
) -> dict[str, Any]:
    for attempt in range(max_attempts):
        state_record = await service.get_or_create_conversation_state(
            patient_id=patient_id,
            options={
                "session_id": session_id,
                "language": language,
                "document_context": document_context,
                "turn_count": len(conversation_history),
            },
        )
        prior_state = _conversation_state_from_record(state_record)
        next_state = _build_conversation_state(
            conversation_history,
            prior_state=prior_state,
            last_intent=last_intent,
            last_urgency=last_urgency,
            last_route=last_route,
        )
        updates = {
            "session_id": session_id,
            "language": language,
            "turn_count": next_state["turn_count"],
            "last_intent": next_state["last_intent"],
            "last_urgency": next_state["last_urgency"],
            "last_route": next_state["last_route"],
            "summary": next_state["summary"],
            "state_json": {
                "history_window": conversation_history[-12:],
            },
        }

        updated_at_token = state_record.get("updated_at")
        try:
            if isinstance(updated_at_token, str) and updated_at_token.strip():
                await service.update_conversation_state(
                    patient_id=patient_id,
                    updates=updates,
                    expected_updated_at=updated_at_token,
                )
            else:
                await service.update_conversation_state(
                    patient_id=patient_id,
                    updates=updates,
                )
            return next_state
        except ConversationStateConflictError:
            if attempt == max_attempts - 1:
                break
            logger.debug(
                "Conversation state optimistic-lock conflict; retrying (%s/%s)",
                attempt + 1,
                max_attempts,
            )

    logger.warning(
        "Conversation state update conflicted after %s attempts; continuing with in-memory state",
        max_attempts,
    )
    return fallback_state


async def _ensure_chat_access(user: CurrentUser, patient_id: UUID, db: Client) -> None:
    if user.role == "patient":
        if user.id != patient_id:
            raise AuthorizationError(
                "Patients can only view their own chat history",
                reason_code=reasons.PATIENT_SCOPE_SELF_ONLY,
                actor_id=str(user.id),
                actor_role=user.role,
                target_type="patient",
                target_id=str(patient_id),
            )
        return

    if user.role == "clinician":
        assignment = await asyncio.to_thread(
            db.table("care_teams")
            .select("id")
            .eq("clinician_id", str(user.id))
            .eq("patient_id", str(patient_id))
            .eq("status", "active")
            .limit(1)
            .execute
        )
        if not assignment.data:
            raise AuthorizationError(
                "You are not assigned to this patient",
                reason_code=reasons.NO_CARE_TEAM_ASSIGNMENT,
                actor_id=str(user.id),
                actor_role=user.role,
                target_type="patient",
                target_id=str(patient_id),
            )
        return

    raise AuthorizationError(
        "Unsupported role for chat access",
        reason_code=reasons.UNSUPPORTED_ROLE,
        actor_id=str(user.id),
        actor_role=user.role,
        target_type="patient",
        target_id=str(patient_id),
    )


def _is_allowed_origin(origin: str | None) -> bool:
    if origin is None:
        return True

    if "*" in settings.allowed_origins:
        return True

    return origin in settings.allowed_origins


WS_AUTH_SUBPROTOCOL = "bearer"
"""Subprotocol the client offers alongside its token.

Browsers cannot set an `Authorization` header on a WebSocket, which is why the token used
to travel in the query string. A URL is the one place a credential must never go: the
server writes the full request path to its access log, so every connection published a
usable session token to anyone who could read logs, and query strings also reach proxies,
browser history and `Referer` headers. `Sec-WebSocket-Protocol` is the standard way out —
the browser sends it as a header, and headers are not logged.
"""


def _offered_subprotocols(websocket: WebSocket) -> list[str]:
    header = websocket.headers.get("sec-websocket-protocol", "")
    return [value.strip() for value in header.split(",") if value.strip()]


def negotiated_subprotocol(websocket: WebSocket) -> str | None:
    """The subprotocol to echo on `accept`, or None when the client offered none.

    A WebSocket handshake that offers subprotocols expects one back, and browsers abort
    the connection when the server selects none. Only the scheme name is ever returned:
    echoing the token would move the credential into a response header and straight back
    into the logs this change exists to keep it out of.
    """
    offered = _offered_subprotocols(websocket)
    if offered and offered[0].lower() == WS_AUTH_SUBPROTOCOL:
        return WS_AUTH_SUBPROTOCOL
    return None


def _extract_ws_token(websocket: WebSocket) -> str:
    # `Sec-WebSocket-Protocol: bearer, <token>` — the browser path.
    offered = _offered_subprotocols(websocket)
    if len(offered) >= 2 and offered[0].lower() == WS_AUTH_SUBPROTOCOL:
        return offered[1]

    # Non-browser clients can send a real header, so keep it.
    auth_header = websocket.headers.get("authorization", "")
    prefix = "bearer "
    if auth_header.lower().startswith(prefix):
        return auth_header[len(prefix) :].strip()

    # The `?token=` query parameter is deliberately not accepted. Reinstating it would
    # reintroduce the log leak for every client at once.
    raise WebSocketException(
        code=status.WS_1008_POLICY_VIOLATION,
        reason="Missing websocket token",
    )


def _authenticate_ws_patient(websocket: WebSocket, patient_id: UUID) -> CurrentUser:
    if not _is_allowed_origin(websocket.headers.get("origin")):
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Origin not allowed",
        )

    user = decode_access_token(_extract_ws_token(websocket))
    if user.role != "patient" or user.id != patient_id:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Unauthorized websocket access",
        )

    return user


@router.get("/history/{patient_id}", response_model=list[ChatMessage])
async def get_chat_history(
    patient_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    before: str | None = Query(default=None),
    session_id: str | None = Query(default=None, max_length=64),
    current_user: CurrentUser = Depends(get_current_user),
    service: ChatService = Depends(_get_service),
) -> Any:
    await _ensure_chat_access(current_user, patient_id, service.db)
    history = await service.get_history(
        str(patient_id), limit=limit, before=before, session_id=session_id
    )
    return [ChatMessage.model_validate(message) for message in history]


@router.get("/conversations/{patient_id}", response_model=list[ChatConversation])
async def list_chat_conversations(
    patient_id: UUID,
    limit: int = Query(default=30, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    service: ChatService = Depends(_get_service),
) -> Any:
    """The patient's conversations with Nora, most recent first."""
    await _ensure_chat_access(current_user, patient_id, service.db)
    rows = await service.list_conversations(str(patient_id), limit=limit)
    return [ChatConversation.model_validate(row) for row in rows]


def _turn_error_message(code: str) -> str:
    """Plain, fixed wording per turn failure code; never provider or exception text."""
    if code == "CHAT_TURN_BUSY":
        return "A reply is already in progress in this conversation. Recovering it now."
    if code == "CHAT_TURN_EXPIRED":
        return "This reply took too long and was not kept. Your message is saved: try again."
    return "Chat recovery is required."


async def _report_turn_failure(
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
        message=f"Durable chat turn did not complete: {_failure_label(exc)}",
        category=type(exc).__name__,
        failure_category=type(exc).__name__,
        outcome=code,
    )
    await emit_error(
        {
            "type": "error",
            "code": code,
            "client_message_id": request.get("client_message_id"),
            "message": _turn_error_message(code),
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
                str(context["patient_id"]), session_id=context["session_id"]
            )
            await emit_shared(
                {
                    "type": "chat_history",
                    "messages": [_serialize_chat_message(row) for row in history],
                }
            )
        await emit_shared(
            {"type": "chat_turns", "turns": [public_turn(row) for row in recovered["items"]]}
        )
    except Exception as recover_exc:
        logger.warning("Saved chat status temporarily unavailable: %s", _failure_label(recover_exc))


async def _execute_turn(
    run: TurnRun,
    service: ChatService,
    turns: ChatTurnService,
    context: dict[str, Any],
    request: dict[str, Any],
    incoming: Any,
    result: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    """The turn itself. Owned by the server: it never looks at, or waits for, a socket."""
    record = result["turn"]
    set_turn_id(record["id"])  # this task's own context; the socket's is untouched
    started_at = time.monotonic()
    execution = TurnExecution(turns, record)
    staged = TurnChatService(service, execution, result["user_message"])

    async def send(event: dict[str, Any]) -> bool:
        turn_runner.publish(run, event)
        return True

    async def send_origin(event: dict[str, Any]) -> None:
        turn_runner.publish(run, event, origin_only=True)

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
            state = await _process_chat_message(
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
            await _refresh_conversation_state(
                service,
                str(context["patient_id"]),
                staged.pending_state,
                staged.pending_state_version,
            )
        event = emitter.complete_event or {"type": "assistant_complete"}
        await send({**event, "message": _serialize_chat_message(saved)})
        await send({"type": "chat_turn", "turn": public_turn({**record, "status": "completed"})})
        log_event(
            logger,
            "chat_turn.finished",
            message="Chat turn finished",
            outcome="completed",
            duration_ms=int((time.monotonic() - started_at) * 1000),
        )
        return state
    except asyncio.CancelledError:
        # Only server shutdown (after the drain window) cancels a turn, never a socket.
        try:
            await asyncio.wait_for(
                asyncio.shield(execution.fail(interrupted=True, trigger="shutdown_cancel")), 3
            )
        except BaseException as exc:
            logger.warning(
                "Cancelled chat turn will reconcile from its saved deadline: %s",
                _failure_label(exc),
            )
        raise
    except Exception as exc:
        try:
            await execution.fail(
                interrupted=isinstance(exc, TimeoutError),
                trigger="processing_timeout"
                if isinstance(exc, TimeoutError)
                else "execution_error",
                category=type(exc).__name__,
            )
        except Exception as fail_exc:
            logger.warning(
                "Chat turn will reconcile from its saved deadline: %s", _failure_label(fail_exc)
            )
        await _report_turn_failure(
            exc,
            service=service,
            turns=turns,
            context=context,
            request=request,
            emit_error=send_origin,
            emit_shared=send,
        )
        return cast(dict[str, Any], context["conversation_state"])


async def _process_durable_message(
    websocket: WebSocket,
    service: ChatService,
    context: dict[str, Any],
    request: dict[str, Any],
    viewer: TurnViewer | None = None,
) -> TurnRun | dict[str, Any]:
    """Begin a turn and hand its execution to the server-side runner.

    Returns the TurnRun when execution started, otherwise the conversation state. The
    websocket only receives events; closing it never touches the turn.
    """
    turns = ChatTurnService(service.db, str(context["patient_id"]), context["session_id"])
    key = (str(context["patient_id"]), str(context["session_id"]))

    async def direct(event: dict[str, Any]) -> None:
        await _send_terminal_event(websocket, event)

    try:
        incoming = context["incoming"]
        incoming = incoming.model_copy(
            update={"language": written_language(incoming.content, incoming.language)}
        )
        timeout, lease_seconds = turn_budget(settings.chat_turn_timeout_seconds)
        result = await turns.begin({**request, "language": incoming.language.value}, lease_seconds)
        record = result["turn"]
        # Label the conversation now, not after completion, so an interrupted first
        # turn is still findable. Only an empty title is written (idempotent).
        if result.get("execute") and result.get("user_message"):
            try:
                await service.set_conversation_title(
                    str(context["patient_id"]),
                    context["session_id"],
                    conversation_title(str(result["user_message"].get("content") or "")),
                )
            except Exception as exc:  # a missing label must never fail the turn
                logger.warning(
                    "Nora conversation title was not saved at turn start: %s",
                    type(exc).__name__,
                )
        if not result.get("execute"):
            await direct(
                {
                    "type": "chat_turn",
                    "turn": public_turn({**record, "user_message": result["user_message"]}),
                }
            )
            await direct(
                {
                    "type": "user_message_saved",
                    "message": _serialize_chat_message(result["user_message"]),
                }
            )
            if result.get("assistant_message"):
                await direct(
                    {
                        "type": "assistant_complete",
                        "message": _serialize_chat_message(result["assistant_message"]),
                    }
                )
            elif result.get("reply_unavailable"):
                # Completed, but the saved reply no longer exists: say so, never replay nothing.
                await direct(
                    {
                        "type": "chat_turn",
                        "turn": public_turn(
                            {
                                **record,
                                "status": "failed",
                                "actions_started": True,
                                "failure_code": "reply_unavailable",
                                "user_message": result["user_message"],
                            }
                        ),
                    }
                )
            return cast(dict[str, Any], context["conversation_state"])
    except Exception as exc:
        await _report_turn_failure(
            exc,
            service=service,
            turns=turns,
            context=context,
            request=request,
            emit_error=direct,
            emit_shared=direct,
        )
        return cast(dict[str, Any], context["conversation_state"])

    own_viewer = viewer is None
    if viewer is None:

        async def socket_send(event: dict[str, Any]) -> bool:
            return await _send_terminal_event(websocket, event)

        viewer = turn_runner.attach(key, socket_send)

    async def body(run: TurnRun) -> dict[str, Any]:
        try:
            return await _execute_turn(
                run, service, turns, context, request, incoming, result, timeout
            )
        finally:
            if own_viewer:
                assert viewer is not None
                await viewer.flush()
                viewer.close()

    return turn_runner.start(str(record["id"]), key, body, origin=viewer)


async def _process_chat_message(
    websocket: Any, service: ChatService, context: dict[str, Any]
) -> dict[str, Any]:
    patient_id = context["patient_id"]
    session_id = context["session_id"]
    incoming = context["incoming"]
    current_user = context["current_user"]
    document_context = context["document_context"]
    patient_context = context["patient_context"]
    conversation_history = context["conversation_history"]
    conversation_state = context["conversation_state"]
    care_coordinator = context["care_coordinator"]
    a2a_service = context["a2a_service"]
    # Label and answer the message in the language it is written in; the client
    # sends the app language, which mislabelled Spanish messages as English.
    incoming = incoming.model_copy(
        update={"language": written_language(incoming.content, incoming.language)}
    )
    user_message = await service.save_message(
        patient_id=str(patient_id),
        data={**incoming.model_dump(), "session_id": session_id},
    )
    if not any(item.get("role") == ChatRole.USER.value for item in conversation_history):
        await service.set_conversation_title(
            str(patient_id), session_id, conversation_title(incoming.content)
        )
    user_payload = _serialize_chat_message(user_message)
    conversation_history.append(user_payload)
    await websocket.send_json({"type": "user_message_saved", "message": user_payload})

    if is_document_catalog_question(incoming.content):
        conversation_state = await _send_document_catalog_reply(
            websocket=websocket,
            service=service,
            patient_id=str(patient_id),
            incoming=incoming,
            session_id=session_id,
            document_context=document_context,
            conversation_history=conversation_history,
            conversation_state=conversation_state,
        )
        return cast(dict[str, Any], conversation_state)

    assistant_content = ""
    cited_documents: list[str] = []
    assistant_intent = "general"
    assistant_urgency = "routine"
    escalation_required = False
    route = "triage"
    assistant_start_sent = False
    streamed_response = False
    outer_fallback = False

    try:
        # The patient's own record is read by the coordinator through a tool
        # rather than pushed in here, so the identifier travels and the record
        # does not. Conversation history is carried by the runtime's session,
        # keyed on this same session id.
        stream_iter = care_coordinator.process_stream(
            patient_id=str(patient_id),
            user_id=str(current_user.id),
            session_id=session_id,
            message=incoming.content,
            language=incoming.language.value,
            document_context=document_context,
            # Stored messages, not the process's memory, so a restart keeps context.
            earlier_messages=conversation_history[:-1],
        )
        async for event in stream_iter:
            ev_type = event.get("type")
            if ev_type == "classification":
                assistant_intent = str(event.get("intent", "general"))
                assistant_urgency = str(event.get("urgency", "routine"))
                route = str(event.get("route", "triage"))
                escalation_required = bool(event.get("escalation_required", False))

                await websocket.send_json(
                    {
                        "type": "assistant_start",
                        "intent": assistant_intent,
                        "urgency": assistant_urgency,
                    }
                )
                assistant_start_sent = True

                # The symptom route is answered by the follow-up worker below, not
                # by the coordinator. Closing the stream here is what keeps the
                # patient from watching one reply arrive and then be replaced by
                # a different one.
                #
                # An emergency is the exception, and must stay one. The floor
                # labels a medical emergency `intent="symptom"`, so it arrives
                # here too — but its reviewed 911 answer comes from the floor in
                # the `complete` event, and the guard below deliberately stops the
                # worker replacing it. Closing the stream early therefore threw
                # that answer away and left the patient reading "I am having
                # trouble answering right now". Nothing replaces an emergency
                # reply, so there is nothing to protect the patient from seeing.
                if route == "symptom" and assistant_urgency != "emergency":
                    await stream_iter.aclose()
                    break
            elif ev_type == "chunk":
                chunk_text = str(event.get("content", ""))
                if not chunk_text:
                    continue
                await websocket.send_json({"type": "assistant_chunk", "content": chunk_text})
                streamed_response = True
            elif ev_type == "complete":
                assistant_content = str(event.get("response_text", "")).strip()
                cited_documents = [str(item) for item in event.get("cited_documents") or [] if item]
    except Exception as exc:
        fallback_reason = categorize_llm_failure(exc)
        record_chat_fallback(layer="L3_outer", reason=fallback_reason)
        logger.warning(
            "Triage processing failed, using outer deterministic fallback: %s",
            _failure_label(exc),
            extra={
                "chat_fallback_layer": "L3_outer",
                "chat_fallback_reason": fallback_reason,
            },
        )
        outer_fallback = True
        # Every other fallback tier is localized through TRIAGE_COPY; this one
        # answered a Spanish-speaking patient in English.
        assistant_content = resolve_locale_resource(incoming.language, OUTER_FALLBACK_COPY)[
            "outer_fallback"
        ]
        assistant_intent = "general"
        assistant_urgency = "routine"
        escalation_required = False
        route = "triage"

    if route == "symptom":
        delegation_events: list[dict[str, Any]] = []
        saved_report: dict[str, Any] | None = None
        # The stream is aborted once the route is known, so the patient is never
        # shown a reply the symptom worker is about to replace. That used to be
        # followed by a second, buffered call to the same model for text that is
        # discarded in the common case. This seeds the honest answer instead: if
        # the worker below produces nothing, we say we could not reply rather than
        # making a second attempt at the failure that just happened.
        if not assistant_content and not outer_fallback:
            # "Try again in a few minutes" is never the right thing to tell someone
            # reporting a medical emergency, whatever else has failed this turn.
            # Only a medical emergency reaches the symptom route; self-harm
            # classifies as `mental_health` and is answered elsewhere.
            seeded_copy_key = (
                "emergency_response" if assistant_urgency == "emergency" else "service_unavailable"
            )
            assistant_content = resolve_locale_resource(incoming.language, TRIAGE_COPY)[
                seeded_copy_key
            ]
        try:
            symptom_result = await analyse_symptom(
                message=incoming.content,
                language=incoming.language,
                history=conversation_history[-12:],
                patient_context=patient_context,
            )
            # An emergency has already been answered with reviewed 911 copy by the
            # deterministic floor, and that answer is not the symptom worker's to
            # replace. The floor classifies a medical emergency as `symptom`, which
            # routes into this branch, so without this guard a patient reporting
            # crushing chest pain was shown "I logged your symptom for follow-up"
            # and never told to call 911. Self-harm escaped it only because it
            # classifies as `mental_health` and never reaches here. The report is
            # still captured and the delegation still runs; only the words the
            # patient reads are protected.
            # Keyed on the text rather than on `status`, because a degraded result
            # still carries something the patient needs to read: that the symptom
            # could not be recorded. Requiring success would swallow exactly the
            # message that admits the failure.
            if symptom_result.response_text:
                if assistant_urgency != "emergency":
                    assistant_content = symptom_result.response_text
                else:
                    logger.warning(
                        "Withheld the symptom worker's reply: the emergency answer stands"
                    )

            if symptom_result.symptom_report:
                saved_report = await service.save_symptom_report(
                    patient_id=str(patient_id),
                    report=symptom_result.symptom_report,
                )
                if saved_report:
                    recent_symptoms = patient_context.get("recent_symptoms", [])
                    patient_context["recent_symptoms"] = [saved_report, *recent_symptoms][:6]

            severity = int((symptom_result.symptom_report or {}).get("severity") or 0)
            if severity >= EMERGENCY_THRESHOLD:
                # Worst-imaginable or danger-sign symptoms reach the care team even
                # when no medication is linked; the reply already carries 911 advice.
                escalation_required = True
                if assistant_urgency == "routine":
                    assistant_urgency = "urgent"

            if symptom_result.flagged_for_adr:
                escalation_required = True
                if assistant_urgency == "routine":
                    assistant_urgency = "urgent"

                symptom_event_id = str((saved_report or {}).get("id") or "").strip()
                if symptom_result.symptom_report and symptom_event_id:
                    lifecycle = await a2a_service.run_symptom_to_pharmacovigilance(
                        patient_id=str(patient_id),
                        payload={
                            "session_id": session_id,
                            "symptom_event_id": symptom_event_id,
                            "idempotency_key": f"symptom_event:{symptom_event_id}",
                            "symptom_report": saved_report,
                            "flagged_for_adr": True,
                            "naranjo_answers": symptom_result.naranjo_answers,
                            "adr_evidence": symptom_result.adr_evidence,
                            "document_context": document_context,
                            "conversation_state": conversation_state,
                        },
                    )
                    delegation_events = [
                        event
                        for event in (lifecycle.get("events") or [])
                        if isinstance(event, dict)
                    ]
                elif symptom_result.symptom_report:
                    logger.warning("Skipping A2A delegation: unable to persist symptom event id")

            assistant_intent = "symptom"
        except Exception as exc:
            fallback_reason = categorize_llm_failure(exc)
            record_chat_fallback(layer="symptom_agent", reason=fallback_reason)
            logger.warning(
                "Symptom routing failed, continuing triage response: %s",
                _failure_label(exc),
                extra={
                    "chat_fallback_layer": "symptom_agent",
                    "chat_fallback_reason": fallback_reason,
                },
            )
            delegation_events = []
    else:
        delegation_events = []

    # If we never sent assistant_start (e.g. exception before classification),
    # emit it now so the client transitions out of "loading" state.
    if not assistant_start_sent:
        await websocket.send_json(
            {
                "type": "assistant_start",
                "intent": assistant_intent,
                "urgency": assistant_urgency,
            }
        )

    # Buffered fallback paths (symptom route, outer fallback) need their
    # text chunked here. Streamed responses already had per-token chunks.
    if not streamed_response and assistant_content:
        for chunk in _chunk_text(assistant_content):
            await websocket.send_json({"type": "assistant_chunk", "content": chunk})

    # Results of the documents the reply cited, as a card under it. Built from the
    # patient's own source-checked facts, never from the reply's text.
    attachments = (
        await asyncio.to_thread(service.result_attachments, str(patient_id), cited_documents)
        if cited_documents
        else []
    )
    assistant_message = await service.save_message(
        patient_id=str(patient_id),
        data={
            "content": assistant_content,
            "role": ChatRole.ASSISTANT,
            "intent": assistant_intent,
            "language": written_language(assistant_content, incoming.language),
            "session_id": session_id,
            "attachments": attachments,
        },
    )
    if attachments and not assistant_message.get("attachments"):
        # Saved as text only (migration 062 not applied); still show the card live.
        assistant_message = {**assistant_message, "attachments": attachments}
    assistant_payload = _serialize_chat_message(assistant_message)
    conversation_history.append(assistant_payload)
    next_state = _build_conversation_state(
        conversation_history,
        prior_state=conversation_state,
        last_intent=assistant_intent,
        last_urgency=assistant_urgency,
        last_route=route,
    )
    conversation_state = await _persist_conversation_state_with_retry(
        service,
        patient_id=str(patient_id),
        session_id=session_id,
        language=incoming.language,
        document_context=document_context,
        conversation_history=conversation_history,
        fallback_state=next_state,
        last_intent=assistant_intent,
        last_urgency=assistant_urgency,
        last_route=route,
    )

    await websocket.send_json(
        {
            "type": "assistant_complete",
            "message": assistant_payload,
            "intent": assistant_intent,
            "urgency": assistant_urgency,
            "escalation_required": escalation_required,
        }
    )
    if delegation_events:
        await _emit_a2a_task_events(websocket, delegation_events)
    if assistant_intent == "schedule":
        proposal = _build_appointment_proposal(
            patient_id=patient_id,
            message=incoming.content,
            patient_context=patient_context,
        )
        if proposal:
            await websocket.send_json(
                {
                    "type": "appointment_proposal",
                    "proposal": proposal,
                }
            )
    if escalation_required:
        clinicians_notified = await service.notify_assigned_clinicians(
            patient_id=str(patient_id),
            payload={
                "urgency": assistant_urgency,
                "intent": assistant_intent,
                "message_excerpt": incoming.content,
            },
        )
        await websocket.send_json(
            {
                "type": "escalation_recommended",
                "message": (
                    "Please contact your care team today. If severe symptoms appear, seek "
                    "emergency care immediately."
                ),
                "clinicians_notified": clinicians_notified,
            }
        )
    return cast(dict[str, Any], conversation_state)


async def chat_websocket_endpoint(
    websocket: WebSocket,
    patient_id: UUID,
    db: Client = Depends(get_db),
) -> None:
    try:
        current_user = _authenticate_ws_patient(websocket, patient_id)
    except Exception as exc:
        if isinstance(exc, WebSocketException):
            raise
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=str(exc),
        ) from None

    await websocket.accept(subprotocol=negotiated_subprotocol(websocket))
    service = ChatService(db)
    a2a_service = A2ATaskService(db)
    care_coordinator = CareCoordinatorRuntime()

    try:
        session_id = _read_session_id(websocket)
        set_actor(patient_id, session_id)
        durable_protocol = websocket.query_params.get("turn_protocol") == "1"
        history = await service.get_history(str(patient_id), limit=50, session_id=session_id)
        conversation_history = [_serialize_chat_message(item) for item in history]
        await websocket.send_json({"type": "chat_history", "messages": conversation_history})
        if durable_protocol:
            recovered = await ChatTurnService(db, str(patient_id), session_id).call(
                "recover", trigger="socket_connect"
            )
            await websocket.send_json(
                {"type": "chat_turns", "turns": [public_turn(row) for row in recovered["items"]]}
            )
        clinician_messages = await service.get_recent_clinician_messages(str(patient_id))
        for message in clinician_messages:
            await websocket.send_json({"type": "clinician_message", "message": message})

        context_dismissed = _document_context_dismissed(websocket)
        context_document_id = None if context_dismissed else _extract_document_context_id(websocket)
        chat_context = await service.get_context(
            patient_id=str(patient_id),
            document_id=context_document_id,
        )
        patient_context = {
            "medications": chat_context.get("medications", []),
            "conditions": chat_context.get("conditions", []),
            "recent_symptoms": chat_context.get("recent_symptoms", []),
        }
        requested_document = chat_context.get("document")

        state_record = await service.get_or_create_conversation_state(
            patient_id=str(patient_id),
            options={
                "session_id": session_id,
                "language": Language.EN,
                "document_context": requested_document,
                "turn_count": len(conversation_history),
            },
        )
        saved_document = state_record.get("document_context")
        document_context, document_unavailable = await _resolve_document_focus(
            service,
            patient_id=str(patient_id),
            session_id=session_id,
            dismissed=context_dismissed,
            requested_document_id=context_document_id,
            requested_document=requested_document,
            saved_document=saved_document if isinstance(saved_document, dict) else None,
        )
        if document_context:
            await websocket.send_json(
                {
                    "type": "chat_context_loaded",
                    "context_type": "document",
                    "document": document_context,
                }
            )
        elif document_unavailable:
            await websocket.send_json(
                {"type": "chat_context_unavailable", "context_type": "document"}
            )
        conversation_state = _conversation_state_from_record(state_record)
    except WebSocketDisconnect:
        logger.info("Chat websocket disconnected during initialization")
        return
    except Exception as exc:
        if _closed_websocket_error(exc):
            logger.info("Chat websocket disconnected during initialization")
            return
        # Never leave an accepted socket to die silently: the client needs an explicit state.
        logger.warning("Chat websocket initialization failed: %s", _failure_label(exc))
        if await _send_terminal_event(
            websocket,
            {
                "type": "error",
                "code": "CHAT_STARTUP_UNAVAILABLE",
                "message": "Chat is temporarily unavailable.",
            },
        ):
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    # This socket is a viewer of the patient's running turn, if any: it gets the draft so
    # far and then live events. Closing it never touches the turn.
    viewer: TurnViewer | None = None
    if durable_protocol:

        async def viewer_send(event: dict[str, Any]) -> bool:
            return await _send_terminal_event(websocket, event)

        viewer = turn_runner.attach((str(patient_id), session_id), viewer_send)
    pending_run: TurnRun | None = None

    try:
        while True:
            try:
                payload = await websocket.receive_json()
            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "invalid_json",
                        "message": "Malformed JSON payload",
                    }
                )
                continue

            if not isinstance(payload, dict):
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "validation_error",
                        "message": "Websocket payload must be a JSON object",
                    }
                )
                continue

            event_type = str(payload.get("type", "")).strip()

            if event_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if durable_protocol and event_type in {"recover_turns", "dismiss_turn"}:
                turns = ChatTurnService(service.db, str(patient_id), session_id)
                if event_type == "dismiss_turn":
                    try:
                        key = str(UUID(str(payload.get("client_message_id", ""))))
                    except ValueError:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "code": "CHAT_TURN_INVALID",
                                "message": "Invalid recovery request.",
                            }
                        )
                        continue
                try:
                    if event_type == "dismiss_turn":
                        await turns.call(
                            "dismiss", {"client_message_id": key}, trigger="socket_dismiss"
                        )
                    recovered = await turns.call(
                        "recover",
                        trigger="socket_dismiss"
                        if event_type == "dismiss_turn"
                        else "socket_recover",
                    )
                    history = await service.get_history(str(patient_id), session_id=session_id)
                except Exception as exc:
                    if _closed_websocket_error(exc):
                        raise
                    logger.warning("Chat recovery request failed: %s", _failure_label(exc))
                    await websocket.send_json(
                        {
                            "type": "error",
                            "code": "CHAT_TURN_UNAVAILABLE",
                            "message": "Chat recovery is required.",
                        }
                    )
                    continue
                await websocket.send_json(
                    {
                        "type": "chat_history",
                        "messages": [_serialize_chat_message(row) for row in history],
                    }
                )
                await websocket.send_json(
                    {
                        "type": "chat_turns",
                        "turns": [public_turn(row) for row in recovered["items"]],
                    }
                )
                continue

            if event_type == "document_focus":
                # Attach or dismiss over the open socket, so a focus change never closes a
                # socket that may be receiving a reply. Each turn still carries its own document.
                raw_document = str(payload.get("document_id") or "").strip()[:64]
                try:
                    if not raw_document:
                        await service.set_document_context(str(patient_id), session_id, None)
                        document_context = None
                    else:
                        focus = await service.get_context(
                            patient_id=str(patient_id), document_id=raw_document
                        )
                        document_context, unavailable = await _resolve_document_focus(
                            service,
                            patient_id=str(patient_id),
                            session_id=session_id,
                            dismissed=False,
                            requested_document_id=raw_document,
                            requested_document=focus.get("document"),
                            saved_document=document_context,
                        )
                        if document_context:
                            await websocket.send_json(
                                {
                                    "type": "chat_context_loaded",
                                    "context_type": "document",
                                    "document": document_context,
                                }
                            )
                        elif unavailable:
                            await websocket.send_json(
                                {"type": "chat_context_unavailable", "context_type": "document"}
                            )
                except Exception as exc:
                    if _closed_websocket_error(exc):
                        raise
                    logger.warning("Chat document focus update failed: %s", _failure_label(exc))
                continue

            if event_type != "user_message":
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "unsupported_event",
                        "message": "Unsupported websocket event type",
                    }
                )
                continue

            try:
                raw_content = str(payload.get("content", ""))
                if not raw_content.strip():
                    await websocket.send_json(
                        {
                            "type": "error",
                            "code": "validation_error",
                            "message": "Message content is required.",
                        }
                    )
                    continue

                incoming = ChatMessageCreate(
                    content=raw_content,
                    role=ChatRole.USER,
                    language=payload.get("language", Language.EN),
                    audio_url=payload.get("audio_url"),
                )
            except Exception as exc:
                logger.info("Rejected user_message payload: %s", _failure_label(exc))
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "validation_error",
                        "message": "Message could not be processed. Please check the content and try again.",
                    }
                )
                continue

            turn_context = {
                "patient_id": patient_id,
                "session_id": session_id,
                "incoming": incoming,
                "current_user": current_user,
                "document_context": document_context,
                "patient_context": patient_context,
                "conversation_history": conversation_history,
                "conversation_state": conversation_state,
                "care_coordinator": care_coordinator,
                "a2a_service": a2a_service,
            }
            if durable_protocol:
                if pending_run is not None and pending_run.task and pending_run.task.done():
                    if isinstance(pending_run.result, dict):
                        conversation_state = pending_run.result
                        turn_context["conversation_state"] = conversation_state
                    pending_run = None
                started = await _process_durable_message(
                    websocket, service, turn_context, payload, viewer
                )
                if isinstance(started, TurnRun):
                    pending_run = started
                else:
                    conversation_state = started
            else:
                conversation_state = await _process_chat_message(websocket, service, turn_context)
    except WebSocketDisconnect:
        logger.info("Chat websocket disconnected")
    except ValidationError as exc:
        await _send_terminal_event(
            websocket,
            {
                "type": "error",
                "code": "validation_error",
                "message": exc.message,
            },
        )
    except Exception as exc:
        if _closed_websocket_error(exc):
            logger.info("Chat websocket disconnected before a response was delivered")
            return
        logger.exception("Chat websocket error: %s", _failure_label(exc))
        sent = await _send_terminal_event(
            websocket,
            {
                "type": "error",
                "code": "server_error",
                "message": "Chat processing failed",
            },
        )
        if sent and websocket.application_state is WebSocketState.CONNECTED:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
    finally:
        if viewer is not None:
            viewer.close()


# WebSocket routes are mounted in main.py.
