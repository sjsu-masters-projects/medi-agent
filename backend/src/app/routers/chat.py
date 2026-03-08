"""Chat routes."""

from uuid import UUID

from fastapi import APIRouter

from app.models import ChatMessage

router = APIRouter()


@router.get("/history/{patient_id}", response_model=list[ChatMessage])
async def get_chat_history(patient_id: UUID, limit: int = 50) -> list:
    raise NotImplementedError


# WebSocket at /ws/chat/{patient_id} — mounted in main.py during Phase 5.
