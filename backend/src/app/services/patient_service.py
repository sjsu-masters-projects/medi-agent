"""Patient profiles and care team."""


class PatientService:

    async def get_profile(self, patient_id: str) -> dict:
        raise NotImplementedError

    async def update_profile(self, patient_id: str, data: dict) -> dict:
        raise NotImplementedError

    async def get_care_team(self, patient_id: str) -> list:
        raise NotImplementedError

    async def join_clinic(self, patient_id: str, invite_code: str) -> dict:
        raise NotImplementedError
