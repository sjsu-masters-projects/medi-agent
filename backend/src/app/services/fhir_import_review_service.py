"""Clinician-facing review reads for provenance-backed SMART candidates."""

from __future__ import annotations

from collections import Counter
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.models.clinical_fact import ClinicalFactReviewState


class FhirImportReviewService:
    """Read mapped FHIR candidates without changing their clinical review state."""

    _FHIR_ENVELOPE_PREFIX = "fhir_import_resources/"

    def __init__(self, db: Client) -> None:
        self.db = db

    def list_facts(
        self,
        *,
        patient_id: UUID,
        review_state: ClinicalFactReviewState,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        """Return one review-state page plus small, patient-scoped review counts."""
        metadata_result = (
            self.db.table("clinical_facts")
            .select("fact_type, review_state")
            .eq("patient_id", str(patient_id))
            .execute()
        )
        metadata = cast(list[dict[str, Any]], metadata_result.data or [])
        visible_metadata = [
            row
            for row in metadata
            if row.get("review_state") != ClinicalFactReviewState.DELETED.value
        ]
        state_counts = Counter(str(row.get("review_state", "unknown")) for row in visible_metadata)
        fact_type_counts = Counter(str(row.get("fact_type", "unknown")) for row in visible_metadata)

        page_result = (
            self.db.table("clinical_facts")
            .select("*")
            .eq("patient_id", str(patient_id))
            .eq("review_state", review_state.value)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        facts = cast(list[dict[str, Any]], page_result.data or [])
        sources = self._sources_for_facts(facts)

        return {
            "patient_id": str(patient_id),
            "review_state": review_state.value,
            "facts": [{**fact, "source": sources.get(str(fact.get("id")))} for fact in facts],
            "total_count": state_counts.get(review_state.value, 0),
            "state_counts": dict(state_counts),
            "fact_type_counts": dict(fact_type_counts),
            "offset": offset,
            "limit": limit,
        }

    def _sources_for_facts(self, facts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        fact_ids = [str(row["id"]) for row in facts if row.get("id")]
        if not fact_ids:
            return {}
        citations_result = (
            self.db.table("evidence_citations")
            .select("fact_id, provenance_id")
            .in_("fact_id", fact_ids)
            .execute()
        )
        citations = cast(list[dict[str, Any]], citations_result.data or [])
        provenance_by_fact = {
            str(row["fact_id"]): str(row["provenance_id"])
            for row in citations
            if row.get("fact_id") and row.get("provenance_id")
        }
        provenance_ids = sorted(set(provenance_by_fact.values()))
        if not provenance_ids:
            return {}
        provenance_result = (
            self.db.table("source_provenances")
            .select("id, source_system, source_reference")
            .in_("id", provenance_ids)
            .execute()
        )
        provenances = cast(list[dict[str, Any]], provenance_result.data or [])
        provenance_by_id = {str(row["id"]): row for row in provenances if row.get("id")}
        envelope_ids = sorted(
            {
                str(row["source_reference"])[len(self._FHIR_ENVELOPE_PREFIX) :]
                for row in provenances
                if isinstance(row.get("source_reference"), str)
                and str(row["source_reference"]).startswith(self._FHIR_ENVELOPE_PREFIX)
            }
        )
        if not envelope_ids:
            return {}
        envelope_result = (
            self.db.table("fhir_import_resources")
            .select(
                "id, issuer, resource_type, external_resource_id, version_id, mapping_warnings, validation_errors"
            )
            .in_("id", envelope_ids)
            .execute()
        )
        envelopes = cast(list[dict[str, Any]], envelope_result.data or [])
        envelope_by_id = {str(row["id"]): row for row in envelopes if row.get("id")}

        result: dict[str, dict[str, Any]] = {}
        for fact_id, provenance_id in provenance_by_fact.items():
            provenance = provenance_by_id.get(provenance_id)
            if not provenance:
                continue
            source_reference = provenance.get("source_reference")
            if not isinstance(source_reference, str) or not source_reference.startswith(
                self._FHIR_ENVELOPE_PREFIX
            ):
                continue
            envelope = envelope_by_id.get(source_reference[len(self._FHIR_ENVELOPE_PREFIX) :])
            if not envelope:
                continue
            result[fact_id] = {
                "issuer": envelope.get("issuer") or provenance.get("source_system"),
                "resource_type": envelope.get("resource_type") or "FHIR resource",
                "external_resource_id": envelope.get("external_resource_id"),
                "version_id": envelope.get("version_id"),
                "mapping_warnings": envelope.get("mapping_warnings") or [],
                "validation_errors": envelope.get("validation_errors") or [],
            }
        return result

    def get_source(self, *, fact_id: UUID, patient_id: UUID) -> dict[str, Any] | None:
        """Return one original FHIR envelope only after the caller authorizes the fact."""
        fact_result = (
            self.db.table("clinical_facts")
            .select("id")
            .eq("id", str(fact_id))
            .eq("patient_id", str(patient_id))
            .single()
            .execute()
        )
        if not fact_result.data:
            return None
        citation_result = (
            self.db.table("evidence_citations")
            .select("provenance_id")
            .eq("fact_id", str(fact_id))
            .execute()
        )
        citations = cast(list[dict[str, Any]], citation_result.data or [])
        provenance_id = next(
            (str(row["provenance_id"]) for row in citations if row.get("provenance_id")), None
        )
        if provenance_id is None:
            return None
        provenance_result = (
            self.db.table("source_provenances")
            .select("source_system, source_reference")
            .eq("id", provenance_id)
            .single()
            .execute()
        )
        provenance = cast(dict[str, Any] | None, provenance_result.data)
        if provenance is None:
            return None
        source_reference = provenance.get("source_reference")
        if not isinstance(source_reference, str) or not source_reference.startswith(
            self._FHIR_ENVELOPE_PREFIX
        ):
            return None
        envelope_result = (
            self.db.table("fhir_import_resources")
            .select(
                "issuer, resource_type, external_resource_id, version_id, mapping_warnings, validation_errors, raw_resource"
            )
            .eq("id", source_reference[len(self._FHIR_ENVELOPE_PREFIX) :])
            .single()
            .execute()
        )
        envelope = cast(dict[str, Any] | None, envelope_result.data)
        if not envelope:
            return None
        return {
            "issuer": envelope.get("issuer") or provenance.get("source_system"),
            "resource_type": envelope.get("resource_type") or "FHIR resource",
            "external_resource_id": envelope.get("external_resource_id"),
            "version_id": envelope.get("version_id"),
            "mapping_warnings": envelope.get("mapping_warnings") or [],
            "validation_errors": envelope.get("validation_errors") or [],
            "raw_resource": envelope.get("raw_resource") or {},
        }
