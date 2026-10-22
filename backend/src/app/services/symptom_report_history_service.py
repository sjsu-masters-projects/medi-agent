"""Confirmed-symptom history for the patient and structured report detail for clinicians.

The database function checks the actor itself (own reports for a patient, an active care-team
link for a clinician); this service adds the existing assignment check first so a clinician's
denial is audited like every other care-team denial. Only patient-confirmed reports are
reachable. Unconfirmed drafts are not in `symptom_reports` and have no route here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, cast
from uuid import UUID

import httpx
from postgrest.exceptions import APIError
from supabase import Client

from app.core.exceptions import NotFoundError, ServiceUnavailableError, ValidationError
from app.models.symptom_report_history import (
    ClinicianSymptomReport,
    SymptomReportDetail,
    SymptomReportList,
)
from app.services.symptom_report_presenter import (
    present_clinician,
    present_detail,
    present_list_item,
)

_TIMEOUT_SECONDS = 8


class SymptomReportHistoryService:
    def __init__(
        self,
        db: Client,
        authorize: Callable[[UUID, UUID], Awaitable[None]] | None = None,
    ) -> None:
        self.db = db
        self.authorize = authorize

    async def _call(self, actor: UUID, role: str, action: str, payload: dict[str, Any]) -> Any:
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.db.rpc(
                        "symptom_report_history",
                        {
                            "p_actor_id": str(actor),
                            "p_actor_role": role,
                            "p_action": action,
                            "p_payload": payload,
                        },
                    ).execute
                ),
                timeout=_TIMEOUT_SECONDS,
            )
        except APIError as exc:
            if exc.code == "42501":
                # Not yours and not there are the same answer.
                raise NotFoundError("Symptom report", str(payload.get("report_id", ""))) from None
            if exc.message == "CARE_TEAM_REQUIRED":
                raise ValidationError(
                    "Choose which of your care teams this is for.", code="CARE_TEAM_REQUIRED"
                ) from None
            raise self._unavailable() from None
        except (TimeoutError, OSError, httpx.TransportError):
            raise self._unavailable() from None
        if not isinstance(result.data, dict):
            raise self._unavailable()
        return cast(dict[str, Any], result.data)

    @staticmethod
    def _unavailable() -> ServiceUnavailableError:
        return ServiceUnavailableError(
            "Symptom reports are temporarily unavailable", code="SYMPTOM_REPORTS_UNAVAILABLE"
        )

    async def _timezone(self, patient_id: UUID) -> str:
        try:
            row = await asyncio.to_thread(
                self.db.table("patients").select("timezone").eq("id", str(patient_id)).execute
            )
            data = cast(Any, row.data)
            zone = data[0].get("timezone") if isinstance(data, list) and data else None
        except (APIError, OSError, httpx.TransportError):
            return "UTC"
        return zone if isinstance(zone, str) and zone else "UTC"

    async def list_for_patient(self, patient_id: UUID, limit: int = 50) -> SymptomReportList:
        data = await self._call(patient_id, "patient", "list", {"limit": limit})
        items = data.get("items")
        if not isinstance(items, list):
            raise self._unavailable()
        return SymptomReportList(
            items=[present_list_item(card) for card in items],
            has_more=bool(data.get("has_more")),
            timezone=await self._timezone(patient_id),
        )

    async def detail_for_patient(self, patient_id: UUID, report_id: UUID) -> SymptomReportDetail:
        card = await self._call(patient_id, "patient", "detail", {"report_id": str(report_id)})
        return present_detail(card)

    async def detail_for_clinician(
        self, clinician_id: UUID, patient_id: UUID, report_id: UUID
    ) -> ClinicianSymptomReport:
        return await self._staff(clinician_id, patient_id, report_id, "detail")

    async def mark_reviewed(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        report_id: UUID,
        care_team_id: UUID | None = None,
    ) -> ClinicianSymptomReport:
        return await self._staff(clinician_id, patient_id, report_id, "review", care_team_id)

    async def _staff(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        report_id: UUID,
        action: str,
        care_team_id: UUID | None = None,
    ) -> ClinicianSymptomReport:
        if self.authorize is None:
            raise self._unavailable()
        await self.authorize(clinician_id, patient_id)
        card = await self._call(
            clinician_id,
            "clinician",
            action,
            {
                "report_id": str(report_id),
                "patient_id": str(patient_id),
                **({"care_team_id": str(care_team_id)} if care_team_id else {}),
            },
        )
        return present_clinician(card)
