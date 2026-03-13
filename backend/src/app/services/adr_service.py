"""ADR assessments and MedWatch form lifecycle."""

from typing import Any


class ADRService:
    async def list_assessments(self, clinician_id: str, status: str | None = None) -> Any:
        raise NotImplementedError

    async def get_assessment(self, assessment_id: str) -> Any:
        raise NotImplementedError

    async def approve_medwatch(self, draft_id: str) -> Any:
        raise NotImplementedError

    async def dismiss_medwatch(self, draft_id: str, reason: str) -> Any:
        raise NotImplementedError
