"""Notification persistence service."""

from __future__ import annotations

import asyncio
from typing import Any

from supabase import Client

from app.core.exceptions import ExternalServiceError, NotFoundError


class NotificationService:
    """Create and read patient notifications."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def create(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "patient_id": patient_id,
            "notification_type": data.get("notification_type"),
            "title": str(data.get("title", "")).strip(),
            "body": str(data.get("body", "")).strip(),
            "action_url": data.get("action_url"),
        }
        result = await self._execute(self.db.table("notifications").insert(payload))
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        if not rows:
            raise ExternalServiceError("Supabase", "Failed to create notification")
        return rows[0]

    async def list_for_patient(self, patient_id: str) -> list[dict[str, Any]]:
        result = await self._execute(
            self.db.table("notifications")
            .select("*")
            .eq("patient_id", patient_id)
            .order("created_at", desc=True)
            .limit(100)
        )
        return [row for row in (result.data or []) if isinstance(row, dict)]

    async def mark_read(self, patient_id: str, notification_id: str) -> dict[str, Any]:
        result = await self._execute(
            self.db.table("notifications")
            .update({"is_read": True})
            .eq("id", notification_id)
            .eq("patient_id", patient_id)
        )
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        if not rows:
            raise NotFoundError("Notification", notification_id)
        return rows[0]

    @staticmethod
    async def _execute(query: Any) -> Any:
        return await asyncio.to_thread(query.execute)
