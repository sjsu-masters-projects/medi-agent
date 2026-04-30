"""Chat routes."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, WebSocketException
from starlette import status
from supabase import Client

from app.agents.symptom import SymptomAgent, SymptomInput
from app.agents.triage import TriageAgent, TriageInput
from app.config import settings
from app.core.exceptions import AgentError, AuthorizationError, ValidationError
from app.core.security import decode_access_token, get_current_user
from app.db.connection import get_db
from app.models import ChatMessage, ChatMessageCreate
from app.models.auth import CurrentUser
from app.models.enums import ChatRole, Language
from app.services.a2a_task_service import A2ATaskService
from app.services.chat_service import ChatService, ConversationStateConflictError
from app.services.drug_knowledge_service import DrugKnowledgeService

router = APIRouter()
logger = logging.getLogger(__name__)


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


def _extract_document_context_id(websocket: WebSocket) -> str | None:
    context = str(websocket.query_params.get("context", "")).strip()
    if context.startswith("doc:"):
        return context[4:].strip() or None

    document_id = str(websocket.query_params.get("document_id", "")).strip()
    return document_id or None


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
    session_id = str(websocket.query_params.get("session_id") or "default").strip()
    return session_id or "default"


def _conversation_state_from_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "turn_count": int(record.get("turn_count") or 0),
        "last_intent": str(record.get("last_intent") or "general"),
        "last_urgency": str(record.get("last_urgency") or "routine"),
        "last_route": str(record.get("last_route") or "triage"),
        "summary": str(record.get("summary") or ""),
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
            "document_context": document_context,
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
            raise AuthorizationError("Patients can only view their own chat history")
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
            raise AuthorizationError("You are not assigned to this patient")
        return

    raise AuthorizationError("Unsupported role for chat access")


def _is_allowed_origin(origin: str | None) -> bool:
    if origin is None:
        return True

    if "*" in settings.allowed_origins:
        return True

    return origin in settings.allowed_origins


def _extract_ws_token(websocket: WebSocket) -> str:
    query_token = websocket.query_params.get("token")
    if query_token:
        return query_token

    auth_header = websocket.headers.get("authorization", "")
    prefix = "bearer "
    if auth_header.lower().startswith(prefix):
        return auth_header[len(prefix) :].strip()

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
    current_user: CurrentUser = Depends(get_current_user),
    service: ChatService = Depends(_get_service),
) -> Any:
    await _ensure_chat_access(current_user, patient_id, service.db)
    history = await service.get_history(str(patient_id), limit=limit, before=before)
    return [ChatMessage.model_validate(message) for message in history]


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

    await websocket.accept()
    service = ChatService(db)
    a2a_service = A2ATaskService(db)
    drug_knowledge_service = DrugKnowledgeService(db)
    triage_agent = TriageAgent()
    symptom_agent = SymptomAgent()

    history = await service.get_history(str(patient_id), limit=50)
    conversation_history = [_serialize_chat_message(item) for item in history]
    await websocket.send_json({"type": "chat_history", "messages": conversation_history})

    context_document_id = _extract_document_context_id(websocket)
    chat_context = await service.get_context(
        patient_id=str(patient_id),
        document_id=context_document_id,
    )
    patient_context = {
        "medications": chat_context.get("medications", []),
        "conditions": chat_context.get("conditions", []),
        "recent_symptoms": chat_context.get("recent_symptoms", []),
    }
    document_context = chat_context.get("document")
    sent_document_context_event = False
    if document_context:
        await websocket.send_json(
            {
                "type": "chat_context_loaded",
                "context_type": "document",
                "document": document_context,
            }
        )
        sent_document_context_event = True

    session_id = _read_session_id(websocket)
    state_record = await service.get_or_create_conversation_state(
        patient_id=str(patient_id),
        options={
            "session_id": session_id,
            "language": Language.EN,
            "document_context": document_context,
            "turn_count": len(conversation_history),
        },
    )
    if not document_context and isinstance(state_record.get("document_context"), dict):
        document_context = state_record["document_context"]
    if document_context and not sent_document_context_event:
        await websocket.send_json(
            {
                "type": "chat_context_loaded",
                "context_type": "document",
                "document": document_context,
            }
        )
    conversation_state = _conversation_state_from_record(state_record)

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
                incoming = ChatMessageCreate(
                    content=str(payload.get("content", "")),
                    role=ChatRole.USER,
                    language=payload.get("language", Language.EN),
                    audio_url=payload.get("audio_url"),
                )
            except Exception as exc:
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "validation_error",
                        "message": str(exc),
                    }
                )
                continue

            user_message = await service.save_message(
                patient_id=str(patient_id),
                data=incoming.model_dump(),
            )
            user_payload = _serialize_chat_message(user_message)
            conversation_history.append(user_payload)
            await websocket.send_json({"type": "user_message_saved", "message": user_payload})

            try:
                drug_knowledge_context = await drug_knowledge_service.retrieve_for_patient_message(
                    message=incoming.content,
                    medications=patient_context.get("medications", []),
                )
                if drug_knowledge_context.get("status") != "not_applicable":
                    patient_context = {
                        **patient_context,
                        "drug_knowledge": drug_knowledge_context,
                    }

                triage_result = await triage_agent(
                    TriageInput(
                        user_id=current_user.id,
                        patient_id=patient_id,
                        session_id=session_id,
                        message=incoming.content,
                        language=incoming.language,
                        history=conversation_history[-12:],
                        patient_context=patient_context,
                        document_context=document_context,
                        conversation_state=conversation_state,
                    )
                )
                if triage_result.status != "success":
                    raise AgentError("Triage returned non-success status")
                assistant_content = str(triage_result.response_text or "").strip()
                assistant_intent = str(triage_result.intent or "general")
                assistant_urgency = str(triage_result.urgency or "routine")
                escalation_required = bool(triage_result.escalation_required)
                route = str(triage_result.route or "triage")
            except Exception as exc:
                logger.warning("Triage processing failed, using deterministic fallback: %s", exc)
                assistant_content = (
                    "I have recorded your message. Please continue monitoring your symptoms and "
                    "contact your care team if anything worsens."
                )
                assistant_intent = "general"
                assistant_urgency = "routine"
                escalation_required = False
                route = "triage"

            if route == "symptom":
                delegation_events: list[dict[str, Any]] = []
                saved_report: dict[str, Any] | None = None
                try:
                    symptom_result = await symptom_agent(
                        SymptomInput(
                            user_id=current_user.id,
                            patient_id=patient_id,
                            session_id=session_id,
                            language=incoming.language,
                            message=incoming.content,
                            history=conversation_history[-12:],
                            patient_context=patient_context,
                        )
                    )
                    if symptom_result.status == "success" and symptom_result.response_text:
                        assistant_content = symptom_result.response_text

                    if symptom_result.symptom_report:
                        saved_report = await service.save_symptom_report(
                            patient_id=str(patient_id),
                            report=symptom_result.symptom_report,
                        )
                        if saved_report:
                            recent_symptoms = patient_context.get("recent_symptoms", [])
                            patient_context["recent_symptoms"] = [saved_report, *recent_symptoms][
                                :6
                            ]

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
                            logger.warning(
                                "Skipping A2A delegation: unable to persist symptom event id"
                            )

                    assistant_intent = "symptom"
                except Exception as exc:
                    logger.warning("Symptom routing failed, continuing triage response: %s", exc)
                    delegation_events = []
            else:
                delegation_events = []

            await websocket.send_json(
                {
                    "type": "assistant_start",
                    "intent": assistant_intent,
                    "urgency": assistant_urgency,
                }
            )

            for chunk in _chunk_text(assistant_content):
                await websocket.send_json(
                    {
                        "type": "assistant_chunk",
                        "content": chunk,
                    }
                )

            assistant_message = await service.save_message(
                patient_id=str(patient_id),
                data={
                    "content": assistant_content,
                    "role": ChatRole.ASSISTANT,
                    "intent": assistant_intent,
                    "language": incoming.language,
                },
            )
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
    except WebSocketDisconnect:
        logger.info("Chat websocket disconnected")
    except ValidationError as exc:
        await websocket.send_json(
            {
                "type": "error",
                "code": "validation_error",
                "message": exc.message,
            }
        )
    except Exception as exc:
        logger.exception("Chat websocket error: %s", exc)
        await websocket.send_json(
            {
                "type": "error",
                "code": "server_error",
                "message": "Chat processing failed",
            }
        )
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)


# WebSocket route is mounted in main.py at /ws/chat/{patient_id}.
