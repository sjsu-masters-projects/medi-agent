"""Audited re-projection of untouched FHIR candidate display values."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, cast
from uuid import UUID, uuid4

from supabase import Client

from app.core.exceptions import ValidationError
from app.services.fhir_import_service import FhirImportService

MAPPER_VERSION = "fhir-r4-candidate-v2"


@dataclass(frozen=True)
class FhirCandidateReprojectionProposal:
    """One reviewed difference between a pending candidate and its raw FHIR source."""

    fact_id: str
    patient_id: str
    fact_type: str
    source_resource_id: str
    source_version: str | None
    mapper_version: str
    prior_value: dict[str, Any]
    projected_value: dict[str, Any]
    changed_fields: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FhirCandidateReprojectionService:
    """Create dry-run proposals and apply only reviewed pending FHIR candidates."""

    def __init__(self, db: Client) -> None:
        self.db = db

    def list_proposals(
        self, *, patient_id: UUID | None = None
    ) -> list[FhirCandidateReprojectionProposal]:
        """Return candidate diffs without writing any data."""
        facts = self._untouched_pending_facts(patient_id=patient_id)
        if not facts:
            return []
        sources_by_fact = self._sources_by_fact([str(fact["id"]) for fact in facts])
        proposals: list[FhirCandidateReprojectionProposal] = []
        for fact in facts:
            proposal = self._proposal_for(
                fact=fact, sources=sources_by_fact.get(str(fact["id"]), [])
            )
            if proposal is not None:
                proposals.append(proposal)
        return proposals

    def apply(
        self,
        proposal: FhirCandidateReprojectionProposal,
        *,
        actor_id: UUID,
        idempotency_key: UUID | None = None,
    ) -> dict[str, Any]:
        """Apply one previously reviewed proposal through the guarded database transaction."""
        result = self.db.rpc(
            "apply_pending_fhir_candidate_reprojection",
            {
                "p_fact_id": proposal.fact_id,
                "p_actor_id": str(actor_id),
                "p_mapper_version": proposal.mapper_version,
                "p_source_version": proposal.source_version,
                "p_projected_value": proposal.projected_value,
                "p_idempotency_key": str(idempotency_key or uuid4()),
            },
        ).execute()
        data = result.data
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict):
            raise ValidationError("Could not apply FHIR candidate reprojection")
        return data

    def _untouched_pending_facts(self, *, patient_id: UUID | None) -> list[dict[str, Any]]:
        query = (
            self.db.table("clinical_facts")
            .select("id, patient_id, fact_type, value, external_source_version")
            .eq("review_state", "pending_review")
            .eq("reconciliation_state", "not_started")
        )
        if patient_id is not None:
            query = query.eq("patient_id", str(patient_id))
        facts = cast(list[dict[str, Any]], query.execute().data or [])
        audit_rows = cast(
            list[dict[str, Any]],
            self.db.table("clinical_fact_audit_events")
            .select("fact_id, event_type")
            .in_("fact_id", [str(fact["id"]) for fact in facts])
            .execute()
            .data
            or [],
        )
        touched = {
            str(row["fact_id"]) for row in audit_rows if row.get("event_type") not in {"created"}
        }
        return [fact for fact in facts if str(fact["id"]) not in touched]

    def _sources_by_fact(self, fact_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        citations = cast(
            list[dict[str, Any]],
            self.db.table("evidence_citations")
            .select("fact_id, provenance_id")
            .in_("fact_id", fact_ids)
            .execute()
            .data
            or [],
        )
        provenance_ids = sorted(
            {str(row["provenance_id"]) for row in citations if row.get("provenance_id")}
        )
        if not provenance_ids:
            return {}
        provenances = cast(
            list[dict[str, Any]],
            self.db.table("source_provenances")
            .select("id, source_reference")
            .in_("id", provenance_ids)
            .execute()
            .data
            or [],
        )
        resource_by_provenance = {
            str(row["id"]): str(row["source_reference"]).removeprefix("fhir_import_resources/")
            for row in provenances
            if isinstance(row.get("source_reference"), str)
            and str(row["source_reference"]).startswith("fhir_import_resources/")
        }
        resource_ids = sorted(set(resource_by_provenance.values()))
        if not resource_ids:
            return {}
        resources = cast(
            list[dict[str, Any]],
            self.db.table("fhir_import_resources")
            .select("id, resource_type, version_id, content_hash, raw_resource")
            .in_("id", resource_ids)
            .execute()
            .data
            or [],
        )
        resources_by_id = {str(row["id"]): row for row in resources}
        sources: dict[str, list[dict[str, Any]]] = {}
        for citation in citations:
            resource_id = resource_by_provenance.get(str(citation.get("provenance_id")))
            resource = resources_by_id.get(resource_id or "")
            if resource is not None:
                sources.setdefault(str(citation["fact_id"]), []).append(resource)
        return sources

    @staticmethod
    def _proposal_for(
        *, fact: dict[str, Any], sources: list[dict[str, Any]]
    ) -> FhirCandidateReprojectionProposal | None:
        prior = fact.get("value")
        if not isinstance(prior, dict):
            return None
        for source in sources:
            source_version = FhirCandidateReprojectionService._source_version(source)
            if fact.get("external_source_version") != source_version:
                continue
            if not isinstance(source.get("raw_resource"), dict):
                continue
            mapped = FhirImportService._map_resource(cast(dict[str, Any], source["raw_resource"]))
            if mapped is None or mapped.get("fact_type") != fact.get("fact_type"):
                continue
            projected = mapped.get("value")
            if not isinstance(projected, dict) or prior == projected:
                continue
            return FhirCandidateReprojectionProposal(
                fact_id=str(fact["id"]),
                patient_id=str(fact["patient_id"]),
                fact_type=str(fact["fact_type"]),
                source_resource_id=str(source["id"]),
                source_version=str(source_version) if source_version is not None else None,
                mapper_version=MAPPER_VERSION,
                prior_value=prior,
                projected_value=projected,
                changed_fields=FhirCandidateReprojectionService._changed_fields(prior, projected),
            )
        return None

    @staticmethod
    def _source_version(source: dict[str, Any]) -> str | None:
        """Mirror import-time version semantics for resources without meta.versionId."""
        version_id = source.get("version_id")
        content_hash = source.get("content_hash")
        if version_id is not None:
            return str(version_id)
        return str(content_hash) if content_hash is not None else None

    @staticmethod
    def _changed_fields(prior: dict[str, Any], projected: dict[str, Any]) -> list[str]:
        return sorted(
            key for key in set(prior) | set(projected) if prior.get(key) != projected.get(key)
        )
