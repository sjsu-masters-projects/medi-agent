"""Which care-team-owned records a clinician may read (PLAN-002, CLN-003 slice G).

A clinician reaches a patient only through an active care-team link of their own. A patient
may have several care teams, and these records belong to ONE of them:

* documents (and the facts extracted from them), the care plan, SOAP notes, FHIR imports,
  reviewed ADR assessments and their MedWatch drafts;
* conditions the patient marks sensitive belong to the team that recorded them.

Everything below is a pure rule over rows that already carry their owner. Callers load the
owner columns (``care_team_id``, ``routing_state``, ...) in the same query as the record; a row
that does not carry them is hidden, never shown. A "Not sure" document is in every active
team's queue until one claims it, which the database does atomically (``claim_document``).

``PatientAccess`` answers one patient; ``ClinicianAccess`` answers many (lists, dashboards,
exports). ``CareTeamAccessService`` loads either from the clinician's active links. Active
membership of the link's clinic is checked where an action is taken (publication, adoption);
reading follows the link itself, exactly as the rest of the product does.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from supabase import Client

from app.core import authorization_reasons as reasons
from app.core.exceptions import AuthorizationError

_CHUNK = 100


def _text(value: Any) -> str | None:
    return str(value) if value else None


@dataclass(frozen=True)
class PatientAccess:
    """One clinician's active care-team links to one patient."""

    clinician_id: str
    patient_id: str
    team_ids: frozenset[str] = frozenset()

    def __bool__(self) -> bool:
        return bool(self.team_ids)

    def owns(self, care_team_id: Any) -> bool:
        return bool(self.team_ids) and _text(care_team_id) in self.team_ids

    def can_see_document(self, document: Mapping[str, Any]) -> bool:
        """Routed documents belong to their team; unrouted ones to every active team."""
        if not self.team_ids:
            return False
        state = document.get("routing_state")
        if state == "unrouted":
            return True
        return state == "routed" and self.owns(document.get("care_team_id"))

    def filter_documents(self, rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows if self.can_see_document(row)]

    def can_see_soap_note(self, note: Mapping[str, Any]) -> bool:
        """A note is its team's; one with no determinable team stays with its author."""
        if not self.team_ids:
            return False
        if note.get("care_team_id"):
            return self.owns(note["care_team_id"])
        return _text(note.get("clinician_id")) == self.clinician_id

    def can_see_import(self, fhir_import: Mapping[str, Any]) -> bool:
        if not self.team_ids:
            return False
        if fhir_import.get("care_team_id"):
            return self.owns(fhir_import["care_team_id"])
        return _text(fhir_import.get("clinician_id")) == self.clinician_id

    def can_see_adr(self, assessment: Mapping[str, Any]) -> bool:
        """A pending assessment is a safety item for every team; a reviewed one is its team's."""
        if not self.team_ids:
            return False
        if not assessment.get("reviewed_by"):
            return True
        if assessment.get("reviewed_by_care_team_id"):
            return self.owns(assessment["reviewed_by_care_team_id"])
        return _text(assessment.get("reviewed_by")) == self.clinician_id

    def can_see_medwatch_draft(self, draft: Mapping[str, Any]) -> bool:
        if not self.team_ids:
            return False
        return not draft.get("care_team_id") or self.owns(draft["care_team_id"])

    def can_see_condition(self, condition: Mapping[str, Any]) -> bool:
        """A sensitive condition reaches only its recording team; none recorded means none."""
        if not self.team_ids:
            return False
        if not condition.get("is_sensitive"):
            return True
        return self.owns(condition.get("recorded_by_care_team_id"))

    def split_conditions(
        self, rows: Iterable[Mapping[str, Any]]
    ) -> tuple[list[dict[str, Any]], bool]:
        """(visible conditions, whether any were withheld). Never a silently shorter list."""
        visible: list[dict[str, Any]] = []
        withheld = False
        for row in rows:
            if self.can_see_condition(row):
                visible.append(dict(row))
            else:
                withheld = True
        return visible, withheld

    def can_read_plan(self, plan: Mapping[str, Any]) -> bool:
        """A plan's detail is its owning team's. Unowned plans are listed, not opened, here."""
        return plan.get("ownership_state") == "owned" and self.owns(plan.get("care_team_id"))


@dataclass(frozen=True)
class ClinicianAccess:
    """A clinician's active links across all patients, for lists and exports."""

    clinician_id: str
    teams_by_patient: Mapping[str, frozenset[str]] = field(default_factory=dict)

    @property
    def patient_ids(self) -> list[str]:
        return sorted(self.teams_by_patient)

    def for_patient(self, patient_id: Any) -> PatientAccess:
        key = str(patient_id)
        return PatientAccess(self.clinician_id, key, self.teams_by_patient.get(key, frozenset()))

    def keep(
        self,
        rows: Iterable[Mapping[str, Any]],
        rule: str,
        *,
        patient_key: str = "patient_id",
    ) -> list[dict[str, Any]]:
        """Rows of the named record kind this clinician may read, whatever the patient."""
        checks = {
            "document": PatientAccess.can_see_document,
            "soap_note": PatientAccess.can_see_soap_note,
            "import": PatientAccess.can_see_import,
            "adr": PatientAccess.can_see_adr,
            "medwatch_draft": PatientAccess.can_see_medwatch_draft,
        }
        check = checks[rule]
        return [dict(row) for row in rows if check(self.for_patient(row.get(patient_key)), row)]


class CareTeamAccessService:
    """Loads the links; the rules above decide. Synchronous, like the other plan services."""

    def __init__(self, db: Client) -> None:
        self.db = db

    def for_patient(
        self, clinician_id: Any, patient_id: Any, *, require: bool = True
    ) -> PatientAccess:
        rows = cast(
            list[dict[str, Any]],
            self.db.table("care_teams")
            .select("id")
            .eq("clinician_id", str(clinician_id))
            .eq("patient_id", str(patient_id))
            .eq("status", "active")
            .execute()
            .data
            or [],
        )
        access = PatientAccess(
            str(clinician_id), str(patient_id), frozenset(str(row["id"]) for row in rows)
        )
        if require and not access:
            raise AuthorizationError(
                "You are not assigned to this patient",
                reason_code=reasons.NO_CARE_TEAM_ASSIGNMENT,
                actor_id=str(clinician_id),
                actor_role="clinician",
                target_type="patient",
                target_id=str(patient_id),
            )
        return access

    def for_clinician(self, clinician_id: Any) -> ClinicianAccess:
        rows = cast(
            list[dict[str, Any]],
            self.db.table("care_teams")
            .select("id, patient_id")
            .eq("clinician_id", str(clinician_id))
            .eq("status", "active")
            .execute()
            .data
            or [],
        )
        grouped: dict[str, set[str]] = {}
        for row in rows:
            if row.get("patient_id"):
                grouped.setdefault(str(row["patient_id"]), set()).add(str(row["id"]))
        return ClinicianAccess(
            str(clinician_id), {key: frozenset(value) for key, value in grouped.items()}
        )

    def visible_fact_ids(self, access: PatientAccess, fact_ids: Sequence[Any]) -> set[str]:
        """Facts whose every source this clinician may see (mirrors fact_visible_to_links).

        A fact is hidden if any source behind it is a document routed to another team (or one
        that cannot be found). A source that is not a document carries its own team; none
        recorded means it was as shared before teams existed.
        """
        wanted = [str(value) for value in dict.fromkeys(fact_ids)]
        if not wanted or not access:
            return set()
        citations: list[dict[str, Any]] = []
        for start in range(0, len(wanted), _CHUNK):
            citations += cast(
                list[dict[str, Any]],
                self.db.table("evidence_citations")
                .select("fact_id, provenance_id")
                .in_("fact_id", wanted[start : start + _CHUNK])
                .execute()
                .data
                or [],
            )
        provenance_ids = sorted({str(row["provenance_id"]) for row in citations})
        provenances: dict[str, dict[str, Any]] = {}
        for start in range(0, len(provenance_ids), _CHUNK):
            for row in cast(
                list[dict[str, Any]],
                self.db.table("source_provenances")
                .select("id, document_id, care_team_id")
                .in_("id", provenance_ids[start : start + _CHUNK])
                .execute()
                .data
                or [],
            ):
                provenances[str(row["id"])] = row
        document_ids = sorted(
            {str(row["document_id"]) for row in provenances.values() if row.get("document_id")}
        )
        documents: dict[str, dict[str, Any]] = {}
        for start in range(0, len(document_ids), _CHUNK):
            for row in cast(
                list[dict[str, Any]],
                self.db.table("documents")
                .select("id, routing_state, care_team_id")
                .in_("id", document_ids[start : start + _CHUNK])
                .execute()
                .data
                or [],
            ):
                documents[str(row["id"])] = row
        hidden: set[str] = set()
        for row in citations:
            provenance = provenances.get(str(row["provenance_id"]))
            if provenance is None:
                hidden.add(str(row["fact_id"]))
            elif provenance.get("document_id"):
                document = documents.get(str(provenance["document_id"]))
                if document is None or not access.can_see_document(document):
                    hidden.add(str(row["fact_id"]))
            elif provenance.get("care_team_id") and not access.owns(provenance["care_team_id"]):
                hidden.add(str(row["fact_id"]))
        return set(wanted) - hidden
