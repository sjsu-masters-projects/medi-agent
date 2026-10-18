"""Appointment persistence and authorization service."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
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
from app.services.clinic_membership_service import ClinicMembershipService

logger = logging.getLogger(__name__)

# A clinician's offer ran into a booked visit of their own at any clinic (CLN-003 slice E).
CLINICIAN_CONFLICT_CODE = "CLINICIAN_SCHEDULE_CONFLICT"

_WITH_CLINIC = "*, clinics(display_name)"

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
    "too_early": ("APPOINTMENT_NOT_ENDED", "This visit has not ended yet"),
}

# Visit statuses a clinician may still edit the details of.
_EDITABLE = {"proposed", "confirmed", "scheduled"}
_BOOKED = {"confirmed", "scheduled"}
_DETAIL_FIELDS = {"appointment_type", "location", "reason", "notes"}
_TIME_FIELDS = {"scheduled_at", "duration_minutes"}


def _booking_error(reason: str) -> ValidationError:
    code, message = _BOOKING_ERRORS[reason]
    return ValidationError(message, code=code)


def _utc_label(value: Any) -> str:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    return moment.astimezone(UTC).strftime("%b %-d, %Y %H:%M UTC")


def _clinician_conflict(conflicts: list[dict[str, Any]]) -> ValidationError:
    """The clinician's own schedule is in the way: name the clinic and the time, nothing else.

    The database returns only the clinic and the interval of the visit in the way. A patient of
    another clinic is never read, so there is nothing to leak; the log carries a count only.
    """
    clean = [
        {
            "slot": str(item.get("slot")),
            "clinic_id": item.get("clinic_id"),
            "clinic_name": str(item.get("clinic_name") or ""),
            "starts_at": str(item.get("starts_at")),
            "ends_at": str(item.get("ends_at")),
        }
        for item in conflicts
        if isinstance(item, dict)
    ]
    logger.info(
        "Appointment offer refused: %d slot(s) overlap the clinician's schedule", len(clean)
    )
    first = clean[0] if clean else {}
    message = (
        f"You already have an appointment at {first.get('clinic_name') or 'another clinic'} "
        f"from {_utc_label(first.get('starts_at'))} to {_utc_label(first.get('ends_at'))}."
    )
    return ValidationError(message, code=CLINICIAN_CONFLICT_CODE, details={"conflicts": clean})


def _clinic_ref(care_team: dict[str, Any]) -> str | None:
    clinic = care_team.get("clinic_id")
    return str(clinic) if clinic else None


def _flatten_clinic(row: dict[str, Any]) -> dict[str, Any]:
    """Turn the embedded ``clinics(display_name)`` into the ``clinic_name`` tag (in place)."""
    clinic = row.pop("clinics", None)
    if isinstance(clinic, dict):
        row["clinic_name"] = clinic.get("display_name")
    else:
        row.setdefault("clinic_name", None)
    return row


class AppointmentService:
    """Patient/clinician appointment operations."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def export_calendar_for_user(
        self, *, user_id: UUID, role: str, appointment_id: UUID, locale: CalendarLocale
    ) -> AppointmentCalendarExport:
        appointment = await self._get_appointment(str(appointment_id))
        await self._ensure_can_access(user_id=user_id, role=role, appointment=appointment)
        if appointment.get("status") not in {"confirmed", "scheduled", "cancelled"}:
            raise _booking_error("stale")
        # A cancelled visit exports as STATUS:CANCELLED, so re-importing it removes the entry.
        return render_appointment_calendar(AppointmentRead.model_validate(appointment), locale)

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        role: str,
        clinic_id: UUID | None = None,
        patient_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
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
                .select(_WITH_CLINIC)
                .eq("patient_id", str(user_id))
                .order("scheduled_at")
            )
            return [_flatten_clinic(row) for row in (result.data or []) if isinstance(row, dict)]

        if role == "clinician":
            scope = await ClinicMembershipService(self).link_scope(user_id, clinic_id)
            assignments = scope.patient_ids
            if patient_id is not None:
                # One patient's record: only if the caller holds a link to them.
                assignments = [pid for pid in assignments if pid == str(patient_id)]
            if not assignments:
                return []
            result = await self._execute(
                self.db.table("appointments")
                .select(_WITH_CLINIC)
                .in_("patient_id", assignments)
                .in_("clinic_id", scope.clinic_ids)
                .order("scheduled_at")
            )
            # An appointment carries the clinic it was made under. The two IN filters above are a
            # cross product, so keep only visits whose (patient, clinic) is one of the caller's
            # links: a shared patient's visit at a clinic where the caller has no link to that
            # patient is not theirs to see.
            return [
                _flatten_clinic(row)
                for row in (result.data or [])
                if isinstance(row, dict)
                and (str(row.get("patient_id")), str(row.get("clinic_id"))) in scope.pairs
            ]

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
                clinic_id=_clinic_ref(care_team),
            )
        if role == "clinician" and clinician_id != str(user_id):
            raise AuthorizationError(
                "Clinicians can only create appointments for assigned patients",
                reason_code=reasons.NO_CARE_TEAM_ASSIGNMENT,
                clinic_id=_clinic_ref(care_team),
            )
        if role not in {"patient", "clinician"}:
            raise AuthorizationError(
                "Unsupported role for appointments",
                reason_code=reasons.UNSUPPORTED_ROLE,
            )

        if role == "clinician":
            # A single offered time is an offer too: it runs against the whole schedule.
            start = datetime.fromisoformat(str(data.get("scheduled_at")).replace("Z", "+00:00"))
            conflicts = await self._schedule_conflicts(
                clinician_id, [start], int(data.get("duration_minutes") or 30)
            )
            if conflicts:
                raise _clinician_conflict(conflicts)

        clinician_name = await self._get_clinician_name(clinician_id)
        # A clinician offers a slot the patient must accept; a patient booking
        # their own appointment has nothing to confirm.
        initial_status = (
            AppointmentStatus.PROPOSED if role == "clinician" else AppointmentStatus.SCHEDULED
        )
        payload = {
            "patient_id": patient_id,
            "care_team_id": str(data.get("care_team_id")),
            # The link decides (a trigger enforces it); naming it keeps the insert explicit.
            "clinic_id": care_team.get("clinic_id"),
            "clinician_id": clinician_id,
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
        return self._tag_clinic(rows[0], care_team)

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
                clinic_id=_clinic_ref(care_team),
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
        return [self._tag_clinic(row, care_team) for row in rows if isinstance(row, dict)]

    async def _schedule_conflicts(
        self, clinician_id: str, slots: list[datetime], duration_minutes: int
    ) -> list[dict[str, Any]]:
        """Booked visits of this clinician, at any clinic, that overlap a proposed slot.

        Intervals are ``[start, end)``: back-to-back visits do not conflict. Only the clinic and
        the interval of the visit in the way are read; no patient is.
        """
        found: list[dict[str, Any]] = []
        for slot in sorted(slots):
            end = slot + timedelta(minutes=duration_minutes)
            result = await self._execute(
                self.db.table("appointments")
                .select("scheduled_at, duration_minutes, clinic_id, clinics(display_name)")
                .eq("clinician_id", clinician_id)
                .in_("status", ["confirmed", "scheduled"])
                .gte("scheduled_at", (slot - timedelta(minutes=480)).isoformat())
                .lt("scheduled_at", end.isoformat())
                .order("scheduled_at")
            )
            for booked in (row for row in (result.data or []) if isinstance(row, dict)):
                begins = datetime.fromisoformat(str(booked["scheduled_at"]).replace("Z", "+00:00"))
                finishes = begins + timedelta(minutes=int(booked.get("duration_minutes") or 30))
                if begins < end and slot < finishes:
                    clinic = booked.get("clinics")
                    found.append(
                        {
                            "slot": slot.isoformat(),
                            "clinic_id": booked.get("clinic_id"),
                            "clinic_name": clinic.get("display_name")
                            if isinstance(clinic, dict)
                            else None,
                            "starts_at": begins.isoformat(),
                            "ends_at": finishes.isoformat(),
                        }
                    )
                    break
        return found

    @staticmethod
    def _tag_clinic(row: dict[str, Any], care_team: dict[str, Any]) -> dict[str, Any]:
        """The clinic name of the link the appointment was made under (read-only in the portal)."""
        clinic = care_team.get("clinics")
        row["clinic_name"] = clinic.get("display_name") if isinstance(clinic, dict) else None
        return row

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
        if error == "clinician_conflict":
            conflicts = data.get("conflicts")
            raise _clinician_conflict(conflicts if isinstance(conflicts, list) else [])
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
        response = dict(offer_result["appointment"])
        response["clinic_name"] = appointment.get("clinic_name")
        return response

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
        grouped = bool(existing.get("proposal_group_id"))
        # A grouped offer's status and times belong to the offer workflow; its details do not.
        if grouped and (set(payload) - _DETAIL_FIELDS):
            raise ValidationError("Use the appointment offer response workflow for grouped visits")
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
        status = str(existing.get("status"))
        if status not in _EDITABLE:
            raise _booking_error("stale")
        if status in _BOOKED and (set(payload) & _TIME_FIELDS):
            # The patient agreed to this time; a different one is a new offer they can answer.
            raise ValidationError(
                "Offer new times to change when a booked visit takes place",
                code="APPOINTMENT_TIME_CHANGE_VIA_OFFER",
            )
        query = self.db.table("appointments").update(payload)
        if grouped and status == "proposed":
            # Every still-open slot of the offer shares its details.
            query = query.eq("proposal_group_id", str(existing["proposal_group_id"])).eq(
                "status", "proposed"
            )
        else:
            query = query.eq("id", str(appointment_id))
        result = await self._execute(query)
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        if not rows:
            raise ExternalServiceError("Supabase", "Failed to update appointment")
        row = next((item for item in rows if str(item.get("id")) == str(appointment_id)), rows[0])
        row["clinic_name"] = existing.get("clinic_name")
        return row

    async def manage_for_user(
        self,
        *,
        user_id: UUID,
        role: str,
        appointment_id: UUID,
        action: str,
        reason_code: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """A clinician cancels, completes or marks a booked visit no-show (one audited RPC).

        Allowed for the appointment's own clinician or one with an active link to the patient at
        the appointment's clinic; the RPC checks the same rule again inside the transaction.
        """
        if role != "clinician":
            raise AuthorizationError(
                "Only clinicians can manage a visit",
                reason_code=reasons.ROLE_LACKS_CLINICAL_SCOPE,
            )
        existing = await self._get_appointment(str(appointment_id))
        await self._ensure_can_access(user_id=user_id, role=role, appointment=existing)
        result = await self._appointment_rpc(
            "manage_appointment",
            {
                "p_actor_id": str(user_id),
                "p_appointment_id": str(appointment_id),
                "p_action": action,
                "p_reason_code": reason_code,
                "p_reason": reason,
            },
        )
        row = dict(result["appointment"])
        row["clinic_name"] = existing.get("clinic_name")
        return row

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
            # The appointment's own clinician, or a colleague whose active link to this patient is
            # at the appointment's clinic. A link at another clinic grants nothing here.
            if str(appointment.get("clinician_id")) == str(user_id):
                return
            assignment = await self._execute(
                self.db.table("care_teams")
                .select("id")
                .eq("clinician_id", str(user_id))
                .eq("patient_id", str(appointment.get("patient_id")))
                .eq("clinic_id", str(appointment.get("clinic_id")))
                .eq("status", "active")
                .limit(1)
            )
            if assignment.data:
                return
        raise AuthorizationError(
            "You are not authorized to manage this appointment",
            reason_code=reasons.NO_CARE_TEAM_ASSIGNMENT,
        )

    async def _get_care_team(self, care_team_id: str) -> dict[str, Any]:
        result = await self._execute(
            self.db.table("care_teams")
            .select("id, patient_id, clinician_id, clinic_id, status, clinics(display_name)")
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
            self.db.table("appointments").select(_WITH_CLINIC).eq("id", appointment_id).limit(1)
        )
        rows = [row for row in (result.data or []) if isinstance(row, dict)]
        if not rows:
            raise NotFoundError("Appointment", appointment_id)
        return _flatten_clinic(rows[0])

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
