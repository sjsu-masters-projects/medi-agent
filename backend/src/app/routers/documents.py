"""Document routes — upload metadata, list, get, explain.

Upload flow:
    1. Frontend uploads file directly to Supabase Storage
    2. Frontend calls POST /documents with file metadata
    3. Backend validates and stores the metadata row
    4. Backend returns DocumentRead with a signed download URL
"""

from __future__ import annotations

import logging
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
from app.services.explanation_service import (
    ExplanationService,
    normalize_patient_summary,
    summary_unavailable_message,
)
from app.services.smart_launch_service import SmartLaunchService

logger = logging.getLogger(__name__)
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


@router.post(
    "/patients/{patient_id}/{document_id}/summary/retry",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry an unavailable patient explanation",
)
async def retry_clinician_document_summary(
    patient_id: UUID,
    document_id: UUID,
    user: CurrentUser = Depends(_clinician_dep),
    service: DocumentService = Depends(_get_service),
    db: Client = Depends(get_db),
) -> Any:
    """Requeue only the optional explanation, leaving the clinical result untouched.

    This re-reads candidates that already exist: it never re-runs OCR, never proposes a
    clinical fact again, and cannot change the document's parse state or stored source.
    """
    SmartLaunchService(db).ensure_assignment(clinician_id=user.id, patient_id=patient_id)
    db.rpc(
        "enqueue_document_summary_retry",
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
    locale = coerce_locale(body.language if body else Language.EN).value
    document = await service.get_document(document_id, user.id)
    cached = str(document.get("ai_summary") or "").strip()

    if not cached:
        # The request path deliberately does not generate an explanation. Generation is
        # the worker's job, so a provider outage is retried there instead of on every
        # page view, and the patient is told why nothing is shown rather than seeing an
        # empty card or generic prose that could read as a clinical statement.
        reported = _reported_summary_status(document)
        return {
            "summary": None,
            "available": False,
            "summary_status": reported,
            "failure_code": document.get("summary_failure_code"),
            "message": summary_unavailable_message(reported, locale),
            "language": locale,
            "cached": False,
        }

    # Summaries created before the plain-text prompt contract may contain Markdown.
    # Keep the cache fast, but make its patient-facing representation match newly
    # generated summaries rather than exposing model formatting in the portal.
    english = normalize_patient_summary(cached)
    if locale == Language.EN.value:
        return {
            "summary": english,
            "available": True,
            "summary_status": "ready",
            "failure_code": None,
            "message": None,
            "language": locale,
            "cached": True,
        }

    try:
        translated = await ExplanationService().translate(english, locale)
    except Exception:  # noqa: BLE001 - a translation outage is reported, never invented around
        logger.warning("Summary translation failed for document %s", document_id)
        return {
            "summary": None,
            "available": False,
            "summary_status": "failed",
            "failure_code": "provider_unavailable",
            "message": summary_unavailable_message("failed", locale),
            "language": locale,
            "cached": False,
        }

    return {
        "summary": translated,
        "available": True,
        "summary_status": "ready",
        "failure_code": None,
        "message": None,
        "language": locale,
        "cached": False,
    }


def _reported_summary_status(document: dict[str, Any]) -> str:
    """Describe a missing explanation from whichever lifecycle state is available.

    The summary lifecycle columns arrive with migration 038, which is applied after this
    image deploys. Until then the document's clinical parse state is the honest source:
    a completed extraction still owes an explanation, and anything else never had one.
    """
    recorded = str(document.get("summary_status") or "").strip()
    if recorded in {"pending", "processing"}:
        return "pending"
    if recorded in {"not_required", "failed"}:
        return recorded
    return "pending" if document.get("parse_status") == "completed" else "not_required"
