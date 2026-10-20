"""Atomic, patient-scoped Nora turn claims. Never repeat an uncertain clinical action."""

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, cast
from uuid import UUID

from postgrest.exceptions import APIError
from pydantic import ValidationError as PydanticValidationError
from supabase import Client

from app.core.db_pools import run_chat_turn_db
from app.core.exceptions import ExternalServiceError, ValidationError
from app.core.structured_logging import log_event
from app.models.chat import ChatMessage
from app.models.enums import coerce_locale
from app.safety import TRIAGE_COPY, deterministic_safety_floor
from app.services.explanation_service import normalize_patient_summary
from app.utils.localization import resolve_locale_resource

logger = logging.getLogger(__name__)

# Time left for saving a finished reply after the processing budget ends: the save call's own
# 10 second limit plus margin for a slow database. The database deadline is the processing
# budget plus this, so a reply that finished inside its budget is never lost to the lease.
SAVE_GRACE_SECONDS = 30


def turn_budget(model_timeout_seconds: float) -> tuple[int, int]:
    """(processing budget, database lease) in seconds for one Nora turn.

    The processing budget bounds history, context, model calls and tools; the lease adds the
    save grace and stays within the database limit of 120 seconds.
    """
    processing = min(90, max(10, int(model_timeout_seconds) + 10))
    return processing, processing + SAVE_GRACE_SECONDS


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


class ChatTurnService:
    def __init__(self, db: Client, patient_id: str, session_id: str) -> None:
        self.db, self.patient_id, self.session_id = db, patient_id, session_id

    async def call(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        *,
        trigger: str = "service",
        category: str | None = None,
    ) -> dict[str, Any]:
        """One database operation. ``trigger`` names the code path that asked for it, so the
        actor that changes a running turn's status is visible in the logs."""
        started = time.monotonic()
        turn_id = (payload or {}).get("id")
        try:
            response = await asyncio.wait_for(
                run_chat_turn_db(
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
            log_event(
                logger,
                "chat_turn.rpc_failed",
                level=logging.WARNING,
                message=f"Chat turn RPC {action} timed out",
                operation=action,
                trigger=trigger,
                turn_id=turn_id,
                outcome="timeout",
                duration_ms=_elapsed_ms(started),
            )
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
            log_event(
                logger,
                "chat_turn.rpc_failed",
                level=logging.WARNING,
                message=f"Chat turn RPC {action} failed",
                operation=action,
                trigger=trigger,
                turn_id=turn_id,
                outcome=code if code in codes else (getattr(exc, "code", None) or "unknown"),
                duration_ms=_elapsed_ms(started),
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
        data = cast(dict[str, Any], response.data)
        self._log_outcome(action, data, trigger, turn_id, started, category)
        return data

    def _log_outcome(
        self,
        action: str,
        data: dict[str, Any],
        trigger: str,
        turn_id: Any,
        started: float,
        category: str | None,
    ) -> None:
        """One line per state-changing or recovery operation; counts and codes only."""
        fields: dict[str, Any] = {
            "operation": action,
            "trigger": trigger,
            "turn_id": turn_id,
            "duration_ms": _elapsed_ms(started),
            "category": category,
        }
        if action == "begin":
            return  # begin() logs its own line with what it learned
        if action == "recover":
            items = [row for row in data.get("items") or [] if isinstance(row, dict)]
            log_event(
                logger,
                "chat_turn.recover",
                message="Chat turns recovered",
                outcome=f"{len(items)}_turns/"
                f"{sum(1 for row in items if row.get('status') == 'processing')}_processing",
                **fields,
            )
            return
        accepted = bool(data.get("accepted"))
        if accepted:
            fields["late"] = bool(data.get("late"))
            log_event(
                logger,
                f"chat_turn.{action}",
                message=f"Chat turn {action} accepted",
                accepted=True,
                outcome="accepted",
                **fields,
            )
            return
        # An old database function returns no reason: say so rather than guess.
        if action == "dismiss":
            # Nothing to dismiss (already dismissed, or still running): not a refusal.
            log_event(
                logger,
                "chat_turn.dismiss",
                message="Chat turn dismiss matched no turn",
                accepted=False,
                outcome="none_dismissible",
                **fields,
            )
            return
        reason = str(data.get("reason") or "unknown")
        log_event(
            logger,
            f"chat_turn.{action}",
            level=logging.WARNING,
            message=f"Chat turn {action} rejected: {reason}",
            accepted=False,
            outcome="rejected",
            reason=reason,
            **fields,
        )

    async def begin(
        self, request: dict[str, Any], timeout: int, *, queued: bool = False
    ) -> dict[str, Any]:
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
        started = time.monotonic()
        result = await self.call(
            "begin",
            {
                **stable,
                "client_message_id": key,
                "request_hash": fingerprint,
                "timeout_seconds": timeout,
                # A queued turn is executed by the worker service; omitted keeps the
                # in-process behaviour and the exact payload older functions expect.
                **({"queued": True} if queued else {}),
            },
        )
        turn = result.get("turn") or {}
        attempt = int(turn.get("attempt") or 1)
        log_event(
            logger,
            "chat_turn.retry" if result.get("execute") and attempt > 1 else "chat_turn.begin",
            message="Chat turn retried"
            if result.get("execute") and attempt > 1
            else "Chat turn begun",
            operation="begin",
            turn_id=turn.get("id"),
            execute=bool(result.get("execute")),
            attempt=attempt,
            status=turn.get("status"),
            outcome="execute" if result.get("execute") else "replay",
            duration_ms=_elapsed_ms(started),
        )
        document = (turn or {}).get("document_context")
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
        result = await self.service.call("actions", self.identity, trigger="execution")
        if not result.get("accepted"):
            raise ValidationError("CHAT_TURN_EXPIRED")

    async def finish(self, message: dict[str, Any]) -> dict[str, Any]:
        result = await self.service.call(
            "complete",
            # The turn's identity wins: the reply carries its own "id", which must never
            # replace the turn id the database looks the lease up by.
            {**message, **self.identity},
            trigger="execution",
        )
        if not result.get("accepted"):
            raise ValidationError("CHAT_TURN_EXPIRED")
        if result.get("late"):
            # The lease had lapsed but nothing replaced it: the finished reply is kept.
            log_event(
                logger,
                "chat_turn.late_completion",
                level=logging.WARNING,
                message="Accepted a finished Nora reply after its turn lease lapsed",
                turn_id=self.identity["id"],
                late=True,
            )
        self.completed = True
        return cast(dict[str, Any], result["message"])

    async def fail(
        self,
        interrupted: bool = False,
        *,
        trigger: str = "execution_error",
        category: str | None = None,
    ) -> None:
        """Mark the turn failed or interrupted. ``trigger`` says which code path did it."""
        if not self.completed:
            await self.service.call(
                "interrupted" if interrupted else "failed",
                self.identity,
                trigger=trigger,
                category=category,
            )


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
