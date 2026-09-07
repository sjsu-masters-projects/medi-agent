"""SMART-on-FHIR routes for local-clinician initiated sandbox imports."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import RedirectResponse
from supabase import Client

from app.config import settings
from app.core.exceptions import AuthorizationError, ExternalServiceError, ValidationError
from app.core.security import require_role
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.clinical_fact import ClinicalFactReviewState
from app.models.fhir_import import (
    ClinicalFactCorrectionRequest,
    ClinicalFactReviewRequest,
    FhirIdentityBindingRead,
    FhirIdentityBindingRequest,
    FhirPatientReviewRead,
    FhirReviewSourceDetailRead,
    SmartHandoffRedeemRequest,
    SmartHandoffRedeemResponse,
    SmartImportRead,
    SmartLaunchRequest,
    SmartLaunchResponse,
)
from app.models.reconciliation import (
    ReconciliationDecisionRead,
    ReconciliationDecisionRequest,
    ReconciliationPreviewRead,
)
from app.services.clinical_fact_service import ClinicalFactService
from app.services.clinical_reconciliation_service import ClinicalReconciliationService
from app.services.external_patient_binding_service import ExternalPatientBindingService
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


def _clinical_reconciliation_service(db: Client = Depends(get_db)) -> ClinicalReconciliationService:
    return ClinicalReconciliationService(db)


def _external_patient_binding_service(
    db: Client = Depends(get_db),
) -> ExternalPatientBindingService:
    return ExternalPatientBindingService(db)


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
    try:
        result = service.handle_callback(state=state, code=code, error=error)
    except (AuthorizationError, ExternalServiceError, ValidationError):
        # Do not strand the clinician on an API JSON error or reflect a provider
        # error description into the portal. The next attempt must start fresh.
        return RedirectResponse(
            url=f"{settings.clinician_portal_url.rstrip('/')}/smart-import?smart_error=authorization_failed",
            status_code=status.HTTP_303_SEE_OTHER,
        )
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


@router.delete("/patients/{patient_id}/imports/{import_id}")
async def remove_import(
    patient_id: UUID,
    import_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: SmartLaunchService = Depends(_service),
) -> Any:
    """Remove only an unapplied SMART import; accepted local truth is retained."""
    return service.remove_import(
        clinician_id=user.id,
        patient_id=patient_id,
        import_id=import_id,
    )


@router.get(
    "/patients/{patient_id}/imports/{import_id}/identity-binding",
    response_model=FhirIdentityBindingRead,
)
async def import_identity_binding_preview(
    patient_id: UUID,
    import_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: SmartLaunchService = Depends(_service),
    bindings: ExternalPatientBindingService = Depends(_external_patient_binding_service),
) -> FhirIdentityBindingRead:
    service.ensure_assignment(clinician_id=user.id, patient_id=patient_id)
    return FhirIdentityBindingRead.model_validate(
        bindings.preview(import_id=import_id, patient_id=patient_id)
    )


@router.post(
    "/patients/{patient_id}/imports/{import_id}/identity-binding",
    response_model=FhirIdentityBindingRead,
)
async def confirm_import_identity_binding(
    patient_id: UUID,
    import_id: UUID,
    request: FhirIdentityBindingRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: SmartLaunchService = Depends(_service),
    bindings: ExternalPatientBindingService = Depends(_external_patient_binding_service),
) -> FhirIdentityBindingRead:
    service.ensure_assignment(clinician_id=user.id, patient_id=patient_id)
    return FhirIdentityBindingRead.model_validate(
        bindings.confirm(
            import_id=import_id,
            patient_id=patient_id,
            clinician_id=user.id,
            confirmation_note=request.confirmation_note,
        )
    )


@router.get("/patients/{patient_id}/facts", response_model=FhirPatientReviewRead)
async def list_pending_facts(
    patient_id: UUID,
    review_state: ClinicalFactReviewState = Query(default=ClinicalFactReviewState.PENDING_REVIEW),
    fact_type: str | None = Query(default=None, min_length=1, max_length=64),
    source_kind: str | None = Query(default=None, pattern="^(smart|document)$"),
    reconciliation_state: str | None = Query(default=None, min_length=1, max_length=32),
    from_date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
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
            fact_type=fact_type,
            source_kind=source_kind,
            reconciliation_state=reconciliation_state,
            from_date=from_date,
            to_date=to_date,
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
    reconciliation: ClinicalReconciliationService = Depends(_clinical_reconciliation_service),
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
    reconciliation: ClinicalReconciliationService = Depends(_clinical_reconciliation_service),
) -> Any:
    service.ensure_assignment(clinician_id=user.id, patient_id=patient_id)
    fact = ClinicalFactService(db).get_fact(fact_id, patient_id)
    if str(fact.get("fact_type")) in ClinicalReconciliationService.PROJECTABLE_FACT_TYPES:
        raise ValidationError(
            "Use the reconciliation decision endpoint to add, update, or keep a local record"
        )
    return reconciliation.decide(
        fact_id=fact_id,
        patient_id=patient_id,
        actor_id=user.id,
        request=ReconciliationDecisionRequest(
            decision="mark_reviewed",
            note=request.note,
            idempotency_key=uuid4(),
        ),
    )


@router.get(
    "/patients/{patient_id}/facts/{fact_id}/reconciliation-preview",
    response_model=ReconciliationPreviewRead,
)
async def reconciliation_preview(
    patient_id: UUID,
    fact_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: SmartLaunchService = Depends(_service),
    reconciliation: ClinicalReconciliationService = Depends(_clinical_reconciliation_service),
) -> ReconciliationPreviewRead:
    service.ensure_assignment(clinician_id=user.id, patient_id=patient_id)
    return ReconciliationPreviewRead.model_validate(
        reconciliation.preview(fact_id=fact_id, patient_id=patient_id)
    )


@router.post(
    "/patients/{patient_id}/facts/{fact_id}/reconcile",
    response_model=ReconciliationDecisionRead,
)
async def reconcile_fact(
    patient_id: UUID,
    fact_id: UUID,
    request: ReconciliationDecisionRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: SmartLaunchService = Depends(_service),
    reconciliation: ClinicalReconciliationService = Depends(_clinical_reconciliation_service),
) -> ReconciliationDecisionRead:
    service.ensure_assignment(clinician_id=user.id, patient_id=patient_id)
    return ReconciliationDecisionRead.model_validate(
        reconciliation.decide(
            fact_id=fact_id,
            patient_id=patient_id,
            actor_id=user.id,
            request=request,
        )
    )


@router.post("/patients/{patient_id}/facts/{fact_id}/reject")
async def reject_fact(
    patient_id: UUID,
    fact_id: UUID,
    request: ClinicalFactReviewRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: SmartLaunchService = Depends(_service),
    db: Client = Depends(get_db),
    reconciliation: ClinicalReconciliationService = Depends(_clinical_reconciliation_service),
) -> Any:
    service.ensure_assignment(clinician_id=user.id, patient_id=patient_id)
    fact = ClinicalFactService(db).get_fact(fact_id, patient_id)
    if str(fact.get("fact_type")) in ClinicalReconciliationService.PROJECTABLE_FACT_TYPES:
        return reconciliation.decide(
            fact_id=fact_id,
            patient_id=patient_id,
            actor_id=user.id,
            request=ReconciliationDecisionRequest(
                decision="reject",
                note=request.note,
                idempotency_key=uuid4(),
            ),
        )
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
