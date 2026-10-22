"""Medication confirmation routes (MED-002).

A clinician asks the patient to confirm one medication discrepancy; the patient answers. The
answer is evidence for the clinician's reconciliation decision and changes no clinical record.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from supabase import Client

from app.core.security import require_role
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.medication_confirmation import (
    MedicationConfirmationAnswer,
    MedicationConfirmationClinicianRead,
    MedicationConfirmationCreate,
    MedicationConfirmationPatientRead,
)
from app.services.medication_confirmation_service import MedicationConfirmationService

clinician_router = APIRouter()
patient_router = APIRouter()
_clinician_dep = require_role("clinician")
_patient_dep = require_role("patient")


def _service(db: Client = Depends(get_db)) -> MedicationConfirmationService:
    return MedicationConfirmationService(db)


_FACT = "/patients/{patient_id}/facts/{fact_id}/confirmations"


@clinician_router.post(
    _FACT,
    response_model=MedicationConfirmationClinicianRead,
    status_code=status.HTTP_201_CREATED,
    summary="Ask the patient to confirm a medication",
)
async def request_confirmation(
    patient_id: UUID,
    fact_id: UUID,
    body: MedicationConfirmationCreate,
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: MedicationConfirmationService = Depends(_service),
) -> MedicationConfirmationClinicianRead:
    response.headers["Cache-Control"] = "no-store"
    result = await service.request(
        clinician_id=user.id, patient_id=patient_id, fact_id=fact_id, body=body
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return result


@clinician_router.get(
    _FACT,
    response_model=list[MedicationConfirmationClinicianRead],
    summary="The patient's answers for one imported medication",
)
async def list_confirmations(
    patient_id: UUID,
    fact_id: UUID,
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: MedicationConfirmationService = Depends(_service),
) -> list[MedicationConfirmationClinicianRead]:
    response.headers["Cache-Control"] = "no-store"
    return await service.list_for_fact(clinician_id=user.id, patient_id=patient_id, fact_id=fact_id)


@patient_router.get(
    "/medication-confirmations",
    response_model=list[MedicationConfirmationPatientRead],
    summary="Medication questions from my care team",
)
async def list_my_confirmations(
    response: Response,
    user: CurrentUser = Depends(_patient_dep),
    service: MedicationConfirmationService = Depends(_service),
) -> list[MedicationConfirmationPatientRead]:
    response.headers["Cache-Control"] = "no-store"
    return await service.list_for_patient(user.id)


@patient_router.post(
    "/medication-confirmations/{request_id}/answer",
    response_model=MedicationConfirmationPatientRead,
    summary="Answer a medication question (patient testimony, never applied automatically)",
)
async def answer_confirmation(
    request_id: UUID,
    body: MedicationConfirmationAnswer,
    response: Response,
    user: CurrentUser = Depends(_patient_dep),
    service: MedicationConfirmationService = Depends(_service),
) -> MedicationConfirmationPatientRead:
    response.headers["Cache-Control"] = "no-store"
    return await service.answer(patient_id=user.id, request_id=request_id, body=body)
