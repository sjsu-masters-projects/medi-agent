"""One place that decides whether a clinician may open a document, fact or import.

Every clinician read or write of a care-team-owned record goes through here, so the rule is
not re-derived per route. The rules themselves are in ``care_team_access``; this module loads
the record together with its owner columns and applies them. A record that is not visible is
reported exactly like one that does not exist.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core.exceptions import NotFoundError
from app.services.care_team_access import CareTeamAccessService, PatientAccess
from app.services.clinical_fact_service import ClinicalFactService


class ClinicianRecordGate:
    """Authorize a clinician against the owner of the record being touched."""

    def __init__(self, db: Client) -> None:
        self.db = db
        self.access_service = CareTeamAccessService(db)

    def access(self, clinician_id: UUID | str, patient_id: UUID | str) -> PatientAccess:
        """The clinician's active links to the patient; no link raises AuthorizationError."""
        return self.access_service.for_patient(clinician_id, patient_id)

    def document(
        self,
        clinician_id: UUID | str,
        patient_id: UUID | str,
        document_id: UUID | str,
        *,
        columns: str = "*",
    ) -> dict[str, Any]:
        """The document row if this clinician may see it, with its owner columns."""
        access = self.access(clinician_id, patient_id)
        select = columns if columns == "*" else f"{columns}, routing_state, care_team_id"
        rows = cast(
            list[dict[str, Any]],
            self.db.table("documents")
            .select(select)
            .eq("id", str(document_id))
            .eq("patient_id", str(patient_id))
            .limit(1)
            .execute()
            .data
            or [],
        )
        if not rows or not access.can_see_document(rows[0]):
            raise NotFoundError("Document", str(document_id))
        return rows[0]

    def fact(
        self, clinician_id: UUID | str, patient_id: UUID | str, fact_id: UUID | str
    ) -> PatientAccess:
        """Require that the fact exists for this patient and every source behind it is visible."""
        access = self.access(clinician_id, patient_id)
        exists = (
            self.db.table("clinical_facts")
            .select("id")
            .eq("id", str(fact_id))
            .eq("patient_id", str(patient_id))
            .limit(1)
            .execute()
            .data
        )
        if not exists or str(fact_id) not in self.access_service.visible_fact_ids(
            access, [fact_id]
        ):
            raise NotFoundError("Clinical fact", str(fact_id))
        return access

    def visible_facts(
        self, access: PatientAccess, facts: Iterable[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        rows = list(facts)
        allowed = self.access_service.visible_fact_ids(access, [row["id"] for row in rows])
        return [row for row in rows if str(row["id"]) in allowed]

    def fhir_import(
        self, clinician_id: UUID | str, patient_id: UUID | str, import_id: UUID | str
    ) -> dict[str, Any]:
        """The import row if this clinician may see it (its team, or its importing clinician)."""
        access = self.access(clinician_id, patient_id)
        rows = cast(
            list[dict[str, Any]],
            self.db.table("fhir_imports")
            .select("id, patient_id, clinician_id, care_team_id")
            .eq("id", str(import_id))
            .eq("patient_id", str(patient_id))
            .limit(1)
            .execute()
            .data
            or [],
        )
        if not rows or not access.can_see_import(rows[0]):
            raise NotFoundError("FHIR import", str(import_id))
        return rows[0]

    def hidden_import_ids(self, access: PatientAccess, import_ids: Sequence[str]) -> set[str]:
        """Imports among ``import_ids`` this clinician may NOT see (missing ones are hidden)."""
        wanted = sorted(set(import_ids))
        if not wanted:
            return set()
        rows = cast(
            list[dict[str, Any]],
            self.db.table("fhir_imports")
            .select("id, clinician_id, care_team_id")
            .in_("id", wanted)
            .execute()
            .data
            or [],
        )
        shown = {str(row["id"]) for row in rows if access.can_see_import(row)}
        return set(wanted) - shown


class ClinicianFactService:
    """Clinician-facing fact reads and review writes, each gated by the fact's source owners."""

    def __init__(self, db: Client) -> None:
        self.gate = ClinicianRecordGate(db)
        self.facts = ClinicalFactService(db)

    def get_fact(self, *, clinician_id: UUID, patient_id: UUID, fact_id: UUID) -> dict[str, Any]:
        self.gate.fact(clinician_id, patient_id, fact_id)
        return self.facts.get_fact(fact_id, patient_id)

    def lineage(self, *, clinician_id: UUID, patient_id: UUID, fact_id: UUID) -> dict[str, Any]:
        self.gate.fact(clinician_id, patient_id, fact_id)
        return self.facts.get_lineage(fact_id, patient_id)

    def reject(
        self, *, clinician_id: UUID, patient_id: UUID, fact_id: UUID, note: str
    ) -> dict[str, Any]:
        self.gate.fact(clinician_id, patient_id, fact_id)
        return self.facts.reject(fact_id, patient_id, reviewer_id=clinician_id, note=note)

    def correct(
        self,
        *,
        clinician_id: UUID,
        patient_id: UUID,
        fact_id: UUID,
        value: dict[str, Any],
        note: str,
    ) -> dict[str, Any]:
        self.gate.fact(clinician_id, patient_id, fact_id)
        return self.facts.correct(
            fact_id, patient_id, actor_id=clinician_id, value=value, note=note
        )
