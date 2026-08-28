"""SMART-on-FHIR routes for local-clinician initiated sandbox imports."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import RedirectResponse
from supabase import Client

from app.config import settings
from app.core.exceptions import ValidationError
from app.core.security import require_role
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.clinical_fact import ClinicalFactReviewState
from app.models.fhir_import import (
    ClinicalFactCorrectionRequest,
    ClinicalFactReviewRequest,
    FhirPatientReviewRead,
    FhirReviewSourceDetailRead,
    SmartHandoffRedeemRequest,
    SmartHandoffRedeemResponse,
    SmartImportRead,
    SmartLaunchRequest,
    SmartLaunchResponse,
)
from app.services.clinical_fact_service import ClinicalFactService
from app.services.fhir_audit_export_service import FhirAuditExportService
from app.services.fhir_import_review_service import FhirImportReviewService
from app.services.smart_launch_service import SmartLaunchService

router = APIRouter()
_clinician_dep = require_role("clinician")


def _service(db: Client = Depends(get_db)) -> SmartLaunchService:
    return SmartLaunchService(db)


def _fhir_audit_export_service(db: Client = Depends(get_db)) -> FhirAuditExportService:
    return FhirAuditExportService(db)


def _fhir_import_review_service(db: Client = Depends(get_db)) -> FhirImportReviewService:
    return FhirImportReviewService(db)


@router.post(
    "/launch", response_model=SmartLaunchResponse, summary="Start a locally authorized SMART launch"
)
async def start_launch(
    request: SmartLaunchRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: SmartLaunchService = Depends(_service),
) -> Any:
    return service.start_launch(
        clinician_id=user.id,
        patient_id=request.patient_id,
        issuer=str(request.issuer),
        launch_context=request.launch_context,
    )


@router.get(
    "/callback", response_model=None, summary="Complete SMART OAuth and redirect to local review"
)
async def smart_callback(
    state: str = Query(min_length=20, max_length=512),
    code: str | None = Query(default=None, min_length=1, max_length=2048),
    error: str | None = Query(default=None, max_length=500),
    service: SmartLaunchService = Depends(_service),
) -> RedirectResponse:
    result = service.handle_callback(state=state, code=code, error=error)
    redirect_url = (
        f"{settings.clinician_portal_url.rstrip('/')}/smart-import?ticket={result['ticket']}"
    )
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/handoff/redeem", response_model=SmartHandoffRedeemResponse)
async def redeem_handoff(
    request: SmartHandoffRedeemRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: SmartLaunchService = Depends(_service),
) -> Any:
    return service.redeem_handoff(clinician_id=user.id, ticket=request.ticket)


@router.get("/patients/{patient_id}/imports", response_model=list[SmartImportRead])
async def list_imports(
    patient_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: SmartLaunchService = Depends(_service),
) -> Any:
    return service.list_imports(clinician_id=user.id, patient_id=patient_id)


@router.get("/patients/{patient_id}/facts", response_model=FhirPatientReviewRead)
async def list_pending_facts(
    patient_id: UUID,
    review_state: ClinicalFactReviewState = Query(default=ClinicalFactReviewState.PENDING_REVIEW),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=50),
    user: CurrentUser = Depends(_clinician_dep),
    service: SmartLaunchService = Depends(_service),
    review_service: FhirImportReviewService = Depends(_fhir_import_review_service),
) -> FhirPatientReviewRead:
    service.ensure_assignment(clinician_id=user.id, patient_id=patient_id)
    return FhirPatientReviewRead.model_validate(
        review_service.list_facts(
            patient_id=patient_id,
            review_state=review_state,
            offset=offset,
            limit=limit,
        )
    )


@router.get("/patients/{patient_id}/facts/{fact_id}/lineage")
async def fact_lineage(
    patient_id: UUID,
    fact_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: SmartLaunchService = Depends(_service),
    db: Client = Depends(get_db),
) -> Any:
    service.ensure_assignment(clinician_id=user.id, patient_id=patient_id)
    return ClinicalFactService(db).get_lineage(fact_id, patient_id)


@router.get(
    "/patients/{patient_id}/facts/{fact_id}/source", response_model=FhirReviewSourceDetailRead
)
async def fact_source(
    patient_id: UUID,
    fact_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: SmartLaunchService = Depends(_service),
    review_service: FhirImportReviewService = Depends(_fhir_import_review_service),
) -> FhirReviewSourceDetailRead:
    service.ensure_assignment(clinician_id=user.id, patient_id=patient_id)
    source = review_service.get_source(fact_id=fact_id, patient_id=patient_id)
    if source is None:
        raise ValidationError("FHIR source is unavailable for this clinical fact")
    return FhirReviewSourceDetailRead.model_validate(source)


@router.get("/patients/{patient_id}/facts/{fact_id}/fhir-audit")
async def fact_fhir_audit(
    patient_id: UUID,
    fact_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: SmartLaunchService = Depends(_service),
    export_service: FhirAuditExportService = Depends(_fhir_audit_export_service),
) -> Any:
    """Generate validated FHIR provenance/audit resources without external writes."""
    service.ensure_assignment(clinician_id=user.id, patient_id=patient_id)
    return export_service.export_for_fact(fact_id=fact_id, patient_id=patient_id)


@router.post("/patients/{patient_id}/facts/{fact_id}/approve")
async def approve_fact(
    patient_id: UUID,
    fact_id: UUID,
    request: ClinicalFactReviewRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: SmartLaunchService = Depends(_service),
    db: Client = Depends(get_db),
) -> Any:
    service.ensure_assignment(clinician_id=user.id, patient_id=patient_id)
    return ClinicalFactService(db).approve(
        fact_id, patient_id, reviewer_id=user.id, note=request.note
    )


@router.post("/patients/{patient_id}/facts/{fact_id}/reject")
async def reject_fact(
    patient_id: UUID,
    fact_id: UUID,
    request: ClinicalFactReviewRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: SmartLaunchService = Depends(_service),
    db: Client = Depends(get_db),
) -> Any:
    service.ensure_assignment(clinician_id=user.id, patient_id=patient_id)
    return ClinicalFactService(db).reject(
        fact_id, patient_id, reviewer_id=user.id, note=request.note or ""
    )


@router.post("/patients/{patient_id}/facts/{fact_id}/correct")
async def correct_fact(
    patient_id: UUID,
    fact_id: UUID,
    request: ClinicalFactCorrectionRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: SmartLaunchService = Depends(_service),
    db: Client = Depends(get_db),
) -> Any:
    if not request.value:
        raise ValidationError("Corrected fact value is required")
    service.ensure_assignment(clinician_id=user.id, patient_id=patient_id)
    return ClinicalFactService(db).correct(
        fact_id, patient_id, actor_id=user.id, value=request.value, note=request.note
    )
