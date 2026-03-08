"""ADR assessments and MedWatch form lifecycle."""


class ADRService:

    async def list_assessments(self, clinician_id: str, status: str | None = None) -> list:
        raise NotImplementedError

    async def get_assessment(self, assessment_id: str) -> dict:
        raise NotImplementedError

    async def approve_medwatch(self, draft_id: str) -> dict:
        raise NotImplementedError

    async def dismiss_medwatch(self, draft_id: str, reason: str) -> dict:
        raise NotImplementedError
