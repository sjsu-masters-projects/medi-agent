"""The shared clinical core (PLAN-002, CLN-003 slice G).

Medications, allergies and the conditions a patient has not marked sensitive are shared with
every care team of the patient, each with the recording team and clinic. A sensitive
condition reaches only the team that recorded it; everyone else is told some are private.
One database function produces the clinician's view so no reader can show a partial list
without saying so.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from app.core import authorization_reasons as reasons
from app.core.exceptions import AuthorizationError, NotFoundError


class SharedClinicalCoreService:
    def __init__(self, db: Client) -> None:
        self.db = db

    def summary_for_clinician(self, clinician_id: UUID, patient_id: UUID) -> dict[str, Any]:
        try:
            result = self.db.rpc(
                "shared_clinical_summary",
                {"p_clinician_id": str(clinician_id), "p_patient_id": str(patient_id)},
            ).execute()
        except APIError as error:
            if str(error.code) == "42501":
                raise AuthorizationError(
                    "You are not assigned to this patient",
                    reason_code=reasons.NO_CARE_TEAM_ASSIGNMENT,
                    actor_id=str(clinician_id),
                    actor_role="clinician",
                    target_type="patient",
                    target_id=str(patient_id),
                ) from None
            raise
        return cast(dict[str, Any], result.data or {})

    def conditions_for_patient(self, patient_id: UUID) -> list[dict[str, Any]]:
        """The patient sees all of their own conditions and which are marked sensitive."""
        rows = cast(
            list[dict[str, Any]],
            self.db.table("conditions")
            .select("id, name, icd10_code, status, is_sensitive, recorded_by")
            .eq("patient_id", str(patient_id))
            .order("created_at")
            .execute()
            .data
            or [],
        )
        return rows

    def set_sensitivity(
        self, patient_id: UUID, condition_id: UUID, is_sensitive: bool
    ) -> dict[str, Any]:
        """Mark or unmark one of the patient's own conditions. Audited without its name."""
        try:
            result = self.db.rpc(
                "set_condition_sensitivity",
                {
                    "p_patient_id": str(patient_id),
                    "p_condition_id": str(condition_id),
                    "p_is_sensitive": is_sensitive,
                },
            ).execute()
        except APIError as error:
            if str(error.code) == "42501":
                raise NotFoundError("Condition", str(condition_id)) from None
            raise
        return cast(dict[str, Any], result.data or {})
