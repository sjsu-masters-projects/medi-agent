"""Adherence logging and score calculation."""


class AdherenceService:

    async def log(self, patient_id: str, data: dict) -> dict:
        raise NotImplementedError

    async def get_stats(self, patient_id: str, period_days: int = 30) -> dict:
        raise NotImplementedError
