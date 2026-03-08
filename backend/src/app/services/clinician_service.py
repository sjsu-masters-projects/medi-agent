"""Clinician profiles, patient lists, invite codes."""


class ClinicianService:

    async def get_profile(self, clinician_id: str) -> dict:
        raise NotImplementedError

    async def get_patients(self, clinician_id: str) -> list:
        raise NotImplementedError

    async def get_patient_detail(self, clinician_id: str, patient_id: str) -> dict:
        raise NotImplementedError

    async def generate_invite_code(self, clinician_id: str) -> str:
        raise NotImplementedError
