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

from fastapi import APIRouter, BackgroundTasks, Depends, status
from pydantic import BaseModel, Field
from supabase import Client

from app.clients.supabase import get_admin_client
from app.core.security import get_current_user
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.document import DocumentRead
from app.models.enums import DocumentType
from app.services.document_service import DocumentService
from app.services.explanation_service import ExplanationService
from app.services.ingestion_service import IngestionService

router = APIRouter()
logger = logging.getLogger(__name__)


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


class ExplainRequest(BaseModel):
    """Language selection for AI explanation responses."""

    language: str = "en"


async def _run_ingestion_safe(
    document_id: str,
    patient_id: UUID,
    file_path: str,
    document_type: str,
) -> None:
    """Background task wrapper — catches all exceptions to prevent crash."""
    try:
        db = get_admin_client()
        service = IngestionService(db)
        await service.ingest_document(
            document_id=UUID(document_id),
            patient_id=patient_id,
            file_path=file_path,
            document_type=document_type,
        )
    except Exception:
        logger.exception("Ingestion background task failed for document %s", document_id)


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
    background_tasks: BackgroundTasks,
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
    )
    background_tasks.add_task(
        _run_ingestion_safe,
        document_id=str(document["id"]),
        patient_id=user.id,
        file_path=body.file_path,
        document_type=body.document_type.value,
    )
    return document


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
    language = body.language if body else "en"
    document = await service.get_document(document_id, user.id)

    if language == "en" and document.get("ai_summary"):
        return {"summary": document["ai_summary"], "language": "en", "cached": True}

    explanation_service = ExplanationService()
    summary = await explanation_service.explain(document_data=document, language=language)

    if language == "en":
        await service.update_summary(document_id, user.id, summary)

    return {"summary": summary, "language": language, "cached": False}
