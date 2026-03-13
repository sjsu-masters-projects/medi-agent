"""Chat message storage and history."""


class ChatService:
    async def save_message(self, patient_id: str, data: dict) -> dict:
        raise NotImplementedError

    async def get_history(self, patient_id: str, limit: int = 50) -> list:
        raise NotImplementedError
