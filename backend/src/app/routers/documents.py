"""Document routes — upload metadata, list, get, explain.

Upload flow:
    1. Frontend uploads file directly to Supabase Storage
    2. Frontend calls POST /documents with file metadata
    3. Backend validates and stores the metadata row
    4. Backend returns DocumentRead with a signed download URL
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from supabase import Client

from app.core.security import get_current_user, require_role
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.document import DocumentRead
from app.models.enums import DocumentType, Language, coerce_locale
from app.services.document_service import DocumentService
from app.services.explanation_service import ExplanationService, normalize_patient_summary
from app.services.smart_launch_service import SmartLaunchService

router = APIRouter()
_clinician_dep = require_role("clinician")


def _get_service(db: Client = Depends(get_db)) -> DocumentService:
    return DocumentService(db)


# ── Request schema (specific to this endpoint) ─────────


class DocumentCreateRequest(BaseModel):
    """Metadata sent after the frontend uploads the file to Storage."""

    file_name: str = Field(..., min_length=1, max_length=255)
    file_path: str = Field(
        ...,
        description="Supabase Storage path, e.g. '{user_id}/2025-01-15_lab-results.pdf'",
    )
    file_size_bytes: int = Field(..., gt=0)
    mime_type: str = Field(..., examples=["application/pdf", "image/jpeg"])
    document_type: DocumentType
    source_clinic: str | None = None
    notes: str | None = None
    content_hash: str | None = Field(default=None, pattern=r"^[A-Fa-f0-9]{64}$")
    start_ingestion: bool = True


class ExplainRequest(BaseModel):
    """Language selection for AI explanation responses."""

    language: Language = Language.EN


# ── Endpoints ───────────────────────────────────────────


@router.post(
    "/",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register an uploaded document",
    description="Call this AFTER uploading the file to Supabase Storage.",
)
async def create_document(
    body: DocumentCreateRequest,
    user: CurrentUser = Depends(get_current_user),
    service: DocumentService = Depends(_get_service),
) -> Any:
    document = await service.create_document(
        patient_id=user.id,
        uploaded_by=user.id,
        uploaded_by_role=user.role,
        file_name=body.file_name,
        file_path=body.file_path,
        file_size_bytes=body.file_size_bytes,
        mime_type=body.mime_type,
        document_type=body.document_type.value,
        source_clinic=body.source_clinic,
        notes=body.notes,
        content_hash=body.content_hash,
        queue_ingestion=body.start_ingestion,
    )
    return document


@router.post(
    "/patients/{patient_id}",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a clinician-uploaded document for an assigned patient",
)
async def create_clinician_document(
    patient_id: UUID,
    body: DocumentCreateRequest,
    user: CurrentUser = Depends(_clinician_dep),
    service: DocumentService = Depends(_get_service),
    db: Client = Depends(get_db),
) -> Any:
    """Require an active care-team assignment before attaching a document to a chart."""
    SmartLaunchService(db).ensure_assignment(clinician_id=user.id, patient_id=patient_id)
    document = await service.create_document(
        patient_id=patient_id,
        uploaded_by=user.id,
        uploaded_by_role=user.role,
        file_name=body.file_name,
        file_path=body.file_path,
        file_size_bytes=body.file_size_bytes,
        mime_type=body.mime_type,
        document_type=body.document_type.value,
        source_clinic=body.source_clinic,
        notes=body.notes,
        content_hash=body.content_hash,
        queue_ingestion=body.start_ingestion,
    )
    return document


@router.post(
    "/patients/{patient_id}/{document_id}/ingestion/retry",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry a failed clinician document ingestion",
)
async def retry_clinician_document_ingestion(
    patient_id: UUID,
    document_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: DocumentService = Depends(_get_service),
    db: Client = Depends(get_db),
) -> Any:
    """Atomically requeue a failed document for the durable worker."""
    SmartLaunchService(db).ensure_assignment(clinician_id=user.id, patient_id=patient_id)
    db.rpc(
        "enqueue_document_ingestion_retry",
        {
            "p_document_id": str(document_id),
            "p_patient_id": str(patient_id),
            "p_actor_id": str(user.id),
        },
    ).execute()
    return await service.get_document(document_id, patient_id)


@router.get(
    "/patients/{patient_id}/{document_id}/source",
    response_model=DocumentRead,
    summary="Get an assigned patient's source document with fresh signed URLs",
)
async def get_clinician_document_source(
    patient_id: UUID,
    document_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: DocumentService = Depends(_get_service),
    db: Client = Depends(get_db),
) -> Any:
    """Allow a clinician to open only an assigned patient's private source document."""
    SmartLaunchService(db).ensure_assignment(clinician_id=user.id, patient_id=patient_id)
    return await service.get_document(document_id, patient_id)


@router.get(
    "/",
    response_model=list[DocumentRead],
    summary="List my documents",
)
async def list_documents(
    user: CurrentUser = Depends(get_current_user),
    service: DocumentService = Depends(_get_service),
) -> Any:
    return await service.list_documents(user.id)


@router.get(
    "/{document_id}",
    response_model=DocumentRead,
    summary="Get document detail with signed URL",
)
async def get_document(
    document_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    service: DocumentService = Depends(_get_service),
) -> Any:
    return await service.get_document(document_id, user.id)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
)
async def delete_document(
    document_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    service: DocumentService = Depends(_get_service),
) -> None:
    await service.delete_document(document_id, user.id)


@router.post(
    "/{document_id}/explain",
    summary="Get AI explanation of a document",
    status_code=status.HTTP_200_OK,
)
async def explain_document(
    document_id: UUID,
    body: ExplainRequest | None = None,
    user: CurrentUser = Depends(get_current_user),
    service: DocumentService = Depends(_get_service),
) -> Any:
    language = body.language if body else Language.EN
    document = await service.get_document(document_id, user.id)

    if language == Language.EN and document.get("ai_summary"):
        # Summaries created before the plain-text prompt contract may contain Markdown.
        # Keep the cache fast, but make its patient-facing representation match newly
        # generated summaries rather than exposing model formatting in the portal.
        summary = normalize_patient_summary(str(document["ai_summary"]))
        return {"summary": summary, "language": language.value, "cached": True}

    explanation_service = ExplanationService()
    summary = await explanation_service.explain(document_data=document, language=language.value)

    if coerce_locale(language) == Language.EN:
        await service.update_summary(document_id, user.id, summary)

    return {"summary": summary, "language": coerce_locale(language).value, "cached": False}
