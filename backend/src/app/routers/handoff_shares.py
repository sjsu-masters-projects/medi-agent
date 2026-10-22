"""Sharing an approved handoff summary version with a colleague (CON-001).

Author routes are keyed by the summary; recipient routes by the share. The database decides
access; a refusal of any kind is the same 404.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from supabase import Client

from app.core.security import require_role
from app.db.connection import get_db
from app.models.auth import CurrentUser
from app.models.handoff import (
    HandoffRecipient,
    HandoffShare,
    HandoffShareRequest,
    SharedHandoffDetail,
    SharedHandoffExportRequest,
    SharedHandoffExportResponse,
    SharedHandoffItem,
)
from app.services.handoff_share_service import HandoffShareService

router = APIRouter()
_clinician_dep = require_role("clinician")


def _service(db: Client = Depends(get_db)) -> HandoffShareService:
    return HandoffShareService(db)


_AUTHOR = "/clinician/handoff-summaries/{summary_id}"
_SHARED = "/clinician/shared-handoffs"


@router.get(_AUTHOR + "/share-candidates", response_model=list[HandoffRecipient])
async def list_share_candidates(
    summary_id: UUID,
    response: Response,
    q: str | None = Query(default=None, max_length=100),
    user: CurrentUser = Depends(_clinician_dep),
    service: HandoffShareService = Depends(_service),
) -> list[HandoffRecipient]:
    response.headers["Cache-Control"] = "no-store"
    return await service.candidates(user.id, summary_id, q)


@router.get(_AUTHOR + "/shares", response_model=list[HandoffShare])
async def list_shares(
    summary_id: UUID,
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: HandoffShareService = Depends(_service),
) -> list[HandoffShare]:
    response.headers["Cache-Control"] = "no-store"
    return await service.shares(user.id, summary_id)


@router.post(_AUTHOR + "/shares", response_model=HandoffShare, status_code=status.HTTP_201_CREATED)
async def share_summary(
    summary_id: UUID,
    body: HandoffShareRequest,
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: HandoffShareService = Depends(_service),
) -> HandoffShare:
    response.headers["Cache-Control"] = "no-store"
    share = await service.share(user.id, summary_id, body.version, body.recipient_id)
    if share.replayed:
        response.status_code = status.HTTP_200_OK
    return share


@router.delete("/clinician/handoff-shares/{share_id}", response_model=HandoffShare)
async def revoke_share(
    share_id: UUID,
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: HandoffShareService = Depends(_service),
) -> HandoffShare:
    response.headers["Cache-Control"] = "no-store"
    return await service.revoke(user.id, share_id)


@router.get(_SHARED, response_model=list[SharedHandoffItem])
async def shared_with_me(
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: HandoffShareService = Depends(_service),
) -> list[SharedHandoffItem]:
    response.headers["Cache-Control"] = "no-store"
    return await service.shared_with_me(user.id)


@router.get(_SHARED + "/{share_id}", response_model=SharedHandoffDetail)
async def read_shared(
    share_id: UUID,
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: HandoffShareService = Depends(_service),
) -> SharedHandoffDetail:
    response.headers["Cache-Control"] = "no-store"
    return await service.read(user.id, share_id)


@router.post(_SHARED + "/{share_id}/export", response_model=SharedHandoffExportResponse)
async def export_shared(
    share_id: UUID,
    body: SharedHandoffExportRequest,
    response: Response,
    user: CurrentUser = Depends(_clinician_dep),
    service: HandoffShareService = Depends(_service),
) -> SharedHandoffExportResponse:
    response.headers["Cache-Control"] = "no-store"
    return await service.export(user.id, share_id, body.format)
