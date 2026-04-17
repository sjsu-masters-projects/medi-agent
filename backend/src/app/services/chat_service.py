"""Chat message storage and history."""

from __future__ import annotations

import asyncio
from typing import Any

from supabase import Client

from app.core.exceptions import ExternalServiceError
from app.models.enums import ChatRole, Language


class ChatService:
    """Persist and retrieve patient chat messages."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def save_message(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "patient_id": patient_id,
            "content": str(data.get("content", "")).strip(),
            "role": self._coerce_role(data.get("role")),
            "language": self._coerce_language(data.get("language")),
            "audio_url": data.get("audio_url"),
            "intent": data.get("intent"),
        }

        result = await self._execute(self.db.table("chat_messages").insert(payload))
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        if not rows:
            raise ExternalServiceError("Supabase", "Failed to save chat message")

        return rows[0]

    async def get_history(
        self,
        patient_id: str,
        limit: int = 50,
        before: str | None = None,
    ) -> list[dict[str, Any]]:
        query = (
            self.db.table("chat_messages")
            .select("id, patient_id, content, role, intent, language, audio_url, created_at")
            .eq("patient_id", patient_id)
            .order("created_at")
            .limit(limit)
        )
        if before:
            query = query.lt("created_at", before)

        result = await self._execute(query)
        return [row for row in (result.data or []) if isinstance(row, dict)]

    async def _execute(self, query: Any) -> Any:
        return await asyncio.to_thread(query.execute)

    @staticmethod
    def _coerce_role(value: Any) -> str:
        if isinstance(value, ChatRole):
            return value.value
        raw = str(value or ChatRole.USER.value)
        return raw if raw in {member.value for member in ChatRole} else ChatRole.USER.value

    @staticmethod
    def _coerce_language(value: Any) -> str:
        if isinstance(value, Language):
            return value.value
        raw = str(value or Language.EN.value)
        return raw if raw in {member.value for member in Language} else Language.EN.value
