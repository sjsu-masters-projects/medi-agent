"""Obligation CRUD."""


class ObligationService:

    async def list_obligations(self, patient_id: str) -> list:
        raise NotImplementedError

    async def create(self, patient_id: str, data: dict) -> dict:
        raise NotImplementedError
