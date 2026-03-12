"""Document routes — upload metadata, list, get, explain.

Upload flow:
    1. Frontend uploads file directly to Supabase Storage
    2. Frontend calls POST /documents with file metadata
    3. Backend validates and stores the metadata row
    4. Backend returns DocumentRead with a signed download URL
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from supabase import Client

from app.core.security import get_current_user
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.document import DocumentRead
from app.models.enums import DocumentType
from app.services.document_service import DocumentService

router = APIRouter()


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
) -> dict:
    return await service.create_document(
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


@router.get(
    "/",
    response_model=list[DocumentRead],
    summary="List my documents",
)
async def list_documents(
    user: CurrentUser = Depends(get_current_user),
    service: DocumentService = Depends(_get_service),
) -> list:
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
) -> dict:
    return await service.get_document(document_id, user.id)


@router.post(
    "/{document_id}/explain",
    summary="Trigger AI explanation (Phase 4)",
    description="Returns plain-language summary. Will be wired to the Ingestion Agent.",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def explain_document(
    document_id: UUID,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    # Placeholder — will be implemented when AI agents are built (Phase 4)
    return {
        "document_id": str(document_id),
        "message": "AI explanation not yet available — coming in Phase 4",
    }
