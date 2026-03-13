"""Chat message storage and history."""

from typing import Any


class ChatService:
    async def save_message(self, patient_id: str, data: dict[str, Any]) -> Any:
        raise NotImplementedError

    async def get_history(self, patient_id: str, limit: int = 50) -> Any:
        raise NotImplementedError
