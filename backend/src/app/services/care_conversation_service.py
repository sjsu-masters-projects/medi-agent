"""Authenticated human messages: all authorization and writes share a DB transaction."""

import asyncio
from typing import Any, cast
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from app.core.exceptions import AuthorizationError, ExternalServiceError, ValidationError
from app.models.auth import CurrentUser
from app.models.care_conversation import (
    ConversationCreate,
    ConversationReadMarker,
    ConversationSend,
)


class CareConversationService:
    def __init__(self, db: Client, actor: CurrentUser) -> None:
        self.db = db
        self.actor = actor

    async def recipients(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], await self._call("recipients"))

    async def list_conversations(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], await self._call("list"))

    async def open_conversation(self, data: ConversationCreate) -> dict[str, Any]:
        return cast(dict[str, Any], await self._call("open", data.model_dump(mode="json")))

    async def messages(self, conversation: UUID, options: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self._call(
                "messages",
                {
                    "conversation_id": str(conversation),
                    **options,
                },
            ),
        )

    async def send(self, conversation: UUID, data: ConversationSend) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self._call(
                "send",
                {
                    "conversation_id": str(conversation),
                    **data.model_dump(mode="json"),
                },
            ),
        )

    async def mark_read(self, conversation: UUID, data: ConversationReadMarker) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self._call(
                "read",
                {
                    "conversation_id": str(conversation),
                    **data.model_dump(mode="json"),
                },
            ),
        )

    async def _call(self, action: str, payload: dict[str, Any] | None = None) -> Any:
        if self.actor.role not in {"patient", "clinician"}:
            raise self._denial()
        try:
            result = await asyncio.to_thread(
                self.db.rpc(
                    "care_conversation_operation",
                    {
                        "p_actor_id": str(self.actor.id),
                        "p_actor_role": self.actor.role,
                        "p_action": action,
                        "p_payload": payload or {},
                    },
                ).execute
            )
        except APIError as exc:
            if exc.code == "42501":
                raise self._denial() from None
            if exc.code == "22023":
                raise ValidationError("Invalid conversation request") from None
            if exc.code == "23505":
                raise ValidationError(
                    "Message retry does not match the original request",
                    code="MESSAGE_IDEMPOTENCY_MISMATCH",
                ) from None
            # Never log PostgREST details: constraints can echo private message text.
            raise ExternalServiceError("Supabase", "Conversation operation failed") from None
        if not isinstance(result.data, dict | list):
            raise ExternalServiceError("Supabase", "Conversation operation failed")
        return result.data

    def _denial(self) -> AuthorizationError:
        return AuthorizationError(
            "Conversation unavailable",
            actor_id=str(self.actor.id),
            actor_role=self.actor.role,
            target_type="care_conversation",
        )
