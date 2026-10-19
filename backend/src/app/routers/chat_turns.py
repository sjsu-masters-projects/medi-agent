"""HTTP send and read for worker-run Nora turns (OPS-006 phase 2).

``POST /chat/turns`` is the stream-friendly send: it validates, begins the turn as ``queued`` in
one transaction, enqueues after that commit and returns the turn. Repeating it with the same
``client_message_id`` returns the same turn and creates no second task. ``GET
/chat/turns/{id}/events`` reads the turn's ordered event log (resume with ``after_seq``); any API
instance serves it. Both exist only while ``CHAT_TURNS_VIA_WORKER`` is on.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from supabase import Client

from app.config import settings
from app.core import authorization_reasons as reasons
from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from app.core.security import get_current_user
from app.core.structured_logging import log_event, set_actor
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.enums import Language
from app.services.chat_service import normalize_session_id
from app.services.chat_turn_events import TurnEventReader
from app.services.chat_turn_pipeline import serialize_chat_message
from app.services.chat_turn_queue import TurnDispatcher, submit_turn
from app.services.chat_turn_service import public_turn
from app.utils.localization import written_language

router = APIRouter()
logger = logging.getLogger(__name__)


class SendTurnRequest(BaseModel):
    client_message_id: UUID
    content: str = Field(min_length=1, max_length=8000)
    language: Language = Language.EN
    session_id: str | None = Field(default=None, max_length=64)
    document_id: UUID | None = None
    audio_url: str | None = Field(default=None, max_length=2048)


def _require_enabled() -> None:
    if not settings.chat_turns_via_worker:
        # Same answer as an unknown route: the feature does not exist until it is switched on.
        raise NotFoundError("Route", "chat turns")


def _require_patient(user: CurrentUser) -> None:
    if user.role != "patient":
        raise AuthorizationError(
            "Only patients can send chat messages",
            reason_code=reasons.PATIENT_SCOPE_SELF_ONLY,
            actor_id=str(user.id),
            actor_role=user.role,
            target_type="patient",
            target_id=str(user.id),
        )


@router.post("", summary="Send a Nora message as a queued turn")
async def send_turn(
    body: SendTurnRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_db),
) -> JSONResponse:
    _require_enabled()
    _require_patient(current_user)
    patient_id = str(current_user.id)
    session_id = normalize_session_id(body.session_id)
    set_actor(patient_id, session_id)
    if not TurnDispatcher.configured():
        log_event(
            logger,
            "chat_turn.worker_unconfigured",
            level=logging.ERROR,
            message="CHAT_TURNS_VIA_WORKER is on but the worker queue is not configured",
            outcome="not_configured",
        )
        raise ExternalServiceError("Chat", "Chat is temporarily unavailable.")
    language = written_language(body.content, body.language)
    try:
        result = await submit_turn(
            db,
            patient_id=patient_id,
            session_id=session_id,
            request={
                "client_message_id": str(body.client_message_id),
                "content": body.content,
                "document_id": str(body.document_id) if body.document_id else None,
                "audio_url": body.audio_url,
            },
            language=language.value,
        )
    except ValidationError as exc:
        if exc.message in {"CHAT_TURN_BUSY", "CHAT_TURN_CONFLICT"}:
            # A reply is already running, or the id was reused with different content.
            raise ConflictError(exc.message, code=exc.message) from None
        raise
    record = result["turn"]
    payload: dict[str, Any] = {
        "turn": public_turn({**record, "user_message": result["user_message"]}),
        "user_message": serialize_chat_message(result["user_message"]),
        "execute": bool(result.get("execute")),
        "dispatched": bool(result.get("dispatched")),
    }
    if result.get("assistant_message"):
        payload["assistant_message"] = serialize_chat_message(result["assistant_message"])
    # 202: accepted for background work. A repeat of a finished turn replays it (200).
    return JSONResponse(
        status_code=200 if payload.get("assistant_message") else 202, content=payload
    )


@router.get("/{turn_id}/events", summary="Read a turn's ordered events")
async def read_turn_events(
    turn_id: UUID,
    after_seq: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    db: Client = Depends(get_db),
) -> dict[str, Any]:
    _require_enabled()
    _require_patient(current_user)
    reader = TurnEventReader(db)
    row = await reader.turn(str(current_user.id), str(turn_id))
    if row is None:  # also another patient's turn: never confirm it exists
        raise NotFoundError("Turn", str(turn_id))
    events = await reader.events_after(str(turn_id), after_seq)
    return {
        "turn": public_turn(row),
        "events": events,
        "next_seq": max([after_seq, *(int(e["seq"]) for e in events)]),
    }
