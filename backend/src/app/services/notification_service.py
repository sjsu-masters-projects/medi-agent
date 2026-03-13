"""Notifications — push, in-app, email."""


class NotificationService:
    async def create(self, patient_id: str, data: dict) -> dict:
        raise NotImplementedError

    async def list_for_patient(self, patient_id: str) -> list:
        raise NotImplementedError

    async def mark_read(self, notification_id: str) -> dict:
        raise NotImplementedError
