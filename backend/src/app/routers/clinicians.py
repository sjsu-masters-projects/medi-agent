"""Clinician routes — profile, patient list, dashboard, deep dive, SOAP notes.

All endpoints require authentication as a clinician.

New in Phase 6:
    GET  /me/dashboard                                   — Risk Radar
    GET  /me/patients/{id}/risk                          — Single-patient Risk Radar card
    GET  /me/patients/{id}/deep-dive                     — Patient Deep Dive
    POST /me/patients/{id}/soap-note                     — Generate SOAP note
    POST /me/patients/{id}/obligations                   — Set patient obligation
    POST /me/patients/{id}/documents/{doc_id}/annotate   — Save doc annotation
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from supabase import Client

from app.core.security import require_role
from app.db.connection import get_db
from app.middleware.rate_limit import soap_note_rate_limiter
from app.models.adr import (
    ADRReviewDecisionRequest,
    ADRReviewDecisionResponse,
    ADRReviewQueueItem,
    ADRReviewQueueResponse,
    MedWatchDraftApprovalRequest,
    MedWatchDraftCreateRequest,
    MedWatchDraftDiscardRequest,
    MedWatchDraftExportResponse,
    MedWatchDraftListResponse,
    MedWatchDraftRead,
    MedWatchDraftUpdateRequest,
    MedWatchSubmissionAmendRequest,
    MedWatchSubmissionRecordRequest,
)
from app.models.auth import CurrentUser
from app.models.care_plan import CarePlanVersionRead
from app.models.clinic_membership import (
    ClinicMembershipsResponse,
    ClinicRenameRequest,
    ClinicRenameResponse,
    ClinicScopedRequest,
    DefaultClinicResponse,
    JoinClinicRequest,
    JoinClinicResponse,
    LeaveClinicResponse,
    SetDefaultClinicRequest,
)
from app.models.clinician import ClinicianRead, ClinicianUpdate
from app.models.clinician_message import (
    ClinicianMessageInboxItem,
    ClinicianMessageRead,
    ClinicianPatientMessageCreate,
)
from app.models.dashboard import (
    A2ATimelineResponse,
    AnnotationCreate,
    AnnotationSaveResponse,
    DashboardResponse,
    DashboardSortBy,
    DashboardSortOrder,
    DocumentReviewActionRequest,
    DocumentReviewActionResponse,
    DocumentReviewQueueItem,
    ObligationSetRequest,
    PatientDeepDive,
    PatientRiskData,
    PatientTimelineResponse,
    RiskLevel,
    SoapNoteGenerationResponse,
    SoapNoteRequest,
)
from app.models.enums import ADRStatus
from app.models.external_record_review import ExternalRecordReviewsResponse
from app.models.invite import (
    CurrentInviteCodeResponse,
    InviteCodeGenerateResponse,
    InviteCodeListResponse,
    InviteCodeRevokeResponse,
)
from app.models.medwatch_form_3500 import (
    Form3500OptionsRead,
    Form3500PreviewRead,
    MedWatchListState,
)
from app.models.patient import PatientDetailRead
from app.models.symptom_report_history import ClinicianSymptomReport
from app.services.clinician_service import ClinicianService
from app.services.external_record_review_service import ExternalRecordReviewService
from app.services.medwatch_service import MedWatchService

router = APIRouter()

_clinician_dep = require_role("clinician")


def _get_service(db: Client = Depends(get_db)) -> ClinicianService:
    return ClinicianService(db)


def _get_medwatch_service(db: Client = Depends(get_db)) -> MedWatchService:
    return MedWatchService(db)


@router.get("/me/external-record-reviews", response_model=ExternalRecordReviewsResponse)
async def get_external_record_reviews(
    clinic_id: UUID | None = Query(None),
    page: int = Query(1, ge=1, le=10000),
    user: CurrentUser = Depends(_clinician_dep),
    db: Client = Depends(get_db),
) -> ExternalRecordReviewsResponse:
    return await ExternalRecordReviewService(db).list_reviews(
        user.id, clinic_id=clinic_id, page=page
    )


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
    "/me/clinics",
    response_model=ClinicMembershipsResponse,
    summary="List my clinics",
    description=(
        "The clinics the signed-in clinician belongs to (active memberships at active "
        "clinics) with the role held at each, for clinic pickers inside clinic-scoped actions."
    ),
)
async def list_my_clinics(
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    response.headers["Cache-Control"] = "private, no-store"
    return await service.memberships.clinics(user.id)


@router.post(
    "/me/clinics",
    response_model=JoinClinicResponse,
    summary="Join another clinic with a clinic code",
    description=(
        "Adds a provider or nurse membership at the clinic to the signed-in account; the "
        "default clinic and other memberships are unchanged. Audited."
    ),
)
async def join_clinic(
    body: JoinClinicRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.memberships.join_by_code(user.id, body.clinic_code, body.role)


@router.put(
    "/me/default-clinic",
    response_model=DefaultClinicResponse,
    summary="Make a clinic my default",
    description=(
        "Changes only which of the caller's clinics is preselected. No membership or patient "
        "link ends. Audited."
    ),
)
async def set_default_clinic(
    body: SetDefaultClinicRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.memberships.set_default(user.id, body.clinic_id)


@router.post(
    "/me/clinics/{clinic_id}/leave",
    response_model=LeaveClinicResponse,
    summary="Leave a clinic",
    description=(
        "Ends the caller's membership at the clinic and their own patient links and unused "
        "invite codes there. Refused for the last clinic and for the clinic's only admin. "
        "Audited."
    ),
)
async def leave_clinic(
    clinic_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.memberships.leave(user.id, clinic_id)


@router.put(
    "/me/clinics/{clinic_id}",
    response_model=ClinicRenameResponse,
    summary="Edit a clinic's display name",
    description="Only an admin at that clinic can edit it. Audited.",
)
async def rename_clinic(
    clinic_id: UUID,
    body: ClinicRenameRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.memberships.rename_clinic(user.id, clinic_id, body.display_name)


@router.get(
    "/me/patients",
    summary="List my assigned patients",
    description="Returns all patients with an active care_team relationship.",
)
async def get_my_patients(
    clinic_id: UUID | None = Query(default=None),
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.get_patients(user.id, clinic_id)


@router.get(
    "/me/patients/{patient_id}",
    response_model=PatientDetailRead,
    summary="Get patient detail",
    description="Only accessible if you have an active care team assignment.",
)
async def get_patient_detail(
    patient_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.get_patient_header(user.id, patient_id)


@router.post(
    "/me/patients/{patient_id}/message",
    response_model=ClinicianMessageRead,
    summary="Send an in-app message to an assigned patient",
)
async def send_patient_message(
    patient_id: UUID,
    data: ClinicianPatientMessageCreate,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.send_patient_message(user.id, patient_id, data.model_dump())


@router.post(
    "/me/patients/{patient_id}/email",
    response_model=ClinicianMessageRead,
    summary="Retired legacy email-record endpoint",
    deprecated=True,
)
async def send_patient_email(
    patient_id: UUID,
    data: ClinicianPatientMessageCreate,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    await service.get_patient_detail(user.id, patient_id)
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Use private care-team messages. Verified recipients may opt into email notices.",
    )


@router.get(
    "/me/patients/{patient_id}/messages",
    response_model=list[ClinicianMessageRead],
    summary="List messages sent to an assigned patient",
)
async def list_patient_messages(
    patient_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.list_patient_messages(user.id, patient_id)


@router.get(
    "/me/messages",
    response_model=list[ClinicianMessageInboxItem],
    summary="List all messages sent by this clinician",
)
async def list_all_messages(
    clinic_id: UUID | None = Query(default=None),
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.list_all_sent_messages(user.id, clinic_id)


@router.post(
    "/me/invite-code",
    response_model=InviteCodeGenerateResponse,
    summary="Generate a patient invite code",
    description="Creates a pending care_team row. Share the code with a patient.",
)
async def generate_invite_code(
    body: ClinicScopedRequest | None = None,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> InviteCodeGenerateResponse:
    clinic_id = body.clinic_id if body else None
    payload = await service.generate_invite_code(user.id, clinic_id)
    return InviteCodeGenerateResponse.model_validate(payload)


@router.get(
    "/me/invite-code",
    response_model=CurrentInviteCodeResponse,
    summary="Get current patient invite code",
    description="Returns the latest pending patient invite code for this clinician, if one exists.",
)
async def get_current_invite_code(
    clinic_id: UUID | None = Query(default=None),
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> CurrentInviteCodeResponse:
    payload = await service.get_current_invite_code(user.id, clinic_id)
    return CurrentInviteCodeResponse.model_validate(payload)


@router.get(
    "/me/invite-codes",
    response_model=InviteCodeListResponse,
    summary="List patient invite codes",
    description=(
        "Returns active, claimed, and inactive invite codes generated by this clinician "
        "for patient onboarding and audit visibility."
    ),
)
async def list_invite_codes(
    clinic_id: UUID | None = Query(default=None),
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> InviteCodeListResponse:
    payload = await service.list_invite_codes(user.id, clinic_id)
    return InviteCodeListResponse.model_validate(payload)


@router.post(
    "/me/invite-codes/{care_team_id}/revoke",
    response_model=InviteCodeRevokeResponse,
    summary="Revoke a pending patient invite code",
    description="Marks a pending unclaimed invite code as inactive.",
)
async def revoke_invite_code(
    care_team_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> InviteCodeRevokeResponse:
    payload = await service.revoke_invite_code(user.id, care_team_id)
    return InviteCodeRevokeResponse.model_validate(payload)


# ── Phase 6 endpoints ────────────────────────────────────────────────────────


@router.get(
    "/me/document-review-queue",
    response_model=list[DocumentReviewQueueItem],
    summary="List pending patient-uploaded documents for review",
    description=(
        "Returns pending patient-uploaded documents for patients currently assigned "
        "to the authenticated clinician."
    ),
)
async def get_document_review_queue(
    clinic_id: UUID | None = Query(default=None),
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.list_document_review_queue(user.id, clinic_id)


@router.post(
    "/me/patients/{patient_id}/documents/{document_id}/approve",
    response_model=DocumentReviewActionResponse,
    summary="Approve a pending patient-uploaded document",
)
async def approve_document_review(
    patient_id: UUID,
    document_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.approve_document_review(user.id, patient_id, document_id)


@router.post(
    "/me/patients/{patient_id}/documents/{document_id}/reject",
    response_model=DocumentReviewActionResponse,
    summary="Reject a pending patient-uploaded document",
)
async def reject_document_review(
    patient_id: UUID,
    document_id: UUID,
    request: DocumentReviewActionRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.reject_document_review(
        user.id,
        patient_id,
        document_id,
        request.review_note,
    )


@router.get(
    "/me/dashboard",
    response_model=DashboardResponse,
    summary="Risk Radar — clinician dashboard",
    description=(
        "Returns risk level, adherence score, ADR count, and last activity "
        "for all assigned patients. Sorted by risk (high first)."
    ),
)
async def get_dashboard(
    sort_by: DashboardSortBy = Query(default="risk"),
    sort_order: DashboardSortOrder = Query(default="desc"),
    risk_filter: RiskLevel | None = Query(default=None),
    min_med_count: int | None = Query(default=None, ge=0),
    max_last_activity_days: int | None = Query(default=None, ge=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    clinic_id: UUID | None = Query(default=None),
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    """GET /api/v1/clinicians/me/dashboard

    Risk Radar endpoint — see DashboardResponse model.
    """
    return await service.get_dashboard_data(
        user.id,
        sort_by=sort_by,
        sort_order=sort_order,
        risk_filter=risk_filter,
        min_med_count=min_med_count,
        max_last_activity_days=max_last_activity_days,
        page=page,
        page_size=page_size,
        clinic_id=clinic_id,
    )


@router.get(
    "/me/adr-assessments",
    response_model=ADRReviewQueueResponse,
    summary="List assigned-patient ADR assessments",
    description=(
        "Returns deterministic Naranjo decision support and patient-grounded evidence "
        "for ADR assessments belonging to assigned patients."
    ),
)
async def list_adr_assessments(
    status_filter: ADRStatus | Literal["all"] = Query(default=ADRStatus.DRAFT, alias="status"),
    patient_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    clinic_id: UUID | None = Query(default=None),
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.list_adr_review_queue(
        user.id,
        status_filter=status_filter,
        patient_id=patient_id,
        limit=limit,
        clinic_id=clinic_id,
    )


@router.get(
    "/me/adr-assessments/{assessment_id}",
    response_model=ADRReviewQueueItem,
    summary="Read one assigned-patient ADR assessment",
    description="An unknown or unauthorised id returns the same 404.",
)
async def get_adr_assessment(
    assessment_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.get_adr_review_item(user.id, assessment_id)


@router.post(
    "/me/adr-assessments/{assessment_id}/review",
    response_model=ADRReviewDecisionResponse,
    summary="Review an assigned-patient ADR assessment",
    description=(
        "Atomically records a clinician review, dismissal, or information request "
        "and writes an immutable audit event."
    ),
)
async def review_adr_assessment(
    assessment_id: UUID,
    decision: ADRReviewDecisionRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.review_adr_assessment(user.id, assessment_id, decision)


@router.post(
    "/me/adr-assessments/{assessment_id}/medwatch-draft",
    response_model=MedWatchDraftRead,
    summary="Prepare an editable Form 3500 draft",
    description=(
        "Creates an evidence-attributed Form FDA 3500 draft after an explicit clinician "
        "reportability decision. This does not submit anything to the FDA."
    ),
)
async def create_medwatch_draft(
    assessment_id: UUID,
    request: MedWatchDraftCreateRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: MedWatchService = Depends(_get_medwatch_service),
) -> Any:
    return await service.create_draft(user.id, assessment_id, request)


@router.get(
    "/me/medwatch-drafts",
    response_model=MedWatchDraftListResponse,
    summary="List assigned-patient Form 3500 drafts",
    description="`state` is `active` (default; draft or approved), `submitted` or `discarded`.",
)
async def list_medwatch_drafts(
    state: MedWatchListState = Query(default="active"),
    clinic_id: UUID | None = Query(default=None),
    user: CurrentUser = Depends(_clinician_dep),
    service: MedWatchService = Depends(_get_medwatch_service),
) -> Any:
    return await service.list_drafts(user.id, state, clinic_id)


@router.get(
    "/me/medwatch-drafts/form-3500-options",
    response_model=Form3500OptionsRead,
    summary="Form 3500 option lists for the draft editor",
)
async def get_medwatch_form_options(
    _user: CurrentUser = Depends(_clinician_dep),
    service: MedWatchService = Depends(_get_medwatch_service),
) -> Any:
    return service.form_options()


@router.get(
    "/me/medwatch-drafts/{draft_id}",
    response_model=MedWatchDraftRead,
    summary="Read one assigned-patient Form 3500 draft",
    description="An unknown or unauthorised id returns the same 404.",
)
async def get_medwatch_draft(
    draft_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: MedWatchService = Depends(_get_medwatch_service),
) -> Any:
    return await service.get_draft(user.id, draft_id)


@router.get(
    "/me/medwatch-drafts/{draft_id}/preview.pdf",
    response_class=Response,
    summary="Watermarked Form FDA 3500 PDF preview of a draft",
    description=(
        "The filled form stamped 'DRAFT - not for submission'. It is not an export: no audit "
        "event and no state change."
    ),
    responses={200: {"content": {"application/pdf": {}}}},
)
async def preview_medwatch_draft_pdf(
    draft_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: MedWatchService = Depends(_get_medwatch_service),
) -> Response:
    preview = await service.preview_pdf(user.id, draft_id)
    return Response(
        content=preview["content"],
        media_type=preview["media_type"],
        headers={
            "Content-Disposition": f'inline; filename="{preview["filename"]}"',
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/me/medwatch-drafts/{draft_id}/preview",
    response_model=Form3500PreviewRead,
    summary="Read-only Form 3500 preview of a draft",
)
async def preview_medwatch_draft(
    draft_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: MedWatchService = Depends(_get_medwatch_service),
) -> Any:
    return await service.get_preview(user.id, draft_id)


@router.put(
    "/me/medwatch-drafts/{draft_id}",
    response_model=MedWatchDraftRead,
    summary="Save an editable MedWatch draft",
)
async def update_medwatch_draft(
    draft_id: UUID,
    request: MedWatchDraftUpdateRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: MedWatchService = Depends(_get_medwatch_service),
) -> Any:
    return await service.update_draft(user.id, draft_id, request)


@router.post(
    "/me/medwatch-drafts/{draft_id}/approve",
    response_model=MedWatchDraftRead,
    summary="Approve a MedWatch draft for export",
    description="Records clinician sign-off; it does not file the draft with the FDA.",
)
async def approve_medwatch_draft(
    draft_id: UUID,
    request: MedWatchDraftApprovalRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: MedWatchService = Depends(_get_medwatch_service),
) -> Any:
    return await service.approve_draft(user.id, draft_id, request)


@router.get(
    "/me/medwatch-drafts/{draft_id}/export",
    response_model=MedWatchDraftExportResponse,
    summary="Export an approved Form 3500 draft as JSON",
    description="Returns an approved JSON artifact and never submits it externally.",
)
async def export_medwatch_draft(
    draft_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: MedWatchService = Depends(_get_medwatch_service),
) -> Any:
    return await service.export_draft(user.id, draft_id)


@router.get(
    "/me/medwatch-drafts/{draft_id}/export.pdf",
    response_class=Response,
    summary="Download the official Form FDA 3500 PDF for an approved draft",
    description=(
        "The fillable official form, filled from the stored revision. MediAgent does not "
        "submit it; the clinician does."
    ),
    responses={200: {"content": {"application/pdf": {}}}},
)
async def export_medwatch_draft_pdf(
    draft_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: MedWatchService = Depends(_get_medwatch_service),
) -> Response:
    exported = await service.export_pdf(user.id, draft_id)
    return Response(
        content=exported["content"],
        media_type=exported["media_type"],
        headers={
            "Content-Disposition": f'attachment; filename="{exported["filename"]}"',
            "Cache-Control": "no-store",
        },
    )


@router.post(
    "/me/medwatch-drafts/{draft_id}/discard",
    response_model=MedWatchDraftRead,
    summary="Discard a Form 3500 draft and return its assessment to review",
)
async def discard_medwatch_draft(
    draft_id: UUID,
    request: MedWatchDraftDiscardRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: MedWatchService = Depends(_get_medwatch_service),
) -> Any:
    return await service.discard_draft(user.id, draft_id, request)


@router.post(
    "/me/medwatch-drafts/{draft_id}/submission",
    response_model=MedWatchDraftRead,
    summary="Record a submission the clinician made to FDA outside MediAgent",
    description="Records the clinician's attestation only; nothing is sent to FDA.",
)
async def record_medwatch_submission(
    draft_id: UUID,
    request: MedWatchSubmissionRecordRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: MedWatchService = Depends(_get_medwatch_service),
) -> Any:
    return await service.record_submission(user.id, draft_id, request)


@router.post(
    "/me/medwatch-drafts/{draft_id}/submission/amend",
    response_model=MedWatchDraftRead,
    summary="Amend the current submission record; the original is kept",
)
async def amend_medwatch_submission(
    draft_id: UUID,
    request: MedWatchSubmissionAmendRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: MedWatchService = Depends(_get_medwatch_service),
) -> Any:
    return await service.amend_submission(user.id, draft_id, request)


@router.get(
    "/me/patients/{patient_id}/risk",
    response_model=PatientRiskData,
    summary="Patient Risk Radar snapshot",
    description="Returns the latest risk card payload for one assigned patient.",
)
async def get_patient_risk_snapshot(
    patient_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    """GET /api/v1/clinicians/me/patients/{patient_id}/risk"""
    return await service.get_patient_risk_snapshot(user.id, patient_id)


@router.get(
    "/me/patients/{patient_id}/timeline",
    response_model=PatientTimelineResponse,
    summary="Bounded source-linked patient timeline",
)
async def get_patient_timeline(
    patient_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    """Recent records per source; private conversations belong only to this clinician."""
    return await service.get_patient_timeline(user.id, patient_id)


@router.get(
    "/me/patients/{patient_id}/symptom-reports/{report_id}",
    response_model=ClinicianSymptomReport,
    summary="Structured patient-confirmed symptom report",
)
async def get_symptom_report(
    patient_id: UUID,
    report_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    """Confirmed answers, provenance and review state; drafts are never reachable."""
    return await service.get_symptom_report(user.id, patient_id, report_id)


@router.post(
    "/me/patients/{patient_id}/symptom-reports/{report_id}/review",
    response_model=ClinicianSymptomReport,
    summary="Mark a confirmed symptom report reviewed (idempotent)",
)
async def review_symptom_report(
    patient_id: UUID,
    report_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.review_symptom_report(user.id, patient_id, report_id)


@router.get(
    "/me/patients/{patient_id}/deep-dive",
    response_model=PatientDeepDive,
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


@router.get(
    "/me/patients/{patient_id}/a2a-timeline",
    response_model=A2ATimelineResponse,
    summary="Patient A2A lifecycle timeline",
    description=(
        "Returns A2A delegation task timeline for a patient, "
        "optionally filtered by chat session_id."
    ),
)
async def get_patient_a2a_timeline(
    patient_id: UUID,
    session_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    """GET /api/v1/clinicians/me/patients/{patient_id}/a2a-timeline"""
    return await service.get_patient_a2a_timeline(
        user.id,
        patient_id,
        session_id=session_id,
        limit=limit,
    )


@router.post(
    "/me/patients/{patient_id}/soap-note",
    response_model=SoapNoteGenerationResponse,
    summary="Generate AI SOAP note",
    description=(
        "Triggers the configured SOAP-note generation service for patient data. "
        "Stores the resulting draft in soap_notes. "
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
    from app.services.soap_note_service import SoapNoteService

    # Verify care team assignment before running the expensive generation
    service = ClinicianService(db)
    await service.get_patient_detail(user.id, patient_id)

    rate_limit_result = await soap_note_rate_limiter.check(f"soap-note:{user.id}")
    if not rate_limit_result.allowed:
        retry_after = rate_limit_result.retry_after_seconds
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "SOAP note generation is temporarily rate limited. "
                f"Retry after {retry_after} seconds."
            ),
            headers={"Retry-After": str(retry_after)},
        )

    result = await SoapNoteService(db).generate(
        patient_id=patient_id,
        clinician_id=user.id,
        lookback_days=request.lookback_days,
        care_team_id=request.care_team_id,
    )

    if result.status != "success":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result.error or "SOAP note generation is unavailable right now.",
        )

    return {
        "status": result.status,
        "soap_note_id": result.soap_note_id,
        "soap_note": result.soap_note,
    }


@router.post(
    "/me/patients/{patient_id}/obligations",
    response_model=CarePlanVersionRead,
    summary="Stage a clinician-authored care-plan item",
    description=(
        "Compatibility endpoint: stages a diet, exercise, or custom item in a clinician "
        "care-plan draft. It never creates an active patient obligation directly."
    ),
)
async def set_patient_obligation(
    patient_id: UUID,
    data: ObligationSetRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    """Stage the legacy obligation payload for review and whole-plan approval."""
    return await service.set_patient_obligation(user.id, patient_id, data.model_dump())


@router.post(
    "/me/patients/{patient_id}/documents/{document_id}/annotate",
    response_model=AnnotationSaveResponse,
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


@router.get(
    "/me/patients/{patient_id}/documents/{document_id}/facts",
    summary="List evidence-backed extracted facts for one document",
)
async def get_document_facts(
    patient_id: UUID,
    document_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: ClinicianService = Depends(_get_service),
) -> Any:
    return await service.get_document_facts(user.id, patient_id, document_id)
