"""Document routes."""

from uuid import UUID

from fastapi import APIRouter, UploadFile

from app.models import DocumentRead, DocumentUpload

router = APIRouter()


@router.post("/upload", response_model=DocumentRead)
async def upload_document(metadata: DocumentUpload, file: UploadFile) -> dict:
    raise NotImplementedError


@router.get("/", response_model=list[DocumentRead])
async def list_documents() -> list:
    raise NotImplementedError


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(document_id: UUID) -> dict:
    raise NotImplementedError


@router.post("/{document_id}/explain")
async def explain_document(document_id: UUID) -> dict:
    """Triggers AI explanation — returns plain-language summary."""
    raise NotImplementedError
