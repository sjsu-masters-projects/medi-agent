"""Today Feed — aggregates meds + obligations across all providers."""

from typing import Any


class FeedService:
    async def get_today(self, patient_id: str) -> Any:
        raise NotImplementedError
