"""Medication CRUD."""


class MedicationService:

    async def list_medications(self, patient_id: str, active_only: bool = True) -> list:
        raise NotImplementedError

    async def create(self, patient_id: str, data: dict) -> dict:
        raise NotImplementedError

    async def update(self, medication_id: str, data: dict) -> dict:
        raise NotImplementedError
