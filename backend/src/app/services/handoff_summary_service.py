"""Reviewed care-handoff summaries: build, edit, approve, export (CON-001).

A summary belongs to the author's care-team link. The database re-checks that link on every
call; a summary that is missing or belongs to another link answers as not found. The sections
are deterministic (``HandoffSummaryBuilder``); no model writes any part of them, and the
narrative is whatever the clinician types. Approval and export are audited in the database.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from postgrest.exceptions import APIError
from supabase import Client

from app.core import authorization_reasons as reasons
from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.models.handoff import (
    HandoffCreateRequest,
    HandoffDetail,
    HandoffExportResponse,
    HandoffHeader,
    HandoffSaveRequest,
    HandoffSection,
)
from app.services.acting_care_team import acting_care_team
from app.services.care_team_access import CareTeamAccessService
from app.services.handoff_fhir_export import build_handoff_bundle
from app.services.handoff_summary_builder import HandoffSummaryBuilder

VERSION_CONFLICT = "HANDOFF_VERSION_CONFLICT"
NOT_APPROVED = "HANDOFF_NOT_APPROVED"
DEFAULT_TITLES = {
    "colleague": "Handoff summary for a colleague",
    "care_team": "Handoff summary for another care team",
    "transition": "Transition-of-care summary",
}


class HandoffSummaryService:
    def __init__(self, db: Client, authorize: Callable[[UUID, UUID], Awaitable[None]]) -> None:
        self.db = db
        self.access = CareTeamAccessService(db)
        self.builder = HandoffSummaryBuilder(db, authorize)

    # ── helpers ─────────────────────────────────────────────────────────────────────────

    def _denied(self, clinician_id: UUID, patient_id: UUID | str) -> AuthorizationError:
        return AuthorizationError(
            "You are not assigned to this patient",
            reason_code=reasons.NO_CARE_TEAM_ASSIGNMENT,
            actor_id=str(clinician_id),
            actor_role="clinician",
            target_type="patient",
            target_id=str(patient_id),
        )

    async def _rpc(self, name: str, params: dict[str, Any]) -> Any:
        result = await asyncio.to_thread(self.db.rpc(name, params).execute)
        return result.data

    def _map(self, error: APIError, summary_id: UUID) -> Exception:
        code = str(error.code)
        text = f"{error.message or ''} {error.hint or ''}"
        if code == "42501":
            return NotFoundError("Handoff summary", str(summary_id))
        if code == "40001" or VERSION_CONFLICT in text:
            return ConflictError(
                "This summary changed since you opened it. Reload it and review the latest "
                "version.",
                code=VERSION_CONFLICT,
            )
        if NOT_APPROVED in text:
            return ValidationError(
                "Approve the current version before exporting it.", code=NOT_APPROVED
            )
        if code == "54000":
            return ValidationError("This patient has reached the handoff summary limit.")
        return error

    async def _call(self, name: str, params: dict[str, Any], summary_id: UUID) -> Any:
        try:
            return await self._rpc(name, params)
        except APIError as error:
            mapped = self._map(error, summary_id)
            if mapped is error:
                raise
            raise mapped from None

    async def _patient_access(self, clinician_id: UUID, patient_id: UUID):  # type: ignore[no-untyped-def]
        return await asyncio.to_thread(self.access.for_patient, clinician_id, patient_id)

    # ── use cases ───────────────────────────────────────────────────────────────────────

    async def create(
        self, clinician_id: UUID, patient_id: UUID, request: HandoffCreateRequest
    ) -> HandoffHeader:
        access = await self._patient_access(clinician_id, patient_id)
        team = acting_care_team(access, request.care_team_id)
        sections = await self.builder.build(clinician_id, patient_id, team, access)
        summary_id = request.client_request_id or uuid4()
        try:
            data = await self._rpc(
                "create_care_handoff_summary",
                {
                    "p_actor_id": str(clinician_id),
                    "p_patient_id": str(patient_id),
                    "p_care_team_id": team,
                    "p_summary_id": str(summary_id),
                    "p_title": request.title or DEFAULT_TITLES[request.purpose],
                    "p_purpose": request.purpose,
                    "p_recipient_label": request.recipient_label,
                    "p_sections": [s.model_dump(mode="json") for s in sections],
                    "p_built_at": datetime.now(UTC).isoformat(),
                },
            )
        except APIError as error:
            if str(error.code) == "42501":
                raise self._denied(clinician_id, patient_id) from None
            if str(error.code) == "54000":
                raise ValidationError(
                    "This patient has reached the handoff summary limit."
                ) from None
            raise
        return HandoffHeader.model_validate(data)

    async def list(self, clinician_id: UUID, patient_id: UUID) -> list[HandoffHeader]:
        await self._patient_access(clinician_id, patient_id)
        data = await self._rpc(
            "list_care_handoff_summaries",
            {"p_actor_id": str(clinician_id), "p_patient_id": str(patient_id)},
        )
        return [HandoffHeader.model_validate(row) for row in cast(list[Any], data or [])]

    async def get(
        self, clinician_id: UUID, patient_id: UUID, summary_id: UUID, version: int | None = None
    ) -> HandoffDetail:
        await self._patient_access(clinician_id, patient_id)
        data = await self._call(
            "read_care_handoff_summary",
            {
                "p_actor_id": str(clinician_id),
                "p_summary_id": str(summary_id),
                "p_version": version,
            },
            summary_id,
        )
        detail = HandoffDetail.model_validate(data)
        if detail.patient_id != patient_id:
            # The summary is real but belongs to another patient's record: same answer.
            raise NotFoundError("Handoff summary", str(summary_id))
        detail.patient_name = await asyncio.to_thread(self._patient_name, str(patient_id))
        return detail

    async def save(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        summary_id: UUID,
        request: HandoffSaveRequest,
    ) -> HandoffDetail:
        current = await self.get(clinician_id, patient_id, summary_id)
        sections: list[HandoffSection] | None = None
        built_at: str | None = None
        if request.refresh:
            access = await self._patient_access(clinician_id, patient_id)
            sections = await self.builder.build(
                clinician_id, patient_id, str(current.care_team_id), access
            )
            built_at = datetime.now(UTC).isoformat()
        await self._call(
            "save_care_handoff_version",
            {
                "p_actor_id": str(clinician_id),
                "p_summary_id": str(summary_id),
                "p_expected_version": request.expected_version,
                "p_narrative": request.narrative,
                "p_notes": request.notes,
                "p_title": request.title,
                "p_sections": [s.model_dump(mode="json") for s in sections]
                if sections is not None
                else None,
                "p_built_at": built_at,
            },
            summary_id,
        )
        return await self.get(clinician_id, patient_id, summary_id)

    async def approve(
        self, clinician_id: UUID, patient_id: UUID, summary_id: UUID, version: int
    ) -> HandoffDetail:
        current = await self.get(clinician_id, patient_id, summary_id)
        if any(s.status == "unavailable" for s in current.version.sections):
            raise ValidationError(
                "A section could not be read. Rebuild the summary before approving it.",
                code="HANDOFF_SECTION_UNAVAILABLE",
            )
        await self._call(
            "approve_care_handoff_summary",
            {
                "p_actor_id": str(clinician_id),
                "p_summary_id": str(summary_id),
                "p_version": version,
            },
            summary_id,
        )
        return await self.get(clinician_id, patient_id, summary_id)

    async def export(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        summary_id: UUID,
        version: int,
        export_format: str,
    ) -> HandoffExportResponse:
        await self.get(clinician_id, patient_id, summary_id)  # patient and team gate
        data = await self._call(
            "record_care_handoff_export",
            {
                "p_actor_id": str(clinician_id),
                "p_summary_id": str(summary_id),
                "p_version": version,
                "p_format": export_format,
            },
            summary_id,
        )
        detail = HandoffDetail.model_validate(data)
        detail.patient_name = await asyncio.to_thread(self._patient_name, str(patient_id))
        bundle = None
        if export_format == "fhir":
            patient = await asyncio.to_thread(self._patient_row, str(patient_id))
            bundle = build_handoff_bundle(detail, patient=patient)
        return HandoffExportResponse(format=cast(Any, export_format), summary=detail, bundle=bundle)

    def _patient_row(self, patient_id: str) -> dict[str, Any]:
        rows = (
            self.db.table("patients")
            .select("first_name,last_name,date_of_birth")
            .eq("id", patient_id)
            .limit(1)
            .execute()
            .data
        )
        if not isinstance(rows, list) or not rows:
            raise NotFoundError("Patient", patient_id)
        return cast(dict[str, Any], rows[0])

    def _patient_name(self, patient_id: str) -> str | None:
        try:
            row = self._patient_row(patient_id)
        except NotFoundError:
            return None
        return f"{row['first_name']} {row['last_name']}"
