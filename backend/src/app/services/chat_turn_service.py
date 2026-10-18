"""Atomic, patient-scoped Nora turn claims. Never repeat an uncertain clinical action."""

import asyncio
import hashlib
import json
import logging
from typing import Any, cast
from uuid import UUID

from postgrest.exceptions import APIError
from pydantic import ValidationError as PydanticValidationError
from supabase import Client

from app.core.exceptions import ExternalServiceError, ValidationError
from app.models.chat import ChatMessage
from app.models.enums import coerce_locale
from app.safety import TRIAGE_COPY, deterministic_safety_floor
from app.services.explanation_service import normalize_patient_summary
from app.utils.localization import resolve_locale_resource

logger = logging.getLogger(__name__)


class ChatTurnService:
    def __init__(self, db: Client, patient_id: str, session_id: str) -> None:
        self.db, self.patient_id, self.session_id = db, patient_id, session_id

    async def call(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.db.rpc(
                        "chat_turn_operation",
                        {
                            "p_patient": self.patient_id,
                            "p_session": self.session_id,
                            "p_action": action,
                            "p_payload": payload or {},
                        },
                    ).execute
                ),
                timeout=10,
            )
        except TimeoutError:
            logger.warning("Chat turn RPC %s timed out", action)
            # The underlying request may still commit: callers must retain its identity.
            raise ExternalServiceError(
                "Chat", "Saved chat recovery is temporarily unavailable."
            ) from None
        except APIError as exc:
            codes = {
                "CHAT_TURN_BUSY",
                "CHAT_TURN_CONFLICT",
                "CHAT_TURN_INVALID",
                "CHAT_DOCUMENT_UNAVAILABLE",
                "CHAT_DOCUMENT_CHANGED",
            }
            code = str(exc.message)
            # Postgres code and RPC action only: enough to tell a missing column from a
            # permission error in plain-text logs, without row values.
            logger.warning(
                "Chat turn RPC %s failed: %s", action, getattr(exc, "code", None) or "unknown"
            )
            if code in codes:
                raise ValidationError(code) from None
            raise ExternalServiceError(
                "Chat", "Saved chat recovery is unavailable. Try again later."
            ) from None
        if not isinstance(response.data, dict):
            raise ExternalServiceError(
                "Chat", "Saved chat recovery is unavailable. Try again later."
            )
        return cast(dict[str, Any], response.data)

    async def begin(self, request: dict[str, Any], timeout: int) -> dict[str, Any]:
        try:
            if "document_id" not in request:
                raise ValueError("Explicit document selection required")
            key = str(UUID(str(request["client_message_id"])))
            document_id = (
                str(UUID(str(request["document_id"]))) if request.get("document_id") else None
            )
        except (KeyError, ValueError, TypeError):
            raise ValidationError("CHAT_TURN_INVALID") from None
        stable: dict[str, Any] = {
            "content": str(request.get("content", "")).strip(),
            "language": coerce_locale(request.get("language")).value,
            "document_id": document_id,
            "audio_url": request.get("audio_url"),
        }
        if stable["audio_url"] is not None and not isinstance(stable["audio_url"], str):
            raise ValidationError("CHAT_TURN_INVALID")
        if not 1 <= len(stable["content"]) <= 8000:
            raise ValidationError("CHAT_TURN_INVALID")
        fingerprint = hashlib.sha256(
            json.dumps(stable, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        result = await self.call(
            "begin",
            {
                **stable,
                "client_message_id": key,
                "request_hash": fingerprint,
                "timeout_seconds": timeout,
            },
        )
        document = (result.get("turn") or {}).get("document_context")
        if isinstance(document, dict) and "summary" in document:
            document["summary"] = normalize_patient_summary(str(document["summary"]))
        return result


class TurnExecution:
    """Lease-bound changes, fenced against another process or expired deadline."""

    def __init__(self, service: ChatTurnService, record: dict[str, Any]) -> None:
        self.service = service
        self.identity = {"id": record["id"], "lease": record["lease"]}
        self.completed = False

    async def actions(self) -> None:
        result = await self.service.call("actions", self.identity)
        if not result.get("accepted"):
            raise ValidationError("CHAT_TURN_EXPIRED")

    async def finish(self, message: dict[str, Any]) -> dict[str, Any]:
        result = await self.service.call("complete", {**self.identity, **message})
        if not result.get("accepted"):
            raise ValidationError("CHAT_TURN_EXPIRED")
        self.completed = True
        return cast(dict[str, Any], result["message"])

    async def fail(self, interrupted: bool = False) -> None:
        if not self.completed:
            await self.service.call("interrupted" if interrupted else "failed", self.identity)


_SAFE_MESSAGE_KEYS = ("id", "role", "content", "language", "session_id", "created_at")


def _serialize_user_message(row: dict[str, Any]) -> dict[str, Any]:
    """Same shape as chat history; a partial or malformed row keeps only safe fields."""
    try:
        return ChatMessage.model_validate(row).model_dump(mode="json")
    except PydanticValidationError:
        return {key: row[key] for key in _SAFE_MESSAGE_KEYS if key in row}


def public_turn(record: dict[str, Any]) -> dict[str, Any]:
    """No lease, fingerprint, clinical context snapshot or private URL enters socket events."""
    fields = (
        "id",
        "client_message_id",
        "status",
        "attempt",
        "deadline_at",
        "failure_code",
    )
    user_message = record.get("user_message") or {}
    verdict = deterministic_safety_floor(str(user_message.get("content") or ""))
    guidance = None
    if verdict is not None and record.get("status") != "completed":
        key = {
            "emergency_mental_health_keyword": "mental_health_emergency_response",
            "emergency_symptom_keyword": "emergency_response",
            "urgent_medication_error": "medication_error_response",
        }.get(verdict.safety_rule, "emergency_response")
        guidance = resolve_locale_resource(user_message.get("language"), TRIAGE_COPY)[key]
    return {
        **{key: record[key] for key in fields if key in record},
        **(
            {"user_message": _serialize_user_message(record["user_message"])}
            if record.get("user_message") and record.get("status") != "completed"
            else {}
        ),
        "document_id": (record.get("document_context") or {}).get("id"),
        **({"safety_guidance": guidance} if guidance else {}),
        "retryable": record.get("status") in {"failed", "interrupted"}
        and not record.get("dismissed_at")
        and not record.get("actions_started")
        and int(record.get("attempt", 1)) < 3,
    }
