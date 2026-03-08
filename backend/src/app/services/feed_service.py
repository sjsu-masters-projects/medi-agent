"""Today Feed — aggregates meds + obligations across all providers."""


class FeedService:

    async def get_today(self, patient_id: str) -> dict:
        raise NotImplementedError
