"""Exact patient/clinician/clinic scope for independent care-plan workspaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from supabase import Client

from app.core.exceptions import AuthorizationError, ValidationError
from app.db.repositories.care_teams import CareTeamRepository
from app.db.repositories.clinic_memberships import ClinicMembershipRepository


@dataclass(frozen=True)
class CareTeamPlanScope:
    care_team_id: UUID
    patient_id: UUID
    clinician_id: UUID
    clinic_id: UUID
    clinic_name: str | None
    specialty: str | None = None


class CareTeamPlanScopeService:
    """Membership is necessary, never sufficient; an exact active link is required."""

    def __init__(self, db: Client) -> None:
        self.db = db
        self.teams = CareTeamRepository(self)
        self.memberships = ClinicMembershipRepository(self)

    def list_for_clinician(self, clinician_id: UUID, patient_id: UUID) -> list[CareTeamPlanScope]:
        memberships = self.memberships.list_active_for_clinician_sync(str(clinician_id))
        allowed = {
            str(row["clinic_id"])
            for row in memberships
            if row.get("clinician_id") == str(clinician_id)
            and row.get("status") == "active"
            and (row.get("clinics") or {}).get("status") == "active"
        }
        rows = self.teams.list_patient_links_sync(str(clinician_id), str(patient_id))
        return [
            self._scope(row)
            for row in rows
            if self._allowed(row, clinician_id, patient_id, allowed)
        ]

    @staticmethod
    def _allowed(
        row: dict[str, Any], clinician_id: UUID, patient_id: UUID, allowed: set[str]
    ) -> bool:
        return (
            row.get("clinician_id") == str(clinician_id)
            and row.get("patient_id") == str(patient_id)
            and row.get("status") == "active"
            and str(row.get("clinic_id")) in allowed
        )

    @staticmethod
    def _scope(row: dict[str, Any]) -> CareTeamPlanScope:
        return CareTeamPlanScope(
            care_team_id=UUID(str(row["id"])),
            patient_id=UUID(str(row["patient_id"])),
            clinician_id=UUID(str(row["clinician_id"])),
            clinic_id=UUID(str(row["clinic_id"])),
            clinic_name=(row.get("clinics") or {}).get("display_name"),
            specialty=(
                str(row.get("specialty_context") or "").strip()
                or str((row.get("clinicians") or {}).get("specialty") or "").strip()
                or str(row.get("role") or "").strip()
                or None
            ),
        )

    def resolve(
        self, clinician_id: UUID, patient_id: UUID, *, care_team_id: UUID | None = None
    ) -> CareTeamPlanScope:
        scopes = self.list_for_clinician(clinician_id, patient_id)
        if care_team_id is not None:
            scopes = [scope for scope in scopes if scope.care_team_id == care_team_id]
        if not scopes:
            raise AuthorizationError("No active care-team scope is available for this patient")
        if len(scopes) != 1:
            raise ValidationError("Choose the care team for this plan", code="CARE_TEAM_REQUIRED")
        return scopes[0]
