"""Notifications — push, in-app, email."""

from typing import Any


class NotificationService:
    async def create(self, patient_id: str, data: dict[str, Any]) -> Any:
        raise NotImplementedError

    async def list_for_patient(self, patient_id: str) -> Any:
        raise NotImplementedError

    async def mark_read(self, notification_id: str) -> Any:
        raise NotImplementedError
