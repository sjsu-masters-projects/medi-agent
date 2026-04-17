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

from app.agents.triage import TriageAgent, TriageInput
from app.config import settings
from app.core.exceptions import AgentError, AuthorizationError, ValidationError
from app.core.security import decode_access_token, get_current_user
from app.db.connection import get_db
from app.models import ChatMessage, ChatMessageCreate
from app.models.auth import CurrentUser
from app.models.enums import ChatRole, Language
from app.services.chat_service import ChatService

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
    triage_agent = TriageAgent()

    history = await service.get_history(str(patient_id), limit=50)
    conversation_history = [_serialize_chat_message(item) for item in history]
    await websocket.send_json({"type": "chat_history", "messages": conversation_history})

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
                triage_result = await triage_agent(
                    TriageInput(
                        user_id=current_user.id,
                        patient_id=patient_id,
                        message=incoming.content,
                        language=incoming.language,
                        history=conversation_history[-12:],
                    )
                )
                if triage_result.status != "success":
                    raise AgentError("Triage returned non-success status")
                assistant_content = str(triage_result.response_text or "").strip()
                assistant_intent = str(triage_result.intent or "general")
                assistant_urgency = str(triage_result.urgency or "routine")
                escalation_required = bool(triage_result.escalation_required)
            except Exception as exc:
                logger.warning("Triage processing failed, using deterministic fallback: %s", exc)
                assistant_content = (
                    "I have recorded your message. Please continue monitoring your symptoms and "
                    "contact your care team if anything worsens."
                )
                assistant_intent = "general"
                assistant_urgency = "routine"
                escalation_required = False

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

            await websocket.send_json(
                {
                    "type": "assistant_complete",
                    "message": assistant_payload,
                    "intent": assistant_intent,
                    "urgency": assistant_urgency,
                    "escalation_required": escalation_required,
                }
            )
            if escalation_required:
                await websocket.send_json(
                    {
                        "type": "escalation_recommended",
                        "message": (
                            "Please contact your care team today. If severe symptoms appear, seek "
                            "emergency care immediately."
                        ),
                    }
                )
    except WebSocketDisconnect:
        logger.info("Chat websocket disconnected for patient %s", patient_id)
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
