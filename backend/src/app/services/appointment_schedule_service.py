"""The clinician's own schedule: visits, what needs action, and busy times (UX-006).

Everything here is the caller's own appointments (``appointments.clinician_id``), across all
their clinics or one. Another clinician's visits are never read, and busy times carry only an
interval and a clinic name, never a patient.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from supabase import Client

from app.core import authorization_reasons as reasons
from app.core.exceptions import AuthorizationError, ValidationError
from app.services.appointment_service import AppointmentService, _flatten_clinic
from app.services.clinic_membership_service import ClinicMembershipService

# A range is bounded so one request cannot read a clinician's whole history.
MAX_RANGE = timedelta(days=45)
# Expired, unanswered offers stay on the strip for two weeks.
EXPIRED_WINDOW = timedelta(days=14)
EXPIRING_SOON = timedelta(hours=48)
BOOKED = ["confirmed", "scheduled"]
_WITH_PATIENT = "*, clinics(display_name), patients(first_name, last_name)"
_KINDS = {
    "proposed": "awaiting_reply",
    "alternative_requested": "change_request",
    "expired": "expired",
}


def _moment(value: Any) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _patient_name(row: dict[str, Any]) -> str | None:
    patient = row.pop("patients", None)
    if not isinstance(patient, dict):
        return None
    name = f"{patient.get('first_name') or ''} {patient.get('last_name') or ''}".strip()
    return name or None


class AppointmentScheduleService:
    """Reads of the caller's own schedule. Writes stay in ``AppointmentService``."""

    def __init__(self, db: Client) -> None:
        self.db = db
        self._appointments = AppointmentService(db)

    def _check_range(self, start: datetime, end: datetime) -> None:
        if end <= start:
            raise ValidationError("The end of the range must be after its start")
        if end - start > MAX_RANGE:
            raise ValidationError("Choose a range of 45 days or less")

    async def _clinic_allowed(self, clinician_id: UUID, clinic_id: UUID | None) -> bool:
        """A clinic filter is honoured only for a clinic the caller belongs to."""
        if clinic_id is None:
            return True
        members = await ClinicMembershipService(self._appointments).active_memberships(clinician_id)
        return str(clinic_id) in {str(member.clinic_id) for member in members}

    @staticmethod
    def _require_clinician(role: str) -> None:
        if role != "clinician":
            raise AuthorizationError(
                "Only clinicians have a schedule", reason_code=reasons.UNSUPPORTED_ROLE
            )

    async def schedule(
        self,
        *,
        user_id: UUID,
        role: str,
        start: datetime,
        end: datetime,
        clinic_id: UUID | None = None,
    ) -> dict[str, Any]:
        self._require_clinician(role)
        self._check_range(start, end)
        if not await self._clinic_allowed(user_id, clinic_id):
            return {"visits": [], "needs_action": [], "next_visit": None}
        execute = self._appointments._execute
        await self._appointments._appointment_rpc(
            "expire_appointment_proposals", {"p_actor_id": str(user_id), "p_actor_role": role}
        )
        now = datetime.now(UTC)

        def own(query: Any) -> Any:
            query = query.eq("clinician_id", str(user_id))
            return query.eq("clinic_id", str(clinic_id)) if clinic_id else query

        visits = await execute(
            own(self.db.table("appointments").select(_WITH_PATIENT))
            .in_("status", BOOKED)
            .gte("scheduled_at", start.isoformat())
            .lt("scheduled_at", end.isoformat())
            .order("scheduled_at")
        )
        open_rows = await execute(
            own(self.db.table("appointments").select(_WITH_PATIENT))
            .in_("status", list(_KINDS))
            .gte("scheduled_at", (now - EXPIRED_WINDOW).isoformat())
            .order("scheduled_at")
        )
        upcoming = await execute(
            own(self.db.table("appointments").select(_WITH_PATIENT))
            .in_("status", BOOKED)
            .gte("scheduled_at", now.isoformat())
            .order("scheduled_at")
            .limit(1)
        )
        return {
            "visits": [self._visit(row) for row in _dicts(visits)],
            "needs_action": self._needs_action(_dicts(open_rows), now),
            "next_visit": next((self._visit(row) for row in _dicts(upcoming)), None),
        }

    @staticmethod
    def _visit(row: dict[str, Any]) -> dict[str, Any]:
        row["patient_name"] = _patient_name(row)
        return _flatten_clinic(row)

    @staticmethod
    def _needs_action(rows: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
        """One item per offer: slots that share a proposal group are one decision."""
        groups: dict[str, dict[str, Any]] = {}
        for row in rows:
            kind = _KINDS.get(str(row.get("status")))
            if kind is None:
                continue
            slot = _moment(row["scheduled_at"])
            expires = (
                _moment(row["proposal_expires_at"]) if row.get("proposal_expires_at") else None
            )
            if kind == "awaiting_reply" and (expires is None or expires <= now or slot <= now):
                continue  # the sweep expires it on the next read; never show a dead offer as open
            key = f"{kind}:{row.get('proposal_group_id') or row['id']}"
            current = groups.get(key)
            if current is None:
                tagged = _flatten_clinic(dict(row))
                groups[key] = {
                    "kind": kind,
                    "appointment_id": row["id"],
                    "proposal_group_id": row.get("proposal_group_id"),
                    "patient_id": row["patient_id"],
                    "patient_name": _patient_name(tagged),
                    "clinic_id": row.get("clinic_id"),
                    "clinic_name": tagged.get("clinic_name"),
                    "slot_count": 1,
                    "first_slot_at": slot,
                    "expires_at": expires,
                    "expiring_soon": bool(
                        kind == "awaiting_reply" and expires and expires - now <= EXPIRING_SOON
                    ),
                }
            else:
                current["slot_count"] += 1
                if slot < current["first_slot_at"]:
                    current["first_slot_at"] = slot
                    current["appointment_id"] = row["id"]
        order = {"awaiting_reply": 0, "change_request": 1, "expired": 2}
        return sorted(
            groups.values(),
            key=lambda item: (
                order[item["kind"]],
                item["expires_at"] or item["first_slot_at"],
            ),
        )

    async def busy(
        self, *, user_id: UUID, role: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        """The caller's booked intervals in a range, all clinics: times and clinic names only."""
        self._require_clinician(role)
        if end <= start or end - start > timedelta(hours=48):
            raise ValidationError("Choose a range of 48 hours or less")
        result = await self._appointments._execute(
            self.db.table("appointments")
            .select("scheduled_at, duration_minutes, clinic_id, clinics(display_name)")
            .eq("clinician_id", str(user_id))
            .in_("status", BOOKED)
            # A booking is at most eight hours long, so one that began earlier may still overlap.
            .gte("scheduled_at", (start - timedelta(minutes=480)).isoformat())
            .lt("scheduled_at", end.isoformat())
            .order("scheduled_at")
        )
        found: list[dict[str, Any]] = []
        for row in _dicts(result):
            begins = _moment(row["scheduled_at"])
            finishes = begins + timedelta(minutes=int(row.get("duration_minutes") or 30))
            if finishes <= start:
                continue
            clinic = row.get("clinics")
            found.append(
                {
                    "starts_at": begins,
                    "ends_at": finishes,
                    "clinic_id": row.get("clinic_id"),
                    "clinic_name": clinic.get("display_name") if isinstance(clinic, dict) else None,
                }
            )
        return found


def _dicts(result: Any) -> list[dict[str, Any]]:
    return [row for row in (result.data or []) if isinstance(row, dict)]
