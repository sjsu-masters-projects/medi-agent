"""Clinician routes — profile, patient list, dashboard, deep dive, SOAP notes.

All endpoints require authentication as a clinician.

New in Phase 6:
    GET  /me/dashboard                                   — Risk Radar
    GET  /me/patients/{id}/deep-dive                     — Patient Deep Dive
    POST /me/patients/{id}/soap-note                     — Generate SOAP note
    POST /me/patients/{id}/obligations                   — Set patient obligation
    POST /me/patients/{id}/documents/{doc_id}/annotate   — Save doc annotation
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from supabase import Client

from app.core.security import require_role
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.clinician import ClinicianRead, ClinicianUpdate
from app.models.dashboard import AnnotationCreate, ObligationSetRequest, SoapNoteRequest
from app.models.patient import PatientRead
from app.services.clinician_service import ClinicianService

router = APIRouter()

_clinician_dep = require_role("clinician")


def _get_service(db: Client = Depends(get_db)) -> ClinicianService:
    return ClinicianService(db)


# ── Existing endpoints ───────────────────────────────────────────────────────


@router.get("/me", response_model=ClinicianRead, summary="Get my clinician profile")
async def get_my_profile(
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.get_profile(user.id)


@router.put("/me", response_model=ClinicianRead, summary="Update my clinician profile")
async def update_my_profile(
    data: ClinicianUpdate,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.update_profile(user.id, data.model_dump(exclude_unset=True))


@router.get(
    "/me/patients",
    summary="List my assigned patients",
    description="Returns all patients with an active care_team relationship.",
)
async def get_my_patients(
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.get_patients(user.id)


@router.get(
    "/me/patients/{patient_id}",
    response_model=PatientRead,
    summary="Get patient detail",
    description="Only accessible if you have an active care team assignment.",
)
async def get_patient_detail(
    patient_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.get_patient_detail(user.id, patient_id)


@router.post(
    "/me/invite-code",
    summary="Generate a patient invite code",
    description="Creates a pending care_team row. Share the code with a patient.",
)
async def generate_invite_code(
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.generate_invite_code(user.id)


# ── Phase 6 endpoints ────────────────────────────────────────────────────────


@router.get(
    "/me/dashboard",
    summary="Risk Radar — clinician dashboard",
    description=(
        "Returns risk level, adherence score, ADR count, and last activity "
        "for all assigned patients. Sorted by risk (high first)."
    ),
)
async def get_dashboard(
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    """GET /api/v1/clinicians/me/dashboard

    Risk Radar endpoint — see DashboardResponse model.
    """
    return await service.get_dashboard_data(user.id)


@router.get(
    "/me/patients/{patient_id}/deep-dive",
    summary="Patient Deep Dive — full aggregated view",
    description=(
        "Returns demographics, active medications, 30-day adherence series, "
        "symptom reports, chat transcript, conditions, allergies, documents, "
        "and the latest AI-generated SOAP note."
    ),
)
async def get_patient_deep_dive(
    patient_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    """GET /api/v1/clinicians/me/patients/{patient_id}/deep-dive"""
    return await service.get_patient_deep_dive(user.id, patient_id)


@router.post(
    "/me/patients/{patient_id}/soap-note",
    summary="Generate AI SOAP note",
    description=(
        "Triggers the LangGraph Summarization Agent (Gemini 3.1 Pro Preview) "
        "to generate a SOAP note from patient data. Stores result in soap_notes table. "
        "Note: this may take 15-30 seconds."
    ),
)
async def generate_soap_note(
    patient_id: UUID,
    request: SoapNoteRequest,
    db: Client = Depends(get_db),
    user: CurrentUser = Depends(_clinician_dep),
) -> Any:
    """POST /api/v1/clinicians/me/patients/{patient_id}/soap-note

    Triggers the Summarization Agent. Returns the generated SOAP note.
    """
    from app.agents.summarization.agent import SummarizationAgent, SummarizationInput

    # Verify care team assignment before running the expensive agent
    service = ClinicianService(db)
    await service.get_patient_detail(user.id, patient_id)

    agent = SummarizationAgent(db=db)
    output = await agent(
        SummarizationInput(
            user_id=user.id,
            patient_id=patient_id,
            lookback_days=request.lookback_days,
        )
    )

    return {
        "status": output.status,
        "soap_note_id": output.soap_note_id,
        "soap_note": output.soap_note,
    }


@router.post(
    "/me/patients/{patient_id}/obligations",
    summary="Set an obligation for a patient",
    description="Clinician creates a diet, exercise, or custom obligation for a patient.",
)
async def set_patient_obligation(
    patient_id: UUID,
    data: ObligationSetRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    """POST /api/v1/clinicians/me/patients/{patient_id}/obligations"""
    return await service.set_patient_obligation(
        user.id, patient_id, data.model_dump()
    )


@router.post(
    "/me/patients/{patient_id}/documents/{document_id}/annotate",
    summary="Add clinician annotation to a document summary",
    description="Saves free-text clinician annotation alongside the AI document summary.",
)
async def annotate_document(
    patient_id: UUID,
    document_id: UUID,
    data: AnnotationCreate,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    """POST /api/v1/clinicians/me/patients/{patient_id}/documents/{document_id}/annotate"""
    return await service.save_document_annotation(
        user.id, patient_id, document_id, data.annotation_text
    )
