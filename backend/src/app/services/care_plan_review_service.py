"""Review items, adoption and retirement for care plans (PLAN-002).

A review item is work for a care team (or, without patient detail, a clinic's admins):
an unowned or unassigned plan, or a conflict another team raised. Adopting a plan makes it
the adopter's; retiring turns off specific activities with a written reason. Neither is ever
automatic, and a care team ending changes no medication status. Authorization is checked
here and again inside the database function, which takes the patient lock.
"""

from __future__ import annotations

import logging
from typing import Any, cast
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.services.care_plan_lineage import CarePlanLineageService

logger = logging.getLogger(__name__)

PATIENT_ITEM_FIELDS = (
    "id, patient_id, care_plan_id, kind, target_care_team_id, conflict_fingerprint, summary, "
    "request_note, reply_note, status, created_at, resolved_at"
)
CLINIC_ITEM_FIELDS = "id, care_plan_id, kind, target_clinic_id, status, created_at"


class CarePlanReviewService:
    def __init__(self, db: Client) -> None:
        self.db = db
        self.lineage = CarePlanLineageService(db)

    def list_for_clinician(self, clinician_id: UUID, *, status: str = "open") -> dict[str, Any]:
        """Items addressed to the clinician's care teams, and counts for clinics they administer."""
        links = cast(
            list[dict[str, Any]],
            self.db.table("care_teams")
            .select("id, patient_id, clinic_id, clinics(display_name)")
            .eq("clinician_id", str(clinician_id))
            .eq("status", "active")
            .execute()
            .data
            or [],
        )
        team_ids = [str(link["id"]) for link in links]
        items: list[dict[str, Any]] = []
        if team_ids:
            items = cast(
                list[dict[str, Any]],
                self.db.table("care_plan_review_items")
                .select(PATIENT_ITEM_FIELDS)
                .in_("target_care_team_id", team_ids)
                .eq("status", status)
                .order("created_at", desc=True)
                .limit(200)
                .execute()
                .data
                or [],
            )
        items = self._with_names(items, links)
        admin_clinics = [
            str(row["clinic_id"])
            for row in cast(
                list[dict[str, Any]],
                self.db.table("clinic_memberships")
                .select("clinic_id")
                .eq("clinician_id", str(clinician_id))
                .eq("status", "active")
                .eq("role", "admin")
                .execute()
                .data
                or [],
            )
        ]
        clinic_items: list[dict[str, Any]] = []
        if admin_clinics:
            clinic_items = cast(
                list[dict[str, Any]],
                self.db.table("care_plan_review_items")
                .select(CLINIC_ITEM_FIELDS)
                .in_("target_clinic_id", admin_clinics)
                .eq("status", status)
                .order("created_at", desc=True)
                .limit(200)
                .execute()
                .data
                or [],
            )
        return {"items": items, "clinic_items": clinic_items}

    def _with_names(
        self, items: list[dict[str, Any]], links: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Add the patient's name and the clinic of the addressed link to each item.

        Both are things this clinician already sees for the patient through that link; the
        clinic items (addressed to admins) never get them.
        """
        if not items:
            return items
        patient_ids = sorted({str(item["patient_id"]) for item in items})
        patients = {
            str(row["id"]): row
            for row in cast(
                list[dict[str, Any]],
                self.db.table("patients")
                .select("id, first_name, last_name")
                .in_("id", patient_ids)
                .execute()
                .data
                or [],
            )
        }
        teams = {str(link["id"]): link for link in links}
        named: list[dict[str, Any]] = []
        for item in items:
            patient = patients.get(str(item["patient_id"]), {})
            team = teams.get(str(item.get("target_care_team_id")), {})
            clinic = cast(dict[str, Any], team.get("clinics") or {})
            name = " ".join(
                part for part in (patient.get("first_name"), patient.get("last_name")) if part
            )
            named.append(
                {
                    **item,
                    "patient_name": name or None,
                    "clinic_id": team.get("clinic_id"),
                    "clinic_name": clinic.get("display_name"),
                }
            )
        return named

    def reply(self, clinician_id: UUID, item_id: UUID, note: str | None) -> dict[str, Any]:
        try:
            result = self.db.rpc(
                "reply_care_plan_review_item",
                {"p_item_id": str(item_id), "p_actor_id": str(clinician_id), "p_note": note},
            ).execute()
        except APIError as error:
            if str(error.code) == "42501":
                raise NotFoundError("Review item", str(item_id)) from None
            raise ValidationError(str(error.message)[:300]) from None
        return cast(dict[str, Any], result.data or {})

    def adopt(
        self,
        clinician_id: UUID,
        care_plan_id: UUID,
        *,
        care_team_id: UUID,
        note: str,
    ) -> dict[str, Any]:
        self._require_own_link(clinician_id, care_plan_id, care_team_id)
        try:
            result = self.db.rpc(
                "adopt_care_plan",
                {
                    "p_care_plan_id": str(care_plan_id),
                    "p_actor_id": str(clinician_id),
                    "p_care_team_id": str(care_team_id),
                    "p_note": note.strip(),
                },
            ).execute()
        except APIError as error:
            if str(error.code) == "40001":
                raise ConflictError(
                    "Another care team already adopted this plan", code="PLAN_ALREADY_ADOPTED"
                ) from None
            if str(error.code) == "42501":
                raise NotFoundError("Care plan", str(care_plan_id)) from None
            raise ValidationError(str(error.message)[:300]) from None
        return cast(dict[str, Any], result.data or {})

    def retire_items(
        self,
        clinician_id: UUID,
        care_plan_id: UUID,
        *,
        care_team_id: UUID,
        item_ids: list[UUID],
        reason: str,
    ) -> dict[str, Any]:
        self._require_own_link(clinician_id, care_plan_id, care_team_id)
        try:
            result = self.db.rpc(
                "retire_care_plan_items",
                {
                    "p_care_plan_id": str(care_plan_id),
                    "p_actor_id": str(clinician_id),
                    "p_care_team_id": str(care_team_id),
                    "p_item_ids": [str(item_id) for item_id in item_ids],
                    "p_reason": reason.strip(),
                },
            ).execute()
        except APIError as error:
            if str(error.code) == "42501":
                raise NotFoundError("Care plan", str(care_plan_id)) from None
            raise ValidationError(str(error.message)[:300]) from None
        return cast(dict[str, Any], result.data or {})

    def take_record(
        self,
        clinician_id: UUID,
        record: str,
        record_id: UUID,
        *,
        care_team_id: UUID,
    ) -> dict[str, Any]:
        """Take up a reviewed ADR assessment or MedWatch draft that has no care team.

        Exactly one team can: a second caller gets 409 RECORD_ALREADY_TAKEN. Until then the
        record is visible to no clinician; the patient's care teams were each asked.
        """
        try:
            result = self.db.rpc(
                "assign_clinical_record_owner",
                {
                    "p_record": record,
                    "p_record_id": str(record_id),
                    "p_actor_id": str(clinician_id),
                    "p_care_team_id": str(care_team_id),
                },
            ).execute()
        except APIError as error:
            if str(error.code) == "40001":
                raise ConflictError(
                    "Another care team already took this record", code="RECORD_ALREADY_TAKEN"
                ) from None
            if str(error.code) == "42501":
                raise NotFoundError("Record", str(record_id)) from None
            raise ValidationError(str(error.message)[:300]) from None
        return cast(dict[str, Any], result.data or {})

    def _require_own_link(self, clinician_id: UUID, care_plan_id: UUID, care_team_id: UUID) -> None:
        """The named link must be the caller's own, at the plan's patient (neutral otherwise)."""
        plan = self.lineage.plan(care_plan_id)
        if plan is None:
            raise NotFoundError("Care plan", str(care_plan_id))
        scopes = self.lineage.scopes.list_for_clinician(clinician_id, UUID(str(plan["patient_id"])))
        if care_team_id not in {scope.care_team_id for scope in scopes}:
            raise NotFoundError("Care plan", str(care_plan_id))
