"""Appointment persistence and authorization service."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from supabase import Client

from app.core.exceptions import AuthorizationError, ExternalServiceError, NotFoundError
from app.models.enums import AppointmentStatus


class AppointmentService:
    """Patient/clinician appointment operations."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def list_for_user(self, *, user_id: UUID, role: str) -> list[dict[str, Any]]:
        if role == "patient":
            result = await self._execute(
                self.db.table("appointments")
                .select("*")
                .eq("patient_id", str(user_id))
                .order("scheduled_at")
            )
            return [row for row in (result.data or []) if isinstance(row, dict)]

        if role == "clinician":
            assignments = await self._assigned_patient_ids(user_id)
            if not assignments:
                return []
            result = await self._execute(
                self.db.table("appointments")
                .select("*")
                .in_("patient_id", assignments)
                .order("scheduled_at")
            )
            return [row for row in (result.data or []) if isinstance(row, dict)]

        raise AuthorizationError("Unsupported role for appointments")

    async def create_for_user(
        self,
        *,
        user_id: UUID,
        role: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        care_team = await self._get_care_team(str(data.get("care_team_id")))
        patient_id = str(care_team.get("patient_id") or "")
        clinician_id = str(care_team.get("clinician_id") or "")

        if role == "patient" and patient_id != str(user_id):
            raise AuthorizationError(
                "Patients can only create appointments for their own care team"
            )
        if role == "clinician" and clinician_id != str(user_id):
            raise AuthorizationError(
                "Clinicians can only create appointments for assigned patients"
            )
        if role not in {"patient", "clinician"}:
            raise AuthorizationError("Unsupported role for appointments")

        clinician_name = await self._get_clinician_name(clinician_id)
        payload = {
            "patient_id": patient_id,
            "care_team_id": str(data.get("care_team_id")),
            "clinician_name": clinician_name,
            "scheduled_at": data.get("scheduled_at"),
            "duration_minutes": data.get("duration_minutes", 30),
            "appointment_type": data.get("appointment_type"),
            "location": data.get("location"),
            "reason": data.get("reason"),
            "notes": data.get("notes"),
            "status": AppointmentStatus.SCHEDULED.value,
        }
        result = await self._execute(self.db.table("appointments").insert(payload))
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        if not rows:
            raise ExternalServiceError("Supabase", "Failed to create appointment")
        return rows[0]

    async def update_for_user(
        self,
        *,
        user_id: UUID,
        role: str,
        appointment_id: UUID,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        existing = await self._get_appointment(str(appointment_id))
        await self._ensure_can_access(user_id=user_id, role=role, appointment=existing)
        payload = {key: value for key, value in data.items() if value is not None}
        if not payload:
            return existing
        result = await self._execute(
            self.db.table("appointments").update(payload).eq("id", str(appointment_id))
        )
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        if not rows:
            raise ExternalServiceError("Supabase", "Failed to update appointment")
        return rows[0]

    async def _ensure_can_access(
        self,
        *,
        user_id: UUID,
        role: str,
        appointment: dict[str, Any],
    ) -> None:
        if role == "patient" and str(appointment.get("patient_id")) == str(user_id):
            return
        if role == "clinician":
            assignment = await self._execute(
                self.db.table("care_teams")
                .select("id")
                .eq("clinician_id", str(user_id))
                .eq("patient_id", str(appointment.get("patient_id")))
                .eq("status", "active")
                .limit(1)
            )
            if assignment.data:
                return
        raise AuthorizationError("You are not authorized to manage this appointment")

    async def _assigned_patient_ids(self, clinician_id: UUID) -> list[str]:
        result = await self._execute(
            self.db.table("care_teams")
            .select("patient_id")
            .eq("clinician_id", str(clinician_id))
            .eq("status", "active")
        )
        return [
            str(row.get("patient_id"))
            for row in (result.data or [])
            if isinstance(row, dict) and row.get("patient_id")
        ]

    async def _get_care_team(self, care_team_id: str) -> dict[str, Any]:
        result = await self._execute(
            self.db.table("care_teams")
            .select("id, patient_id, clinician_id, status")
            .eq("id", care_team_id)
            .eq("status", "active")
            .limit(1)
        )
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        if not rows:
            raise NotFoundError("Care team", care_team_id)
        return rows[0]

    async def _get_appointment(self, appointment_id: str) -> dict[str, Any]:
        result = await self._execute(
            self.db.table("appointments").select("*").eq("id", appointment_id).limit(1)
        )
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        if not rows:
            raise NotFoundError("Appointment", appointment_id)
        return rows[0]

    async def _get_clinician_name(self, clinician_id: str) -> str | None:
        result = await self._execute(
            self.db.table("clinicians")
            .select("first_name, last_name")
            .eq("id", clinician_id)
            .limit(1)
        )
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        if not rows:
            return None
        first_name = str(rows[0].get("first_name") or "").strip()
        last_name = str(rows[0].get("last_name") or "").strip()
        return " ".join(part for part in [first_name, last_name] if part) or None

    @staticmethod
    async def _execute(query: Any) -> Any:
        return await asyncio.to_thread(query.execute)
