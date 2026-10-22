"""Share an approved care-handoff version with a named colleague (CON-001, migration 096).

The database owns every decision: who may receive (an active link to the patient, or an
active member of the author's clinic), which version (the approved current one), revocation,
audit and the notification. This service maps its answers and never adds access. A caller who
is not the author, not the recipient, or whose share is revoked gets the same not-found.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from app.core.exceptions import NotFoundError, ValidationError
from app.models.handoff import (
    HandoffDetail,
    HandoffRecipient,
    HandoffShare,
    HandoffVersionBody,
    SharedHandoffDetail,
    SharedHandoffExportResponse,
    SharedHandoffItem,
)
from app.services.handoff_fhir_export import build_handoff_bundle

logger = logging.getLogger(__name__)
NOT_APPROVED = "HANDOFF_NOT_APPROVED"
RECIPIENT_NOT_ALLOWED = "HANDOFF_RECIPIENT_NOT_ALLOWED"
# The FHIR builder reads the care team nowhere; a recipient never learns it.
_NO_TEAM = UUID(int=0)


class HandoffShareService:
    def __init__(self, db: Client) -> None:
        self.db = db

    async def _call(self, name: str, params: dict[str, Any], subject: UUID) -> Any:
        try:
            result = await asyncio.to_thread(self.db.rpc(name, params).execute)
        except APIError as error:
            code = str(error.code)
            text = f"{error.message or ''} {error.hint or ''}"
            # Reason codes and ids only; never names or clinical text.
            logger.info("handoff_share_refused", extra={"rpc": name, "code": code})
            if code == "42501":
                raise NotFoundError("Handoff summary", str(subject)) from None
            if NOT_APPROVED in text:
                raise ValidationError(
                    "Only the approved version of a summary can be shared. "
                    "Approve the current version first.",
                    code=NOT_APPROVED,
                ) from None
            if RECIPIENT_NOT_ALLOWED in text:
                raise ValidationError(
                    "That clinician cannot receive this summary.", code=RECIPIENT_NOT_ALLOWED
                ) from None
            if code == "54000":
                raise ValidationError("This summary has reached its sharing limit.") from None
            if code == "22023":
                raise ValidationError("That request is not valid.") from None
            raise
        return result.data

    # ── author ──────────────────────────────────────────────────────────────────────────

    async def candidates(
        self, clinician_id: UUID, summary_id: UUID, query: str | None
    ) -> list[HandoffRecipient]:
        data = await self._call(
            "list_care_handoff_share_candidates",
            {"p_actor_id": str(clinician_id), "p_summary_id": str(summary_id), "p_query": query},
            summary_id,
        )
        return [HandoffRecipient.model_validate(row) for row in cast(list[Any], data or [])]

    async def shares(self, clinician_id: UUID, summary_id: UUID) -> list[HandoffShare]:
        data = await self._call(
            "list_care_handoff_shares",
            {"p_actor_id": str(clinician_id), "p_summary_id": str(summary_id)},
            summary_id,
        )
        return [HandoffShare.model_validate(row) for row in cast(list[Any], data or [])]

    async def share(
        self, clinician_id: UUID, summary_id: UUID, version: int, recipient_id: UUID
    ) -> HandoffShare:
        data = await self._call(
            "share_care_handoff_summary",
            {
                "p_actor_id": str(clinician_id),
                "p_summary_id": str(summary_id),
                "p_version": version,
                "p_recipient_id": str(recipient_id),
            },
            summary_id,
        )
        return HandoffShare.model_validate(data)

    async def revoke(self, clinician_id: UUID, share_id: UUID) -> HandoffShare:
        data = await self._call(
            "revoke_care_handoff_share",
            {"p_actor_id": str(clinician_id), "p_share_id": str(share_id)},
            share_id,
        )
        return HandoffShare.model_validate(data)

    # ── recipient ───────────────────────────────────────────────────────────────────────

    async def shared_with_me(self, clinician_id: UUID) -> list[SharedHandoffItem]:
        data = await self._call(
            "list_care_handoff_shared_with_me", {"p_actor_id": str(clinician_id)}, clinician_id
        )
        return [SharedHandoffItem.model_validate(row) for row in cast(list[Any], data or [])]

    async def read(self, clinician_id: UUID, share_id: UUID) -> SharedHandoffDetail:
        data = await self._call(
            "read_shared_care_handoff",
            {"p_actor_id": str(clinician_id), "p_share_id": str(share_id)},
            share_id,
        )
        return SharedHandoffDetail.model_validate(data)

    async def export(
        self, clinician_id: UUID, share_id: UUID, export_format: str
    ) -> SharedHandoffExportResponse:
        data = await self._call(
            "record_shared_care_handoff_export",
            {
                "p_actor_id": str(clinician_id),
                "p_share_id": str(share_id),
                "p_format": export_format,
            },
            share_id,
        )
        detail = SharedHandoffDetail.model_validate(data)
        bundle = None
        if export_format == "fhir":
            bundle = build_handoff_bundle(
                self._as_detail(detail), patient=await asyncio.to_thread(self._patient, detail)
            )
        return SharedHandoffExportResponse(
            format=cast(Any, export_format), summary=detail, bundle=bundle
        )

    def _patient(self, detail: SharedHandoffDetail) -> dict[str, Any]:
        rows = (
            self.db.table("patients")
            .select("first_name,last_name,date_of_birth")
            .eq("id", str(detail.patient_id))
            .limit(1)
            .execute()
            .data
        )
        if not isinstance(rows, list) or not rows:
            raise NotFoundError("Handoff summary", str(detail.share_id))
        return cast(dict[str, Any], rows[0])

    @staticmethod
    def _as_detail(detail: SharedHandoffDetail) -> HandoffDetail:
        return HandoffDetail(
            id=detail.summary_id,
            patient_id=detail.patient_id,
            care_team_id=_NO_TEAM,
            author_id=detail.author_id,
            title=detail.title,
            purpose=detail.purpose,
            status="approved",
            current_version=detail.version,
            approved_version=detail.version,
            approved_by=detail.approved_by,
            approved_at=detail.approved_at,
            created_at=detail.shared_at,
            updated_at=detail.shared_at,
            version=HandoffVersionBody(
                version=detail.version,
                sections=detail.sections,
                narrative=detail.narrative,
                notes=detail.notes,
                built_at=detail.built_at,
                created_by=detail.author_id,
                created_at=detail.built_at,
            ),
            versions=[],
            events=[],
        )
