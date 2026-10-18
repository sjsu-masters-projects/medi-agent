"""Stage a durable reply until the existing turn pipeline has finished its actions."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.models.enums import ChatRole
from app.services.chat_service import ChatService
from app.services.chat_turn_service import TurnExecution


class TurnChatService(ChatService):
    def __init__(
        self, original: ChatService, execution: TurnExecution, user: dict[str, Any]
    ) -> None:
        super().__init__(original.db)
        self.execution, self.user = execution, user
        self.reply: dict[str, Any] | None = None
        self.pending_state: dict[str, Any] | None = None
        self.pending_state_version: str | None = None

    async def save_message(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if self._coerce_role(data.get("role")) == ChatRole.USER.value:
            return self.user
        if self.reply is not None:
            raise RuntimeError("Only one reply can be staged per turn")
        self.reply = {
            **data,
            "id": str(uuid4()),
            "patient_id": patient_id,
            "role": self._coerce_role(data.get("role")),
            "language": self._coerce_language(data.get("language")),
            "created_at": datetime.now(UTC).isoformat(),
        }
        return self.reply

    async def save_symptom_report(
        self, patient_id: str, report: dict[str, Any]
    ) -> dict[str, Any] | None:
        await self.execution.actions()
        return await super().save_symptom_report(patient_id, report)

    async def notify_assigned_clinicians(self, patient_id: str, payload: dict[str, Any]) -> int:
        await self.execution.actions()
        return await super().notify_assigned_clinicians(patient_id, payload)

    async def update_conversation_state(
        self, patient_id: str, updates: dict[str, Any], *, expected_updated_at: str | None = None
    ) -> dict[str, Any]:
        # Metadata is a projection, not the authority for saved message completion.
        self.pending_state = updates
        self.pending_state_version = expected_updated_at
        return {**updates, "updated_at": datetime.now(UTC).isoformat()}

    async def complete(self) -> dict[str, Any]:
        if self.reply is None:
            raise RuntimeError("A turn completed without a reply")
        return await self.execution.finish({**self.reply, "message_id": self.reply["id"]})


class TurnEmitter:
    def __init__(self, send: Callable[[dict[str, Any]], Awaitable[bool]]) -> None:
        self.send = send
        self.complete_event: dict[str, Any] | None = None

    async def send_json(self, event: dict[str, Any]) -> None:
        if event.get("type") == "assistant_complete":
            self.complete_event = event
        else:
            await self.send(event)
