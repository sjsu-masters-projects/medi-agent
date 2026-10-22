"""Which care team a document belongs to: choosing it at upload, claiming it, listing it.

PLAN-002 / CLN-003 slice G. A patient can have several care teams and a document belongs to
one of them. At upload the patient names a team, or says "Not sure" and the document is
unrouted: it sits in every active team's queue until one clinician claims the whole document
(``claim_document``, atomic in the database). The read rules live in ``care_team_access``;
this service only decides where a new document goes and exposes claiming and the queue.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from app.core.exceptions import NotFoundError, ValidationError
from app.services.care_team_access import CareTeamAccessService

CARE_TEAM_REQUIRED = "CARE_TEAM_REQUIRED"
DOCUMENT_ALREADY_CLAIMED = "DOCUMENT_ALREADY_CLAIMED"
_CHUNK = 100
_QUEUE_COLUMNS = (
    "id, patient_id, file_name, display_title, document_type, created_at, review_status, "
    "uploaded_by_role, parse_status, routing_state, care_team_id"
)


def _rows(response: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], response.data or [])


def _chunks(values: Sequence[str]) -> list[list[str]]:
    return [list(values[start : start + _CHUNK]) for start in range(0, len(values), _CHUNK)]


class DocumentRoutingService:
    """Decides, claims and lists document ownership. Synchronous, like the access service."""

    def __init__(self, db: Client) -> None:
        self.db = db
        self.access = CareTeamAccessService(db)

    # ── Upload ──────────────────────────────────────────

    def upload_target(
        self,
        *,
        uploader_role: str,
        uploader_id: UUID | str,
        patient_id: UUID | str,
        care_team_id: UUID | str | None,
        not_sure: bool,
    ) -> dict[str, Any]:
        """Where a new document goes: ``{"care_team_id", "routing_state"}``."""
        if uploader_role == "clinician":
            return self._clinician_target(uploader_id, patient_id, care_team_id, not_sure)
        return self._patient_target(patient_id, care_team_id, not_sure)

    def _patient_target(
        self, patient_id: UUID | str, care_team_id: UUID | str | None, not_sure: bool
    ) -> dict[str, Any]:
        if care_team_id and not_sure:
            raise ValidationError("Choose one care team or Not sure, not both")
        active = [
            str(row["id"])
            for row in _rows(
                self.db.table("care_teams")
                .select("id")
                .eq("patient_id", str(patient_id))
                .eq("status", "active")
                .execute()
            )
        ]
        if care_team_id:
            # One neutral message for unknown, someone else's and ended teams alike.
            if str(care_team_id) not in active:
                raise ValidationError("Choose one of your care teams for this document")
            return _routed(str(care_team_id))
        if not_sure:
            return _unrouted()
        if len(active) == 1:
            return _routed(active[0])
        if not active:
            return _unrouted()
        raise ValidationError(
            "Choose which care team this document is for, or Not sure", code=CARE_TEAM_REQUIRED
        )

    def _clinician_target(
        self,
        clinician_id: UUID | str,
        patient_id: UUID | str,
        care_team_id: UUID | str | None,
        not_sure: bool,
    ) -> dict[str, Any]:
        if not_sure:
            raise ValidationError("A clinician upload must belong to one of your care teams")
        return _routed(self.resolve_clinician_link(clinician_id, patient_id, care_team_id))

    def resolve_clinician_link(
        self,
        clinician_id: UUID | str,
        patient_id: UUID | str,
        care_team_id: UUID | str | None = None,
    ) -> str:
        """The clinician's own active link to use for a new record about this patient.

        The only link when there is one; the named link when it is theirs; otherwise the
        caller must say which (``CARE_TEAM_REQUIRED``). No link at all is an authorization
        error, exactly as for every other clinician read.
        """
        access = self.access.for_patient(clinician_id, patient_id)
        if care_team_id:
            if str(care_team_id) not in access.team_ids:
                raise ValidationError("Choose one of your own care teams for this record")
            return str(care_team_id)
        if len(access.team_ids) == 1:
            return next(iter(access.team_ids))
        raise ValidationError(
            "Choose which of your care teams this record belongs to", code=CARE_TEAM_REQUIRED
        )

    def patient_options(self, patient_id: UUID | str) -> list[dict[str, Any]]:
        """The patient's active teams for the upload picker. Names only, no contact details."""
        teams = _rows(
            self.db.table("care_teams")
            .select("id, clinician_id, clinic_id, role, specialty_context")
            .eq("patient_id", str(patient_id))
            .eq("status", "active")
            .execute()
        )
        clinicians = self._by_id(
            "clinicians",
            "id, first_name, last_name, specialty",
            [str(team["clinician_id"]) for team in teams if team.get("clinician_id")],
        )
        clinics = self._by_id(
            "clinics",
            "id, display_name",
            [str(team["clinic_id"]) for team in teams if team.get("clinic_id")],
        )
        options = []
        for team in teams:
            clinician = clinicians.get(str(team.get("clinician_id")), {})
            clinic = clinics.get(str(team.get("clinic_id")), {})
            name = " ".join(
                str(clinician.get(key) or "").strip() for key in ("first_name", "last_name")
            ).strip()
            options.append(
                {
                    "care_team_id": str(team["id"]),
                    "specialty": _first_text(
                        team.get("specialty_context"), clinician.get("specialty"), team.get("role")
                    ),
                    "clinician_name": name or None,
                    "clinic_name": clinic.get("display_name"),
                    "clinic_id": str(team["clinic_id"]) if team.get("clinic_id") else None,
                }
            )
        return sorted(options, key=lambda item: (item["clinic_name"] or "", item["care_team_id"]))

    def _by_id(self, table: str, columns: str, ids: list[str]) -> dict[str, dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        for chunk in _chunks(sorted(set(ids))):
            for row in _rows(self.db.table(table).select(columns).in_("id", chunk).execute()):
                found[str(row["id"])] = row
        return found

    # ── Claim ───────────────────────────────────────────

    def claim(
        self, *, clinician_id: UUID | str, document_id: UUID | str, care_team_id: UUID | str
    ) -> dict[str, Any]:
        """Claim an unrouted document for one of the clinician's own teams."""
        document = _rows(
            self.db.table("documents")
            .select("id, patient_id")
            .eq("id", str(document_id))
            .limit(1)
            .execute()
        )
        if not document:
            raise NotFoundError("Document", str(document_id))
        access = self.access.for_patient(clinician_id, document[0]["patient_id"], require=False)
        if not access.owns(care_team_id):
            # Same answer as a missing document: no existence leak.
            raise NotFoundError("Document", str(document_id))
        try:
            response = self.db.rpc(
                "claim_document",
                {
                    "p_document_id": str(document_id),
                    "p_actor_id": str(clinician_id),
                    "p_care_team_id": str(care_team_id),
                },
            ).execute()
        except APIError as exc:
            message = str(getattr(exc, "message", exc))
            code = str(getattr(exc, "code", ""))
            if "document unavailable" in message or code == "42501":
                raise NotFoundError("Document", str(document_id)) from None
            if "claimed by someone else" in message or code == "40001":
                raise ValidationError(
                    "This document was already claimed by another care team",
                    code=DOCUMENT_ALREADY_CLAIMED,
                ) from None
            raise
        data = response.data
        if isinstance(data, list):
            data = data[0] if data else None
        outcome = cast(dict[str, Any], data or {})
        return {
            "document_id": str(outcome.get("document_id") or document_id),
            "care_team_id": str(outcome.get("care_team_id") or care_team_id),
            "status": str(outcome.get("status") or "claimed"),
            "replayed": bool(outcome.get("replayed", False)),
        }

    # ── Queue ───────────────────────────────────────────

    def queue(
        self, *, clinician_id: UUID | str, patient_id: UUID | str | None = None
    ) -> list[dict[str, Any]]:
        """Documents this clinician may see: their teams' routed ones, plus unrouted ones."""
        links = self.access.for_clinician(clinician_id)
        if patient_id is not None:
            patients = [str(patient_id)] if str(patient_id) in links.teams_by_patient else []
        else:
            patients = links.patient_ids
        rows: list[dict[str, Any]] = []
        for chunk in _chunks(patients):
            rows += _rows(
                self.db.table("documents")
                .select(_QUEUE_COLUMNS)
                .in_("patient_id", chunk)
                .order("created_at", desc=True)
                .execute()
            )
        visible = links.keep(rows, "document")
        for row in visible:
            row["needs_claim"] = row.get("routing_state") == "unrouted"
            row["claimable_care_team_ids"] = sorted(links.for_patient(row["patient_id"]).team_ids)
        return visible


def _routed(care_team_id: str) -> dict[str, Any]:
    return {"care_team_id": care_team_id, "routing_state": "routed"}


def _unrouted() -> dict[str, Any]:
    return {"care_team_id": None, "routing_state": "unrouted"}


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value and str(value).strip():
            return str(value).strip()
    return None
