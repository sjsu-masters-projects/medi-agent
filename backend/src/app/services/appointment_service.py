"""Appointment persistence and authorization service."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from app.core import authorization_reasons as reasons
from app.core.exceptions import (
    AuthorizationError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from app.models.appointment import AppointmentCalendarExport, AppointmentRead
from app.models.enums import AppointmentResponseAction, AppointmentStatus
from app.services.appointment_calendar import CalendarLocale, render_appointment_calendar

# Patient responses to an appointment: the statuses each action may be applied
# from, and the status it moves the appointment to. Actions only apply while the
# appointment is in one of the allowed source states.
_RESPONSE_TRANSITIONS: dict[AppointmentResponseAction, tuple[frozenset[str], AppointmentStatus]] = {
    AppointmentResponseAction.ACCEPT: (
        frozenset({AppointmentStatus.PROPOSED.value}),
        AppointmentStatus.CONFIRMED,
    ),
    AppointmentResponseAction.DECLINE: (
        frozenset({AppointmentStatus.PROPOSED.value}),
        AppointmentStatus.DECLINED,
    ),
    AppointmentResponseAction.REQUEST_ALTERNATIVE: (
        frozenset({AppointmentStatus.PROPOSED.value}),
        AppointmentStatus.ALTERNATIVE_REQUESTED,
    ),
    AppointmentResponseAction.CANCEL: (
        frozenset(
            {
                AppointmentStatus.PROPOSED.value,
                AppointmentStatus.CONFIRMED.value,
                AppointmentStatus.SCHEDULED.value,
            }
        ),
        AppointmentStatus.CANCELLED,
    ),
}

_BOOKING_ERRORS = {
    "conflict": ("APPOINTMENT_CONFLICT", "This time overlaps another booked visit"),
    "expired": ("APPOINTMENT_EXPIRED", "This appointment offer has expired"),
    "stale": ("APPOINTMENT_UNAVAILABLE", "This appointment is no longer available"),
    "past": ("APPOINTMENT_PAST", "Choose a future appointment time"),
}


def _booking_error(reason: str) -> ValidationError:
    code, message = _BOOKING_ERRORS[reason]
    return ValidationError(message, code=code)


class AppointmentService:
    """Patient/clinician appointment operations."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def export_calendar_for_user(
        self, *, user_id: UUID, role: str, appointment_id: UUID, locale: CalendarLocale
    ) -> AppointmentCalendarExport:
        appointment = await self._get_appointment(str(appointment_id))
        await self._ensure_can_access(user_id=user_id, role=role, appointment=appointment)
        if appointment.get("status") not in {"confirmed", "scheduled"}:
            raise _booking_error("stale")
        return render_appointment_calendar(AppointmentRead.model_validate(appointment), locale)

    async def list_for_user(self, *, user_id: UUID, role: str) -> list[dict[str, Any]]:
        if role not in {"patient", "clinician"}:
            raise AuthorizationError(
                "Unsupported role for appointments", reason_code=reasons.UNSUPPORTED_ROLE
            )
        await self._appointment_rpc(
            "expire_appointment_proposals", {"p_actor_id": str(user_id), "p_actor_role": role}
        )
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

        raise AuthorizationError(
            "Unsupported role for appointments",
            reason_code=reasons.UNSUPPORTED_ROLE,
        )

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
                "Patients can only create appointments for their own care team",
                reason_code=reasons.PATIENT_SCOPE_SELF_ONLY,
            )
        if role == "clinician" and clinician_id != str(user_id):
            raise AuthorizationError(
                "Clinicians can only create appointments for assigned patients",
                reason_code=reasons.NO_CARE_TEAM_ASSIGNMENT,
            )
        if role not in {"patient", "clinician"}:
            raise AuthorizationError(
                "Unsupported role for appointments",
                reason_code=reasons.UNSUPPORTED_ROLE,
            )

        clinician_name = await self._get_clinician_name(clinician_id)
        # A clinician offers a slot the patient must accept; a patient booking
        # their own appointment has nothing to confirm.
        initial_status = (
            AppointmentStatus.PROPOSED if role == "clinician" else AppointmentStatus.SCHEDULED
        )
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
            "status": initial_status.value,
        }
        result = await self._execute(self.db.table("appointments").insert(payload))
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        if not rows:
            raise ExternalServiceError("Supabase", "Failed to create appointment")
        return rows[0]

    async def propose_for_user(
        self, *, user_id: UUID, role: str, data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if role != "clinician":
            raise AuthorizationError(
                "Only clinicians can offer appointment times",
                reason_code=reasons.ROLE_LACKS_CLINICAL_SCOPE,
            )
        care_team = await self._get_care_team(str(data["care_team_id"]))
        if str(care_team.get("clinician_id")) != str(user_id):
            raise AuthorizationError(
                "Clinicians can only propose for assigned patients",
                reason_code=reasons.NO_CARE_TEAM_ASSIGNMENT,
            )
        slots = [datetime.fromisoformat(value) for value in data["slots"]]
        if any(slot <= datetime.now(UTC) for slot in slots):
            raise _booking_error("past")
        result = await self._appointment_rpc(
            "propose_appointment_slots",
            {
                "p_actor_id": str(user_id),
                "p_care_team_id": str(data["care_team_id"]),
                "p_slots": data["slots"],
                "p_duration_minutes": data.get("duration_minutes", 30),
                "p_appointment_type": data.get("appointment_type", "follow_up"),
                "p_location": data.get("location"),
                "p_reason": data.get("reason"),
            },
        )
        rows = result.get("appointments")
        if not isinstance(rows, list) or not rows:
            raise ExternalServiceError("Supabase", "Appointment offer could not be saved")
        return [row for row in rows if isinstance(row, dict)]

    async def _appointment_rpc(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        result = await self._execute(self.db.rpc(name, params))
        data = result.data
        if not isinstance(data, dict):
            raise ExternalServiceError("Supabase", "Could not update appointment offer")
        error = data.get("error")
        if error == "forbidden":
            raise AuthorizationError(
                "You cannot change this appointment offer",
                reason_code=reasons.NO_CARE_TEAM_ASSIGNMENT,
            )
        if error == "not_found":
            raise NotFoundError("Appointment offer", "unavailable")
        if error in _BOOKING_ERRORS:
            raise _booking_error(error)
        if error:
            raise ValidationError("This appointment offer is no longer available or is invalid")
        return data

    async def respond_to_appointment(
        self,
        *,
        user_id: UUID,
        role: str,
        appointment_id: UUID,
        action: AppointmentResponseAction,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Apply a patient's response to their appointment.

        Handles accept, decline, request-alternative, and cancel, each allowed
        only from the source statuses declared in ``_RESPONSE_TRANSITIONS``.
        """
        if role != "patient":
            raise AuthorizationError(
                "Only the patient can respond to an appointment",
                reason_code=reasons.ROLE_LACKS_CLINICAL_SCOPE,
            )

        allowed_from, _ = _RESPONSE_TRANSITIONS[action]

        appointment = await self._get_appointment(str(appointment_id))
        if str(appointment.get("patient_id")) != str(user_id):
            raise AuthorizationError(
                "You can only respond to your own appointments",
                reason_code=reasons.PATIENT_SCOPE_SELF_ONLY,
            )
        if appointment.get("status") == AppointmentStatus.EXPIRED.value:
            raise _booking_error("expired")
        if appointment.get("status") not in allowed_from:
            raise _booking_error("stale")

        offer_result = await self._appointment_rpc(
            "respond_to_appointment_offer",
            {
                "p_actor_id": str(user_id),
                "p_appointment_id": str(appointment_id),
                "p_action": action.value,
                "p_note": note,
            },
        )
        return dict(offer_result["appointment"])

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
        if existing.get("proposal_group_id"):
            raise ValidationError("Use the appointment offer response workflow for grouped visits")
        payload = {key: value for key, value in data.items() if value is not None}
        if not payload:
            return existing
        if role == "patient":
            raise AuthorizationError(
                "Use the appointment response workflow to change your visit",
                reason_code=reasons.ROLE_LACKS_CLINICAL_SCOPE,
            )
        # Standalone offers must use the same audited lifecycle as grouped offers.
        # Generic edits must not reopen a declined/cancelled visit or confirm it.
        if "status" in payload:
            raise _booking_error("stale")
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
        raise AuthorizationError(
            "You are not authorized to manage this appointment",
            reason_code=reasons.NO_CARE_TEAM_ASSIGNMENT,
        )

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
        try:
            return await asyncio.to_thread(query.execute)
        except APIError as exc:
            if exc.code == "23P01":
                raise _booking_error("conflict") from None
            if exc.code == "40P01":
                raise _booking_error("stale") from None
            if exc.code == "P0001" and exc.message in {
                "appointment_expired",
                "appointment_past",
                "appointment_stale",
            }:
                raise _booking_error(exc.message.removeprefix("appointment_")) from None
            raise ExternalServiceError("Supabase", "Appointment operation failed") from None
