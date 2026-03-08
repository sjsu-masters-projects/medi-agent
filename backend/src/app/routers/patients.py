"""Patient routes."""

from fastapi import APIRouter

from app.models import PatientRead, PatientUpdate

router = APIRouter()


@router.get("/me", response_model=PatientRead)
async def get_my_profile() -> dict:
    # TODO: get_current_user → patient_service.get_profile()
    raise NotImplementedError


@router.put("/me", response_model=PatientRead)
async def update_my_profile(data: PatientUpdate) -> dict:
    # TODO: get_current_user → patient_service.update_profile()
    raise NotImplementedError


@router.get("/me/care-team")
async def get_my_care_team() -> list:
    # TODO: get_current_user → patient_service.get_care_team()
    raise NotImplementedError


@router.post("/me/care-team/join")
async def join_clinic(invite_code: str) -> dict:
    # TODO: get_current_user → patient_service.join_clinic()
    raise NotImplementedError
